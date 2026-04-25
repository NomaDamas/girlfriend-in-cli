"""Auto-generate persona JSON from a name or URL using LLM."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_AUTO_PERSONA_PROMPT = """You are a persona generator for a Korean romance simulation game.
Given a name, celebrity, character, or profile URL, research what you know about them and
generate a rich, believable persona as JSON.

Input: {input_text}

Generate a persona with this EXACT JSON structure (respond with ONLY valid JSON, no markdown):
{{
  "name": "Korean name or English name",
  "age": integer (must be 20+),
  "relationship_mode": "crush" or "girlfriend",
  "difficulty": "easy/normal/hard/nightmare — based on real-world dating difficulty for this person/character. A super famous celebrity = nightmare. A shy student = easy. A guarded ice queen = hard.",
  "background": "2-3 sentences in Korean about who they are, where they live/work, personality",
  "situation": "1-2 sentences in Korean describing the current texting situation with the user",
  "texting_style": "how they text on KakaoTalk (short/long, emoji use, tone) in Korean",
  "interests": ["관심사 1", "관심사 2", "관심사 3", "관심사 4"],
  "soft_spots": ["마음이 녹는 포인트 1", "2", "3"],
  "boundaries": ["싫어하는 것 1", "2", "3"],
  "greeting": "첫 인사 메시지 (1-2 sentences in Korean)",
  "accent_color": "magenta/cyan/yellow/green/red/blue (pick one that fits their vibe)",
  "provider_system_hint": "1 sentence in Korean — key personality note for the LLM",
  "context_summary": "1 sentence in Korean — overall relationship context",
  "typing": {{"min_seconds": 0.8, "max_seconds": 3.2}},
  "nudge_policy": {{
    "idle_after_seconds": 35,
    "follow_up_after_seconds": 80,
    "max_nudges": 2,
    "templates": ["fallback nudge 1", "fallback nudge 2"]
  }},
  "style_profile": {{
    "warmth": 0.0-1.0,
    "teasing": 0.0-1.0,
    "directness": 0.0-1.0,
    "message_length": "short/short-medium/medium",
    "emoji_level": "very-low/low/medium/high",
    "signature_phrases": ["자주 쓰는 말 1", "2", "3"]
  }},
  "initiative_profile": {{
    "min_interval_seconds": 600,
    "max_interval_seconds": 3000,
    "spontaneity": 0.0-1.0,
    "opener_templates": ["먼저 보내는 톡 1", "2", "3"],
    "follow_up_templates": ["1", "2"]
  }}
}}

Rules:
- Age must be 20 or higher (adult only).
- If you don't know who this is (unknown person or random URL), INVENT a believable character
  with reasonable traits based on any clues in the input.
- Make the personality VIVID and SPECIFIC — avoid generic "친절하고 밝은" descriptions.
- Texting style should match the person/character (celebrity = busy, anime character = stylized, etc).
- Korean text except for English names/words.
"""


@dataclass(slots=True)
class PersonaGeneratorConfig:
    provider: str = "openai"
    model: str | None = None
    ollama_base_url: str | None = None


def _looks_like_url(text: str) -> bool:
    return text.startswith("http://") or text.startswith("https://") or "://" in text


def _fetch_url_content(url: str) -> str:
    """Fetch and extract text from a URL (best effort)."""
    try:
        from urllib import request
        from urllib.parse import urlparse
        import re

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return ""

        req = request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            },
        )
        with request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")

        # Strip HTML tags crudely
        text = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text[:8000]
    except Exception:
        return ""


def _resolve_persona_model(config: PersonaGeneratorConfig) -> str:
    defaults = {
        "openai": "gpt-5.4-mini",
        "anthropic": "claude-haiku-4-5",
    }
    return config.model or defaults.get(config.provider, defaults["openai"])


def _build_generator_client(config: PersonaGeneratorConfig) -> tuple[str, Any]:
    if config.provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set. Set it in Settings > API Keys.")
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("Install anthropic package.") from exc
        return "anthropic", anthropic.Anthropic()

    if config.provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set. Set it in Settings > API Keys.")
        from .providers import _build_openai_client
        return "openai", _build_openai_client()

    raise RuntimeError(f"Unsupported persona generation provider: {config.provider}")


def _create_text_response(
    client: Any,
    client_kind: str,
    *,
    model: str,
    prompt: str,
    temperature: float | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> str:
    if client_kind == "anthropic":
        response = client.messages.create(
            model=model,
            max_tokens=2400,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()

    request: dict[str, Any] = {
        "model": model,
        "input": prompt,
    }
    if temperature is not None:
        request["temperature"] = temperature
    if tools:
        request["tools"] = tools

    response = client.responses.create(**request)
    return response.output_text.strip()


def _web_search_context(
    query: str,
    client: Any,
    *,
    client_kind: str,
    model: str,
) -> str:
    """Use OpenAI web_search tool to gather context about the query when available."""
    if client_kind != "openai":
        return ""

    try:
        response = client.responses.create(
            model=model,
            tools=[{"type": "web_search"}],
            input=f"Search for information about: {query}\n\n"
            f"Summarize their personality, background, interests, style, "
            f"notable quotes, and characteristic traits. Korean or English OK. "
            f"Be concrete and specific. Max 600 words.",
        )
        return response.output_text.strip()[:4000]
    except Exception:
        return ""


def generate_persona_from_input(
    input_text: str,
    model: str = "gpt-5.4-mini",
    config: PersonaGeneratorConfig | None = None,
) -> dict[str, Any]:
    """Call LLM to generate persona JSON from a name, URL, or description.
    If input is a URL, fetch page content. Otherwise, use web_search tool."""
    resolved_config = config or PersonaGeneratorConfig(model=model)
    resolved_model = _resolve_persona_model(resolved_config)
    client_kind, client = _build_generator_client(resolved_config)

    # Gather research context
    research_context = ""
    if _looks_like_url(input_text):
        research_context = _fetch_url_content(input_text)
        if not research_context:
            research_context = _web_search_context(
                input_text,
                client,
                client_kind=client_kind,
                model=resolved_model,
            )
    else:
        # Name or description — use web search
        research_context = _web_search_context(
            input_text,
            client,
            client_kind=client_kind,
            model=resolved_model,
        )

    full_input = input_text
    if research_context:
        full_input = (
            f"{input_text}\n\n"
            f"=== Research context (use this to ground the persona) ===\n"
            f"{research_context}"
        )

    prompt = _AUTO_PERSONA_PROMPT.format(input_text=full_input)
    raw = _create_text_response(
        client,
        client_kind,
        model=resolved_model,
        prompt=prompt,
        temperature=0.9,
    )

    # Strip markdown if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM returned invalid JSON: {exc}\n\n{raw[:500]}") from exc

    # Validate required fields
    required = ["name", "age", "relationship_mode", "background", "situation",
                "texting_style", "interests", "soft_spots", "boundaries", "greeting"]
    for field in required:
        if field not in data:
            raise RuntimeError(f"Generated persona missing required field: {field}")

    if data.get("age", 0) < 20:
        data["age"] = 20

    return data


def deep_research_persona(
    input_text: str,
    on_progress: Any = None,
    model: str = "gpt-5.4-mini",
    config: PersonaGeneratorConfig | None = None,
) -> dict[str, Any]:
    """Multi-step deep research persona generation with progress callbacks.

    Steps:
    1. Analyze input to extract key entities/themes
    2. Web search for each entity (up to 3 queries)
    3. Gather all context together
    4. Synthesize into detailed persona JSON
    5. Review and enrich
    """
    resolved_config = config or PersonaGeneratorConfig(model=model)
    resolved_model = _resolve_persona_model(resolved_config)

    def _notify(step: int) -> None:
        if callable(on_progress):
            try:
                on_progress(step)
            except Exception:
                pass

    client_kind, client = _build_generator_client(resolved_config)

    # Step 1: Analyze
    _notify(0)
    analyze_raw = _create_text_response(
        client,
        client_kind,
        model=resolved_model,
        prompt=(
            f"Input for persona creation:\n{input_text}\n\n"
            "Extract up to 3 key web search queries that would help research this persona. "
            "Return as JSON: {\"queries\": [\"q1\", \"q2\", \"q3\"], \"is_url\": true/false}. "
            "If input is a URL, set is_url=true and queries=[]. "
            "If input is a known name/character, make queries specific. "
            "If input is a free-form description, make queries based on key traits mentioned. "
            "Respond with ONLY valid JSON, no markdown."
        ),
    )
    try:
        raw = analyze_raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        plan = json.loads(raw)
        queries = plan.get("queries", []) or []
        is_url = plan.get("is_url", False)
    except Exception:
        queries = [input_text[:100]]
        is_url = _looks_like_url(input_text)

    # Step 2-3: Gather context
    _notify(1)
    research_chunks: list[str] = []
    if is_url or _looks_like_url(input_text):
        html = _fetch_url_content(input_text)
        if html:
            research_chunks.append(html)

    _notify(2)
    if client_kind == "openai":
        for q in queries[:3]:
            try:
                search_text = _create_text_response(
                    client,
                    client_kind,
                    model=resolved_model,
                    tools=[{"type": "web_search"}],
                    prompt=(
                        f"Search the web for: {q}\n\n"
                        f"Summarize concrete facts, personality traits, style quotes, "
                        f"characteristic behavior, and anything useful for building "
                        f"a texting-persona simulation. Max 400 words."
                    ),
                )
                research_chunks.append(search_text)
            except Exception:
                continue
    elif client_kind == "anthropic":
        research_chunks.append(
            "Web search is unavailable for this provider; rely on the user input and fetched URL text only."
        )

    combined_research = "\n\n---\n\n".join(research_chunks)[:8000]

    # Step 4: Synthesize
    _notify(3)
    full_input = (
        f"{input_text}\n\n"
        f"=== Research context (use this to ground the persona) ===\n"
        f"{combined_research if combined_research else '(no web context available — invent a believable character)'}"
    )
    prompt = _AUTO_PERSONA_PROMPT.format(input_text=full_input)

    raw = _create_text_response(
        client,
        client_kind,
        model=resolved_model,
        prompt=prompt,
        temperature=0.9,
    )
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM returned invalid JSON: {exc}\n\n{raw[:500]}") from exc

    # Step 5: Validate & finalize
    _notify(4)
    required = ["name", "age", "relationship_mode", "background", "situation",
                "texting_style", "interests", "soft_spots", "boundaries", "greeting"]
    for field_name in required:
        if field_name not in data:
            raise RuntimeError(f"Generated persona missing required field: {field_name}")
    if data.get("age", 0) < 20:
        data["age"] = 20

    return data


def save_generated_persona(data: dict[str, Any], personas_dir: Path) -> Path:
    """Save generated persona to personas/ directory."""
    from .session_io import slugify
    name = data.get("name", "custom")
    filename = f"{slugify(name)}-auto.json"
    personas_dir.mkdir(parents=True, exist_ok=True)
    path = personas_dir / filename
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
