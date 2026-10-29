"""Service-side git queries against a real repository."""

from __future__ import annotations

import os
import subprocess

import pytest

from worker.git_reader import (
    BUNDLE_SENTINEL,
    get_bundle_history,
    get_file_at_revision,
    get_file_history,
)
from worker.git_writer import commit_all, ensure_repo, write_settings_file
from worker.paths import bundle_relpath, settings_relpath

CORE = settings_relpath("core", "1.0.0", "production")


@pytest.mark.asyncio
async def test_history_lists_only_commits_touching_the_file(
    bundle_repo,
) -> None:
    entries = await get_file_history(bundle_repo.path, CORE)

    assert [e["message"] for e in entries] == ["core 2", "core 1"]
    assert entries[0]["author"] == "alice"
    assert len(entries[0]["revision"]) == 40
    # Strict ISO 8601, parsed by the frontend's `new Date()`.
    assert entries[0]["authored_at"][4] == "-"
    assert entries[0]["authored_at"][10] == "T"


@pytest.mark.asyncio
async def test_history_includes_deletion(repo) -> None:
    repo.write(CORE, {"a": 1}, "add")
    repo.delete(CORE, "reset")

    entries = await get_file_history(repo.path, CORE)

    assert [e["message"] for e in entries] == ["reset", "add"]


@pytest.mark.asyncio
async def test_history_of_empty_or_missing_repo(repo, tmp_path) -> None:
    assert await get_file_history(repo.path, CORE) == []
    assert await get_file_history(str(tmp_path / "missing"), CORE) == []


@pytest.mark.asyncio
async def test_history_paths_are_literal(repo) -> None:
    # `*` must not match other addons as a glob pathspec would.
    repo.write(CORE, {"a": 1}, "core")
    star = settings_relpath("*", "1.0.0", "production")

    assert await get_file_history(repo.path, star) == []


@pytest.mark.asyncio
async def test_file_at_revision(bundle_repo) -> None:
    latest, first = await get_file_history(bundle_repo.path, CORE)

    first_yaml = await get_file_at_revision(
        bundle_repo.path, CORE, first["revision"]
    )
    latest_yaml = await get_file_at_revision(
        bundle_repo.path, CORE, latest["revision"][:8]
    )
    assert first_yaml == "a: 1\n"
    assert latest_yaml == "a: 2\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", ["HEAD", "--output=x", "HEAD~1", "zz"])
async def test_file_at_revision_rejects_non_shas(
    bundle_repo, revision
) -> None:
    assert (
        await get_file_at_revision(bundle_repo.path, CORE, revision) is None
    )


@pytest.mark.asyncio
async def test_file_at_revision_missing_file(bundle_repo) -> None:
    latest, *_ = await get_file_history(bundle_repo.path, CORE)
    missing = settings_relpath("core", "9.9.9", "production")

    assert (
        await get_file_at_revision(
            bundle_repo.path, missing, latest["revision"]
        )
        is None
    )


@pytest.mark.asyncio
async def test_bundle_history_merges_pinned_addons(bundle_repo) -> None:
    result = await get_bundle_history(bundle_repo.path, "prod", None)

    assert result["variant"] == "production"
    assert [e["message"] for e in result["entries"]] == [
        "core 2",
        "maya 1",
        "core 1",
        "bundle prod changed",
    ]
    assert result["entries"][0]["changed"] == [
        {"addon_name": "core", "addon_version": "1.0.0"}
    ]
    assert result["entries"][-1]["changed"] == [
        {"addon_name": BUNDLE_SENTINEL, "addon_version": None}
    ]
    assert {"addon_name": "nuke", "addon_version": None} in result["addons"]


@pytest.mark.asyncio
async def test_bundle_history_for_project(bundle_repo) -> None:
    result = await get_bundle_history(bundle_repo.path, "prod", "proj")

    assert [e["message"] for e in result["entries"]] == [
        "core proj",
        "bundle prod changed",
    ]


@pytest.mark.asyncio
async def test_bundle_history_commit_touching_several_files(repo) -> None:
    repo.write(
        bundle_relpath("dev1"),
        {"isDev": True, "addons": {"core": "1.0.0", "maya": "2.0.0"}},
        "bundle",
    )
    # Like the bootstrap, one commit with many files.
    write_settings_file(
        repo.path, settings_relpath("core", "1.0.0", "dev1"), {"a": 1}
    )
    write_settings_file(
        repo.path, settings_relpath("maya", "2.0.0", "dev1"), {"m": 1}
    )
    commit_all(repo.path, "both", "bob", "bob@example.com")

    result = await get_bundle_history(repo.path, "dev1", None)

    assert result["variant"] == "dev1"
    assert result["entries"][0]["changed"] == [
        {"addon_name": "core", "addon_version": "1.0.0"},
        {"addon_name": "maya", "addon_version": "2.0.0"},
    ]


@pytest.mark.asyncio
async def test_bundle_history_without_role(repo) -> None:
    repo.write(bundle_relpath("old"), {"addons": {"core": "1.0.0"}}, "bundle")
    repo.write(CORE, {"a": 1}, "core")

    result = await get_bundle_history(repo.path, "old", None)

    assert result["variant"] is None
    assert [e["message"] for e in result["entries"]] == ["bundle"]


@pytest.mark.asyncio
async def test_bundle_history_unknown_bundle(bundle_repo) -> None:
    assert await get_bundle_history(bundle_repo.path, "nope", None) is None


def test_commit_graph_has_bloom_filters(bundle_repo) -> None:
    chain = os.path.join(
        bundle_repo.path,
        ".git",
        "objects",
        "info",
        "commit-graphs",
        "commit-graph-chain",
    )
    assert os.path.exists(chain)
    # git reports using the filters for a path-limited log.
    result = subprocess.run(
        ["git", "-C", bundle_repo.path, "log", "--format=%H", "--", CORE],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "GIT_TRACE2_PERF": "1"},
    )
    assert "bloom" in result.stderr


def test_enables_auto_gc_on_old_repos(repo) -> None:
    subprocess.run(
        ["git", "-C", repo.path, "config", "gc.auto", "0"], check=True
    )

    assert ensure_repo(repo.path) is False
    result = subprocess.run(
        ["git", "-C", repo.path, "config", "--get", "gc.auto"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout == ""
