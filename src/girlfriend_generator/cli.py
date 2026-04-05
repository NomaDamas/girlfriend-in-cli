from __future__ import annotations

import argparse
from pathlib import Path

from .app import AppConfig, run_chat_app
from .paths import (
    bundled_persona_dir,
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
    return parser


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
        persona_path = args.persona or (bundled_personas[0] if bundled_personas else None)
        if persona_path is None:
            parser.error("No persona file found. Add one under personas/ or pass --persona.")
        persona_path = resolve_persona_path(persona_path)

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
    )
    return run_chat_app(config)
