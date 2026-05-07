"""Tests for persona reactions to non-text terminal actions."""

from pathlib import Path

from girlfriend_generator.app import _handle_command, _handle_key
from girlfriend_generator.engine import ConversationSession, utc_now
from girlfriend_generator.personas import load_persona
from girlfriend_generator.voice import DisabledVoiceInput


def _persona():
    return load_persona(Path("personas/wonyoung-idol.json"))


def _base_kwargs(session, persona):
    return {
        "session": session,
        "persona": persona,
        "provider": object(),
        "pending_job": None,
        "pending_delivery": None,
        "voice_input": DisabledVoiceInput(),
        "voice_output_available": False,
        "voice_output_enabled": False,
        "show_trace": True,
        "session_dir": Path("sessions"),
    }


def _command_kwargs(session):
    return {
        "session": session,
        "provider": object(),
        "pending_job": None,
        "pending_delivery": None,
        "voice_input": DisabledVoiceInput(),
        "voice_output_available": False,
        "voice_output_enabled": False,
        "show_trace": True,
        "session_dir": Path("sessions"),
    }


def test_large_paste_triggers_persona_reaction() -> None:
    persona = _persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()
    before = len(session.messages)

    outcome = _handle_key(
        key="x" * 120,
        draft="",
        **_base_kwargs(session, persona),
    )

    assert outcome["draft"] == "x" * 120
    assert "noticed the big paste" in outcome["status_line"]
    assert len(session.messages) == before + 1
    assert session.messages[-1].role == "assistant"
    assert "붙여넣었네" in session.messages[-1].text


def test_scrollback_triggers_persona_reaction() -> None:
    persona = _persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()
    before = len(session.messages)

    outcome = _handle_key(
        key="\x1b[A",
        draft="",
        **_base_kwargs(session, persona),
    )

    assert outcome["scroll_delta"] == 2
    assert len(session.messages) == before + 1
    assert session.messages[-1].role == "assistant"
    assert "예전 대화" in session.messages[-1].text


def test_non_text_reactions_are_rate_limited() -> None:
    persona = _persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()

    _handle_key(key="x" * 120, draft="", **_base_kwargs(session, persona))
    before = len(session.messages)
    _handle_key(key="y" * 120, draft="", **_base_kwargs(session, persona))

    assert len(session.messages) == before


def test_action_reaction_kill_switch() -> None:
    persona = _persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()

    off = _handle_command(
        text="/actions off",
        **_command_kwargs(session),
    )
    assert off["status_line"] == "Non-text action reactions off."

    before = len(session.messages)
    _handle_key(key="x" * 120, draft="", **_base_kwargs(session, persona))
    assert len(session.messages) == before

    on = _handle_command(
        text="/actions on",
        **_command_kwargs(session),
    )
    assert on["status_line"] == "Non-text action reactions on."
    session.last_action_reaction_at = utc_now().replace(year=2000)
    _handle_key(key="x" * 120, draft="", **_base_kwargs(session, persona))
    assert len(session.messages) == before + 1
