from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .models import ChatMessage, MoodState, MoodType, Persona, TickResult


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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

    def bootstrap(self, now: datetime | None = None) -> None:
        now = now or utc_now()
        self.add_assistant_message(self.persona.greeting, now=now, schedule_nudge=True)
        self.schedule_initiative(now)

    def add_user_message(self, text: str, now: datetime | None = None) -> None:
        now = now or utc_now()
        self.messages.append(ChatMessage(role="user", text=text, created_at=now))
        self.awaiting_user_reply = False
        self.nudge_due_at = None
        self.nudge_count = 0
        self.schedule_initiative(now)
        self._update_affection(text, now)
        self._update_mood_from_text(text)
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
                seconds=self.persona.nudge_policy.idle_after_seconds
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
        template_index = min(
            self.nudge_count,
            len(self.persona.nudge_policy.templates) - 1,
        )
        return self.persona.nudge_policy.templates[template_index]

    def consume_nudge(self, now: datetime | None = None) -> str:
        now = now or utc_now()
        text = self.next_nudge_text()
        self.messages.append(ChatMessage(role="assistant", text=text, created_at=now))
        self.nudge_count += 1
        self.nudge_due_at = now + timedelta(
            seconds=self.persona.nudge_policy.follow_up_after_seconds
        )
        return text

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
            seconds=self.persona.nudge_policy.idle_after_seconds
        )
        self.initiative_count += 1
        self.schedule_initiative(now)
        return text

    def _update_affection(self, text: str, now: datetime) -> None:
        positive_tokens = ("고마워", "좋아", "보고싶", "재밌", "설레", "사랑", "예쁘", "최고", "행복", "귀여")
        negative_tokens = ("짜증", "싫어", "별로", "귀찮", "몰라", "됐어", "ㅋ")
        if any(token in text for token in positive_tokens):
            self.affection_score = min(100, self.affection_score + 5)
        if any(token in text for token in negative_tokens):
            self.affection_score = max(0, self.affection_score - 3)
        if len(text.strip()) <= 2:
            self.affection_score = max(0, self.affection_score - 1)
        if self.last_activity_at:
            gap = (now - self.last_activity_at).total_seconds()
            if gap > 300:
                decay = min(8, int(gap / 300))
                self.affection_score = max(0, self.affection_score - decay)

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
