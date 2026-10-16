import asyncio
import logging

from langchain_core.tools import BaseTool, tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import HttpUrl

from app.agent.mcp import load_mcp_tools


@tool
def wms_get_order() -> str:
    """A tool as server "wms" would expose it, already prefixed."""
    return "{}"


async def fake_get_tools(
    self: MultiServerMCPClient, *, server_name: str | None = None
) -> list[BaseTool]:
    # what load_mcp_tools must hand the adapters: the URL as a str (httpx rejects an HttpUrl), short timeouts,
    # prefixed names
    assert server_name is not None
    assert self.connections[server_name] == {
        "transport": "streamable_http",
        "url": f"http://{server_name}:1/mcp",
        "timeout": 15,
        "sse_read_timeout": 15,
    }
    assert self.tool_name_prefix is True
    if server_name == "down":
        # what a dead Streamable HTTP server raises out of anyio's task group
        raise ExceptionGroup("unhandled errors", [ConnectionError("refused")])
    return [wms_get_order]


def test_a_dead_server_is_skipped_with_a_warning(monkeypatch, caplog):
    monkeypatch.setattr(MultiServerMCPClient, "get_tools", fake_get_tools)
    servers = {"wms": HttpUrl("http://wms:1/mcp"), "down": HttpUrl("http://down:1/mcp")}

    with caplog.at_level(logging.WARNING):
        tools = asyncio.run(load_mcp_tools(servers))

    assert [t.name for t in tools] == ["wms_get_order"]
    assert caplog.messages == [
        "MCP server 'down' is unavailable; starting without its tools"
    ]


def test_no_servers_no_tools():
    assert asyncio.run(load_mcp_tools({})) == []
