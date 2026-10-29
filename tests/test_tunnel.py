"""End-to-end: the addon's endpoints answered by the service's app,
through the real tunnel code on both sides."""

from __future__ import annotations

import httpx
import pytest
from conftest import REPO_ROOT
from fake_ayon_server import SERVICE_KEY, FakeWorker, background, running

from worker.api import create_app
from worker.paths import settings_relpath
from worker.tunnel import TunnelClient, tunnel_url


def test_protocol_copies_are_identical() -> None:
    service = (
        REPO_ROOT / "services" / "git-settings" / "worker" / "tunnel_protocol.py"
    )
    addon = REPO_ROOT / "server" / "tunnel" / "protocol.py"
    assert service.read_bytes() == addon.read_bytes(), (
        "server/tunnel/protocol.py must be a copy of "
        "services/git-settings/worker/tunnel_protocol.py"
    )


def test_protocol_matches_ayon_mcp() -> None:
    mcp = (
        REPO_ROOT.parent / "ayon-mcp" / "server" / "mcp_tunnel" / "protocol.py"
    )
    if not mcp.exists():
        pytest.skip("ayon-mcp is not checked out next to this repo")
    addon = REPO_ROOT / "server" / "tunnel" / "protocol.py"
    assert addon.read_bytes() == mcp.read_bytes()


def test_tunnel_url() -> None:
    assert (
        tunnel_url("https://ayon.example.com/", "0.2.0")
        == "wss://ayon.example.com/api/addons/settings_git/0.2.0/ws"
    )


@pytest.mark.asyncio
async def test_endpoints_through_tunnel(bundle_repo) -> None:
    async with running(FakeWorker()) as worker:
        client = TunnelClient(
            create_app(bundle_repo.path), worker.ws_url, SERVICE_KEY
        )
        async with background(client.run()):
            await worker.wait_for_tunnels()
            async with httpx.AsyncClient(base_url=worker.base_url) as http:
                query = {"addon_name": "core", "addon_version": "1.0.0"}
                response = await http.get("/history", params=query)
                history = response.json()
                assert [e["message"] for e in history] == ["core 2", "core 1"]

                revision = history[0]["revision"]
                diff = await http.get(
                    "/diff", params={**query, "revision": revision}
                )
                assert diff.status_code == 200
                assert diff.json() == {
                    "revision": revision,
                    "path": settings_relpath("core", "1.0.0", "production"),
                    "yaml": "a: 2\n",
                }

                missing = await http.get(
                    "/diff", params={**query, "revision": "abcd"}
                )
                assert missing.status_code == 404

                assert (await http.get("/history")).status_code == 400

                response = await http.get(
                    "/bundle_history", params={"bundle_name": "prod"}
                )
                bundle = response.json()
                assert bundle["variant"] == "production"
                assert len(bundle["entries"]) == 4


@pytest.mark.asyncio
async def test_service_not_connected() -> None:
    async with running(FakeWorker()) as worker:
        async with httpx.AsyncClient(base_url=worker.base_url) as http:
            response = await http.get(
                "/history", params={"addon_name": "a", "addon_version": "1"}
            )
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Settings Git service is not connected"
    }
