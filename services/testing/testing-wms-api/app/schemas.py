from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    Field,
    PositiveInt,
    StringConstraints,
    computed_field,
    model_validator,
)

from app.clock import Moment

OrderStatus = Literal["new", "partially_reserved", "reserved", "shipped", "cancelled"]
# receiving dock, pallet reserve, pick face, dispatch
Zone = Literal["RECV", "BULK", "PICK", "SHIP"]
# the zone is the id's prefix (`PICK-A-05`), so a location can't drift from its zone
LocationId = Annotated[str, StringConstraints(pattern=r"^(RECV|BULK|PICK|SHIP)-")]


class Product(BaseModel):
    sku: str
    name: str


class StockRow(BaseModel):
    sku: str
    location: str
    on_hand: int
    # set for goods in receiving: how long they've waited to be put away
    received_at: Moment | None = None


class Allocation(BaseModel):
    location: str
    qty: PositiveInt


class OrderLine(BaseModel):
    sku: str
    qty: PositiveInt
    allocations: list[Allocation] = Field(default_factory=list)

    # computed_field: derived on every dump (API, /_state), never read from input, so it can't drift
    @computed_field
    @property
    def reserved(self) -> int:
        return sum(a.qty for a in self.allocations)


class Order(BaseModel):
    id: str
    # the ERP sales order this warehouse order fulfils
    ref: str
    customer: str
    status: OrderStatus
    lines: list[OrderLine]


class NewLine(BaseModel):
    sku: str
    qty: PositiveInt


class NewOrder(BaseModel):
    ref: str = Field(min_length=1)
    customer: str = Field(min_length=1)
    lines: list[NewLine] = Field(min_length=1)


# the whole warehouse: seed.jsonc, the in-memory state and GET /_state share this one shape
class Store(BaseModel):
    products: list[Product]
    locations: list[LocationId]
    stock: list[StockRow]
    orders: list[Order]


class StockLevel(BaseModel):
    sku: str
    location: str
    zone: Zone
    on_hand: int
    reserved: int
    # what orders can still take: 0 outside the pick face and pallet reserve
    available: int
    received_at: datetime | None = None


class SkuStock(BaseModel):
    sku: str
    name: str
    on_hand: int
    reserved: int
    available: int
    locations: list[StockLevel]


class LocationStock(BaseModel):
    location: str
    zone: Zone
    stock: list[StockLevel]


class Shortage(BaseModel):
    sku: str
    missing: int


class Reservation(BaseModel):
    order: Order
    shortages: list[Shortage]


class Move(BaseModel):
    sku: str
    from_location: str
    to_location: str
    qty: PositiveInt

    # raising ValueError here becomes a 422, before the route runs
    @model_validator(mode="after")
    def different_locations(self) -> Self:
        if self.from_location == self.to_location:
            raise ValueError("from_location and to_location must differ")
        return self


class MoveResult(BaseModel):
    source: StockLevel
    destination: StockLevel
