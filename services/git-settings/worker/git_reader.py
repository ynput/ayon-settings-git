"""Read-only queries against the settings git repository.

Answers the addon's `/history`, `/diff` and `/bundle_history` endpoints
(see `api.py`) with the `git` binary. Runs `git` as asyncio subprocesses,
so queries don't block the tunnel or each other.

`git log -- <path>` is fast on long histories because the service keeps
a commit-graph with changed-path Bloom filters up to date (see
`git_writer.update_commit_graph`): git skips commits that didn't touch
the path without reading their trees.
"""

import asyncio
import re
from typing import Any

import yaml

from .paths import bundle_relpath, settings_relpath

BUNDLE_SENTINEL = "__bundle__"

# A revision as listed by `/history`. Anything else (ref names, `HEAD~1`,
# options) is rejected, so user input never reaches git as an option.
REVISION_RE = re.compile(r"[0-9a-fA-F]{4,64}")

# `git log` output: one record per commit, fields separated by FIELD_SEP.
FIELD_SEP = "\x1f"
RECORD_SEP = "\x1e"
LOG_FORMAT = (
    f"--format={RECORD_SEP}%H{FIELD_SEP}%aI{FIELD_SEP}%an{FIELD_SEP}%s"
)


class GitError(Exception):
    """A git command failed unexpectedly."""


async def _git(repo_path: str, *args: str) -> tuple[int, bytes, bytes]:
    # --literal-pathspecs: settings paths are plain file paths; `*`, `?`
    # or `:` in addon/project names must not act as pathspec magic.
    # core.quotePath=false: `--name-only` prints non-ASCII paths as is.
    process = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        repo_path,
        "--literal-pathspecs",
        "-c",
        "core.quotePath=false",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return process.returncode or 0, stdout, stderr


async def _has_commits(repo_path: str) -> bool:
    code, _, _ = await _git(
        repo_path, "rev-parse", "--verify", "--quiet", "HEAD^{commit}"
    )
    return code == 0


async def _log(repo_path: str, args: list[str]) -> str:
    """Run `git log` with LOG_FORMAT.

    Returns:
        The log output, or "" for a repository without commits.

    Raises:
        GitError: If `git log` fails.

    """
    if not await _has_commits(repo_path):
        return ""
    code, stdout, stderr = await _git(repo_path, "log", LOG_FORMAT, *args)
    if code != 0:
        raise GitError(stderr.decode("utf-8", errors="replace").strip())
    return stdout.decode("utf-8", errors="replace")


def _parse_entry(header: str) -> dict[str, Any]:
    revision, authored_at, author, message = header.split(FIELD_SEP, 3)
    return {
        "revision": revision,
        "authored_at": authored_at,
        "author": author,
        "message": message,
    }


async def get_file_history(
    repo_path: str, relpath: str
) -> list[dict[str, Any]]:
    """Return the commits that touched `relpath`, newest first.

    Returns:
        History entries: revision, authored_at, author, message.

    """
    output = await _log(repo_path, ["--", relpath])
    return [
        _parse_entry(record.strip("\n"))
        for record in output.split(RECORD_SEP)
        if record.strip()
    ]


async def get_file_at_revision(
    repo_path: str, relpath: str, revision: str
) -> str | None:
    """Return the content of `relpath` at `revision`.

    Returns:
        The file content, or None if `revision` is not a commit sha or
        the file doesn't exist there.

    """
    if not REVISION_RE.fullmatch(revision):
        return None
    return await _cat_blob(repo_path, f"{revision}:{relpath}")


async def _cat_blob(repo_path: str, spec: str) -> str | None:
    code, stdout, _ = await _git(repo_path, "cat-file", "blob", spec)
    if code != 0:
        return None
    return stdout.decode("utf-8", errors="replace")


def _bundle_variant(
    bundle_name: str, bundle_data: dict[str, Any]
) -> str | None:
    if bundle_data.get("isProduction"):
        return "production"
    if bundle_data.get("isStaging"):
        return "staging"
    if bundle_data.get("isDev"):
        # Dev bundles have no "production"/"staging" role of their own -
        # AYON keys their settings by the bundle's own name instead (see
        # `devBundleNames` handling in `SettingsGitPage.tsx`), and the
        # service commits `settings.changed` events under that same
        # variant string (see `process.py`). Not covered by the bootstrap
        # dump (`VARIANTS = ("production", "staging")` in `dump.py`), so
        # history here only goes back to the first such event.
        return bundle_name
    return None


async def get_bundle_history(
    repo_path: str, bundle_name: str, project_name: str | None
) -> dict[str, Any] | None:
    """Return the merged history of a bundle and the addons it pins.

    Merges the history of the bundle's pin file with the settings history
    of every addon it currently pins, for the bundle's variant.

    Scope for v1, matching the bootstrap policy (see `dump.py`): only the
    addon versions *currently* pinned by this bundle are considered. A
    bundle that is none of production/staging/dev has no variant of its
    own, so there is nothing to merge beyond its own pin-file history.

    Returns:
        The bundle's variant, pinned addons and merged history entries
        (each with the addons it `changed`), or None if the bundle has no
        tracked definition.

    """
    bundle_path = bundle_relpath(bundle_name)
    bundle_yaml = await _cat_blob(repo_path, f"HEAD:{bundle_path}")
    if bundle_yaml is None:
        return None

    bundle_data = yaml.safe_load(bundle_yaml) or {}
    addons_map: dict[str, str | None] = bundle_data.get("addons") or {}
    variant = _bundle_variant(bundle_name, bundle_data)

    # Path -> what the UI shows as changed, in display order: the bundle
    # pins first, then the addons in the bundle's order.
    changes: dict[str, dict[str, str | None]] = {
        bundle_path: {"addon_name": BUNDLE_SENTINEL, "addon_version": None}
    }
    if variant is not None:
        for addon_name, addon_version in addons_map.items():
            if not addon_version:
                continue
            relpath = settings_relpath(
                addon_name, addon_version, variant, project_name
            )
            changes[relpath] = {
                "addon_name": addon_name,
                "addon_version": addon_version,
            }

    # One `git log` for all paths; `--name-only` lists which of them
    # each commit touched.
    output = await _log(repo_path, ["--name-only", "--", *changes])
    entries = []
    for record in output.split(RECORD_SEP):
        if not record.strip():
            continue
        header, _, names = record.strip("\n").partition("\n")
        touched = set(names.split("\n"))
        entry = _parse_entry(header)
        entry["changed"] = [
            change for path, change in changes.items() if path in touched
        ]
        entries.append(entry)

    return {
        "bundle_name": bundle_name,
        "variant": variant,
        "addons": [
            {"addon_name": name, "addon_version": version}
            for name, version in addons_map.items()
        ],
        "entries": entries,
    }
