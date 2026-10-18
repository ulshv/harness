from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, NonNegativeInt, PositiveInt

from app.clock import Moment

OrderStatus = Literal["unshipped", "shipped", "cancelled"]


class OrderLine(BaseModel):
    sku: str
    qty: PositiveInt


class Order(BaseModel):
    # Amazon-style id: the marketplace's own, the ERP keeps it as `marketplace_order_id`
    id: str
    buyer: str
    lines: list[OrderLine]
    # the marketplace's deadline: an order not shipped by then counts against the seller
    ship_by: Moment
    status: OrderStatus


class Listing(BaseModel):
    sku: str
    title: str
    price: Decimal
    # what buyers can order; the marketplace doesn't know the warehouse, the seller keeps this in sync
    quantity: NonNegativeInt


# the whole marketplace account: seed.jsonc, the in-memory state and GET /_state share this one shape
class Store(BaseModel):
    orders: list[Order]
    listings: list[Listing]


class QuantityUpdate(BaseModel):
    quantity: NonNegativeInt
