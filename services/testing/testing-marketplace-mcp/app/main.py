from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.marketplace import Marketplace
from app.server import build_server
from app.settings import load_marketplace_settings

# Without this the app assumes localhost and answers 421 to harness calling http://testing-marketplace-mcp:8121.
# An explicit setting also empties the origins, and browsers (only they send Origin) would get 403
SECURITY = TransportSecuritySettings(
    allowed_hosts=[
        "testing-marketplace-mcp:*",
        "localhost:*",
        "127.0.0.1:*",
        "[::1]:*",
    ],
    allowed_origins=["http://localhost:*", "http://127.0.0.1:*", "http://[::1]:*"],
)


def default_server() -> MCPServer:
    return build_server(Marketplace(str(load_marketplace_settings().url)))


# uvicorn calls this with --factory, so importing the module reads no env; a missing MARKETPLACE_URL fails the boot.
# Tests build an app each: a session manager can run() only once
def create_app(server: MCPServer | None = None) -> Starlette:
    server = server or default_server()

    # registered before streamable_http_app(): it copies the custom routes at that call
    @server.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    # stateless: no sessions even for 2025-era clients; every call is one self-contained request
    return server.streamable_http_app(stateless_http=True, transport_security=SECURITY)
