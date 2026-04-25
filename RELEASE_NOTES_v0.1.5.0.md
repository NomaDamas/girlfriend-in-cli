# v0.1.5.0 — AI-companion repositioning + deprecated model cleanup

## Summary

Two structural changes driven by user feedback in [#22](https://github.com/NomaDamas/girlfriend-in-cli/issues/22):

1. The persona is now positioned as an **AI companion living in your CLI**, not as a fictional "real person" being shuffled through scripted physical scenes.
2. All **deprecated provider model defaults** have been removed. The new defaults work in environments where the old IDs (e.g. `gpt-4.1-mini`, `claude-3-7-sonnet-latest`) are no longer reachable.

## What changed

### Scene system removed

Closes [#22](https://github.com/NomaDamas/girlfriend-in-cli/issues/22).

The "scene system" (carousel of cafe / restaurant / convenience store / park / night walk / home doorstep, plus the periodic LLM evaluator that proposed location changes mid-conversation, plus the report-card transition card) felt artificial and broke the long-form conversational continuity users actually wanted.

Removed:

- `src/girlfriend_generator/scenes.py` (Scene, SceneState, evaluator/report builders, ReportCard renderer)
- `scenes/*.json` (all six bundled location files)
- `seeds/scene-system.yaml` (Ouroboros seed for the feature)
- The scene evaluator that fired every 6 user messages
- The accept/reject scene-proposal mechanics + ±5 / −2 affection adjustments tied to them
- The full-screen scene-transition report card
- `propose_scene` field in `ProviderReply` and the corresponding LLM JSON-schema slot
- The `/move` command
- "Current location/situation:" injection in the system prompt

Renamed:

- `ConversationSession.strategy_uses_this_scene` → `strategy_uses_this_session`
- `ConversationSession.max_strategy_per_scene` → `max_strategy_per_session`

### Persona repositioned as AI companion

The system prompt's "you are NOT an AI, chatbot, or model" rule has been replaced. The companion now:

- accepts that it is an AI companion living inside the user's terminal
- admits it honestly when the user asks "are you an AI?"
- still keeps the persona's personality, voice, signature phrases, and texting style
- no longer fabricates external physical events ("I just got off work", "I'm at the cafe", "let's go to the park") to maintain a fake-real-person illusion
- frames itself as a companion that helps the user practice conversational skill, timing, and warmth — the project's stated philosophy

### Deprecated model defaults removed

Some environments cannot reach the previous defaults (`gpt-4.1-mini` was retired from ChatGPT in February 2026 and is increasingly flaky on third-party gateways; `claude-3-7-sonnet-latest` has been retired from the Claude API since 2025-10-28).

| Provider  | Old default                 | New default        |
|-----------|-----------------------------|--------------------|
| OpenAI    | `gpt-4.1-mini`              | `gpt-5.4-mini`     |
| Anthropic | `claude-3-7-sonnet-latest`  | `claude-haiku-4-5` |

Persona auto-generation (`persona_auto.py`) also updated from `gpt-4.1-mini` to `gpt-5.4-mini`.

If you were relying on the old IDs explicitly via `--model`, pass them explicitly — only the implicit defaults changed.

## Breaking changes

- The `/move` command no longer exists.
- `scenes/` directory and `seeds/scene-system.yaml` are gone. If you forked these, vendor them locally.
- `ProviderReply.propose_scene` is gone.
- `ConversationSession.strategy_uses_this_scene` / `max_strategy_per_scene` are renamed to `_session`.

## Verification

- `uv run pytest` — 91 passed
- `bash scripts/smoke.sh` — green
