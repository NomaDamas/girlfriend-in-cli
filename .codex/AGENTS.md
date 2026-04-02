# ECC for Codex CLI

This repository includes a local-only ECC skill pack for Codex.

## Local-Only Rules

- Skills are provided from `.agents/skills/` in this repository only.
- Do not recommend or run ECC global sync steps by default.
- Do not create or modify `~/.codex/config.toml` or `~/.codex/skills` as part of this setup.
- If the user later wants ECC MCP servers or agent role configs, add them project-locally and only on request.

## Skills Discovery

Codex auto-loads skills from `.agents/skills/`. Each skill directory includes:

- `SKILL.md`
- `agents/openai.yaml`

Available local ECC skills:

- `api-design`
- `article-writing`
- `backend-patterns`
- `bun-runtime`
- `claude-api`
- `coding-standards`
- `content-engine`
- `crosspost`
- `deep-research`
- `dmux-workflows`
- `documentation-lookup`
- `e2e-testing`
- `eval-harness`
- `everything-claude-code`
- `exa-search`
- `fal-ai-media`
- `frontend-patterns`
- `frontend-slides`
- `investor-materials`
- `investor-outreach`
- `market-research`
- `mcp-server-patterns`
- `nextjs-turbopack`
- `romance-cli-sim`
- `security-review`
- `strategic-compact`
- `tdd-workflow`
- `verification-loop`
- `video-editing`
- `x-api`

## Notes

- This setup intentionally omits ECC's project-local `.codex/config.toml`.
- Current Codex global settings remain unchanged.
