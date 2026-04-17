from __future__ import annotations

import os
import queue
import select
import sys
import termios
import threading
import time
import tty
from dataclasses import dataclass, field
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
from .i18n import get_language, t
from .models import MOOD_EMOJI, ChatMessage, Persona, ProviderReply, RelationshipState, RuntimeTrace
from .personas import load_persona
from .providers import ProviderConfig, build_provider
from .session_io import export_session, load_session_snapshot
from .music import build_music_player
from .scenes import (
    SceneState, Scene, load_scenes, available_scenes,
    build_evaluator_prompt, build_report_prompt,
    parse_evaluator_response, parse_report_response, render_report_card,
)
from .voice import build_voice_input, build_voice_output


@dataclass(slots=True)
class AppConfig:
    persona_path: Path
    persona_override: Persona | None = None
    provider_name: str = "heuristic"
    provider_model: str | None = None
    ollama_base_url: str | None = None
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
    burst_queue: list[str] = field(default_factory=list)  # follow-up burst messages
    propose_scene: str = ""  # LLM-proposed scene change


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


def _resolve_ending_choice(choice: str) -> str:
    normalized = " ".join(choice.strip().lower().split())
    if normalized in {
        "c",
        "continue",
        "continue report",
        "report",
        "keep playing",
        "resume",
        "play on",
        "계속",
        "계속 플레이",
        "계속하기",
        "続ける",
        "继续",
    }:
        return "continue_report"
    if normalized in {
        "e",
        "endless",
        "no report",
        "silent",
        "silent continue",
        "reportless",
        "노리포트",
        "리포트 없이",
        "무한",
        "skip report",
    }:
        return "continue_silent"
    return "back"


class RawKeyboard:
    """Keyboard handler: raw mode for special keys, input() for text."""

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
        data = os.read(self.fd, 64)
        if not data:
            return None
        # Escape sequences (arrows, etc.)
        if data[0] == 0x1B:
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 0.02)
                if not ready:
                    break
                data += os.read(self.fd, 1)
            return data.decode(errors="ignore")
        # Drain any remaining bytes (multi-byte chars, IME burst)
        time.sleep(0.01)
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0)
            if not ready:
                break
            data += os.read(self.fd, 64)
        # Decode safely — drop incomplete trailing UTF-8
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="ignore") or None


def _drain_pending_stdin() -> None:
    """Best-effort drain of queued stdin bytes between nested UI phases."""
    if not sys.stdin.isatty():
        return
    fd = sys.stdin.fileno()
    for _ in range(8):
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            break
        try:
            os.read(fd, 64)
        except OSError:
            break



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
            ollama_base_url=config.ollama_base_url,
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
        resumed_messages, resumed_state = load_session_snapshot(config.resume_path)
        session.messages = resumed_messages
        if resumed_state:
            session.current_relationship_label = str(resumed_state.get("label", session.current_relationship_label))
            session.current_relationship_summary = str(resumed_state.get("summary", session.current_relationship_summary))
            session.relationship_guidance = str(resumed_state.get("guidance", session.relationship_guidance))
            session.dynamic_personality = str(resumed_state.get("dynamic_personality", session.dynamic_personality))
            session.relationship_state.phase = str(resumed_state.get("phase", session.relationship_state.phase))
            session.relationship_state.situation = str(resumed_state.get("situation", session.relationship_state.situation))
            session.relationship_state.nudge_style = str(resumed_state.get("nudge_style", session.relationship_state.nudge_style))
            session.relationship_state.nudge_examples = [str(item) for item in resumed_state.get("nudge_examples", session.relationship_state.nudge_examples)]
            session.relationship_state.boundary_kind = str(resumed_state.get("boundary_kind", session.relationship_state.boundary_kind))
        session.awaiting_user_reply = False
        session.schedule_initiative()
        session.add_system_message(f"Session resumed ({len(resumed_messages)} messages loaded)")
        _localize_session_display_state(provider, persona, session)
    else:
        session.bootstrap()
        _localize_session_display_state(provider, persona, session)

    draft = ""
    status_line = t("prompt_message_input")
    pending_job: BackgroundJob | None = None
    pending_delivery: PendingDelivery | None = None
    last_key_at = time.monotonic()
    show_trace = config.show_trace
    last_render_key: tuple[Any, ...] | None = None
    scroll_offset = 0  # 0 = latest messages, positive = scrolled up
    voice_output_enabled = config.voice_output and voice_output.name != "off"
    all_scenes = load_scenes()
    scene_state = SceneState()
    if all_scenes:
        scene_state.current_scene = all_scenes[0]  # Start at cafe

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
                    delivered_text = pending_delivery.text
                    if pending_delivery.kind == "nudge":
                        session.deliver_nudge(delivered_text)
                    elif pending_delivery.kind == "initiative":
                        session.consume_initiative(delivered_text)
                    else:
                        session.add_assistant_message(delivered_text, schedule_nudge=True)
                    trace.status_line = _friendly_activity_status(pending_delivery.kind)
                    status_line = _friendly_activity_status(pending_delivery.kind)
                    if voice_output_enabled:
                        voice_output.speak(delivered_text)
                    # Handle burst follow-ups: queue them as additional deliveries
                    if pending_delivery.burst_queue:
                        next_text = pending_delivery.burst_queue[0]
                        remaining = pending_delivery.burst_queue[1:]
                        seen_delay = 0.6
                        pending_delivery = PendingDelivery(
                            kind="reply",
                            text=next_text,
                            due_at=time.monotonic() + seen_delay + len(next_text) / 20.0,
                            typing_starts_at=time.monotonic() + seen_delay,
                            trace_note="burst follow-up",
                            burst_queue=remaining,
                        )
                    else:
                        pending_delivery = None

                boundary_kind = (
                    session.consume_boundary_trigger()
                    if hasattr(session, "consume_boundary_trigger")
                    else (
                        "game_over" if (not getattr(session, "endless_mode", False) and session.affection_score <= 0)
                        else "success" if (not getattr(session, "endless_mode", False) and session.affection_score >= 100)
                        else None
                    )
                )
                if boundary_kind is not None and not session.ended:
                    session.ended = True
                    ending_action = _show_ending(live, console, persona, session, boundary_kind, provider)
                    if ending_action == "continue":
                        status_line = t("status_continue_after_ending")
                        trace.status_line = status_line
                        continue
                    return 2

                # LLM-scheduled proactive follow-up (highest priority)
                proactive_ready = (
                    session.proactive_due_at is not None
                    and now >= session.proactive_due_at
                    and pending_job is None
                    and pending_delivery is None
                )
                if proactive_ready:
                    session.proactive_due_at = None
                    try:
                        proactive_reply = provider.generate_initiative(
                            persona, session.recent_history(), session.affection_score,
                            **session.prompt_context(),
                        )
                        if proactive_reply:
                            pending_delivery = PendingDelivery(
                                kind="initiative",
                                text=proactive_reply,
                                due_at=time.monotonic() + 0.6,
                                trace_note="initiative",
                            )
                    except Exception:
                        pass

                if session.nudge_due(now) and pending_job is None and pending_delivery is None:
                    nudge_text = provider.generate_nudge(
                        persona, session.recent_history(), session.affection_score,
                        **session.prompt_context(),
                    )
                    pending_delivery = PendingDelivery(
                        kind="nudge",
                        text=nudge_text,
                        due_at=time.monotonic() + 1.2,
                        trace_note="nudge",
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
                            **session.prompt_context(),
                        ),
                        due_at=time.monotonic() + 0.9,
                        trace_note="initiative",
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

                # Poll faster when user is actively typing
                recently_typed = (time.monotonic() - last_key_at) < 2.0
                if recently_typed or draft:
                    poll_timeout = 0.02  # 20ms — fast response while typing
                elif pending_job is not None or pending_delivery is not None:
                    poll_timeout = config.input_poll_active_seconds
                else:
                    poll_timeout = config.input_poll_idle_seconds
                key = keyboard.poll(poll_timeout)
                if key is not None:
                    last_key_at = time.monotonic()
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
                    scroll_offset = 0 if outcome.get("sent") else scroll_offset
                    # Strategy discussion
                    if outcome.get("strategy"):
                        _show_strategy_discussion(
                            live, console, persona, session, provider, scene_state,
                        )
                        last_render_key = None
                    if outcome.get("coach_full"):
                        _show_full_coach_panel(live, console, session)
                        last_render_key = None
                    # Scene: handle pending proposal acceptance/rejection
                    if outcome.get("sent") and scene_state.pending_proposal:
                        user_text = session.messages[-1].text if session.messages else ""
                        lower_text = user_text.lower()
                        accept_words = ("좋아", "가자", "ㅇㅇ", "응", "그래", "오케이", "ok", "ㅇ", "가요", "가볼까")
                        reject_words = ("싫어", "아니", "ㄴㄴ", "안가", "여기", "별로", "아직")
                        if any(w in lower_text for w in accept_words):
                            # Find the scene
                            target = None
                            for s in all_scenes:
                                if s.name == scene_state.pending_proposal.next_scene:
                                    target = s
                                    break
                            if target:
                                # Generate report card
                                try:
                                    report_prompt = build_report_prompt(
                                        persona, scene_state.current_scene or target,
                                        target, session.messages,
                                        session.affection_score, session.mood.current,
                                        language=get_language(),
                                    )
                                    report_reply = provider.generate_reply(
                                        persona, [], report_prompt,
                                        session.affection_score, session.mood.current,
                                        language=get_language(),
                                        **session.prompt_context(),
                                    )
                                    report = parse_report_response(
                                        report_reply.text,
                                        session.affection_score, session.mood.current,
                                        target,
                                    )
                                except Exception:
                                    from .scenes import ReportCard
                                    report = ReportCard(
                                        highlights=["(요약 생성 중 오류)"],
                                        advice="자연스럽게 대화를 이어가보세요.",
                                        scene_summary="",
                                        affection=session.affection_score,
                                        mood=session.mood.current,
                                        next_scene_name=target.name,
                                        next_scene_desc=target.description,
                                    )
                                # Show report card as system message
                                session.add_system_message(render_report_card(report))
                                # Transition
                                scene_state.accept_transition(target)
                                session.strategy_uses_this_scene = 0  # reset per scene
                                session.apply_affection_delta(5, user_text, source="scene_accept")
                                session.mood.shift(target.mood_hint)
                                # Clear messages for new scene, keep summary
                                if report.scene_summary:
                                    session.messages.clear()
                                    session.add_system_message(f"[이전 장소 요약] {report.scene_summary}")
                                    session.add_system_message(f"[현재 장소] {target.name} — {target.description}")
                        elif any(w in lower_text for w in reject_words):
                            scene_state.reject_transition()
                            session.apply_affection_delta(-2, user_text, source="scene_reject")
                        # else: ambiguous response, keep proposal pending

                    # Scene evaluator: check after every user message
                    if outcome.get("sent") and all_scenes and not scene_state.pending_proposal:
                        scene_state.record_user_message()
                        if scene_state.should_evaluate() and pending_job is None:
                            avail = available_scenes(
                                all_scenes, session.affection_score,
                                scene_state.current_scene.name if scene_state.current_scene else "",
                            )
                            if avail:
                                eval_prompt = build_evaluator_prompt(
                                    persona, scene_state.current_scene,
                                    session.affection_score, session.mood.current,
                                    session.recent_history(), avail,
                                    language=get_language(),
                                )
                                try:
                                    eval_reply = provider.generate_reply(
                                        persona, session.recent_history(),
                                        eval_prompt, session.affection_score,
                                        session.mood.current,
                                        language=get_language(),
                                        **session.prompt_context(),
                                    )
                                    result = parse_evaluator_response(eval_reply.text)
                                    if result.should_move and result.proposal_line:
                                        scene_state.pending_proposal = result
                                        session.add_assistant_message(result.proposal_line)
                                except Exception:
                                    pass  # evaluator failure is non-fatal
                    status_line = outcome["status_line"]
                    pending_job = outcome["pending_job"]
                    show_trace = outcome["show_trace"]
                    voice_output_enabled = outcome["voice_output_enabled"]
                    if "scroll_delta" in outcome:
                        scroll_offset = max(0, scroll_offset + outcome["scroll_delta"])
                        max_scroll = max(0, len(session.messages) - 4)
                        scroll_offset = min(scroll_offset, max_scroll)
                        if scroll_offset == 0:
                            status_line = ""
                    if outcome and outcome.get("quit"):
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
                relationship_state=session.export_state().get("relationship_state"),
            )


def _show_strategy_discussion(
    live: Any,
    console: Console,
    persona: Persona,
    session: ConversationSession,
    provider: Any,
    scene_state: Any,
) -> None:
    """Pause chat, show strategic LLM discussion in a full-screen card.

    Limited to 3 uses per scene. The LLM acts as a dating strategist
    analyzing the current state and suggesting specific next moves.
    """
    from rich.align import Align
    from rich.panel import Panel
    from rich.text import Text
    from rich.console import Group as RichGroup
    from .wide_input import wide_input

    # Check usage limit
    if session.strategy_uses_this_scene >= session.max_strategy_per_scene:
        live.stop()
        console.clear()
        console.print()
        console.print(Align.center(Panel(
            Text.assemble(
                ("\n  Strategy cards exhausted for this scene.\n", "bold yellow"),
                (f"  You used all {session.max_strategy_per_scene} discussions.\n", "white"),
                ("\n  Move to a new scene via /move to refresh.\n", "dim"),
            ),
            title="[bold yellow]⚠ Limit reached[/bold yellow]",
            border_style="yellow",
            width=60,
        )))
        console.print()
        try:
            wide_input("  Press Enter to continue...")
        except (EOFError, KeyboardInterrupt):
            pass
        live.start(refresh=True)
        return

    live.stop()
    console.clear()

    # Show "thinking" spinner
    from rich.spinner import Spinner
    from rich.live import Live as RichLive
    with RichLive(
        Spinner("dots", text="  🧠 Strategist is analyzing...", style="cyan"),
        console=console,
        refresh_per_second=10,
    ) as spinner:
        # Build strategy prompt
        recent = "\n".join(
            f"{m.role}: {m.text}" for m in session.messages[-12:] if m.role != "system"
        )
        strategy_prompt = (
            f"You are a sharp dating strategist analyzing a live conversation. "
            f"Target: {persona.name} ({persona.age}세, {persona.relationship_mode}), "
            f"difficulty={persona.difficulty}. "
            f"Current affection: {session.affection_score}/100. Mood: {session.mood.current}.\n\n"
            f"Recent conversation:\n{recent}\n\n"
            f"Analyze the dynamic and give a strategic card. Respond with ONLY JSON:\n"
            "{\n"
            '  "assessment": "1-2 sentences on the current state of the relationship",\n'
            '  "user_strength": "what the user is doing well (1 sentence)",\n'
            '  "user_weakness": "what the user is doing wrong (1 sentence, specific)",\n'
            '  "strategy": "high-level strategic recommendation (2 sentences)",\n'
            '  "suggested_lines": ["concrete message 1 to try", "message 2", "message 3"],\n'
            '  "avoid": ["what NOT to say 1", "what NOT to say 2"]\n'
            "}"
        )
        try:
            strategy_reply = provider.generate_reply(
                persona, session.recent_history(), strategy_prompt,
                session.affection_score, session.mood.current,
                **session.prompt_context(),
            )
            import json as _json
            raw = strategy_reply.text
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            data = _json.loads(raw)
        except Exception:
            data = {
                "assessment": "분석에 실패했습니다.",
                "user_strength": "",
                "user_weakness": "",
                "strategy": "잠시 후 다시 시도해보세요.",
                "suggested_lines": [],
                "avoid": [],
            }

    session.strategy_uses_this_scene += 1
    uses_left = session.max_strategy_per_scene - session.strategy_uses_this_scene

    console.clear()
    console.print()

    rows = [
        Text(""),
        Text.assemble(("  STRATEGY ANALYSIS\n", "bold bright_cyan")),
        Text.assemble(("  ─────────────────\n", "dim")),
        Text(""),
        Text.assemble(("  Current State\n", "bold")),
        Text.assemble(("  ", ""), (data.get("assessment", ""), "white")),
        Text(""),
        Text.assemble(("  ✓ Strength  ", "bold green"), (data.get("user_strength", ""), "green")),
        Text.assemble(("  ✗ Weakness  ", "bold red"), (data.get("user_weakness", ""), "red")),
        Text(""),
        Text.assemble(("  ► Strategy\n", "bold yellow")),
        Text.assemble(("  ", ""), (data.get("strategy", ""), "yellow")),
        Text(""),
        Text.assemble(("  Suggested Lines\n", "bold bright_cyan")),
    ]
    for line in data.get("suggested_lines", [])[:3]:
        rows.append(Text.assemble(("    • ", "cyan"), (line, "white")))
    if data.get("avoid"):
        rows.append(Text(""))
        rows.append(Text.assemble(("  Avoid\n", "bold red")))
        for a in data.get("avoid", [])[:3]:
            rows.append(Text.assemble(("    ✗ ", "red"), (a, "dim red")))
    rows.append(Text(""))
    rows.append(Text.assemble(
        (f"  Strategy cards used: {session.strategy_uses_this_scene}/{session.max_strategy_per_scene}  ", "dim"),
        (f"({uses_left} left this scene)", "dim italic"),
    ))
    rows.append(Text(""))

    console.print(Align.center(Panel(
        RichGroup(*rows),
        title="[bold bright_cyan]  🎯 Strategy Discussion  [/bold bright_cyan]",
        border_style="bright_cyan",
        width=80,
        padding=(0, 2),
    )))
    console.print()
    console.print(Align.center(Text("Press Enter to return to chat", style="dim")))

    try:
        wide_input("")
    except (EOFError, KeyboardInterrupt):
        pass

    live.start(refresh=True)


def _fallback_relationship_state(session: ConversationSession, kind: str) -> RelationshipState:
    relation = session.current_relationship_label.lower()
    if kind == "success":
        if any(token in relation for token in ("crush", "friend", "situationship")):
            return RelationshipState(
                label="dating",
                summary="서로 좋아하는 걸 확인하고 이제는 공식적으로 사귀는 관계",
                guidance="더 가까워졌지만 너무 쉬운 사람은 아니다. 다정함과 익숙함이 함께 있다.",
                dynamic_personality="애정 표현이 더 자연스럽고 사적인 관심이 깊어졌다",
                phase="evolved-after-success",
                situation="서로의 일상과 일정이 자연스럽게 얽힌 연애 초기",
                nudge_style="soft clingy",
                nudge_examples=["자기야 뭐 해", "오늘 내 생각 안 했지 솔직히", "답장 좀 해봐 보고싶단 말이야"],
                boundary_kind=kind,
            )
        if any(token in relation for token in ("dating", "girlfriend", "boyfriend", "partner")):
            return RelationshipState(
                label="married cofounders",
                summary="연인 단계를 지나 서로의 인생과 일까지 함께 책임지는 사이",
                guidance="편하지만 더 깊은 책임감과 현실적인 대화가 섞인다.",
                dynamic_personality="친밀함 위에 신뢰와 생활감이 더해졌다",
                phase="evolved-after-success",
                situation="함께 살거나 함께 큰 프로젝트를 운영하는 상태",
                nudge_style="assertive intimate",
                nudge_examples=["회의 끝났어? 이제 답해", "배우자 무시하면 혼난다", "바쁜 건 알겠는데 한 줄은 남겨"],
                boundary_kind=kind,
            )
        return RelationshipState(
            label="trusted partner",
            summary="강한 신뢰와 팀워크를 기반으로 삶을 함께 꾸리는 관계",
            guidance="감정만이 아니라 신뢰와 동맹 의식이 크게 작동한다.",
            dynamic_personality="한층 안정적이고 단단한 애착",
            phase="evolved-after-success",
            situation="서로의 미래 계획을 같이 움직이는 상태",
            nudge_style="warm reliable",
            nudge_examples=["우리 팀원님 어디 갔어", "나 혼자 결정하게 두지 마", "한 줄 보고는 해줘"],
            boundary_kind=kind,
        )
    if any(token in relation for token in ("dating", "girlfriend", "boyfriend", "partner", "married", "spouse")):
        return RelationshipState(
            label="bitter exes",
            summary="감정은 남아 있지만 지금은 앙금과 서운함이 더 큰 관계",
            guidance="차갑고 예민하지만 완전히 무심하지는 않다.",
            dynamic_personality="상처받기 쉬워졌고 방어적이며 비꼬는 톤이 늘었다",
            phase="evolved-after-failure",
            situation="서로 끊지 못한 채 어색하게 다시 마주치는 상태",
            nudge_style="cold resentful",
            nudge_examples=["읽고도 답 없네 끝까지 그러네", "또 피하네 아주 너답다", "말 안 하면 더 짜증나"],
            boundary_kind=kind,
        )
    if any(token in relation for token in ("bitter exes", "awkward", "ex")):
        return RelationshipState(
            label="career rivals",
            summary="이제는 감정보다 경쟁심과 자존심이 앞서는 관계",
            guidance="호감보다는 신경전과 승부욕이 먼저 튀어나온다.",
            dynamic_personality="예민하고 공격적이지만 상대를 계속 의식한다",
            phase="evolved-after-failure",
            situation="같은 업계나 같은 판에서 자꾸 부딪히는 상태",
            nudge_style="sharp competitive",
            nudge_examples=["도망간다고 끝난 줄 알아?", "또 답 없네 자신 없냐", "계속 피하면 내가 더 기억한다"],
            boundary_kind=kind,
        )
    return RelationshipState(
        label="sworn enemies",
        summary="대화는 이어지지만 서로에게 적대감과 집착이 남아 있는 관계",
        guidance="노골적으로 날카롭고 경계심이 강하다. 호감보다는 집착과 적의가 크다.",
        dynamic_personality="훨씬 공격적이고 감정 기복이 크며 사소한 반응에도 예민하다",
        phase="evolved-after-failure",
        situation="같은 사람을 두고 완전히 꼬여버린 원수 상태",
        nudge_style="hostile obsessive",
        nudge_examples=["끝까지 무시하네", "답 없어도 기억은 다 해", "원수 만들 재주는 진짜 있네"],
        boundary_kind=kind,
    )


def _parse_relationship_transition(raw: str, session: ConversationSession, kind: str) -> RelationshipState:
    import json as _json

    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        data = _json.loads(clean)
    except Exception:
        return _fallback_relationship_state(session, kind)

    fallback = _fallback_relationship_state(session, kind)
    return RelationshipState(
        label=str(data.get("relation_label") or data.get("relationship_label") or fallback.label),
        summary=str(data.get("relationship_summary") or data.get("relation_summary") or fallback.summary),
        guidance=str(data.get("relationship_guidance") or data.get("stance_guide") or fallback.guidance),
        dynamic_personality=str(data.get("dynamic_personality") or data.get("mutable_personality") or fallback.dynamic_personality),
        phase=str(data.get("relationship_phase") or fallback.phase),
        situation=str(data.get("updated_situation") or data.get("situation") or fallback.situation),
        nudge_style=str(data.get("nudge_style") or fallback.nudge_style),
        nudge_examples=[str(item) for item in data.get("nudge_examples", fallback.nudge_examples)],
        boundary_kind=kind,
    )


def _relationship_transition_prompt(persona: Persona, session: ConversationSession, kind: str) -> str:
    boundary = "affection reached 100" if kind == "success" else "affection reached 0"
    language = get_language()
    return (
        f"The relationship just hit a boundary: {boundary}. The user is STILL the same person.\n"
        f"You must redefine ONLY the relationship between {persona.name} and the user.\n"
        "Keep the persona's core personality intact, but change the mutable/dynamic stance based on this new stage.\n"
        f"Write `relationship_summary`, `relationship_guidance`, `dynamic_personality`, `updated_situation`, and `nudge_examples` in language={language}.\n"
        f"Current relationship label: {session.current_relationship_label}\n"
        f"Current summary: {session.current_relationship_summary}\n"
        f"Current dynamic personality: {session.dynamic_personality}\n"
        f"Persona background/job/context: {persona.background}\n"
        f"Situation: {session.relationship_state.situation or persona.situation}\n"
        "Respond with ONLY valid JSON:\n"
        "{\n"
        '  "relation_label": "new relationship title such as dating, married cofounders, bitter exes, career rivals, sworn enemies",\n'
        '  "relationship_phase": "short phase name",\n'
        '  "relationship_summary": "one sentence describing the new relationship",\n'
        '  "relationship_guidance": "how the persona should now treat the user in chat",\n'
        '  "dynamic_personality": "what changed in the persona while preserving core personality",\n'
        '  "updated_situation": "updated current situation line for the header",\n'
        '  "nudge_style": "brief tone description for silence nudges",\n'
        '  "nudge_examples": ["nudge example 1", "nudge example 2", "nudge example 3"]\n'
        "}\n"
    )


def _localize_relationship_state(provider: Any, persona: Persona, state: RelationshipState) -> RelationshipState:
    language = get_language()
    if language == "ko":
        return state
    state.summary = _maybe_translate_display_text(provider, persona, state.summary, language)
    state.guidance = _maybe_translate_display_text(provider, persona, state.guidance, language)
    state.dynamic_personality = _maybe_translate_display_text(provider, persona, state.dynamic_personality, language)
    state.situation = _maybe_translate_display_text(provider, persona, state.situation, language)
    state.nudge_examples = [
        _maybe_translate_display_text(provider, persona, example, language)
        for example in state.nudge_examples
    ]
    return state


def _determine_relationship_state(
    provider: Any,
    persona: Persona,
    session: ConversationSession,
    kind: str,
) -> RelationshipState:
    from .i18n import get_language

    prompt = _relationship_transition_prompt(persona, session, kind)
    try:
        reply = provider.generate_reply(
            persona,
            session.recent_history(),
            prompt,
            session.affection_score,
            session.mood.current,
            difficulty=persona.difficulty,
            language=get_language(),
            special_mode=persona.special_mode,
            **session.prompt_context(),
        )
        state = _parse_relationship_transition(reply.text, session, kind)
    except Exception:
        state = _fallback_relationship_state(session, kind)
    return _localize_relationship_state(provider, persona, state)


def _apply_relationship_state(session: ConversationSession, state: RelationshipState) -> None:
    session.apply_relationship_state(state)
    session.add_system_message(f"[Relationship Shift] {state.label} — {state.summary}")


def _evolve_relationship(
    provider: Any,
    persona: Persona,
    session: ConversationSession,
    kind: str,
) -> RelationshipState:
    state = _determine_relationship_state(provider, persona, session, kind)
    _apply_relationship_state(session, state)
    _localize_session_display_state(provider, persona, session)
    return state


def _show_scrollable_text_panel(
    console: Console,
    title: str,
    border_style: str,
    lines: list[str],
    width: int = 80,
) -> None:
    total_lines = max(1, len(lines))
    page_height = max(8, console.size.height - 12)
    offset = 0

    def _panel() -> Any:
        end = min(total_lines, offset + page_height)
        visible = lines[offset:end] or [""]
        subtitle = (
            f"[dim]↑↓ scroll  PgUp/PgDn fast  Enter/Esc close  "
            f"{offset + 1}-{end}/{total_lines}[/dim]"
        )
        return Align.center(Panel(
            Text("\n".join(visible), overflow="fold"),
            title=title,
            border_style=border_style,
            width=width,
            padding=(1, 2),
            subtitle=subtitle,
        ))

    if not sys.stdin.isatty():
        console.print()
        console.print(Align.center(Panel(
            Text("\n".join(lines), overflow="fold"),
            title=title,
            border_style=border_style,
            width=width,
            padding=(1, 2),
        )))
        console.print()
        return

    _drain_pending_stdin()
    opened_at = time.monotonic()
    with RawKeyboard() as keyboard, Live(
        _panel(),
        console=console,
        refresh_per_second=20,
    ) as live:
        while True:
            key = keyboard.poll(0.05)
            if key is None:
                continue
            # Ignore an immediate trailing Enter/Esc from the previous input phase.
            if (time.monotonic() - opened_at) < 0.2 and key in {"\r", "\n", "\x1b"}:
                continue
            if key in {"\r", "\n", "\x1b"}:
                break
            if key in ("\x1b[A", "["):
                offset = max(0, offset - 1)
            elif key in ("\x1b[B", "]"):
                offset = min(max(0, total_lines - page_height), offset + 1)
            elif key == "\x1b[5~":
                offset = max(0, offset - max(3, page_height - 3))
            elif key == "\x1b[6~":
                offset = min(max(0, total_lines - page_height), offset + max(3, page_height - 3))
            else:
                continue
            live.update(_panel(), refresh=True)


def _localized_relationship_label(label: str) -> str:
    language = get_language()
    mapping = {
        "crush": {"ko": "썸", "en": "Crush", "ja": "片思い", "zh": "暧昧对象"},
        "girlfriend": {"ko": "연인", "en": "Girlfriend", "ja": "恋人", "zh": "恋人"},
        "dating": {"ko": "사귀는 사이", "en": "Dating", "ja": "交際中", "zh": "交往中"},
        "married cofounders": {"ko": "결혼한 공동창업자", "en": "Married Cofounders", "ja": "夫婦共同創業者", "zh": "已婚共同创业者"},
        "trusted partner": {"ko": "굳게 믿는 동반자", "en": "Trusted Partner", "ja": "信頼できる相棒", "zh": "可信赖的伴侣"},
        "bitter exes": {"ko": "앙금 남은 전연인", "en": "Bitter Exes", "ja": "わだかまりのある元恋人", "zh": "带怨气的前任"},
        "career rivals": {"ko": "업계 라이벌", "en": "Career Rivals", "ja": "業界ライバル", "zh": "事业对手"},
        "sworn enemies": {"ko": "원수", "en": "Sworn Enemies", "ja": "宿敵", "zh": "死对头"},
        "awkward ex-rivals": {"ko": "어색한 전썸 라이벌", "en": "Awkward Ex-Rivals", "ja": "気まずい元恋ライバル", "zh": "尴尬的前暧昧对手"},
    }
    return mapping.get(label.lower(), {}).get(language, label)


def _localized_mood_label(mood: str) -> str:
    language = get_language()
    mapping = {
        "neutral": {"ko": "무난", "en": "Neutral", "ja": "普通", "zh": "平静"},
        "happy": {"ko": "기분 좋음", "en": "Happy", "ja": "ご機嫌", "zh": "开心"},
        "playful": {"ko": "장난기", "en": "Playful", "ja": "いたずらっぽい", "zh": "爱闹"},
        "sulky": {"ko": "삐짐", "en": "Sulky", "ja": "すね気味", "zh": "闹别扭"},
        "excited": {"ko": "들뜸", "en": "Excited", "ja": "テンション高め", "zh": "兴奋"},
        "worried": {"ko": "걱정", "en": "Worried", "ja": "心配", "zh": "担心"},
        "flirty": {"ko": "설렘", "en": "Flirty", "ja": "ときめき", "zh": "暧昧"},
    }
    return mapping.get(mood, {}).get(language, mood)


def _friendly_activity_status(kind: str) -> str:
    mapping = {
        "reply": "",
        "initiative": "페르소나가 먼저 말을 꺼냈어요.",
        "nudge": "답장을 기다리며 다시 말을 걸었어요.",
        "listen": "음성 입력을 듣는 중이에요.",
    }
    return mapping.get(kind, "")


_DISPLAY_TRANSLATION_CACHE: dict[tuple[str, str], str] = {}


def _maybe_translate_display_text(
    provider: Any,
    persona: Persona,
    text: str,
    language: str,
) -> str:
    if not text or language == "ko":
        return text
    cache_key = (language, text)
    if cache_key in _DISPLAY_TRANSLATION_CACHE:
        return _DISPLAY_TRANSLATION_CACHE[cache_key]
    if provider.__class__.__name__ == "HeuristicProvider" or not hasattr(provider, "generate_reply"):
        return text
    try:
        reply = provider.generate_reply(
            persona,
            [],
            (
                f"(system: Translate the following relationship/situation text into {language}. "
                "Return only the translated text without explanation.)\n"
                f"{text}"
            ),
            50,
            "neutral",
            language=language,
            difficulty=persona.difficulty,
            special_mode="",
        )
        translated = (reply.text or "").strip()
        if translated:
            _DISPLAY_TRANSLATION_CACHE[cache_key] = translated
            return translated
    except Exception:
        pass
    return text


def _localize_session_display_state(provider: Any, persona: Persona, session: ConversationSession) -> None:
    language = get_language()
    if language == "ko":
        return
    if hasattr(session, "current_relationship_summary"):
        session.current_relationship_summary = _maybe_translate_display_text(
            provider, persona, session.current_relationship_summary, language
        )
    if hasattr(session, "relationship_guidance"):
        session.relationship_guidance = _maybe_translate_display_text(
            provider, persona, session.relationship_guidance, language
        )
    if getattr(session, "relationship_state", None) is not None and hasattr(session.relationship_state, "situation"):
        session.relationship_state.situation = _maybe_translate_display_text(
            provider, persona, session.relationship_state.situation, language
        )


def _show_ending(
    live: Any,
    console: Console,
    persona: Persona,
    session: ConversationSession,
    kind: str,
    provider: Any,
) -> str:
    """Show boundary options, optional report, and relationship evolution."""
    from rich.align import Align
    from rich.console import Group as RichGroup
    from rich.panel import Panel
    from rich.text import Text
    from .wide_input import wide_input

    live.stop()
    console.clear()

    color = "red" if kind == "game_over" else "bright_green"
    boundary_title = t("game_over") if kind == "game_over" else t("success")
    transition_kind = "success" if kind == "success" else "failure"
    from rich.live import Live as RichLive
    from rich.spinner import Spinner

    with RichLive(
        Spinner("dots", text="  다음 관계를 정리하는 중...", style="cyan"),
        console=console,
        refresh_per_second=12,
    ):
        next_state = _determine_relationship_state(provider, persona, session, transition_kind)

    console.print()
    console.print(Align.center(Panel(
        Text.assemble(
            ("\n  ", ""),
            (boundary_title, f"bold {color}"),
            ("\n\n  Current relationship:  ", "bold"),
            (f"{_localized_relationship_label(session.current_relationship_label)}\n", f"bold {persona.accent_color}"),
            ("  ", ""),
            (f"{session.current_relationship_summary}\n", "white"),
            ("\n  Next relationship:  ", "bold"),
            (f"{_localized_relationship_label(next_state.label)}\n", f"bold {color}"),
            ("  ", ""),
            (f"{next_state.summary}\n", "white"),
            ("\n  Situation after ending:  ", "bold"),
            (f"{next_state.situation}\n", "dim"),
            ("\n  ", ""),
            (t("ending_continue_prompt"), "dim"),
            ("\n", ""),
        ),
        title=f"[bold {color}]Boundary Reached[/bold {color}]",
        border_style=color,
        width=80,
        padding=(1, 2),
    )))
    console.print()

    try:
        choice = wide_input("")
    except (EOFError, KeyboardInterrupt):
        choice = ""
    action = _resolve_ending_choice(choice)
    if action == "back":
        return "back"

    if action == "continue_silent":
        _apply_relationship_state(session, next_state)
        session.continue_after_ending(kind)
        session.add_system_message(
            f"[새 관계] {_localized_relationship_label(next_state.label)} — {next_state.summary}\n[상황] {next_state.situation}"
        )
        if hasattr(live, "start"):
            live.start(refresh=True)
        return "continue"

    # Ask LLM for ending narrative + report
    ending_prompt = (
        f"The simulation has reached {'GAME OVER (affection 0)' if kind == 'game_over' else 'SUCCESS (affection 100)'}. "
        f"You are {persona.name}. Generate an ending scene and a report. "
        "Respond with ONLY valid JSON:\n"
        "{\n"
        '  "ending_narrative": "2-3 sentences in the user language describing how the relationship ended (dramatic, emotional)",\n'
        '  "persona_final_words": "the last message the persona sends (in-character, 1-2 sentences)",\n'
        '  "report_title": "a dramatic title for the ending (like 차가운 작별, 해피엔딩, 완전한 사랑)",\n'
        '  "highlights": ["key moment 1", "key moment 2", "key moment 3"],\n'
        '  "user_strength": "what the user did well across the chat (1 sentence)",\n'
        '  "user_weakness": "what the user consistently did poorly across the chat (1 sentence)",\n'
        '  "user_charm_point": "the user\'s strongest attractive point across the chat (1 sentence)",\n'
        '  "user_charm_type": "a short charm category like playful, warm, bold, thoughtful, flirty, steady",\n'
        '  "user_charm_feedback": "why that charm worked or failed in the relationship (1 sentence)",\n'
        '  "what_went_wrong": "what the user did right or wrong (1-2 sentences)",\n'
        '  "rating": "S/A/B/C/D/F grade on their performance"\n'
        "}"
    )
    try:
        from .i18n import get_language
        with RichLive(
            Spinner("dots", text="  엔딩 리포트를 정리하는 중...", style="cyan"),
            console=console,
            refresh_per_second=12,
        ):
            ending_reply = provider.generate_reply(
                persona, session.recent_history(), ending_prompt,
                session.affection_score, session.mood.current,
                difficulty=persona.difficulty,
                language=get_language(),
                special_mode=persona.special_mode,
                **session.prompt_context(),
            )
        import json as _json
        raw = ending_reply.text
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        data = _json.loads(raw)
    except Exception:
        data = {
            "ending_narrative": "The story has ended.",
            "persona_final_words": "...",
            "report_title": "GAME OVER" if kind == "game_over" else "SUCCESS",
            "highlights": [],
            "user_strength": "",
            "user_weakness": "",
            "user_charm_point": "",
            "user_charm_type": "",
            "user_charm_feedback": "",
            "what_went_wrong": "",
            "rating": "?",
        }
    _apply_relationship_state(session, next_state)
    session.continue_after_ending(kind)
    console.clear()
    title = data.get("report_title", "END")
    rating = data.get("rating", "?")

    console.print()
    report_lines = [
        "",
        f"  {data.get('persona_final_words', '')}",
        "",
        "  ──────────────────────────────",
        "",
        f"  {data.get('ending_narrative', '')}",
        "",
        "  ──────────────────────────────",
        "",
        "  Highlights:",
    ]
    for h in data.get("highlights", []):
        report_lines.append(f"    • {h}")
    if data.get("user_strength"):
        report_lines.extend(["", f"  Strength: {data.get('user_strength', '')}"])
    if data.get("user_weakness"):
        report_lines.extend(["", f"  Weakness: {data.get('user_weakness', '')}"])
    if data.get("user_charm_point"):
        report_lines.extend(["", f"  Charm Point: {data.get('user_charm_point', '')}"])
    if data.get("user_charm_type"):
        report_lines.extend(["", f"  Charm Type: {data.get('user_charm_type', '')}"])
    if data.get("user_charm_feedback"):
        report_lines.extend(["", f"  Charm Feedback: {data.get('user_charm_feedback', '')}"])
    report_lines.extend([
        "",
        f"  Review: {data.get('what_went_wrong', '')}",
        "",
        f"  Grade: {rating}",
        "",
        f"  Final Affection: {100 if kind == 'success' else 0}/100",
        "",
        f"  Next Relationship: {_localized_relationship_label(next_state.label)}",
        f"  {next_state.summary}",
        "",
        f"  Situation: {next_state.situation}",
        "",
        f"  Stance: {next_state.guidance}",
        "",
    ])
    _show_scrollable_text_panel(
        console,
        title=f"[bold {color}]━━ {title} ━━[/bold {color}]",
        border_style=color,
        lines=report_lines,
    )
    if hasattr(live, "start"):
        live.start(refresh=True)
    return "continue"


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
                lambda: provider.generate_reply(
                    persona,
                    session.recent_history(),
                    transcript,
                    session.affection_score,
                    session.mood.current,
                    **session.prompt_context(),
                ),
            ),
            previous_delivery,
            "voice transcript captured",
        )

    if previous_job.kind == "reply":
        reply = value
        if not isinstance(reply, ProviderReply):
            session.add_system_message("Unexpected reply object from provider.")
            return None, previous_delivery, previous_status

        # ProviderReply now has parsed fields from LLM JSON
        actual_text = reply.text  # already clean
        latest_user_text = next(
            (message.text for message in reversed(session.messages) if message.role == "user"),
            "",
        )
        session.apply_affection_delta(reply.affection_delta, latest_user_text, source="reply")
        if reply.mood and reply.mood in ("neutral", "happy", "playful", "sulky", "excited", "worried", "flirty"):
            session.mood.shift(reply.mood)
        if reply.memory_update:
            session.memory_notes.append(reply.memory_update)
        session.last_coach_feedback = reply.coach_feedback
        session.last_coach_strength = reply.coach_strength
        session.last_coach_weakness = reply.coach_weakness
        session.last_coach_charm_point = reply.coach_charm_point
        session.last_coach_charm_type = reply.coach_charm_type
        session.last_coach_charm_feedback = reply.coach_charm_feedback
        session.last_internal_thought = reply.internal_thought
        # LLM-decided proactive follow-up scheduling
        if reply.next_proactive_seconds and reply.next_proactive_seconds > 0:
            from datetime import timedelta
            session.proactive_due_at = utc_now() + timedelta(seconds=reply.next_proactive_seconds)
        else:
            session.proactive_due_at = None

        # Add "seen" delay before typing indicator shows (1-2.5s)
        import random
        seen_delay = random.uniform(1.0, 2.5)
        now = time.monotonic()
        trace_extra = f" | thought: {reply.internal_thought}" if reply.internal_thought else ""
        delivery = PendingDelivery(
            kind="reply",
            text=actual_text,
            due_at=now + seen_delay + reply.typing_seconds,
            typing_starts_at=now + seen_delay,
            trace_note=reply.trace_note + trace_extra,
            burst_queue=reply.burst_messages if reply.should_burst else [],
            propose_scene=reply.propose_scene,
        )
        return None, delivery, "답장을 준비 중이에요."

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
            "status_line": "이전 대화 보는 중 · 입력창이 비어 있을 때 ↑↓로 이동",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
            "scroll_delta": 2,
        }
    if is_scroll_down and not draft:
        return {
            "draft": draft,
            "status_line": "최신 대화로 이동 · 입력창이 비어 있을 때 ↑↓로 다시 보기",
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
        # User sending while assistant busy: abandon the in-flight job
        # and start a new one that sees ALL user messages. The old thread
        # still runs in background but its result will be ignored.
        if pending_job is not None and not text.startswith("/"):
            pending_job = None  # drop reference; thread completes into dead queue
        if pending_delivery is not None and not text.startswith("/"):
            pending_delivery = None
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
        # Build time context for LLM
        now_str = time.strftime("%Y-%m-%d %H:%M")
        time_since = ""
        if session.last_activity_at:
            gap = (utc_now() - session.last_activity_at).total_seconds()
            if gap > 60:
                mins = int(gap / 60)
                time_since = f"{mins}분" if mins < 60 else f"{mins // 60}시간 {mins % 60}분"
        memory = "; ".join(session.memory_notes[-5:])
        from .i18n import get_language
        lang = get_language()
        job = BackgroundJob(
            "reply",
            lambda: provider.generate_reply(
                persona, session.recent_history(), text,
                session.affection_score, mood,
                current_time=now_str, time_since_last=time_since,
                memory=memory,
                difficulty=persona.difficulty,
                language=lang,
                special_mode=persona.special_mode,
                **session.prompt_context(),
            ),
        )
        return {
            "draft": "",
            "status_line": "assistant is thinking...",
            "pending_job": job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
            "sent": True,
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
    lang = get_language()
    if lowered == "/quit":
        return {
            "draft": "",
            "status_line": t("status_session_closed", lang),
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": True,
        }
    if lowered == "/move":
        session.add_system_message(
            "Use /move in the main loop (handled separately)."
        )
        return {
            "draft": "",
            "status_line": "Opening scene selector...",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
            "move": True,
        }
    if lowered == "/back":
        return {
            "draft": "",
            "status_line": t("status_back_to_menu", lang),
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": True,
            "back": True,
        }
    if lowered == "/help":
        session.add_system_message(
            "Commands: /help /back /quit /strategy /advice /coach /trace /status /affection /export /music /voice on|off /listen"
        )
        return {
            "draft": "",
            "status_line": t("status_help_opened", lang),
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
        }
    if lowered == "/trace":
        return {
            "draft": "",
            "status_line": t("status_trace_toggled", lang),
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
            "status_line": t("status_session_posted", lang),
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
        }
    if lowered == "/strategy" or lowered == "/discuss":
        return {
            "draft": "",
            "status_line": t("status_strategy", lang),
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
            "strategy": True,
        }
    if lowered == "/advice":
        # Show latest coach feedback as a system message
        feedback = session.last_coach_feedback or "아직 조언이 없어요. 메시지를 보내보세요!"
        strength = session.last_coach_strength or "아직 강점 분석이 없어요."
        weakness = session.last_coach_weakness or "아직 약점 분석이 없어요."
        charm_point = session.last_coach_charm_point or "아직 매력 포인트 분석이 없어요."
        charm_type = session.last_coach_charm_type or "unknown"
        charm_feedback = session.last_coach_charm_feedback or "아직 매력 피드백이 없어요."
        session.add_system_message(
            f"💡 Coach\n✓ Strength: {strength}\n✗ Weakness: {weakness}\n♥ Charm Point: {charm_point}\n♥ Charm Type: {charm_type}\n♥ Charm Feedback: {charm_feedback}\n→ Advice: {feedback}"
        )
        return {
            "draft": "",
            "status_line": t("status_coach_posted", lang),
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
        }
    if lowered == "/coach":
        return {
            "draft": "",
            "status_line": "코치 피드백 전체보기를 열어요.",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": False,
            "coach_full": True,
        }
    if lowered == "/affection":
        report = session.affection_report()
        hearts = "❤️" * report["level"] + "🤍" * (5 - report["level"])
        bar_filled = report["score"] // 5
        bar_empty = 20 - bar_filled
        bar = "█" * bar_filled + "░" * bar_empty
        battle_power = report["battle_power"]

        def metric_cell(short: str, value: int) -> str:
            filled = min(8, max(0, round(value / 12.5)))
            meter = "█" * filled + "░" * (8 - filled)
            return f"{short:<6}{value:>3} {meter}"

        row1 = "  |  ".join([
            metric_cell("Init", battle_power["Initiation"]),
            metric_cell("Assert", battle_power["Assertiveness"]),
            metric_cell("Open", battle_power["Self-Disclosure"]),
            metric_cell("Support", battle_power["Emotional Support"]),
            metric_cell("Repair", battle_power["Conflict Repair"]),
        ])
        row2 = "  |  ".join([
            metric_cell("Emp", battle_power["Empathy"]),
            metric_cell("Control", battle_power["Emotional Control"]),
            metric_cell("Play", battle_power["Playfulness"]),
            metric_cell("React", battle_power["Responsiveness"]),
            metric_cell("Steady", battle_power["Consistency"]),
        ])
        charm_emoji = report.get("charm_type_emoji", "✨")

        lines = [
            f"{'═' * 92}",
            f"  ⚔ 전투력 측정",
            f"  {hearts}  {report['label']}",
            f"  [{bar}] {report['score']}/100",
            f"{'─' * 92}",
            f"  {row1}",
            f"  {row2}",
            f"{'─' * 92}",
            f"  Charm Point: {session.last_coach_charm_point or '아직 분석 없음'}",
            f"  Charm Type: {charm_emoji} {session.last_coach_charm_type or 'unknown'}",
            f"  Charm Feedback: {session.last_coach_charm_feedback or '아직 분석 없음'}",
            f"{'─' * 92}",
            f"  Messages:  you {report['total_user']}  /  {session.persona.name} {report['total_assistant']}",
            f"  Avg length: {report['avg_msg_length']} chars",
            f"  Positive:  {report['positive_messages']}  |  Negative: {report['negative_messages']}",
            f"  Mood: {report['mood']} (intensity {report['mood_intensity']:.1f})",
            f"{'─' * 92}",
            f"  Tip: {report['tip']}",
            f"{'─' * 92}",
        ]
        session.add_system_message("\n".join(lines))
        return {
            "draft": "",
            "status_line": t("status_battle_power", lang),
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
            relationship_state=session.export_state().get("relationship_state"),
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
        Layout(_render_composer(draft, status_line, user_typing), size=max(5, 4 + (len(draft) // 50))),
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

    relation = _localized_relationship_label(session.current_relationship_label)
    relation_lower = relation.lower()
    if any(token in relation_lower for token in ("married", "wife", "husband", "spouse")):
        mode_icon = "💍"
    elif any(token in relation_lower for token in ("dating", "girlfriend", "boyfriend", "fiance")):
        mode_icon = "💕"
    elif any(token in relation_lower for token in ("enemy", "rival", "ex")):
        mode_icon = "⚔"
    else:
        mode_icon = {"girlfriend": "💕", "crush": "💘"}.get(persona.relationship_mode, "💬")

    body = Text.assemble(
        (f" {mode_icon} ", ""),
        (persona.name, f"bold {persona.accent_color}"),
        (f"  {persona.age}세", "dim"),
        ("  ·  ", "dim"),
        (relation, f"italic {persona.accent_color}"),
        ("  ·  ", "dim"),
        (f"{mood_emoji} {_localized_mood_label(session.mood.current)}", ""),
        ("\n ", ""),
        (session.current_relationship_summary, f"bold {persona.accent_color}"),
        ("\n ", ""),
        (session.relationship_state.situation or persona.situation, "dim"),
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
            Text(f"\n  {t('start_conversation')}\n", style="dim italic")
        ))
    scroll_hint = (
        f"[grey70]↑{scroll_offset} older messages · 입력창이 비어 있을 때 ↑↓ 이동[/grey70]"
        if scroll_offset > 0
        else "[grey70]입력창이 비어 있을 때 ↑↓로 이전 대화 보기[/grey70]"
    )
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
    keys = "[grey70]Enter[/grey70] 전송  [grey70]Esc[/grey70] 뒤로  [grey70]입력창 비었을 때 ↑↓[/grey70] 이전 대화  [grey70]/help[/grey70]"
    title = "[bright_blue]typing...[/bright_blue]" if user_typing else "[dim]message[/dim]"
    body = Text()
    if draft:
        body.append(f" {draft}")
        body.append("|", style="blink")
    else:
        body.append(" 메시지를 입력하세요...", style="dim italic")
    body.append("\n\n ")
    body.append(status_line, style="dim italic")
    return Panel(
        body,
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
    table.add_row("Mood", f"{mood_emoji} {_localized_mood_label(session.mood.current)}")
    table.add_row("Affection", f"{aff_bar} {aff}")
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
    table.add_row("Status", f"[dim]{trace.status_line[:28]}[/dim]")

    # Coach feedback panel
    from rich.console import Group as RichGroup
    feedback_panels = [table]
    if session.last_internal_thought:
        thought_text = f"[italic dim]{session.last_internal_thought[:80]}[/italic dim]"
        feedback_panels.append(Panel(
            thought_text,
            title=f"[dim]{persona.name} 속마음[/dim]",
            border_style="magenta",
            padding=(0, 1),
        ))
    if (
        session.last_coach_feedback
        or session.last_coach_strength
        or session.last_coach_weakness
        or session.last_coach_charm_point
        or session.last_coach_charm_type
        or session.last_coach_charm_feedback
    ):
        coach_lines = []
        if session.last_coach_strength:
            coach_lines.append(Text.assemble(
                ("✓ Strength  ", "bold green"),
                (session.last_coach_strength[:220], "green"),
            ))
        if session.last_coach_weakness:
            coach_lines.append(Text.assemble(
                ("✗ Weakness  ", "bold red"),
                (session.last_coach_weakness[:220], "red"),
            ))
        if session.last_coach_charm_point:
            coach_lines.append(Text.assemble(
                ("♥ Charm Point  ", "bold magenta"),
                (session.last_coach_charm_point[:220], "magenta"),
            ))
        if session.last_coach_charm_type:
            coach_lines.append(Text.assemble(
                ("♥ Charm Type  ", "bold bright_magenta"),
                (session.last_coach_charm_type[:220], "bright_magenta"),
            ))
        if session.last_coach_charm_feedback:
            coach_lines.append(Text.assemble(
                ("♥ Charm Feedback  ", "bold cyan"),
                (session.last_coach_charm_feedback[:220], "cyan"),
            ))
        coach_lines.append(Text.assemble(
            ("→ Advice  ", "bold cyan"),
            (session.last_coach_feedback[:220], "cyan"),
        ))
        feedback_panels.append(Panel(
            RichGroup(*coach_lines),
            title="[bold cyan]💡 Dating Coach[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        ))
    body = RichGroup(*feedback_panels)
    return Panel(body, title="[dim]trace[/dim]", border_style="grey37", padding=(0, 0))


def _show_full_coach_panel(live: Any, console: Console, session: ConversationSession) -> None:
    live.stop()
    console.clear()
    lines = [
        "",
        f"  Strength: {session.last_coach_strength or '아직 강점 분석이 없어요.'}",
        "",
        f"  Weakness: {session.last_coach_weakness or '아직 약점 분석이 없어요.'}",
        "",
        f"  Charm Point: {session.last_coach_charm_point or '아직 매력 포인트 분석이 없어요.'}",
        "",
        f"  Charm Type: {session.last_coach_charm_type or 'unknown'}",
        "",
        f"  Charm Feedback: {session.last_coach_charm_feedback or '아직 매력 피드백이 없어요.'}",
        "",
        f"  Advice: {session.last_coach_feedback or '아직 조언이 없어요. 메시지를 보내보세요!'}",
        "",
    ]
    _show_scrollable_text_panel(
        console,
        title="[bold cyan]💡 Dating Coach[/bold cyan]",
        border_style="cyan",
        lines=lines,
        width=88,
    )
    live.start(refresh=True)


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
        session.current_relationship_label,
        session.current_relationship_summary,
        session.mood.current,
        session.mood.intensity,
        scroll_offset,
        int(time.monotonic() * 3) % 4 if assistant_typing else 0,  # animate dots
        session.last_coach_feedback,
        session.last_internal_thought,
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
