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


async def test_lists_five_tools(client: Client):
    tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert sorted(tools) == [
        "get_listing",
        "get_order",
        "list_listings",
        "list_orders",
        "set_listing_quantity",
    ]
    quantity = tools["set_listing_quantity"].input_schema["properties"]["quantity"]
    assert quantity["minimum"] == 0


async def test_returns_the_api_body_verbatim(client: Client, api):
    body = '{"id":"114-3349201","status":"unshipped"}'
    api.handler = lambda request: httpx2.Response(200, text=body)

    result = await client.call_tool("get_order", {"order_id": "114-3349201"})

    assert text(result) == body
    assert (
        str(api.requests[0].url)
        == "http://testing-marketplace-api:8120/orders/114-3349201"
    )


async def test_set_listing_quantity_puts_the_body(client: Client, api):
    await client.call_tool("set_listing_quantity", {"sku": "KET-GOOSE", "quantity": 0})

    assert api.requests[0].method == "PUT"
    assert api.requests[0].url.path == "/listings/KET-GOOSE/quantity"
    assert api.requests[0].content == b'{"quantity":0}'


async def test_negative_quantity_never_reaches_the_api(client: Client, api):
    result = await client.call_tool(
        "set_listing_quantity", {"sku": "KET-GOOSE", "quantity": -1}
    )

    assert result.is_error
    assert api.requests == []


async def test_api_errors_become_tool_errors(client: Client, api):
    api.handler = lambda request: httpx2.Response(
        404, json={"detail": "No listing for NOPE."}
    )

    result = await client.call_tool("get_listing", {"sku": "NOPE"})

    assert result.is_error
    assert text(result) == "Error executing tool get_listing: No listing for NOPE."


async def test_ids_stay_one_path_segment(client: Client, api):
    await client.call_tool("get_listing", {"sku": "../_state"})

    assert api.requests[0].url.raw_path == b"/listings/..%2F_state"
