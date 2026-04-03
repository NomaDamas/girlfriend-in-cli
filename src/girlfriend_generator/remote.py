from __future__ import annotations

import json
from urllib import request

from .models import ChatMessage, Persona, ProviderReply
from .personas import persona_from_pack


def fetch_remote_persona(base_url: str, persona_id: str) -> Persona:
    payload = _get_json(f"{base_url.rstrip('/')}/v1/persona/{persona_id}")
    return persona_from_pack(payload)


class RemoteProvider:
    def __init__(self, base_url: str, persona_id: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.persona_id = persona_id

    def generate_reply(
        self,
        persona: Persona,
        history: list[ChatMessage],
        user_text: str,
        affection_score: int,
    ) -> ProviderReply:
        payload = _post_json(
            f"{self.base_url}/v1/chat/respond",
            {
                "persona_id": self.persona_id,
                "history": [_message_to_dict(item) for item in history],
                "user_message": user_text,
                "affection_score": affection_score,
            },
        )
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
    ) -> str:
        payload = _post_json(
            f"{self.base_url}/v1/chat/initiate",
            {
                "persona_id": self.persona_id,
                "history": [_message_to_dict(item) for item in history],
                "affection_score": affection_score,
            },
        )
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
