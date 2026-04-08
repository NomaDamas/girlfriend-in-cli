import subprocess
import sys
from pathlib import Path


def _auto_reinstall() -> None:
    """Auto-reinstall package from source on every launch to pick up code changes."""
    # Find the project root (where pyproject.toml lives)
    pkg_dir = Path(__file__).resolve().parent
    for candidate in (pkg_dir, *pkg_dir.parents):
        if (candidate / "pyproject.toml").exists():
            root = candidate
            break
    else:
        return  # Not running from source tree

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", str(root), "--quiet", "--quiet"],
            capture_output=True,
            timeout=30,
        )
    except Exception:
        pass  # Don't block the app if install fails


_auto_reinstall()

from .cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
