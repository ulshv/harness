"""The MCP server: one tool per ERP operation, described for a model.

Descriptions state facts only. Policies (what to put on hold, when) belong to the agent's prompt.
"""

from decimal import Decimal
from typing import Literal
from urllib.parse import quote

from mcp.server import MCPServer
from pydantic import AwareDatetime, BaseModel, PositiveInt

from app.erp import Erp

Channel = Literal["b2b", "web", "marketplace"]
SalesStatus = Literal["open", "on_hold", "fulfilled", "cancelled"]
PurchaseStatus = Literal["open", "received"]


class SalesLineInput(BaseModel):
    sku: str
    qty: PositiveInt
    unit_price: Decimal


# tools close over `erp`, so tests build a server around a mocked API instead of patching globals
def build_server(erp: Erp) -> MCPServer:
    # the docstring becomes the tool description and the type hints its input schema: both are what the model sees
    server = MCPServer("testing-erp")

    @server.tool()
    async def list_customers() -> str:
        """List customers: id, name, type (b2b, consumer, marketplace), account manager, payment terms in days."""
        return await erp.get("/customers")

    @server.tool()
    async def get_customer(customer_id: str) -> str:
        """One customer by id (`CUST-001`)."""
        return await erp.get(f"/customers/{quote(customer_id, safe='')}")

    @server.tool()
    async def list_sales_orders(
        status: SalesStatus | None = None, channel: Channel | None = None
    ) -> str:
        """List sales orders, optionally by status and sales channel. Each has its customer id, lines with prices,
        `marketplace_order_id` (orders from the marketplace), `wms_order_id` (the warehouse order fulfilling it,
        null if none), `delivery_by`, and the invoice: `due`, `paid` and `overdue` (unpaid past its due date)."""
        params = {
            key: value
            for key, value in (("status", status), ("channel", channel))
            if value
        }
        return await erp.get("/sales-orders", params=params or None)

    @server.tool()
    async def get_sales_order(order_id: str) -> str:
        """One sales order by id (`SO-1041`)."""
        return await erp.get(f"/sales-orders/{quote(order_id, safe='')}")

    @server.tool()
    async def create_sales_order(
        customer_id: str,
        channel: Channel,
        lines: list[SalesLineInput],
        delivery_by: AwareDatetime,
        paid: bool,
        marketplace_order_id: str | None = None,
    ) -> str:
        """Create an open sales order, e.g. to import a marketplace order (channel `marketplace`, its
        `marketplace_order_id`, required for that channel). `delivery_by` needs a timezone. The invoice is due
        after the customer's payment terms, paid or not as given. Fails if a sales order for that marketplace
        order already exists, or the customer doesn't."""
        body = {
            "customer_id": customer_id,
            "channel": channel,
            "lines": [line.model_dump(mode="json") for line in lines],
            "delivery_by": delivery_by.isoformat(),
            "paid": paid,
            "marketplace_order_id": marketplace_order_id,
        }
        return await erp.post("/sales-orders", json=body)

    @server.tool()
    async def hold_sales_order(order_id: str, reason: str) -> str:
        """Put an open sales order on hold with a reason. Only open orders can be put on hold."""
        return await erp.post(
            f"/sales-orders/{quote(order_id, safe='')}/hold", json={"reason": reason}
        )

    @server.tool()
    async def link_wms_order(order_id: str, wms_order_id: str) -> str:
        """Record which warehouse order (`OUT-5053`) fulfils a sales order. Fails if one is already linked."""
        return await erp.post(
            f"/sales-orders/{quote(order_id, safe='')}/wms-order",
            json={"wms_order_id": wms_order_id},
        )

    @server.tool()
    async def list_purchase_orders(status: PurchaseStatus | None = None) -> str:
        """List purchase orders from suppliers, optionally by status: supplier, lines, `expected_at`, status."""
        params = {"status": status} if status else None
        return await erp.get("/purchase-orders", params=params)

    @server.tool()
    async def get_purchase_order(order_id: str) -> str:
        """One purchase order by id (`PO-2207`)."""
        return await erp.get(f"/purchase-orders/{quote(order_id, safe='')}")

    return server
