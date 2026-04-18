# Contributing

Thanks for contributing to `girlfriend-in-cli`.

## Ways To Contribute

- Fix bugs in the terminal chat UX
- Improve personas under `personas/`
- Add tests for chat, scene, export, and provider flows
- Improve docs, setup, and release tooling

## Development Setup

From the repository root:

```bash
uv sync --extra dev
uv run pytest
uv run mygf
```

If you prefer activating the environment manually:

```bash
source .venv/bin/activate
pytest
mygf
```

## Workflow

1. Fork the repository
2. Create a branch from `main`
3. Make a focused change
4. Run relevant tests
5. Open a pull request with a clear summary

## What To Include In A PR

- What changed
- Why it changed
- How you verified it
- Screenshots or terminal captures if the UX changed

## Testing

Run the full suite:

```bash
pytest -q
```

Run a focused suite:

```bash
pytest -q tests/test_app.py tests/test_cli.py tests/test_engine.py
```

Compile sources:

```bash
python3 -m compileall src/girlfriend_generator
```

## Personas

If you contribute a persona:

- Keep all personas explicitly adult
- Keep behavior non-explicit
- Make the style specific, not generic
- Add or update tests if schema/behavior changes

## Notes

- Project-local Codex/ECC setup lives in `AGENTS.md`, `.codex/AGENTS.md`, and `.agents/skills/`
- Do not assume global Codex config changes are wanted
