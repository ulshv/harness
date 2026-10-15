"""Warehouse logic over the in-memory store. Knows nothing about HTTP."""

from pathlib import Path

import json5

from app.schemas import (
    Allocation,
    LocationStock,
    Move,
    MoveResult,
    Order,
    OrderLine,
    OrderStatus,
    Reservation,
    Shortage,
    SkuStock,
    StockLevel,
    StockRow,
    Store,
    StoredProduct,
)

SEED_PATH = Path(__file__).with_name("seed.jsonc")
CLOSED: frozenset[OrderStatus] = frozenset({"shipped", "cancelled"})


# error messages are written for the agent: through MCP, `str(exc)` is what it reads
class WarehouseError(Exception):
    pass


class NotFound(WarehouseError):
    pass


class Conflict(WarehouseError):
    pass


class Unavailable(WarehouseError):
    pass


def load_seed() -> Store:
    # json5 reads JSON plus // comments and trailing commas
    return Store.model_validate(json5.loads(SEED_PATH.read_text()))


class Warehouse:
    def __init__(self, store: Store) -> None:
        self.store = store

    def reset(self) -> Store:
        self.store = load_seed()
        return self.store

    def products(self, query: str | None) -> list[StoredProduct]:
        q = (query or "").casefold()
        return [
            p
            for p in self.store.products
            if q in p.sku.casefold() or q in p.name.casefold()
        ]

    def locations(self) -> list[LocationStock]:
        return [
            LocationStock(
                location=location,
                stock=[
                    self._level(r) for r in self.store.stock if r.location == location
                ],
            )
            for location in self.store.locations
        ]

    def stock(self, sku: str) -> SkuStock:
        product = self._product(sku)
        if product.broken:
            raise Unavailable(f"The stock service failed for {sku}. Try again later.")
        levels = [self._level(r) for r in self._rows(sku)]
        return SkuStock(
            sku=sku,
            name=product.name,
            on_hand=sum(level.on_hand for level in levels),
            reserved=sum(level.reserved for level in levels),
            available=sum(level.available for level in levels),
            locations=levels,
        )

    def orders(self, status: OrderStatus | None) -> list[Order]:
        return [o for o in self.store.orders if status in (None, o.status)]

    def order(self, order_id: int) -> Order:
        if order := next((o for o in self.store.orders if o.id == order_id), None):
            return order
        raise NotFound(f"Order {order_id} not found.")

    def reserve(self, order_id: int) -> Reservation:
        order = self.order(order_id)
        if order.status in CLOSED:
            raise Conflict(f"Order {order_id} is {order.status}; it can't be reserved.")
        # a fully reserved order is a no-op; partially_reserved tries to fill the rest
        if order.status != "reserved":
            reserved_now = 0
            for line in order.lines:
                reserved_now += self._allocate(line)
            if not reserved_now:
                missing = ", ".join(
                    line.sku for line in order.lines if line.reserved < line.qty
                )
                raise Conflict(
                    f"Nothing reserved for order {order_id}: no available stock of {missing}."
                )
            full = all(line.reserved == line.qty for line in order.lines)
            order.status = "reserved" if full else "partially_reserved"
        shortages = [
            Shortage(sku=line.sku, missing=line.qty - line.reserved)
            for line in order.lines
            if line.reserved < line.qty
        ]
        return Reservation(order=order, shortages=shortages)

    def cancel(self, order_id: int) -> Order:
        order = self.order(order_id)
        if order.status in CLOSED:
            raise Conflict(
                f"Order {order_id} is {order.status}; it can't be cancelled."
            )
        for line in order.lines:
            line.allocations.clear()
        order.status = "cancelled"
        return order

    def move(self, move: Move) -> MoveResult:
        self._product(move.sku)
        self._location(move.from_location)
        self._location(move.to_location)
        source = self._row(move.sku, move.from_location)
        available = self._available(source) if source else 0
        if source is None or move.qty > available:
            raise Conflict(
                f"Only {available} of {move.sku} can move from {move.from_location}; "
                "the rest is reserved for orders or isn't there."
            )
        destination = self._row(move.sku, move.to_location) or self._add_row(
            move.sku, move.to_location
        )
        source.on_hand -= move.qty
        destination.on_hand += move.qty
        result = MoveResult(
            source=self._level(source), destination=self._level(destination)
        )
        # only available stock moves, so an emptied row has no reservations left: drop it
        if not source.on_hand:
            self.store.stock.remove(source)
        return result

    # takes what's available for the line, locations in ascending id order (deterministic for evals);
    # a re-reserve tops up an existing allocation, so /_state has one allocation per location, sorted
    def _allocate(self, line: OrderLine) -> int:
        taken = 0
        for row in sorted(self._rows(line.sku), key=lambda r: r.location):
            if take := min(line.qty - line.reserved, self._available(row)):
                self._add_allocation(line, row.location, take)
                taken += take
        line.allocations.sort(key=lambda a: a.location)
        return taken

    def _add_allocation(self, line: OrderLine, location: str, qty: int) -> None:
        if existing := next(
            (a for a in line.allocations if a.location == location), None
        ):
            existing.qty += qty
        else:
            line.allocations.append(Allocation(location=location, qty=qty))

    # reserved stock isn't stored: it's the sum of order allocations, so it can't disagree with the orders
    def _reserved(self, sku: str, location: str) -> int:
        return sum(
            a.qty
            for order in self.store.orders
            for line in order.lines
            if line.sku == sku
            for a in line.allocations
            if a.location == location
        )

    def _available(self, row: StockRow) -> int:
        return row.on_hand - self._reserved(row.sku, row.location)

    def _level(self, row: StockRow) -> StockLevel:
        reserved = self._reserved(row.sku, row.location)
        return StockLevel(
            sku=row.sku,
            location=row.location,
            on_hand=row.on_hand,
            reserved=reserved,
            available=row.on_hand - reserved,
        )

    def _product(self, sku: str) -> StoredProduct:
        if product := next((p for p in self.store.products if p.sku == sku), None):
            return product
        raise NotFound(f"Unknown SKU {sku}.")

    def _location(self, location: str) -> None:
        if location not in self.store.locations:
            raise NotFound(f"Unknown location {location}.")

    def _rows(self, sku: str) -> list[StockRow]:
        return [r for r in self.store.stock if r.sku == sku]

    def _row(self, sku: str, location: str) -> StockRow | None:
        return next((r for r in self._rows(sku) if r.location == location), None)

    def _add_row(self, sku: str, location: str) -> StockRow:
        row = StockRow(sku=sku, location=location, on_hand=0)
        self.store.stock.append(row)
        return row
