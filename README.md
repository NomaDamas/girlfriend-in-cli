# Girlfriend Generator

`girlfriend-generator` is a terminal-only romance simulation chat designed for short vibe-coding breaks. It keeps the interaction inside the CLI, renders chat bubbles with Rich, simulates typing indicators, sends real-time nudges when the user leaves the conversation hanging, and exposes an ECC trace panel so you can see which local Everything Claude Code assets are driving the session.

## What It Does

- Runs a KakaoTalk-like chat flow in the terminal
- Loads detailed adult personas from `personas/*.json`
- Simulates assistant typing and follow-up nudges
- Supports optional voice output on macOS via `say`
- Supports optional voice input through a user-supplied transcription command
- Shows a live `ECC Trace` panel with the active persona, provider, voice adapters, idle timers, and local skill roots

## Why It Uses ECC Locally

This repository vendors Everything Claude Code assets project-locally:

- `AGENTS.md`
- `.codex/AGENTS.md`
- `.agents/skills/`

It does **not** modify `~/.codex/config.toml` or global Codex defaults.

## Run

```bash
PYTHONPATH=src python3 -m girlfriend_generator --persona personas/han-seo-jin-crush.json
```

Bootstrap a local venv:

```bash
bash scripts/bootstrap.sh
```

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
PYTHONPATH=src python3 -m girlfriend_generator \
  --persona personas/yu-na-girlfriend.json \
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

## Transcript Export

By default the app exports each finished session to `sessions/` as:

- JSON for programmatic reuse
- Markdown for quick review or prompt reuse

You can also trigger this manually with `/export`.

## Verification

Local smoke check:

```bash
bash scripts/smoke.sh
```

GitHub Actions also runs compile + test on Python 3.10, 3.11, and 3.12 after push.
