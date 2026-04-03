from __future__ import annotations

import os
import random
from dataclasses import dataclass

from .models import ChatMessage, Persona, ProviderReply


@dataclass(slots=True)
class ProviderConfig:
    name: str
    model: str | None = None
    performance_mode: str = "turbo"


class HeuristicProvider:
    def __init__(
        self,
        rng: random.Random | None = None,
        performance_mode: str = "turbo",
    ) -> None:
        self.rng = rng or random.Random()
        self.performance_mode = performance_mode

    def generate_reply(
        self,
        persona: Persona,
        history: list[ChatMessage],
        user_text: str,
        affection_score: int,
    ) -> ProviderReply:
        lower = user_text.lower()
        opener = self._pick_opener(persona.relationship_mode, lower)
        emotion = self._pick_emotion(lower)
        hook = self._pick_hook(persona, affection_score)
        question = self._pick_question(persona, lower)
        style = self._pick_style_hook(persona)
        text = f"{opener} {emotion} {hook} {style} {question}".strip()
        typing_seconds = self._typing_seconds(persona, text)
        return ProviderReply(
            text=text,
            typing_seconds=typing_seconds,
            trace_note=f"{self.performance_mode}-heuristic: zero-network local reply",
        )

    def generate_initiative(
        self,
        persona: Persona,
        history: list[ChatMessage],
        affection_score: int,
    ) -> str:
        opener = self.rng.choice(
            persona.initiative_profile.opener_templates or [persona.greeting]
        )
        follow_up = self.rng.choice(
            persona.initiative_profile.follow_up_templates or ["오늘 텐션 어떤지 궁금했어."]
        )
        context = ""
        if persona.context_summary:
            context = f" {persona.context_summary.split('.')[0]}."
        if affection_score >= 65:
            closer = " 지금은 내가 먼저 말 걸어도 되는 타이밍 같아서 왔어."
        else:
            closer = " 그냥 갑자기 네 톤이 떠올라서 먼저 와봤어."
        return f"{opener} {follow_up}{context}{closer}".strip()

    def _typing_seconds(self, persona: Persona, text: str) -> float:
        if self.performance_mode == "turbo":
            return min(1.05, max(0.18, len(text) / 42.0))
        if self.performance_mode == "balanced":
            return min(
                persona.typing.max_seconds,
                max(persona.typing.min_seconds * 0.75, len(text) / 24.0),
            )
        return min(
            persona.typing.max_seconds,
            max(persona.typing.min_seconds, len(text) / 18.0),
        )

    def _pick_opener(self, relationship_mode: str, user_text: str) -> str:
        if relationship_mode == "girlfriend":
            options = [
                "아 뭐야, 갑자기 그렇게 말하면 좀 귀엽잖아.",
                "음, 그 말투 오늘 좀 심쿵인데.",
                "너 지금 분위기 잘 타고 있네.",
            ]
        else:
            options = [
                "오, 그렇게 들어오면 나 좀 신경 쓰이는데.",
                "지금 톤 괜찮다. 센스 있는데?",
                "그 말은 꽤 좋다. 계속 해봐.",
            ]
        if "밥" in user_text or "먹" in user_text:
            return "밥 얘기 나오니까 갑자기 데이트 플랜 짜고 싶어지네."
        if "보고" in user_text:
            return "그 말 진짜 반칙이다."
        return self.rng.choice(options)

    def _pick_emotion(self, user_text: str) -> str:
        if "힘들" in user_text or "피곤" in user_text:
            return "오늘 힘들었으면 내가 잠깐 텐션 올려줄게."
        if "좋아" in user_text or "설레" in user_text:
            return "이렇게 직진으로 오면 나도 장난 못 치겠다."
        return self.rng.choice(
            [
                "리듬감 좋게 오니까 대화가 쫀쫀해진다.",
                "이런 식으로 톡하면 확실히 존재감이 생겨.",
                "짧게 던져도 결이 살아 있어서 계속 보게 돼.",
            ]
        )

    def _pick_hook(self, persona: Persona, affection_score: int) -> str:
        interest = self.rng.choice(persona.interests)
        soft_spot = self.rng.choice(persona.soft_spots)
        if affection_score >= 65:
            return f"특히 {soft_spot} 같은 포인트가 느껴져서 더 끌린다."
        return f"다음엔 {interest} 얘기도 같이 꺼내면 훨씬 분위기 잘 붙을 것 같아."

    def _pick_question(self, persona: Persona, user_text: str) -> str:
        if "뭐해" in user_text:
            return "근데 지금 네가 진짜 제일 말하고 싶은 건 뭐야?"
        if "주말" in user_text:
            return "주말엔 나를 어디로 데리고 가고 싶은데?"
        return self.rng.choice(
            [
                "지금 이 대화에서 한 단계 더 올리려면 너는 어떤 한마디를 던질 거야?",
                "그러면 내가 오늘 너한테 반응할 포인트를 하나만 더 줘봐.",
                "좋아, 그 흐름이면 다음 톡은 조금 더 대담하게 가도 되겠는데?",
            ]
        )

    def _pick_style_hook(self, persona: Persona) -> str:
        phrases = persona.style_profile.signature_phrases
        if not phrases:
            return ""
        chosen = self.rng.choice(phrases)
        if chosen in {"ㅋㅋ", "ㅎㅎ"}:
            return chosen
        return f"그리고 네가 {chosen} 같은 결로 말하면 persona 유지가 훨씬 잘 돼."


class OpenAIProvider:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or "gpt-4.1-mini"

    def generate_reply(
        self,
        persona: Persona,
        history: list[ChatMessage],
        user_text: str,
        affection_score: int,
    ) -> ProviderReply:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the openai package to use this provider.") from exc
        client = OpenAI()
        response = client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _build_system_prompt(persona, affection_score),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _build_user_prompt(history, user_text),
                        }
                    ],
                },
            ],
        )
        text = response.output_text.strip()
        return ProviderReply(
            text=text,
            typing_seconds=min(
                persona.typing.max_seconds,
                max(persona.typing.min_seconds, len(text) / 18.0),
            ),
            trace_note=f"openai:{self.model}",
        )

    def generate_initiative(
        self,
        persona: Persona,
        history: list[ChatMessage],
        affection_score: int,
    ) -> str:
        reply = self.generate_reply(
            persona=persona,
            history=history,
            user_text="Start a believable initiative message first, as if the persona texted unexpectedly.",
            affection_score=affection_score,
        )
        return reply.text


class AnthropicProvider:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or "claude-3-7-sonnet-latest"

    def generate_reply(
        self,
        persona: Persona,
        history: list[ChatMessage],
        user_text: str,
        affection_score: int,
    ) -> ProviderReply:
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                "Install the anthropic package to use this provider."
            ) from exc
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=self.model,
            max_tokens=220,
            system=_build_system_prompt(persona, affection_score),
            messages=[
                {
                    "role": "user",
                    "content": _build_user_prompt(history, user_text),
                }
            ],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        return ProviderReply(
            text=text,
            typing_seconds=min(
                persona.typing.max_seconds,
                max(persona.typing.min_seconds, len(text) / 18.0),
            ),
            trace_note=f"anthropic:{self.model}",
        )

    def generate_initiative(
        self,
        persona: Persona,
        history: list[ChatMessage],
        affection_score: int,
    ) -> str:
        reply = self.generate_reply(
            persona=persona,
            history=history,
            user_text="Start a believable initiative message first, as if the persona texted unexpectedly.",
            affection_score=affection_score,
        )
        return reply.text


def build_provider(config: ProviderConfig):
    if config.name == "heuristic":
        return HeuristicProvider(performance_mode=config.performance_mode)
    if config.name == "openai":
        return OpenAIProvider(config.model)
    if config.name == "anthropic":
        return AnthropicProvider(config.model)
    raise ValueError(f"Unknown provider: {config.name}")


def _build_system_prompt(persona: Persona, affection_score: int) -> str:
    return (
        "You are simulating a texting conversation in Korean inside a terminal-only chat UI. "
        "Stay warm, playful, and believable. Keep replies concise, emotionally legible, and "
        "rooted in the persona. Avoid explicit sexual content. "
        f"Persona: {persona.name}, age {persona.age}, relationship mode {persona.relationship_mode}. "
        f"Background: {persona.background}. Situation: {persona.situation}. "
        f"Texting style: {persona.texting_style}. Interests: {', '.join(persona.interests)}. "
        f"Soft spots: {', '.join(persona.soft_spots)}. Boundaries: {', '.join(persona.boundaries)}. "
        f"Context summary: {persona.context_summary or 'None'}. "
        f"Signature phrases: {', '.join(persona.style_profile.signature_phrases) or 'None'}. "
        f"Affection score: {affection_score}/100. "
        f"Additional hint: {persona.provider_system_hint or 'None'}"
    )


def _build_user_prompt(history: list[ChatMessage], user_text: str) -> str:
    transcript = "\n".join(f"{message.role}: {message.text}" for message in history[-8:])
    return f"Recent transcript:\n{transcript}\n\nLatest user text:\n{user_text}"
