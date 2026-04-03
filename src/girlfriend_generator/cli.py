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
        choices=["heuristic", "openai", "anthropic"],
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

    persona_path = args.persona or (bundled_personas[0] if bundled_personas else None)
    if persona_path is None:
        parser.error("No persona file found. Add one under personas/ or pass --persona.")
    persona_path = resolve_persona_path(persona_path)

    config = AppConfig(
        persona_path=persona_path,
        provider_name=args.provider,
        provider_model=args.model,
        performance_mode=args.performance,
        voice_output=args.voice_output,
        voice_input_command=args.voice_input_command,
        session_dir=resolve_session_dir(args.session_dir),
        export_on_exit=not args.no_export_on_exit,
        show_trace=not args.no_trace,
    )
    return run_chat_app(config)
