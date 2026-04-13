import os
import sys
from pathlib import Path

from girlfriend_generator import cli
from girlfriend_generator.paths import bundled_persona_dir, project_root, resolve_persona_path


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


def test_show_main_menu_returns_selected_persona_for_new_chat(monkeypatch) -> None:
    args = cli.build_parser().parse_args([])
    persona_path = bundled_persona_dir() / "wonyoung-idol.json"

    monkeypatch.setattr(cli, "_show_star_popup", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("girlfriend_generator.selector.arrow_select", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(cli, "_pick_persona_interactive", lambda *_args, **_kwargs: persona_path)
    monkeypatch.setattr(
        cli,
        "discover_personas",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("discover_personas should not run when a persona is selected")
        ),
    )

    result = cli._show_main_menu([persona_path], args, skip_intro=True)

    assert result == (args, resolve_persona_path(persona_path), None)


def test_show_main_menu_returns_selected_chat_room(monkeypatch, tmp_path: Path) -> None:
    args = cli.build_parser().parse_args([])
    persona_path = bundled_persona_dir() / "wonyoung-idol.json"
    resume_path = tmp_path / "resume-session.json"
    resume_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(cli, "_show_star_popup", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("girlfriend_generator.selector.arrow_select", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(cli, "_show_chat_rooms", lambda *_args, **_kwargs: (persona_path, resume_path))
    monkeypatch.setattr(
        cli,
        "discover_personas",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("discover_personas should not run when a chat room is selected")
        ),
    )

    result = cli._show_main_menu([persona_path], args, skip_intro=True)

    assert result == (args, resolve_persona_path(persona_path), resume_path)


def test_show_main_menu_does_not_show_star_popup_on_skip_intro(monkeypatch) -> None:
    args = cli.build_parser().parse_args([])
    persona_path = bundled_persona_dir() / "wonyoung-idol.json"
    calls = {"star": 0}

    monkeypatch.setattr(cli, "_show_star_popup", lambda *_args, **_kwargs: calls.__setitem__("star", calls["star"] + 1))
    monkeypatch.setattr("girlfriend_generator.selector.arrow_select", lambda *_args, **_kwargs: None)

    cli._show_main_menu([persona_path], args, skip_intro=True)

    assert calls["star"] == 0


def test_show_main_menu_shows_star_popup_on_first_entry(monkeypatch) -> None:
    args = cli.build_parser().parse_args([])
    persona_path = bundled_persona_dir() / "wonyoung-idol.json"
    calls = {"star": 0, "intro": 0, "onboarding": 0}

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(cli, "_show_star_popup", lambda *_args, **_kwargs: calls.__setitem__("star", calls["star"] + 1))
    monkeypatch.setattr(cli, "_play_intro", lambda *_args, **_kwargs: calls.__setitem__("intro", calls["intro"] + 1))
    monkeypatch.setattr(cli, "_show_first_run_onboarding", lambda *_args, **_kwargs: calls.__setitem__("onboarding", calls["onboarding"] + 1))
    monkeypatch.setattr("girlfriend_generator.selector.arrow_select", lambda *_args, **_kwargs: None)

    cli._show_main_menu([persona_path], args, skip_intro=False)

    assert calls == {"star": 1, "intro": 1, "onboarding": 1}


def test_build_filled_title_rows_uses_solid_blocks() -> None:
    rows = cli._build_filled_title_rows("girlfriend in cli", style_variant="solid")

    assert rows
    assert any("█" in row.plain for row in rows)
    assert any(row.plain.strip() == "" for row in rows)
    title_rows = [row.plain for row in rows if row.plain.strip()]
    assert not any("/" in row or "\\" in row or "_" in row for row in title_rows)


def test_build_filled_title_rows_supports_gradient_variant() -> None:
    rows = cli._build_filled_title_rows("girlfriend in cli", style_variant="gradient")

    colored_spans = {
        str(span.style)
        for row in rows
        for span in row.spans
        if span.style and "#" in str(span.style)
    }

    assert len(colored_spans) >= 2


def test_build_logo_rows_keeps_title_swappable() -> None:
    rows = cli._build_logo_rows(title_text="test title", style_variant="solid")

    plain_rows = [row.plain for row in rows]

    assert any("♡ terminal romance simulator ♡" in row for row in plain_rows)
    assert any("v0.1.3.2" in row for row in plain_rows)


def test_build_main_menu_actions_shows_setup_guide_when_provider_needs_setup(monkeypatch) -> None:
    args = cli.build_parser().parse_args([])
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    actions = cli._build_main_menu_actions(0, args, "en")

    assert any(action == "setup_guide" for action, _item in actions)
    assert any(action == "usage_guide" for action, _item in actions)


def test_build_main_menu_actions_hides_setup_guide_when_provider_is_configured(monkeypatch) -> None:
    args = cli.build_parser().parse_args([])
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    actions = cli._build_main_menu_actions(0, args, "en")

    assert all(action != "setup_guide" for action, _item in actions)
    assert any(action == "usage_guide" for action, _item in actions)


def test_show_star_popup_treats_enter_as_yes(monkeypatch, tmp_path: Path) -> None:
    flag_path = tmp_path / "star_shown"
    opened = {}

    monkeypatch.setattr(cli, "_STAR_FLAG_PATH", flag_path)
    monkeypatch.setattr("girlfriend_generator.wide_input.wide_input", lambda _prompt="": "")
    monkeypatch.setattr(cli, "_star_repo_with_gh", lambda: False)
    monkeypatch.setattr("webbrowser.open", lambda url: opened.setdefault("url", url))

    from rich.console import Console
    cli._show_star_popup(Console(record=True, width=120))

    assert opened["url"].endswith("NomaDamas/girlfriend-in-cli")
    assert flag_path.exists()


def test_show_star_popup_uses_github_cli_when_available(monkeypatch, tmp_path: Path) -> None:
    flag_path = tmp_path / "star_shown"
    opened = {}

    monkeypatch.setattr(cli, "_STAR_FLAG_PATH", flag_path)
    monkeypatch.setattr("girlfriend_generator.wide_input.wide_input", lambda _prompt="": "")
    monkeypatch.setattr(cli, "_star_repo_with_gh", lambda: True)
    monkeypatch.setattr("webbrowser.open", lambda url: opened.setdefault("url", url))

    from rich.console import Console
    cli._show_star_popup(Console(record=True, width=120))

    assert opened == {}
    assert flag_path.exists()
