"""Reusable arrow-key selector for terminal menus."""

from __future__ import annotations

import os
import select
import sys
import termios
import tty
from dataclasses import dataclass
from typing import Any

from rich.console import Console
from rich.panel import Panel
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
    columns: int = 1,
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
        while True:
            _render_selector(console, items, cursor, title, allow_back)
            key = _read_key(fd)

            if key == "up":
                cursor = (cursor - 1) % len(items)
            elif key == "down":
                cursor = (cursor + 1) % len(items)
            elif key == "left" and columns > 1:
                cursor = (cursor - 1) % len(items)
            elif key == "right" and columns > 1:
                cursor = (cursor + 1) % len(items)
            elif key == "enter":
                return cursor
            elif key == "esc" or key == "q":
                if allow_back:
                    return None
            elif key == "ctrl-c" or key == "ctrl-d":
                return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        # Clear the selector rendering
        line_count = len(items) * 2 + 4
        sys.stdout.write(f"\033[{line_count}A\033[J")
        sys.stdout.flush()


def _render_selector(
    console: Console,
    items: list[MenuItem],
    cursor: int,
    title: str,
    allow_back: bool,
) -> None:
    # Move cursor up to overwrite previous render
    total_lines = len(items) * 2 + 4  # each item gets 2 lines
    sys.stdout.write(f"\033[{total_lines}A\033[J")
    sys.stdout.flush()

    if title:
        sys.stdout.write(f"\n  \033[1;97m{title}\033[0m\n")

    for i, item in enumerate(items):
        selected = i == cursor
        icon = item.icon + " " if item.icon else ""
        if selected:
            # Highlighted item: bright background bar
            sys.stdout.write(f"  \033[1;35m ▸ \033[0m\033[1;97m{icon}{item.label}\033[0m\n")
            if item.description:
                sys.stdout.write(f"      \033[36m{item.description}\033[0m\n")
            else:
                sys.stdout.write("\n")
        else:
            sys.stdout.write(f"  \033[2m   {icon}{item.label}\033[0m\n")
            sys.stdout.write("\n")

    nav_parts = ["\033[2m", "  ↑↓ ", "\033[0;2m", "move", "  \033[2m│\033[0;2m  ↵ ", "select"]
    if allow_back:
        nav_parts += ["  \033[2m│\033[0;2m  esc ", "back"]
    nav_parts.append("\033[0m")
    sys.stdout.write("".join(nav_parts) + "\n")
    sys.stdout.flush()


def _read_key(fd: int) -> str:
    ready, _, _ = select.select([sys.stdin], [], [])
    if not ready:
        return ""
    data = os.read(fd, 1)
    if not data:
        return ""

    b = data[0]

    if b == 0x1B:  # Escape
        # Check for escape sequence
        ready2, _, _ = select.select([sys.stdin], [], [], 0.05)
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

    if b in (0x0D, 0x0A):  # Enter
        return "enter"
    if b == 0x03:  # Ctrl+C
        return "ctrl-c"
    if b == 0x04:  # Ctrl+D
        return "ctrl-d"
    if b == ord("q") or b == ord("Q"):
        return "q"

    return ""
