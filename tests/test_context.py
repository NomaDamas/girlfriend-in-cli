from girlfriend_generator.context import build_context_bundle, compile_persona


def test_compile_persona_turns_context_into_structured_persona() -> None:
    bundle = build_context_bundle(
        {
            "name": "민지",
            "age": 26,
            "relationship_mode": "crush",
            "notes": "홍대에서 브랜드 마케터로 일하고 전시와 카페를 좋아한다. 답장이 센스 있으면 호감을 잘 느낀다.",
            "links": ["https://instagram.com/minji.example"],
            "snippets": ["뭐 해? ㅋㅋ", "전시 보러 가는 거 좋아해"],
            "requested_traits": ["playful", "specific check-ins"],
        }
    )

    persona = compile_persona(bundle)

    assert persona.name == "민지"
    assert persona.age == 26
    assert persona.context_summary
    assert persona.evidence
    assert "카페" in persona.interests or "전시회" in persona.interests
    assert persona.initiative_profile.opener_templates
    assert persona.style_profile.signature_phrases
