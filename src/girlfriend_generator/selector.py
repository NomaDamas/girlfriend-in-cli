"""Reusable arrow-key selector for terminal menus using Rich Live rendering."""

from __future__ import annotations

import os
import select as sel
import sys
import termios
import time
import tty
from dataclasses import dataclass
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


@dataclass
class MenuItem:
    label: str
    description: str = ""
    style: str = "white"
    icon: str = ""
    data: Any = None


def arrow_select(
    console: Console,
    items: list[MenuItem],
    title: str = "",
    allow_back: bool = True,
    border_style: str = "bright_magenta",
) -> int | None:
    """Show an arrow-key navigable menu. Returns selected index or None if Esc/back."""
    if not items:
        return None
    if not sys.stdin.isatty():
        return 0

    cursor = 0
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)

        with Live(
            _build_panel(items, cursor, title, allow_back, border_style),
            console=console,
            auto_refresh=False,
            transient=True,
        ) as live:
            while True:
                key = _read_key(fd)

                if key == "up":
                    cursor = (cursor - 1) % len(items)
                elif key == "down":
                    cursor = (cursor + 1) % len(items)
                elif key == "enter":
                    return cursor
                elif key == "esc":
                    if allow_back:
                        return None
                elif key in ("ctrl-c", "ctrl-d"):
                    return None
                else:
                    continue

                live.update(
                    _build_panel(items, cursor, title, allow_back, border_style),
                    refresh=True,
                )
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _build_panel(
    items: list[MenuItem],
    cursor: int,
    title: str,
    allow_back: bool,
    border_style: str,
) -> Panel:
    rows = []
    for i, item in enumerate(items):
        selected = i == cursor
        icon = f"{item.icon} " if item.icon else ""

        if selected:
            line = Text()
            line.append("  ▸ ", style="bold bright_magenta")
            line.append(f"{icon}{item.label}", style="bold white")
            if item.description:
                line.append(f"  {item.description}", style="cyan")
            rows.append(line)
        else:
            line = Text()
            line.append(f"    {icon}{item.label}", style="dim")
            rows.append(line)

    # Navigation hint
    nav = Text()
    nav.append("\n  ↑↓ ", style="dim")
    nav.append("move", style="dim bold")
    nav.append("   Enter ", style="dim")
    nav.append("select", style="dim bold")
    if allow_back:
        nav.append("   Esc ", style="dim")
        nav.append("back", style="dim bold")
    rows.append(nav)

    body = Group(*rows)
    return Panel(
        body,
        title=f"[bold]{title}[/bold]" if title else None,
        border_style=border_style,
        padding=(1, 2),
    )


def _read_key(fd: int) -> str:
    ready, _, _ = sel.select([sys.stdin], [], [])
    if not ready:
        return ""
    data = os.read(fd, 1)
    if not data:
        return ""

    b = data[0]

    if b == 0x1B:  # Escape
        ready2, _, _ = sel.select([sys.stdin], [], [], 0.05)
        if not ready2:
            return "esc"
        data2 = os.read(fd, 1)
        if data2 == b"[":
            data3 = os.read(fd, 1)
            if data3 == b"A":
                return "up"
            if data3 == b"B":
                return "down"
            if data3 == b"C":
                return "right"
            if data3 == b"D":
                return "left"
        return "esc"

    if b in (0x0D, 0x0A):
        return "enter"
    if b == 0x03:
        return "ctrl-c"
    if b == 0x04:
        return "ctrl-d"

    return ""
