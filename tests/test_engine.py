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
    persona = load_persona(Path("personas/dua-international.json"))
    session = ConversationSession(persona=persona)
    start = utc_now()
    session.bootstrap(now=start)

    assert session.awaiting_user_reply is True
    assert session.seconds_until_nudge(start) == session._idle_after_seconds()

    session.add_user_message("방금 빌드 끝났어. 이제 너한테 집중 가능.")

    assert session.awaiting_user_reply is False
    assert session.nudge_due_at is None
    assert session.nudge_count == 0


def test_nudge_due_and_consumed_once() -> None:
    persona = load_persona(Path("personas/wonyoung-idol.json"))
    session = ConversationSession(persona=persona)
    start = utc_now()
    session.bootstrap(now=start)
    due_time = start + timedelta(seconds=session._idle_after_seconds())
    starting_affection = session.affection_score

    assert session.nudge_due(due_time) is True

    text = session.consume_nudge(now=due_time)

    assert text == persona.nudge_policy.templates[0]
    assert session.nudge_count == 1
    assert session.awaiting_user_reply is True
    assert session.affection_score == starting_affection - 2


def test_tick_emits_idle_nudge_when_reply_is_overdue() -> None:
    persona = load_persona(Path("personas/wonyoung-idol.json"))
    session = ConversationSession(persona=persona)
    provider = _StubProvider()
    start = utc_now()
    session.bootstrap(now=start)

    result = session.fast_forward(
        seconds=session._idle_after_seconds() + 5,
        provider=provider,
    )

    assert result.event_type == "nudge"
    assert result.text == persona.nudge_policy.templates[0]
    assert result.trace_note == "tick:nudge"


def test_tick_emits_initiative_when_conversation_is_quiet() -> None:
    persona = load_persona(Path("personas/dua-international.json"))
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


def test_bootstrap_greeting_uses_configured_language(monkeypatch) -> None:
    persona = load_persona(Path("personas/wonyoung-idol.json"))
    session = ConversationSession(persona=persona)
    start = utc_now()
    monkeypatch.setattr("girlfriend_generator.engine.get_language", lambda: "en")

    session.bootstrap(now=start)

    assert session.messages[0].role == "assistant"
    assert "wanted to text you first" in session.messages[0].text


def test_affection_delta_dampens_generic_repeated_flattery() -> None:
    persona = load_persona(Path("personas/wonyoung-idol.json"))
    session = ConversationSession(persona=persona)

    first = session.apply_affection_delta(10, "좋아", source="reply")
    second = session.apply_affection_delta(10, "좋아", source="reply")

    assert first <= 6
    assert second <= 7
    assert session.affection_score <= 63


def test_affection_delta_rewards_specific_consistent_interest_more_than_generic() -> None:
    persona = load_persona(Path("personas/wonyoung-idol.json"))
    generic_session = ConversationSession(persona=persona)
    specific_session = ConversationSession(persona=persona)

    generic_gain = generic_session.apply_affection_delta(10, "좋아", source="reply")
    first_specific = specific_session.apply_affection_delta(
        10,
        "어제 힘들다고 했잖아 그래서 네가 좋아하는 커피 챙겨주고 싶었어",
        source="reply",
    )
    second_specific = specific_session.apply_affection_delta(
        10,
        "아까 말한 발표 끝나면 같이 맛있는 거 먹자 내가 기억하고 있을게",
        source="reply",
    )

    assert first_specific > generic_gain
    assert second_specific >= first_specific
    assert specific_session.affection_score > generic_session.affection_score


def test_affection_delta_repeated_harsh_replies_drop_harder_each_time() -> None:
    persona = load_persona(Path("personas/wonyoung-idol.json"))
    session = ConversationSession(persona=persona)

    first = session.apply_affection_delta(-8, "닥쳐", source="reply")
    second = session.apply_affection_delta(-8, "꺼져", source="reply")

    assert first <= -12
    assert second < first
    assert session.affection_score <= 20


def test_endless_mode_clamps_affection_inside_playable_range() -> None:
    persona = load_persona(Path("personas/wonyoung-idol.json"))
    session = ConversationSession(persona=persona)
    session.continue_after_ending("success")

    assert session.endless_mode is True
    session.apply_affection_delta(40, "진짜 사랑해", source="reply")
    assert session.affection_score <= 99
    session.apply_affection_delta(-80, "닥쳐 꺼져", source="reply")
    assert session.affection_score >= 1
