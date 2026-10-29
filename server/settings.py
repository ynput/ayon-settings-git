from ayon_server.settings import BaseSettingsModel, SettingsField


class SettingsGitSettings(BaseSettingsModel):
    repo_path: str = SettingsField(
        "/storage/settings_git",
        title="Repository path",
        description=(
            "Filesystem path inside the service container where the "
            "settings git repository lives. Must be on persistent "
            "storage (e.g. under /storage, which ash forwards into "
            "service containers)."
        ),
    )

    remote_url: str = SettingsField(
        "",
        title="Remote URL",
        description=(
            "Optional git remote to push commits to (e.g. a bare repo, "
            "GitHub/GitLab). Leave empty to keep the repository local-only. "
            "Whoever can read this remote can read all studio/project "
            "settings verbatim (no secret redaction) - treat access to it "
            "the same as direct database access."
        ),
    )

    push_after_commit: bool = SettingsField(
        False,
        title="Push after commit",
        description="Push to 'remote_url' after every commit.",
    )

    poll_interval: int = SettingsField(
        5,
        title="Poll interval (seconds)",
        description="How often the worker polls for new events when idle.",
        gt=0,
    )

    commit_author_name: str = SettingsField(
        "AYON Settings Git",
        title="Commit author name",
    )

    commit_author_email: str = SettingsField(
        "settings-git@ayon.local",
        title="Commit author email",
    )
