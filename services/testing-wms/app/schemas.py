from typing import Literal, Self

from pydantic import BaseModel, Field, PositiveInt, computed_field, model_validator

OrderStatus = Literal["new", "partially_reserved", "reserved", "shipped", "cancelled"]


class Product(BaseModel):
    sku: str
    name: str


# test-only `broken` never leaves the API: /products declares response_model=list[Product]
class StoredProduct(Product):
    broken: bool = False


class StockRow(BaseModel):
    sku: str
    location: str
    on_hand: int


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
    id: int
    customer: str
    status: OrderStatus
    lines: list[OrderLine]


# the whole warehouse: seed.jsonc, the in-memory state and GET /_state share this one shape
class Store(BaseModel):
    products: list[StoredProduct]
    locations: list[str]
    stock: list[StockRow]
    orders: list[Order]


class StockLevel(BaseModel):
    sku: str
    location: str
    on_hand: int
    reserved: int
    available: int


class SkuStock(BaseModel):
    sku: str
    name: str
    on_hand: int
    reserved: int
    available: int
    locations: list[StockLevel]


class LocationStock(BaseModel):
    location: str
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
