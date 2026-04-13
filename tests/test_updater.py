from pathlib import Path

from girlfriend_generator.updater import (
    InstallContext,
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
