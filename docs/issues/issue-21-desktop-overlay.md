# Issue #21: Desktop Companion Overlay

Refs #21

## Status

Design scaffold. This does not implement an overlay window, desktop pet runtime, OS integration, or task-state event bridge.

## Why This Is Not Closing Yet

Always-on-top desktop UI and proactive companion behavior require runtime selection, OS permission handling, event sourcing, process lifecycle management, and manual smoke evidence. A placeholder notification would not satisfy the issue and could create privacy or stability risks.

## Target Experience

1. The user opts into desktop companion mode.
2. A small companion window appears above normal windows without blocking work.
3. The companion reflects session states such as idle, thinking, typing, waiting, done, and celebration.
4. On task completion, the active persona produces one proactive line.
5. The user can dismiss or disable the overlay cleanly.

## Runtime Shape

- Start with one explicitly supported OS/runtime before claiming cross-platform support.
- Keep terminal-first play intact; desktop mode is optional.
- Overlay events should come from explicit app/session state, not screen scraping.
- Persona-aware lines should use existing relationship/session context when available.
- The overlay process must exit when the CLI exits or when the user disables it.

## Security / Privacy / Runtime Gate

- Supported OS/runtime: choose the first target, packaging path, and minimum OS version.
- Always-on-top mechanism: document the windowing library/API, focus behavior, click-through behavior, and teardown.
- Permission UX: define prompts and fallbacks for notifications, accessibility, screen recording, or automation if any are needed.
- Event source: define which session events drive states and prove no private editor contents are collected.
- Proactive line policy: define rate limits, persona context use, and how to avoid surprising output during sensitive work.
- Failure UX: define behavior when the overlay cannot start, crashes, loses IPC, or outlives the CLI.
- Resource limits: cap CPU, memory, animation loop work, and background model calls.
- Manual overlay smoke: require evidence that the overlay opens, stays above windows, updates state, and exits cleanly.

## Implementation Acceptance Criteria

- A documented opt-in command or flag starts desktop companion mode.
- The overlay shows at least idle, thinking/typing, and completed states.
- Task completion triggers exactly one persona-aware line per completion event unless the user asks for more.
- The user can disable desktop mode and the process exits cleanly.
- The implementation has a tested fallback path for unsupported OS/runtime.
- Manual smoke evidence is attached for the supported OS/runtime.

## Verification Before Close

- Run focused unit tests for event mapping and lifecycle behavior once implementation exists.
- Manually smoke the overlay on the supported OS/runtime.
- Inspect logs and event payloads to confirm editor contents, transcripts, and tokens are not collected by overlay plumbing.
- The PR body may use `Closes #21` only after the implementation acceptance criteria and gate are evidenced.
