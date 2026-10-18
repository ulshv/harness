from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    PositiveInt,
    computed_field,
    model_validator,
)

from app.clock import Moment

Channel = Literal["b2b", "web", "marketplace"]
CustomerType = Literal["b2b", "consumer", "marketplace"]
SalesStatus = Literal["open", "on_hold", "fulfilled", "cancelled"]
PurchaseStatus = Literal["open", "received"]


class Customer(BaseModel):
    id: str
    name: str
    type: CustomerType
    account_manager: str | None = None
    payment_terms_days: int | None = None


class SalesLine(BaseModel):
    sku: str
    qty: PositiveInt
    unit_price: Decimal


class Invoice(BaseModel):
    due: Moment
    paid: bool

    # computed on every read: "overdue" moves with the clock, so storing it would go stale
    @computed_field
    @property
    def overdue(self) -> bool:
        return not self.paid and self.due < datetime.now(UTC)


class SalesOrder(BaseModel):
    id: str
    customer_id: str
    channel: Channel
    lines: list[SalesLine]
    # the order's id on the marketplace, for orders that came from there
    marketplace_order_id: str | None = None
    # the warehouse order that fulfils this one; None until someone sends it to the warehouse
    wms_order_id: str | None = None
    delivery_by: Moment
    invoice: Invoice
    status: SalesStatus = "open"
    hold_reason: str | None = None


class PurchaseLine(BaseModel):
    sku: str
    qty: PositiveInt


class PurchaseOrder(BaseModel):
    id: str
    supplier: str
    lines: list[PurchaseLine]
    expected_at: Moment
    status: PurchaseStatus


# the whole ERP: seed.jsonc, the in-memory state and GET /_state share this one shape
class Store(BaseModel):
    customers: list[Customer]
    sales_orders: list[SalesOrder]
    purchase_orders: list[PurchaseOrder]


class NewSalesOrder(BaseModel):
    customer_id: str
    channel: Channel
    lines: list[SalesLine] = Field(min_length=1)
    marketplace_order_id: str | None = None
    # aware: every stored time is UTC, and comparing a naive one with them raises
    delivery_by: AwareDatetime
    # marketplace and web shop orders arrive paid; a B2B order is invoiced later
    paid: bool

    # without the marketplace id an import would slip past the duplicate check
    @model_validator(mode="after")
    def marketplace_orders_carry_their_id(self) -> Self:
        if self.channel == "marketplace" and not self.marketplace_order_id:
            raise ValueError("a marketplace order needs its marketplace_order_id")
        return self


class Hold(BaseModel):
    reason: str = Field(min_length=1)


class WmsLink(BaseModel):
    wms_order_id: str = Field(min_length=1)
