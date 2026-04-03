# Girlfriend Generator

`girlfriend-generator` is a terminal-only romance simulation chat designed for short vibe-coding breaks. It keeps the interaction inside the CLI, renders chat bubbles with Rich, simulates typing indicators, sends real-time nudges when the user leaves the conversation hanging, and exposes an ECC trace panel so you can see which local Everything Claude Code assets are driving the session.

## What It Does

- Runs a KakaoTalk-like chat flow in the terminal
- Loads detailed adult personas from `personas/*.json`
- Compiles richer personas from notes, snippets, and public-context links
- Simulates assistant typing and follow-up nudges
- Supports irregular first-message initiative instead of only reactive replies
- Supports optional voice output on macOS via `say`
- Supports optional voice input through a user-supplied transcription command
- Shows a live `ECC Trace` panel with the active persona, provider, voice adapters, idle timers, and local skill roots

## Why It Uses ECC Locally

This repository vendors Everything Claude Code assets project-locally:

- `AGENTS.md`
- `.codex/AGENTS.md`
- `.agents/skills/`

It does **not** modify `~/.codex/config.toml` or global Codex defaults.

## Install

Bootstrap a local editable environment:

```bash
bash scripts/bootstrap.sh
```

That script prefers `python -m pip install --no-build-isolation -e ".[dev]"`, then falls back to `python setup.py develop` inside a `--system-site-packages` virtualenv when standards-based editable installs are blocked. The `--no-build-isolation` path avoids unnecessary network lookups for build dependencies and keeps setup local without touching `~/.codex`.

On machines without local `wheel` support, the script skips straight to `python setup.py develop`, which is the verified offline-safe path in this repository.

Manual local install from the repository root:

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python setup.py develop
```

If your environment already has `wheel` installed locally, this standards-based editable install also works:

```bash
python -m pip install --no-build-isolation -e ".[dev]"
```

## Run

Once installed, run the package entrypoint from anywhere:

```bash
girlfriend-generator
```

You can also use the module entrypoint while staying in the repository:

```bash
python3 -m girlfriend_generator --persona personas/han-seo-jin-crush.json
```

If you want to pin a specific persona from outside the repository, pass an absolute path to the persona file.

Optional flags:

- `--provider heuristic|openai|anthropic`
- `--model <model-name>`
- `--performance turbo|balanced|cinematic`
- `--voice-output`
- `--voice-input-command "<command that prints a transcript to stdout>"`
- `--session-dir <path>`
- `--no-export-on-exit`
- `--no-trace`
- `--list-personas`

## API

Run the server-ready JSON API:

```bash
girlfriend-generator-api --host 127.0.0.1 --port 8765
```

Core endpoints:

- `POST /v1/context/compile`
- `POST /v1/sessions`
- `POST /v1/sessions/:id/message`
- `POST /v1/sessions/:id/tick`
- `GET /v1/sessions/:id/state`

The moat-oriented flow is:

1. ingest notes, snippets, and links
2. compile them into a structured persona
3. run a session with memory, nudges, and irregular initiative
4. verify the behavior with end-to-end tests and evidence capture

## Controls

- Type normally to compose a message
- `Enter` sends
- `Esc` clears the draft
- `/help` shows in-app commands
- `/trace` toggles the ECC trace panel
- `/status` posts internal session state into the chat
- `/export` writes JSON and Markdown transcripts to `sessions/`
- `/voice on` and `/voice off` toggle voice output
- `/listen` runs the configured voice-input command and sends the transcript
- `/quit` exits

## Example

```bash
girlfriend-generator \
  --persona /absolute/path/to/girlfriend_generator/personas/yu-na-girlfriend.json \
  --voice-output
```

## Voice Notes

Voice output works out of the box on macOS through the built-in `say` command.

Voice input is intentionally adapter-based for now. Pass a command that records and transcribes speech, then prints the transcript to stdout. This keeps the base app lightweight while still making voice flows scriptable inside Codex or Claude Code workflows.

## Performance

Default runtime is tuned for low latency:

- `--provider heuristic`
- `--performance turbo`
- local zero-network reply generation
- event-driven Rich redraws instead of constant frame refresh

If you switch to `openai` or `anthropic`, quality can improve, but latency will be worse than the local turbo path.

Use `--performance balanced` if you want slightly longer typing simulation without leaving the local heuristic path. Use `--performance cinematic` only when you explicitly want slower, more dramatic pacing.

## Transcript Export

By default the app exports each finished session to the repository-local `sessions/` directory as:

- JSON for programmatic reuse
- Markdown for quick review or prompt reuse

The default export target is resolved from the repository root, not your current shell directory, so installed entrypoints still keep transcripts local to this project. You can also trigger export manually with `/export`.

## Verification

Local smoke check:

```bash
bash scripts/smoke.sh
```

The smoke script verifies:

- package compilation
- `pytest` from the repository root
- editable install into a temporary virtualenv, using the offline-safe local path when `wheel` is unavailable
- `girlfriend-generator --help`
- bundled persona discovery from outside the repository
- repository-local transcript path resolution
- direct transcript export into the repository-local `sessions/` directory
- API/server-ready persona compilation and session behavior through pytest E2E coverage

## Ouroboros

This repository now includes a repo-local Ralph workflow setup:

- pinned anti-oscillation seed: `.codex/ralph-seed.yaml`
- current loop notes: `.codex/ralph-status.md`
- evidence capture: `scripts/ouroboros_capture_evidence.sh`
- Ralph launcher with ontology gate: `scripts/ouroboros_ralph.sh`

Run the full repo-local Ralph path:

```bash
bash scripts/ouroboros_ralph.sh
```

What it does:

- checks `ouroboros status health`
- captures reproducible verification evidence under `artifacts/ouroboros/latest/`
- scans changed paths for likely ontology drift
- launches an interview if instability is detected
- otherwise runs the pinned Ralph workflow sequentially

To force a re-interview even when the ontology looks stable:

```bash
FORCE_INTERVIEW=1 bash scripts/ouroboros_ralph.sh "Refine the ontology before the next execution"
```
