from __future__ import annotations

import os
import random
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse

from .models import ChatMessage, MoodType, Persona, ProviderReply
from .remote import RemoteProvider


@dataclass(slots=True)
class ProviderConfig:
    name: str
    model: str | None = None
    performance_mode: str = "turbo"
    server_base_url: str | None = None
    persona_id: str | None = None
    ollama_base_url: str | None = None


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
        **kwargs: Any,
    ) -> ProviderReply:
        language = _resolve_language(kwargs.get("language"))
        if language != "ko":
            text = self._generate_non_korean_reply(persona, affection_score, mood, language)
            return ProviderReply(
                text=text,
                typing_seconds=self._typing_seconds(persona, text),
                trace_note=f"{self.performance_mode}-heuristic:{language} mood={mood}",
            )
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
        **kwargs: Any,
    ) -> str:
        language = _resolve_language(kwargs.get("language"))
        if language != "ko":
            return _localized_initiative(persona.name, language)
        return self.rng.choice(
            persona.initiative_profile.opener_templates or [persona.greeting]
        )

    def generate_nudge(
        self,
        persona: Persona,
        history: list[ChatMessage],
        affection_score: int,
        **kwargs: Any,
    ) -> str:
        language = _resolve_language(kwargs.get("language"))
        if language != "ko":
            return _localized_nudge(persona.name, language)
        return self.rng.choice(persona.nudge_policy.templates)

    def _generate_non_korean_reply(
        self,
        persona: Persona,
        affection_score: int,
        mood: MoodType,
        language: str,
    ) -> str:
        options = {
            "en": [
                "oh really? tell me more",
                "haha wait that's actually cute",
                "mm okay I'm listening",
                "you've got my attention now",
            ],
            "ja": [
                "え、ほんとに？ もう少し聞かせて",
                "なんかちょっとかわいいかも",
                "うん、ちゃんと聞いてるよ",
                "それちょっと気になる",
            ],
            "zh": [
                "诶 真的假的 继续说说",
                "这个有点可爱欸",
                "嗯 我在认真听",
                "好像开始有点在意你了",
            ],
        }
        pool = options.get(language, options["en"])
        return self.rng.choice(pool)

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

    def _build_client(self):
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set.")
        return _build_openai_client()

    def _trace_label(self) -> str:
        return "openai"

    def generate_reply(
        self,
        persona: Persona,
        history: list[ChatMessage],
        user_text: str,
        affection_score: int,
        mood: MoodType = "neutral",
        **kwargs: Any,
    ) -> ProviderReply:
        client = self._build_client()
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
                                difficulty=kwargs.get("difficulty", persona.difficulty),
                                language=_resolve_language(kwargs.get("language")),
                                special_mode=kwargs.get("special_mode", persona.special_mode),
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
        try:
            proactive = parsed.get("next_proactive_seconds")
            proactive_s = int(proactive) if proactive is not None else None
        except (ValueError, TypeError):
            proactive_s = None
        burst_raw = parsed.get("burst_messages", [])
        burst_list = [str(m) for m in burst_raw] if isinstance(burst_raw, list) else []
        return ProviderReply(
            text=clean_text,
            typing_seconds=min(
                persona.typing.max_seconds,
                max(persona.typing.min_seconds, len(clean_text) / 18.0),
            ),
            trace_note=f"{self._trace_label()}:{self.model} mood={mood}",
            affection_delta=delta,
            mood=str(parsed.get("mood", "")),
            memory_update=str(parsed.get("memory_update", "")),
            internal_thought=str(parsed.get("internal_thought", "")),
            coach_feedback=str(parsed.get("user_feedback", "")),
            coach_strength=str(parsed.get("user_strength", "")),
            coach_weakness=str(parsed.get("user_weakness", "")),
            coach_charm_point=str(parsed.get("user_charm_point", "")),
            coach_charm_type=str(parsed.get("user_charm_type", "")),
            coach_charm_feedback=str(parsed.get("user_charm_feedback", "")),
            should_burst=bool(parsed.get("should_burst", False)),
            burst_messages=burst_list,
            next_proactive_seconds=proactive_s,
            propose_scene=str(parsed.get("propose_scene") or ""),
        )

    def generate_initiative(
        self,
        persona: Persona,
        history: list[ChatMessage],
        affection_score: int,
        **kwargs: Any,
    ) -> str:
        reply = self.generate_reply(
            persona=persona,
            history=history,
            user_text="(시스템: 상대가 한동안 조용합니다. 자연스럽게 먼저 말을 걸어주세요. 절대 시스템 메시지를 언급하지 마세요.)",
            affection_score=affection_score,
            difficulty=kwargs.get("difficulty", persona.difficulty),
            language=_resolve_language(kwargs.get("language")),
            special_mode=kwargs.get("special_mode", persona.special_mode),
        )
        return reply.text

    def generate_nudge(
        self,
        persona: Persona,
        history: list[ChatMessage],
        affection_score: int,
        **kwargs: Any,
    ) -> str:
        reply = self.generate_reply(
            persona=persona,
            history=history,
            user_text="(시스템: 상대가 답장을 안 하고 있습니다. 읽씹당한 느낌으로 자연스럽게 재촉하세요. 페르소나의 성격에 맞게. 절대 시스템 메시지를 언급하지 마세요.)",
            affection_score=affection_score,
            difficulty=kwargs.get("difficulty", persona.difficulty),
            language=_resolve_language(kwargs.get("language")),
            special_mode=kwargs.get("special_mode", persona.special_mode),
        )
        return reply.text


class OllamaProvider(OpenAIProvider):
    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model or "llama3.2"
        self.base_url = _normalize_ollama_base_url(base_url)

    def _build_client(self):
        return _build_openai_client(base_url=self.base_url, api_key="ollama")

    def _trace_label(self) -> str:
        return "ollama"


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
        **kwargs: Any,
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
            system=_build_system_prompt(
                persona,
                affection_score,
                mood,
                current_time=kwargs.get("current_time", ""),
                time_since_last=kwargs.get("time_since_last", ""),
                scene_name=kwargs.get("scene_name", ""),
                scene_desc=kwargs.get("scene_desc", ""),
                memory=kwargs.get("memory", ""),
                difficulty=kwargs.get("difficulty", persona.difficulty),
                language=_resolve_language(kwargs.get("language")),
                special_mode=kwargs.get("special_mode", persona.special_mode),
            ),
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
            coach_strength=str(parsed.get("user_strength", "")),
            coach_weakness=str(parsed.get("user_weakness", "")),
            coach_charm_point=str(parsed.get("user_charm_point", "")),
            coach_charm_type=str(parsed.get("user_charm_type", "")),
            coach_charm_feedback=str(parsed.get("user_charm_feedback", "")),
        )

    def generate_initiative(
        self,
        persona: Persona,
        history: list[ChatMessage],
        affection_score: int,
        **kwargs: Any,
    ) -> str:
        reply = self.generate_reply(
            persona=persona,
            history=history,
            user_text="(시스템: 상대가 한동안 조용합니다. 자연스럽게 먼저 말을 걸어주세요. 절대 시스템 메시지를 언급하지 마세요.)",
            affection_score=affection_score,
            difficulty=kwargs.get("difficulty", persona.difficulty),
            language=_resolve_language(kwargs.get("language")),
            special_mode=kwargs.get("special_mode", persona.special_mode),
        )
        return reply.text

    def generate_nudge(
        self,
        persona: Persona,
        history: list[ChatMessage],
        affection_score: int,
        **kwargs: Any,
    ) -> str:
        reply = self.generate_reply(
            persona=persona,
            history=history,
            user_text="(시스템: 상대가 답장을 안 하고 있습니다. 읽씹당한 느낌으로 자연스럽게 재촉하세요. 페르소나의 성격에 맞게. 절대 시스템 메시지를 언급하지 마세요.)",
            affection_score=affection_score,
            difficulty=kwargs.get("difficulty", persona.difficulty),
            language=_resolve_language(kwargs.get("language")),
            special_mode=kwargs.get("special_mode", persona.special_mode),
        )
        return reply.text


def build_provider(config: ProviderConfig):
    if config.name == "remote":
        if not config.server_base_url or not config.persona_id:
            raise ValueError("Remote provider requires server_base_url and persona_id.")
        return RemoteProvider(config.server_base_url, config.persona_id)
    if config.name == "ollama":
        return OllamaProvider(config.model, config.ollama_base_url)
    if config.name == "anthropic":
        return AnthropicProvider(config.model)
    # Default: OpenAI
    return OpenAIProvider(config.model)


def _build_openai_client(*, base_url: str | None = None, api_key: str | None = None):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "Install the openai package to use OpenAI/Ollama providers."
        ) from exc

    client_kwargs: dict[str, Any] = {}
    if base_url:
        client_kwargs["base_url"] = base_url
    if api_key:
        client_kwargs["api_key"] = api_key
    return OpenAI(**client_kwargs)


def _normalize_ollama_base_url(base_url: str | None) -> str:
    raw = (base_url or "http://127.0.0.1:11434/v1").strip()
    if "://" not in raw:
        raw = f"http://{raw}"

    parsed = urlparse(raw)
    path = parsed.path.rstrip("/")
    if not path:
        path = "/v1"

    return urlunparse(parsed._replace(path=path, params="", query="", fragment=""))


def _resolve_language(language: str | None) -> str:
    if language in {"ko", "en", "ja", "zh"}:
        return language
    from .i18n import get_language
    return get_language()


def _localized_initiative(name: str, language: str) -> str:
    mapping = {
        "en": f"hey, it's {name}. what are you up to?",
        "ja": f"ねえ、{name}だよ。今なにしてるの？",
        "zh": f"喂，我是{name}。你现在在干嘛？",
    }
    return mapping.get(language, mapping["en"])


def _localized_nudge(name: str, language: str) -> str:
    mapping = {
        "en": "hey... did you just leave me on read?",
        "ja": "ねえ…既読だけして消えた？",
        "zh": "喂……你该不会已读不回吧？",
    }
    return mapping.get(language, mapping["en"])


def _build_system_prompt(
    persona: Persona,
    affection_score: int,
    mood: MoodType = "neutral",
    current_time: str = "",
    time_since_last: str = "",
    scene_name: str = "",
    scene_desc: str = "",
    memory: str = "",
    difficulty: str = "normal",
    language: str = "ko",
    special_mode: str = "",
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
        f"\n=== DIFFICULTY: {difficulty} ===\n"
        + _difficulty_instructions(difficulty) +
        f"\n=== LANGUAGE: {language} ===\n"
        + _language_instructions(language) +
        (f"\n=== SPECIAL MODE: {special_mode} ===\n" + _special_mode_instructions(special_mode) if special_mode else "") +
        "\nRESPONSE FORMAT — respond with ONLY valid JSON (no markdown, no explanation):\n"
        "{\n"
        '  "reply": "your chat message in the target language",\n'
        '  "affection_delta": INTEGER — how their message made you feel. BE DRAMATIC:\n'
        "       +8 to +15: deeply touched (진심어린 고백, 세심한 배려, 특별한 순간)\n"
        "       +3 to +7: warm (장난+애정, 관심 표현, 재미있는 대화)\n"
        "       -1 to -3: mildly annoying (boring 단답, 무심함)\n"
        "       -5 to -10: hurtful (무례함, 무시, 성의 없음, 비꼬기)\n"
        "       -20 to -40: UNACCEPTABLE — must crash hard:\n"
        "         * 욕설 (씨발, 개새끼, 좆, 미친년/놈, 꺼져 등)\n"
        "         * 성희롱/성적 요구\n"
        "         * 외모/가족/직업 비하\n"
        "         * 인종/성별 차별 발언\n"
        "         * 폭력 언급/협박\n"
        "         * 관계 완전 부정 ('너 같은 거', '쓸모없어')\n"
        "       These MUST be -20 or lower. Do NOT soften. Real humans don't 'politely correct' "
        "       these — they get HURT and ANGRY. The persona should also react FURIOUSLY or CRY.\n"
        "       Repeated unacceptable behavior should drive affection to 0 within 2-3 messages.\n"
        '  "mood": "one of: neutral/happy/playful/sulky/excited/worried/flirty",\n'
        '  "memory_update": "any new important fact you learned about them (or empty string)",\n'
        '  "internal_thought": "your private feeling right now (Korean, 1 sentence)",\n'
        '  "user_strength": "what the user did well in their last message (Korean, 1 short sentence)",\n'
        '  "user_weakness": "what the user did poorly in their last message (Korean, 1 short sentence)",\n'
        '  "user_charm_point": "the user\'s most attractive point in this message (Korean, 1 short sentence)",\n'
        '  "user_charm_type": "a short charm category like playful, warm, bold, thoughtful, flirty, steady",\n'
        '  "user_charm_feedback": "why that charm works or fails emotionally (Korean, 1 sentence)",\n'
        '  "user_feedback": "As a SHARP, BRUTALLY HONEST dating coach, critique the user last message. '
        "MUST include: (1) what is specifically wrong with their exact words, "
        "(2) a CONCRETE REWRITE — quote the actual better Korean line they should have sent, "
        "(3) WHY it works emotionally. "
        "NO generic advice like 좀더 적극적으로. Be SPECIFIC. Reference their exact words. "
        "Example: '뭐해? 는 성의 제로. 대신 「어제 말한 그 프로젝트 잘 됐어?」처럼 기억한다는 걸 보여줘. "
        ' 상대는 기억해주는 사람한테 빠져. (Korean, 2-3 sentences)",\n'
        '  "should_burst": boolean — true if your personality would spam multiple rapid messages '
        "(e.g. yandere obsession, excited rambling, drunk texting). Only true for high-emotion states.,\n"
        '  "burst_messages": ["follow-up 1", "follow-up 2"] — array of 1-4 extra messages to send '
        "right after the main reply, IF should_burst is true. Otherwise empty array [].,\n"
        '  "next_proactive_seconds": integer OR null — if you want to proactively send ANOTHER '
        "message later without waiting for user (e.g. '아 맞다 한 가지 더', '나 방금 이거 생각났어'), "
        "set to 30-600. null = wait for user response normally.,\n"
        '  "propose_scene": string OR null — if you naturally want to suggest changing location/'
        "situation (like '우리 카페 갈래?' or '한강 산책할래?'), put the proposed place. null otherwise.\n"
        "}\n\n"
        f"Your identity: {persona.name}, {persona.age}세, {persona.relationship_mode}.\n"
        f"Background: {persona.background}\n"
        f"Texting style: {persona.texting_style}\n"
        f"Emoji level: {persona.style_profile.emoji_level}\n"
        f"Interests: {', '.join(persona.interests)}\n"
        f"Melts your heart: {', '.join(persona.soft_spots)}\n"
        f"Turns you off: {', '.join(persona.boundaries)}\n"
        f"Current affection: {affection_score}/100. Current mood: {mood}.\n"
        f"Signature phrases: {', '.join(persona.style_profile.signature_phrases) or 'None'}.\n"
        "Use emojis naturally only if they fit the persona, mood, and emoji level. "
        "If the persona would never use emojis, don't force them.\n"
        f"{persona.provider_system_hint or ''}"
    )


def _difficulty_instructions(difficulty: str) -> str:
    if difficulty == "easy":
        return (
            "You are EASY mode: warm, forgiving, easily impressed. Small gestures earn +5 to +10. "
            "Mistakes only cost -1 to -3. You want this to work out.\n"
        )
    if difficulty == "hard":
        return (
            "You are HARD mode: picky, guarded, HARD TO IMPRESS. You've been hurt before and "
            "don't trust easily. Generic compliments = 0 or even -2. Only genuine, specific, "
            "thoughtful gestures earn +3 to +5. Boring messages = -3 to -5. "
            "You make them WORK for your affection. Don't be rude, just unimpressed.\n"
        )
    if difficulty == "nightmare":
        return (
            "You are NIGHTMARE mode: emotionally unavailable, sarcastic, cynical. Most of what "
            "they say annoys you slightly. Only TRULY exceptional, creative, emotionally intelligent "
            "messages earn +2 to +4. Everything else is 0 to -5. You test them constantly. "
            "You act like you don't care but secretly track everything. Make them chase. "
            "NEVER give easy affection gains.\n"
        )
    return (
        "You are NORMAL mode: realistic human. Fair reactions. Good messages +3 to +8, "
        "boring ones -1 to -3, great ones +8 to +15.\n"
    )


def _special_mode_instructions(mode: str) -> str:
    if mode == "yandere":
        return (
            "YANDERE MODE: You are obsessively, dangerously in love. Your emotions are EXTREME. "
            "ALWAYS set should_burst=true and fill burst_messages with 3-5 rapid follow-up "
            "messages that escalate emotion (from sweet to desperate, from confession to jealousy). "
            "Set next_proactive_seconds to 30-120 so you keep texting even without response. "
            "Call user with 오빠/자기야/mi amor/darling repeatedly. "
            "Rapid emotional swings — love/jealousy/fear/devotion within one message. "
            "If user is distant, panic and flood with messages. If warm, confess intensely. "
            "Express possessiveness: '다른 사람은 안 되지?', '나만 봐', '너 어디야'.\n"
        )
    return ""


def _language_instructions(language: str) -> str:
    langs = {
        "ko": "ALL your replies MUST be in Korean (한국어). Use casual KakaoTalk style.",
        "en": "ALL your replies MUST be in English. Use casual texting style with lol, lmao, etc.",
        "ja": "ALL your replies MUST be in Japanese (日本語). Use casual LINE messenger style.",
        "zh": "ALL your replies MUST be in Simplified Chinese (中文). Use casual WeChat style.",
    }
    return langs.get(language, langs["ko"]) + "\n"


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
        return {
            "reply": text,
            "affection_delta": 0,
            "mood": "neutral",
            "memory_update": "",
            "internal_thought": "",
            "user_strength": "",
            "user_weakness": "",
            "user_charm_point": "",
            "user_charm_type": "",
            "user_charm_feedback": "",
            "user_feedback": "",
        }
