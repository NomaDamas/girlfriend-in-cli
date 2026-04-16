from __future__ import annotations

import json
from urllib import request
from urllib.parse import quote

from .models import ChatMessage, MoodType, Persona, ProviderReply
from .personas import persona_from_pack


def fetch_remote_persona(base_url: str, persona_id: str) -> Persona:
    payload = _get_json(f"{base_url.rstrip('/')}/v1/persona/{persona_id}")
    return persona_from_pack(payload)


def fetch_remote_persona_by_slug(base_url: str, slug: str) -> Persona:
    payload = _get_json(f"{base_url.rstrip('/')}/v1/persona/by-slug/{quote(slug)}")
    return persona_from_pack(payload)


def compile_remote_persona(
    base_url: str,
    display_name: str,
    age: int,
    relationship_mode: str,
    context_notes: str = "",
    context_links: list[str] | None = None,
    context_snippets: list[str] | None = None,
) -> dict:
    queued = _post_json(
        f"{base_url.rstrip('/')}/v1/persona/ingest",
        {
            "name_hint": display_name,
            "manual_description": context_notes,
            "links": context_links or [],
            "source_mode": "assisted" if context_links else "manual",
        },
    )
    ingestion = _get_json(
        f"{base_url.rstrip('/')}/v1/persona/ingest/{queued['ingestion_id']}"
    )
    return _post_json(
        f"{base_url.rstrip('/')}/v1/persona/compile",
        {
            "ingestion_id": queued["ingestion_id"],
            "display_name": display_name,
            "relationship_mode": relationship_mode,
            "confirmed_facts": ingestion.get("fact_candidates", []),
            "confirmed_style": [
                *ingestion.get("style_candidates", []),
                *(context_snippets or []),
            ],
            "manual_description": context_notes,
            "links": context_links or [],
            "age": age,
        },
    )


def list_remote_personas(base_url: str) -> list[dict]:
    payload = _get_json(f"{base_url.rstrip('/')}/v1/personas")
    return list(payload.get("items", []))


class RemoteProvider:
    def __init__(self, base_url: str, persona_id: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.persona_id = persona_id
        self.last_trace: dict[str, object] = {}

    def generate_reply(
        self,
        persona: Persona,
        history: list[ChatMessage],
        user_text: str,
        affection_score: int,
        mood: MoodType = "neutral",
        **kwargs,
    ) -> ProviderReply:
        payload = _post_json(
            f"{self.base_url}/v1/chat/respond",
            {
                "persona_id": self.persona_id,
                "history": [_message_to_dict(item) for item in history],
                "user_message": user_text,
                "affection_score": affection_score,
                "mood": mood,
                "relationship_label": kwargs.get("relationship_label"),
                "relationship_summary": kwargs.get("relationship_summary"),
                "relationship_guidance": kwargs.get("relationship_guidance"),
                "dynamic_personality": kwargs.get("dynamic_personality"),
            },
        )
        self.last_trace = {
            "emotion": payload.get("emotion"),
            "initiative_reason": payload.get("initiative_reason"),
            "memory_hits": list(payload.get("memory_hits", [])),
            "persona_version": payload.get("persona_version"),
            "persona_ref": self.persona_id,
        }
        return ProviderReply(
            text=str(payload["text"]),
            typing_seconds=float(payload.get("typing_delay_ms", 800)) / 1000.0,
            trace_note=f"remote:{payload.get('emotion', 'reply')}",
        )

    def generate_initiative(
        self,
        persona: Persona,
        history: list[ChatMessage],
        affection_score: int,
        **kwargs,
    ) -> str:
        payload = _post_json(
            f"{self.base_url}/v1/chat/initiate",
            {
                "persona_id": self.persona_id,
                "history": [_message_to_dict(item) for item in history],
                "affection_score": affection_score,
                "relationship_label": kwargs.get("relationship_label"),
                "relationship_summary": kwargs.get("relationship_summary"),
            },
        )
        self.last_trace = {
            "emotion": None,
            "initiative_reason": payload.get("reason"),
            "memory_hits": [],
            "persona_version": payload.get("persona_version"),
            "persona_ref": self.persona_id,
        }
        return str(payload["text"])


def _message_to_dict(message: ChatMessage) -> dict:
    return {
        "role": message.role,
        "text": message.text,
        "created_at": message.created_at.isoformat(),
    }


def _get_json(url: str) -> dict:
    with request.urlopen(url) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))
