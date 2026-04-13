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
        choices=["openai", "anthropic", "remote"],
        default="openai",
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
        args.provider not in ("openai",),
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
        while True:
            result = _show_main_menu(bundled_personas, args)
            if result is None:
                return 0
            args, persona_path, resume_path = result
            exit_code = _launch_chat(args, parser, persona_path, None, resume_path)
            if exit_code != 2:  # 2 = back to menu
                return exit_code
            # Re-discover personas (user may have created new ones)
            persona_dir = bundled_persona_dir()
            bundled_personas = discover_personas(persona_dir) if persona_dir.exists() else []
            args = build_parser().parse_args()  # reset args

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
            picked = _pick_persona_interactive(bundled_personas)
            persona_path = picked if picked is not None else bundled_personas[0]
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


_NERD_FRAMES = [
    "(•_•)  I just want someone to text me first...",
    "(•‿•)  Maybe today is the day...",
    "(✧ᴗ✧) ♡  Compiling feelings... 100%!",
]

_LOGO_LINES = [
    "          _      ______     _                __   _               ___ ",
    "   ____ _(_)____/ / __/____(_)__  ____  ____/ /  (_)___     _____/ (_)",
    "  / __ `/ / ___/ / /_/ ___/ / _ \\/ __ \\/ __  /  / / __ \\   / ___/ / / ",
    " / /_/ / / /  / / __/ /  / /  __/ / / / /_/ /  / / / / /  / /__/ / /  ",
    " \\__, /_/_/  /_/_/ /_/  /_/\\___/_/ /_/\\__,_/  /_/_/ /_/   \\___/_/_/   ",
    "/____/                                                                 ",
]

_MODE_ICONS = {
    "girlfriend": "💕",
    "crush": "💘",
}

_PERF_ICONS = {
    "turbo": "⚡",
    "balanced": "🎵",
    "cinematic": "🎬",
}


def _build_logo_rows() -> list["Text"]:  # type: ignore[name-defined]
    from rich.text import Text

    face_colors = [
        "#ff7eb6",
        "#ff75c3",
        "#ff6ad5",
        "#e96dff",
        "#bf7bff",
        "#8b8cff",
        "#5ea6ff",
        "#4fc3ff",
    ]
    shadow_color = "#4a214f"
    caption_face = "#ffd6ec"

    rows: list[Text] = []
    for index, line in enumerate(_LOGO_LINES):
        color = face_colors[index % len(face_colors)]
        rows.append(Text(f" {line}", style=f"bold {shadow_color}"))
        rows.append(Text(line, style=f"bold {color}"))

    title = "♡ terminal romance simulator ♡"
    rows.append(Text())
    rows.append(Text(f" {title}", style=f"bold {shadow_color}"))
    rows.append(Text(title, style=f"bold italic {caption_face}"))
    rows.append(Text(" v0.1.0", style="grey35"))
    rows.append(Text("v0.1.0", style="bold #d7c3ff"))
    return rows


def _play_intro(console: "Console") -> None:  # type: ignore[name-defined]
    """Play the nerd animation intro."""
    import time
    from rich.align import Align
    from rich.text import Text

    for frame_text in _NERD_FRAMES:
        console.clear()
        console.print()
        console.print()
        console.print(Align.center(Text(frame_text, style="bold bright_magenta")))
        console.print()
        time.sleep(0.55)

    # Final logo reveal
    console.clear()
    console.print()
    for row in _build_logo_rows():
        console.print(Align.center(row))
        time.sleep(0.08)
    time.sleep(0.5)


_STAR_FLAG_PATH = Path.home() / ".girlfriend-in-cli" / "star_shown"
_GITHUB_REPO = "NomaDamas/girlfriend-in-cli"


def _show_star_popup(console: "Console") -> None:  # type: ignore[name-defined]
    """Show GitHub star request. Only stop showing after user says yes."""
    if _STAR_FLAG_PATH.exists():
        return

    from rich.align import Align
    from rich.panel import Panel
    from rich.text import Text
    import webbrowser

    console.print()
    body = Text.assemble(
        ("\n", ""),
        ("  (✧ᴗ✧)  ", "bold bright_magenta"),
        ("If you enjoy this project,\n", "white"),
        ("         a GitHub ", "white"),
        ("Star", "bold yellow"),
        (" means a lot to the developers!\n\n", "white"),
        (f"         github.com/{_GITHUB_REPO}\n", "dim"),
    )
    console.print(Align.center(Panel(
        body,
        border_style="bright_yellow",
        title="[bold bright_yellow]  Star  [/bold bright_yellow]",
        width=55,
        padding=(0, 1),
    )))

    try:
        from .wide_input import wide_input
        answer = wide_input("  Open GitHub to star? (y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer in ("y", "yes"):
        url = f"https://github.com/{_GITHUB_REPO}"
        try:
            webbrowser.open(url)
            console.print("  [green]Opened in browser. Thank you![/green]\n")
        except Exception:
            console.print(f"  [dim]Open: {url}[/dim]\n")
        # Only mark as shown when user actually said yes
        _STAR_FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STAR_FLAG_PATH.write_text("shown", encoding="utf-8")


def _show_main_menu(
    bundled_personas: list[Path],
    args: argparse.Namespace,
    skip_intro: bool = False,
) -> tuple[argparse.Namespace, Path, Path | None] | None:
    from rich.align import Align
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.text import Text
    from .selector import MenuItem, arrow_select

    console = Console()
    console.clear()

    # Play intro animation on first launch
    if not skip_intro:
        _play_intro(console)
        _show_star_popup(console)
        console.clear()

    # Centered logo block
    logo_group = Group(*[Align.center(r) for r in _build_logo_rows()])
    console.print(Panel(logo_group, border_style="bright_magenta", padding=(1, 1)))

    # Settings bar — centered
    perf_icon = _PERF_ICONS.get(args.performance, "")
    status = Text.assemble(
        ("(✧ᴗ✧) ", "bold bright_magenta"),
        ("Provider: ", "dim"),
        (args.provider, "bold cyan"),
        ("  │  ", "dim"),
        (f"{perf_icon} {args.performance}", "bold yellow"),
        ("  │  Voice: ", "dim"),
        ("ON" if args.voice_output else "OFF", "bold green" if args.voice_output else "dim"),
    )
    console.print(Align.center(status))

    # Check API key
    import os as _os
    has_key = bool(_os.environ.get("OPENAI_API_KEY")) or bool(_os.environ.get("ANTHROPIC_API_KEY"))
    if not has_key:
        console.print(Align.center(Text(
            "⚠ API key not set. Go to Settings > API Keys first.",
            style="bold yellow",
        )))
    console.print()

    # Count chat rooms
    session_dir = bundled_session_dir()
    room_count = len(list(session_dir.glob("*.json"))) if session_dir.exists() else 0

    from .i18n import t, get_language
    lang = get_language()

    menu_items = [
        MenuItem(t("new_chat", lang), t("new_chat_desc", lang), icon="💬"),
        MenuItem(f"{t('chat_rooms', lang)} ({room_count})", t("chat_rooms_desc", lang), icon="💌"),
        MenuItem(t("persona_studio", lang), t("persona_studio_desc", lang), icon="✨"),
        MenuItem(t("settings", lang), t("settings_desc", lang), icon="⚙️"),
        MenuItem(t("quit", lang), t("quit_desc", lang), icon="👋"),
    ]

    while True:
        choice = arrow_select(
            console, menu_items,
            title=t("main_title", lang),
            allow_back=False,
            border_style="bright_magenta",
        )

        if choice is None or choice == 4:  # Quit
            console.print("\n  [dim]Goodbye.[/dim]")
            return None

        if choice == 0:  # New Chat
            console.print()
            result = _pick_persona_interactive(bundled_personas, console)
            if result is None:
                console.clear()
                fresh = discover_personas(bundled_persona_dir()) if bundled_persona_dir().exists() else []
                return _show_main_menu(fresh, args, skip_intro=True)
            return args, resolve_persona_path(result), None

        if choice == 1:  # Chat Rooms
            console.print()
            room_result = _show_chat_rooms(console, bundled_personas)
            if room_result is None:
                console.clear()
                fresh = discover_personas(bundled_persona_dir()) if bundled_persona_dir().exists() else []
                return _show_main_menu(fresh, args, skip_intro=True)
            persona_path, resume_path = room_result
            return args, resolve_persona_path(persona_path), resume_path

        if choice == 2:  # Persona Studio
            console.print()
            studio_result = _persona_studio(console, bundled_personas)
            if studio_result is not None:
                return args, studio_result, None
            console.clear()
            fresh = discover_personas(bundled_persona_dir()) if bundled_persona_dir().exists() else []
            return _show_main_menu(fresh, args, skip_intro=True)

        if choice == 3:  # Settings
            console.print()
            _settings_menu(console, args)
            console.clear()
            fresh = discover_personas(bundled_persona_dir()) if bundled_persona_dir().exists() else []
            return _show_main_menu(fresh, args, skip_intro=True)


_BUILTIN_PERSONAS = {
    "wonyoung-idol.json",
    "dua-international.json",
    "reze-anime.json",
}


def _persona_studio(
    console: "Console",  # type: ignore[name-defined]
    bundled_personas: list[Path],
) -> Path | None:
    """Persona studio: create, edit, or delete custom personas."""
    from .selector import MenuItem, arrow_select

    while True:
        # Find custom personas — re-read from disk every loop to avoid stale state
        persona_dir = bundled_persona_dir()
        fresh_personas = discover_personas(persona_dir) if persona_dir.exists() else []
        custom_personas = [
            p for p in fresh_personas
            if p.name not in _BUILTIN_PERSONAS and p.exists()
        ]

        items = [
            MenuItem("Auto Generate", "Enter a name/link — deep research", icon="🤖"),
            MenuItem("Import Persona", "From file, URL, or pasted JSON", icon="📥"),
            MenuItem("Create Manually", "Step-by-step wizard", icon="✨"),
        ]
        for cp in custom_personas:
            try:
                data = json.loads(cp.read_text(encoding="utf-8"))
                name = data.get("name", cp.stem)
            except Exception:
                name = cp.stem
            items.append(MenuItem(f"Edit: {name}", cp.name, icon="✏️"))

        if custom_personas:
            items.append(MenuItem("Delete a Persona", "Remove a custom persona", icon="🗑️"))
        items.append(MenuItem("Back", "", icon="←"))

        choice = arrow_select(
            console, items,
            title="✨ Persona Studio",
            border_style="bright_green",
        )

        if choice is None or choice == len(items) - 1:  # Back
            return None

        if choice == 0:  # Auto Generate
            result = _auto_generate_persona(console)
            if result is not None:
                return result
            continue

        if choice == 1:  # Import Persona
            result = _import_persona(console)
            if result is not None:
                return result
            continue

        if choice == 2:  # Create Manually
            return _create_persona_wizard(console)

        if custom_personas and choice == len(items) - 2:  # Delete
            _delete_persona(console, custom_personas)
            continue

        # Edit: choice 3..N maps to custom_personas[choice-3]
        edit_idx = choice - 3
        if 0 <= edit_idx < len(custom_personas):
            result = _edit_persona(console, custom_personas[edit_idx])
            if result is not None:
                return result
            continue

        return None


def _import_persona(console: "Console") -> Path | None:  # type: ignore[name-defined]
    """Import a persona from file path, URL, or pasted JSON."""
    from rich.panel import Panel
    from .wide_input import wide_input, wide_multiline_input
    from .selector import MenuItem, arrow_select
    from .personas import persona_from_pack

    console.clear()
    console.print(Panel(
        "[bold bright_cyan]📥 Import Persona[/bold bright_cyan]\n\n"
        "[dim]Import a persona created by someone else.[/dim]\n"
        "[dim]Any JSON matching the persona schema will work.[/dim]\n\n"
        "[dim]See personas/PERSONA_FORMAT.md for the format spec.[/dim]",
        border_style="bright_cyan",
        width=70,
        padding=(1, 2),
    ))
    console.print()

    items = [
        MenuItem("From File Path", "Local .json file on disk", icon="📄"),
        MenuItem("From URL", "HTTP URL (GitHub Gist, Pastebin, etc.)", icon="🌐"),
        MenuItem("Paste JSON", "Paste the JSON content directly", icon="📋"),
        MenuItem("Back", "", icon="←"),
    ]
    choice = arrow_select(console, items, title="Import source", border_style="bright_cyan")
    if choice is None or choice == 3:
        return None

    data: dict[str, Any] | None = None

    if choice == 0:
        try:
            path_str = wide_input("  File path: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not path_str:
            return None
        src = Path(path_str).expanduser().resolve()
        if not src.exists():
            console.print(f"  [red]File not found: {src}[/red]")
            wide_input("  Press Enter...")
            return None
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
        except Exception as exc:
            console.print(f"  [red]Invalid JSON: {exc}[/red]")
            wide_input("  Press Enter...")
            return None

    elif choice == 1:
        try:
            url = wide_input("  URL: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not url:
            return None
        # Support GitHub Gist raw URL auto-conversion
        if "gist.github.com" in url and "/raw/" not in url:
            url = url.rstrip("/") + "/raw"
        try:
            from urllib import request as _request
            req = _request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with _request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            console.print(f"  [red]URL content is not valid JSON: {exc}[/red]")
            wide_input("  Press Enter...")
            return None
        except Exception as exc:
            console.print(f"  [red]Fetch failed: {exc}[/red]")
            wide_input("  Press Enter...")
            return None

    elif choice == 2:
        console.print("  [dim]Paste the JSON content. Empty line to submit.[/dim]")
        console.print()
        try:
            raw = wide_multiline_input("  > ")
        except (EOFError, KeyboardInterrupt):
            return None
        if not raw.strip():
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            console.print(f"  [red]Invalid JSON: {exc}[/red]")
            wide_input("  Press Enter...")
            return None

    if data is None:
        return None

    # Validate by constructing the Persona
    try:
        persona = persona_from_pack(data)
    except Exception as exc:
        console.print(f"  [red]Invalid persona data: {exc}[/red]")
        wide_input("  Press Enter...")
        return None

    # Save
    from .session_io import slugify
    persona_dir = bundled_persona_dir()
    persona_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{slugify(persona.name)}-imported.json"
    save_path = persona_dir / filename
    save_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    console.print(f"\n  [bold green]✓ Imported: {persona.name}[/bold green]")
    console.print(f"  [dim]Saved to: {save_path.name}[/dim]\n")

    try:
        chat = wide_input("  Start chat now? (y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None
    if chat in ("y", "yes", ""):
        return save_path
    return None


def _auto_generate_persona(console: "Console") -> Path | None:  # type: ignore[name-defined]
    """Auto-generate persona from a name/URL/description using deep research."""
    from rich.panel import Panel
    from .persona_auto import generate_persona_from_input, save_generated_persona, deep_research_persona
    from .wide_input import wide_input, wide_multiline_input

    console.clear()
    console.print(Panel(
        "[bold bright_green]🤖 Auto Persona Generator  (Deep Research)[/bold bright_green]\n\n"
        "[dim]Enter anything — a name, URL, or a full multi-line description.[/dim]\n"
        "[dim]Press Enter on an empty line to finish. Deep research will run automatically.[/dim]\n\n"
        "[dim]Examples (single-line or multi-line):[/dim]\n"
        "  [cyan]장원영[/cyan]\n"
        "  [cyan]Dua Lipa[/cyan]\n"
        "  [cyan]Reze from Chainsaw Man[/cyan]\n"
        "  [cyan]https://namu.wiki/w/아이유[/cyan]\n"
        "  [cyan]차가운 도시 여자 26살 변호사[/cyan]\n\n"
        "[dim]Or describe in detail (multi-line):[/dim]\n"
        "  [cyan]홍대에서 일러스트 그리는 24살 여자.[/cyan]\n"
        "  [cyan]INFP, 조용하지만 웃음 많음.[/cyan]\n"
        "  [cyan]고양이 두 마리 키우고 새벽에 작업함.[/cyan]",
        border_style="bright_green",
        width=80,
        padding=(1, 2),
    ))
    console.print()
    console.print("  [dim]Type your input (Enter on empty line to submit):[/dim]")
    console.print()

    try:
        input_text = wide_multiline_input("  > ")
    except (EOFError, KeyboardInterrupt):
        return None

    if not input_text.strip():
        return None

    console.clear()
    console.print(Panel(
        f"[bold]🔍 Deep Research Mode[/bold]\n\n"
        f"[dim]Input:[/dim]\n[white]{input_text[:300]}{'...' if len(input_text) > 300 else ''}[/white]",
        border_style="bright_cyan",
        width=80,
        padding=(1, 2),
    ))
    console.print()

    # Deep research — multi-step with progress
    from rich.live import Live
    from rich.spinner import Spinner
    steps = [
        "🔍 Analyzing input...",
        "🌐 Web searching...",
        "📚 Gathering context...",
        "🧠 Synthesizing persona...",
        "✨ Finalizing details...",
    ]
    try:
        with Live(
            Spinner("dots", text=f"  {steps[0]}", style="cyan"),
            console=console,
            refresh_per_second=10,
        ) as live:
            def on_progress(step_idx: int) -> None:
                if 0 <= step_idx < len(steps):
                    live.update(Spinner("dots", text=f"  {steps[step_idx]}", style="cyan"))

            data = deep_research_persona(input_text.strip(), on_progress=on_progress)
    except Exception as exc:
        console.print(f"  [red]Failed: {exc}[/red]\n")
        try:
            wide_input("  Press Enter to go back...")
        except (EOFError, KeyboardInterrupt):
            pass
        return None

    console.clear()

    # Show preview
    console.print(Panel(
        f"[bold]{data.get('name', '?')}[/bold]  [dim]{data.get('age', '?')}세  {data.get('relationship_mode', '?')}[/dim]\n\n"
        f"[white]{data.get('background', '')[:100]}...[/white]\n\n"
        f"[dim]Interests:[/dim] {', '.join(data.get('interests', [])[:3])}\n"
        f'[dim]Greeting:[/dim] [italic]"{data.get("greeting", "")}"[/italic]',
        title="[bold green]✓ Generated[/bold green]",
        border_style="bright_green",
        width=70,
    ))

    try:
        answer = wide_input("\n  Save and start chat? (Y/n): ").strip().lower()
        if answer and answer.startswith("n"):
            return None
    except (EOFError, KeyboardInterrupt):
        return None

    persona_dir = bundled_persona_dir()
    path = save_generated_persona(data, persona_dir)
    console.print(f"  [green]✓ Saved: {path.name}[/green]")
    console.print(f"  [bold green]Starting chat with {data.get('name', '')}...[/bold green]\n")
    return path


def _edit_persona(console: "Console", persona_path: Path) -> Path | None:  # type: ignore[name-defined]
    """Edit an existing custom persona's fields."""
    try:
        data = json.loads(persona_path.read_text(encoding="utf-8"))
    except Exception:
        console.print("  [red]Failed to load persona.[/red]\n")
        return None

    name = data.get("name", "?")
    console.print(f"\n  [bold]Editing: {name}[/bold]")
    console.print("  [dim]Press Enter to keep current value.[/dim]\n")

    from .wide_input import wide_input

    def _ask(prompt: str, current: str) -> str:
        try:
            val = wide_input(f"  {prompt}: ", default=current or "")
            return val.strip() if val.strip() else current
        except (EOFError, KeyboardInterrupt):
            return current

    def _ask_list(prompt: str, current: list[str]) -> list[str]:
        display = ", ".join(current[:3])
        try:
            val = wide_input(f"  {prompt}: ", default=display)
            if not val.strip():
                return current
            return [item.strip() for item in val.split(",") if item.strip()]
        except (EOFError, KeyboardInterrupt):
            return current

    data["name"] = _ask("Name", data.get("name", ""))
    data["background"] = _ask("Background", data.get("background", ""))
    data["situation"] = _ask("Situation", data.get("situation", ""))
    data["texting_style"] = _ask("Texting style", data.get("texting_style", ""))
    data["interests"] = _ask_list("Interests (comma)", data.get("interests", []))
    data["soft_spots"] = _ask_list("Soft spots (comma)", data.get("soft_spots", []))
    data["boundaries"] = _ask_list("Boundaries (comma)", data.get("boundaries", []))
    data["greeting"] = _ask("First message", data.get("greeting", ""))

    persona_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    console.print(f"\n  [green]Saved: {persona_path.name}[/green]\n")

    # Ask if they want to chat now
    from .wide_input import wide_input
    try:
        chat = wide_input("  Start chat with this persona? (y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None
    if chat in ("y", "yes", "ㅛ"):
        return persona_path
    return None


def _delete_persona(console: "Console", custom_personas: list[Path]) -> None:  # type: ignore[name-defined]
    from .selector import MenuItem, arrow_select

    items = []
    for cp in custom_personas:
        try:
            data = json.loads(cp.read_text(encoding="utf-8"))
            name = data.get("name", cp.stem)
        except Exception:
            name = cp.stem
        items.append(MenuItem(name, cp.name, icon="🗑️"))
    items.append(MenuItem("Cancel", "", icon="←"))

    choice = arrow_select(
        console, items,
        title="Delete which persona?",
        border_style="red",
    )

    if choice is None or choice == len(items) - 1:
        return

    target = custom_personas[choice]
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        name = data.get("name", target.stem)
    except Exception:
        name = target.stem

    from .wide_input import wide_input
    try:
        confirm = wide_input(f"  Delete {name}? This cannot be undone. (y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if confirm in ("y", "yes", "ㅛ"):
        try:
            target.unlink(missing_ok=True)
            console.print(f"  [red]Deleted: {name}[/red]\n")
        except Exception as exc:
            console.print(f"  [red]Failed to delete: {exc}[/red]\n")


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

    from .wide_input import wide_input

    def _ask(prompt: str, default: str = "") -> str:
        try:
            val = wide_input(f"  {prompt}: ", default=default or "")
            return val.strip() or default
        except (EOFError, KeyboardInterrupt):
            return default

    def _ask_list(prompt: str, hint: str = "") -> list[str]:
        hint_str = f" ({hint})" if hint else ""
        try:
            val = wide_input(f"  {prompt}{hint_str}: ")
            if not val:
                return []
            return [item.strip() for item in val.split(",") if item.strip()]
        except (EOFError, KeyboardInterrupt):
            return []

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


def _show_chat_rooms(
    console: "Console",  # type: ignore[name-defined]
    bundled_personas: list[Path],
) -> tuple[Path, Path] | None:
    """KakaoTalk-style chat room list with resume and delete."""
    from .selector import MenuItem, arrow_select

    session_dir = bundled_session_dir()
    if not session_dir.exists() or not list(session_dir.glob("*.json")):
        console.print("  [yellow]No chat rooms yet. Start a new chat first![/yellow]\n")
        return None

    while True:
        session_files = sorted(session_dir.glob("*.json"), reverse=True)
        if not session_files:
            console.print("  [yellow]No chat rooms left.[/yellow]\n")
            return None

        rooms = []
        for sf in session_files[:12]:
            try:
                data = json.loads(sf.read_text(encoding="utf-8"))
                persona_name = data.get("persona", {}).get("name", "?")
                mode = data.get("persona", {}).get("relationship_mode", "?")
                msgs = data.get("messages", [])
                msg_count = len(msgs)
                # Last message preview
                last_msg = ""
                for m in reversed(msgs):
                    if m.get("role") in ("user", "assistant"):
                        last_msg = m.get("text", "")[:30]
                        break
                # Timestamp from filename
                ts = sf.stem.split("-")[0] if "-" in sf.stem else ""
                rooms.append({
                    "path": sf,
                    "persona_name": persona_name,
                    "mode": mode,
                    "msg_count": msg_count,
                    "last_msg": last_msg,
                    "ts": ts,
                })
            except Exception:
                rooms.append({
                    "path": sf,
                    "persona_name": "?",
                    "mode": "?",
                    "msg_count": 0,
                    "last_msg": "",
                    "ts": "",
                })

        menu_items = []
        for r in rooms:
            icon = _MODE_ICONS.get(r["mode"], "💬")
            preview = r["last_msg"] if r["last_msg"] else "(empty)"
            menu_items.append(MenuItem(
                f"{r['persona_name']}  ({r['msg_count']})",
                preview,
                icon=icon,
            ))
        menu_items.append(MenuItem("Back", "Return to main menu", icon="←"))

        choice = arrow_select(
            console, menu_items,
            title="💌 Chat Rooms",
            border_style="bright_cyan",
        )

        if choice is None or choice == len(rooms):  # Back
            return None

        selected = rooms[choice]

        # Sub-menu: Resume or Delete
        action_items = [
            MenuItem("Resume Chat", "Continue this conversation", icon="▸"),
            MenuItem("Delete Room", "Remove this chat room", icon="✕"),
            MenuItem("Back", "Return to room list", icon="←"),
        ]
        action = arrow_select(
            console, action_items,
            title=f"{selected['persona_name']} — What to do?",
            border_style="bright_cyan",
        )

        if action == 0:  # Resume
            persona_path = _find_persona_by_name(selected["persona_name"], bundled_personas)
            if persona_path is None and bundled_personas:
                persona_path = bundled_personas[0]
            elif persona_path is None:
                console.print("  [red]Persona not found.[/red]")
                continue
            console.print(f"\n  [bold cyan]Resuming chat with {selected['persona_name']}...[/bold cyan]\n")
            return persona_path, selected["path"]

        if action == 1:  # Delete
            try:
                # Also delete matching .md file
                md_path = selected["path"].with_suffix(".md")
                selected["path"].unlink()
                if md_path.exists():
                    md_path.unlink()
                console.print(f"  [red]Deleted: {selected['persona_name']} room[/red]\n")
            except Exception:
                console.print("  [red]Failed to delete.[/red]\n")
            # Loop back to room list
            continue

        # action == 2 or None: back to room list
        continue


def _pick_session_to_resume(
    console: "Console",  # type: ignore[name-defined]
    bundled_personas: list[Path],
) -> tuple[Path, Path] | None:
    from .selector import MenuItem, arrow_select

    session_dir = bundled_session_dir()
    if not session_dir.exists():
        console.print("  [yellow]No saved sessions yet.[/yellow]\n")
        return None

    session_files = sorted(session_dir.glob("*.json"), reverse=True)
    if not session_files:
        console.print("  [yellow]No saved sessions yet.[/yellow]\n")
        return None

    session_summaries = []
    menu_items = []
    for sf in session_files[:8]:
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            persona_name = data.get("persona", {}).get("name", "?")
            msg_count = len(data.get("messages", []))
            mode = data.get("persona", {}).get("relationship_mode", "?")
            session_summaries.append({
                "path": sf,
                "persona_name": persona_name,
            })
            icon = _MODE_ICONS.get(mode, "💬")
            menu_items.append(MenuItem(
                persona_name,
                f"{msg_count} messages  |  {sf.stem}",
                icon=icon,
            ))
        except Exception:
            session_summaries.append({"path": sf, "persona_name": "?"})
            menu_items.append(MenuItem(sf.stem, "corrupted", icon="❓"))

    choice = arrow_select(console, menu_items, title="Resume Session")
    if choice is None:
        return None

    selected = session_summaries[choice]
    persona_name = selected["persona_name"]
    persona_path = _find_persona_by_name(persona_name, bundled_personas)
    if persona_path is None and bundled_personas:
        persona_path = bundled_personas[0]
    elif persona_path is None:
        console.print("  [red]No matching persona found.[/red]")
        return None
    console.print(f"\n  [bold green]Resuming chat with {persona_name}...[/bold green]\n")
    return persona_path, selected["path"]


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
    import os
    from .selector import MenuItem, arrow_select
    from .i18n import get_language, set_language

    providers = ["openai", "anthropic"]
    perfs = ["turbo", "balanced", "cinematic"]
    languages = ["ko", "en", "ja", "zh"]
    lang_names = {"ko": "한국어", "en": "English", "ja": "日本語", "zh": "中文"}

    while True:
        perf_icon = _PERF_ICONS.get(args.performance, "")
        has_openai = bool(os.environ.get("OPENAI_API_KEY"))
        has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
        current_lang = get_language()

        items = [
            MenuItem(f"Language: {lang_names.get(current_lang, current_lang)}", "UI + chat language", icon="🌍"),
            MenuItem(f"Provider: {args.provider}", "Cycle openai / anthropic", icon="🔌"),
            MenuItem(f"Performance: {perf_icon} {args.performance}", "Cycle turbo / balanced / cinematic", icon="⚡"),
            MenuItem(f"Voice: {'ON' if args.voice_output else 'OFF'}", "Toggle voice output", icon="🔊"),
            MenuItem(f"Trace: {'ON' if not args.no_trace else 'OFF'}", "Toggle debug trace panel", icon="📊"),
            MenuItem(
                "API Keys",
                f"OpenAI: {'set' if has_openai else 'missing'}  |  Anthropic: {'set' if has_anthropic else 'missing'}",
                icon="🔑",
            ),
        ]

        choice = arrow_select(console, items, title="Settings")
        if choice is None:
            return

        if choice == 0:  # Language
            idx = languages.index(current_lang) if current_lang in languages else 0
            new_lang = languages[(idx + 1) % len(languages)]
            set_language(new_lang)
            console.print(f"  [green]Language -> {lang_names[new_lang]}[/green]\n")
        elif choice == 1:  # Provider
            current_idx = providers.index(args.provider) if args.provider in providers else 0
            args.provider = providers[(current_idx + 1) % len(providers)]
            console.print(f"  [green]Provider -> {args.provider}[/green]\n")
        elif choice == 2:  # Performance
            current_idx = perfs.index(args.performance) if args.performance in perfs else 0
            args.performance = perfs[(current_idx + 1) % len(perfs)]
            console.print(f"  [green]Performance -> {args.performance}[/green]\n")
        elif choice == 3:  # Voice
            args.voice_output = not args.voice_output
            console.print(f"  [green]Voice -> {'ON' if args.voice_output else 'OFF'}[/green]\n")
        elif choice == 4:  # Trace
            args.no_trace = not args.no_trace
            console.print(f"  [green]Trace -> {'ON' if not args.no_trace else 'OFF'}[/green]\n")
        elif choice == 5:  # API Keys
            _api_key_guide(console)


def _api_key_guide(console: "Console") -> None:  # type: ignore[name-defined]
    import os
    from .selector import MenuItem, arrow_select

    while True:
        has_openai = bool(os.environ.get("OPENAI_API_KEY"))
        has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))

        openai_status = "[green]set[/green]" if has_openai else "[red]not set[/red]"
        anthropic_status = "[green]set[/green]" if has_anthropic else "[red]not set[/red]"

        items = [
            MenuItem(
                f"OpenAI Key  ({('set' if has_openai else 'not set')})",
                "Paste your OpenAI API key here",
                icon="🔑",
            ),
            MenuItem(
                f"Anthropic Key  ({('set' if has_anthropic else 'not set')})",
                "Paste your Anthropic API key here",
                icon="🔑",
            ),
        ]

        choice = arrow_select(
            console, items,
            title="API Key Setup",
            border_style="bright_yellow",
        )
        if choice is None:
            return

        if choice == 0:
            _set_api_key(console, "OPENAI_API_KEY", "OpenAI", "sk-")
        elif choice == 1:
            _set_api_key(console, "ANTHROPIC_API_KEY", "Anthropic", "sk-ant-")


def _set_api_key(console: "Console", env_var: str, provider_name: str, prefix: str) -> None:  # type: ignore[name-defined]
    import os

    current = os.environ.get(env_var, "")
    if current:
        masked = current[:8] + "..." + current[-4:]
        console.print(f"\n  [dim]Current: {masked}[/dim]")

    console.print(f"\n  [bold]Paste your {provider_name} API key:[/bold]")
    console.print(f"  [dim]Get one at: {'platform.openai.com/api-keys' if 'OPENAI' in env_var else 'console.anthropic.com/settings/keys'}[/dim]")
    console.print(f"  [dim]Should start with: {prefix}[/dim]")
    console.print()

    try:
        from .wide_input import wide_input
        key = wide_input("  Key: ").strip()
    except (EOFError, KeyboardInterrupt):
        return

    if not key:
        console.print("  [dim]Cancelled.[/dim]\n")
        return

    if not key.startswith(prefix):
        console.print(f"  [yellow]Warning: key doesn't start with '{prefix}'. Saving anyway.[/yellow]\n")

    # Set for current session
    os.environ[env_var] = key

    # Save to ~/.zshrc for persistence
    saved = _save_key_to_shell_profile(env_var, key)
    masked = key[:8] + "..." + key[-4:]
    console.print(f"  [green]Saved: {masked}[/green]")
    if saved:
        console.print(f"  [green]Added to ~/.zshrc (persistent across sessions)[/green]")
    else:
        console.print(f"  [yellow]Saved for this session only. Add manually to ~/.zshrc for persistence.[/yellow]")
    console.print()


def _save_key_to_shell_profile(env_var: str, key: str) -> bool:
    """Append export to ~/.zshrc. Returns True if successful."""
    from pathlib import Path

    rc_path = Path.home() / ".zshrc"
    if not rc_path.exists():
        rc_path = Path.home() / ".bashrc"

    try:
        content = rc_path.read_text(encoding="utf-8") if rc_path.exists() else ""

        # Remove existing line for this var
        lines = content.splitlines()
        lines = [l for l in lines if not l.strip().startswith(f"export {env_var}=")]
        lines.append(f'export {env_var}="{key}"')

        rc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    except Exception:
        return False


def _pick_persona_interactive(personas: list[Path], console: "Console | None" = None) -> Path | None:  # type: ignore[name-defined]
    from rich.console import Console as RichConsole
    from .selector import MenuItem, arrow_select

    if console is None:
        console = RichConsole()

    menu_items = []
    for path in personas:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            name = data.get("name", path.stem)
            age = data.get("age", "?")
            mode = data.get("relationship_mode", "?")
            interests = ", ".join(data.get("interests", [])[:3])
            icon = _MODE_ICONS.get(mode, "💬")
            menu_items.append(MenuItem(
                f"{name}  {age}세  {mode}",
                interests if interests else "-",
                icon=icon,
            ))
        except Exception:
            menu_items.append(MenuItem(path.stem, "", icon="💬"))

    choice = arrow_select(console, menu_items, title="Who do you want to talk to?")
    if choice is None:
        return None

    selected_path = personas[choice]
    try:
        data = json.loads(selected_path.read_text(encoding="utf-8"))
        name = data.get("name", "")
    except Exception:
        data = {}
        name = ""

    # Difficulty picker (overrides persona default)
    difficulty_items = [
        MenuItem("Easy", "잘 풀어준다, 작은 것도 +", icon="🟢"),
        MenuItem("Normal", "현실적", icon="🟡"),
        MenuItem("Hard", "까다롭다, 노력 필요", icon="🟠"),
        MenuItem("Nightmare", "거의 불가능, 시니컬", icon="🔴"),
        MenuItem("Persona Default", f"기본값 ({data.get('difficulty', 'normal')})", icon="⚙️"),
    ]
    diff_choice = arrow_select(
        console, difficulty_items,
        title=f"Difficulty for {name}",
        border_style="yellow",
    )
    if diff_choice is None:
        return None

    diff_map = {0: "easy", 1: "normal", 2: "hard", 3: "nightmare", 4: None}
    chosen_diff = diff_map.get(diff_choice)
    if chosen_diff is not None and data:
        # Override the persona's difficulty for this session by writing back
        data["difficulty"] = chosen_diff
        selected_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        console.print(f"\n  [yellow]Difficulty: {chosen_diff}[/yellow]")

    console.print(f"\n  [bold magenta]Starting chat with {name}...[/bold magenta]\n")
    return selected_path
