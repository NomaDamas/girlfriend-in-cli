import types
from pathlib import Path

from girlfriend_generator.personas import load_persona
from girlfriend_generator.providers import AnthropicProvider, OpenAIProvider


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
