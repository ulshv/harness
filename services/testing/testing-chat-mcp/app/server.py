"""The MCP server: one tool per team chat operation, described for a model.

Descriptions state facts only. Policies (who to tell what) belong to the agent's prompt.
"""

from typing import Annotated

from mcp.server import MCPServer
from pydantic import Field

from app.chat import Chat


# tools close over `chat`, so tests build a server around a mocked API instead of patching globals
def build_server(chat: Chat) -> MCPServer:
    # the docstring becomes the tool description and the type hints its input schema: both are what the model sees
    server = MCPServer("testing-chat")

    @server.tool()
    async def list_channels() -> str:
        """List the team's channels (`#sales`) with their topics."""
        return await chat.get("/channels")

    @server.tool()
    async def list_users() -> str:
        """List the team: handle (`@maria`), name and role."""
        return await chat.get("/users")

    @server.tool()
    async def read_messages(to: str) -> str:
        """Messages in a channel (`#warehouse`) or the direct messages to a person (`@tom`), oldest first."""
        return await chat.get("/messages", params={"to": to})

    @server.tool()
    async def post_message(to: str, text: Annotated[str, Field(min_length=1)]) -> str:
        """Post a message to a channel (`#sales`) or directly to a person (`@maria`), as ops-assistant."""
        return await chat.post("/messages", json={"to": to, "text": text})

    return server
