# Issue #11: Creator Persona Hub

Refs #11

## Status

Design scaffold. This does not implement publishing, browsing, moderation, ownership, popularity metrics, or monetization.

## Why This Is Not Closing Yet

The requested creator hub is an online ecosystem, not a local persona-file share. A complete implementation needs account identity, persistence, public URLs, moderation/reporting, metric integrity, and import safety. This document defines the safe merge gate for future product and runtime work.

## Target Experience

1. A creator builds or edits a persona locally.
2. The creator signs into the product and submits the persona to a hub.
3. The hub shows title, tags, vibe, description, creator identity, and safety metadata.
4. Other users can browse, import, and play the persona.
5. Popularity and creator stats are visible without exposing private chat transcripts.

## Product Model

- Persona ownership belongs to a product account, not the local filename.
- A published persona receives a stable ID and share URL.
- Imported personas preserve source attribution and version metadata.
- Popularity metrics should be aggregated server-side.
- Featured, trending, and rising lists require anti-manipulation rules before public launch.

## Security / Privacy / Runtime Gate

- Creator identity: define display name, stable account ID, impersonation protections, and deletion behavior.
- Persona ownership: define edit permissions, transfer policy, takedown policy, and fork/remix attribution.
- Persistence/store: choose storage for persona JSON, metadata, version history, and moderation state.
- Moderation/reporting: define pre-publish validation, user reports, review queue, abuse escalation, and removal UX.
- Metric integrity: define how likes, imports, play counts, and session-time metrics resist spam and replay.
- Import safety: validate schema, prompt fields, external links, oversized payloads, and unsafe metadata before local use.
- Privacy: popularity metrics must not expose raw transcripts, private affection history, or personal identifiers.
- Monetization readiness: document how premium personas or revenue share would avoid breaking import/export ownership rules.

## Implementation Acceptance Criteria

- A signed-in creator can publish a custom persona with metadata.
- Another user can browse, import, and use the published persona.
- Persona ownership and creator identity are visible in the hub and import metadata.
- Popularity metrics are tracked server-side and rendered without transcript leakage.
- Reports and moderation state can hide or remove unsafe personas.
- Tests cover publishing, import validation, ownership checks, metric updates, and report/moderation behavior.

## Verification Before Close

- Run hub/API tests and focused CLI import/export tests once implementation exists.
- Manually publish a persona, import it from another account, report it, and verify moderation visibility.
- Inspect stored metrics and local imported files for transcript or private-state leakage.
- The PR body may use `Closes #11` only after the implementation acceptance criteria and gate are evidenced.
