# Issue #7: Login-Based Play Flow

Refs #7

## Status

Design scaffold. This does not implement login, hosted sessions, or provider-backed play.

## Why This Is Not Closing Yet

The issue requires product-owned authentication, token lifecycle decisions, hosted provider-key custody, and online failure behavior. A local CLI stub would create unsafe expectations and could imply unsupported OpenAI or Anthropic OAuth flows. This document defines the gate for a future implementation PR.

## Target Experience

1. The user runs `girlfriend-in-cli login`.
2. The CLI opens a product-owned browser login or displays a device-code flow.
3. The product returns a short-lived CLI session token scoped to this app.
4. The user runs `girlfriend-in-cli` and can play without pasting provider API keys.
5. Provider calls happen through the product backend when the user chooses hosted play.

## Architecture Boundary

- The CLI never receives raw OpenAI or Anthropic provider keys.
- Product login is separate from provider authentication.
- Hosted play uses a product session token exchanged with a product API.
- Local API-key play remains available for offline or self-managed users.
- CLI copy must not claim provider OAuth support unless a provider officially supports the exact flow.

## Security / Privacy / Runtime Gate

- Auth owner: identify the product service that owns account creation, login, logout, and token revocation.
- Token storage: define OS keychain support, plaintext fallback policy, expiry, refresh, and logout deletion.
- Provider-key custody: prove provider keys stay server-side and are never serialized into CLI config or logs.
- Hosted-vs-local boundary: document how users choose hosted play versus local key play.
- Offline behavior: define user-facing errors for expired tokens, revoked tokens, network loss, and backend outage.
- Abuse/cost controls: define rate limits, model limits, billing quota behavior, and account suspension path.
- Privacy: define what account, session, and transcript metadata is sent to the product backend.
- Observability: ensure logs redact tokens, account identifiers where possible, prompts, and provider responses by default.

## Implementation Acceptance Criteria

- `girlfriend-in-cli login` completes a product-owned login flow and stores only a scoped product token.
- `girlfriend-in-cli logout` removes the token and future hosted calls fail closed.
- Hosted play calls the product backend and never requires local provider keys.
- Local provider-key play still works without a product account.
- Token expiry and backend outage paths show clear recovery instructions.
- Tests cover token storage, logout, expired token behavior, hosted/local mode selection, and copy that avoids fake provider OAuth.

## Verification Before Close

- Run focused CLI and remote tests once implementation exists.
- Inspect generated config and logs to confirm no provider keys or bearer tokens are persisted in plaintext unexpectedly.
- Manually exercise login, hosted play, logout, expired token, and offline startup.
- The PR body may use `Closes #7` only after the implementation acceptance criteria and gate are evidenced.
