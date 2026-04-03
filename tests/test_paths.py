import os
import subprocess
import sys
from pathlib import Path

from girlfriend_generator.paths import bundled_persona_dir, bundled_session_dir, project_root


def test_project_root_defaults_stay_inside_repository() -> None:
    root = project_root()

    assert root == Path(__file__).resolve().parents[1]
    assert bundled_persona_dir() == root / "personas"
    assert bundled_session_dir() == root / "sessions"


def test_cli_lists_bundled_personas_outside_repository(tmp_path: Path) -> None:
    root = project_root()
    src_dir = root / "src"
    env = {**os.environ, "PYTHONPATH": str(src_dir)}

    result = subprocess.run(
        [sys.executable, "-m", "girlfriend_generator", "--list-personas"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "han-seo-jin-crush.json" in result.stdout
    assert "yu-na-girlfriend.json" in result.stdout
