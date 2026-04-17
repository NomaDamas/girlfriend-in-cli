import os
import sys
from pathlib import Path

from girlfriend_generator import cli
from girlfriend_generator import i18n
from girlfriend_generator.i18n import get_language
from girlfriend_generator.paths import bundled_persona_dir, project_root, resolve_persona_path


def test_main_passes_resolved_runtime_config_to_app(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured = {}
    monkeypatch.setattr(i18n, "_PREFS_PATH", tmp_path / "prefs.json")

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
    monkeypatch.setattr(i18n, "_PREFS_PATH", tmp_path / "prefs.json")

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


def test_main_passes_ollama_runtime_config_to_app(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_run_chat_app(config):
        captured["config"] = config
        return 0

    monkeypatch.setattr(cli, "run_chat_app", fake_run_chat_app)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "girlfriend-generator",
            "--provider",
            "ollama",
            "--model",
            "llama3.2",
            "--ollama-base-url",
            "http://127.0.0.1:11434/v1",
        ],
    )
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main()

    assert exit_code == 0
    assert captured["config"].provider_name == "ollama"
    assert captured["config"].provider_model == "llama3.2"
    assert captured["config"].ollama_base_url == "http://127.0.0.1:11434/v1"


def test_main_uses_saved_provider_preferences(monkeypatch, tmp_path: Path) -> None:
    captured = {}
    prefs_path = tmp_path / "prefs.json"
    prefs_path.write_text(
        '{"provider":"ollama","provider_model":"gemma4:26b","ollama_base_url":"http://127.0.0.1:11434/v1","performance":"balanced","no_trace":true}',
        encoding="utf-8",
    )

    def fake_run_chat_app(config):
        captured["config"] = config
        return 0

    monkeypatch.setattr(i18n, "_PREFS_PATH", prefs_path)
    monkeypatch.setattr(cli, "run_chat_app", fake_run_chat_app)
    monkeypatch.setattr(sys, "argv", ["girlfriend-generator"])
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main()

    assert exit_code == 0
    assert captured["config"].provider_name == "ollama"
    assert captured["config"].provider_model == "gemma4:26b"
    assert captured["config"].ollama_base_url == "http://127.0.0.1:11434/v1"
    assert captured["config"].performance_mode == "balanced"
    assert captured["config"].show_trace is False


def test_main_restores_saved_runtime_settings_after_back_to_menu(
    monkeypatch,
    tmp_path: Path,
) -> None:
    prefs_path = tmp_path / "prefs.json"
    prefs_path.write_text(
        (
            '{"provider":"ollama","provider_models":{"ollama":"gemma4:26b"},'
            '"ollama_base_url":"http://127.0.0.1:11434/v1","performance":"balanced"}'
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(i18n, "_PREFS_PATH", prefs_path)
    monkeypatch.setattr(sys, "argv", ["girlfriend-generator"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli, "maybe_prompt_for_update", lambda _console: False)

    persona_path = bundled_persona_dir() / "wonyoung-idol.json"
    menu_calls = {"count": 0}
    captured = {}

    def fake_show_main_menu(_bundled_personas, args):
        menu_calls["count"] += 1
        if menu_calls["count"] == 1:
            return args, persona_path, None
        captured["provider"] = args.provider
        captured["model"] = args.model
        captured["ollama_base_url"] = args.ollama_base_url
        captured["performance"] = args.performance
        return None

    def fake_run_chat_app(_config):
        return 2

    monkeypatch.setattr(cli, "_show_main_menu", fake_show_main_menu)
    monkeypatch.setattr(cli, "run_chat_app", fake_run_chat_app)
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main()

    assert exit_code == 0
    assert captured == {
        "provider": "ollama",
        "model": "gemma4:26b",
        "ollama_base_url": "http://127.0.0.1:11434/v1",
        "performance": "balanced",
    }


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
    assert any("v0.1.3.5" in row for row in plain_rows)


def test_build_main_menu_actions_includes_guide_entry(monkeypatch) -> None:
    args = cli.build_parser().parse_args([])
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    actions = cli._build_main_menu_actions(0, args, "en")

    assert any(action == "guide" for action, _item in actions)
    assert all(action != "setup_guide" for action, _item in actions)
    assert all(action != "usage_guide" for action, _item in actions)


def test_build_main_menu_actions_keeps_guide_when_provider_is_configured(monkeypatch) -> None:
    args = cli.build_parser().parse_args([])
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    actions = cli._build_main_menu_actions(0, args, "en")

    assert any(action == "guide" for action, _item in actions)


def test_show_guides_menu_routes_to_usage_guide(monkeypatch) -> None:
    args = cli.build_parser().parse_args([])
    calls = {"usage": 0, "setup": 0}

    monkeypatch.setattr(
        "girlfriend_generator.selector.arrow_select",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(cli, "_show_usage_guide", lambda *_args, **_kwargs: calls.__setitem__("usage", calls["usage"] + 1))
    monkeypatch.setattr(cli, "_provider_setup_guide", lambda *_args, **_kwargs: calls.__setitem__("setup", calls["setup"] + 1))

    from rich.console import Console
    cli._show_guides_menu(Console(record=True, width=120), args)

    assert calls == {"usage": 1, "setup": 0}


def test_show_guides_menu_routes_to_setup_guide(monkeypatch) -> None:
    args = cli.build_parser().parse_args([])
    calls = {"usage": 0, "setup": 0}

    monkeypatch.setattr(
        "girlfriend_generator.selector.arrow_select",
        lambda *_args, **_kwargs: 1,
    )
    monkeypatch.setattr(cli, "_show_usage_guide", lambda *_args, **_kwargs: calls.__setitem__("usage", calls["usage"] + 1))
    monkeypatch.setattr(cli, "_provider_setup_guide", lambda *_args, **_kwargs: calls.__setitem__("setup", calls["setup"] + 1))

    from rich.console import Console
    cli._show_guides_menu(Console(record=True, width=120), args)

    assert calls == {"usage": 0, "setup": 1}


def test_provider_needs_setup_is_false_for_ollama(monkeypatch) -> None:
    args = cli.build_parser().parse_args(["--provider", "ollama"])
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert cli._provider_needs_setup(args) is False


def test_has_any_flags_ignores_provider_settings() -> None:
    args = cli.build_parser().parse_args(["--provider", "ollama", "--model", "gemma4:26b"])

    assert cli._has_any_flags(args) is False


def test_apply_provider_defaults_uses_saved_ollama_settings(monkeypatch) -> None:
    args = cli.build_parser().parse_args(["--provider", "ollama"])
    monkeypatch.setenv(cli.OLLAMA_BASE_URL_ENV, "http://127.0.0.1:22434/v1")
    monkeypatch.setenv(cli.OLLAMA_MODEL_ENV, "qwen2.5:7b")

    cli._apply_provider_defaults(args)

    assert args.ollama_base_url == "http://127.0.0.1:22434/v1"
    assert args.model == "qwen2.5:7b"


def test_persist_runtime_settings_writes_provider_preferences(monkeypatch, tmp_path: Path) -> None:
    prefs_path = tmp_path / "prefs.json"
    monkeypatch.setattr(i18n, "_PREFS_PATH", prefs_path)
    args = cli.build_parser().parse_args([])
    args.provider = "ollama"
    args.model = "gemma4:26b"
    args.ollama_base_url = "http://127.0.0.1:11434/v1"
    args.performance = "balanced"
    args.voice_output = True
    args.no_trace = True

    cli._persist_runtime_settings(args)

    data = prefs_path.read_text(encoding="utf-8")
    assert '"provider": "ollama"' in data
    assert '"provider_model": "gemma4:26b"' in data
    assert '"ollama_base_url": "http://127.0.0.1:11434/v1"' in data


def test_apply_saved_runtime_settings_restores_provider_preferences(monkeypatch, tmp_path: Path) -> None:
    prefs_path = tmp_path / "prefs.json"
    prefs_path.write_text(
        '{"provider":"ollama","provider_model":"gemma4:26b","ollama_base_url":"http://127.0.0.1:11434/v1","performance":"balanced","voice_output":true,"no_trace":true}',
        encoding="utf-8",
    )
    monkeypatch.setattr(i18n, "_PREFS_PATH", prefs_path)
    parser = cli.build_parser()
    args = parser.parse_args([])

    cli._apply_saved_runtime_settings(args, parser, [])

    assert args.provider == "ollama"
    assert args.model == "gemma4:26b"
    assert args.ollama_base_url == "http://127.0.0.1:11434/v1"
    assert args.performance == "balanced"
    assert args.voice_output is True
    assert args.no_trace is True


def test_apply_saved_runtime_settings_does_not_override_explicit_provider(monkeypatch, tmp_path: Path) -> None:
    prefs_path = tmp_path / "prefs.json"
    prefs_path.write_text('{"provider":"ollama"}', encoding="utf-8")
    monkeypatch.setattr(i18n, "_PREFS_PATH", prefs_path)
    parser = cli.build_parser()
    args = parser.parse_args(["--provider", "openai"])

    cli._apply_saved_runtime_settings(args, parser, ["--provider", "openai"])

    assert args.provider == "openai"


def test_apply_saved_runtime_settings_does_not_override_equals_style_provider_flag(
    monkeypatch,
    tmp_path: Path,
) -> None:
    prefs_path = tmp_path / "prefs.json"
    prefs_path.write_text(
        '{"provider":"ollama","provider_models":{"ollama":"gemma4:26b"},"performance":"balanced"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(i18n, "_PREFS_PATH", prefs_path)
    parser = cli.build_parser()
    raw_args = ["--provider=openai", "--performance=cinematic"]
    args = parser.parse_args(raw_args)

    cli._apply_saved_runtime_settings(args, parser, raw_args)

    assert args.provider == "openai"
    assert args.performance == "cinematic"
    assert args.model is None


def test_apply_saved_runtime_settings_restores_model_for_active_provider_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    prefs_path = tmp_path / "prefs.json"
    prefs_path.write_text(
        (
            '{"provider":"ollama","provider_model":"legacy-ollama",'
            '"provider_models":{"ollama":"gemma4:26b","openai":"gpt-4.1-mini"}}'
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(i18n, "_PREFS_PATH", prefs_path)
    parser = cli.build_parser()
    args = parser.parse_args(["--provider", "anthropic"])

    cli._apply_saved_runtime_settings(args, parser, ["--provider", "anthropic"])

    assert args.provider == "anthropic"
    assert args.model is None


def test_apply_saved_runtime_settings_uses_provider_specific_model_for_saved_provider(
    monkeypatch,
    tmp_path: Path,
) -> None:
    prefs_path = tmp_path / "prefs.json"
    prefs_path.write_text(
        '{"provider":"ollama","provider_models":{"ollama":"gemma4:26b","openai":"gpt-4.1-mini"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(i18n, "_PREFS_PATH", prefs_path)
    parser = cli.build_parser()
    args = parser.parse_args([])

    cli._apply_saved_runtime_settings(args, parser, [])

    assert args.provider == "ollama"
    assert args.model == "gemma4:26b"


def test_build_persona_generator_config_falls_back_to_openai_for_ollama(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(i18n, "_PREFS_PATH", tmp_path / "prefs.json")
    args = cli.build_parser().parse_args(["--provider", "ollama"])
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    config = cli._build_persona_generator_config(args)

    assert config.provider == "openai"
    assert config.model is None
    assert config.ollama_base_url is None


def test_provider_model_choices_include_latest_official_entries() -> None:
    assert "gpt-5.2" in cli._provider_model_choices("openai")
    assert "gpt-5.2-pro" in cli._provider_model_choices("openai")
    assert "claude-opus-4-1-20250805" in cli._provider_model_choices("anthropic")
    assert "claude-3-5-haiku-latest" in cli._provider_model_choices("anthropic")
    assert "llama4" in cli._provider_model_choices("ollama")
    assert "qwen3" in cli._provider_model_choices("ollama")


def test_set_model_override_uses_menu_selection(monkeypatch, tmp_path: Path) -> None:
    prefs_path = tmp_path / "prefs.json"
    monkeypatch.setattr(i18n, "_PREFS_PATH", prefs_path)
    args = cli.build_parser().parse_args(["--provider", "openai"])

    monkeypatch.setattr(
        "girlfriend_generator.selector.arrow_select",
        lambda *_args, **_kwargs: 1,
    )

    from rich.console import Console
    cli._set_model_override(Console(record=True, width=120), args)

    assert args.model == "gpt-5.2"


def test_set_ollama_model_uses_curated_choices(monkeypatch, tmp_path: Path) -> None:
    prefs_path = tmp_path / "prefs.json"
    monkeypatch.setattr(i18n, "_PREFS_PATH", prefs_path)
    args = cli.build_parser().parse_args(["--provider", "openai"])

    monkeypatch.setattr(
        "girlfriend_generator.selector.arrow_select",
        lambda *_args, **_kwargs: 2,
    )
    monkeypatch.setattr(cli, "_save_key_to_shell_profile", lambda *_args, **_kwargs: False)

    from rich.console import Console
    cli._set_ollama_model(Console(record=True, width=120), args)

    assert args.model is None
    data = prefs_path.read_text(encoding="utf-8")
    assert '"provider_models": {"ollama": "llama3.2"}' in data


def test_build_persona_generator_config_keeps_anthropic_when_selected() -> None:
    args = cli.build_parser().parse_args(["--provider", "anthropic", "--model", "claude-test"])

    config = cli._build_persona_generator_config(args)

    assert config.provider == "anthropic"
    assert config.model == "claude-test"


def test_build_persona_generator_config_falls_back_to_anthropic_when_openai_is_unavailable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    prefs_path = tmp_path / "prefs.json"
    prefs_path.write_text(
        '{"provider_models":{"anthropic":"claude-3-7-sonnet-latest"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(i18n, "_PREFS_PATH", prefs_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    args = cli.build_parser().parse_args(["--provider", "ollama"])

    config = cli._build_persona_generator_config(args)

    assert config.provider == "anthropic"
    assert config.model == "claude-3-7-sonnet-latest"


def test_persist_runtime_settings_keeps_models_scoped_per_provider(
    monkeypatch,
    tmp_path: Path,
) -> None:
    prefs_path = tmp_path / "prefs.json"
    monkeypatch.setattr(i18n, "_PREFS_PATH", prefs_path)

    openai_args = cli.build_parser().parse_args([])
    openai_args.provider = "openai"
    openai_args.model = "gpt-4.1-mini"
    cli._persist_runtime_settings(openai_args)

    ollama_args = cli.build_parser().parse_args(["--provider", "ollama"])
    ollama_args.provider = "ollama"
    ollama_args.model = "gemma4:26b"
    ollama_args.ollama_base_url = "http://127.0.0.1:11434/v1"
    cli._persist_runtime_settings(ollama_args)

    data = prefs_path.read_text(encoding="utf-8")
    assert '"provider_models": {"openai": "gpt-4.1-mini", "ollama": "gemma4:26b"}' in data


def test_default_language_is_english(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("girlfriend_generator.i18n._PREFS_PATH", tmp_path / "prefs.json")

    assert get_language() == "en"


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
