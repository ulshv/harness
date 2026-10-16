"""Tools from MCP servers, loaded once at startup."""

import logging
from collections.abc import Mapping

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection
from pydantic import HttpUrl

logger = logging.getLogger(__name__)

# the adapters' defaults wait 30 s to connect and 5 min for a response: a hung server would stall startup and every
# call to it. Applies to loading and to each tool call
MCP_TIMEOUT_SECONDS = 15


async def load_mcp_tools(servers: Mapping[str, HttpUrl]) -> list[BaseTool]:
    # url as str: an HttpUrl object makes httpx raise inside a task group, which would look like a dead server
    connections: dict[str, Connection] = {
        name: {
            "transport": "streamable_http",
            "url": str(url),
            "timeout": MCP_TIMEOUT_SECONDS,
            "sse_read_timeout": MCP_TIMEOUT_SECONDS,
        }
        for name, url in servers.items()
    }
    # tool_name_prefix: `get_order` from server "wms" becomes `wms_get_order`, so servers can't collide
    client = MultiServerMCPClient(connections, tool_name_prefix=True)
    tools: list[BaseTool] = []
    # one server at a time: get_tools() for all of them fails as a whole when one is down
    for name in connections:
        try:
            tools += await client.get_tools(server_name=name)
        except Exception:
            # one dead integration must not take the agent down; its tools come back with a restart
            logger.warning(
                "MCP server %r is unavailable; starting without its tools",
                name,
                exc_info=True,
            )
    return tools
