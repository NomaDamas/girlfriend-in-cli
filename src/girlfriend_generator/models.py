from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

MessageRole = Literal["user", "assistant", "system"]


@dataclass(slots=True)
class TypingProfile:
    min_seconds: float = 1.2
    max_seconds: float = 3.8


@dataclass(slots=True)
class NudgePolicy:
    idle_after_seconds: int = 45
    follow_up_after_seconds: int = 90
    max_nudges: int = 2
    templates: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Persona:
    name: str
    age: int
    relationship_mode: str
    background: str
    situation: str
    texting_style: str
    interests: list[str]
    soft_spots: list[str]
    boundaries: list[str]
    greeting: str
    accent_color: str = "magenta"
    provider_system_hint: str = ""
    typing: TypingProfile = field(default_factory=TypingProfile)
    nudge_policy: NudgePolicy = field(default_factory=NudgePolicy)

    def validate(self) -> None:
        if self.age < 20:
            raise ValueError("Personas must be explicitly adult.")
        if not self.nudge_policy.templates:
            raise ValueError("Persona must define at least one nudge template.")


@dataclass(slots=True)
class ChatMessage:
    role: MessageRole
    text: str
    created_at: datetime


@dataclass(slots=True)
class ProviderReply:
    text: str
    typing_seconds: float
    trace_note: str


@dataclass(slots=True)
class RuntimeTrace:
    persona_path: Path
    provider_name: str
    provider_model: str | None
    performance_mode: str
    voice_output_name: str
    voice_input_name: str
    ecc_mode: str = "project-local"
    skills_root: str = ".agents/skills"
    uses_global_codex_defaults: bool = False
    pending_reply_kind: str = "idle"
    pending_nudge_in: int | None = None
    status_line: str = "Ready"
