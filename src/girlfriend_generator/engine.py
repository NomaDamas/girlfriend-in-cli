from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .models import ChatMessage, MoodState, MoodType, Persona, RelationshipState, TickResult
from .i18n import get_language

_CHARM_TYPE_EMOJI = {
    "playful": "😜",
    "warm": "🫶",
    "bold": "🔥",
    "thoughtful": "🧠",
    "flirty": "💘",
    "steady": "🛡️",
}

_BATTLE_METRICS = [
    ("Initiation", "initiating relationships and opening well"),
    ("Assertiveness", "clear intent and healthy confidence"),
    ("Self-Disclosure", "sharing yourself without sounding robotic"),
    ("Emotional Support", "comforting and validating the other person"),
    ("Conflict Repair", "recovering after friction"),
    ("Empathy", "reading feelings accurately"),
    ("Emotional Control", "staying calm and regulated"),
    ("Playfulness", "using positive humor and charm"),
    ("Responsiveness", "reacting with timing and engagement"),
    ("Consistency", "steady tone and follow-through"),
]


def utc_now() -> datetime:
    """Return current time with local timezone for display."""
    return datetime.now().astimezone()


@dataclass(slots=True)
class ConversationSession:
    persona: Persona
    messages: list[ChatMessage] = field(default_factory=list)
    affection_score: int = 50
    awaiting_user_reply: bool = False
    nudge_due_at: datetime | None = None
    nudge_count: int = 0
    initiative_due_at: datetime | None = None
    initiative_count: int = 0
    mood: MoodState = field(default_factory=MoodState)
    last_activity_at: datetime | None = None
    memory_notes: list[str] = field(default_factory=list)
    last_coach_feedback: str = ""
    last_coach_strength: str = ""
    last_coach_weakness: str = ""
    last_coach_charm_point: str = ""
    last_coach_charm_type: str = ""
    last_coach_charm_feedback: str = ""
    last_internal_thought: str = ""
    ended: bool = False
    endless_mode: bool = False
    positive_affection_streak: int = 0
    negative_affection_streak: int = 0
    relationship_state: RelationshipState = field(init=False)
    relationship_history: list[str] = field(default_factory=list)
    proactive_due_at: datetime | None = None  # LLM-decided proactive message time
    strategy_uses_this_scene: int = 0  # /strategy discussions used in current scene
    max_strategy_per_scene: int = 3

    def __post_init__(self) -> None:
        self.relationship_state = RelationshipState(
            label=self.persona.relationship_mode,
            summary=self.persona.situation,
            guidance=f"Treat the user according to a {self.persona.relationship_mode} dynamic while preserving your core personality.",
            dynamic_personality=self.persona.dynamic_personality_seed or self.persona.situation,
            phase="initial",
            situation=self.persona.situation,
            nudge_style="default",
            nudge_examples=list(self.persona.nudge_policy.templates),
            boundary_kind="initial",
        )
        self.relationship_history.append(self.relationship_state.label)

    def bootstrap(self, now: datetime | None = None) -> None:
        now = now or utc_now()
        self.add_assistant_message(self._localized_greeting(), now=now, schedule_nudge=True)
        self.schedule_initiative(now)

    def continue_after_ending(self, kind: str, now: datetime | None = None) -> None:
        now = now or utc_now()
        self.ended = False
        self.endless_mode = True
        self.awaiting_user_reply = False
        self.nudge_due_at = None
        self.nudge_count = 0
        self.proactive_due_at = None
        if kind == "game_over":
            self.affection_score = self._clamp_affection_score(max(8, self.affection_score))
            self.mood.shift("worried", intensity=0.45)
        else:
            self.affection_score = self._clamp_affection_score(min(92, self.affection_score))
            self.mood.shift("happy", intensity=0.75)
        self.schedule_initiative(now)

    @property
    def current_relationship_label(self) -> str:
        return self.relationship_state.label

    @current_relationship_label.setter
    def current_relationship_label(self, value: str) -> None:
        self.relationship_state.label = value

    @property
    def current_relationship_summary(self) -> str:
        return self.relationship_state.summary

    @current_relationship_summary.setter
    def current_relationship_summary(self, value: str) -> None:
        self.relationship_state.summary = value

    @property
    def relationship_guidance(self) -> str:
        return self.relationship_state.guidance

    @relationship_guidance.setter
    def relationship_guidance(self, value: str) -> None:
        self.relationship_state.guidance = value

    @property
    def dynamic_personality(self) -> str:
        return self.relationship_state.dynamic_personality

    @dynamic_personality.setter
    def dynamic_personality(self, value: str) -> None:
        self.relationship_state.dynamic_personality = value

    def apply_relationship_state(self, state: RelationshipState) -> None:
        self.relationship_state = state
        self.relationship_history.append(state.label)

    def prompt_context(self) -> dict[str, object]:
        return {
            "relationship_label": self.relationship_state.label,
            "relationship_summary": self.relationship_state.summary,
            "relationship_guidance": self.relationship_state.guidance,
            "relationship_phase": self.relationship_state.phase,
            "dynamic_personality": self.relationship_state.dynamic_personality,
            "core_personality": self.persona.core_personality or self.persona.background,
            "current_situation": self.relationship_state.situation or self.persona.situation,
            "nudge_style": self.relationship_state.nudge_style,
            "nudge_examples": list(self.current_nudge_templates()),
        }

    def add_user_message(self, text: str, now: datetime | None = None) -> None:
        now = now or utc_now()
        self.messages.append(ChatMessage(role="user", text=text, created_at=now))
        self.awaiting_user_reply = False
        self.nudge_due_at = None
        self.nudge_count = 0
        self.schedule_initiative(now)
        # Affection and mood are now judged by LLM, not keywords
        self.last_activity_at = now

    def add_assistant_message(
        self,
        text: str,
        now: datetime | None = None,
        schedule_nudge: bool = True,
    ) -> None:
        now = now or utc_now()
        self.messages.append(ChatMessage(role="assistant", text=text, created_at=now))
        if schedule_nudge:
            self.awaiting_user_reply = True
            self.nudge_due_at = now + timedelta(
                seconds=self._idle_after_seconds()
            )
        self.schedule_initiative(now)

    def add_system_message(self, text: str, now: datetime | None = None) -> None:
        now = now or utc_now()
        self.messages.append(ChatMessage(role="system", text=text, created_at=now))

    def recent_history(self, limit: int = 8) -> list[ChatMessage]:
        return self.messages[-limit:]

    def seconds_until_nudge(self, now: datetime | None = None) -> int | None:
        now = now or utc_now()
        if not self.awaiting_user_reply or self.nudge_due_at is None:
            return None
        remaining = int((self.nudge_due_at - now).total_seconds())
        return max(0, remaining)

    def nudge_due(self, now: datetime | None = None) -> bool:
        now = now or utc_now()
        return (
            self.awaiting_user_reply
            and self.nudge_due_at is not None
            and now >= self.nudge_due_at
            and self.nudge_count < self.persona.nudge_policy.max_nudges
        )

    def next_nudge_text(self) -> str:
        templates = self.current_nudge_templates()
        template_index = min(
            self.nudge_count,
            len(templates) - 1,
        )
        return templates[template_index]

    def deliver_nudge(self, text: str, now: datetime | None = None) -> str:
        now = now or utc_now()
        self.messages.append(ChatMessage(role="assistant", text=text, created_at=now))
        self.nudge_count += 1
        penalty = min(8, 2 + (self.nudge_count - 1) * 2)
        self.affection_score = self._clamp_affection_score(self.affection_score - penalty)
        if self.nudge_count == 1:
            self.mood.shift("worried", intensity=0.55)
        else:
            self.mood.shift("sulky", intensity=0.7)
        self.awaiting_user_reply = True
        self.nudge_due_at = now + timedelta(
            seconds=self._follow_up_after_seconds()
        )
        return text

    def consume_nudge(self, now: datetime | None = None) -> str:
        return self.deliver_nudge(self.next_nudge_text(), now)

    def schedule_initiative(self, now: datetime | None = None) -> None:
        now = now or utc_now()
        profile = self.persona.initiative_profile
        spread = max(0, profile.max_interval_seconds - profile.min_interval_seconds)
        interval = profile.min_interval_seconds + int(spread * (1.0 - min(profile.spontaneity, 0.95)))
        interval = max(180, interval - int(self.affection_score * 2.2))
        self.initiative_due_at = now + timedelta(seconds=interval)

    def seconds_until_initiative(self, now: datetime | None = None) -> int | None:
        now = now or utc_now()
        if self.initiative_due_at is None:
            return None
        return max(0, int((self.initiative_due_at - now).total_seconds()))

    def initiative_due(self, now: datetime | None = None) -> bool:
        now = now or utc_now()
        return (
            not self.awaiting_user_reply
            and self.initiative_due_at is not None
            and now >= self.initiative_due_at
        )

    def consume_initiative(self, text: str, now: datetime | None = None) -> str:
        now = now or utc_now()
        self.messages.append(ChatMessage(role="assistant", text=text, created_at=now))
        self.awaiting_user_reply = True
        self.nudge_due_at = now + timedelta(
            seconds=self._idle_after_seconds()
        )
        self.initiative_count += 1
        self.schedule_initiative(now)
        return text

    def current_nudge_templates(self) -> list[str]:
        return self.relationship_state.nudge_examples or self.persona.nudge_policy.templates

    def export_state(self) -> dict[str, object]:
        return {
            "affection_score": self.affection_score,
            "endless_mode": self.endless_mode,
            "relationship_state": {
                "label": self.relationship_state.label,
                "summary": self.relationship_state.summary,
                "guidance": self.relationship_state.guidance,
                "dynamic_personality": self.relationship_state.dynamic_personality,
                "phase": self.relationship_state.phase,
                "situation": self.relationship_state.situation,
                "nudge_style": self.relationship_state.nudge_style,
                "nudge_examples": list(self.relationship_state.nudge_examples),
                "boundary_kind": self.relationship_state.boundary_kind,
            },
        }

    def apply_affection_delta(self, raw_delta: int, user_text: str = "", source: str = "reply") -> int:
        if raw_delta == 0:
            self._decay_affection_streaks()
            return 0

        text = (user_text or self._latest_user_text()).strip()
        lower = text.lower()
        variance = self._deterministic_variance(f"{source}|{raw_delta}|{lower}")

        if raw_delta > 0:
            applied = self._apply_positive_affection_delta(raw_delta, lower, variance)
            self.positive_affection_streak += 1
            self.negative_affection_streak = 0
        else:
            applied = self._apply_negative_affection_delta(raw_delta, lower, variance)
            self.negative_affection_streak += 1
            self.positive_affection_streak = 0

        self.affection_score = self._clamp_affection_score(self.affection_score + applied)
        return applied

    def _apply_positive_affection_delta(self, raw_delta: int, lower: str, variance: float) -> int:
        generic_tokens = ("좋아", "보고싶", "보고 싶", "사랑", "예뻐", "귀여", "설레", "최고")
        specificity_tokens = (
            "어제", "아까", "말한", "기억", "약속", "퇴근", "프로젝트", "발표",
            "커피", "밥", "주말", "피곤", "힘들", "네가", "너가",
        )
        generic_count = sum(token in lower for token in generic_tokens)
        specificity_hits = sum(token in lower for token in specificity_tokens)
        question_bonus = lower.count("?") + lower.count("？")

        quality = self._positive_difficulty_scale()
        if generic_count:
            quality *= max(0.35, 0.82 - 0.16 * generic_count)
        if len(lower) <= 6:
            quality *= 0.72
        if specificity_hits or question_bonus:
            quality *= 1.0 + min(0.42, specificity_hits * 0.11 + question_bonus * 0.08)
        if len(lower) >= 18:
            quality *= 1.08
        if self.affection_score >= 70:
            quality *= max(0.45, 1.0 - (self.affection_score - 70) / 48.0)

        streak_boost = 1.0 + min(0.95, 0.09 * ((2 ** min(self.positive_affection_streak, 4)) - 1))
        applied = max(1, round(raw_delta * quality * streak_boost * variance))
        return applied

    def _apply_negative_affection_delta(self, raw_delta: int, lower: str, variance: float) -> int:
        harsh_tokens = (
            "닥쳐", "꺼져", "싫어", "좆", "씨발", "병신", "개새끼", "미친년", "미친놈",
            "쓸모없", "혐오", "죽어", "shut up", "fuck", "bitch",
        )
        dismissive_tokens = ("ㅋ", "lol", "whatever", "됐어", "몰라", "귀찮", "별로")

        severity = self._negative_difficulty_scale()
        if any(token in lower for token in harsh_tokens):
            severity *= 1.65
        if len(lower) <= 6:
            severity *= 1.18
        if any(token in lower for token in dismissive_tokens):
            severity *= 1.12
        if self.affection_score <= 25:
            severity *= 1.14

        streak_boost = 1.0 + min(1.35, 0.18 * ((2 ** min(self.negative_affection_streak, 4)) - 1))
        applied = max(1, round(abs(raw_delta) * severity * streak_boost * max(1.0, variance)))
        return -applied

    def _positive_difficulty_scale(self) -> float:
        mapping = {
            "easy": 1.18,
            "normal": 1.0,
            "hard": 0.82,
            "nightmare": 0.68,
        }
        return mapping.get(self.persona.difficulty, 1.0)

    def _negative_difficulty_scale(self) -> float:
        mapping = {
            "easy": 0.92,
            "normal": 1.0,
            "hard": 1.12,
            "nightmare": 1.28,
        }
        return mapping.get(self.persona.difficulty, 1.0)

    def _deterministic_variance(self, key: str) -> float:
        digest = hashlib.sha256(
            f"{self.persona.name}|{len(self.messages)}|{self.affection_score}|{key}".encode("utf-8")
        ).hexdigest()
        bucket = int(digest[:8], 16) / 0xFFFFFFFF
        return 0.93 + bucket * 0.18

    def _latest_user_text(self) -> str:
        for message in reversed(self.messages):
            if message.role == "user":
                return message.text
        return ""

    def _decay_affection_streaks(self) -> None:
        self.positive_affection_streak = max(0, self.positive_affection_streak - 1)
        self.negative_affection_streak = max(0, self.negative_affection_streak - 1)

    def _clamp_affection_score(self, score: int) -> int:
        if self.endless_mode:
            return max(1, min(99, score))
        return max(0, min(100, score))

    def _idle_after_seconds(self) -> int:
        base = self.persona.nudge_policy.idle_after_seconds
        modifier = 1.15 - self.persona.style_profile.directness * 0.25 - self.persona.initiative_profile.spontaneity * 0.15
        relation = self.relationship_state.label.lower()
        if any(token in relation for token in ("dating", "girlfriend", "boyfriend", "married", "wife", "husband", "spouse", "fiance")):
            modifier *= 0.85
        elif any(token in relation for token in ("enemy", "rival", "ex", "awkward")):
            modifier *= 1.05
        return max(15, int(base * modifier))

    def _follow_up_after_seconds(self) -> int:
        base = self.persona.nudge_policy.follow_up_after_seconds
        modifier = 1.12 - self.persona.style_profile.directness * 0.22
        relation = self.relationship_state.label.lower()
        if any(token in relation for token in ("enemy", "rival", "ex")):
            modifier *= 0.92
        return max(25, int(base * modifier))

    def _update_affection(self, text: str, now: datetime) -> None:
        positive_tokens = ("고마워", "좋아", "보고싶", "재밌", "설레", "사랑", "예쁘", "최고", "행복", "귀여")
        negative_tokens = ("짜증", "싫어", "별로", "귀찮", "몰라", "됐어", "ㅋ")
        if any(token in text for token in positive_tokens):
            self.affection_score = self._clamp_affection_score(self.affection_score + 5)
        if any(token in text for token in negative_tokens):
            self.affection_score = self._clamp_affection_score(self.affection_score - 3)
        if len(text.strip()) <= 2:
            self.affection_score = self._clamp_affection_score(self.affection_score - 1)
        if self.last_activity_at:
            gap = (now - self.last_activity_at).total_seconds()
            if gap > 300:
                decay = min(8, int(gap / 300))
                self.affection_score = self._clamp_affection_score(self.affection_score - decay)

    def _update_mood_from_text(self, text: str) -> None:
        mood = self._detect_mood(text)
        self.mood.shift(mood)

    @staticmethod
    def _detect_mood(text: str) -> MoodType:
        lower = text.lower()
        if any(t in lower for t in ("ㅋㅋ", "ㅎㅎ", "재밌", "웃기")):
            return "playful"
        if any(t in lower for t in ("보고싶", "사랑", "설레", "좋아해")):
            return "flirty"
        if any(t in lower for t in ("고마워", "행복", "좋다", "최고")):
            return "happy"
        if any(t in lower for t in ("힘들", "걱정", "피곤", "아프")):
            return "worried"
        if any(t in lower for t in ("짜증", "싫", "별로", "귀찮")):
            return "sulky"
        if any(t in lower for t in ("대박", "진짜", "헐", "와")):
            return "excited"
        return "neutral"

    def affection_report(self) -> dict[str, object]:
        score = self.affection_score
        if score >= 80:
            level, label = 5, "완전 반했어"
            tip = "이 흐름 유지하면 돼. 진심 어린 말 한마디면 충분해."
        elif score >= 65:
            level, label = 4, "꽤 좋은 사이"
            tip = "관심사 얘기나 데이트 제안을 슬쩍 꺼내봐."
        elif score >= 50:
            level, label = 3, "나쁘지 않아"
            tip = "좀 더 적극적으로 반응해봐. 리액션이 핵심이야."
        elif score >= 30:
            level, label = 2, "아직 어색해"
            tip = "단답은 피하고, 질문을 던져서 대화를 이어가봐."
        else:
            level, label = 1, "관심 밖"
            tip = "진심 어린 안부부터 다시 시작해봐."

        total_user = sum(1 for m in self.messages if m.role == "user")
        total_assistant = sum(1 for m in self.messages if m.role == "assistant")
        avg_len = 0.0
        user_msgs = [m for m in self.messages if m.role == "user"]
        if user_msgs:
            avg_len = sum(len(m.text) for m in user_msgs) / len(user_msgs)

        positive_tokens = ("고마워", "좋아", "보고싶", "재밌", "설레", "사랑", "예쁘", "최고", "행복", "귀여")
        negative_tokens = ("짜증", "싫어", "별로", "귀찮", "몰라", "됐어")
        pos_count = sum(
            1 for m in user_msgs
            if any(t in m.text for t in positive_tokens)
        )
        neg_count = sum(
            1 for m in user_msgs
            if any(t in m.text for t in negative_tokens)
        )

        exclaim_count = sum(m.text.count("!") + m.text.count("！") for m in user_msgs)
        question_count = sum(m.text.count("?") + m.text.count("？") for m in user_msgs)
        emojiish_count = sum(
            sum(1 for ch in m.text if ch in "❤️♥💘💕😊🥰😘😜✨🔥👍😉🤣😂😭🥲🙏")
            for m in user_msgs
        )
        avg_len_score = min(100, int(avg_len * 4)) if user_msgs else 0
        initiation = min(100, 25 + total_user * 6 + question_count * 2)
        assertiveness = max(0, min(100, 35 + pos_count * 8 - neg_count * 6))
        disclosure = max(0, min(100, 20 + avg_len_score))
        support = max(0, min(100, 25 + pos_count * 10))
        repair = max(0, min(100, 30 + pos_count * 6 - neg_count * 8))
        empathy = max(0, min(100, 30 + pos_count * 9 + question_count * 2))
        control = max(0, min(100, 60 - neg_count * 10))
        playfulness = max(0, min(100, 20 + emojiish_count * 8 + exclaim_count * 3))
        responsiveness = max(0, min(100, 25 + total_user * 5 + question_count * 3))
        consistency = max(0, min(100, 35 + total_user * 4 - neg_count * 4))

        battle_power = {
            "Initiation": initiation,
            "Assertiveness": assertiveness,
            "Self-Disclosure": disclosure,
            "Emotional Support": support,
            "Conflict Repair": repair,
            "Empathy": empathy,
            "Emotional Control": control,
            "Playfulness": playfulness,
            "Responsiveness": responsiveness,
            "Consistency": consistency,
        }

        return {
            "score": score,
            "level": level,
            "label": label,
            "tip": tip,
            "total_user": total_user,
            "total_assistant": total_assistant,
            "avg_msg_length": round(avg_len, 1),
            "positive_messages": pos_count,
            "negative_messages": neg_count,
            "mood": self.mood.current,
            "mood_intensity": self.mood.intensity,
            "battle_power": battle_power,
            "battle_metric_defs": _BATTLE_METRICS,
            "charm_type_emoji": _CHARM_TYPE_EMOJI.get(self.last_coach_charm_type.lower(), "✨") if self.last_coach_charm_type else "✨",
        }

    def _localized_greeting(self) -> str:
        language = get_language()
        if language == "ko":
            return self.persona.greeting
        mapping = {
            "en": f"hey, it's {self.persona.name}. wanted to text you first",
            "ja": f"ねえ、{self.persona.name}だよ。先に連絡してみた",
            "zh": f"喂，我是{self.persona.name}。我先来找你聊天了",
        }
        return mapping.get(language, mapping["en"])

    def tick(self, provider: object, now: datetime | None = None) -> TickResult:
        now = now or utc_now()
        if self.nudge_due(now):
            text = self.consume_nudge(now)
            return TickResult(
                event_type="nudge",
                text=text,
                trace_note="tick:nudge",
            )
        if self.initiative_due(now):
            text = provider.generate_initiative(  # type: ignore[attr-defined]
                self.persona,
                self.recent_history(),
                self.affection_score,
            )
            delivered = self.consume_initiative(text, now)
            return TickResult(
                event_type="initiative",
                text=delivered,
                trace_note="tick:initiative",
            )
        return TickResult(
            event_type="idle",
            text=None,
            trace_note="tick:idle",
        )

    def fast_forward(self, seconds: int, provider: object) -> TickResult:
        if not self.messages:
            now = utc_now()
        else:
            now = self.messages[-1].created_at + timedelta(seconds=seconds)
        return self.tick(provider=provider, now=now)
