import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import create_app

NEW_ORDER = {
    "customer_id": "CUST-007",
    "channel": "marketplace",
    "lines": [{"sku": "COF-ESP-1KG", "qty": 3, "unit_price": "24.00"}],
    "marketplace_order_id": "114-7781302",
    "delivery_by": "2026-10-21T12:00:00Z",
    "paid": True,
}


def test_overdue_follows_the_invoice(client):
    aurora = client.get("/sales-orders/SO-1041").json()
    harbor = client.get("/sales-orders/SO-1045").json()

    assert aurora["invoice"]["overdue"] is True
    assert harbor["invoice"]["overdue"] is False
    assert client.get("/sales-orders/SO-9999").status_code == 404


def test_hold_an_open_order(client):
    held = client.post("/sales-orders/SO-1041/hold", json={"reason": "Payment overdue"})
    again = client.post(
        "/sales-orders/SO-1041/hold", json={"reason": "Payment overdue"}
    )

    assert held.json()["status"] == "on_hold"
    assert held.json()["hold_reason"] == "Payment overdue"
    assert again.status_code == 409
    assert again.json() == {
        "detail": "Sales order SO-1041 is on_hold; only open orders can be put on hold."
    }
    assert (
        client.post("/sales-orders/SO-1045/hold", json={"reason": ""}).status_code
        == 422
    )


def test_import_a_marketplace_order(client):
    created = client.post("/sales-orders", json=NEW_ORDER)
    again = client.post("/sales-orders", json=NEW_ORDER)
    unknown = client.post(
        "/sales-orders", json={**NEW_ORDER, "customer_id": "CUST-999"}
    )

    assert created.status_code == 201
    body = created.json()
    assert (body["id"], body["status"], body["wms_order_id"]) == (
        "SO-1053",
        "open",
        None,
    )
    assert body["invoice"]["paid"] is True
    assert again.status_code == 409
    assert again.json() == {
        "detail": "Marketplace order 114-7781302 is already sales order SO-1053."
    }
    assert unknown.status_code == 404


def test_link_the_warehouse_order(client):
    client.post("/sales-orders", json=NEW_ORDER)

    linked = client.post(
        "/sales-orders/SO-1053/wms-order", json={"wms_order_id": "OUT-5053"}
    )
    taken = client.post(
        "/sales-orders/SO-1041/wms-order", json={"wms_order_id": "OUT-5053"}
    )

    assert linked.json()["wms_order_id"] == "OUT-5053"
    assert taken.status_code == 409
    assert taken.json() == {
        "detail": "Sales order SO-1041 is already fulfilled by warehouse order OUT-5041."
    }


def test_sales_orders_filter_by_channel_and_status(client):
    marketplace = client.get(
        "/sales-orders", params={"channel": "marketplace", "status": "open"}
    )

    assert [o["id"] for o in marketplace.json()] == [
        "SO-1035",
        "SO-1038",
        "SO-1040",
        "SO-1050",
        "SO-1052",
    ]
    assert client.get("/sales-orders", params={"channel": "fax"}).status_code == 422


def test_the_late_purchase_order(client):
    open_orders = client.get("/purchase-orders", params={"status": "open"}).json()

    assert [o["id"] for o in open_orders] == ["PO-2207"]
    assert open_orders[0]["supplier"] == "Andes Coffee Importers"
    expected = datetime.fromisoformat(open_orders[0]["expected_at"])
    assert (
        timedelta(days=3) <= datetime.now(UTC) - expected < timedelta(days=3, minutes=1)
    )
    assert client.get("/purchase-orders/PO-9999").status_code == 404


def test_customers(client):
    aurora = client.get("/customers/CUST-001").json()

    assert aurora == {
        "id": "CUST-001",
        "name": "Hotel Aurora",
        "type": "b2b",
        "account_manager": "Maria Lopez",
        "payment_terms_days": 30,
    }
    assert len(client.get("/customers").json()) == 7


def test_state_shows_the_whole_store(client):
    state = client.get("/_state").json()

    assert sorted(state) == ["customers", "purchase_orders", "sales_orders"]


def test_an_unpaid_order_is_due_after_the_payment_terms(client):
    b2b = {**NEW_ORDER, "customer_id": "CUST-001", "channel": "b2b", "paid": False}
    del b2b["marketplace_order_id"]

    created = client.post("/sales-orders", json=b2b).json()

    assert created["invoice"]["overdue"] is False


def test_create_validation(client):
    naive = {**NEW_ORDER, "delivery_by": "2026-10-21T12:00:00"}
    no_id = {**NEW_ORDER, "marketplace_order_id": None}

    assert client.post("/sales-orders", json=naive).status_code == 422
    assert client.post("/sales-orders", json=no_id).status_code == 422


def test_latency_delays_every_response():
    client = TestClient(create_app(latency=(0.2, 0.2)))

    started = time.monotonic()
    client.get("/health")

    assert time.monotonic() - started >= 0.2
