"""AYON Settings Git worker.

Watches `settings.changed` / `bundle.created` / `bundle.updated` events
via the standard AYON enroll mechanism and mirrors the resulting settings
state into a git repository as YAML files - one commit per event.

Also answers the addon's read endpoints (history, diff) from the same
repository, through a WebSocket tunnel to the AYON server (see
`tunnel.py` and `api.py`). The tunnel runs in its own thread, so it is
up while the initial bootstrap is still running.
"""

import asyncio
import logging
import os
import socket
import threading
import time
import traceback

import ayon_api

from .api import create_app
from .dump import bootstrap
from .git_writer import ensure_repo, update_commit_graph
from .process import process_event
from .tunnel import resolve_tunnel_url, serve_forever

log = logging.getLogger(__name__)

SOURCE_TOPICS = ["settings.changed", "bundle.created", "bundle.updated"]
TARGET_TOPIC = "settings_git.processed"


class SettingsGitWorker:
    def __init__(self) -> None:
        ayon_api.init_service()
        self.settings = ayon_api.get_service_addon_settings()

        self.repo_path: str = self.settings["repo_path"]
        self.poll_interval: int = self.settings.get("poll_interval", 5)
        self.author_name: str = self.settings.get(
            "commit_author_name", "AYON Settings Git"
        )
        self.author_email: str = self.settings.get(
            "commit_author_email", "settings-git@ayon.local"
        )
        self.remote_url: str = self.settings.get("remote_url", "")
        self.push_after_commit: bool = self.settings.get("push_after_commit", False)

    def prepare_repo(self) -> None:
        """Create and bootstrap the repository, or update an existing one."""
        was_created = ensure_repo(self.repo_path)
        if was_created:
            log.info("New repository, running initial bootstrap dump")
            bootstrap(self.repo_path, self.author_name, self.author_email)
        else:
            # Repositories from before the commit-graph was kept up to
            # date, or after it was removed by hand.
            update_commit_graph(self.repo_path)

    def run_forever(self) -> None:
        log.info("Settings Git worker started, watching %s", SOURCE_TOPICS)
        while True:
            try:
                self._tick()
            except Exception:
                log.error("Unhandled error in worker loop", exc_info=True)
                time.sleep(self.poll_interval)

    def _tick(self) -> None:
        job = ayon_api.enroll_event_job(
            SOURCE_TOPICS,
            TARGET_TOPIC,
            socket.gethostname(),
            description="Mirroring AYON settings into git",
            sequential=True,
            max_retries=3,
        )

        if not job:
            time.sleep(self.poll_interval)
            return

        try:
            source_event = ayon_api.get_event(job["dependsOn"])
            ayon_api.update_event(job["id"], status="in_progress")
            log.info("Processing event: %s", source_event)

            message = process_event(
                self.repo_path,
                source_event,
                self.author_email.split("@")[-1],
            )

            if self.push_after_commit and self.remote_url:
                from .git_writer import push

                push(self.repo_path, self.remote_url)

            ayon_api.update_event(
                job["id"], status="finished", description=message
            )
        except Exception:
            log.error("Failed to process event", exc_info=True)
            ayon_api.update_event(
                job["id"],
                status="failed",
                payload={"message": traceback.format_exc()},
            )


def _run_tunnel(repo_path: str) -> None:
    """Serve the read API through the tunnel.

    Exits the process if the tunnel stops for good, so ash restarts the
    service.
    """
    # `ayon_api.init_service()` already required both.
    server_url = os.environ["AYON_SERVER_URL"]
    api_key = os.environ["AYON_API_KEY"]

    async def serve() -> None:
        url = await resolve_tunnel_url(server_url, api_key)
        await serve_forever(
            create_app(repo_path), url, api_key, server_url=server_url
        )

    try:
        asyncio.run(serve())
    except Exception:
        log.critical("Tunnel to the AYON server stopped", exc_info=True)
    os._exit(1)


def service_main() -> None:
    logging.basicConfig(level=logging.INFO)
    ayon_api.set_sender_type("settings_git")
    worker = SettingsGitWorker()
    threading.Thread(
        target=_run_tunnel,
        args=(worker.repo_path,),
        name="tunnel",
        daemon=True,
    ).start()
    worker.prepare_repo()
    worker.run_forever()
