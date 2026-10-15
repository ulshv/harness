import pytest

from app.schemas import Allocation, Order, OrderLine, StockRow, Store, StoredProduct
from app.store import Conflict, Warehouse, load_seed


def test_seed_is_consistent():
    store = load_seed()
    warehouse = Warehouse(store)
    rows = {(r.sku, r.location) for r in store.stock}

    assert {r.location for r in store.stock} <= set(store.locations)
    for order in store.orders:
        for line in order.lines:
            assert line.reserved <= line.qty
            assert all((line.sku, a.location) in rows for a in line.allocations)
    for row in store.stock:
        assert warehouse._available(row) >= 0


def test_reserve_with_nothing_available_conflicts_and_changes_nothing():
    store = Store(
        products=[StoredProduct(sku="X", name="X")],
        locations=["A"],
        stock=[StockRow(sku="X", location="A", on_hand=0)],
        orders=[
            Order(id=1, customer="C", status="new", lines=[OrderLine(sku="X", qty=1)])
        ],
    )
    warehouse = Warehouse(store)

    with pytest.raises(Conflict):
        warehouse.reserve(1)

    assert warehouse.order(1).status == "new"
    assert warehouse.order(1).lines[0].allocations == []


def test_re_reserve_tops_up_allocations_in_location_order():
    store = Store(
        products=[StoredProduct(sku="X", name="X")],
        locations=["A", "B"],
        stock=[
            StockRow(sku="X", location="A", on_hand=1),
            StockRow(sku="X", location="B", on_hand=2),
        ],
        orders=[
            Order(id=1, customer="C", status="new", lines=[OrderLine(sku="X", qty=3)]),
            Order(
                id=2,
                customer="C",
                status="reserved",
                lines=[
                    OrderLine(
                        sku="X",
                        qty=2,
                        allocations=[
                            Allocation(location="A", qty=1),
                            Allocation(location="B", qty=1),
                        ],
                    )
                ],
            ),
        ],
    )
    warehouse = Warehouse(store)

    assert warehouse.reserve(1).order.status == "partially_reserved"
    warehouse.cancel(2)
    order = warehouse.reserve(1).order

    assert order.status == "reserved"
    assert order.lines[0].allocations == [
        Allocation(location="A", qty=1),
        Allocation(location="B", qty=2),
    ]
