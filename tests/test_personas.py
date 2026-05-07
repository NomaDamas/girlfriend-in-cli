from pathlib import Path

from girlfriend_generator.personas import discover_personas, load_persona


def test_discover_personas_lists_bundled_files() -> None:
    persona_paths = discover_personas(Path("personas"))
    names = [path.name for path in persona_paths]
    assert "wonyoung-idol.json" in names
    assert "dua-international.json" in names
    assert "mina-saju-cafe.json" in names


def test_load_persona_validates_adult_and_nudges() -> None:
    persona = load_persona(Path("personas/wonyoung-idol.json"))
    assert persona.age >= 20
    assert persona.relationship_mode == "crush"
    assert persona.nudge_policy.templates


def test_discover_personas_is_empty_for_missing_directory(tmp_path: Path) -> None:
    assert discover_personas(tmp_path / "missing") == []


def test_load_saju_persona_keeps_scenario_and_birth_info_hook() -> None:
    persona = load_persona(Path("personas/mina-saju-cafe.json"))

    assert persona.scenario == "saju"
    assert "생년월일" in persona.greeting
    assert "태어난 시간" in persona.greeting
    assert any("운세" in template or "생년월일" in template for template in persona.nudge_policy.templates)
