import sys

from girlfriend_generator import cli


def test_main_builds_remote_config(monkeypatch) -> None:
    captured = {}

    class DummyPersona:
        pass

    def fake_fetch(base_url: str, persona_id: str):
        assert base_url == "http://127.0.0.1:8787"
        assert persona_id == "persona_123"
        return DummyPersona()

    def fake_run_chat_app(config):
        captured["config"] = config
        return 0

    monkeypatch.setattr(cli, "fetch_remote_persona", fake_fetch)
    monkeypatch.setattr(cli, "run_chat_app", fake_run_chat_app)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "girlfriend-generator",
            "--provider",
            "remote",
            "--server-base-url",
            "http://127.0.0.1:8787",
            "--persona-id",
            "persona_123",
        ],
    )

    exit_code = cli.main()

    assert exit_code == 0
    assert captured["config"].provider_name == "remote"
    assert captured["config"].server_base_url == "http://127.0.0.1:8787"
    assert captured["config"].persona_id == "persona_123"
    assert captured["config"].persona_override.__class__.__name__ == "DummyPersona"


def test_main_supports_remote_compile_flow(monkeypatch) -> None:
    captured = {}

    class DummyPersona:
        pass

    monkeypatch.setattr(
        cli,
        "compile_remote_persona",
        lambda **kwargs: {"persona_id": "persona_compiled", "persona_pack": {"slug": "유나"}},
    )
    monkeypatch.setattr(cli, "fetch_remote_persona", lambda base_url, persona_id: DummyPersona())

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
            "remote",
            "--server-base-url",
            "http://127.0.0.1:8787",
            "--compile-remote",
            "--display-name",
            "유나",
            "--relationship-mode",
            "girlfriend",
            "--context-notes",
            "성수에서 일하는 디자이너 느낌",
            "--context-link",
            "https://instagram.com/yuna.example",
            "--context-snippet",
            "자기야 뭐 해?",
        ],
    )

    exit_code = cli.main()

    assert exit_code == 0
    assert captured["config"].provider_name == "remote"
    assert captured["config"].persona_id == "persona_compiled"


def test_list_remote_personas_prints_listing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "list_remote_personas",
        lambda base_url: [{"slug": "유나", "persona_id": "persona_1", "display_name": "유나"}],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "girlfriend-generator",
            "--list-remote-personas",
            "--server-base-url",
            "http://127.0.0.1:8787",
        ],
    )

    exit_code = cli.main()

    assert exit_code == 0
    assert "persona_1" in capsys.readouterr().out
