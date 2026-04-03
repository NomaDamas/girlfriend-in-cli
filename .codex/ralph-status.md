# Ralph Status

- Requested on: 2026-04-03
- Intended lineage: `lin_girlfriend_generator_ralph_20260403`
- Mode: anti-oscillation / pinned ontology

## Current Blocker

Ouroboros MCP tools are currently unreachable from Codex in this session.
Observed error:

`Transport closed`

The Ouroboros server processes are alive, but the tool transport is not.

## Prepared Fallback

The stable seed is stored at:

- `.codex/ralph-seed.yaml`

This seed pins the ontology so Ralph can resume without product-scope vibration once the MCP transport is restored.

## Repo-Local Workflow

- Capture evidence: `bash scripts/ouroboros_capture_evidence.sh`
- Run Ralph with ontology gate: `bash scripts/ouroboros_ralph.sh`
- Force re-interview: `FORCE_INTERVIEW=1 bash scripts/ouroboros_ralph.sh "<context>"`
