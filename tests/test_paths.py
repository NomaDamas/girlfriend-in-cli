import os
import subprocess
import sys
from pathlib import Path

from girlfriend_generator.paths import (
    ROOT_ENV_VAR,
    bundled_persona_dir,
    bundled_session_dir,
    project_root,
    resolve_persona_path,
    resolve_session_dir,
)


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

    assert "wonyoung-idol.json" in result.stdout
    assert "dua-international.json" in result.stdout


def test_project_root_accepts_valid_environment_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "personas").mkdir()
    monkeypatch.setenv(ROOT_ENV_VAR, str(tmp_path))

    assert project_root() == tmp_path.resolve()
    assert bundled_persona_dir() == tmp_path.resolve() / "personas"
    assert bundled_session_dir() == tmp_path.resolve() / "sessions"


def test_resolve_persona_path_finds_repo_relative_persona_from_outside_repo(
    tmp_path: Path,
) -> None:
    root = project_root()

    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        resolved = resolve_persona_path(Path("personas/wonyoung-idol.json"))
    finally:
        os.chdir(original_cwd)

    assert resolved == root / "personas" / "wonyoung-idol.json"


def test_resolve_session_dir_keeps_relative_exports_under_project_root() -> None:
    root = project_root()

    assert resolve_session_dir(Path("sessions/custom")) == root / "sessions" / "custom"


def test_pyproject_exposes_only_terminal_cli_entrypoint() -> None:
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
        encoding="utf-8"
    )

    assert 'girlfriend-generator = "girlfriend_generator.cli:main"' in pyproject
    assert "girlfriend-generator-api" not in pyproject
