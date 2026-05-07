from pathlib import Path

from girlfriend_generator.personas import discover_personas, load_persona, persona_from_pack


def test_discover_personas_lists_bundled_files() -> None:
    persona_paths = discover_personas(Path("personas"))
    names = [path.name for path in persona_paths]
    assert "wonyoung-idol.json" in names
    assert "dua-international.json" in names


def test_load_persona_validates_adult_and_nudges() -> None:
    persona = load_persona(Path("personas/wonyoung-idol.json"))
    assert persona.age >= 20
    assert persona.relationship_mode == "crush"
    assert persona.nudge_policy.templates


def test_discover_personas_is_empty_for_missing_directory(tmp_path: Path) -> None:
    assert discover_personas(tmp_path / "missing") == []


def test_persona_profile_image_dict_is_loaded() -> None:
    persona = persona_from_pack(
        {
            "name": "미사키",
            "age": 24,
            "relationship_mode": "crush",
            "background": "서울에서 일하는 성인 페르소나",
            "situation": "서로 알아가는 중",
            "texting_style": "짧고 장난스럽게",
            "interests": ["영화"],
            "soft_spots": ["기억해주기"],
            "boundaries": ["무례함"],
            "greeting": "왔어?",
            "profile_image": {
                "url": "https://example.com/misaki.png",
                "source": "auto_fetched",
                "cached_path": "personas/.images/misaki.png",
                "style": "anime",
            },
            "nudge_policy": {"templates": ["왜 답장 안 해?"]},
        }
    )

    assert persona.profile_image is not None
    assert persona.profile_image.url == "https://example.com/misaki.png"
    assert persona.profile_image.cached_path == "personas/.images/misaki.png"
    assert persona.profile_image.style == "anime"


def test_persona_profile_image_string_is_loaded_as_user_uploaded_path() -> None:
    persona = persona_from_pack(
        {
            "name": "지은",
            "age": 24,
            "relationship_mode": "crush",
            "background": "서울에서 일하는 성인 페르소나",
            "situation": "서로 알아가는 중",
            "texting_style": "짧고 장난스럽게",
            "interests": ["고양이"],
            "soft_spots": ["기억해주기"],
            "boundaries": ["무례함"],
            "greeting": "왔어?",
            "profile_image": "~/Pictures/jieun.jpg",
            "nudge_policy": {"templates": ["왜 답장 안 해?"]},
        }
    )

    assert persona.profile_image is not None
    assert persona.profile_image.cached_path == "~/Pictures/jieun.jpg"
    assert persona.profile_image.source == "user_uploaded"
