from pathlib import Path
import types

from girlfriend_generator.updater import (
    InstallContext,
    _run_brew_update,
    build_update_command,
    is_newer_version,
    normalize_version,
)


def test_normalize_version_handles_v_prefix() -> None:
    assert normalize_version("v0.1.2") == (0, 1, 2)


def test_is_newer_version_compares_semver_like_values() -> None:
    assert is_newer_version("0.1.1", current="0.1.0") is True
    assert is_newer_version("0.1.0", current="0.1.0") is False
    assert is_newer_version("0.0.9", current="0.1.0") is False


def test_build_update_command_for_git_install() -> None:
    command = build_update_command(
        InstallContext(method="git", repo_root=Path("/tmp/repo")),
        "v0.1.0",
    )

    assert command == ["bash", "scripts/update_release.sh", "v0.1.0"]


def test_build_update_command_for_unknown_install() -> None:
    assert build_update_command(InstallContext(method="unknown"), "v0.1.0") is None


def test_run_brew_update_refreshes_tap_before_upgrade(monkeypatch) -> None:
    calls = []

    def fake_run(command, capture_output, text, check):
        calls.append(command)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    ok, _detail = _run_brew_update(InstallContext(method="brew"))

    assert ok is True
    assert calls == [
        ["brew", "update"],
        ["brew", "untap", "NomaDamas/girlfriend-in-cli"],
        ["brew", "tap", "NomaDamas/girlfriend-in-cli", "https://github.com/NomaDamas/brew-girlfriend-in-cli.git"],
        ["brew", "upgrade", "girlfriend-in-cli"],
    ]
