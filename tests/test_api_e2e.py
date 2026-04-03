from http import HTTPStatus
from datetime import timedelta

from girlfriend_generator.api import RomanceService
from girlfriend_generator.engine import utc_now
from girlfriend_generator.server import route_request


def test_api_end_to_end_compile_message_and_tick() -> None:
    service = RomanceService()

    status, compiled = route_request(
        service,
        "POST",
        "/v1/context/compile",
        {
            "name": "서윤",
            "age": 27,
            "relationship_mode": "girlfriend",
            "notes": "성수에서 프로덕트 디자이너로 일하고 사진 산책과 야식을 좋아한다. 안부를 세심하게 묻는 사람에게 약하다.",
            "links": ["https://instagram.com/seoyun.example"],
            "snippets": ["자기야 뭐 해?", "오늘은 좀 보고 싶네 ㅎㅎ"],
        },
    )
    assert status == HTTPStatus.CREATED
    persona_id = compiled["persona_id"]
    assert compiled["persona"]["evidence"]

    status, created = route_request(
        service,
        "POST",
        "/v1/sessions",
        {"persona_id": persona_id},
    )
    assert status == HTTPStatus.CREATED
    session_id = created["session_id"]
    assert created["state"]["message_count"] >= 1

    status, replied = route_request(
        service,
        "POST",
        f"/v1/sessions/{session_id}/message",
        {"text": "오늘 코딩하다가 네 생각 났어.", "provider": "heuristic"},
    )
    assert status == HTTPStatus.OK
    assert replied["reply"]["text"]
    assert replied["state"]["awaiting_user_reply"] is True
    assert replied["state"]["messages"][-2]["role"] == "user"
    assert replied["state"]["messages"][-1]["role"] == "assistant"

    status, nudged = route_request(
        service,
        "POST",
        f"/v1/sessions/{session_id}/tick",
        {"advance_seconds": 120, "provider": "heuristic"},
    )
    assert status == HTTPStatus.OK
    assert nudged["event_type"] == "nudge"
    assert nudged["text"]

    status, created2 = route_request(
        service,
        "POST",
        "/v1/sessions",
        {"persona_id": persona_id, "bootstrap": False},
    )
    assert status == HTTPStatus.CREATED
    quiet_session_id = created2["session_id"]

    state = service.sessions[quiet_session_id]
    state.initiative_due_at = utc_now() - timedelta(seconds=1)
    status, initiative = route_request(
        service,
        "POST",
        f"/v1/sessions/{quiet_session_id}/tick",
        {"provider": "heuristic"},
    )
    assert status == HTTPStatus.OK
    assert initiative["event_type"] == "initiative"
    assert initiative["text"]

    status, state_payload = route_request(
        service,
        "GET",
        f"/v1/sessions/{quiet_session_id}/state",
        {},
    )
    assert status == HTTPStatus.OK
    assert state_payload["message_count"] >= 1
    assert state_payload["context_summary"]
