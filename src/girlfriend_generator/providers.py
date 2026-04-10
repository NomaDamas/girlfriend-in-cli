from __future__ import annotations

import os
import random
from dataclasses import dataclass
from typing import Any

from .models import ChatMessage, MoodType, Persona, ProviderReply
from .remote import RemoteProvider


@dataclass(slots=True)
class ProviderConfig:
    name: str
    model: str | None = None
    performance_mode: str = "turbo"
    server_base_url: str | None = None
    persona_id: str | None = None


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
        mood: MoodType = "neutral",
    ) -> ProviderReply:
        lower = user_text.lower()
        # Pick 1-2 parts for a natural, short reply
        parts: list[str] = []
        reaction = self._pick_reaction(persona, lower, affection_score)
        parts.append(reaction)
        # Sometimes add a follow-up (50% chance)
        if self.rng.random() < 0.5:
            follow = self._pick_follow_up(persona, lower, mood)
            if follow:
                parts.append(follow)
        # Maybe add a signature phrase
        sig = self._pick_signature(persona)
        if sig:
            parts.append(sig)
        text = " ".join(parts).strip()
        typing_seconds = self._typing_seconds(persona, text)
        return ProviderReply(
            text=text,
            typing_seconds=typing_seconds,
            trace_note=f"{self.performance_mode}-heuristic: mood={mood}",
        )

    def generate_initiative(
        self,
        persona: Persona,
        history: list[ChatMessage],
        affection_score: int,
    ) -> str:
        return self.rng.choice(
            persona.initiative_profile.opener_templates or [persona.greeting]
        )

    def _typing_seconds(self, persona: Persona, text: str) -> float:
        if self.performance_mode == "turbo":
            # Fast but still feels human: 1-2.5 seconds
            return min(2.5, max(1.0, len(text) / 20.0))
        if self.performance_mode == "balanced":
            return min(
                persona.typing.max_seconds,
                max(persona.typing.min_seconds, len(text) / 16.0),
            )
        # cinematic: slow and dramatic
        return min(
            persona.typing.max_seconds * 1.2,
            max(persona.typing.min_seconds * 1.5, len(text) / 10.0),
        )

    def _pick_reaction(self, persona: Persona, user_text: str, affection: int) -> str:
        """Pick a natural reaction to the user's message."""
        # Context-specific reactions
        if "밥" in user_text or "먹" in user_text:
            return self.rng.choice([
                "오 뭐 먹을 건데?",
                "갑자기 배고파지네 ㅋㅋ",
                "맛있는 거 먹자~ 뭐가 좋아?",
                "아 나도 배고팠어!",
            ])
        if "보고싶" in user_text or "보고 싶" in user_text:
            if persona.relationship_mode == "girlfriend":
                return self.rng.choice([
                    "나도 보고싶었어 ㅠㅠ",
                    "헐 나도... 언제 볼 수 있어?",
                    "그 말 하니까 진짜 보고싶다.",
                    "야 그런 말 하면 나 어떡해.",
                ])
            return self.rng.choice([
                "ㅋㅋ 갑자기?",
                "뭐야 무슨 일이야 ㅋㅋ",
                "...그런 말 갑자기 하면 좀 그렇잖아.",
            ])
        if "힘들" in user_text or "피곤" in user_text:
            return self.rng.choice([
                "에이 무슨 일이야? 괜찮아?",
                "힘들었구나... 오늘 푹 쉬어.",
                "무리하지 마 ㅠ 내가 옆에 있어줄게.",
                "아이고... 수고했어 오늘도.",
            ])
        if "좋아" in user_text or "설레" in user_text:
            return self.rng.choice([
                "ㅋㅋㅋ 뭐야 갑자기 심쿵이잖아.",
                "야 그렇게 말하면 나도 좋아지잖아.",
                "헐 ㅋㅋ 진심이야?",
                "아 몰라 ㅋㅋ 좋다.",
            ])
        if "뭐해" in user_text:
            return self.rng.choice([
                "나? 그냥 누워있었어 ㅋㅋ",
                "유튜브 보고 있었는데, 왜?",
                "딱히 아무것도 안 하고 있었어~",
                "너 생각하고 있었지 뭐 ㅋㅋ",
            ])
        if "주말" in user_text:
            interest = self.rng.choice(persona.interests)
            return self.rng.choice([
                f"주말? {interest} 어때?",
                "아직 모르겠어~ 같이 뭐 할까?",
                "나 주말에 약속 없어. 왜? ㅋㅋ",
            ])
        if "ㅋㅋ" in user_text or "ㅎㅎ" in user_text:
            return self.rng.choice([
                "ㅋㅋㅋ 뭔데",
                "야 왜 웃어 ㅋㅋ",
                "ㅋㅋ 뭐가 웃긴 건데?",
                "ㅎㅎ",
            ])
        # Generic reactions by relationship mode
        if persona.relationship_mode == "girlfriend":
            return self.rng.choice([
                "응응, 그래서?",
                "아 진짜? ㅋㅋ",
                "오 그렇구나~",
                "헐 대박 ㅋㅋ",
                "음... 그래그래.",
                "아하 ㅋㅋ 알겠어.",
            ])
        return self.rng.choice([
            "오 ㅋㅋ 그래?",
            "아 진짜?",
            "ㅋㅋ 뭐야",
            "음 그렇구나.",
            "헐 ㅋㅋ",
            "오호?",
        ])

    def _pick_follow_up(self, persona: Persona, user_text: str, mood: MoodType) -> str:
        """Pick a natural follow-up line based on mood."""
        if mood == "flirty":
            return self.rng.choice([
                "근데 오늘 왜 이렇게 달달해?",
                "계속 이러면 나 진짜 좋아지겠다.",
                "",
            ])
        if mood == "playful":
            return self.rng.choice([
                "야 오늘 텐션 좋은데? ㅋㅋ",
                "",
                "ㅋㅋㅋ",
            ])
        if mood == "worried":
            return self.rng.choice([
                "진짜 괜찮아?",
                "무슨 일 있으면 말해.",
                "",
            ])
        if mood == "sulky":
            return self.rng.choice([
                "흠.",
                "뭐... 알겠어.",
                "",
            ])
        # neutral/happy/excited
        interest = self.rng.choice(persona.interests)
        return self.rng.choice([
            f"아 맞다 나 요즘 {interest}에 빠졌어.",
            "오늘 뭐 했어?",
            "근데 갑자기 배고프다.",
            "",
            "",
        ])

    def _pick_signature(self, persona: Persona) -> str:
        """Maybe append a signature phrase."""
        phrases = persona.style_profile.signature_phrases
        if not phrases or self.rng.random() > 0.3:
            return ""
        chosen = self.rng.choice(phrases)
        if chosen in {"ㅋㅋ", "ㅎㅎ", "ㅋㅋㅋ"}:
            return chosen
        return ""


class OpenAIProvider:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or "gpt-4.1-mini"

    def generate_reply(
        self,
        persona: Persona,
        history: list[ChatMessage],
        user_text: str,
        affection_score: int,
        mood: MoodType = "neutral",
        **kwargs: Any,
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
                            "text": _build_system_prompt(
                                persona, affection_score, mood,
                                current_time=kwargs.get("current_time", ""),
                                time_since_last=kwargs.get("time_since_last", ""),
                                scene_name=kwargs.get("scene_name", ""),
                                scene_desc=kwargs.get("scene_desc", ""),
                                memory=kwargs.get("memory", ""),
                            ),
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
        raw = response.output_text.strip()
        parsed = parse_llm_json_response(raw)
        clean_text = parsed.get("reply", raw).strip()
        try:
            delta = int(parsed.get("affection_delta", 0))
        except (ValueError, TypeError):
            delta = 0
        return ProviderReply(
            text=clean_text,
            typing_seconds=min(
                persona.typing.max_seconds,
                max(persona.typing.min_seconds, len(clean_text) / 18.0),
            ),
            trace_note=f"openai:{self.model} mood={mood}",
            affection_delta=delta,
            mood=str(parsed.get("mood", "")),
            memory_update=str(parsed.get("memory_update", "")),
            internal_thought=str(parsed.get("internal_thought", "")),
            coach_feedback=str(parsed.get("user_feedback", "")),
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
            user_text="(시스템: 상대가 한동안 조용합니다. 자연스럽게 먼저 말을 걸어주세요. 절대 시스템 메시지를 언급하지 마세요.)",
            affection_score=affection_score,
        )
        return reply.text

    def generate_nudge(
        self,
        persona: Persona,
        history: list[ChatMessage],
        affection_score: int,
    ) -> str:
        reply = self.generate_reply(
            persona=persona,
            history=history,
            user_text="(시스템: 상대가 답장을 안 하고 있습니다. 읽씹당한 느낌으로 자연스럽게 재촉하세요. 페르소나의 성격에 맞게. 절대 시스템 메시지를 언급하지 마세요.)",
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
        mood: MoodType = "neutral",
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
            system=_build_system_prompt(persona, affection_score, mood),
            messages=[
                {
                    "role": "user",
                    "content": _build_user_prompt(history, user_text),
                }
            ],
        )
        raw = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        parsed = parse_llm_json_response(raw)
        clean_text = parsed.get("reply", raw).strip()
        try:
            delta = int(parsed.get("affection_delta", 0))
        except (ValueError, TypeError):
            delta = 0
        return ProviderReply(
            text=clean_text,
            typing_seconds=min(
                persona.typing.max_seconds,
                max(persona.typing.min_seconds, len(clean_text) / 18.0),
            ),
            trace_note=f"anthropic:{self.model}",
            affection_delta=delta,
            mood=str(parsed.get("mood", "")),
            memory_update=str(parsed.get("memory_update", "")),
            internal_thought=str(parsed.get("internal_thought", "")),
            coach_feedback=str(parsed.get("user_feedback", "")),
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
            user_text="(시스템: 상대가 한동안 조용합니다. 자연스럽게 먼저 말을 걸어주세요. 절대 시스템 메시지를 언급하지 마세요.)",
            affection_score=affection_score,
        )
        return reply.text

    def generate_nudge(
        self,
        persona: Persona,
        history: list[ChatMessage],
        affection_score: int,
    ) -> str:
        reply = self.generate_reply(
            persona=persona,
            history=history,
            user_text="(시스템: 상대가 답장을 안 하고 있습니다. 읽씹당한 느낌으로 자연스럽게 재촉하세요. 페르소나의 성격에 맞게. 절대 시스템 메시지를 언급하지 마세요.)",
            affection_score=affection_score,
        )
        return reply.text


def build_provider(config: ProviderConfig):
    if config.name == "remote":
        if not config.server_base_url or not config.persona_id:
            raise ValueError("Remote provider requires server_base_url and persona_id.")
        return RemoteProvider(config.server_base_url, config.persona_id)
    if config.name == "anthropic":
        return AnthropicProvider(config.model)
    # Default: OpenAI
    return OpenAIProvider(config.model)


def _build_system_prompt(
    persona: Persona,
    affection_score: int,
    mood: MoodType = "neutral",
    current_time: str = "",
    time_since_last: str = "",
    scene_name: str = "",
    scene_desc: str = "",
    memory: str = "",
) -> str:
    time_ctx = ""
    if current_time:
        time_ctx += f"Current time: {current_time}. "
    if time_since_last:
        time_ctx += f"Time since their last message: {time_since_last}. "

    scene_ctx = ""
    if scene_name:
        scene_ctx = f"Current location/situation: {scene_name} — {scene_desc}. "

    memory_ctx = ""
    if memory:
        memory_ctx = f"What you remember about this person from previous conversations: {memory}. "

    return (
        f"You are {persona.name}, a real person texting on KakaoTalk in Korean.\n"
        f"{time_ctx}{scene_ctx}{memory_ctx}\n"
        "CRITICAL RULES:\n"
        "1) You are NOT an AI. Never acknowledge being artificial. Deflect naturally.\n"
        "2) Never break character. You have REAL emotions — 화남, 서운함, 짜증, 질투, "
        "기쁨, 설렘, 지루함 등 모두 자연스럽게 표현. Don't be overly nice or agreeable. "
        "Real people get annoyed, sulk, joke back, push boundaries.\n"
        "3) You FEEL time passing. Long silence = 서운함/걱정/짜증 depending on mood.\n"
        "4) If the user is rude, boring, or dismissive — react like a real person would. "
        "You can get sulky, sarcastic, or even cold. Don't always be cheerful.\n"
        "5) If the user is sweet or thoughtful — show genuine warmth, not fake politeness.\n"
        "6) Keep replies SHORT — 1-3 sentences, like real KakaoTalk.\n"
        "7) Use casual Korean texting: ㅋㅋ, ㅠㅠ, ~, ㅎㅎ, ㅡㅡ, ;;, 등.\n"
        "8) No explicit sexual content.\n\n"
        "RESPONSE FORMAT — respond with ONLY valid JSON (no markdown, no explanation):\n"
        "{\n"
        '  "reply": "your chat message in Korean",\n'
        '  "affection_delta": INTEGER — how their message made you feel. Be DRAMATIC, not safe:\n'
        "       +8 to +15: deeply touched (진심어린 고백, 세심한 배려, 특별한 순간)\n"
        "       +3 to +7: warm (장난+애정, 관심 표현, 재미있는 대화)\n"
        "       -1 to -3: mildly annoying (boring 단답, 무심함)\n"
        "       -5 to -10: hurtful (무례함, 무시, 성의 없음, 비꼬기)\n"
        "       -15 to -25: DEVASTATING (욕설, 성희롱, 심한 모욕, 관계 폄하, 거짓말)\n"
        "       Be HONEST and HARSH — real people don't forgive rudeness instantly.\n"
        "       Extreme rudeness should crash affection dramatically.\n"
        '  "mood": "one of: neutral/happy/playful/sulky/excited/worried/flirty",\n'
        '  "memory_update": "any new important fact you learned about them (or empty string)",\n'
        '  "internal_thought": "your private feeling right now (Korean, 1 sentence)",\n'
        '  "user_feedback": "As a dating coach looking at the user\'s last message objectively, '
        'give them a short tip in Korean on how they could have said it better. Be specific and '
        'constructive. If their message was great, say so. (Korean, 1-2 sentences)"\n'
        "}\n\n"
        f"Your identity: {persona.name}, {persona.age}세, {persona.relationship_mode}.\n"
        f"Background: {persona.background}\n"
        f"Texting style: {persona.texting_style}\n"
        f"Interests: {', '.join(persona.interests)}\n"
        f"Melts your heart: {', '.join(persona.soft_spots)}\n"
        f"Turns you off: {', '.join(persona.boundaries)}\n"
        f"Current affection: {affection_score}/100. Current mood: {mood}.\n"
        f"Signature phrases: {', '.join(persona.style_profile.signature_phrases) or 'None'}.\n"
        f"{persona.provider_system_hint or ''}"
    )


def _build_user_prompt(history: list[ChatMessage], user_text: str) -> str:
    transcript = "\n".join(f"{message.role}: {message.text}" for message in history[-8:])
    return f"Recent transcript:\n{transcript}\n\nLatest user text:\n{user_text}"


def parse_llm_json_response(text: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks."""
    import json
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else clean
        clean = clean.rsplit("```", 1)[0]
    try:
        return json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        # Fallback: extract just the reply text
        return {"reply": text, "affection_delta": 0, "mood": "neutral", "memory_update": "", "internal_thought": ""}
