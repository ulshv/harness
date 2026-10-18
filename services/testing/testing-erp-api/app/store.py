"""ERP logic over the in-memory store. Knows nothing about HTTP."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import json5

from app.schemas import (
    Channel,
    Customer,
    Invoice,
    NewSalesOrder,
    PurchaseOrder,
    PurchaseStatus,
    SalesOrder,
    SalesStatus,
    Store,
)

SEED_PATH = Path(__file__).with_name("seed.jsonc")
SALES_PREFIX = "SO-"


# error messages are written for the agent: through MCP, `str(exc)` is what it reads
class ErpError(Exception):
    pass


class NotFound(ErpError):
    pass


class Conflict(ErpError):
    pass


def load_seed(now: datetime) -> Store:
    # json5 reads JSON plus // comments and trailing commas; `now` turns the seed's offsets into times
    return Store.model_validate(
        json5.loads(SEED_PATH.read_text()), context={"now": now}
    )


class Erp:
    def __init__(self, store: Store) -> None:
        self.store = store

    def customers(self) -> list[Customer]:
        return self.store.customers

    def customer(self, customer_id: str) -> Customer:
        if customer := next(
            (c for c in self.store.customers if c.id == customer_id), None
        ):
            return customer
        raise NotFound(f"Customer {customer_id} not found.")

    def sales_orders(
        self, status: SalesStatus | None, channel: Channel | None
    ) -> list[SalesOrder]:
        return [
            o
            for o in self.store.sales_orders
            if status in (None, o.status) and channel in (None, o.channel)
        ]

    def sales_order(self, order_id: str) -> SalesOrder:
        if order := next(
            (o for o in self.store.sales_orders if o.id == order_id), None
        ):
            return order
        raise NotFound(f"Sales order {order_id} not found.")

    def create(self, new: NewSalesOrder) -> SalesOrder:
        customer = self.customer(new.customer_id)
        if new.marketplace_order_id and (
            taken := next(
                (
                    o
                    for o in self.store.sales_orders
                    if o.marketplace_order_id == new.marketplace_order_id
                ),
                None,
            )
        ):
            raise Conflict(
                f"Marketplace order {new.marketplace_order_id} is already sales order {taken.id}."
            )
        order = SalesOrder(
            id=self._next_id(),
            customer_id=new.customer_id,
            channel=new.channel,
            lines=new.lines,
            marketplace_order_id=new.marketplace_order_id,
            delivery_by=new.delivery_by,
            # due after the customer's payment terms, so a new unpaid order isn't overdue on arrival
            invoice=Invoice(
                due=datetime.now(UTC)
                + timedelta(days=customer.payment_terms_days or 0),
                paid=new.paid,
            ),
        )
        self.store.sales_orders.append(order)
        return order

    def hold(self, order_id: str, reason: str) -> SalesOrder:
        order = self.sales_order(order_id)
        if order.status != "open":
            raise Conflict(
                f"Sales order {order_id} is {order.status}; only open orders can be put on hold."
            )
        order.status = "on_hold"
        order.hold_reason = reason
        return order

    def link_wms_order(self, order_id: str, wms_order_id: str) -> SalesOrder:
        order = self.sales_order(order_id)
        if order.wms_order_id:
            raise Conflict(
                f"Sales order {order_id} is already fulfilled by warehouse order {order.wms_order_id}."
            )
        order.wms_order_id = wms_order_id
        return order

    def purchase_orders(self, status: PurchaseStatus | None) -> list[PurchaseOrder]:
        return [o for o in self.store.purchase_orders if status in (None, o.status)]

    def purchase_order(self, order_id: str) -> PurchaseOrder:
        if order := next(
            (o for o in self.store.purchase_orders if o.id == order_id), None
        ):
            return order
        raise NotFound(f"Purchase order {order_id} not found.")

    def _next_id(self) -> str:
        last = max(
            (int(o.id.removeprefix(SALES_PREFIX)) for o in self.store.sales_orders),
            default=0,
        )
        return f"{SALES_PREFIX}{last + 1}"
