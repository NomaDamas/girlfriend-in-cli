import os
import sys
from pathlib import Path

from girlfriend_generator import cli
from girlfriend_generator.paths import bundled_persona_dir, project_root


def test_main_passes_resolved_runtime_config_to_app(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured = {}

    def fake_run_chat_app(config):
        captured["config"] = config
        return 7

    monkeypatch.setattr(cli, "run_chat_app", fake_run_chat_app)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "girlfriend-generator",
            "--persona",
            "personas/wonyoung-idol.json",
            "--provider",
            "openai",
            "--performance",
            "balanced",
            "--voice-output",
            "--voice-input-command",
            "printf hello",
            "--session-dir",
            "sessions/manual-check",
            "--no-export-on-exit",
            "--no-trace",
        ],
    )
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main()

    root = project_root()
    assert exit_code == 7
    assert captured["config"].persona_path == root / "personas" / "wonyoung-idol.json"
    assert captured["config"].provider_name == "openai"
    assert captured["config"].performance_mode == "balanced"
    assert captured["config"].voice_output is True
    assert captured["config"].voice_input_command == "printf hello"
    assert captured["config"].session_dir == root / "sessions" / "manual-check"
    assert captured["config"].export_on_exit is False
    assert captured["config"].show_trace is False


def test_main_defaults_to_bundled_persona_outside_repository(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured = {}

    def fake_run_chat_app(config):
        captured["config"] = config
        return 0

    monkeypatch.setattr(cli, "run_chat_app", fake_run_chat_app)
    monkeypatch.setattr(sys, "argv", ["girlfriend-generator"])
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main()

    assert exit_code == 0
    assert captured["config"].persona_path.parent == bundled_persona_dir()
    assert captured["config"].session_dir == project_root() / "sessions"
    assert captured["config"].provider_name == "openai"
    assert captured["config"].performance_mode == "turbo"
    assert captured["config"].show_trace is True
    assert captured["config"].export_on_exit is True


def test_list_personas_prints_bundled_personas_without_launching_app(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    def fake_run_chat_app(_config):
        raise AssertionError("run_chat_app should not be called for --list-personas")

    monkeypatch.setattr(cli, "run_chat_app", fake_run_chat_app)
    monkeypatch.setattr(sys, "argv", ["girlfriend-generator", "--list-personas"])
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "wonyoung-idol.json" in output
    assert "dua-international.json" in output
