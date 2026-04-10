"""Auto-generate persona JSON from a name or URL using LLM."""

from __future__ import annotations

import json
import os
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


def _web_search_context(query: str) -> str:
    """Use OpenAI web_search tool to gather context about the query."""
    try:
        from openai import OpenAI
    except ImportError:
        return ""

    try:
        client = OpenAI()
        response = client.responses.create(
            model="gpt-4.1-mini",
            tools=[{"type": "web_search"}],
            input=f"Search for information about: {query}\n\n"
            f"Summarize their personality, background, interests, style, "
            f"notable quotes, and characteristic traits. Korean or English OK. "
            f"Be concrete and specific. Max 600 words.",
        )
        return response.output_text.strip()[:4000]
    except Exception:
        return ""


def generate_persona_from_input(input_text: str, model: str = "gpt-4.1-mini") -> dict[str, Any]:
    """Call LLM to generate persona JSON from a name, URL, or description.
    If input is a URL, fetch page content. Otherwise, use web_search tool."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Set it in Settings > API Keys.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install openai package.") from exc

    # Gather research context
    research_context = ""
    if _looks_like_url(input_text):
        research_context = _fetch_url_content(input_text)
        if not research_context:
            research_context = _web_search_context(input_text)
    else:
        # Name or description — use web search
        research_context = _web_search_context(input_text)

    full_input = input_text
    if research_context:
        full_input = (
            f"{input_text}\n\n"
            f"=== Research context (use this to ground the persona) ===\n"
            f"{research_context}"
        )

    client = OpenAI()
    prompt = _AUTO_PERSONA_PROMPT.format(input_text=full_input)

    response = client.responses.create(
        model=model,
        temperature=0.9,
        input=[
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }
        ],
    )
    raw = response.output_text.strip()

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
