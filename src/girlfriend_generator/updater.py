from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from .paths import project_root
from .version import __version__

LATEST_RELEASE_URL = "https://api.github.com/repos/NomaDamas/girlfriend-in-cli/releases/latest"
DEFAULT_PACKAGE_NAME = "girlfriend-in-cli"


@dataclass(slots=True)
class ReleaseInfo:
    version: str
    tag_name: str
    html_url: str
    notes: str


@dataclass(slots=True)
class InstallContext:
    method: str
    package_name: str = DEFAULT_PACKAGE_NAME
    repo_root: Path | None = None


def normalize_version(value: str) -> tuple[int, ...]:
    cleaned = value.strip().lower().removeprefix("v")
    parts = []
    for token in cleaned.split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        parts.append(int(digits or "0"))
    return tuple(parts)


def is_newer_version(candidate: str, current: str = __version__) -> bool:
    return normalize_version(candidate) > normalize_version(current)


def fetch_latest_release(timeout_seconds: float = 1.5) -> ReleaseInfo | None:
    request = Request(
        LATEST_RELEASE_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{DEFAULT_PACKAGE_NAME}/{__version__}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None

    tag_name = str(payload.get("tag_name") or "").strip()
    if not tag_name:
        return None
    return ReleaseInfo(
        version=tag_name.removeprefix("v"),
        tag_name=tag_name,
        html_url=str(payload.get("html_url") or ""),
        notes=str(payload.get("name") or payload.get("body") or ""),
    )


def detect_install_context() -> InstallContext:
    forced = os.environ.get("GIRLFRIEND_GENERATOR_INSTALL_METHOD", "").strip().lower()
    if forced == "brew":
        return InstallContext(method="brew")

    module_path = Path(__file__).resolve()
    if "Cellar" in str(module_path) or "Homebrew" in str(module_path):
        return InstallContext(method="brew")

    root = project_root()
    if root and (root / ".git").exists():
        return InstallContext(method="git", repo_root=root)

    return InstallContext(method="unknown")


def build_update_command(context: InstallContext, tag_name: str) -> list[str] | None:
    if context.method == "brew":
        if shutil.which("brew") is None:
            return None
        return ["brew", "upgrade", context.package_name]
    if context.method == "git" and context.repo_root is not None:
        return ["bash", "scripts/update_release.sh", tag_name]
    return None


def run_update_command(context: InstallContext, tag_name: str) -> tuple[bool, str]:
    command = build_update_command(context, tag_name)
    if command is None:
        return False, "No supported update command for this install."

    try:
        completed = subprocess.run(
            command,
            cwd=str(context.repo_root) if context.repo_root else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return False, str(exc)

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return False, detail or f"Update failed with exit code {completed.returncode}"
    return True, (completed.stdout or "Updated successfully.").strip()


def maybe_prompt_for_update(console: "Console") -> bool:  # type: ignore[name-defined]
    release = fetch_latest_release()
    if release is None or not is_newer_version(release.version):
        return False

    from rich.align import Align
    from rich.panel import Panel
    from rich.text import Text
    from .wide_input import wide_input

    context = detect_install_context()
    command = build_update_command(context, release.tag_name)
    action_hint = (
        "This install can update automatically."
        if command is not None
        else "Automatic update is unavailable for this install."
    )

    body = Text.assemble(
        ("\n", ""),
        ("  ✨ Update available\n", "bold bright_cyan"),
        (f"  Current: v{__version__}\n", "white"),
        (f"  Latest:  {release.tag_name}\n\n", "bold green"),
        (f"  {action_hint}\n", "dim"),
        (f"  {release.html_url}\n", "dim"),
    )
    console.print()
    console.print(Align.center(Panel(
        body,
        border_style="bright_cyan",
        title="[bold bright_cyan]  Update  [/bold bright_cyan]",
        width=68,
        padding=(0, 1),
    )))

    try:
        answer = wide_input("  Update now? (y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer not in {"y", "yes"}:
        return False

    success, detail = run_update_command(context, release.tag_name)
    if success:
        console.print(f"\n  [green]Updated to {release.tag_name}. Please relaunch the app.[/green]")
        return True
    console.print(f"\n  [red]Update failed:[/red] {detail}")
    return False
