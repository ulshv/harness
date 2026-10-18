import pytest

from app.schemas import (
    Allocation,
    Move,
    NewLine,
    NewOrder,
    Order,
    OrderLine,
    OrderStatus,
    Product,
    StockRow,
    Store,
)
from app.store import Conflict, NotFound, Warehouse, load_seed
from tests.conftest import NOW


def small_store(stock: list[StockRow], orders: list[Order]) -> Warehouse:
    locations = sorted({row.location for row in stock})
    return Warehouse(
        Store(
            products=[Product(sku="X", name="X")],
            locations=locations,
            stock=stock,
            orders=orders,
        )
    )


def order(id: str, qty: int, status: OrderStatus = "new", allocations=()) -> Order:
    line = OrderLine(sku="X", qty=qty, allocations=list(allocations))
    return Order(id=id, ref=f"SO-{id}", customer="C", status=status, lines=[line])


def test_seed_is_consistent():
    store = load_seed(NOW)
    warehouse = Warehouse(store)
    rows = {(r.sku, r.location) for r in store.stock}

    assert {r.location for r in store.stock} <= set(store.locations)
    for o in store.orders:
        for line in o.lines:
            assert line.reserved <= line.qty
            for a in line.allocations:
                assert (line.sku, a.location) in rows
                assert a.location.startswith(("PICK-", "BULK-"))
    for row in store.stock:
        assert warehouse._free(row) >= 0


def test_seed_statuses_agree_with_allocations():
    for o in load_seed(NOW).orders:
        reserved = [line.reserved for line in o.lines]
        full = all(line.reserved == line.qty for line in o.lines)
        match o.status:
            case "shipped" | "cancelled" | "new":
                assert not any(reserved), o.id
            case "reserved":
                assert full, o.id
            case "partially_reserved":
                assert any(reserved) and not full, o.id


def test_seed_stuck_states_are_the_demo_ones():
    store = load_seed(NOW)
    warehouse = Warehouse(store)
    short = {
        o.id
        for o in store.orders
        if o.status not in ("shipped", "cancelled")
        and any(line.reserved < line.qty for line in o.lines)
    }
    receiving = [
        (r.sku, r.location) for r in store.stock if r.location.startswith("RECV-")
    ]

    assert short == {"OUT-5045", "OUT-5048", "OUT-5052"}
    assert receiving == [("FRT-ELEC", "RECV-01")]
    assert {
        o.id: (o.ref, o.status)
        for o in store.orders
        if o.id in {"OUT-5041", "OUT-5045", "OUT-5048", "OUT-5050", "OUT-5052"}
    } == {
        "OUT-5041": ("SO-1041", "reserved"),
        "OUT-5045": ("SO-1045", "partially_reserved"),
        "OUT-5048": ("SO-1048", "partially_reserved"),
        "OUT-5050": ("SO-1050", "reserved"),
        "OUT-5052": ("SO-1052", "new"),
    }
    assert [
        (lv.location, lv.on_hand, lv.reserved, lv.available)
        for lv in warehouse.stock("GRN-HOME").locations
    ] == [("PICK-A-05", 10, 10, 0)]
    assert [
        (lv.location, lv.on_hand, lv.reserved, lv.available)
        for lv in warehouse.stock("KET-GOOSE").locations
    ] == [("PICK-B-03", 2, 2, 0)]
    assert [
        (lv.location, lv.on_hand, lv.reserved, lv.available)
        for lv in warehouse.stock("COF-HOU-1KG").locations
    ] == [("PICK-A-02", 15, 15, 0)]


def test_reserve_takes_the_pick_face_before_pallets_and_skips_receiving():
    warehouse = small_store(
        stock=[
            StockRow(sku="X", location="BULK-A-01", on_hand=5),
            StockRow(sku="X", location="PICK-B-01", on_hand=1),
            StockRow(sku="X", location="PICK-A-01", on_hand=1),
            StockRow(sku="X", location="RECV-01", on_hand=9),
        ],
        orders=[order("OUT-1", qty=4)],
    )

    reserved = warehouse.reserve("OUT-1").order

    assert reserved.status == "reserved"
    assert reserved.lines[0].allocations == [
        Allocation(location="BULK-A-01", qty=2),
        Allocation(location="PICK-A-01", qty=1),
        Allocation(location="PICK-B-01", qty=1),
    ]


def test_reserve_with_nothing_available_conflicts_and_changes_nothing():
    warehouse = small_store(
        stock=[StockRow(sku="X", location="RECV-01", on_hand=5)],
        orders=[order("OUT-1", qty=1)],
    )

    with pytest.raises(Conflict):
        warehouse.reserve("OUT-1")

    assert warehouse.order("OUT-1").status == "new"
    assert warehouse.order("OUT-1").lines[0].allocations == []


def test_re_reserve_tops_up_allocations_in_location_order():
    warehouse = small_store(
        stock=[
            StockRow(sku="X", location="PICK-A-01", on_hand=1),
            StockRow(sku="X", location="PICK-A-02", on_hand=2),
        ],
        orders=[
            order("OUT-1", qty=3),
            order(
                "OUT-2",
                qty=2,
                status="reserved",
                allocations=[
                    Allocation(location="PICK-A-01", qty=1),
                    Allocation(location="PICK-A-02", qty=1),
                ],
            ),
        ],
    )

    assert warehouse.reserve("OUT-1").order.status == "partially_reserved"
    warehouse.release("OUT-2")
    topped_up = warehouse.reserve("OUT-1").order

    assert topped_up.status == "reserved"
    assert topped_up.lines[0].allocations == [
        Allocation(location="PICK-A-01", qty=1),
        Allocation(location="PICK-A-02", qty=2),
    ]


def test_release_of_a_new_order_is_a_no_op():
    warehouse = Warehouse(load_seed(NOW))

    released = warehouse.release("OUT-5052")

    assert released.status == "new"
    assert released.lines[0].allocations == []


def test_s1_release_the_unpaid_order_and_reserve_the_marketplace_one():
    warehouse = Warehouse(load_seed(NOW))

    with pytest.raises(Conflict):
        warehouse.reserve("OUT-5052")
    held = warehouse.release("OUT-5041")
    reserved = warehouse.reserve("OUT-5052").order

    assert held.status == "new"
    assert held.lines[0].allocations == []
    assert reserved.status == "reserved"
    assert reserved.lines[0].allocations == [Allocation(location="PICK-A-05", qty=6)]


def test_s5_stock_in_receiving_is_reserved_only_after_the_put_away():
    warehouse = Warehouse(load_seed(NOW))

    with pytest.raises(Conflict):
        warehouse.reserve("OUT-5048")
    with pytest.raises(Conflict):
        warehouse.move(
            Move(
                sku="FRT-ELEC", from_location="RECV-01", to_location="PICK-B-02", qty=49
            )
        )
    warehouse.move(
        Move(sku="FRT-ELEC", from_location="RECV-01", to_location="PICK-B-02", qty=48)
    )
    reserved = warehouse.reserve("OUT-5048").order

    assert warehouse.order("OUT-5048").lines[0].reserved == 6
    assert reserved.status == "reserved"


def test_s3_create_an_order_for_an_erp_order():
    warehouse = Warehouse(load_seed(NOW))
    new = NewOrder(
        ref="SO-1053",
        customer="Marketplace buyers",
        lines=[NewLine(sku="COF-ESP-1KG", qty=3)],
    )

    created = warehouse.create(new)

    assert (created.id, created.status) == ("OUT-5053", "new")
    reserved = warehouse.reserve("OUT-5053").order
    assert reserved.lines[0].allocations == [Allocation(location="PICK-A-01", qty=3)]
    with pytest.raises(Conflict, match="OUT-5053 already fulfils SO-1053"):
        warehouse.create(new)


def test_create_rejects_an_unknown_sku():
    warehouse = Warehouse(load_seed(NOW))
    new = NewOrder(ref="SO-1", customer="C", lines=[NewLine(sku="NOPE", qty=1)])

    with pytest.raises(NotFound):
        warehouse.create(new)


def test_a_cancelled_order_can_be_replaced():
    warehouse = Warehouse(load_seed(NOW))
    warehouse.cancel("OUT-5052")

    replacement = warehouse.create(
        NewOrder(
            ref="SO-1052",
            customer="Marketplace buyers",
            lines=[NewLine(sku="GRN-HOME", qty=6)],
        )
    )

    assert replacement.id == "OUT-5053"
