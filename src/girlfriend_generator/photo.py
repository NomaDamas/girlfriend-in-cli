"""Persona-initiated photo sending (duct-tape implementation).

The persona's reply JSON can include a `photo_prompt` string. When the user
opted in via `--photos` and the OpenAI provider is in use, we generate the
image with `gpt-image-1`, save it under `<session_dir>/photos/`, and surface
a system message in chat with a clickable file:// link. macOS auto-opens.

The whole subsystem is intentionally simple — no in-terminal rendering, no
fallback providers, no caching. Anthropic / Ollama / remote do not generate.
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PhotoState:
    enabled: bool = False
    session_photos_dir: Path | None = None
    sent_count: int = 0
    max_per_session: int = 5
    auto_open: bool = True

    def can_send(self) -> bool:
        return self.enabled and self.sent_count < self.max_per_session

    def remaining(self) -> int:
        return max(0, self.max_per_session - self.sent_count)


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9가-힣\s_-]", "", text).strip()
    cleaned = re.sub(r"\s+", "-", cleaned)
    return cleaned[:40] or "photo"


def generate_photo(
    prompt: str,
    persona_name: str,
    out_dir: Path,
    *,
    size: str = "1024x1024",
    model: str = "gpt-image-1",
) -> Path:
    """Call OpenAI image API and write the PNG. Returns the saved path."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")

    from openai import OpenAI

    client = OpenAI()
    full_prompt = (
        f"A casual smartphone photo that {persona_name} would naturally text. "
        f"Subject: {prompt}. "
        "Style: candid, slightly imperfect framing, warm phone-camera tone, "
        "no text overlays, no watermarks, no logos."
    )
    response = client.images.generate(
        model=model,
        prompt=full_prompt,
        size=size,
        n=1,
    )
    data = response.data[0]
    b64 = getattr(data, "b64_json", None)
    if not b64:
        url = getattr(data, "url", "")
        if not url:
            raise RuntimeError("Image API returned no usable payload.")
        from urllib.request import urlopen
        with urlopen(url, timeout=30) as resp:
            blob = resp.read()
    else:
        blob = base64.b64decode(b64)

    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    fname = f"{timestamp}-{_slugify(prompt)}.png"
    path = out_dir / fname
    path.write_bytes(blob)
    return path


def open_in_default_app(path: Path) -> None:
    """Best-effort: open the file in the OS default viewer. Silent on failure."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(
                ["open", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif sys.platform.startswith("linux"):
            subprocess.Popen(
                ["xdg-open", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass


def render_photo_message(path: Path, prompt: str, remaining: int) -> str:
    """System-message text shown in chat after a photo is delivered."""
    file_url = f"file://{path.resolve()}"
    suffix = f" · {remaining}장 남음" if remaining >= 0 else ""
    return f"📷 사진 도착 — {prompt}\n   {file_url}{suffix}"
