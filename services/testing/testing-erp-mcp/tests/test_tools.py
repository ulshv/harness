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


async def test_lists_nine_tools(client: Client):
    tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert sorted(tools) == [
        "create_sales_order",
        "get_customer",
        "get_purchase_order",
        "get_sales_order",
        "hold_sales_order",
        "link_wms_order",
        "list_customers",
        "list_purchase_orders",
        "list_sales_orders",
    ]


async def test_returns_the_api_body_verbatim(client: Client, api):
    body = '{"id":"SO-1041","status":"open"}'
    api.handler = lambda request: httpx2.Response(200, text=body)

    result = await client.call_tool("get_sales_order", {"order_id": "SO-1041"})

    assert text(result) == body
    assert (
        str(api.requests[0].url) == "http://testing-erp-api:8110/sales-orders/SO-1041"
    )


async def test_list_sales_orders_sends_only_the_given_filters(client: Client, api):
    api.handler = lambda request: httpx2.Response(200, text="[]")

    await client.call_tool("list_sales_orders", {"channel": "marketplace"})
    await client.call_tool("list_sales_orders", {})

    assert str(api.requests[0].url) == (
        "http://testing-erp-api:8110/sales-orders?channel=marketplace"
    )
    assert str(api.requests[1].url) == "http://testing-erp-api:8110/sales-orders"


async def test_hold_posts_the_reason(client: Client, api):
    await client.call_tool(
        "hold_sales_order", {"order_id": "SO-1041", "reason": "Payment overdue"}
    )

    assert api.requests[0].method == "POST"
    assert api.requests[0].url.path == "/sales-orders/SO-1041/hold"
    assert api.requests[0].content == b'{"reason":"Payment overdue"}'


async def test_create_sales_order_posts_the_import(client: Client, api):
    args = {
        "customer_id": "CUST-007",
        "channel": "marketplace",
        "lines": [{"sku": "COF-ESP-1KG", "qty": 3, "unit_price": "24.00"}],
        "delivery_by": "2026-10-21T12:00:00Z",
        "paid": True,
        "marketplace_order_id": "114-7781302",
    }

    await client.call_tool("create_sales_order", args)

    assert api.requests[0].url.path == "/sales-orders"
    assert api.requests[0].content == (
        b'{"customer_id":"CUST-007","channel":"marketplace",'
        b'"lines":[{"sku":"COF-ESP-1KG","qty":3,"unit_price":"24.00"}],'
        b'"delivery_by":"2026-10-21T12:00:00+00:00","paid":true,"marketplace_order_id":"114-7781302"}'
    )


async def test_link_wms_order_posts_the_id(client: Client, api):
    await client.call_tool(
        "link_wms_order", {"order_id": "SO-1053", "wms_order_id": "OUT-5053"}
    )

    assert api.requests[0].url.path == "/sales-orders/SO-1053/wms-order"
    assert api.requests[0].content == b'{"wms_order_id":"OUT-5053"}'


async def test_api_conflict_becomes_a_tool_error(client: Client, api):
    detail = "Sales order SO-1041 is on_hold; only open orders can be put on hold."
    api.handler = lambda request: httpx2.Response(409, json={"detail": detail})

    result = await client.call_tool(
        "hold_sales_order", {"order_id": "SO-1041", "reason": "Payment overdue"}
    )

    assert result.is_error
    assert text(result) == f"Error executing tool hold_sales_order: {detail}"


async def test_unreachable_api(client: Client, api):
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    api.handler = refuse

    result = await client.call_tool("list_customers", {})

    assert text(result) == (
        "Error executing tool list_customers: The ERP API is unreachable. Try again later."
    )


async def test_ids_stay_one_path_segment(client: Client, api):
    await client.call_tool("get_sales_order", {"order_id": "SO-1041/../../_state"})

    assert api.requests[0].url.raw_path == b"/sales-orders/SO-1041%2F..%2F..%2F_state"
