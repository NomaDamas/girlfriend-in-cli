from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .app import AppConfig, run_chat_app
from .paths import (
    bundled_persona_dir,
    bundled_session_dir,
    resolve_persona_path,
    resolve_session_dir,
)
from .personas import discover_personas
from .remote import (
    compile_remote_persona,
    fetch_remote_persona,
    fetch_remote_persona_by_slug,
    list_remote_personas,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Terminal-only romance simulation chat for vibe coding breaks."
    )
    parser.add_argument(
        "--persona",
        type=Path,
        help="Path to a persona JSON/YAML file.",
    )
    parser.add_argument(
        "--provider",
        choices=["heuristic", "openai", "anthropic", "remote"],
        default="heuristic",
        help="Reply generator backend.",
    )
    parser.add_argument(
        "--model",
        help="Provider-specific model override.",
    )
    parser.add_argument(
        "--performance",
        choices=["turbo", "balanced", "cinematic"],
        default="turbo",
        help="Latency profile. turbo is the fastest path.",
    )
    parser.add_argument(
        "--voice-output",
        action="store_true",
        help="Enable voice output. On macOS this uses the built-in say command.",
    )
    parser.add_argument(
        "--voice-input-command",
        help="Command that prints a voice transcript to stdout.",
    )
    parser.add_argument(
        "--server-base-url",
        help="Base URL for the remote persona/runtime server.",
    )
    parser.add_argument(
        "--persona-id",
        help="Remote persona identifier used with --provider remote.",
    )
    parser.add_argument(
        "--persona-slug",
        help="Remote persona slug used with --provider remote.",
    )
    parser.add_argument(
        "--compile-remote",
        action="store_true",
        help="Compile a remote persona before launching chat.",
    )
    parser.add_argument(
        "--list-remote-personas",
        action="store_true",
        help="List personas from the remote hosting server and exit.",
    )
    parser.add_argument(
        "--display-name",
        help="Display name for remote persona compilation.",
    )
    parser.add_argument(
        "--age",
        type=int,
        default=25,
        help="Adult age used for remote persona compilation.",
    )
    parser.add_argument(
        "--relationship-mode",
        choices=["crush", "girlfriend"],
        default="crush",
        help="Relationship mode for remote persona compilation.",
    )
    parser.add_argument(
        "--context-notes",
        default="",
        help="Free-form persona context used for remote compilation.",
    )
    parser.add_argument(
        "--context-link",
        action="append",
        default=[],
        help="Public link used for remote persona compilation. Repeatable.",
    )
    parser.add_argument(
        "--context-snippet",
        action="append",
        default=[],
        help="Short style snippet used for remote persona compilation. Repeatable.",
    )
    parser.add_argument(
        "--session-dir",
        type=Path,
        default=None,
        help="Directory where exported chat transcripts are stored.",
    )
    parser.add_argument(
        "--no-export-on-exit",
        action="store_true",
        help="Disable automatic transcript export when the app exits.",
    )
    parser.add_argument(
        "--no-trace",
        action="store_true",
        help="Hide the ECC trace panel.",
    )
    parser.add_argument(
        "--list-personas",
        action="store_true",
        help="List bundled personas and exit.",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        help="Resume a previous session from an exported JSON file.",
    )
    return parser


def _has_any_flags(args: argparse.Namespace) -> bool:
    return any([
        args.persona,
        args.provider != "heuristic",
        args.list_personas,
        args.list_remote_personas,
        getattr(args, "resume", None),
        args.compile_remote,
        args.server_base_url,
        args.persona_id,
        args.persona_slug,
    ])


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    persona_dir = bundled_persona_dir()
    bundled_personas = discover_personas(persona_dir) if persona_dir.exists() else []

    if args.list_personas:
        for persona_path in bundled_personas:
            print(persona_path)
        return 0

    if args.list_remote_personas:
        if not args.server_base_url:
            parser.error("--list-remote-personas requires --server-base-url.")
        for item in list_remote_personas(args.server_base_url):
            print(f"{item['slug']}\t{item['persona_id']}\t{item['display_name']}")
        return 0

    # Show main menu when run without flags in a TTY
    if not _has_any_flags(args) and sys.stdin.isatty() and bundled_personas:
        result = _show_main_menu(bundled_personas, args)
        if result is None:
            return 0
        args, persona_path, resume_path = result
        return _launch_chat(args, parser, persona_path, None, resume_path)

    persona_override = None
    if args.provider == "remote":
        if not args.server_base_url:
            parser.error("--provider remote requires --server-base-url.")
        persona_id = args.persona_id
        if args.compile_remote:
            if not args.display_name:
                parser.error("--compile-remote requires --display-name.")
            compiled = compile_remote_persona(
                base_url=args.server_base_url,
                display_name=args.display_name,
                age=args.age,
                relationship_mode=args.relationship_mode,
                context_notes=args.context_notes,
                context_links=args.context_link,
                context_snippets=args.context_snippet,
            )
            persona_id = compiled["persona_id"]
            args.persona_id = persona_id
            args.persona_slug = compiled["persona_pack"]["slug"]
        if persona_id:
            persona_override = fetch_remote_persona(args.server_base_url, persona_id)
            persona_path = Path(f"remote/{persona_id}.json")
        elif args.persona_slug:
            persona_override = fetch_remote_persona_by_slug(
                args.server_base_url,
                args.persona_slug,
            )
            persona_path = Path(f"remote/{args.persona_slug}.json")
        else:
            parser.error(
                "--provider remote requires --persona-id, --persona-slug, or --compile-remote."
            )
    else:
        if args.persona:
            persona_path = resolve_persona_path(args.persona)
        elif len(bundled_personas) > 1 and sys.stdin.isatty():
            persona_path = _pick_persona_interactive(bundled_personas)
        elif bundled_personas:
            persona_path = bundled_personas[0]
        else:
            parser.error("No persona file found. Add one under personas/ or pass --persona.")
        persona_path = resolve_persona_path(persona_path)

    resume_path = None
    if getattr(args, "resume", None):
        resume_path = Path(args.resume).expanduser().resolve()
        if not resume_path.exists():
            parser.error(f"Resume file not found: {resume_path}")

    return _launch_chat(args, parser, persona_path, persona_override, resume_path)


def _launch_chat(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    persona_path: Path,
    persona_override: object | None,
    resume_path: Path | None,
) -> int:
    config = AppConfig(
        persona_path=persona_path,
        persona_override=persona_override,
        provider_name=args.provider,
        provider_model=args.model,
        server_base_url=args.server_base_url,
        persona_id=args.persona_id or args.persona_slug,
        performance_mode=args.performance,
        voice_output=args.voice_output,
        voice_input_command=args.voice_input_command,
        session_dir=resolve_session_dir(args.session_dir),
        export_on_exit=not args.no_export_on_exit,
        show_trace=not args.no_trace,
        resume_path=resume_path,
    )
    return run_chat_app(config)


_LOGO = r"""
   ___  _      _  __     _          _
  / __\(_)_ __| |/ _|_ __(_) ___ _ __  __| |
 / _  | | '__| | |_| '__| |/ _ \ '_ \/ _` |
/ /_\_| | |  | |  _| |  | |  __/ | | \__,_|
\____/|_|_|  |_|_| |_|  |_|\___|_| |_|___/
 ___                          _
/ _ \___ _ __   ___ _ __ __ _| |_ ___  _ __
/ /_\/ _ \ '_ \ / _ \ '__/ _` | __/ _ \| '__|
/ /_\\  __/ | | |  __/ | | (_| | || (_) | |
\____/\___|_| |_|\___|_|  \__,_|\__\___/|_|
"""

_MODE_ICONS = {
    "girlfriend": "💕",
    "crush": "💘",
}

_PERF_ICONS = {
    "turbo": "⚡",
    "balanced": "🎵",
    "cinematic": "🎬",
}


def _show_main_menu(
    bundled_personas: list[Path],
    args: argparse.Namespace,
) -> tuple[argparse.Namespace, Path, Path | None] | None:
    from rich.columns import Columns
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    console = Console()
    console.clear()

    # ASCII art logo with gradient
    logo_text = Text(_LOGO)
    logo_text.stylize("bold magenta")
    console.print(Panel(
        logo_text,
        border_style="bright_magenta",
        padding=(0, 2),
        subtitle="[dim italic]terminal romance simulator  |  v0.1.0[/dim italic]",
    ))

    # Current settings bar
    perf_icon = _PERF_ICONS.get(args.performance, "")
    settings_bar = Text.assemble(
        ("  Provider: ", "dim"),
        (args.provider, "bold cyan"),
        ("  |  Performance: ", "dim"),
        (f"{perf_icon} {args.performance}", "bold yellow"),
        ("  |  Voice: ", "dim"),
        ("ON" if args.voice_output else "OFF", "bold green" if args.voice_output else "dim"),
        ("  |  Trace: ", "dim"),
        ("ON" if not args.no_trace else "OFF", "bold green" if not args.no_trace else "dim"),
    )
    console.print(settings_bar)
    console.print()

    # Menu cards
    cards = [
        Panel(
            "[bold white]New Chat[/bold white]\n[dim]Start a fresh conversation\nwith a persona[/dim]",
            border_style="bright_magenta",
            title="[bold bright_magenta]1[/bold bright_magenta]",
            width=28,
            padding=(1, 2),
        ),
        Panel(
            "[bold white]Create[/bold white]\n[dim]Build your own custom\npersona from scratch[/dim]",
            border_style="bright_green",
            title="[bold bright_green]2[/bold bright_green]",
            width=28,
            padding=(1, 2),
        ),
        Panel(
            "[bold white]Resume[/bold white]\n[dim]Continue a previous\nchat session[/dim]",
            border_style="bright_cyan",
            title="[bold bright_cyan]3[/bold bright_cyan]",
            width=28,
            padding=(1, 2),
        ),
        Panel(
            "[bold white]Settings[/bold white]\n[dim]Provider, performance\nvoice, music[/dim]",
            border_style="bright_yellow",
            title="[bold bright_yellow]4[/bold bright_yellow]",
            width=28,
            padding=(1, 2),
        ),
    ]
    console.print(Columns(cards, padding=(0, 1)))
    console.print()

    while True:
        try:
            choice = input("  \033[1;35m>\033[0m Select [\033[1;35m1\033[0m/\033[1;32m2\033[0m/\033[1;36m3\033[0m/\033[1;33m4\033[0m/\033[2mq\033[0m]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n  [dim]Goodbye.[/dim]")
            return None

        if choice == "q":
            console.print("\n  [dim]Goodbye.[/dim]")
            return None

        if choice == "1":
            console.print()
            persona_path = _pick_persona_interactive(bundled_personas, console)
            return args, resolve_persona_path(persona_path), None

        if choice == "2":
            console.print()
            created = _create_persona_wizard(console)
            if created is not None:
                return args, created, None
            console.clear()
            return _show_main_menu(bundled_personas, args)

        if choice == "3":
            console.print()
            resume_result = _pick_session_to_resume(console, bundled_personas)
            if resume_result is None:
                continue
            persona_path, resume_path = resume_result
            return args, resolve_persona_path(persona_path), resume_path

        if choice == "4":
            console.print()
            _settings_menu(console, args)
            console.clear()
            return _show_main_menu(bundled_personas, args)

        console.print("  [red]1, 2, 3, 4, or q[/red]")


def _create_persona_wizard(console: "Console") -> Path | None:  # type: ignore[name-defined]
    from rich.panel import Panel
    from rich.text import Text

    console.print(Panel(
        "[bold bright_green]  Persona Creator  [/bold bright_green]\n\n"
        "[dim]Build a custom persona step by step.\n"
        "Fill in the details to create your own character.[/dim]",
        border_style="bright_green",
        width=60,
        padding=(1, 2),
    ))

    def _ask(prompt: str, default: str = "") -> str:
        suffix = f" [dim]({default})[/dim]" if default else ""
        try:
            val = input(f"  \033[1;32m>\033[0m {prompt}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            return default
        return val if val else default

    def _ask_list(prompt: str, hint: str = "") -> list[str]:
        hint_str = f" [dim]({hint})[/dim]" if hint else ""
        try:
            val = input(f"  \033[1;32m>\033[0m {prompt}{hint_str}: ").strip()
        except (EOFError, KeyboardInterrupt):
            return []
        return [item.strip() for item in val.split(",") if item.strip()]

    console.print("\n  [bold]Basic Info[/bold]")
    console.print("  [dim]─────────────────────────────[/dim]")
    name = _ask("Name (이름)", "")
    if not name:
        console.print("  [red]Name is required.[/red]")
        return None

    age_str = _ask("Age (나이)", "25")
    try:
        age = int(age_str)
        if age < 20:
            console.print("  [red]Must be 20 or older.[/red]")
            return None
    except ValueError:
        age = 25

    console.print("\n  [bold]Relationship[/bold]")
    console.print("  [dim]─────────────────────────────[/dim]")
    console.print("  [dim]1) girlfriend (연인)  2) crush (썸)[/dim]")
    mode_choice = _ask("Relationship mode", "2")
    mode = "girlfriend" if mode_choice == "1" else "crush"

    console.print("\n  [bold]Personality[/bold]")
    console.print("  [dim]─────────────────────────────[/dim]")
    background = _ask("Background (배경)", f"{name}은(는) 서울에서 일하는 {age}세 성인이다.")
    situation = _ask("Situation (상황)", "가볍게 대화하며 호감을 키워가는 단계")
    texting_style = _ask("Texting style (말투)", "짧고 리듬감 있게, 장난과 진심을 섞어서")

    console.print("\n  [bold]Details[/bold]  [dim](comma-separated)[/dim]")
    console.print("  [dim]─────────────────────────────[/dim]")
    interests = _ask_list("Interests (관심사)", "e.g. 카페, 영화, 러닝")
    if not interests:
        interests = ["카페", "산책", "음악"]
    soft_spots = _ask_list("Soft spots (약점)", "e.g. 세심한 안부, 센스 있는 장난")
    if not soft_spots:
        soft_spots = ["성의 있는 리액션", "자연스러운 배려"]
    boundaries = _ask_list("Boundaries (경계선)", "e.g. 집착, 무성의한 답변")
    if not boundaries:
        boundaries = ["과한 집착", "감정 회피"]

    console.print("\n  [bold]Greeting & Style[/bold]")
    console.print("  [dim]─────────────────────────────[/dim]")
    greeting = _ask("First message (첫 인사)", f"야, 뭐 해? 심심해서 톡했어 :)")
    accent_color = _ask("Theme color (magenta/cyan/yellow/green)", "magenta")
    if accent_color not in ("magenta", "cyan", "yellow", "green", "red", "blue"):
        accent_color = "magenta"

    console.print("\n  [bold]Extra Context[/bold]  [dim](optional, paste text or leave empty)[/dim]")
    console.print("  [dim]─────────────────────────────[/dim]")
    context_desc = _ask("Description or notes about this person", "")

    # Build the persona JSON
    from .session_io import slugify
    persona_data = {
        "name": name,
        "age": age,
        "relationship_mode": mode,
        "background": background,
        "situation": situation,
        "texting_style": texting_style,
        "interests": interests,
        "soft_spots": soft_spots,
        "boundaries": boundaries,
        "greeting": greeting,
        "accent_color": accent_color,
        "provider_system_hint": f"{name}의 말투와 성격을 자연스럽게 유지한다.",
        "context_summary": context_desc if context_desc else f"{name}과(와)의 대화 시뮬레이션",
        "typing": {"min_seconds": 0.9, "max_seconds": 3.2},
        "nudge_policy": {
            "idle_after_seconds": 35,
            "follow_up_after_seconds": 70,
            "max_nudges": 2,
            "templates": [
                f"왜 답장 안 해? 나 기다리고 있었는데.",
                f"진짜 바쁜 거야? 아니면 일부러 뜸 들이는 거야?",
            ],
        },
        "style_profile": {
            "warmth": 0.7,
            "teasing": 0.6,
            "directness": 0.5,
            "message_length": "short-medium",
            "emoji_level": "low",
            "signature_phrases": ["ㅋㅋ", "ㅎㅎ", "진짜?"],
        },
        "initiative_profile": {
            "min_interval_seconds": 600,
            "max_interval_seconds": 2400,
            "spontaneity": 0.55,
            "opener_templates": [
                f"야, 뭐 해? 갑자기 네 생각나서 톡했어.",
                f"심심해서 왔어. 오늘 뭐 했어?",
            ],
            "follow_up_templates": [
                "그냥 네가 뭐 하나 궁금해서.",
                "별 건 아닌데, 톡하고 싶었어.",
            ],
        },
    }

    # Save to personas/
    filename = f"{slugify(name)}-custom.json"
    persona_dir = bundled_persona_dir()
    persona_dir.mkdir(parents=True, exist_ok=True)
    save_path = persona_dir / filename
    save_path.write_text(
        json.dumps(persona_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    console.print(f"\n  [bold green]Persona saved: {save_path.name}[/bold green]")
    console.print(f"  [bold green]Starting chat with {name}...[/bold green]\n")
    return save_path


def _pick_session_to_resume(
    console: "Console",  # type: ignore[name-defined]
    bundled_personas: list[Path],
) -> tuple[Path, Path] | None:
    from rich.panel import Panel
    from rich.text import Text

    session_dir = bundled_session_dir()
    if not session_dir.exists():
        console.print("  [yellow]No saved sessions yet.[/yellow]\n")
        return None

    session_files = sorted(session_dir.glob("*.json"), reverse=True)
    if not session_files:
        console.print("  [yellow]No saved sessions yet.[/yellow]\n")
        return None

    session_summaries = []
    for sf in session_files[:8]:
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            persona_name = data.get("persona", {}).get("name", "?")
            msg_count = len(data.get("messages", []))
            mode = data.get("persona", {}).get("relationship_mode", "?")
            session_summaries.append({
                "path": sf,
                "persona_name": persona_name,
                "msg_count": msg_count,
                "mode": mode,
            })
        except Exception:
            session_summaries.append({
                "path": sf,
                "persona_name": "?",
                "msg_count": 0,
                "mode": "?",
            })

    items = []
    for i, s in enumerate(session_summaries, 1):
        icon = _MODE_ICONS.get(s["mode"], "💬")
        body = Text.assemble(
            (f" {icon} ", ""),
            (s["persona_name"], "bold white"),
            (f"  {s['msg_count']} msgs", "dim"),
            ("\n   ", ""),
            (s["path"].stem, "dim italic"),
        )
        items.append(Panel(
            body,
            border_style="bright_green",
            title=f"[bold bright_green]{i}[/bold bright_green]",
            width=50,
        ))

    console.print(Panel(
        "\n".join("" for _ in range(0)),  # spacer
        title="[bold bright_green]  Saved Sessions  [/bold bright_green]",
        border_style="bright_green",
        width=54,
        padding=(0, 0),
    ))
    for item in items:
        console.print(item)
    console.print()

    while True:
        try:
            raw = input(f"  \033[1;32m>\033[0m Select [1-{len(session_summaries)}] or \033[2mb\033[0m: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if raw.lower() == "b":
            return None
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(session_summaries):
                selected = session_summaries[idx]
                persona_name = selected["persona_name"]
                persona_path = _find_persona_by_name(persona_name, bundled_personas)
                if persona_path is None and bundled_personas:
                    persona_path = bundled_personas[0]
                elif persona_path is None:
                    console.print("  [red]No matching persona found.[/red]")
                    return None
                console.print(f"\n  [bold green]Resuming chat with {persona_name}...[/bold green]\n")
                return persona_path, selected["path"]
        except ValueError:
            pass
        console.print(f"  [red]1-{len(session_summaries)} or b[/red]")


def _find_persona_by_name(name: str, personas: list[Path]) -> Path | None:
    for p in personas:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("name") == name:
                return p
        except Exception:
            continue
    return None


def _settings_menu(console: "Console", args: argparse.Namespace) -> None:  # type: ignore[name-defined]
    from rich.panel import Panel
    from rich.text import Text

    providers = ["heuristic", "openai", "anthropic"]
    perfs = ["turbo", "balanced", "cinematic"]

    def _render() -> None:
        perf_icon = _PERF_ICONS.get(args.performance, "")
        body = Text.assemble(
            ("\n", ""),
            ("  [1] Provider       ", "bold yellow"),
            (args.provider, "bold cyan"),
            ("\n", ""),
            ("  [2] Performance    ", "bold yellow"),
            (f"{perf_icon} {args.performance}", "bold white"),
            ("\n", ""),
            ("  [3] Voice Output   ", "bold yellow"),
            ("ON " if args.voice_output else "OFF", "bold green" if args.voice_output else "dim red"),
            ("\n", ""),
            ("  [4] Trace Panel    ", "bold yellow"),
            ("ON " if not args.no_trace else "OFF", "bold green" if not args.no_trace else "dim red"),
            ("\n", ""),
        )
        console.print(Panel(
            body,
            title="[bold bright_yellow]  Settings  [/bold bright_yellow]",
            border_style="bright_yellow",
            width=50,
        ))

    _render()

    while True:
        try:
            raw = input("  \033[1;33m>\033[0m Select [1/2/3/4] or \033[2mb\033[0m: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return

        if raw == "b":
            return
        if raw == "1":
            current_idx = providers.index(args.provider) if args.provider in providers else 0
            args.provider = providers[(current_idx + 1) % len(providers)]
            console.print(f"  [green]Provider -> {args.provider}[/green]")
            return
        if raw == "2":
            current_idx = perfs.index(args.performance) if args.performance in perfs else 0
            args.performance = perfs[(current_idx + 1) % len(perfs)]
            console.print(f"  [green]Performance -> {args.performance}[/green]")
            return
        if raw == "3":
            args.voice_output = not args.voice_output
            console.print(f"  [green]Voice -> {'ON' if args.voice_output else 'OFF'}[/green]")
            return
        if raw == "4":
            args.no_trace = not args.no_trace
            console.print(f"  [green]Trace -> {'ON' if not args.no_trace else 'OFF'}[/green]")
            return
        console.print("  [red]1, 2, 3, 4, or b[/red]")


def _pick_persona_interactive(personas: list[Path], console: "Console | None" = None) -> Path:  # type: ignore[name-defined]
    from rich.columns import Columns
    from rich.console import Console as RichConsole
    from rich.panel import Panel
    from rich.text import Text

    if console is None:
        console = RichConsole()

    cards = []
    summaries = []
    for i, path in enumerate(personas, 1):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            name = data.get("name", path.stem)
            age = data.get("age", "?")
            mode = data.get("relationship_mode", "?")
            bg = (data.get("background") or "")[:50]
            interests = data.get("interests", [])[:3]
            soft_spots = data.get("soft_spots", [])[:2]
            greeting = (data.get("greeting") or "")[:40]
            accent = data.get("accent_color", "magenta")
            summaries.append({"name": name, "accent": accent})
        except Exception:
            name, age, mode, bg = path.stem, "?", "?", ""
            interests, soft_spots, greeting, accent = [], [], "", "magenta"
            summaries.append({"name": name, "accent": accent})

        icon = _MODE_ICONS.get(mode, "💬")
        interest_str = ", ".join(interests) if interests else "-"
        spot_str = ", ".join(soft_spots) if soft_spots else "-"

        body = Text.assemble(
            (f"  {icon} ", ""),
            (name, f"bold {accent}"),
            (f"  {age}세", "dim"),
            (f"  {mode}", f"italic {accent}"),
            ("\n\n", ""),
            ("  ", ""),
            (bg, "dim"),
            ("\n\n", ""),
            ("  Interests  ", "bold dim"),
            (interest_str, "white"),
            ("\n", ""),
            ("  Soft spots ", "bold dim"),
            (spot_str, "white"),
            ("\n\n", ""),
            (f'  "{greeting}"', f"italic {accent}"),
            ("\n", ""),
        )
        cards.append(Panel(
            body,
            border_style=accent,
            title=f"[bold]{i}[/bold]",
            width=42,
            padding=(1, 0),
        ))

    console.print(Columns(cards, padding=(0, 1), equal=True))
    console.print()

    while True:
        try:
            raw = input(f"  \033[1;35m>\033[0m Who do you want to talk to? [1-{len(personas)}]: ").strip()
            idx = int(raw) - 1
            if 0 <= idx < len(personas):
                s = summaries[idx]
                console.print(f"\n  [bold {s['accent']}]Starting chat with {s['name']}...[/bold {s['accent']}]\n")
                return personas[idx]
        except (ValueError, EOFError):
            pass
        console.print(f"  [red]1-{len(personas)}[/red]")
