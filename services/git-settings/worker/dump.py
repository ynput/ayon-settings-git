"""One-time bootstrap: dump current DB settings state into a fresh repo.

Scope for v1: only settings reachable through a bundle currently marked
production or staging (that's what "current settings" means to a user -
addon versions that aren't pinned by any bundle are not interesting
history). Site-level settings are out of scope, see README.
"""

import logging

import ayon_api

from .git_writer import write_settings_file, commit_all
from .paths import settings_relpath, bundle_relpath

log = logging.getLogger(__name__)

VARIANTS = ("production", "staging")


def _bundle_addon_versions(bundle: dict) -> dict[str, str]:
    return bundle.get("addons", {})


def bootstrap(repo_path: str, author_name: str, author_email: str) -> None:
    log.info("Bootstrapping settings-git repository at %s", repo_path)

    bundles_info = ayon_api.get_bundles()
    bundles = bundles_info.get("bundles", [])
    production_bundle = bundles_info.get("productionBundle")
    staging_bundle = bundles_info.get("stagingBundle")

    project_names = list(ayon_api.get_project_names())

    for bundle in bundles:
        write_settings_file(
            repo_path, bundle_relpath(bundle["name"]), bundle
        )

        variant = None
        if bundle["name"] == production_bundle:
            variant = "production"
        elif bundle["name"] == staging_bundle:
            variant = "staging"
        if variant is None:
            # Not an active bundle - keep the bundle definition file
            # above, but don't dump per-addon settings for it.
            continue

        for addon_name, addon_version in _bundle_addon_versions(bundle).items():
            _dump_addon_settings(
                repo_path, addon_name, addon_version, variant, project_names
            )

    committed = commit_all(
        repo_path, "Initial import from AYON database", author_name, author_email
    )
    if committed:
        log.info("Initial import committed")
    else:
        log.info("Nothing to import - repository left empty")


def _dump_addon_settings(
    repo_path: str,
    addon_name: str,
    addon_version: str,
    variant: str,
    project_names: list[str],
) -> None:
    try:
        studio_settings = ayon_api.get_addon_studio_settings(
            addon_name, addon_version, variant=variant
        )
    except Exception:
        log.warning(
            "Could not read studio settings for %s %s (%s), skipping",
            addon_name,
            addon_version,
            variant,
            exc_info=True,
        )
        return

    write_settings_file(
        repo_path,
        settings_relpath(addon_name, addon_version, variant),
        studio_settings,
    )

    for project_name in project_names:
        try:
            project_settings = ayon_api.get_addon_project_settings(
                addon_name,
                addon_version,
                project_name,
                variant=variant,
                use_site=False,
            )
        except Exception:
            continue

        write_settings_file(
            repo_path,
            settings_relpath(addon_name, addon_version, variant, project_name),
            project_settings,
        )
