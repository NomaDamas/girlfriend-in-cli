# Issue #12: YouTube Persona Generation

This PR adds the local normalization layer for YouTube persona sources without
claiming to download media or run hosted STT yet.

## Implemented

- Validate supported YouTube video URLs:
  - `youtube.com/watch?v=...`
  - `youtu.be/...`
  - `/shorts/...`
  - `/embed/...`
- Build a source-attributed persona context from:
  - video metadata
  - captions
  - STT transcript text
  - deep research notes
- Route YouTube URLs through this context layer in the existing deep research
  persona generator.
- Add Persona Studio example copy for YouTube URLs.

## Security / Privacy / Runtime Gate

- No raw audio/video is downloaded in this PR.
- No captions or transcripts are persisted by the ingest module.
- Source context explicitly warns synthesis not to claim private facts.
- Real caption/STT adapters must document provider boundaries, retention, and
  copyright/source-attribution behavior before this issue can use `Closes`.

## Not Closing Yet

This does not yet implement live caption extraction, STT fallback execution, or
hosted deep-research orchestration. The PR should use `Refs #12`.
