"""A thin client for the testing-erp API that speaks in tool results and tool errors."""

from typing import Any

import httpx2
from mcp.server.mcpserver.exceptions import ToolError

TIMEOUT_SECONDS = 10.0
UNREACHABLE = "The ERP API is unreachable. Try again later."


class Erp:
    # transport is the seam for tests: they pass httpx2.MockTransport instead of the network
    def __init__(
        self, base_url: str, transport: httpx2.AsyncBaseTransport | None = None
    ) -> None:
        self.base_url = base_url
        self.transport = transport

    async def get(self, path: str, params: dict[str, Any] | None = None) -> str:
        return await self._call("GET", path, params=params)

    async def post(self, path: str, json: dict[str, Any] | None = None) -> str:
        return await self._call("POST", path, json=json)

    # returns the API body verbatim: one text block with the exact JSON the API sent
    async def _call(self, method: str, path: str, **kwargs: Any) -> str:
        try:
            # a client per call: no pool to open and close in a lifespan, fine for a test double
            async with httpx2.AsyncClient(
                base_url=self.base_url,
                timeout=TIMEOUT_SECONDS,
                transport=self.transport,
            ) as client:
                response = await client.request(method, path, **kwargs)
        except httpx2.RequestError as exc:  # connection, timeout, a broken response
            raise ToolError(UNREACHABLE) from exc
        if response.is_error:
            # ToolError is the one exception whose message the model reads; any other is sanitized
            raise ToolError(_reason(response))
        return response.text


# FastAPI's `detail` is a string for our 404/409/503 and a list of errors for a 422; a crashed server or a proxy
# sends plain text or nothing
def _reason(response: httpx2.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = None
    match body:
        case {"detail": str(detail)}:
            return detail
        case {"detail": [{"msg": str(msg)}, *_]}:
            return msg
        case _:
            return response.text or f"HTTP {response.status_code}"
