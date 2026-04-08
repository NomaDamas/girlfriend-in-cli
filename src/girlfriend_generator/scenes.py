"""Scene System: LLM-driven location changes with report cards."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import ChatMessage, MoodType, Persona


@dataclass(slots=True)
class Scene:
    name: str
    description: str
    mood_hint: str = "neutral"
    bgm_mood: str = "neutral"
    min_affection: int = 0


@dataclass(slots=True)
class EvaluatorResult:
    should_move: bool
    next_scene: str = ""
    proposal_line: str = ""


@dataclass(slots=True)
class ReportCard:
    highlights: list[str]
    advice: str
    scene_summary: str
    affection: int
    mood: str
    next_scene_name: str = ""
    next_scene_desc: str = ""


@dataclass
class SceneState:
    current_scene: Scene | None = None
    user_msg_count: int = 0
    rejection_count: int = 0
    scene_history: list[str] = field(default_factory=list)
    pending_proposal: EvaluatorResult | None = None
    eval_interval: int = 7
    max_rejections: int = 3

    def should_evaluate(self) -> bool:
        if self.rejection_count >= self.max_rejections:
            return False
        return self.user_msg_count > 0 and self.user_msg_count % self.eval_interval == 0

    def record_user_message(self) -> None:
        self.user_msg_count += 1

    def accept_transition(self, new_scene: Scene) -> None:
        if self.current_scene:
            self.scene_history.append(self.current_scene.name)
        self.current_scene = new_scene
        self.user_msg_count = 0
        self.rejection_count = 0
        self.pending_proposal = None

    def reject_transition(self) -> None:
        self.rejection_count += 1
        self.pending_proposal = None


def load_scenes(scenes_dir: Path | None = None) -> list[Scene]:
    """Load scenes from scenes/ directory."""
    if scenes_dir is None:
        from .paths import project_root
        root = project_root()
        if root is None:
            return []
        scenes_dir = root / "scenes"

    if not scenes_dir.is_dir():
        return []

    scenes = []
    for path in sorted(scenes_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            scenes.append(Scene(
                name=data.get("name", path.stem),
                description=data.get("description", ""),
                mood_hint=data.get("mood_hint", "neutral"),
                bgm_mood=data.get("bgm_mood", "neutral"),
                min_affection=data.get("min_affection", 0),
            ))
        except Exception:
            continue
    return scenes


def available_scenes(
    all_scenes: list[Scene],
    affection: int,
    current_name: str = "",
    rejected_names: list[str] | None = None,
) -> list[Scene]:
    """Filter scenes that the player can visit now."""
    rejected = set(rejected_names or [])
    return [
        s for s in all_scenes
        if s.min_affection <= affection
        and s.name != current_name
        and s.name not in rejected
    ]


def build_evaluator_prompt(
    persona: Persona,
    current_scene: Scene | None,
    affection: int,
    mood: MoodType,
    recent_messages: list[ChatMessage],
    available: list[Scene],
) -> str:
    """Build the evaluator LLM prompt."""
    scene_name = current_scene.name if current_scene else "없음 (시작)"
    scene_list = ", ".join(f"{s.name}({s.description[:20]})" for s in available)
    history = "\n".join(f"{m.role}: {m.text}" for m in recent_messages[-8:])

    return (
        "You are a scene evaluator for a Korean romance simulation game. "
        "Based on the conversation flow, decide if it's time to move to a new location.\n\n"
        f"Current location: {scene_name}\n"
        f"Affection: {affection}/100\n"
        f"Mood: {mood}\n"
        f"Persona: {persona.name} ({persona.relationship_mode})\n"
        f"Available locations: {scene_list}\n\n"
        f"Recent conversation:\n{history}\n\n"
        "Respond with ONLY valid JSON (no markdown, no explanation):\n"
        '{"should_move": true/false, "next_scene": "장소이름", "proposal_line": "자연스러운 제안 대사 (한국어)"}\n\n'
        "Rules:\n"
        "- should_move=true only if the conversation has reached a natural pause or topic change\n"
        "- proposal_line must sound like the persona naturally suggesting to go somewhere\n"
        "- If should_move=false, set next_scene and proposal_line to empty strings\n"
    )


def build_report_prompt(
    persona: Persona,
    current_scene: Scene,
    next_scene: Scene,
    messages: list[ChatMessage],
    affection: int,
    mood: MoodType,
) -> str:
    """Build the report card + scene summary LLM prompt."""
    history = "\n".join(f"{m.role}: {m.text}" for m in messages if m.role != "system")

    return (
        "You are generating a scene transition report for a Korean romance simulation.\n\n"
        f"Leaving: {current_scene.name} ({current_scene.description})\n"
        f"Going to: {next_scene.name} ({next_scene.description})\n"
        f"Persona: {persona.name}, {persona.relationship_mode}\n"
        f"Affection: {affection}/100, Mood: {mood}\n\n"
        f"Conversation in this scene:\n{history}\n\n"
        "Respond with ONLY valid JSON (no markdown):\n"
        "{\n"
        '  "highlights": ["대화 하이라이트 1", "대화 하이라이트 2", "대화 하이라이트 3"],\n'
        '  "advice": "다음 장소에서의 관계 조언 (한국어, 1-2문장)",\n'
        '  "scene_summary": "이 장소에서의 대화 요약 (한국어, 2-3문장, 다음 장소 context로 사용됨)"\n'
        "}\n"
    )


def parse_evaluator_response(text: str) -> EvaluatorResult:
    """Parse JSON from evaluator LLM response."""
    try:
        # Strip markdown code blocks if present
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean
            clean = clean.rsplit("```", 1)[0]
        data = json.loads(clean)
        return EvaluatorResult(
            should_move=bool(data.get("should_move", False)),
            next_scene=str(data.get("next_scene", "")),
            proposal_line=str(data.get("proposal_line", "")),
        )
    except (json.JSONDecodeError, KeyError):
        return EvaluatorResult(should_move=False)


def parse_report_response(text: str, affection: int, mood: str, next_scene: Scene) -> ReportCard:
    """Parse JSON from report card LLM response."""
    try:
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean
            clean = clean.rsplit("```", 1)[0]
        data = json.loads(clean)
        return ReportCard(
            highlights=list(data.get("highlights", [])),
            advice=str(data.get("advice", "")),
            scene_summary=str(data.get("scene_summary", "")),
            affection=affection,
            mood=mood,
            next_scene_name=next_scene.name,
            next_scene_desc=next_scene.description,
        )
    except (json.JSONDecodeError, KeyError):
        return ReportCard(
            highlights=["(요약 생성 실패)"],
            advice="자연스럽게 대화를 이어가보세요.",
            scene_summary="이전 장소에서의 대화.",
            affection=affection,
            mood=mood,
            next_scene_name=next_scene.name,
            next_scene_desc=next_scene.description,
        )


def render_report_card(report: ReportCard) -> str:
    """Render report card as Rich markup string for Panel."""
    hearts = "❤️" * min(5, report.affection // 20) + "🤍" * max(0, 5 - report.affection // 20)
    bar_filled = report.affection // 5
    bar_empty = 20 - bar_filled

    lines = [
        "",
        f"  [bold]Affection[/bold]  {hearts}  [bold]{report.affection}[/bold]/100",
        f"  [red]{'█' * bar_filled}[/red][dim]{'░' * bar_empty}[/dim]",
        "",
        "  [bold]Highlights[/bold]",
    ]
    for h in report.highlights[:3]:
        lines.append(f"  [cyan]•[/cyan] {h}")
    lines += [
        "",
        f"  [bold]Advice[/bold]",
        f"  [yellow]{report.advice}[/yellow]",
        "",
        f"  [bold]Next[/bold]  [magenta]{report.next_scene_name}[/magenta]",
        f"  [dim]{report.next_scene_desc}[/dim]",
        "",
    ]
    return "\n".join(lines)
