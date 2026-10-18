import time

from fastapi.testclient import TestClient

from app.main import create_app


def move(client, sku="FRT-ELEC", source="RECV-01", destination="PICK-B-02", qty=1):
    body = {"sku": sku, "from_location": source, "to_location": destination, "qty": qty}
    return client.post("/moves", json=body)


def levels(client, sku):
    return {
        level["location"]: (
            level["zone"],
            level["on_hand"],
            level["reserved"],
            level["available"],
        )
        for level in client.get(f"/stock/{sku}").json()["locations"]
    }


def test_stock_in_receiving_counts_on_hand_but_isnt_available(client):
    body = client.get("/stock/FRT-ELEC").json()

    assert (body["on_hand"], body["reserved"], body["available"]) == (50, 2, 0)
    assert levels(client, "FRT-ELEC") == {
        "PICK-B-02": ("PICK", 2, 2, 0),
        "RECV-01": ("RECV", 48, 0, 0),
    }
    received = next(
        level for level in body["locations"] if level["location"] == "RECV-01"
    )
    assert received["received_at"] == "2026-10-16T12:00:00Z"


def test_unknown_sku_is_not_found(client):
    resp = client.get("/stock/NOPE")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Unknown SKU NOPE."}


def test_products_search_is_a_substring_match(client):
    beans = client.get("/products", params={"q": "beans"}).json()

    assert [p["sku"] for p in beans] == ["COF-ESP-1KG", "COF-HOU-1KG", "COF-DEC-1KG"]


def test_locations_carry_their_zone_and_include_empty_ones(client):
    by_id = {loc["location"]: loc for loc in client.get("/locations").json()}

    assert len(by_id) == 18
    assert by_id["RECV-02"] == {"location": "RECV-02", "zone": "RECV", "stock": []}
    assert by_id["SHIP-01"]["zone"] == "SHIP"


def test_orders_filter_by_status(client):
    orders = client.get("/orders", params={"status": "partially_reserved"}).json()

    assert [o["id"] for o in orders] == ["OUT-5045", "OUT-5048"]
    assert client.get("/orders", params={"status": "lost"}).status_code == 422


def test_create_order(client):
    body = {
        "ref": "SO-1053",
        "customer": "Marketplace buyers",
        "lines": [{"sku": "COF-ESP-1KG", "qty": 3}],
    }

    created = client.post("/orders", json=body)
    again = client.post("/orders", json=body)

    assert created.status_code == 201
    assert created.json() == {
        "id": "OUT-5053",
        "ref": "SO-1053",
        "customer": "Marketplace buyers",
        "status": "new",
        "lines": [{"sku": "COF-ESP-1KG", "qty": 3, "allocations": [], "reserved": 0}],
    }
    assert again.status_code == 409
    assert again.json() == {"detail": "Order OUT-5053 already fulfils SO-1053."}
    assert client.post("/orders", json={**body, "lines": []}).status_code == 422


def test_reserve_reports_shortages(client):
    resp = client.post("/orders/OUT-5045/release")
    reserved = client.post("/orders/OUT-5045/reserve").json()

    assert resp.json()["status"] == "new"
    assert reserved["order"]["status"] == "partially_reserved"
    assert reserved["shortages"] == [{"sku": "COF-HOU-1KG", "missing": 25}]


def test_reserve_with_nothing_available_conflicts(client):
    resp = client.post("/orders/OUT-5052/reserve")

    assert resp.status_code == 409
    assert resp.json() == {
        "detail": "Nothing reserved for order OUT-5052: no available stock of GRN-HOME."
    }


def test_reserve_a_reserved_order_is_a_no_op(client):
    before = client.get("/orders/OUT-5041").json()
    resp = client.post("/orders/OUT-5041/reserve")

    assert resp.json() == {"order": before, "shortages": []}


def test_closed_orders_cant_change(client):
    assert client.post("/orders/OUT-5030/reserve").status_code == 409
    assert client.post("/orders/OUT-5030/release").status_code == 409
    assert client.post("/orders/OUT-5030/cancel").json() == {
        "detail": "Order OUT-5030 is shipped; it can't be cancelled."
    }
    assert client.get("/orders/OUT-9999").status_code == 404


def test_cancel_releases_allocations(client):
    resp = client.post("/orders/OUT-5041/cancel")

    assert resp.json()["status"] == "cancelled"
    assert levels(client, "GRN-HOME") == {"PICK-A-05": ("PICK", 10, 0, 10)}


def test_put_away_moves_stock_out_of_receiving(client):
    resp = move(client, qty=48)

    assert resp.status_code == 200
    assert resp.json()["destination"] == {
        "sku": "FRT-ELEC",
        "location": "PICK-B-02",
        "zone": "PICK",
        "on_hand": 50,
        "reserved": 2,
        "available": 48,
        "received_at": None,
    }
    # the emptied receiving row is dropped
    assert levels(client, "FRT-ELEC") == {"PICK-B-02": ("PICK", 50, 2, 48)}


def test_move_errors(client):
    assert move(client, source="PICK-B-02", qty=1).status_code == 422
    assert move(client, qty=49).json() == {
        "detail": "Only 48 of FRT-ELEC can move from RECV-01; the rest is reserved for orders or isn't there."
    }
    assert move(client, destination="PICK-Z-99").status_code == 404
    assert move(client, source="PICK-B-02", destination="RECV-02").json() == {
        "detail": "RECV-02 is in receiving, which only takes deliveries; move stock to a PICK or BULK location."
    }
    assert move(client, qty=0).status_code == 422


def test_state_shows_the_whole_store(client):
    state = client.get("/_state").json()

    assert sorted(state) == ["locations", "orders", "products", "stock"]
    assert len(state["products"]) == 13
    assert client.post("/_reset").status_code == 404


def test_latency_delays_every_response():
    client = TestClient(create_app(latency=(0.2, 0.2)))

    started = time.monotonic()
    client.get("/health")

    assert time.monotonic() - started >= 0.2
