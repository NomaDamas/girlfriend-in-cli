from __future__ import annotations

import os
import queue
import select
import sys
import termios
import threading
import time
import tty
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .engine import ConversationSession, utc_now
from .models import MOOD_EMOJI, ChatMessage, Persona, ProviderReply, RuntimeTrace
from .personas import load_persona
from .providers import ProviderConfig, build_provider
from .session_io import export_session, load_session_messages
from .music import build_music_player
from .voice import build_voice_input, build_voice_output


@dataclass(slots=True)
class AppConfig:
    persona_path: Path
    persona_override: Persona | None = None
    provider_name: str = "heuristic"
    provider_model: str | None = None
    server_base_url: str | None = None
    persona_id: str | None = None
    performance_mode: str = "turbo"
    voice_output: bool = False
    voice_input_command: str | None = None
    show_trace: bool = True
    input_poll_active_seconds: float = 0.03
    input_poll_idle_seconds: float = 0.08
    session_dir: Path = Path("sessions")
    export_on_exit: bool = True
    resume_path: Path | None = None


@dataclass(slots=True)
class PendingDelivery:
    kind: str
    text: str
    due_at: float
    trace_note: str
    typing_starts_at: float | None = None  # when to show "typing..." indicator


class BackgroundJob:
    def __init__(self, kind: str, target: Callable[..., Any], *args: Any) -> None:
        self.kind = kind
        self._result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)
        self._thread = threading.Thread(
            target=self._runner,
            args=(target, *args),
            daemon=True,
        )
        self._thread.start()

    def _runner(self, target: Callable[..., Any], *args: Any) -> None:
        try:
            self._result_queue.put((True, target(*args)))
        except Exception as exc:  # pragma: no cover - surfaced in UI
            self._result_queue.put((False, exc))

    def poll(self) -> tuple[bool, Any] | None:
        try:
            return self._result_queue.get_nowait()
        except queue.Empty:
            return None


class RawKeyboard:
    """Hybrid keyboard: raw mode for special keys, readline for text input."""

    def __init__(self) -> None:
        self.fd = sys.stdin.fileno()
        self._old_settings: list[Any] | None = None
        self._raw = False

    def __enter__(self) -> "RawKeyboard":
        if not sys.stdin.isatty():
            raise RuntimeError("Interactive chat requires a TTY.")
        self._old_settings = termios.tcgetattr(self.fd)
        self._enter_raw()
        return self

    def __exit__(self, *_: Any) -> None:
        if self._old_settings is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._old_settings)

    def _enter_raw(self) -> None:
        if not self._raw:
            tty.setcbreak(self.fd)
            self._raw = True

    def _exit_raw(self) -> None:
        if self._raw and self._old_settings is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._old_settings)
            self._raw = False

    def poll(self, timeout: float) -> str | None:
        """Poll for special keys (Esc, arrows, Ctrl+C/D, Enter)."""
        if not self._raw:
            self._enter_raw()
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if not ready:
            return None
        data = os.read(self.fd, 64)
        if not data:
            return None
        if data[0:1] == b"\x1b":
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 0)
                if not ready:
                    break
                data += os.read(self.fd, 1)
            return data.decode(errors="ignore")
        # Drain any additional pending bytes
        time.sleep(0.02)
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0)
            if not ready:
                break
            extra = os.read(self.fd, 64)
            if not extra:
                break
            data += extra
        return data.decode(errors="replace")

    def read_line(self, live: Any, prefill: str = "") -> str | None:
        """Temporarily exit raw mode to use readline for Korean IME support."""
        self._exit_raw()
        live.stop()
        try:
            # Show input prompt with prefilled character
            sys.stdout.write(f"\r\033[K  \033[1;35m>\033[0m {prefill}")
            sys.stdout.flush()
            if prefill:
                # Use readline with pre-inserted text
                try:
                    import readline
                    readline.set_startup_hook(lambda: readline.insert_text(prefill))
                    try:
                        line = input()
                    finally:
                        readline.set_startup_hook()
                except ImportError:
                    line = input()
                    line = prefill + line
            else:
                line = input()
            return line.strip()
        except (EOFError, KeyboardInterrupt):
            return None
        finally:
            self._enter_raw()
            live.start()


def run_chat_app(config: AppConfig) -> int:
    console = Console()
    if not _supports_interactive_chat():
        console.print(
            "Interactive chat requires a TTY. Run `girlfriend-generator` in a real terminal.",
            style="bold red",
        )
        return 1

    persona = config.persona_override or load_persona(config.persona_path)
    provider = build_provider(
        ProviderConfig(
            name=config.provider_name,
            model=config.provider_model,
            performance_mode=config.performance_mode,
            server_base_url=config.server_base_url,
            persona_id=config.persona_id,
        )
    )
    voice_output = build_voice_output(config.voice_output)
    voice_input = build_voice_input(config.voice_input_command)
    music_player = build_music_player()
    trace = RuntimeTrace(
        persona_path=config.persona_path,
        provider_name=config.provider_name,
        provider_model=config.provider_model,
        performance_mode=config.performance_mode,
        voice_output_name=voice_output.name,
        voice_input_name=voice_input.name,
    )
    session = ConversationSession(persona=persona)
    if config.resume_path and config.resume_path.exists():
        resumed_messages = load_session_messages(config.resume_path)
        session.messages = resumed_messages
        session.awaiting_user_reply = False
        session.schedule_initiative()
        session.add_system_message(f"Session resumed ({len(resumed_messages)} messages loaded)")
    else:
        session.bootstrap()

    draft = ""
    status_line = "Enter to send. /help for commands."
    pending_job: BackgroundJob | None = None
    pending_delivery: PendingDelivery | None = None
    last_key_at = time.monotonic()
    show_trace = config.show_trace
    last_render_key: tuple[Any, ...] | None = None
    scroll_offset = 0  # 0 = latest messages, positive = scrolled up
    voice_output_enabled = config.voice_output and voice_output.name != "off"

    try:
        with RawKeyboard() as keyboard, Live(
            _render_screen(
                console=console,
                persona=persona,
                session=session,
                draft=draft,
                trace=trace,
                show_trace=show_trace,
                status_line=status_line,
                assistant_typing=False,
                user_typing=False,
            ),
            console=console,
            screen=True,
            auto_refresh=False,
            refresh_per_second=15,
        ) as live:
            while True:
                now = utc_now()
                current_monotonic = time.monotonic()
                user_typing = bool(draft) and (current_monotonic - last_key_at) < 1.6

                if pending_job is not None:
                    result = pending_job.poll()
                    if result is not None:
                        pending_job, pending_delivery, status_line = _finish_job(
                            session=session,
                            persona=persona,
                            provider=provider,
                            result=result,
                            previous_job=pending_job,
                            previous_delivery=pending_delivery,
                            previous_status=status_line,
                        )

                if pending_delivery and time.monotonic() >= pending_delivery.due_at:
                    if pending_delivery.kind == "nudge":
                        delivered_text = session.consume_nudge()
                    elif pending_delivery.kind == "initiative":
                        delivered_text = session.consume_initiative(pending_delivery.text)
                    else:
                        delivered_text = pending_delivery.text
                        session.add_assistant_message(delivered_text, schedule_nudge=True)
                    trace.status_line = pending_delivery.trace_note
                    status_line = pending_delivery.trace_note
                    if voice_output_enabled:
                        voice_output.speak(delivered_text)
                    pending_delivery = None

                if session.nudge_due(now) and pending_job is None and pending_delivery is None:
                    pending_delivery = PendingDelivery(
                        kind="nudge",
                        text=session.next_nudge_text(),
                        due_at=time.monotonic() + 1.2,
                        trace_note="idle-nudge: assistant escalated after no reply",
                    )
                elif (
                    session.initiative_due(now)
                    and pending_job is None
                    and pending_delivery is None
                    and not draft
                ):
                    pending_delivery = PendingDelivery(
                        kind="initiative",
                        text=provider.generate_initiative(
                            persona,
                            session.recent_history(),
                            session.affection_score,
                        ),
                        due_at=time.monotonic() + 0.9,
                        trace_note="idle-initiative: assistant started a fresh conversation",
                    )

                trace.pending_reply_kind = _pending_activity_kind(
                    pending_job=pending_job,
                    pending_delivery=pending_delivery,
                )
                trace.pending_nudge_in = session.seconds_until_nudge(now)
                trace.pending_initiative_in = session.seconds_until_initiative(now)
                _sync_provider_trace(provider, trace)
                trace.status_line = status_line
                music_player.update_mood(session.mood.current)

                poll_timeout = (
                    config.input_poll_active_seconds
                    if (pending_job is not None or pending_delivery is not None or draft)
                    else config.input_poll_idle_seconds
                )
                key = keyboard.poll(poll_timeout)
                if key is not None:
                    last_key_at = time.monotonic()

                    # Any printable key or Enter → readline mode for Korean IME
                    is_printable = len(key) == 1 and key.isprintable()
                    is_enter = key in {"\r", "\n"}
                    if (is_printable or is_enter) and not _assistant_busy(pending_job, pending_delivery):
                        # Pre-fill with the typed character if printable
                        prefill = key if is_printable else ""
                        text = keyboard.read_line(live, prefill=prefill)
                        if text is None:
                            continue
                        if not text:
                            continue
                        if text.startswith("/"):
                            # Command
                            outcome = _handle_key(
                                key="\r", draft=text, session=session,
                                persona=persona, provider=provider,
                                pending_job=pending_job, pending_delivery=pending_delivery,
                                voice_input=voice_input,
                                voice_output_available=voice_output.name != "off",
                                voice_output_enabled=voice_output_enabled,
                                show_trace=show_trace, session_dir=config.session_dir,
                                music_player=music_player,
                            )
                        else:
                            # Normal message — send directly
                            session.add_user_message(text)
                            scroll_offset = 0
                            mood = session.mood.current
                            pending_job = BackgroundJob(
                                "reply", provider.generate_reply,
                                persona, session.recent_history(),
                                text, session.affection_score, mood,
                            )
                            draft = ""
                            status_line = "..."
                            continue
                    else:
                        outcome = _handle_key(
                            key=key, draft=draft, session=session,
                            persona=persona, provider=provider,
                            pending_job=pending_job, pending_delivery=pending_delivery,
                            voice_input=voice_input,
                            voice_output_available=voice_output.name != "off",
                            voice_output_enabled=voice_output_enabled,
                            show_trace=show_trace, session_dir=config.session_dir,
                            music_player=music_player,
                        )
                    draft = outcome["draft"]
                    status_line = outcome["status_line"]
                    pending_job = outcome["pending_job"]
                    show_trace = outcome["show_trace"]
                    voice_output_enabled = outcome["voice_output_enabled"]
                    if "scroll_delta" in outcome:
                        scroll_offset = max(0, scroll_offset + outcome["scroll_delta"])
                        max_scroll = max(0, len(session.messages) - 4)
                        scroll_offset = min(scroll_offset, max_scroll)
                        if scroll_offset == 0:
                            status_line = "Latest messages."
                    if outcome.get("quit"):
                        if outcome.get("back"):
                            return 2  # signal: back to main menu
                        live.update(
                            _render_screen(
                                console=console,
                                persona=persona,
                                session=session,
                                draft=draft,
                                trace=trace,
                                show_trace=show_trace,
                                status_line="Session closed.",
                                assistant_typing=False,
                                user_typing=False,
                            ),
                            refresh=True,
                        )
                        return 0

                render_key = _build_render_key(
                    session=session,
                    draft=draft,
                    trace=trace,
                    show_trace=show_trace,
                    status_line=status_line,
                    assistant_typing=_show_typing_indicator(pending_job, pending_delivery),
                    user_typing=user_typing,
                    scroll_offset=scroll_offset,
                )
                if render_key != last_render_key:
                    live.update(
                        _render_screen(
                            console=console,
                            persona=persona,
                            session=session,
                            draft=draft,
                            trace=trace,
                            show_trace=show_trace,
                            status_line=status_line,
                            assistant_typing=_show_typing_indicator(pending_job, pending_delivery),
                            user_typing=user_typing,
                            scroll_offset=scroll_offset,
                        ),
                        refresh=True,
                    )
                    last_render_key = render_key
    finally:
        music_player.stop()
        if config.export_on_exit and session.messages:
            export_session(
                session_dir=config.session_dir,
                persona=persona,
                messages=session.messages,
            )


def _finish_job(
    session: ConversationSession,
    persona: Persona,
    provider: Any,
    result: tuple[bool, Any],
    previous_job: BackgroundJob,
    previous_delivery: PendingDelivery | None,
    previous_status: str,
) -> tuple[BackgroundJob | None, PendingDelivery | None, str]:
    ok, value = result
    if not ok:
        session.add_system_message(f"{previous_job.kind} failed: {value}")
        return None, previous_delivery, f"{previous_job.kind} failed"

    if previous_job.kind == "listen":
        transcript = str(value)
        session.add_user_message(transcript)
        return (
            BackgroundJob(
                "reply",
                provider.generate_reply,
                persona,
                session.recent_history(),
                transcript,
                session.affection_score,
                session.mood.current,
            ),
            previous_delivery,
            "voice transcript captured",
        )

    if previous_job.kind == "reply":
        reply = value
        if not isinstance(reply, ProviderReply):
            session.add_system_message("Unexpected reply object from provider.")
            return None, previous_delivery, previous_status
        # Add "seen" delay before typing indicator shows (1-2.5s)
        import random
        seen_delay = random.uniform(1.0, 2.5)
        now = time.monotonic()
        delivery = PendingDelivery(
            kind="reply",
            text=reply.text,
            due_at=now + seen_delay + reply.typing_seconds,
            typing_starts_at=now + seen_delay,
            trace_note=reply.trace_note,
        )
        return None, delivery, reply.trace_note

    return None, previous_delivery, previous_status


def _handle_key(
    key: str,
    draft: str,
    session: ConversationSession,
    persona: Persona,
    provider: Any,
    pending_job: BackgroundJob | None,
    pending_delivery: PendingDelivery | None,
    voice_input: Any,
    voice_output_available: bool,
    voice_output_enabled: bool,
    show_trace: bool,
    session_dir: Path,
    music_player: Any = None,
) -> dict[str, Any]:
    # Scroll: arrow keys when draft is empty, also [ and ]
    is_scroll_up = key in ("\x1b[A", "\x1b[5~", "[")
    is_scroll_down = key in ("\x1b[B", "\x1b[6~", "]")
    if is_scroll_up and not draft:
        return {
            "draft": draft,
            "status_line": "↑ Scrolled up. ↓ to scroll down.",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
            "scroll_delta": 2,
        }
    if is_scroll_down and not draft:
        return {
            "draft": draft,
            "status_line": "Latest messages.",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
            "scroll_delta": -2,
        }
    if key in {"\x03", "\x04"}:
        return {
            "draft": draft,
            "status_line": "Session closed.",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": True,
        }

    if key == "\x1b":
        if draft:
            # Esc with draft: clear draft
            return {
                "draft": "",
                "status_line": "Draft cleared.",
                "pending_job": pending_job,
                "show_trace": show_trace,
                "voice_output_enabled": voice_output_enabled,
                "quit": False,
            }
        # Esc with empty draft: back to menu
        return {
            "draft": "",
            "status_line": "Back to main menu.",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": True,
            "back": True,
        }

    if key in {"\r", "\n"}:
        text = draft.strip()
        if not text:
            return {
                "draft": draft,
                "status_line": "Empty message skipped.",
                "pending_job": pending_job,
                "show_trace": show_trace,
                "voice_output_enabled": voice_output_enabled,
                "quit": False,
            }
        if _assistant_busy(pending_job, pending_delivery):
            session.add_system_message(
                "Wait for the current assistant turn to finish first."
            )
            return {
                "draft": draft,
                "status_line": "Assistant is still busy.",
                "pending_job": pending_job,
                "show_trace": show_trace,
                "voice_output_enabled": voice_output_enabled,
                "quit": False,
            }
        if text.startswith("/"):
            return _handle_command(
                text=text,
                session=session,
                provider=provider,
                pending_job=pending_job,
                pending_delivery=pending_delivery,
                voice_input=voice_input,
                voice_output_available=voice_output_available,
                voice_output_enabled=voice_output_enabled,
                show_trace=show_trace,
                session_dir=session_dir,
                music_player=music_player,
            )
        session.add_user_message(text)
        mood = session.mood.current
        job = BackgroundJob(
            "reply",
            provider.generate_reply,
            persona,
            session.recent_history(),
            text,
            session.affection_score,
            mood,
        )
        return {
            "draft": "",
            "status_line": "assistant is thinking...",
            "pending_job": job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
        }

    if key in {"\x7f", "\b"}:
        return {
            "draft": draft[:-1],
            "status_line": "Editing draft...",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
        }

    if key.isprintable():
        return {
            "draft": draft + key,
            "status_line": "Editing draft...",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
        }

    return {
        "draft": draft,
        "status_line": "Unsupported key ignored.",
        "pending_job": pending_job,
        "show_trace": show_trace,
        "voice_output_enabled": voice_output_enabled,
        "quit": False,
    }


def _handle_command(
    text: str,
    session: ConversationSession,
    provider: Any,
    pending_job: BackgroundJob | None,
    pending_delivery: PendingDelivery | None,
    voice_input: Any,
    voice_output_available: bool,
    voice_output_enabled: bool,
    show_trace: bool,
    session_dir: Path,
    music_player: Any = None,
) -> dict[str, Any]:
    lowered = text.lower()
    if lowered == "/quit":
        return {
            "draft": "",
            "status_line": "Session closed.",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": True,
        }
    if lowered == "/back":
        return {
            "draft": "",
            "status_line": "Back to main menu.",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": True,
            "back": True,
        }
    if lowered == "/help":
        session.add_system_message(
            "Commands: /help /back /quit /trace /status /affection /export /music /voice on|off /listen"
        )
        return {
            "draft": "",
            "status_line": "Help opened in chat.",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
        }
    if lowered == "/trace":
        return {
            "draft": "",
            "status_line": "Trace panel toggled.",
            "pending_job": pending_job,
            "show_trace": not show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
        }
    if lowered == "/status":
        session.add_system_message(
            "affection="
            f"{session.affection_score}/100, "
            f"nudge_in={session.seconds_until_nudge() or '-'}, "
            f"pending_activity={_pending_activity_kind(pending_job, pending_delivery)}"
        )
        return {
            "draft": "",
            "status_line": "Session status posted.",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
        }
    if lowered == "/affection":
        report = session.affection_report()
        hearts = "❤️" * report["level"] + "🤍" * (5 - report["level"])
        bar_filled = report["score"] // 5
        bar_empty = 20 - bar_filled
        bar = "█" * bar_filled + "░" * bar_empty

        lines = [
            f"{'─' * 36}",
            f"  {hearts}  {report['label']}",
            f"  [{bar}] {report['score']}/100",
            f"{'─' * 36}",
            f"  Messages:  you {report['total_user']}  /  {session.persona.name} {report['total_assistant']}",
            f"  Avg length: {report['avg_msg_length']} chars",
            f"  Positive:  {report['positive_messages']}  |  Negative: {report['negative_messages']}",
            f"  Mood: {report['mood']} (intensity {report['mood_intensity']:.1f})",
            f"{'─' * 36}",
            f"  Tip: {report['tip']}",
            f"{'─' * 36}",
        ]
        session.add_system_message("\n".join(lines))
        return {
            "draft": "",
            "status_line": "Affection report posted.",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
        }
    if lowered == "/reload":
        session.add_system_message(
            "Persona reload is startup-bound for now. Restart the app after editing the persona file."
        )
        return {
            "draft": "",
            "status_line": "Persona reload requires restart.",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
        }
    if lowered == "/export":
        json_path, markdown_path = export_session(
            session_dir=session_dir,
            persona=session.persona,
            messages=session.messages,
        )
        session.add_system_message(
            f"Exported session to {json_path} and {markdown_path}"
        )
        return {
            "draft": "",
            "status_line": "Session exported.",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
        }
    if lowered in {"/voice on", "/voice off"}:
        if not voice_output_available:
            session.add_system_message(
                "Voice output backend is unavailable in this environment."
            )
            return {
                "draft": "",
                "status_line": "Voice output unavailable.",
                "pending_job": pending_job,
                "show_trace": show_trace,
                "voice_output_enabled": False,
                "quit": False,
            }
        enabled = lowered == "/voice on"
        session.add_system_message(f"Voice output {'enabled' if enabled else 'disabled'}.")
        return {
            "draft": "",
            "status_line": f"Voice output {'enabled' if enabled else 'disabled'}.",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": enabled,
            "quit": False,
        }
    if lowered in {"/music", "/music on", "/music off"}:
        if music_player is None or music_player.name == "unavailable":
            session.add_system_message("Music is unavailable (requires macOS afplay).")
            return {
                "draft": "",
                "status_line": "Music unavailable.",
                "pending_job": pending_job,
                "show_trace": show_trace,
                "voice_output_enabled": voice_output_enabled,
                "quit": False,
            }
        if lowered == "/music on":
            music_player.enabled = True
            music_player.update_mood(session.mood.current)
            session.add_system_message("Music enabled. Add .mp3 files to music/{mood}/ folders.")
        elif lowered == "/music off":
            music_player.enabled = False
            music_player.stop()
            session.add_system_message("Music disabled.")
        else:
            result = music_player.toggle()
            if result:
                music_player.update_mood(session.mood.current)
            session.add_system_message(f"Music {'enabled' if result else 'disabled'}.")
        return {
            "draft": "",
            "status_line": f"Music {music_player.name}.",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
        }
    if lowered == "/listen":
        if _assistant_busy(pending_job, pending_delivery):
            session.add_system_message(
                "Wait for the current assistant turn to finish first."
            )
            return {
                "draft": "",
                "status_line": "Assistant is still busy.",
                "pending_job": pending_job,
                "show_trace": show_trace,
                "voice_output_enabled": voice_output_enabled,
                "quit": False,
            }
        if getattr(voice_input, "name", "off") == "off":
            session.add_system_message("Voice input is disabled. Provide --voice-input-command.")
            return {
                "draft": "",
                "status_line": "Voice input unavailable.",
                "pending_job": pending_job,
                "show_trace": show_trace,
                "voice_output_enabled": voice_output_enabled,
                "quit": False,
            }
        job = BackgroundJob("listen", voice_input.listen)
        return {
            "draft": "",
            "status_line": "Listening via external transcription command...",
            "pending_job": job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
        }
    session.add_system_message(f"Unknown command: {text}")
    return {
        "draft": "",
        "status_line": "Unknown command.",
        "pending_job": pending_job,
        "show_trace": show_trace,
        "voice_output_enabled": voice_output_enabled,
        "quit": False,
    }


def _render_screen(
    console: Console,
    persona: Persona,
    session: ConversationSession,
    draft: str,
    trace: RuntimeTrace,
    show_trace: bool,
    status_line: str,
    assistant_typing: bool,
    user_typing: bool,
    scroll_offset: int = 0,
):
    layout = Layout(name="root")
    layout.split_column(
        Layout(_render_header(persona, session), size=4),
        Layout(name="middle"),
        Layout(_render_composer(draft, status_line, user_typing), size=5),
    )
    if show_trace:
        layout["middle"].split_row(
            Layout(_render_chat(console, session, assistant_typing, scroll_offset), ratio=3),
            Layout(_render_trace(trace, persona, session), ratio=1),
        )
    else:
        layout["middle"].update(_render_chat(console, session, assistant_typing, scroll_offset))
    return layout


def _render_header(persona: Persona, session: ConversationSession):
    mood_emoji = MOOD_EMOJI.get(session.mood.current, "")
    affection = session.affection_score
    bar_filled = affection // 5
    bar_empty = 20 - bar_filled
    hearts = "".join("❤️" if i < bar_filled // 4 else "🤍" for i in range(5))
    affection_bar = f"{hearts}  [bold]{affection}[/bold][dim]/100[/dim]"

    mode_icon = {"girlfriend": "💕", "crush": "💘"}.get(persona.relationship_mode, "💬")

    body = Text.assemble(
        (f" {mode_icon} ", ""),
        (persona.name, f"bold {persona.accent_color}"),
        (f"  {persona.age}세", "dim"),
        ("  ·  ", "dim"),
        (persona.relationship_mode, f"italic {persona.accent_color}"),
        ("  ·  ", "dim"),
        (f"{mood_emoji} {session.mood.current}", ""),
        ("\n ", ""),
        (persona.situation, "dim"),
    )
    return Panel(
        body,
        border_style=persona.accent_color,
        title=f"[bold {persona.accent_color}]{persona.name}[/bold {persona.accent_color}]",
        subtitle=affection_bar,
        padding=(0, 1),
    )


def _render_chat(console: Console, session: ConversationSession, assistant_typing: bool, scroll_offset: int = 0):
    available_width = max(60, console.size.width - 38)
    available_lines = max(6, console.size.height - 11)
    # Apply scroll offset: trim from the end
    if scroll_offset > 0 and len(session.messages) > scroll_offset:
        visible_messages = session.messages[:-scroll_offset]
    else:
        visible_messages = session.messages
    history = _fit_messages(visible_messages, available_lines)
    blocks = []
    for i, message in enumerate(history):
        is_read = True
        if message.role == "user":
            remaining = history[i + 1:]
            is_read = any(m.role == "assistant" for m in remaining)
        blocks.append(_render_message(
            message, available_width,
            is_read=is_read,
            persona_name=session.persona.name,
            accent=session.persona.accent_color,
        ))
    if assistant_typing:
        # Animated typing dots based on time
        phase = int(time.monotonic() * 3) % 4
        dot_styles = [
            [("●", "bright_white"), ("●", "dim"), ("●", "dim")],
            [("●", "dim"), ("●", "bright_white"), ("●", "dim")],
            [("●", "dim"), ("●", "dim"), ("●", "bright_white")],
            [("●", "dim white"), ("●", "dim white"), ("●", "dim white")],
        ]
        dots = Text.assemble(
            (f" {session.persona.name}  ", f"bold {session.persona.accent_color}"),
            *dot_styles[phase],
        )
        blocks.append(Align.left(
            Panel(dots, border_style=session.persona.accent_color, width=min(available_width, 30), padding=(0, 1))
        ))
    if not blocks:
        blocks.append(Align.center(
            Text("\n  Start the conversation...\n", style="dim italic")
        ))
    scroll_hint = f"[dim] ↑{scroll_offset} older messages [/dim]" if scroll_offset > 0 else ""
    return Panel(Group(*blocks), border_style="grey37", padding=(0, 0), subtitle=scroll_hint)


def _fit_messages(messages: list[ChatMessage], max_lines: int) -> list[ChatMessage]:
    """Select recent messages that fit within available terminal lines."""
    result: list[ChatMessage] = []
    used_lines = 0
    for msg in reversed(messages):
        if msg.role == "system":
            cost = 1
        else:
            # Bubble width is ~35 chars. Panel chrome = 4 lines (border top/bottom + title + subtitle)
            # Text wraps at ~30 chars inside the bubble
            text_lines = max(1, (len(msg.text) + 29) // 30)
            cost = 4 + text_lines
        if used_lines + cost > max_lines and result:
            break
        result.append(msg)
        used_lines += cost
    result.reverse()
    return result


def _render_message(
    message: ChatMessage,
    width: int,
    is_read: bool = True,
    persona_name: str = "",
    accent: str = "magenta",
):
    bubble_width = min(width, max(24, int(width * 0.65)))
    timestamp = message.created_at.strftime("%H:%M")
    # Truncate very long messages to prevent panel overflow
    max_chars = bubble_width * 4
    display_text = message.text if len(message.text) <= max_chars else message.text[:max_chars] + "..."
    if message.role == "user":
        read_mark = "[bright_cyan]✓✓[/bright_cyan]" if is_read else "[dim]✓[/dim]"
        content = Text(display_text, style="white")
        return Align.right(
            Panel(
                content,
                border_style="bright_blue",
                subtitle=f"[dim]{timestamp}[/dim] {read_mark}",
                subtitle_align="right",
                width=bubble_width,
                padding=(0, 1),
            )
        )
    if message.role == "assistant":
        content = Text(display_text, style="white")
        return Align.left(
            Panel(
                content,
                border_style=accent,
                title=f"[bold {accent}]{persona_name}[/bold {accent}]",
                title_align="left",
                subtitle=f"[dim]{timestamp}[/dim]",
                subtitle_align="left",
                width=bubble_width,
                padding=(0, 1),
            )
        )
    return Align.center(
        Text(f"── {message.text} ──", style="dim italic"),
    )


def _render_composer(draft: str, status_line: str, user_typing: bool):
    prompt = " [dim italic]아무 키나 눌러서 입력 시작...[/dim italic]"
    keys = "[dim]Type[/dim] 입력  [dim]Esc[/dim] 뒤로  [dim]↑↓[/dim] 스크롤  [dim]/help[/dim]"
    status = f"[dim italic]{status_line}[/dim italic]"
    title = "[bright_blue]typing...[/bright_blue]" if user_typing else "[dim]message[/dim]"
    return Panel(
        f"{prompt}\n\n {status}",
        title=title,
        subtitle=keys,
        border_style="bright_blue" if user_typing else "grey37",
        padding=(0, 1),
    )


def _render_trace(trace: RuntimeTrace, persona: Persona, session: ConversationSession):
    mood_emoji = MOOD_EMOJI.get(session.mood.current, "")
    aff = session.affection_score
    aff_bar = f"[red]{'█' * (aff // 10)}[/red][dim]{'░' * (10 - aff // 10)}[/dim]"

    table = Table.grid(padding=(0, 1))
    table.add_column(style="dim", width=9)
    table.add_column(style="white")

    # Key stats at top
    table.add_row("Mood", f"{mood_emoji} {session.mood.current}")
    table.add_row("Affection", f"{aff_bar} {aff}")
    table.add_row("", "")

    # Provider info
    table.add_row("Provider", f"[cyan]{trace.provider_name}[/cyan]")
    table.add_row("Model", trace.provider_model or "[dim]default[/dim]")
    table.add_row("Perf", f"[yellow]{trace.performance_mode}[/yellow]")
    table.add_row("", "")

    # Timers
    nudge_str = f"[yellow]{trace.pending_nudge_in}s[/yellow]" if trace.pending_nudge_in is not None else "[dim]-[/dim]"
    init_str = f"[cyan]{trace.pending_initiative_in}s[/cyan]" if trace.pending_initiative_in is not None else "[dim]-[/dim]"
    table.add_row("Nudge", nudge_str)
    table.add_row("Init", init_str)
    table.add_row("Job", f"[green]{trace.pending_reply_kind}[/green]" if trace.pending_reply_kind != "idle" else "[dim]idle[/dim]")

    # Remote info (only if present)
    if trace.remote_emotion:
        table.add_row("Emotion", trace.remote_emotion)
    if trace.remote_initiative_reason:
        table.add_row("Reason", trace.remote_initiative_reason)
    if trace.remote_memory_hits:
        table.add_row("Memory", ", ".join(trace.remote_memory_hits[:2]))

    table.add_row("", "")
    table.add_row("Voice", f"{trace.voice_output_name}/{trace.voice_input_name}")
    table.add_row("Status", f"[dim]{trace.status_line[:20]}[/dim]")

    return Panel(table, title="[dim]trace[/dim]", border_style="grey37", padding=(0, 0))


def _build_render_key(
    session: ConversationSession,
    draft: str,
    trace: RuntimeTrace,
    show_trace: bool,
    status_line: str,
    assistant_typing: bool,
    user_typing: bool,
    scroll_offset: int = 0,
) -> tuple[Any, ...]:
    latest = session.messages[-1] if session.messages else None
    latest_marker = (
        latest.role,
        latest.text,
        latest.created_at.isoformat(),
    ) if latest is not None else None
    return (
        len(session.messages),
        latest_marker,
        draft,
        show_trace,
        status_line,
        assistant_typing,
        user_typing,
        trace.pending_reply_kind,
        trace.pending_nudge_in,
        trace.pending_initiative_in,
        trace.remote_persona_ref,
        trace.remote_persona_version,
        trace.remote_emotion,
        trace.remote_initiative_reason,
        tuple(trace.remote_memory_hits),
        trace.status_line,
        session.affection_score,
        session.mood.current,
        session.mood.intensity,
        scroll_offset,
        int(time.monotonic() * 3) % 4 if assistant_typing else 0,  # animate dots
    )


def _pending_activity_kind(
    pending_job: BackgroundJob | None,
    pending_delivery: PendingDelivery | None,
) -> str:
    if pending_job is not None:
        return pending_job.kind
    if pending_delivery is not None:
        return pending_delivery.kind
    return "idle"


def _assistant_busy(
    pending_job: BackgroundJob | None,
    pending_delivery: PendingDelivery | None,
) -> bool:
    return pending_job is not None or pending_delivery is not None


def _show_typing_indicator(
    pending_job: BackgroundJob | None,
    pending_delivery: PendingDelivery | None,
) -> bool:
    """Show typing dots only after the 'seen' delay has passed."""
    if pending_job is not None:
        return True  # generating reply, show thinking
    if pending_delivery is not None:
        if pending_delivery.typing_starts_at is not None:
            return time.monotonic() >= pending_delivery.typing_starts_at
        return True  # nudge/initiative: show immediately
    return False


def _supports_interactive_chat() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _sync_provider_trace(provider: Any, trace: RuntimeTrace) -> None:
    provider_trace = getattr(provider, "last_trace", None)
    if not isinstance(provider_trace, dict):
        return
    trace.remote_persona_ref = (
        str(provider_trace.get("persona_ref")) if provider_trace.get("persona_ref") else None
    )
    version = provider_trace.get("persona_version")
    trace.remote_persona_version = int(version) if isinstance(version, int) else None
    trace.remote_emotion = (
        str(provider_trace.get("emotion")) if provider_trace.get("emotion") else None
    )
    trace.remote_initiative_reason = (
        str(provider_trace.get("initiative_reason"))
        if provider_trace.get("initiative_reason")
        else None
    )
    memory_hits = provider_trace.get("memory_hits")
    trace.remote_memory_hits = [str(item) for item in memory_hits] if isinstance(memory_hits, list) else []
