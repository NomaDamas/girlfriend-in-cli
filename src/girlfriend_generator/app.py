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
from .models import MOOD_EMOJI, ChatMessage, Persona, ProviderReply, RuntimeTrace
from .personas import load_persona
from .providers import ProviderConfig, build_provider
from .session_io import export_session, load_session_messages
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
    status_line = "Enter로 메시지 입력"
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
                    trace.status_line = pending_delivery.trace_note
                    status_line = pending_delivery.trace_note
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

                # Check for game over / success ending
                if session.affection_score <= 0 and not session.ended:
                    session.ended = True
                    _show_ending(live, console, persona, session, "game_over", provider)
                    return 2
                if session.affection_score >= 100 and not session.ended:
                    session.ended = True
                    _show_ending(live, console, persona, session, "success", provider)
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
                        )
                        if proactive_reply:
                            pending_delivery = PendingDelivery(
                                kind="initiative",
                                text=proactive_reply,
                                due_at=time.monotonic() + 0.6,
                                trace_note="proactive: LLM scheduled follow-up",
                            )
                    except Exception:
                        pass

                if session.nudge_due(now) and pending_job is None and pending_delivery is None:
                    nudge_text = provider.generate_nudge(
                        persona, session.recent_history(), session.affection_score,
                    )
                    pending_delivery = PendingDelivery(
                        kind="nudge",
                        text=nudge_text,
                        due_at=time.monotonic() + 1.2,
                        trace_note="idle-nudge: persona noticed silence",
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
                        trace_note="idle-initiative: persona started conversation",
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
                                    )
                                    report_reply = provider.generate_reply(
                                        persona, [], report_prompt,
                                        session.affection_score, session.mood.current,
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
                                session.affection_score = min(100, session.affection_score + 5)
                                session.mood.shift(target.mood_hint)
                                # Clear messages for new scene, keep summary
                                if report.scene_summary:
                                    session.messages.clear()
                                    session.add_system_message(f"[이전 장소 요약] {report.scene_summary}")
                                    session.add_system_message(f"[현재 장소] {target.name} — {target.description}")
                        elif any(w in lower_text for w in reject_words):
                            scene_state.reject_transition()
                            session.affection_score = max(0, session.affection_score - 2)
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
                                )
                                try:
                                    eval_reply = provider.generate_reply(
                                        persona, session.recent_history(),
                                        eval_prompt, session.affection_score,
                                        session.mood.current,
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


def _show_ending(
    live: Any,
    console: Console,
    persona: Persona,
    session: ConversationSession,
    kind: str,
    provider: Any,
) -> None:
    """Show full-screen game over or success ending with LLM-generated report."""
    from rich.align import Align
    from rich.panel import Panel
    from rich.text import Text

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
        '  "what_went_wrong": "what the user did right or wrong (1-2 sentences)",\n'
        '  "rating": "S/A/B/C/D/F grade on their performance"\n'
        "}"
    )
    try:
        from .i18n import get_language
        ending_reply = provider.generate_reply(
            persona, session.recent_history(), ending_prompt,
            session.affection_score, session.mood.current,
            difficulty=persona.difficulty,
            language=get_language(),
            special_mode=persona.special_mode,
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
            "what_went_wrong": "",
            "rating": "?",
        }

    live.stop()
    console.clear()

    color = "red" if kind == "game_over" else "bright_green"
    title = data.get("report_title", "END")
    rating = data.get("rating", "?")

    body = Text.assemble(
        ("\n", ""),
        (f"  {data.get('persona_final_words', '')}\n\n", "italic white"),
        ("  ──────────────────────────────\n\n", "dim"),
        (f"  {data.get('ending_narrative', '')}\n\n", "white"),
        ("  ──────────────────────────────\n\n", "dim"),
        ("  Highlights:\n", "bold"),
    )
    lines = [body]
    for h in data.get("highlights", []):
        lines.append(Text(f"    • {h}\n", style="cyan"))
    if data.get("user_strength"):
        lines.append(Text.assemble(
            ("\n  Strength:  ", "bold green"),
            (f"{data.get('user_strength', '')}\n", "green"),
        ))
    if data.get("user_weakness"):
        lines.append(Text.assemble(
            ("\n  Weakness:  ", "bold red"),
            (f"{data.get('user_weakness', '')}\n", "red"),
        ))
    lines.append(Text.assemble(
        ("\n  ", ""),
        ("Review:  ", "bold"),
        (f"{data.get('what_went_wrong', '')}\n\n", "yellow"),
        ("  Grade:  ", "bold"),
        (f"{rating}\n\n", f"bold {color}"),
        ("  Final Affection:  ", "bold"),
        (f"{session.affection_score}/100\n", f"bold {color}"),
    ))

    from rich.console import Group as RichGroup
    panel_body = RichGroup(*lines)
    console.print()
    console.print(Align.center(Panel(
        panel_body,
        title=f"[bold {color}]━━ {title} ━━[/bold {color}]",
        border_style=color,
        width=80,
        padding=(1, 2),
    )))
    console.print()
    console.print(Align.center(Text("Press Enter to return to main menu", style="dim")))
    try:
        from .wide_input import wide_input
        wide_input("")
    except (EOFError, KeyboardInterrupt):
        pass


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

        # ProviderReply now has parsed fields from LLM JSON
        actual_text = reply.text  # already clean
        session.affection_score = max(0, min(100, session.affection_score + reply.affection_delta))
        if reply.mood and reply.mood in ("neutral", "happy", "playful", "sulky", "excited", "worried", "flirty"):
            session.mood.shift(reply.mood)
        if reply.memory_update:
            session.memory_notes.append(reply.memory_update)
        session.last_coach_feedback = reply.coach_feedback
        session.last_coach_strength = reply.coach_strength
        session.last_coach_weakness = reply.coach_weakness
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
    if lowered == "/quit":
        return {
            "draft": "",
            "status_line": "Session closed.",
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
            "status_line": "Back to main menu.",
            "pending_job": pending_job,
            "show_trace": show_trace,
            "voice_output_enabled": voice_output_enabled,
            "quit": True,
            "back": True,
        }
    if lowered == "/help":
        session.add_system_message(
            "Commands: /help /back /quit /strategy /advice /trace /status /affection /export /music /voice on|off /listen"
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
    if lowered == "/strategy" or lowered == "/discuss":
        return {
            "draft": "",
            "status_line": "Strategy discussion...",
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
        session.add_system_message(
            f"💡 Coach\n✓ Strength: {strength}\n✗ Weakness: {weakness}\n→ Advice: {feedback}"
        )
        return {
            "draft": "",
            "status_line": "Coach advice posted.",
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
    if draft:
        prompt = f" {draft}[blink]|[/blink]"
    else:
        prompt = " [dim italic]메시지를 입력하세요...[/dim italic]"
    keys = "[dim]Enter[/dim] 전송  [dim]Esc[/dim] 뒤로  [dim]↑↓[/dim] 스크롤  [dim]/help[/dim]"
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
    if session.last_coach_feedback:
        coach_lines = []
        if session.last_coach_strength:
            coach_lines.append(Text.assemble(
                ("✓ Strength  ", "bold green"),
                (session.last_coach_strength[:80], "green"),
            ))
        if session.last_coach_weakness:
            coach_lines.append(Text.assemble(
                ("✗ Weakness  ", "bold red"),
                (session.last_coach_weakness[:80], "red"),
            ))
        coach_lines.append(Text.assemble(
            ("→ Advice  ", "bold cyan"),
            (session.last_coach_feedback[:120], "cyan"),
        ))
        feedback_panels.append(Panel(
            RichGroup(*coach_lines),
            title="[bold cyan]💡 Dating Coach[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        ))
    body = RichGroup(*feedback_panels)
    return Panel(body, title="[dim]trace[/dim]", border_style="grey37", padding=(0, 0))


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
