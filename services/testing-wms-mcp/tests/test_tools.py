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


async def test_lists_eight_tools_with_typed_arguments(client: Client):
    tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert sorted(tools) == [
        "cancel_order",
        "get_order",
        "get_stock",
        "list_locations",
        "list_orders",
        "move_stock",
        "reserve_order",
        "search_products",
    ]
    reserve = tools["reserve_order"].input_schema
    assert reserve["properties"]["order_id"]["type"] == "integer"
    assert reserve["required"] == ["order_id"]


async def test_returns_the_api_body_verbatim(client: Client, api):
    body = '{"id":1003,"status":"new"}'
    api.handler = lambda request: httpx2.Response(200, text=body)

    result = await client.call_tool("get_order", {"order_id": 1003})

    assert not result.is_error
    assert text(result) == body
    assert str(api.requests[0].url) == "http://testing-wms:8100/orders/1003"


async def test_an_empty_list_stays_visible(client: Client, api):
    api.handler = lambda request: httpx2.Response(200, text="[]")

    result = await client.call_tool("search_products", {"query": "gloves l"})

    assert text(result) == "[]"
    assert api.requests[0].url.params["q"] == "gloves l"


async def test_move_stock_posts_the_body(client: Client, api):
    api.handler = lambda request: httpx2.Response(200, text="{}")
    args = {
        "sku": "GLV-NIT-L",
        "from_location": "A-01-02",
        "to_location": "D-01-01",
        "qty": 80,
    }

    await client.call_tool("move_stock", args)

    assert api.requests[0].method == "POST"
    assert api.requests[0].url.path == "/moves"
    assert api.requests[0].content == (
        b'{"sku":"GLV-NIT-L","from_location":"A-01-02","to_location":"D-01-01","qty":80}'
    )


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (
            httpx2.Response(
                409, json={"detail": "Order 999 is shipped; it can't be reserved."}
            ),
            "Error executing tool reserve_order: Order 999 is shipped; it can't be reserved.",
        ),
        (
            httpx2.Response(
                503, json={"detail": "The stock service failed for SCN-01."}
            ),
            "Error executing tool reserve_order: The stock service failed for SCN-01.",
        ),
        (
            httpx2.Response(500, text="Internal Server Error"),
            "Error executing tool reserve_order: Internal Server Error",
        ),
        (
            httpx2.Response(
                422, json={"detail": [{"msg": "Value error, locations differ"}]}
            ),
            "Error executing tool reserve_order: Value error, locations differ",
        ),
        (httpx2.Response(502), "Error executing tool reserve_order: HTTP 502"),
    ],
)
async def test_api_errors_become_tool_errors(client: Client, api, response, message):
    api.handler = lambda request: response

    result = await client.call_tool("reserve_order", {"order_id": 999})

    assert result.is_error
    assert text(result) == message


async def test_unreachable_api(client: Client, api):
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    api.handler = refuse

    result = await client.call_tool("get_order", {"order_id": 1})

    assert result.is_error
    assert text(result) == (
        "Error executing tool get_order: The warehouse API is unreachable. Try again later."
    )


async def test_invalid_qty_never_reaches_the_api(client: Client, api):
    args = {
        "sku": "GLV-NIT-L",
        "from_location": "A-01-02",
        "to_location": "D-01-01",
        "qty": 0,
    }

    result = await client.call_tool("move_stock", args)

    assert result.is_error
    assert api.requests == []


async def test_sku_stays_one_path_segment(client: Client, api):
    await client.call_tool("get_stock", {"sku": "../_state"})

    assert api.requests[0].url.raw_path == b"/stock/..%2F_state"


async def test_list_orders_without_a_status_sends_no_filter(client: Client, api):
    api.handler = lambda request: httpx2.Response(200, text="[]")

    await client.call_tool("list_orders", {})

    assert str(api.requests[0].url) == "http://testing-wms:8100/orders"
