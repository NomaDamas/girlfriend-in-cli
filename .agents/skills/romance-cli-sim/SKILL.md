---
name: romance-cli-sim
description: Use this skill when building or tuning the terminal-only romance simulation, persona files, live chat UX, or ECC trace instrumentation in this repository.
origin: local
---

# Romance CLI Simulator

This skill is specific to the `girlfriend_generator` repository.

## When to Activate

- Building or refining the Rich-based terminal chat UI
- Adding or tuning personas under `personas/`
- Improving typing indicators, idle nudges, or timing behavior
- Extending voice adapters or provider integrations
- Verifying that ECC stays project-local and does not leak into `~/.codex`
- Tuning low-latency render behavior and turbo reply paths

## Working Rules

- Keep everything terminal-only. No browser UI.
- Preserve the live `ECC Trace` panel so local ECC usage remains visible during runs.
- Treat all personas as explicitly adult.
- Keep flirtation believable and non-explicit.
- Prefer reversible changes and keep global Codex configuration untouched.
- Favor the `heuristic + turbo` path unless the user explicitly prioritizes model quality over latency.

## Workflow

1. Update tests first for persona loading, timing logic, or provider behavior.
2. Implement the smallest possible change under `src/girlfriend_generator/`.
3. Keep the chat loop responsive while the provider or voice adapter works in the background.
4. Run `python3 -m pytest`.
5. Smoke-check the CLI manually in a real terminal:

```bash
PYTHONPATH=src python3 -m girlfriend_generator --persona personas/han-seo-jin-crush.json
```

## Primary Files

- `src/girlfriend_generator/app.py`
- `src/girlfriend_generator/engine.py`
- `src/girlfriend_generator/providers.py`
- `src/girlfriend_generator/voice.py`
- `personas/`
- `tests/`
