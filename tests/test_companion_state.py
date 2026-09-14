"""Tests for local relationship milestone state."""

from __future__ import annotations

import pytest

from girlfriend_generator import companion_state


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("GIRLFRIEND_IN_CLI_HOME", str(tmp_path))
    return tmp_path / companion_state._FILENAME


def test_load_returns_empty_when_no_file(isolated_state):
    assert companion_state.load_cleared() == []
    assert companion_state.has_any_cleared() is False
    assert companion_state.cleared_badge_text() == ""


def test_mark_persists_record(isolated_state):
    record = companion_state.mark_cleared(
        persona_name="Yu-na",
        milestone="lover",
        persona_path="personas/yu-na-girlfriend.json",
    )

    assert record.persona_name == "Yu-na"
    assert record.milestone == "lover"
    assert isolated_state.exists()
    assert companion_state.has_any_cleared() is True
    assert "Yu-na" in companion_state.cleared_badge_text()


def test_mark_dedupes_same_persona_milestone(isolated_state):
    companion_state.mark_cleared("Yu-na", milestone="lover")
    companion_state.mark_cleared("Yu-na", milestone="lover")

    assert len(companion_state.load_cleared()) == 1


def test_mark_keeps_distinct_milestones(isolated_state):
    companion_state.mark_cleared("Yu-na", milestone="lover")
    companion_state.mark_cleared("Yu-na", milestone="married")

    assert len(companion_state.load_cleared()) == 2


def test_load_recovers_from_corrupt_file(isolated_state):
    isolated_state.parent.mkdir(parents=True, exist_ok=True)
    isolated_state.write_text("{not json", encoding="utf-8")

    assert companion_state.load_cleared() == []


def test_badge_caps_to_three_names(isolated_state):
    for name in ["A", "B", "C", "D", "E"]:
        companion_state.mark_cleared(name, milestone="lover")

    badge = companion_state.cleared_badge_text()

    assert badge.startswith("5 cleared · ")
    listed = badge.split("·", 1)[1]
    assert "A" in listed and "B" in listed and "C" in listed
    assert "D" not in listed
