from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .models import ChatMessage, Persona


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

    def bootstrap(self, now: datetime | None = None) -> None:
        now = now or utc_now()
        self.add_assistant_message(self.persona.greeting, now=now, schedule_nudge=True)

    def add_user_message(self, text: str, now: datetime | None = None) -> None:
        now = now or utc_now()
        self.messages.append(ChatMessage(role="user", text=text, created_at=now))
        self.awaiting_user_reply = False
        self.nudge_due_at = None
        self.nudge_count = 0
        if any(token in text for token in ("고마워", "좋아", "보고싶", "재밌", "설레")):
            self.affection_score = min(100, self.affection_score + 6)

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
