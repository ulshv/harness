"""The MCP server: one tool per warehouse operation, described for a model.

Descriptions state facts only. Policies (what to reserve first, when to put stock away) belong to the agent's
prompt, so any agent can use these tools under its own rules.
"""

from typing import Literal
from urllib.parse import quote

from mcp.server import MCPServer
from pydantic import BaseModel, PositiveInt

from app.wms import Wms

OrderStatus = Literal["new", "partially_reserved", "reserved", "shipped", "cancelled"]


class OrderLineInput(BaseModel):
    sku: str
    qty: PositiveInt


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
        """List every storage location with its zone and the stock it holds; empty locations have an empty
        list. Zones: RECV (receiving dock), BULK (pallet reserve), PICK (pick face), SHIP (dispatch)."""
        return await wms.get("/locations")

    @server.tool()
    async def get_stock(sku: str) -> str:
        """Stock of one SKU, in total and per location: on hand, reserved for orders, and available for new
        reservations. Only PICK and BULK stock is available; stock in RECV shows `received_at`, when it arrived."""
        # escaped: a model-made "../_state" must stay one path segment, not reach another endpoint
        return await wms.get(f"/stock/{quote(sku, safe='')}")

    @server.tool()
    async def list_orders(status: OrderStatus | None = None) -> str:
        """List orders, optionally only those with the given status."""
        params = {"status": status} if status else None
        return await wms.get("/orders", params=params)

    @server.tool()
    async def get_order(order_id: str) -> str:
        """One warehouse order (`OUT-5041`): the ERP sales order it fulfils (`ref`), status, customer, lines,
        and for each line how much is reserved and in which locations."""
        return await wms.get(f"/orders/{quote(order_id, safe='')}")

    @server.tool()
    async def create_order(ref: str, customer: str, lines: list[OrderLineInput]) -> str:
        """Create a warehouse order for an ERP sales order (`ref`, e.g. `SO-1053`). It starts as `new` with
        nothing reserved. Fails if an order that isn't cancelled already fulfils that `ref`."""
        body = {
            "ref": ref,
            "customer": customer,
            "lines": [line.model_dump() for line in lines],
        }
        return await wms.post("/orders", json=body)

    @server.tool()
    async def reserve_order(order_id: str) -> str:
        """Reserve available stock for an order's lines: the pick face first, then pallets, in location order.
        If stock is short, reserves what it can: the order becomes partially_reserved and `shortages` lists
        what is missing. If nothing is available, it fails and nothing changes. A reserved order is a no-op.
        Shipped and cancelled orders can't be reserved."""
        return await wms.post(f"/orders/{quote(order_id, safe='')}/reserve")

    @server.tool()
    async def release_order(order_id: str) -> str:
        """Give an order's reserved stock back and set it to `new`; the order stays and can be reserved again.
        Shipped and cancelled orders can't be released."""
        return await wms.post(f"/orders/{quote(order_id, safe='')}/release")

    @server.tool()
    async def cancel_order(order_id: str) -> str:
        """Cancel an order and release its reservations. Shipped and cancelled orders can't be cancelled."""
        return await wms.post(f"/orders/{quote(order_id, safe='')}/cancel")

    @server.tool()
    async def move_stock(
        sku: str, from_location: str, to_location: str, qty: PositiveInt
    ) -> str:
        """Move `qty` units of a SKU between two different locations. Moving out of RECV is the put-away;
        nothing can move into RECV. Only unreserved stock moves. Returns this SKU's stock at both locations
        after the move."""
        body = {
            "sku": sku,
            "from_location": from_location,
            "to_location": to_location,
            "qty": qty,
        }
        return await wms.post("/moves", json=body)

    return server
