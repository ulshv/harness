"""Marketplace logic over the in-memory store. Knows nothing about HTTP."""

from datetime import datetime
from pathlib import Path

import json5

from app.schemas import Listing, Order, OrderStatus, Store

SEED_PATH = Path(__file__).with_name("seed.jsonc")


# error messages are written for the agent: through MCP, `str(exc)` is what it reads
class MarketplaceError(Exception):
    pass


class NotFound(MarketplaceError):
    pass


def load_seed(now: datetime) -> Store:
    # json5 reads JSON plus // comments and trailing commas; `now` turns the seed's offsets into times
    return Store.model_validate(
        json5.loads(SEED_PATH.read_text()), context={"now": now}
    )


class Marketplace:
    def __init__(self, store: Store) -> None:
        self.store = store

    def orders(self, status: OrderStatus | None) -> list[Order]:
        return [o for o in self.store.orders if status in (None, o.status)]

    def order(self, order_id: str) -> Order:
        if order := next((o for o in self.store.orders if o.id == order_id), None):
            return order
        raise NotFound(f"Marketplace order {order_id} not found.")

    def listings(self) -> list[Listing]:
        return self.store.listings

    def listing(self, sku: str) -> Listing:
        if listing := next((x for x in self.store.listings if x.sku == sku), None):
            return listing
        raise NotFound(f"No listing for {sku}.")

    def set_quantity(self, sku: str, quantity: int) -> Listing:
        listing = self.listing(sku)
        listing.quantity = quantity
        return listing
