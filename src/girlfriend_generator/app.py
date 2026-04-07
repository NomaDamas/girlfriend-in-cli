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
    def __init__(self) -> None:
        self.fd = sys.stdin.fileno()
        self._old_settings: list[Any] | None = None

    def __enter__(self) -> "RawKeyboard":
        if not sys.stdin.isatty():
            raise RuntimeError("Interactive chat requires a TTY.")
        self._old_settings = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        return self

    def __exit__(self, *_: Any) -> None:
        if self._old_settings is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._old_settings)

    def poll(self, timeout: float) -> str | None:
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if not ready:
            return None
        data = os.read(self.fd, 1)
        if not data:
            return None
        if data == b"\x1b":
            # Drain a short escape sequence if present.
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 0)
                if not ready:
                    break
                data += os.read(self.fd, 1)
            return data.decode(errors="ignore")
        return data.decode(errors="ignore")


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

                poll_timeout = (
                    config.input_poll_active_seconds
                    if (pending_job is not None or pending_delivery is not None or draft)
                    else config.input_poll_idle_seconds
                )
                key = keyboard.poll(poll_timeout)
                if key is not None:
                    last_key_at = time.monotonic()
                    outcome = _handle_key(
                        key=key,
                        draft=draft,
                        session=session,
                        persona=persona,
                        provider=provider,
                        pending_job=pending_job,
                        pending_delivery=pending_delivery,
                        voice_input=voice_input,
                        voice_output_available=voice_output.name != "off",
                        voice_output_enabled=voice_output_enabled,
                        show_trace=show_trace,
                        session_dir=config.session_dir,
                    )
                    draft = outcome["draft"]
                    status_line = outcome["status_line"]
                    pending_job = outcome["pending_job"]
                    show_trace = outcome["show_trace"]
                    voice_output_enabled = outcome["voice_output_enabled"]
                    if outcome["quit"]:
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
                    assistant_typing=pending_job is not None or pending_delivery is not None,
                    user_typing=user_typing,
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
                            assistant_typing=pending_job is not None
                            or pending_delivery is not None,
                            user_typing=user_typing,
                        ),
                        refresh=True,
                    )
                    last_render_key = render_key
    finally:
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
        delivery = PendingDelivery(
            kind="reply",
            text=reply.text,
            due_at=time.monotonic() + reply.typing_seconds,
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
) -> dict[str, Any]:
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
        return {
            "draft": "",
            "status_line": "Draft cleared.",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
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
    if lowered == "/help":
        session.add_system_message(
            "Commands: /help, /quit, /trace, /status, /export, /reload, /voice on, /voice off, /listen"
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
):
    layout = Layout(name="root")
    layout.split_column(
        Layout(_render_header(persona, session), size=5),
        Layout(name="middle"),
        Layout(_render_composer(draft, status_line, user_typing), size=6),
    )
    if show_trace:
        layout["middle"].split_row(
            Layout(_render_chat(console, session, assistant_typing), ratio=3),
            Layout(_render_trace(trace, persona, session), ratio=1),
        )
    else:
        layout["middle"].update(_render_chat(console, session, assistant_typing))
    return layout


def _render_header(persona: Persona, session: ConversationSession):
    mood_emoji = MOOD_EMOJI.get(session.mood.current, "")
    affection = session.affection_score
    bar_filled = affection // 5
    bar_empty = 20 - bar_filled
    affection_bar = f"[red]{'█' * bar_filled}[/red][dim]{'░' * bar_empty}[/dim] {affection}/100"
    subtitle = (
        f"{persona.name} · {persona.relationship_mode} · {persona.age}세 · "
        f"관심사 {', '.join(persona.interests[:3])}"
    )
    body = Text.assemble(
        ("CLI Romance Simulator", "bold white"),
        (f"  {mood_emoji} {session.mood.current}", ""),
        ("\n"),
        (subtitle, f"bold {persona.accent_color}"),
        ("\n"),
        (persona.situation, "dim"),
    )
    return Panel(body, border_style=persona.accent_color, title="Session", subtitle=f"Affection {affection_bar}")


def _render_chat(console: Console, session: ConversationSession, assistant_typing: bool):
    available_width = max(60, console.size.width - 38)
    history = session.messages[-12:]
    blocks = []
    for i, message in enumerate(history):
        is_read = True
        if message.role == "user":
            remaining = history[i + 1:]
            is_read = any(m.role == "assistant" for m in remaining)
        blocks.append(_render_message(message, available_width, is_read=is_read))
    if assistant_typing:
        blocks.append(
            Align.left(
                Panel(
                    Text("...", style="italic"),
                    border_style=session.persona.accent_color,
                    title=f"{session.persona.name} typing",
                    width=min(available_width, 28),
                )
            )
        )
    if not blocks:
        blocks.append(Panel("No messages yet.", border_style="dim"))
    return Panel(Group(*blocks), title="Chat", border_style="cyan")


def _render_message(message: ChatMessage, width: int, is_read: bool = True):
    bubble_width = min(width, max(28, width - 6))
    timestamp = message.created_at.strftime("%H:%M")
    if message.role == "user":
        read_mark = " ✓✓" if is_read else " ✓"
        return Align.right(
            Panel(
                Text(message.text),
                title=f"You · {timestamp}{read_mark}",
                border_style="bright_blue",
                width=bubble_width,
            )
        )
    if message.role == "assistant":
        return Align.left(
            Panel(
                Text(message.text),
                title=f"{timestamp}",
                border_style="magenta",
                width=bubble_width,
            )
        )
    return Align.center(
        Panel(
            Text(message.text, style="dim"),
            border_style="dim",
            width=min(width, 58),
        )
    )


def _render_composer(draft: str, status_line: str, user_typing: bool):
    prompt = draft if draft else "[dim]메시지를 입력하세요...[/dim]"
    footer = f"{status_line} | Enter send | Esc clear | /quit exit"
    title = "You are typing..." if user_typing else "Composer"
    return Panel(prompt, title=title, subtitle=footer, border_style="bright_blue")


def _render_trace(trace: RuntimeTrace, persona: Persona, session: ConversationSession):
    table = Table.grid(padding=(0, 1))
    table.add_column(style="bold cyan", width=11)
    table.add_column(style="white")
    table.add_row("ECC mode", trace.ecc_mode)
    table.add_row("AGENTS", "AGENTS.md + .codex/AGENTS.md")
    table.add_row("Skills", trace.skills_root)
    table.add_row("Skill set", "ECC local + romance-cli-sim")
    table.add_row("Provider", trace.provider_name)
    table.add_row("Model", trace.provider_model or "default")
    table.add_row("Perf", trace.performance_mode)
    table.add_row("Voice out", trace.voice_output_name)
    table.add_row("Voice in", trace.voice_input_name)
    table.add_row("Persona", trace.persona_path.name)
    table.add_row("Remote ref", trace.remote_persona_ref or "-")
    table.add_row(
        "Remote ver",
        str(trace.remote_persona_version) if trace.remote_persona_version is not None else "-",
    )
    table.add_row("Emotion", trace.remote_emotion or "-")
    table.add_row("Init why", trace.remote_initiative_reason or "-")
    table.add_row(
        "Memory",
        ", ".join(trace.remote_memory_hits[:3]) if trace.remote_memory_hits else "-",
    )
    table.add_row("Nudge in", str(trace.pending_nudge_in) if trace.pending_nudge_in is not None else "-")
    table.add_row(
        "Init in",
        str(trace.pending_initiative_in)
        if trace.pending_initiative_in is not None
        else "-",
    )
    table.add_row("Job", trace.pending_reply_kind)
    table.add_row("Global cfg", "no")
    mood_emoji = MOOD_EMOJI.get(session.mood.current, "")
    table.add_row("Mood", f"{mood_emoji} {session.mood.current} ({session.mood.intensity:.1f})")
    table.add_row("Affection", f"{session.affection_score}/100")
    table.add_row("Trace", trace.status_line)
    bullet_list = "\n".join(f"- {item}" for item in persona.soft_spots[:3])
    body = Group(table, Panel(bullet_list, title="Soft Spots", border_style="dim"))
    return Panel(body, title="ECC Trace", border_style="green")


def _build_render_key(
    session: ConversationSession,
    draft: str,
    trace: RuntimeTrace,
    show_trace: bool,
    status_line: str,
    assistant_typing: bool,
    user_typing: bool,
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
