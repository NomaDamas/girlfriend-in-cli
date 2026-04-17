import types
from pathlib import Path

from girlfriend_generator.personas import load_persona
from girlfriend_generator.providers import (
    AnthropicProvider,
    HeuristicProvider,
    OllamaProvider,
    OpenAIProvider,
)


def _load_test_persona():
    return load_persona(Path("personas/wonyoung-idol.json"))


def test_openai_provider_passes_language_related_kwargs_to_system_prompt(
    monkeypatch,
) -> None:
    persona = _load_test_persona()
    captured = {}

    class _FakeClient:
        def __init__(self):
            self.responses = self

        def create(self, **kwargs):
            captured["create_kwargs"] = kwargs
            return types.SimpleNamespace(output_text='{"reply":"hello"}')

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("girlfriend_generator.providers._build_system_prompt", lambda *args, **kwargs: captured.setdefault("prompt_kwargs", kwargs) or "SYSTEM")
    monkeypatch.setattr("girlfriend_generator.providers.parse_llm_json_response", lambda raw: {"reply": "hello"})
    monkeypatch.setattr("girlfriend_generator.providers._resolve_language", lambda language: language or "ko")
    monkeypatch.setattr("girlfriend_generator.providers.OpenAI", None, raising=False)
    monkeypatch.setitem(__import__("sys").modules, "openai", types.SimpleNamespace(OpenAI=lambda: _FakeClient()))

    provider = OpenAIProvider("gpt-test")
    reply = provider.generate_reply(
        persona=persona,
        history=[],
        user_text="hi",
        affection_score=55,
        difficulty="hard",
        language="en",
        special_mode="yandere",
    )

    assert reply.text == "hello"
    assert captured["prompt_kwargs"]["difficulty"] == "hard"
    assert captured["prompt_kwargs"]["language"] == "en"
    assert captured["prompt_kwargs"]["special_mode"] == "yandere"


def test_anthropic_provider_uses_saved_language_when_none_is_passed(
    monkeypatch,
) -> None:
    persona = _load_test_persona()
    captured = {}

    class _FakeClient:
        def __init__(self):
            self.messages = self

        def create(self, **kwargs):
            captured["create_kwargs"] = kwargs
            block = types.SimpleNamespace(type="text", text='{"reply":"やあ"}')
            return types.SimpleNamespace(content=[block])

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr("girlfriend_generator.providers._build_system_prompt", lambda *args, **kwargs: captured.setdefault("prompt_kwargs", kwargs) or "SYSTEM")
    monkeypatch.setattr("girlfriend_generator.providers.parse_llm_json_response", lambda raw: {"reply": "やあ"})
    monkeypatch.setattr("girlfriend_generator.providers._resolve_language", lambda language: language or "ja")
    monkeypatch.setitem(__import__("sys").modules, "anthropic", types.SimpleNamespace(Anthropic=lambda: _FakeClient()))

    provider = AnthropicProvider("claude-test")
    reply = provider.generate_reply(
        persona=persona,
        history=[],
        user_text="hi",
        affection_score=55,
    )

    assert reply.text == "やあ"
    assert captured["prompt_kwargs"]["language"] == "ja"


def test_ollama_provider_uses_openai_compatible_endpoint(monkeypatch) -> None:
    persona = _load_test_persona()
    captured = {}

    class _FakeClient:
        def __init__(self):
            self.responses = self

        def create(self, **kwargs):
            captured["create_kwargs"] = kwargs
            return types.SimpleNamespace(output_text='{"reply":"local hi"}')

    def _fake_openai(**kwargs):
        captured["client_kwargs"] = kwargs
        return _FakeClient()

    monkeypatch.setattr(
        "girlfriend_generator.providers._build_system_prompt",
        lambda *args, **kwargs: "SYSTEM",
    )
    monkeypatch.setattr(
        "girlfriend_generator.providers.parse_llm_json_response",
        lambda raw: {"reply": "local hi"},
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "openai",
        types.SimpleNamespace(OpenAI=_fake_openai),
    )

    provider = OllamaProvider("llama3.2", "127.0.0.1:11434")
    reply = provider.generate_reply(
        persona=persona,
        history=[],
        user_text="hi",
        affection_score=55,
        language="ko",
    )

    assert reply.text == "local hi"
    assert captured["client_kwargs"]["base_url"] == "http://127.0.0.1:11434/v1"
    assert captured["client_kwargs"]["api_key"] == "ollama"
    assert captured["create_kwargs"]["model"] == "llama3.2"


def test_heuristic_provider_respects_non_korean_language() -> None:
    persona = _load_test_persona()
    provider = HeuristicProvider()

    reply = provider.generate_reply(
        persona=persona,
        history=[],
        user_text="hi",
        affection_score=50,
        language="en",
    )

    assert any(token in reply.text.lower() for token in ["really", "cute", "listening", "attention"])
