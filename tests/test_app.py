from pathlib import Path

from rich.console import Console

from girlfriend_generator.app import _finish_job, _handle_command, _render_screen, _render_trace
from girlfriend_generator.engine import ConversationSession
from girlfriend_generator.models import ProviderReply, RuntimeTrace
from girlfriend_generator.personas import load_persona
from girlfriend_generator.voice import DisabledVoiceInput, VoiceInputAdapter


def _load_test_persona():
    return load_persona(Path("personas/han-seo-jin-crush.json"))


def _render_to_text(renderable) -> str:
    console = Console(record=True, width=120)
    console.print(renderable)
    return console.export_text()


def test_listen_command_requires_configured_voice_input(tmp_path: Path) -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()

    outcome = _handle_command(
        text="/listen",
        session=session,
        provider=object(),
        pending_job=None,
        voice_input=DisabledVoiceInput(),
        voice_output_available=False,
        voice_output_enabled=False,
        show_trace=True,
        session_dir=tmp_path,
    )

    assert outcome["pending_job"] is None
    assert outcome["status_line"] == "Voice input unavailable."
    assert session.messages[-1].role == "system"
    assert "Voice input is disabled" in session.messages[-1].text


def test_listen_command_starts_background_job_when_voice_input_is_configured(
    tmp_path: Path,
) -> None:
    class FakeVoiceInput(VoiceInputAdapter):
        def __init__(self) -> None:
            super().__init__(name="external-command")

        def listen(self) -> str:
            return "지금 뭐 해?"

    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()

    outcome = _handle_command(
        text="/listen",
        session=session,
        provider=object(),
        pending_job=None,
        voice_input=FakeVoiceInput(),
        voice_output_available=False,
        voice_output_enabled=False,
        show_trace=True,
        session_dir=tmp_path,
    )

    assert outcome["pending_job"] is not None
    assert outcome["pending_job"].kind == "listen"
    assert outcome["status_line"] == "Listening via external transcription command..."


def test_finish_job_turns_voice_transcript_into_reply_job() -> None:
    class FakeProvider:
        def generate_reply(self, persona, history, user_text, affection_score):
            return ProviderReply(
                text=f"reply to: {user_text}",
                typing_seconds=0.2,
                trace_note="turbo-heuristic: zero-network local reply",
            )

    class PreviousJob:
        kind = "listen"

    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()

    next_job, next_delivery, status = _finish_job(
        session=session,
        persona=persona,
        provider=FakeProvider(),
        result=(True, "오늘은 네 목소리 톤이 궁금했어."),
        previous_job=PreviousJob(),
        previous_delivery=None,
        previous_status="Listening via external transcription command...",
    )

    assert session.messages[-1].role == "user"
    assert session.messages[-1].text == "오늘은 네 목소리 톤이 궁금했어."
    assert next_job is not None
    assert next_job.kind == "reply"
    assert next_delivery is None
    assert status == "voice transcript captured"


def test_export_command_writes_local_transcript_files(tmp_path: Path) -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()
    session.add_user_message("오늘은 네가 먼저 말 걸어줘서 좋네.")

    outcome = _handle_command(
        text="/export",
        session=session,
        provider=object(),
        pending_job=None,
        voice_input=DisabledVoiceInput(),
        voice_output_available=False,
        voice_output_enabled=False,
        show_trace=True,
        session_dir=tmp_path,
    )

    exported_files = sorted(path.name for path in tmp_path.iterdir())

    assert outcome["status_line"] == "Session exported."
    assert len(exported_files) == 2
    assert any(name.endswith(".json") for name in exported_files)
    assert any(name.endswith(".md") for name in exported_files)
    assert str(tmp_path) in session.messages[-1].text


def test_render_screen_shows_typing_and_trace_visibility() -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()
    trace = RuntimeTrace(
        persona_path=Path("personas/han-seo-jin-crush.json"),
        provider_name="heuristic",
        provider_model=None,
        performance_mode="turbo",
        voice_output_name="off",
        voice_input_name="off",
        pending_reply_kind="nudge",
        pending_nudge_in=12,
        pending_initiative_in=420,
    )

    renderable = _render_screen(
        console=Console(width=120),
        persona=persona,
        session=session,
        draft="지금 뭐 해?",
        trace=trace,
        show_trace=True,
        status_line="assistant is thinking...",
        assistant_typing=True,
        user_typing=True,
    )
    rendered = _render_to_text(renderable)

    assert "ECC Trace" in rendered
    assert "AGENTS.md +" in rendered
    assert ".codex/AGENTS" in rendered
    assert "You are typing..." in rendered
    assert "typing" in rendered


def test_render_trace_shows_idle_timers() -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()
    trace = RuntimeTrace(
        persona_path=Path("personas/han-seo-jin-crush.json"),
        provider_name="heuristic",
        provider_model=None,
        performance_mode="turbo",
        voice_output_name="off",
        voice_input_name="external-command",
        pending_reply_kind="nudge",
        pending_nudge_in=12,
        pending_initiative_in=420,
    )

    rendered = _render_to_text(_render_trace(trace, persona, session))

    assert "Init in" in rendered
    assert "420" in rendered
    assert "Voice in" in rendered
    assert "external-command" in rendered


def test_trace_command_toggles_panel_visibility(tmp_path: Path) -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()

    outcome = _handle_command(
        text="/trace",
        session=session,
        provider=object(),
        pending_job=None,
        voice_input=DisabledVoiceInput(),
        voice_output_available=False,
        voice_output_enabled=False,
        show_trace=True,
        session_dir=tmp_path,
    )

    assert outcome["show_trace"] is False
    assert outcome["status_line"] == "Trace panel toggled."


def test_voice_commands_toggle_when_backend_is_available(tmp_path: Path) -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()

    enabled = _handle_command(
        text="/voice on",
        session=session,
        provider=object(),
        pending_job=None,
        voice_input=DisabledVoiceInput(),
        voice_output_available=True,
        voice_output_enabled=False,
        show_trace=True,
        session_dir=tmp_path,
    )
    disabled = _handle_command(
        text="/voice off",
        session=session,
        provider=object(),
        pending_job=None,
        voice_input=DisabledVoiceInput(),
        voice_output_available=True,
        voice_output_enabled=True,
        show_trace=True,
        session_dir=tmp_path,
    )

    assert enabled["voice_output_enabled"] is True
    assert enabled["status_line"] == "Voice output enabled."
    assert disabled["voice_output_enabled"] is False
    assert disabled["status_line"] == "Voice output disabled."
