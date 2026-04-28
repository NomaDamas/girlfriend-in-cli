![girlfriend-in-cli hero](assets/readme/hero-banner.png)

![girlfriend-in-cli solo pepe](assets/readme/solo-pepe.png)

**⚡ Wake up, nerds.**

**💘 An AI girlfriend or boyfriend that lives inside your terminal. Real personas, real conversations, your shell as a chat room.**

`girlfriend-in-cli` is a terminal-native romance simulator: weird, playful, and surprisingly sincere. Pick a character, build your own, and just live with someone in your CLI.

The hook is not the gimmick — it’s the personas.

- 💬 characters with mood, memory, and texting style of their own
- 📷 they can send photos when it feels right (opt-in)
- 🎙️ voice in, voice out (macOS)
- 🎵 ambient music that follows the vibe of the chat
- 🛠️ a Persona Studio so you can build the exact character you want
- 💾 saved sessions, resume, transcript export

Less "open another tab." More "someone in your shell just texted you."

# Demo
https://github.com/user-attachments/assets/1126916c-6cdb-4e92-bfd6-53f6cf35ea15

# Index

- [✨ Why this exists](#-why-this-exists)
- [🛠️ What it does](#️-what-it-does)
- [🧭 The vibe](#-the-vibe)
- [🚀 Quick Start](#-quick-start)
- [📝 Release Notes](#-release-notes)
- [🎮 First run](#-first-run)
- [🧠 Build your own persona harness](#-build-your-own-persona-harness)
- [⌨️ Example commands](#️-example-commands)
- [🌐 Remote mode](#-remote-mode)
- [🎛️ In-app controls](#️-in-app-controls)
- [🗂️ Sessions and export](#️-sessions-and-export)
- [🤝 Contributing](#-contributing)
- [✅ Verification](#-verification)
- [🧩 Local-only ECC setup](#-local-only-ecc-setup)
- [⚖️ License](#️-license)


---

## ✨ Why this exists

You already live in the terminal.

So the terminal might as well stop being only:

- shells
- logs
- tests
- deployments

…and quietly turn into:

- 💌 a place where someone you actually like texts you
- 🎭 a stage for characters you build yourself
- 🌙 a less lonely place during long sessions
- 📖 a tiny ongoing story your shell remembers

`girlfriend-in-cli` is for:

- people who want a character in their shell
- creators who want to build personas and live with them
- terminal-first builders who think their shell deserves a roommate
- anyone who wanted a romance sim but didn't want to leave their terminal

---

## 🛠️ What it does

- 💬 Runs a terminal-only chat UI with Rich
- 🧑‍🤝‍🧑 Lets you chat with bundled boyfriend / girlfriend personas
- 💾 Supports saved sessions and resume flow
- 📩 Sends follow-up nudges if you leave the other side hanging
- 🔊 Supports voice output on macOS via `say`
- 🎙️ Supports voice input through a custom transcription command
- 🧪 Includes a Persona Studio for importing, editing, and creating personas
- 🔎 Can auto-generate personas from a **name, link, or short prompt**
- 🌐 Supports remote persona compilation and hosting workflows
- 📊 Exposes a live ECC trace/debug panel during runs
- 📷 Optional persona-initiated photo sending via `--photos` (OpenAI image gen, capped at 5 per session)

---

## 🧭 The vibe

The point of this project is not "fake romance."

The point is that **a character can live inside your shell** — with a voice, a mood, a memory, a phone, and a Tuesday-night texting cadence — and that's a kind of company you can't get from a chat web app.

We care about:

- 🎭 personas that feel like an actual person, not an assistant
- 🪢 conversations that stretch over days and remember themselves
- 🛠️ a sandbox where you can author the exact character you'd want around
- 🧊 a tone that respects you instead of preaching at you

The romance frame is a vibe, not a sermon. Whatever you take away from spending time here is yours.

---

## 🚀 Quick Start

### Option A — install with Homebrew

```bash
brew tap NomaDamas/girlfriend-in-cli https://github.com/NomaDamas/brew-girlfriend-in-cli.git
brew install girlfriend-in-cli
mygf
```

This is the easiest path for most users.

Preferred launch commands:

```bash
mygf
girlfriend-in-cli
```

> Note: true bare `brew install girlfriend-in-cli` for a fresh machine would require acceptance into `homebrew/core`.  
> Right now the project ships through a public custom tap, which is the realistic path at this stage.

### Option B — install from source
From the repository root:

```bash
uv sync --extra dev
uv run mygf
```

If `uv` is not installed yet:

```bash
brew install uv
```

That gives you:

- ✅ a local `.venv`
- ✅ editable project install from `pyproject.toml`
- ✅ the `mygf` shortcut via `uv run`
- ✅ the `girlfriend-in-cli` entrypoint
- ✅ bundled persona discovery

If you prefer activating the environment manually:

```bash
source .venv/bin/activate
mygf
```

If you want to run tests:

```bash
uv run pytest
```

If you want a full smoke check:

```bash
uv run bash scripts/smoke.sh
```

### Release-aware updates

On startup, the app can check the latest **stable GitHub Release** and prompt before updating.

- ✅ checks releases, not random commits on `main`
- ✅ only updates when you explicitly say yes
- ✅ supports safe upgrade flows for release installs
- ✅ updates the Homebrew tap formula automatically on release publish
- ✅ designed to protect users from unstable in-between pushes

---

## 📝 Release Notes

Recent release line:

- `v0.1.6.0` — current stable release. Adds optional persona-initiated photo sending via `--photos`. See [RELEASE_NOTES_v0.1.6.0.md](RELEASE_NOTES_v0.1.6.0.md).
- `v0.1.5.0` — AI-companion repositioning + deprecated model cleanup. See [RELEASE_NOTES_v0.1.5.0.md](RELEASE_NOTES_v0.1.5.0.md).
- `v0.1.4.1` — previous stable release

Release pages:

- GitHub Releases: [github.com/NomaDamas/girlfriend-in-cli/releases](https://github.com/NomaDamas/girlfriend-in-cli/releases)

If you want the latest packaged version:

```bash
brew tap NomaDamas/girlfriend-in-cli https://github.com/NomaDamas/brew-girlfriend-in-cli.git
brew upgrade girlfriend-in-cli
```

If you install from source, pull latest `main` and resync:

```bash
git pull origin main
uv sync --extra dev
```

---

## 🎮 First run

Launch the app:

```bash
mygf
```

When the main menu opens, you can:

- start a new chat
- resume an old session
- open Persona Studio
- change provider / language / performance settings

If you want cloud model-backed chat, set an API key first in your shell or via the in-app Settings menu.
For local inference, you can also use Ollama with a local endpoint + model.

Examples:

```bash
export OPENAI_API_KEY=your_key_here
mygf
```

or

```bash
export ANTHROPIC_API_KEY=your_key_here
mygf --provider anthropic
```

or

```bash
mygf --provider ollama --model llama3.2 --ollama-base-url http://127.0.0.1:11434/v1
```

---

## 🧠 Build your own persona harness

This project is not limited to bundled characters.

One of the real hooks is that you can build your own **persona harness**:

- import a persona from JSON
- create one manually in Persona Studio
- generate one from a **name**
- generate one from a **link**
- generate one from a short **description / vibe**

Auto-generation is routed through **OpenAI / Anthropic only**:

- **OpenAI** keeps live web-search grounding
- **Anthropic** uses model synthesis plus fetched URL text
- **Ollama** is for chat/runtime, not Persona Studio generation

The idea is simple:

You should be able to author the exact character you want to spend time with.

That means you can build:

- 😘 a flirty persona
- 🧊 a cold persona
- 😜 a playful persona
- 🔗 someone based on a public figure vibe
- 🧩 a totally custom character with your own style rules

In other words:

**don’t just use personas — build your own persona harness.**

---

## ⌨️ Example commands

Run the app:

```bash
mygf
```

Launch with a specific persona:

```bash
mygf --persona personas/wonyoung-idol.json
```

Use Anthropic instead of OpenAI:

```bash
mygf --provider anthropic
```

Use a local Ollama model:

```bash
mygf --provider ollama --model llama3.2
```

Use a specific performance profile:

```bash
mygf --performance turbo
mygf --performance balanced
mygf --performance cinematic
```

Enable voice output:

```bash
mygf --voice-output
```

Resume a saved session:

```bash
mygf --resume sessions/your-session.json
```

List bundled personas:

```bash
mygf --list-personas
```

---

## 🌐 Remote mode

If you want server-hosted personas and remote runtime generation:

```bash
girlfriend-generator \
  --provider remote \
  --server-base-url http://127.0.0.1:8787 \
  --persona-id persona_123
```

You can also compile a remote persona on the fly:

```bash
girlfriend-generator \
  --provider remote \
  --server-base-url http://127.0.0.1:8787 \
  --compile-remote \
  --display-name Yuna \
  --relationship-mode girlfriend \
  --context-notes "designer in Seongsu with dry humor" \
  --context-link https://instagram.com/example \
  --context-snippet "what are you doing"
```

Remote mode is useful when you want:

- server-owned persona generation
- hosted runtime logic
- more dynamic persona compilation flows

while keeping the **terminal UI, transcript export, and local interaction loop** in this repo.

---

## 🎛️ In-app controls

- `Enter` — send message
- `Esc` — clear draft / go back from empty draft
- `/help` — show command help
- `/trace` — toggle trace panel
- `/status` — print session state into chat
- `/export` — export transcript
- `/voice on` / `/voice off` — toggle voice output
- `/listen` — run voice input command
- `/back` — return to main menu
- `/quit` — quit session

---

## 🗂️ Sessions and export

Sessions are exported as:

- JSON
- Markdown

under the local `sessions/` directory by default.

That makes it easy to:

- review conversations
- resume old chats
- inspect persona behavior
- reuse transcripts for prompting or iteration

---

## 🤝 Contributing

This repo is open to fork-and-PR contributions.

Typical flow:

1. Fork the repo
2. Create a branch from `main`
3. Make a focused change
4. Run tests
5. Open a PR

Start here:

- [CONTRIBUTING.md](CONTRIBUTING.md)

Good contribution targets:

- terminal UX polish
- persona tuning
- provider integrations
- docs and release workflow improvements

---

## ✅ Verification

Run the test suite:

```bash
python3 -m pytest
```

Run the smoke checks:

```bash
bash scripts/smoke.sh
```

The smoke path verifies:

- package import / compilation
- entrypoints
- persona discovery
- transcript export
- repository-root path behavior

---

## 🧩 Local-only ECC setup

This repository vendors Everything Claude Code assets **project-locally**.

It uses:

- `AGENTS.md`
- `.codex/AGENTS.md`
- `.agents/skills/`

It does **not** modify global Codex defaults or your `~/.codex` setup unless you explicitly choose to do that yourself.

---
## ⚖️ License

This project is licensed under **Elastic License 2.0**.

That means people can use, modify, and distribute the code,
but they cannot turn it into a competing hosted/managed service.

This is intentional:
- the terminal client can stay public
- the monetizable server-side moat remains protected
