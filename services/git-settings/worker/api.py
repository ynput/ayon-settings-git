"""HTTP app answering the addon's read endpoints through the tunnel.

The addon forwards `/api/addons/settings_git/<version>/{history,diff,
bundle_history}` here unchanged (query string included, credentials
removed) after checking the caller is an AYON manager. See `tunnel.py`.
"""

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .git_reader import (
    get_bundle_history,
    get_file_at_revision,
    get_file_history,
)
from .paths import bundle_relpath, settings_relpath


def _error(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


def _settings_relpath(request: Request) -> str | None:
    params = request.query_params
    addon_name = params.get("addon_name")
    addon_version = params.get("addon_version")
    if not addon_name or not addon_version:
        return None
    return settings_relpath(
        addon_name,
        addon_version,
        params.get("variant") or "production",
        params.get("project_name") or None,
    )


def create_app(repo_path: str) -> Starlette:
    """Create the app answering the addon's endpoints from `repo_path`.

    Returns:
        The ASGI app.

    """

    async def history(request: Request) -> JSONResponse:
        relpath = _settings_relpath(request)
        if relpath is None:
            return _error(400, "addon_name and addon_version are required")
        return JSONResponse(await get_file_history(repo_path, relpath))

    async def diff(request: Request) -> JSONResponse:
        params = request.query_params
        revision = params.get("revision")
        if not revision:
            return _error(400, "revision is required")
        bundle_name = params.get("bundle_name")
        relpath = (
            bundle_relpath(bundle_name)
            if bundle_name
            else _settings_relpath(request)
        )
        if relpath is None:
            return _error(
                400,
                "Either bundle_name or addon_name+addon_version is required",
            )
        content = await get_file_at_revision(repo_path, relpath, revision)
        if content is None:
            return _error(404, f"Revision {revision} not found for {relpath}")
        return JSONResponse(
            {"revision": revision, "path": relpath, "yaml": content}
        )

    async def bundle_history(request: Request) -> JSONResponse:
        params = request.query_params
        bundle_name = params.get("bundle_name")
        if not bundle_name:
            return _error(400, "bundle_name is required")
        result = await get_bundle_history(
            repo_path, bundle_name, params.get("project_name") or None
        )
        if result is None:
            return _error(
                404, f"No tracked bundle definition for {bundle_name}"
            )
        return JSONResponse(result)

    return Starlette(
        routes=[
            Route("/history", history),
            Route("/diff", diff),
            Route("/bundle_history", bundle_history),
        ]
    )
