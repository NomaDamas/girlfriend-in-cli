# ECC Local Setup

This repository vendors project-local assets from `affaan-m/everything-claude-code`.

## Local-Only Policy

- Use the repo-local `.agents/skills/` directory for ECC skills in this repository.
- Do not install or sync ECC into `~/.codex/skills` or `~/.codex/config.toml` unless the user explicitly asks.
- Treat the absence of a project-local `.codex/config.toml` as intentional. This setup should not change Codex defaults.
- If extra MCP servers, multi-agent roles, or other ECC defaults are needed later, add them project-locally first.

## Scope

- These instructions apply only inside this repository.
- For Codex-specific skill discovery and usage notes, also read `.codex/AGENTS.md`.

## Ralph Evidence

- When running Ouroboros/Ralph-style verification in this repository, prefer repo-local evidence files under `artifacts/ouroboros/latest/`.
- Treat `artifacts/ouroboros/latest/test-output.txt` as the canonical condensed `test_output` artifact.
- When summarizing verification, prefer direct command/output evidence over prose-only claims.
