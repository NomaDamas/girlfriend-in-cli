![girlfriend-in-cli hero](assets/readme/hero-banner.png)

![girlfriend-in-cli meme](assets/readme/secondary-banner.jpeg)

# girlfriend-in-cli

**⚡ Wake up, nerds.**

**💘 Your CLI boyfriend or girlfriend chats with you — sharpen your social skills and discover your charm.**

`girlfriend-in-cli` is a terminal-native romance simulator for the AI-native era: a weird, playful, and surprisingly sincere open-source project for vibe coders who spend too much time in the shell and not enough time practicing how to talk like a human.

This is not just a joke app.

It is built around a simple belief:

> If developers are getting better at talking to models every day,  
> they should also get better at talking to people.

So yes:

- 💻 code in the terminal
- ⏳ waste less Slack time
- 🌙 survive lonely vibe-coding sessions
- 🫶 practice warmth, timing, empathy, and charm
- 🧠 build your own persona harness and talk to the energy you want

**Don’t just grind code. Grind charm.**

---

## ✨ Why this exists

Modern builders already live in the terminal.

That means the terminal can become more than a place for:

- shells
- logs
- tests
- deployments

It can also become a place to practice:

- 💬 conversation flow
- ⏱️ emotional timing
- 👀 reading reactions
- 😏 flirting without sounding robotic
- 🧊 becoming a slightly less socially dead T-type developer

`girlfriend-in-cli` is for:

- lonely vibe coders
- terminal-first builders
- developers who want to feel a little more human while they work
- people who want to practice social instinct inside the same environment where they build

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

---

## 🧭 The philosophy

**⚡ Wake up, nerds.**

The point of this project is not “fake romance.”

The point is that the AI-native era should not produce developers who are only good at:

- prompting models
- shipping faster
- writing more code

It should also produce developers who are better at:

- empathy
- timing
- tone
- emotional calibration
- making other people feel understood

If you can train coding instincts in the terminal, maybe you can train social instincts there too.

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
bash scripts/bootstrap.sh
source .venv/bin/activate
mygf
```

That gives you:

- ✅ a local virtualenv
- ✅ an editable install
- ✅ the `mygf` shortcut
- ✅ the `girlfriend-in-cli` entrypoint
- ✅ bundled persona discovery

If you want to run tests:

```bash
python3 -m pytest
```

If you want a full smoke check:

```bash
bash scripts/smoke.sh
```

### Release-aware updates

On startup, the app can check the latest **stable GitHub Release** and prompt before updating.

- ✅ checks releases, not random commits on `main`
- ✅ only updates when you explicitly say yes
- ✅ supports safe upgrade flows for release installs
- ✅ updates the Homebrew tap formula automatically on release publish
- ✅ designed to protect users from unstable in-between pushes

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

If you want model-backed chat, set an API key first in your shell or via the in-app Settings menu.

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

---

## 🧠 Build your own persona harness

This project is not limited to bundled characters.

One of the real hooks is that you can build your own **persona harness**:

- import a persona from JSON
- create one manually in Persona Studio
- generate one from a **name**
- generate one from a **link**
- generate one from a short **description / vibe**

The idea is simple:

You should be able to create the exact conversational energy you want to train against.

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

## 🛣️ Project status

This project is actively evolving as a terminal-native social simulator.

Current directions include:

- better landing page / title rendering
- more playful main-menu flows
- persona generation and editing improvements
- random chat discovery flows
- stronger remote persona pipelines

---

## 📣 One-line pitch

**Your CLI boyfriend or girlfriend chats with you — sharpen your social skills and discover your charm. Wake up, nerds.**

---

## ⚖️ License

This project is licensed under **Elastic License 2.0**.

That means people can use, modify, and distribute the code,
but they cannot turn it into a competing hosted/managed service.

This is intentional:
- the terminal client can stay public
- the monetizable server-side moat remains protected
