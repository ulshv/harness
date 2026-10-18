import httpx2
import pytest
from mcp import Client
from mcp.types import TextContent

pytestmark = pytest.mark.anyio


def text(result) -> str:
    assert len(result.content) == 1
    block = result.content[0]
    assert isinstance(block, TextContent)
    return block.text


async def test_lists_four_tools(client: Client):
    tools = {tool.name for tool in (await client.list_tools()).tools}

    assert sorted(tools) == [
        "list_channels",
        "list_users",
        "post_message",
        "read_messages",
    ]


async def test_read_messages_encodes_the_channel(client: Client, api):
    api.handler = lambda request: httpx2.Response(200, text="[]")

    result = await client.call_tool("read_messages", {"to": "#sales"})

    assert text(result) == "[]"
    assert api.requests[0].url.raw_path == b"/messages?to=%23sales"


async def test_post_message_posts_the_body(client: Client, api):
    await client.call_tool(
        "post_message", {"to": "@maria", "text": "SO-1041 is on hold."}
    )

    assert api.requests[0].method == "POST"
    assert api.requests[0].url.path == "/messages"
    assert api.requests[0].content == b'{"to":"@maria","text":"SO-1041 is on hold."}'


async def test_empty_text_never_reaches_the_api(client: Client, api):
    result = await client.call_tool("post_message", {"to": "#ops", "text": ""})

    assert result.is_error
    assert api.requests == []


async def test_unknown_target_becomes_a_tool_error(client: Client, api):
    detail = "No channel or user @bob. Channels start with #, people with @."
    api.handler = lambda request: httpx2.Response(404, json={"detail": detail})

    result = await client.call_tool("post_message", {"to": "@bob", "text": "Hi"})

    assert result.is_error
    assert text(result) == f"Error executing tool post_message: {detail}"
