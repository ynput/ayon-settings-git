"""Proxy for the settings-git service, reached through a WebSocket tunnel.

The service connects to the addon's WebSocket
(``/api/addons/settings_git/{version}/ws``) and answers the addon's
read endpoints (``/history``, ``/diff``, ``/bundle_history``) through it,
so it needs no listening port, public IP or ingress. See ``protocol`` for
the wire format and ``hub`` for routing across server workers.

Copied from ayon-mcp (``server/mcp_tunnel``). ``protocol`` is byte for
byte the same, so both addons speak one protocol and the code can later
move into a shared package. The other modules differ only in log
wording, and ``proxy_request`` takes the service path to forward to.

Only ``redis_bus`` needs the AYON server; the rest runs anywhere, which
lets the tests use it without one.
"""

from .endpoint import (
    CLOSE_FORBIDDEN,
    CLOSE_UNAUTHORIZED,
    CLOSE_UNSUPPORTED,
    TunnelRejectedError,
    serve_tunnel,
)
from .hub import TunnelHub
from .proxy import proxy_request

__all__ = [
    "CLOSE_FORBIDDEN",
    "CLOSE_UNAUTHORIZED",
    "CLOSE_UNSUPPORTED",
    "TunnelHub",
    "TunnelRejectedError",
    "proxy_request",
    "serve_tunnel",
]
