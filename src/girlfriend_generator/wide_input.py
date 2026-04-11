"""Wide-character-aware input replacement for broken macOS libedit.

macOS Python's `input()` uses libedit which miscalculates cursor position
for CJK (Korean, Japanese, Chinese) wide characters — each Korean char
occupies 2 display cells, but libedit moves the cursor back only 1 cell
on backspace, leaving ghost characters behind.

This module provides `wide_input()` — a raw-mode input implementation
that explicitly tracks display width and correctly erases wide chars.
"""

from __future__ import annotations

import os
import select
import sys
import termios
import tty
import unicodedata


def char_width(ch: str) -> int:
    """Return display column width of a single character (0, 1, or 2)."""
    if not ch:
        return 0
    # Zero-width and combining characters
    if unicodedata.category(ch) in ("Mn", "Me", "Cf"):
        return 0
    # East Asian Wide / Fullwidth
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ("W", "F"):
        return 2
    # Emoji heuristic: many emoji are wide
    if ord(ch) >= 0x1F000:
        return 2
    return 1


def _text_width(s: str) -> int:
    return sum(char_width(c) for c in s)


def wide_input(prompt: str = "", default: str = "") -> str:
    """Read a line of text with correct Korean/CJK backspace handling.

    Uses raw cbreak mode and manually manages display. Supports:
    - Multi-byte UTF-8 (Korean, emoji, etc.)
    - Backspace that properly erases wide chars
    - Ctrl+C, Ctrl+D, Enter
    - Default value (shown, pre-filled buffer)
    """
    if not sys.stdin.isatty():
        try:
            raw = input(prompt) if not default else (input(prompt) or default)
        except (EOFError, KeyboardInterrupt):
            return default
        return raw

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)

    buf = default
    try:
        tty.setcbreak(fd)
        # Write prompt + default text
        sys.stdout.write(prompt)
        if default:
            sys.stdout.write(default)
        sys.stdout.flush()

        while True:
            ready, _, _ = select.select([sys.stdin], [], [], None)
            if not ready:
                continue
            data = os.read(fd, 64)
            if not data:
                break

            # Ctrl+C
            if data == b"\x03":
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                raise KeyboardInterrupt
            # Ctrl+D
            if data == b"\x04":
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                if not buf:
                    raise EOFError
                return buf
            # Enter
            if data in (b"\r", b"\n"):
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                return buf
            # Backspace / Delete
            if data in (b"\x7f", b"\x08"):
                if buf:
                    last = buf[-1]
                    buf = buf[:-1]
                    width = char_width(last)
                    if width > 0:
                        # Move back, overwrite with spaces, move back again
                        sys.stdout.write("\b" * width + " " * width + "\b" * width)
                        sys.stdout.flush()
                continue
            # Escape sequences (arrow keys, etc.) — ignore
            if data[0:1] == b"\x1b":
                # Drain the rest
                while True:
                    r, _, _ = select.select([sys.stdin], [], [], 0)
                    if not r:
                        break
                    os.read(fd, 1)
                continue

            # Drain any remaining multi-byte bytes
            time_drain_iterations = 0
            while time_drain_iterations < 3:
                r, _, _ = select.select([sys.stdin], [], [], 0.005)
                if not r:
                    break
                extra = os.read(fd, 64)
                if not extra:
                    break
                data += extra
                time_drain_iterations += 1

            # Decode safely
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                # Try trimming incomplete trailing bytes
                decoded = None
                for trim in range(1, 4):
                    try:
                        decoded = data[:-trim].decode("utf-8")
                        break
                    except UnicodeDecodeError:
                        continue
                text = decoded or ""

            # Filter only printable
            printable = "".join(c for c in text if c.isprintable())
            if printable:
                buf += printable
                sys.stdout.write(printable)
                sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    return buf


def wide_multiline_input(prompt: str = "  > ") -> str:
    """Read multiple lines until an empty line is entered.

    Each line is collected with wide_input() so Korean backspace works.
    Returns the joined text separated by newlines.
    """
    lines: list[str] = []
    while True:
        try:
            line = wide_input(prompt)
        except (EOFError, KeyboardInterrupt):
            break
        if not line.strip():
            break
        lines.append(line)
    return "\n".join(lines)
