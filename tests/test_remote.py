from datetime import datetime, timezone

from girlfriend_generator.models import ChatMessage
from girlfriend_generator.personas import persona_from_pack
from girlfriend_generator.remote import RemoteProvider


def test_persona_from_server_pack_maps_to_local_persona() -> None:
    pack = {
        "persona_id": "persona_1",
        "display_name": "유나",
        "summary": "연인 관계에서 작동하는 성인 페르소나다.",
        "identity": {
            "background": "성수에서 일하는 디자이너",
            "interests": ["전시회", "야식"],
            "boundaries": ["과한 집착"],
        },
        "style": {
            "tone_keywords": ["다정한", "장난기 있는"],
            "sample_lines": ["왜 답장 안 해?", "자기야 뭐 해?"],
        },
        "relationship": {
            "mode": "girlfriend",
            "soft_spots": ["세심한 안부"],
        },
    }

    persona = persona_from_pack(pack)

    assert persona.name == "유나"
    assert persona.relationship_mode == "girlfriend"
    assert persona.interests == ["전시회", "야식"]


def test_remote_provider_uses_runtime_endpoints(monkeypatch) -> None:
    called = []

    def fake_post(url: str, payload: dict) -> dict:
        called.append((url, payload))
        if url.endswith("/respond"):
            return {
                "text": "왜 갑자기 조용해졌어?",
                "typing_delay_ms": 900,
                "emotion": "teasing",
            }
        return {"text": "먼저 톡해봤어."}

    monkeypatch.setattr("girlfriend_generator.remote._post_json", fake_post)
    provider = RemoteProvider("http://127.0.0.1:8787", "persona_1")
    message = ChatMessage(
        role="user",
        text="오늘 뭐 해?",
        created_at=datetime.now(timezone.utc),
    )

    reply = provider.generate_reply(persona=None, history=[message], user_text="오늘 뭐 해?", affection_score=50)  # type: ignore[arg-type]
    initiative = provider.generate_initiative(persona=None, history=[message], affection_score=50)  # type: ignore[arg-type]

    assert reply.text
    assert initiative == "먼저 톡해봤어."
    assert called[0][0].endswith("/v1/chat/respond")
    assert called[1][0].endswith("/v1/chat/initiate")
