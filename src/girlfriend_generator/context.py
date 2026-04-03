from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from .models import (
    ContextBundle,
    ContextEvidence,
    InitiativeProfile,
    NudgePolicy,
    Persona,
    StyleProfile,
    TypingProfile,
)


INTEREST_KEYWORDS: dict[str, tuple[str, ...]] = {
    "전시회": ("전시", "gallery", "museum", "exhibition"),
    "카페": ("카페", "cafe", "coffee"),
    "러닝": ("러닝", "run", "running"),
    "사진": ("사진", "photo", "camera"),
    "음악": ("음악", "music", "playlist", "band"),
    "브런치": ("브런치", "brunch"),
    "야식": ("야식", "late-night", "snack"),
    "여행": ("여행", "trip", "travel"),
    "디자인": ("디자인", "design", "figma", "visual"),
}

SOFT_SPOT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "세심한 안부": ("안부", "check-in", "세심"),
    "센스 있는 장난": ("장난", "tease", "joke", "playful"),
    "직진하지만 과하지 않은 표현": ("직진", "straightforward", "honest"),
    "구체적인 데이트 제안": ("데이트", "plan", "weekend"),
}


def build_context_bundle(payload: dict) -> ContextBundle:
    return ContextBundle(
        name=payload["name"],
        age=int(payload["age"]),
        relationship_mode=payload.get("relationship_mode", "crush"),
        notes=payload.get("notes", "").strip(),
        links=list(payload.get("links", [])),
        snippets=[item.strip() for item in payload.get("snippets", []) if item.strip()],
        boundaries=list(payload.get("boundaries", [])),
        requested_traits=list(payload.get("requested_traits", [])),
    )


def compile_persona(bundle: ContextBundle) -> Persona:
    corpus = " ".join([bundle.notes, *bundle.links, *bundle.snippets, *bundle.requested_traits])
    lowered = corpus.lower()
    interests = _extract_interests(lowered)
    soft_spots = _extract_soft_spots(lowered)
    evidence = _build_evidence(bundle)
    style_profile = _derive_style_profile(bundle)
    initiative_profile = _derive_initiative_profile(bundle)
    background = _build_background(bundle, interests)
    situation = _build_situation(bundle)
    texting_style = _build_texting_style(style_profile, bundle)
    greeting = _build_greeting(bundle)
    boundaries = bundle.boundaries or _default_boundaries(bundle.relationship_mode)
    provider_hint = _build_provider_hint(style_profile, initiative_profile)
    persona = Persona(
        name=bundle.name,
        age=bundle.age,
        relationship_mode=bundle.relationship_mode,
        background=background,
        situation=situation,
        texting_style=texting_style,
        interests=interests,
        soft_spots=soft_spots,
        boundaries=boundaries,
        greeting=greeting,
        provider_system_hint=provider_hint,
        context_summary=_build_context_summary(bundle, interests, soft_spots),
        style_profile=style_profile,
        initiative_profile=initiative_profile,
        evidence=evidence,
        typing=TypingProfile(
            min_seconds=0.9 if bundle.relationship_mode == "girlfriend" else 1.0,
            max_seconds=3.4 if style_profile.message_length == "short" else 3.9,
        ),
        nudge_policy=_derive_nudge_policy(bundle),
    )
    persona.validate()
    return persona


def persona_to_dict(persona: Persona) -> dict:
    data = asdict(persona)
    return data


def _extract_interests(corpus: str) -> list[str]:
    detected = [
        label for label, keywords in INTEREST_KEYWORDS.items() if any(token in corpus for token in keywords)
    ]
    if not detected:
        return ["카페", "산책", "음악"]
    return detected[:4]


def _extract_soft_spots(corpus: str) -> list[str]:
    detected = [
        label for label, keywords in SOFT_SPOT_KEYWORDS.items() if any(token in corpus for token in keywords)
    ]
    if not detected:
        return ["세심한 안부", "센스 있는 장난", "구체적인 데이트 제안"]
    return detected[:3]


def _build_evidence(bundle: ContextBundle) -> list[ContextEvidence]:
    evidence: list[ContextEvidence] = []
    for link in bundle.links:
        evidence.append(
            ContextEvidence(
                source_type="link",
                label="external context",
                value=link,
                confidence=0.62,
                tags=_tag_link(link),
            )
        )
    for snippet in bundle.snippets:
        evidence.append(
            ContextEvidence(
                source_type="snippet",
                label="style sample",
                value=snippet,
                confidence=0.78,
                tags=_tag_snippet(snippet),
            )
        )
    if bundle.notes:
        evidence.append(
            ContextEvidence(
                source_type="notes",
                label="user notes",
                value=bundle.notes,
                confidence=0.82,
                tags=["manual-context"],
            )
        )
    return evidence


def _derive_style_profile(bundle: ContextBundle) -> StyleProfile:
    snippets = bundle.snippets
    corpus = " ".join(snippets + [bundle.notes]).lower()
    exclamation_count = corpus.count("!") + corpus.count("ㅋ")
    emoji_hits = sum(token in corpus for token in (":)", "ㅎㅎ", "ㅠ", "🥺", "❤️"))
    average_length = sum(len(item) for item in snippets) / len(snippets) if snippets else 28
    message_length = "short" if average_length < 20 else "short-medium" if average_length < 45 else "medium"
    emoji_level = "medium" if emoji_hits >= 2 else "low"
    warmth = 0.6 + min(0.25, emoji_hits * 0.05)
    teasing = 0.55 + min(0.25, exclamation_count * 0.02)
    directness = 0.5 + (0.12 if "보고싶" in corpus or "좋아" in corpus else 0.0)
    signature = []
    for token in ("자기야", "뭐 해", "ㅋㅋ", "ㅎㅎ", "아니", "진짜"):
        if token in corpus:
            signature.append(token)
    return StyleProfile(
        warmth=round(min(warmth, 0.95), 2),
        teasing=round(min(teasing, 0.92), 2),
        directness=round(min(directness, 0.9), 2),
        message_length=message_length,
        emoji_level=emoji_level,
        signature_phrases=signature[:4],
    )


def _derive_initiative_profile(bundle: ContextBundle) -> InitiativeProfile:
    if bundle.relationship_mode == "girlfriend":
        opener_templates = [
            "자기야, 잠깐만 체크인. 지금 뭐 하고 있어?",
            "뭐야, 코딩하다가 나 생각은 했어?",
            "갑자기 네 생각 나서 먼저 톡해봤어.",
        ]
        follow_ups = [
            "오늘 텐션 어떤지 궁금해서 먼저 왔지.",
            "답장 늦으면 살짝 서운하긴 한데 그래도 기다려볼게.",
        ]
        return InitiativeProfile(
            min_interval_seconds=900,
            max_interval_seconds=2700,
            spontaneity=0.74,
            opener_templates=opener_templates,
            follow_up_templates=follow_ups,
        )
    opener_templates = [
        "갑자기 네 톤 생각나서 먼저 말 걸어봤어.",
        "오늘은 네가 먼저 올 줄 알았는데 내가 와버렸네.",
        "이 시간대엔 네가 무슨 말 할지 좀 궁금해져.",
    ]
    follow_ups = [
        "답장 없으면 좀 신경 쓰일 것 같긴 해.",
        "뜸 들이는 거면 그것도 나쁘진 않은데 너무 길면 서운해.",
    ]
    return InitiativeProfile(
        min_interval_seconds=1800,
        max_interval_seconds=5400,
        spontaneity=0.58,
        opener_templates=opener_templates,
        follow_up_templates=follow_ups,
    )


def _build_background(bundle: ContextBundle, interests: list[str]) -> str:
    notes = bundle.notes or "사용자가 직접 입력한 설명과 링크를 바탕으로 컴파일된 성인 여성 페르소나다."
    interest_text = ", ".join(interests[:3])
    return f"{notes} 관심사는 주로 {interest_text} 쪽으로 정리된다."


def _build_situation(bundle: ContextBundle) -> str:
    if bundle.relationship_mode == "girlfriend":
        return "이미 연인 관계이며, 일상적인 체크인과 가벼운 장난이 자주 오가는 상태다."
    return "호감이 형성된 상태에서 대화를 통해 친밀도를 높여 가는 썸 단계다."


def _build_texting_style(style_profile: StyleProfile, bundle: ContextBundle) -> str:
    tone = "짧고 리듬감 있게" if style_profile.message_length != "medium" else "적당한 길이로 감정선을 담아"
    emoji = "이모지는 거의 쓰지 않고" if style_profile.emoji_level == "low" else "가끔 이모지와 웃음 표현을 섞고"
    return f"{tone} 말한다. {emoji} 따뜻함 {style_profile.warmth}, 장난기 {style_profile.teasing}, 직진도 {style_profile.directness} 수준으로 반응한다."


def _build_greeting(bundle: ContextBundle) -> str:
    if bundle.relationship_mode == "girlfriend":
        return f"{bundle.name} 모드 체크인. 오늘은 어떤 분위기로 얘기하고 싶어?"
    return f"{bundle.name} 페르소나 준비됐어. 오늘은 어떤 식으로 흐름을 잡아볼까?"


def _build_provider_hint(style_profile: StyleProfile, initiative_profile: InitiativeProfile) -> str:
    return (
        "Keep the persona consistent across turns. "
        f"Warmth={style_profile.warmth}, teasing={style_profile.teasing}, directness={style_profile.directness}. "
        f"Initiative spontaneity={initiative_profile.spontaneity}. "
        "Use short, believable Korean chat phrasing and preserve the compiled context."
    )


def _build_context_summary(
    bundle: ContextBundle,
    interests: list[str],
    soft_spots: list[str],
) -> str:
    interest_text = ", ".join(interests[:3])
    soft_spot_text = ", ".join(soft_spots[:2])
    return (
        f"Compiled from {len(bundle.links)} link(s), {len(bundle.snippets)} snippet(s), and manual notes. "
        f"Likely interests: {interest_text}. Soft spots: {soft_spot_text}."
    )


def _derive_nudge_policy(bundle: ContextBundle) -> NudgePolicy:
    if bundle.relationship_mode == "girlfriend":
        return NudgePolicy(
            idle_after_seconds=28,
            follow_up_after_seconds=55,
            max_nudges=2,
            templates=[
                "왜 답장 안 해, 나 은근 기다리고 있었는데.",
                "이쯤이면 내가 먼저 삐진 척 해도 되지?",
            ],
        )
    return NudgePolicy(
        idle_after_seconds=40,
        follow_up_after_seconds=80,
        max_nudges=2,
        templates=[
            "갑자기 조용해지니까 살짝 신경 쓰이네.",
            "뜸 들이는 거야? 아니면 내가 먼저 또 와야 해?",
        ],
    )


def _default_boundaries(relationship_mode: str) -> list[str]:
    base = ["지나치게 선정적인 흐름", "감정 강요", "집착성 압박"]
    if relationship_mode == "girlfriend":
        return ["무성의한 단답", *base]
    return base


def _tag_link(link: str) -> list[str]:
    lowered = link.lower()
    tags = []
    if "instagram" in lowered or "insta" in lowered:
        tags.append("sns")
        tags.append("instagram")
    if "x.com" in lowered or "twitter" in lowered:
        tags.append("sns")
        tags.append("x")
    if "youtube" in lowered:
        tags.append("video")
    if not tags:
        tags.append("link")
    return tags


def _tag_snippet(snippet: str) -> list[str]:
    lowered = snippet.lower()
    tags = ["style"]
    if "ㅋㅋ" in snippet or "ㅎㅎ" in snippet:
        tags.append("playful")
    if "?" in snippet:
        tags.append("curious")
    if "보고싶" in lowered or "miss" in lowered:
        tags.append("affection")
    return tags
