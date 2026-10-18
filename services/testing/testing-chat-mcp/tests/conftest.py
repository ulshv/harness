from collections.abc import AsyncIterator, Callable

import httpx2
import pytest
from mcp import Client

from app.chat import Chat
from app.server import build_server

type Handler = Callable[[httpx2.Request], httpx2.Response]


# a fake testing-chat-api: a test sets `handler` to answer; every request the tools make is recorded
class FakeApi:
    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.handler: Handler = lambda request: httpx2.Response(200, text="{}")

    def transport(self) -> httpx2.MockTransport:
        def handle(request: httpx2.Request) -> httpx2.Response:
            self.requests.append(request)
            return self.handler(request)

        return httpx2.MockTransport(handle)


# Client(server) runs on anyio; its pytest plugin ships with anyio, so no pytest-asyncio
@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def api() -> FakeApi:
    return FakeApi()


# in memory: Client talks to the server object directly, no transport, no port
@pytest.fixture
async def client(api: FakeApi) -> AsyncIterator[Client]:
    server = build_server(
        Chat("http://testing-chat-api:8130", transport=api.transport())
    )
    async with Client(server) as c:
        yield c
