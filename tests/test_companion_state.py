"""Tests for Random Chat companion-clear gating."""

from girlfriend_generator import companion_state


def test_load_returns_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GIRLFRIEND_IN_CLI_HOME", str(tmp_path))
    assert companion_state.load_cleared() == []
    assert companion_state.has_any_cleared() is False


def test_mark_persists_and_badge_summarizes(tmp_path, monkeypatch):
    monkeypatch.setenv("GIRLFRIEND_IN_CLI_HOME", str(tmp_path))
    companion_state.mark_cleared("Yu-na", milestone="lover")
    companion_state.mark_cleared("Mina", milestone="lover")

    assert companion_state.has_any_cleared() is True
    assert "2 cleared" in companion_state.cleared_badge_text()
    assert "Yu-na" in companion_state.cleared_badge_text()


def test_mark_dedupes_same_persona_milestone(tmp_path, monkeypatch):
    monkeypatch.setenv("GIRLFRIEND_IN_CLI_HOME", str(tmp_path))
    companion_state.mark_cleared("Yu-na", milestone="lover")
    companion_state.mark_cleared("Yu-na", milestone="lover")

    assert len(companion_state.load_cleared()) == 1
