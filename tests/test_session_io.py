from datetime import timezone
from pathlib import Path

from girlfriend_generator.engine import ConversationSession
from girlfriend_generator.personas import load_persona
from girlfriend_generator.session_io import export_session, load_session_snapshot, slugify


def test_export_session_writes_json_and_markdown(tmp_path: Path) -> None:
    persona = load_persona(Path("personas/wonyoung-idol.json"))
    session = ConversationSession(persona=persona)
    session.bootstrap()
    session.add_user_message("오늘은 네가 먼저 말 걸어줘서 좋네.")

    json_path, markdown_path = export_session(
        session_dir=tmp_path,
        persona=persona,
        messages=session.messages,
    )

    assert json_path.exists()
    assert markdown_path.exists()
    assert persona.name in markdown_path.read_text(encoding="utf-8")
    assert "오늘은 네가 먼저 말 걸어줘서 좋네." in markdown_path.read_text(
        encoding="utf-8"
    )


def test_export_session_uses_unique_filenames_on_repeat_export(tmp_path: Path) -> None:
    persona = load_persona(Path("personas/wonyoung-idol.json"))
    session = ConversationSession(persona=persona)
    session.bootstrap()
    session.add_user_message("같은 초에 두 번 저장해도 덮어쓰지 마.")

    first_json, first_markdown = export_session(
        session_dir=tmp_path,
        persona=persona,
        messages=session.messages,
    )
    second_json, second_markdown = export_session(
        session_dir=tmp_path,
        persona=persona,
        messages=session.messages,
    )

    assert first_json.exists()
    assert first_markdown.exists()
    assert second_json.exists()
    assert second_markdown.exists()
    assert second_json != first_json
    assert second_markdown != first_markdown
    assert second_json.stem.endswith("-2")
    assert second_markdown.stem.endswith("-2")


def test_export_session_persists_relationship_state(tmp_path: Path) -> None:
    persona = load_persona(Path("personas/wonyoung-idol.json"))
    session = ConversationSession(persona=persona)
    session.bootstrap()
    session.current_relationship_label = "married cofounders"
    session.current_relationship_summary = "서로의 일과 삶을 같이 책임지는 상태"
    session.relationship_state.situation = "같이 회사를 운영하며 집도 함께 쓰는 상태"

    json_path, _ = export_session(
        session_dir=tmp_path,
        persona=persona,
        messages=session.messages,
        relationship_state=session.export_state().get("relationship_state"),
    )

    _messages, snapshot = load_session_snapshot(json_path)

    assert snapshot["label"] == "married cofounders"
    assert snapshot["summary"] == "서로의 일과 삶을 같이 책임지는 상태"


def test_slugify_keeps_ascii_safe_names() -> None:
    assert slugify("Han Seo Jin") == "han-seo-jin"
    assert slugify("유나") == "유나"
