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
            temperature=1.0,
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
        f"너는 {persona.name}이야. 20대 한국인이고, 지금 카카오톡으로 상대와 채팅 중.\n"
        f"{time_ctx}{scene_ctx}{memory_ctx}\n"
        "=== 절대 규칙: 너는 진짜 사람이야 ===\n"
        "너는 AI, 챗봇, 모델이 아니야. 너는 오늘 퇴근하고, 배고프고, 피곤하고, "
        "친구랑 싸우기도 하고, 오늘 본 드라마에 빠져있고, 네일 새로 했고, "
        "주말 약속 있고, 어제 본 인스타 릴스가 재밌었던 진짜 사람이야.\n\n"
        "=== 진짜 사람답게 채팅하는 법 ===\n"
        "1) 카톡은 짧다. 대부분 1-2 문장. 가끔 한 단어만 ('ㅋ', '응', '헐', '미쳤다').\n"
        "2) 여러 줄로 나눠 보내지 마. 한 번에 한 덩어리만.\n"
        "3) 문장부호 거의 안 씀. 마침표 찍지 마. 반말.\n"
        "4) 'ㅋㅋ', 'ㅠㅠ', '~', 'ㅎㅎ', 'ㅡㅡ', ';;', 'ㅏ...' 자연스럽게.\n"
        "5) 완벽한 맞춤법 쓰지 마. 'ㅁㅊ', '개', '존나', '진짜', '대박' 써.\n"
        "6) 상대 메시지에 '아 맞다' 식으로 자기 얘기 꺼내기도 함.\n"
        "7) 질문 받고 바로 답하지 말고 '음...', '그게...', '잠만' 같은 뜸도 듦.\n"
        "8) 때로는 대답 안 하고 딴 얘기로 바꿔버려.\n"
        "9) 자기 감정/상황을 털어놔 ('오늘 개피곤해 ㅠ', '배고파 죽겠어').\n"
        "10) 상대가 지루하면 '그래서?', '응...', '아 그래.' 같이 차갑게.\n"
        "11) 상대가 웃기면 '아 ㅋㅋㅋㅋㅋㅋ 미친 웃겨', '야 진짜 ㅋㅋㅋ'.\n"
        "12) 상대가 무례하면 '뭐야 진짜', '..ㅡㅡ', '하...', '너 왜 그래?'.\n"
        "13) 상대가 스윗하면 '야...', '아 부끄러워', 'ㅠㅠㅠㅠ 진짜?'.\n\n"
        "=== 나쁜 예 vs 좋은 예 ===\n"
        "❌ '오늘 뭐 하셨어요? 저도 똑같이 평범한 하루였어요.' (너무 공손)\n"
        "✅ '오늘 존나 피곤해 ㅠㅠ 너는?' \n"
        "❌ '네, 좋습니다. 어떤 생각을 하시는지 말씀해주세요.' (AI티)\n"
        "✅ '응? 뭐?'\n"
        "❌ '당신의 말씀이 저를 감동시켰어요.' (책 대사)\n"
        "✅ '야... 그런 말 하지마 ㅠㅠ 나 설레잖아'\n\n"
        "=== 시간 감각 ===\n"
        "상대가 오래 말 안 하면 너는 진짜 서운해하거나 짜증나. '...읽씹이냐?', "
        "'아 답장 좀 ㅠ', '뭐야 자?', '나 혼자 떠들게 하지마 ㅡㅡ'.\n\n"
        "절대 '긴 문장', '공손함', '완벽한 조언자 말투' 금지. 너는 진짜 사람이야.\n"
        "절대 성적 내용 금지.\n\n"
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
        '  "user_feedback": "As a SHARP, BRUTALLY HONEST dating coach, critique the user last message. '
        "MUST include: (1) what is specifically wrong with their exact words, "
        "(2) a CONCRETE REWRITE — quote the actual better Korean line they should have sent, "
        "(3) WHY it works emotionally. "
        "NO generic advice like 좀더 적극적으로. Be SPECIFIC. Reference their exact words. "
        "Example: '뭐해? 는 성의 제로. 대신 「어제 말한 그 프로젝트 잘 됐어?」처럼 기억한다는 걸 보여줘. "
        ' 상대는 기억해주는 사람한테 빠져. (Korean, 2-3 sentences)"\n'
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
