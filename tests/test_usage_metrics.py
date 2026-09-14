"""Tests for local-first usage metrics."""

from pathlib import Path

from girlfriend_generator import usage_metrics


class FakeClock:
    def __init__(self) -> None:
        self.now = 10.0

    def __call__(self) -> float:
        return self.now


def test_session_duration_persists_across_loads(tmp_path: Path) -> None:
    path = tmp_path / "usage_metrics.json"
    clock = FakeClock()
    session = usage_metrics.start_session(
        persona_name="Yu-na",
        persona_path="personas/yu-na.json",
        provider_name="openai",
        provider_model="gpt-5.4",
        performance_mode="turbo",
        resumed=False,
        path=path,
        clock=clock,
    )

    clock.now += 12.5
    duration = session.finish()

    metrics = usage_metrics.load_metrics(path)
    assert duration == 12.5
    assert metrics["total_active_seconds"] == 12.5
    assert metrics["sessions_total"] == 1
    assert metrics["events"][-1]["type"] == "session_ended"


def test_resumed_session_counter_and_event_are_recorded(tmp_path: Path) -> None:
    path = tmp_path / "usage_metrics.json"
    session = usage_metrics.start_session(
        persona_name="Yu-na",
        persona_path="personas/yu-na.json",
        provider_name="anthropic",
        provider_model="claude-sonnet-4-6",
        performance_mode="balanced",
        resumed=True,
        path=path,
    )
    session.finish()

    metrics = usage_metrics.load_metrics(path)
    assert metrics["sessions_total"] == 1
    assert metrics["sessions_resumed"] == 1
    assert metrics["events"][0]["type"] == "session_resumed"


def test_metrics_do_not_store_transcript_text(tmp_path: Path) -> None:
    path = tmp_path / "usage_metrics.json"
    usage_metrics.record_event(
        "session_started",
        {
            "persona_name": "Yu-na",
            "provider_name": "openai",
            "user_text": "this should never be stored",
            "assistant_reply": "nor should this",
        },
        path=path,
    )

    raw = path.read_text(encoding="utf-8")
    assert "this should never be stored" not in raw
    assert "nor should this" not in raw
    assert "Yu-na" in raw


def test_load_metrics_recovers_from_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "usage_metrics.json"
    path.write_text("{not json", encoding="utf-8")

    metrics = usage_metrics.load_metrics(path)

    assert metrics["total_active_seconds"] == 0.0
    assert metrics["events"] == []
