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
