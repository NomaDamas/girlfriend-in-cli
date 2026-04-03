from __future__ import annotations

import uuid

from .context import build_context_bundle, compile_persona, persona_to_dict
from .engine import ConversationSession, utc_now
from .models import Persona
from .providers import ProviderConfig, build_provider


class RomanceService:
    def __init__(self) -> None:
        self.personas: dict[str, Persona] = {}
        self.sessions: dict[str, ConversationSession] = {}
        self.session_personas: dict[str, str] = {}

    def compile_context(self, payload: dict) -> dict:
        bundle = build_context_bundle(payload)
        persona = compile_persona(bundle)
        persona_id = f"persona_{uuid.uuid4().hex[:10]}"
        self.personas[persona_id] = persona
        return {
            "persona_id": persona_id,
            "persona": persona_to_dict(persona),
        }

    def create_session(self, payload: dict) -> dict:
        persona = self._resolve_persona(payload)
        session = ConversationSession(persona=persona)
        if payload.get("bootstrap", True):
            session.bootstrap()
        else:
            session.schedule_initiative()
        session_id = f"session_{uuid.uuid4().hex[:10]}"
        self.sessions[session_id] = session
        for persona_id, candidate in self.personas.items():
            if candidate is persona:
                self.session_personas[session_id] = persona_id
                break
        return {
            "session_id": session_id,
            "state": self._session_state(session_id),
        }

    def post_message(self, session_id: str, payload: dict) -> dict:
        session = self._get_session(session_id)
        provider = build_provider(
            ProviderConfig(
                name=payload.get("provider", "heuristic"),
                model=payload.get("model"),
                performance_mode=payload.get("performance", "turbo"),
            )
        )
        text = str(payload["text"]).strip()
        session.add_user_message(text)
        reply = provider.generate_reply(
            persona=session.persona,
            history=session.recent_history(),
            user_text=text,
            affection_score=session.affection_score,
        )
        session.add_assistant_message(reply.text)
        return {
            "reply": {
                "text": reply.text,
                "typing_seconds": reply.typing_seconds,
                "trace_note": reply.trace_note,
            },
            "state": self._session_state(session_id),
        }

    def tick(self, session_id: str, payload: dict) -> dict:
        session = self._get_session(session_id)
        provider = build_provider(
            ProviderConfig(
                name=payload.get("provider", "heuristic"),
                model=payload.get("model"),
                performance_mode=payload.get("performance", "turbo"),
            )
        )
        advance_seconds = int(payload.get("advance_seconds", 0))
        if advance_seconds > 0:
            result = session.fast_forward(seconds=advance_seconds, provider=provider)
        else:
            result = session.tick(provider=provider, now=utc_now())
        return {
            "event_type": result.event_type,
            "text": result.text,
            "trace_note": result.trace_note,
            "state": self._session_state(session_id),
        }

    def get_state(self, session_id: str) -> dict:
        return self._session_state(session_id)

    def _resolve_persona(self, payload: dict) -> Persona:
        persona_id = payload.get("persona_id")
        if persona_id:
            try:
                return self.personas[persona_id]
            except KeyError as exc:
                raise KeyError(f"Unknown persona_id: {persona_id}") from exc
        if "persona" in payload:
            bundle = build_context_bundle(payload["persona"])
            return compile_persona(bundle)
        raise KeyError("persona_id or persona payload is required")

    def _get_session(self, session_id: str) -> ConversationSession:
        try:
            return self.sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"Unknown session_id: {session_id}") from exc

    def _session_state(self, session_id: str) -> dict:
        session = self._get_session(session_id)
        messages = [
            {
                "role": message.role,
                "text": message.text,
                "created_at": message.created_at.isoformat(),
            }
            for message in session.messages
        ]
        return {
            "session_id": session_id,
            "persona_name": session.persona.name,
            "relationship_mode": session.persona.relationship_mode,
            "affection_score": session.affection_score,
            "awaiting_user_reply": session.awaiting_user_reply,
            "nudge_in": session.seconds_until_nudge(),
            "initiative_in": session.seconds_until_initiative(),
            "message_count": len(session.messages),
            "messages": messages[-8:],
            "context_summary": session.persona.context_summary,
        }
