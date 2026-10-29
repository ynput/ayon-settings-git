"""Test configuration and shared fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent

# Make the service's `worker` package importable.
sys.path.insert(0, str(REPO_ROOT / "services" / "git-settings"))
# Make the addon's tunnel code (`tunnel`) importable without importing the
# addon itself, which needs the AYON server.
sys.path.append(str(REPO_ROOT / "server"))

from worker.git_writer import (  # noqa: E402
    commit_all,
    delete_settings_file,
    ensure_repo,
    write_settings_file,
)
from worker.paths import bundle_relpath, settings_relpath  # noqa: E402


class RepoBuilder:
    """Builds a settings repository the way the service does."""

    def __init__(self, path: Path) -> None:
        self.path = str(path)
        ensure_repo(self.path)

    def write(self, relpath: str, data: dict, message: str, author: str = "alice") -> None:
        write_settings_file(self.path, relpath, data)
        commit_all(self.path, message, author, f"{author}@example.com")

    def delete(self, relpath: str, message: str) -> None:
        delete_settings_file(self.path, relpath)
        commit_all(self.path, message, "alice", "alice@example.com")


@pytest.fixture
def repo(tmp_path: Path) -> RepoBuilder:
    return RepoBuilder(tmp_path / "repo")


@pytest.fixture
def bundle_repo(repo: RepoBuilder) -> RepoBuilder:
    """Production bundle pinning core 1.0.0 and maya 2.0.0, plus noise."""

    repo.write(
        bundle_relpath("prod"),
        {"name": "prod", "isProduction": True,
         "addons": {"core": "1.0.0", "maya": "2.0.0", "nuke": None}},
        "bundle prod changed",
    )
    repo.write(settings_relpath("core", "1.0.0", "production"), {"a": 1}, "core 1")
    repo.write(settings_relpath("nuke", "3.0.0", "production"), {"n": 1}, "nuke, not pinned")
    repo.write(settings_relpath("maya", "2.0.0", "production"), {"m": 1}, "maya 1")
    repo.write(settings_relpath("core", "1.0.0", "staging"), {"s": 1}, "core staging")
    repo.write(
        settings_relpath("core", "1.0.0", "production", "proj"), {"p": 1}, "core proj"
    )
    repo.write(settings_relpath("core", "1.0.0", "production"), {"a": 2}, "core 2")
    return repo
