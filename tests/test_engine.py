from datetime import timedelta
from pathlib import Path

from girlfriend_generator.engine import ConversationSession, utc_now
from girlfriend_generator.personas import load_persona


class _StubProvider:
    """Minimal provider stub for engine tests."""
    def generate_initiative(self, persona, history, affection_score):
        return "hey, you there?"
    def generate_nudge(self, persona, history, affection_score):
        return "why no reply?"


def test_user_reply_clears_pending_nudge() -> None:
    persona = load_persona(Path("personas/yu-na-girlfriend.json"))
    session = ConversationSession(persona=persona)
    start = utc_now()
    session.bootstrap(now=start)

    assert session.awaiting_user_reply is True
    assert session.seconds_until_nudge(start) == persona.nudge_policy.idle_after_seconds

    session.add_user_message("방금 빌드 끝났어. 이제 너한테 집중 가능.")

    assert session.awaiting_user_reply is False
    assert session.nudge_due_at is None
    assert session.nudge_count == 0


def test_nudge_due_and_consumed_once() -> None:
    persona = load_persona(Path("personas/han-seo-jin-crush.json"))
    session = ConversationSession(persona=persona)
    start = utc_now()
    session.bootstrap(now=start)
    due_time = start + timedelta(seconds=persona.nudge_policy.idle_after_seconds)

    assert session.nudge_due(due_time) is True

    text = session.consume_nudge(now=due_time)

    assert text == persona.nudge_policy.templates[0]
    assert session.nudge_count == 1
    assert session.awaiting_user_reply is True


def test_tick_emits_idle_nudge_when_reply_is_overdue() -> None:
    persona = load_persona(Path("personas/han-seo-jin-crush.json"))
    session = ConversationSession(persona=persona)
    provider = _StubProvider()
    start = utc_now()
    session.bootstrap(now=start)

    result = session.fast_forward(
        seconds=persona.nudge_policy.idle_after_seconds + 5,
        provider=provider,
    )

    assert result.event_type == "nudge"
    assert result.text == persona.nudge_policy.templates[0]
    assert result.trace_note == "tick:nudge"


def test_tick_emits_initiative_when_conversation_is_quiet() -> None:
    persona = load_persona(Path("personas/yu-na-girlfriend.json"))
    session = ConversationSession(persona=persona)
    provider = _StubProvider()
    start = utc_now()
    session.schedule_initiative(start)

    result = session.tick(
        provider=provider,
        now=start + timedelta(seconds=persona.initiative_profile.max_interval_seconds + 5),
    )

    assert result.event_type == "initiative"
    assert result.text
    assert result.trace_note == "tick:initiative"


def test_openai_provider_is_default() -> None:
    from girlfriend_generator.providers import build_provider, ProviderConfig, OpenAIProvider
    provider = build_provider(ProviderConfig(name="openai"))
    assert isinstance(provider, OpenAIProvider)
