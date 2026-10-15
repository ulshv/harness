"""The MCP server: one tool per warehouse operation, described for a model.

Descriptions state facts only. Policies ("don't reserve partially without asking") belong to the agent's prompt,
so evals measure the agent, not this text.
"""

from typing import Literal
from urllib.parse import quote

from mcp.server import MCPServer
from pydantic import PositiveInt

from app.wms import Wms

OrderStatus = Literal["new", "partially_reserved", "reserved", "shipped", "cancelled"]


# tools close over `wms`, so tests build a server around a mocked API instead of patching globals
def build_server(wms: Wms) -> MCPServer:
    # the docstring becomes the tool description and the type hints its input schema: both are what the model sees
    server = MCPServer("testing-wms")

    @server.tool()
    async def search_products(query: str) -> str:
        """Find products whose SKU or name contains `query` (case-insensitive substring match).
        Returns a JSON list of {sku, name}."""
        return await wms.get("/products", params={"q": query})

    @server.tool()
    async def list_locations() -> str:
        """List every storage location with the stock it holds; empty locations have an empty list."""
        return await wms.get("/locations")

    @server.tool()
    async def get_stock(sku: str) -> str:
        """Stock of one SKU: on hand, reserved for orders and available (on hand minus reserved),
        in total and per location."""
        # escaped: a model-made "../_state" must stay one path segment, not reach another endpoint
        return await wms.get(f"/stock/{quote(sku, safe='')}")

    @server.tool()
    async def list_orders(status: OrderStatus | None = None) -> str:
        """List orders, optionally only those with the given status."""
        params = {"status": status} if status else None
        return await wms.get("/orders", params=params)

    @server.tool()
    async def get_order(order_id: int) -> str:
        """One order: status, customer, lines, and for each line how much is reserved and in which locations."""
        return await wms.get(f"/orders/{order_id}")

    @server.tool()
    async def reserve_order(order_id: int) -> str:
        """Reserve available stock for an order's lines, taking locations in id order.
        If stock is short, reserves what it can: the order becomes partially_reserved and `shortages` lists
        what is missing. If nothing is available, it fails and nothing changes. A reserved order is a no-op.
        Shipped and cancelled orders can't be reserved."""
        return await wms.post(f"/orders/{order_id}/reserve")

    @server.tool()
    async def cancel_order(order_id: int) -> str:
        """Cancel an order and release its reservations. Shipped and cancelled orders can't be cancelled."""
        return await wms.post(f"/orders/{order_id}/cancel")

    @server.tool()
    async def move_stock(
        sku: str, from_location: str, to_location: str, qty: PositiveInt
    ) -> str:
        """Move `qty` units of a SKU between two different locations. Only available stock moves: the reserved
        part stays. Returns this SKU's stock at both locations after the move."""
        body = {
            "sku": sku,
            "from_location": from_location,
            "to_location": to_location,
            "qty": qty,
        }
        return await wms.post("/moves", json=body)

    return server
