"""Server-side addon for managing AYON settings in a git repository."""

from collections.abc import Awaitable, Callable
from typing import Any, Type

from ayon_server.addons import BaseServerAddon
from ayon_server.api.auth import user_from_request
from ayon_server.api.dependencies import CurrentUser
from ayon_server.entities import UserEntity
from ayon_server.exceptions import AyonException, ForbiddenException
from fastapi import APIRouter, Request, Response, WebSocket

from .settings import SettingsGitSettings
from .tunnel import (
    CLOSE_FORBIDDEN,
    CLOSE_UNAUTHORIZED,
    TunnelHub,
    TunnelRejectedError,
    proxy_request,
    serve_tunnel,
)
from .tunnel.redis_bus import RedisTunnelBus

# Read endpoints answered by the service, at the same path in its app.
SERVICE_ENDPOINTS = {
    "/history": "List git revisions for a given settings scope",
    "/diff": "Get the settings content at a given revision",
    "/bundle_history": (
        "List git revisions across every addon pinned by a bundle"
    ),
}


async def _authenticate_service(websocket: WebSocket) -> str:
    """Return the service user that opened a tunnel WebSocket.

    The HTTP auth middleware doesn't run for WebSockets, so the API key
    is checked here. Only service users may open a tunnel.

    Returns:
        Name of the service user.

    Raises:
        TunnelRejectedError: If the caller is not a service user.

    """
    try:
        user = await user_from_request(websocket)  # type: ignore[arg-type]
    except AyonException as exc:
        raise TunnelRejectedError(
            CLOSE_UNAUTHORIZED, f"Unauthorized: {exc}"
        ) from exc
    if not user.is_service:
        raise TunnelRejectedError(
            CLOSE_FORBIDDEN, f"User '{user.name}' is not a service user"
        )
    return user.name


class SettingsGitAddon(BaseServerAddon):
    """Mirrors AYON settings into a git repository for history/diff/backup.

    All git work happens in this addon's `git-settings` service, which
    has the `git` binary: it commits on `settings.changed` / `bundle.*`
    events and answers the read endpoints. The service connects out to
    this addon's WebSocket (`/api/addons/settings_git/<version>/ws`) and
    the endpoints are forwarded to it through that tunnel, so the server
    needs neither `git` nor access to the repository.

    Restoring a revision is intentionally NOT done by writing to the git
    working tree directly - it re-submits the old settings payload through
    the normal AYON settings API, so it goes through the usual validation
    and produces a normal `settings.changed` event (which the service will
    then commit as a new, forward-moving revision).
    """

    settings_model: Type[SettingsGitSettings] = SettingsGitSettings
    addon_type = "server"
    # Settings-scope addons are embedded by the shell as a plain iframe
    # pointing at this addon's own `frontend/dist/index.html` - no
    # `frontend_modules` (that's Module Federation, for project/dashboard
    # scopes only; see frontend/vite.config.ts and frontend/src/main.tsx).
    frontend_scopes: dict[str, Any] = {"settings": {}}

    def initialize(self) -> None:
        """Set up the read endpoints and the service tunnel."""
        # Each addon version has its own hub and Redis keys, so production
        # and staging services each serve their own version's endpoints.
        self.tunnels = TunnelHub(
            RedisTunnelBus(f"settings_git-{self.version}:")
        )
        router = APIRouter()
        for path, description in SERVICE_ENDPOINTS.items():
            router.add_api_route(
                path,
                self._forward_to(path),
                methods=["GET"],
                description=description,
            )
        self.add_router(router)

    def _forward_to(
        self, path: str
    ) -> Callable[[Request, UserEntity], Awaitable[Response]]:
        async def endpoint(request: Request, user: CurrentUser) -> Response:
            # The repository holds every studio and project setting
            # verbatim (no secret redaction), so only managers may read it,
            # like the settings themselves.
            if not user.is_manager:
                msg = "Only managers can read settings"
                raise ForbiddenException(msg)
            return await proxy_request(request, self.tunnels, user.name, path)

        return endpoint

    async def ws(self, websocket: WebSocket) -> None:
        """Tunnel connection of the git-settings service."""
        await serve_tunnel(websocket, self.tunnels, _authenticate_service)
