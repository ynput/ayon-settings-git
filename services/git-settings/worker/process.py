import logging
from typing import Any

import ayon_api

from .git_writer import write_settings_file, delete_settings_file, commit_all
from .paths import settings_relpath, bundle_relpath

log = logging.getLogger(__name__)


def process_event(
    repo_path: str,
    source_event: dict[str, Any],
    author_email_domain: str,
) -> str:
    """Handle one source event, write the resulting file(s), commit.

    Returns a short human-readable summary of what was done, used for
    logging / the commit message.
    """

    topic = source_event["topic"]
    summary = source_event.get("summary") or {}
    user_name = source_event.get("user") or "unknown"
    author_name = user_name
    author_email = f"{user_name}@{author_email_domain}"

    if topic == "settings.changed":
        message = _process_settings_changed(repo_path, source_event, summary)
    elif topic in ("bundle.created", "bundle.updated"):
        message = _process_bundle_event(repo_path, summary)
    else:
        log.debug("Ignoring unhandled topic %s", topic)
        return "ignored"

    if message is None:
        return "skipped (no addon settings model / site-level change)"

    commit_all(repo_path, message, author_name, author_email)
    return message


def _process_settings_changed(
    repo_path: str,
    source_event: dict[str, Any],
    summary: dict[str, Any],
) -> str | None:
    if summary.get("site_id"):
        # Per-user site settings are out of scope for v1.
        return None

    addon_name = summary["addon_name"]
    addon_version = summary["addon_version"]
    variant = summary.get("variant") or "production"
    project_name = source_event.get("project")

    relpath = settings_relpath(addon_name, addon_version, variant, project_name)

    new_value = (source_event.get("payload") or {}).get("newValue")
    if new_value is None:
        # audit_trail may be disabled server-side, or settings were
        # cleared (reset to defaults) - re-fetch current state instead
        # of relying solely on the event payload.
        new_value = _fetch_current_settings(
            addon_name, addon_version, variant, project_name
        )

    if not new_value:
        deleted = delete_settings_file(repo_path, relpath)
        if not deleted:
            return None
        return (
            f"{addon_name} {addon_version} {variant} "
            f"{'(' + project_name + ') ' if project_name else ''}"
            "settings reset to defaults"
        )

    write_settings_file(repo_path, relpath, new_value)
    return (
        f"{addon_name} {addon_version} {variant} "
        f"{'(' + project_name + ') ' if project_name else ''}settings changed"
    )


def _fetch_current_settings(
    addon_name: str,
    addon_version: str,
    variant: str,
    project_name: str | None,
) -> dict[str, Any]:
    if project_name:
        return ayon_api.get_addon_project_settings(
            addon_name, addon_version, project_name, variant=variant, use_site=False
        )
    return ayon_api.get_addon_studio_settings(
        addon_name, addon_version, variant=variant
    )


def _process_bundle_event(repo_path: str, summary: dict[str, Any]) -> str | None:
    bundle_name = summary.get("name")
    if not bundle_name:
        return None

    bundles_info = ayon_api.get_bundles()
    bundle = next(
        (b for b in bundles_info.get("bundles", []) if b["name"] == bundle_name),
        None,
    )
    if bundle is None:
        return None

    write_settings_file(repo_path, bundle_relpath(bundle_name), bundle)
    return f"bundle {bundle_name} changed"
