from datetime import UTC, datetime

from app.store import Erp, load_seed


# loaded at the real time: `overdue` compares with the real clock
def test_the_only_stuck_states_are_the_demo_ones():
    now = datetime.now(UTC)
    erp = Erp(load_seed(now))
    open_orders = erp.sales_orders("open", None)

    assert {o.id for o in erp.store.sales_orders if o.invoice.overdue} == {"SO-1041"}
    assert {o.id for o in erp.purchase_orders("open") if o.expected_at < now} == {
        "PO-2207"
    }
    assert [o.id for o in open_orders if not o.wms_order_id] == []
    assert [o.id for o in open_orders if o.delivery_by < now] == []
