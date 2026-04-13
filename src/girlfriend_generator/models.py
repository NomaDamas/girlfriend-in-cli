from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

MessageRole = Literal["user", "assistant", "system"]
MoodType = Literal["neutral", "happy", "playful", "sulky", "excited", "worried", "flirty"]

MOOD_EMOJI: dict[str, str] = {
    "neutral": "😐",
    "happy": "😊",
    "playful": "😜",
    "sulky": "😒",
    "excited": "🥰",
    "worried": "😟",
    "flirty": "💕",
}


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
class ContextEvidence:
    source_type: str
    label: str
    value: str
    confidence: float = 0.6
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class StyleProfile:
    warmth: float = 0.7
    teasing: float = 0.6
    directness: float = 0.55
    message_length: str = "short-medium"
    emoji_level: str = "low"
    signature_phrases: list[str] = field(default_factory=list)


@dataclass(slots=True)
class InitiativeProfile:
    min_interval_seconds: int = 900
    max_interval_seconds: int = 3600
    spontaneity: float = 0.55
    opener_templates: list[str] = field(default_factory=list)
    follow_up_templates: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ContextBundle:
    name: str
    age: int
    relationship_mode: str
    notes: str = ""
    links: list[str] = field(default_factory=list)
    snippets: list[str] = field(default_factory=list)
    boundaries: list[str] = field(default_factory=list)
    requested_traits: list[str] = field(default_factory=list)


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
    context_summary: str = ""
    style_profile: StyleProfile = field(default_factory=StyleProfile)
    initiative_profile: InitiativeProfile = field(default_factory=InitiativeProfile)
    evidence: list[ContextEvidence] = field(default_factory=list)
    typing: TypingProfile = field(default_factory=TypingProfile)
    nudge_policy: NudgePolicy = field(default_factory=NudgePolicy)
    difficulty: str = "normal"  # easy, normal, hard, nightmare
    special_mode: str = ""  # "", "yandere"

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
    text: str  # Clean reply text (parsed from JSON)
    typing_seconds: float
    trace_note: str
    affection_delta: int = 0
    mood: str = ""
    memory_update: str = ""
    internal_thought: str = ""
    coach_feedback: str = ""
    coach_strength: str = ""
    coach_weakness: str = ""
    coach_charm_point: str = ""
    coach_charm_type: str = ""
    coach_charm_feedback: str = ""
    should_burst: bool = False
    burst_messages: list[str] = field(default_factory=list)
    next_proactive_seconds: int | None = None
    propose_scene: str = ""


@dataclass(slots=True)
class MoodState:
    current: MoodType = "neutral"
    intensity: float = 0.5  # 0.0 to 1.0
    turns_in_mood: int = 0

    def shift(self, new_mood: MoodType, intensity: float = 0.6) -> None:
        if new_mood == self.current:
            self.intensity = min(1.0, self.intensity + 0.1)
            self.turns_in_mood += 1
        else:
            self.current = new_mood
            self.intensity = max(0.3, intensity)
            self.turns_in_mood = 0

    def decay(self) -> None:
        self.turns_in_mood += 1
        if self.turns_in_mood > 4 and self.current != "neutral":
            self.current = "neutral"
            self.intensity = 0.5
            self.turns_in_mood = 0


@dataclass(slots=True)
class TickResult:
    event_type: str
    text: str | None
    trace_note: str


@dataclass(slots=True)
class RuntimeTrace:
    persona_path: Path
    provider_name: str
    provider_model: str | None
    performance_mode: str
    voice_output_name: str
    voice_input_name: str
    remote_persona_ref: str | None = None
    remote_persona_version: int | None = None
    remote_emotion: str | None = None
    remote_initiative_reason: str | None = None
    remote_memory_hits: list[str] = field(default_factory=list)
    ecc_mode: str = "project-local"
    skills_root: str = ".agents/skills"
    uses_global_codex_defaults: bool = False
    pending_reply_kind: str = "idle"
    pending_nudge_in: int | None = None
    pending_initiative_in: int | None = None
    status_line: str = "Ready"
