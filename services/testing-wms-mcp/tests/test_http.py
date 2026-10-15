import json
from collections.abc import Iterator

import httpx2
import pytest
from starlette.testclient import TestClient

from app.main import create_app
from app.server import build_server
from app.wms import Wms

# a 2025-era client's first request: the handshake that harness's MCP client (mcp 1.x) will send
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
# without the JSON content type the transport answers 400 before it even looks at Host
HEADERS = {
    "content-type": "application/json",
    "accept": "application/json, text/event-stream",
}


# `with` runs the lifespan, which starts the session manager; a fresh app per test, since it starts only once
@pytest.fixture
def http() -> Iterator[TestClient]:
    api = httpx2.MockTransport(lambda request: httpx2.Response(200, text='{"id":1}'))
    server = build_server(Wms("http://testing-wms:8100", transport=api))
    with TestClient(create_app(server)) as client:
        yield client


@pytest.mark.parametrize("host", ["testing-wms-mcp:8101", "localhost:8101"])
def test_allowed_hosts_get_through(http: TestClient, host: str):
    response = http.post("/mcp", json=INITIALIZE, headers=HEADERS | {"host": host})

    assert response.status_code == 200


def test_unknown_host_is_rejected(http: TestClient):
    response = http.post(
        "/mcp", json=INITIALIZE, headers=HEADERS | {"host": "evil.example"}
    )

    assert response.status_code == 421
    assert response.text == "Invalid Host header"


def test_foreign_origin_is_rejected(http: TestClient):
    headers = HEADERS | {"host": "localhost:8101", "origin": "http://evil.example"}

    assert http.post("/mcp", json=INITIALIZE, headers=headers).status_code == 403


def test_health(http: TestClient):
    assert http.get("/health").json() == {"status": "ok"}


# stateless: a 2025-era client can call a tool with no initialize first; the answer is one SSE message
def test_stateless_tool_call_over_http(http: TestClient):
    call = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "get_order", "arguments": {"order_id": 1}},
    }
    headers = HEADERS | {
        "host": "testing-wms-mcp:8101",
        "mcp-protocol-version": "2025-11-25",
    }

    response = http.post("/mcp", json=call, headers=headers)

    data = next(
        line for line in response.text.splitlines() if line.startswith("data: ")
    )
    result = json.loads(data.removeprefix("data: "))["result"]
    assert result["isError"] is False
    assert result["content"] == [{"type": "text", "text": '{"id":1}'}]
