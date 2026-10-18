"""The MCP server: one tool per marketplace operation, described for a model.

Descriptions state facts only. Policies (what a listing may offer) belong to the agent's prompt.
"""

from typing import Literal
from urllib.parse import quote

from mcp.server import MCPServer
from pydantic import NonNegativeInt

from app.marketplace import Marketplace

OrderStatus = Literal["unshipped", "shipped", "cancelled"]


# tools close over `marketplace`, so tests build a server around a mocked API instead of patching globals
def build_server(marketplace: Marketplace) -> MCPServer:
    # the docstring becomes the tool description and the type hints its input schema: both are what the model sees
    server = MCPServer("testing-marketplace")

    @server.tool()
    async def list_orders(status: OrderStatus | None = None) -> str:
        """List the seller's marketplace orders, optionally by status: id (`114-3349201`), buyer, lines,
        `ship_by` (the marketplace's shipping deadline) and status."""
        params = {"status": status} if status else None
        return await marketplace.get("/orders", params=params)

    @server.tool()
    async def get_order(order_id: str) -> str:
        """One marketplace order by id."""
        return await marketplace.get(f"/orders/{quote(order_id, safe='')}")

    @server.tool()
    async def list_listings() -> str:
        """List the seller's listings: SKU, title, price and `quantity`, how many buyers can order. The
        marketplace doesn't see the warehouse: the quantity changes only when the seller sets it."""
        return await marketplace.get("/listings")

    @server.tool()
    async def get_listing(sku: str) -> str:
        """One listing by SKU."""
        return await marketplace.get(f"/listings/{quote(sku, safe='')}")

    @server.tool()
    async def set_listing_quantity(sku: str, quantity: NonNegativeInt) -> str:
        """Set how many units of a SKU buyers can order on the marketplace; 0 stops new orders."""
        return await marketplace.put(
            f"/listings/{quote(sku, safe='')}/quantity", json={"quantity": quantity}
        )

    return server
