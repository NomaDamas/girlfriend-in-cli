# v0.1.6.0 — Optional persona-initiated photo sending

## Summary

The persona can now autonomously send a phone-style photo during a conversation when it would feel natural — opt-in via `--photos`.

## What's new

### `--photos` flag (default OFF)

```bash
mygf --photos                   # auto-open photos in OS viewer (default on macOS)
mygf --photos --photos-no-open  # save only, no auto-open
```

When enabled (and using the OpenAI provider), the persona's reply JSON gains a `photo_prompt` slot. If the persona judges that sending a photo would fit the moment, it fills it in. The app then:

1. Generates the image in a background thread via `gpt-image-1`
2. Saves the PNG to `<session_dir>/photos/<timestamp>-<slug>.png`
3. Posts a system message in chat: `📷 사진 도착 — <description>` plus a clickable `file://` URL
4. On macOS, auto-opens the image in Preview (suppress with `--photos-no-open`)

### Smart prompt gating

The system prompt advertises the `photo_prompt` slot **only when `--photos` is on**. With the flag off, the LLM doesn't even know the option exists — zero token cost, zero risk of accidental triggers.

### Rate limiting

Capped at **5 photos per session**. On generation failure the slot is refunded so a single API hiccup doesn't burn the budget.

### Provider scope

Only the OpenAI provider can generate. With `--provider anthropic` or `--provider ollama` the flag is accepted but ignored (no image gen API in those paths).

## Cost note

`gpt-image-1` 1024x1024 ≈ $0.04 per image. With the 5/session cap that's ~$0.20/session worst case. Off by default keeps users from accidentally burning budget.

## Verification

- `uv run pytest` — 123 passed (was 112; 11 new tests in `tests/test_photo.py`)
- CI green across Python 3.10 / 3.11 / 3.12

## Files

- New: `src/girlfriend_generator/photo.py`, `tests/test_photo.py`
- Modified: `cli.py` (flags), `app.py` (`PhotoState`, `_spawn_photo_job`, main loop wiring), `providers.py` (system prompt slot + JSON parsing for both OpenAI/Anthropic), `models.py` (`ProviderReply.photo_prompt`)

## Related

- Concept: per #19 (multimodal feature) — photos branch shipped first
- Companion repositioning: keeps the v0.1.5.0 line (#22) — the persona stays an AI companion who happens to have a phone
