"""Warehouse logic over the in-memory store. Knows nothing about HTTP."""

from datetime import datetime
from pathlib import Path
from typing import cast

import json5

from app.schemas import (
    Allocation,
    LocationStock,
    Move,
    MoveResult,
    NewOrder,
    Order,
    OrderLine,
    OrderStatus,
    Product,
    Reservation,
    Shortage,
    SkuStock,
    StockLevel,
    StockRow,
    Store,
    Zone,
)

SEED_PATH = Path(__file__).with_name("seed.jsonc")
CLOSED: frozenset[OrderStatus] = frozenset({"shipped", "cancelled"})
ORDER_PREFIX = "OUT-"
# zones orders can take stock from, in the order reserve takes it: the pick face first, then pallets.
# Receiving isn't put away yet, dispatch is already leaving
RESERVABLE: dict[Zone, int] = {"PICK": 0, "BULK": 1}


# error messages are written for the agent: through MCP, `str(exc)` is what it reads
class WarehouseError(Exception):
    pass


class NotFound(WarehouseError):
    pass


class Conflict(WarehouseError):
    pass


def load_seed(now: datetime) -> Store:
    # json5 reads JSON plus // comments and trailing commas; `now` turns the seed's offsets into times
    return Store.model_validate(
        json5.loads(SEED_PATH.read_text()), context={"now": now}
    )


def zone_of(location: str) -> Zone:
    # LocationId validated the prefix, so the cast only tells the checker what's already true
    return cast(Zone, location.partition("-")[0])


class Warehouse:
    def __init__(self, store: Store) -> None:
        self.store = store

    def products(self, query: str | None) -> list[Product]:
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
                zone=zone_of(location),
                stock=[
                    self._level(r) for r in self.store.stock if r.location == location
                ],
            )
            for location in self.store.locations
        ]

    def stock(self, sku: str) -> SkuStock:
        product = self._product(sku)
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

    def order(self, order_id: str) -> Order:
        if order := next((o for o in self.store.orders if o.id == order_id), None):
            return order
        raise NotFound(f"Order {order_id} not found.")

    def create(self, new: NewOrder) -> Order:
        for line in new.lines:
            self._product(line.sku)
        # a cancelled order may be replaced; any other one already fulfils this ERP order
        if taken := next(
            (
                o
                for o in self.store.orders
                if o.ref == new.ref and o.status != "cancelled"
            ),
            None,
        ):
            raise Conflict(f"Order {taken.id} already fulfils {new.ref}.")
        order = Order(
            id=self._next_id(),
            ref=new.ref,
            customer=new.customer,
            status="new",
            lines=[OrderLine(sku=line.sku, qty=line.qty) for line in new.lines],
        )
        self.store.orders.append(order)
        return order

    def reserve(self, order_id: str) -> Reservation:
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

    # gives the stock back but keeps the order: it can be reserved again later
    def release(self, order_id: str) -> Order:
        order = self.order(order_id)
        if order.status in CLOSED:
            raise Conflict(f"Order {order_id} is {order.status}; it can't be released.")
        for line in order.lines:
            line.allocations.clear()
        order.status = "new"
        return order

    def cancel(self, order_id: str) -> Order:
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
        # receiving only takes deliveries: a move into it would have no `received_at` to age by
        if zone_of(move.to_location) == "RECV":
            raise Conflict(
                f"{move.to_location} is in receiving, which only takes deliveries; "
                "move stock to a PICK or BULK location."
            )
        source = self._row(move.sku, move.from_location)
        free = self._free(source) if source else 0
        if source is None or move.qty > free:
            raise Conflict(
                f"Only {free} of {move.sku} can move from {move.from_location}; "
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
        # only unreserved stock moves, so an emptied row has no reservations left: drop it
        if not source.on_hand:
            self.store.stock.remove(source)
        return result

    # takes what's available for the line: the pick face, then pallets, ascending location id within a zone
    # (deterministic); a re-reserve tops up an existing allocation, so /_state has one allocation per location
    def _allocate(self, line: OrderLine) -> int:
        taken = 0
        reservable = [
            r for r in self._rows(line.sku) if zone_of(r.location) in RESERVABLE
        ]
        for row in sorted(
            reservable, key=lambda r: (RESERVABLE[zone_of(r.location)], r.location)
        ):
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

    # what can move: on hand minus reserved, in any zone (moving out of receiving is the put-away)
    def _free(self, row: StockRow) -> int:
        return row.on_hand - self._reserved(row.sku, row.location)

    # what orders can still take: free stock, but only where reserve looks
    def _available(self, row: StockRow) -> int:
        return self._free(row) if zone_of(row.location) in RESERVABLE else 0

    def _level(self, row: StockRow) -> StockLevel:
        return StockLevel(
            sku=row.sku,
            location=row.location,
            zone=zone_of(row.location),
            on_hand=row.on_hand,
            reserved=self._reserved(row.sku, row.location),
            available=self._available(row),
            received_at=row.received_at,
        )

    def _next_id(self) -> str:
        last = max(
            (int(o.id.removeprefix(ORDER_PREFIX)) for o in self.store.orders), default=0
        )
        return f"{ORDER_PREFIX}{last + 1}"

    def _product(self, sku: str) -> Product:
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
