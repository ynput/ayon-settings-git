"""Writes settings dumps into the git repository."""

import logging
import os
import subprocess
from typing import Any

import yaml

log = logging.getLogger(__name__)


def yaml_dump(data: dict[str, Any]) -> str:
    return yaml.safe_dump(
        data,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
    )


def ensure_repo(repo_path: str) -> bool:
    """Make sure `repo_path` is a git repository. Returns True if it was
    just created (empty)."""

    os.makedirs(repo_path, exist_ok=True)
    if os.path.isdir(os.path.join(repo_path, ".git")):
        _enable_auto_gc(repo_path)
        return False

    _run(repo_path, "init")
    return True


def _enable_auto_gc(repo_path: str) -> None:
    """Undo `gc.auto 0`, set on repositories created by earlier versions.

    The server used to read loose objects directly, which needed objects
    never to be packed. All reads now go through this service's `git`,
    so the repository can be packed like any other.
    """
    result = subprocess.run(
        ["git", "-C", repo_path, "config", "--get", "gc.auto"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout.strip() == "0":
        _run(repo_path, "config", "--unset", "gc.auto")


def update_commit_graph(repo_path: str) -> None:
    """Write the commit-graph with changed-path Bloom filters.

    With them, `git log -- <path>` (the `/history` endpoint) skips
    commits that didn't touch the path without reading their trees, so it
    stays fast however long the history gets. `--split` only writes the
    commits added since the last call, merging layers as they grow.
    Best effort: history still works without it, only slower.
    """
    try:
        _run(
            repo_path,
            "commit-graph",
            "write",
            "--reachable",
            "--changed-paths",
            "--split",
        )
    except subprocess.CalledProcessError as exc:
        log.warning("Could not write the commit-graph: %s", exc.stderr)


def write_settings_file(
    repo_path: str,
    relpath: str,
    data: dict[str, Any],
) -> str:
    """Write `data` as YAML to `relpath` inside the repo. Returns the
    absolute path written."""

    abspath = os.path.join(repo_path, relpath)
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    with open(abspath, "w", encoding="utf-8") as stream:
        stream.write(yaml_dump(data))
    return abspath


def delete_settings_file(repo_path: str, relpath: str) -> bool:
    abspath = os.path.join(repo_path, relpath)
    if not os.path.exists(abspath):
        return False
    os.remove(abspath)
    return True


def commit_all(
    repo_path: str,
    message: str,
    author_name: str,
    author_email: str,
) -> bool:
    """Stage everything and commit. Returns False if there was nothing
    to commit (clean tree)."""

    _run(repo_path, "add", "-A")
    status = _run(repo_path, "status", "--porcelain")
    if not status.strip():
        return False

    env = {
        "GIT_AUTHOR_NAME": author_name,
        "GIT_AUTHOR_EMAIL": author_email,
        "GIT_COMMITTER_NAME": author_name,
        "GIT_COMMITTER_EMAIL": author_email,
    }
    _run(repo_path, "commit", "-m", message, extra_env=env)
    update_commit_graph(repo_path)
    return True


def push(repo_path: str, remote_url: str) -> None:
    remotes = _run(repo_path, "remote")
    if "origin" not in remotes.split():
        _run(repo_path, "remote", "add", "origin", remote_url)
    _run(repo_path, "push", "origin", "HEAD")


def _run(
    repo_path: str,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> str:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        ["git", "-C", repo_path, *args],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return result.stdout
