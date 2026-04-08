#!/usr/bin/env python3
"""Standalone test: can we read keystrokes and display them in Rich Live?"""
import os
import select
import sys
import time
import tty
import termios

from rich.console import Console
from rich.live import Live
from rich.panel import Panel

def main():
    if not sys.stdin.isatty():
        print("Needs a TTY.")
        return

    console = Console()
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    draft = ""
    log = []

    try:
        with Live(
            Panel(f"[dim]Type something... Ctrl+C to quit[/dim]"),
            console=console,
            screen=True,
            auto_refresh=False,
        ) as live:
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 0.05)
                if not ready:
                    continue

                data = os.read(fd, 64)
                if not data:
                    continue

                # Ctrl+C
                if data[0] == 0x03:
                    break

                # Backspace
                if data[0] in (0x7F, 0x08):
                    draft = draft[:-1]
                    live.update(Panel(
                        f"Draft: {draft}|\n\n[dim]Log: {', '.join(log[-5:])}[/dim]",
                        title="Input Test",
                    ), refresh=True)
                    continue

                # Enter
                if data[0] in (0x0D, 0x0A):
                    log.append(f"SENT: {draft}")
                    draft = ""
                    live.update(Panel(
                        f"Draft: |\n\n[dim]Log: {', '.join(log[-5:])}[/dim]",
                        title="Input Test",
                    ), refresh=True)
                    continue

                # Escape sequences (arrows etc)
                if data[0] == 0x1B:
                    log.append(f"ESC: {repr(data)}")
                    live.update(Panel(
                        f"Draft: {draft}|\n\n[dim]Log: {', '.join(log[-5:])}[/dim]",
                        title="Input Test",
                    ), refresh=True)
                    continue

                # Drain remaining bytes
                time.sleep(0.05)
                while True:
                    r, _, _ = select.select([sys.stdin], [], [], 0)
                    if not r:
                        break
                    data += os.read(fd, 64)

                text = data.decode(errors="replace")
                draft += text
                log.append(f"KEY: {repr(data)} -> {text}")

                live.update(Panel(
                    f"Draft: {draft}|\n\n[dim]Log: {', '.join(log[-5:])}[/dim]",
                    title="Input Test",
                ), refresh=True)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print("\nDone. Last log entries:")
        for entry in log[-10:]:
            print(f"  {entry}")


if __name__ == "__main__":
    main()
