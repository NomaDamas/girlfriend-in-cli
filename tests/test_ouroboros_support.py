from girlfriend_generator.ouroboros_support import detect_ontology_instability


def test_detect_ontology_instability_is_quiet_for_cli_changes() -> None:
    reasons = detect_ontology_instability(
        [
            "src/girlfriend_generator/app.py",
            "tests/test_app.py",
            "README.md",
            "scripts/smoke.sh",
        ]
    )

    assert reasons == []


def test_detect_ontology_instability_flags_web_mobile_surface_changes() -> None:
    reasons = detect_ontology_instability(
        [
            "app/page.tsx",
            "ios/App.swift",
            "package.json",
            "src/ui_shell.tsx",
        ]
    )

    assert len(reasons) == 4
    assert any("surface drift candidate" in reason for reason in reasons)
    assert any("non-cli UI artifact" in reason for reason in reasons)
    assert any("build manifest" in reason for reason in reasons)
