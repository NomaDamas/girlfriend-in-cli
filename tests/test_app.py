from pathlib import Path

from rich.console import Console

from girlfriend_generator.app import _handle_command, _render_screen
from girlfriend_generator.engine import ConversationSession
from girlfriend_generator.models import RuntimeTrace
from girlfriend_generator.personas import load_persona
from girlfriend_generator.voice import DisabledVoiceInput


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
