def move(client, sku="GLV-NIT-L", source="A-01-02", destination="D-01-01", qty=1):
    body = {"sku": sku, "from_location": source, "to_location": destination, "qty": qty}
    return client.post("/moves", json=body)


def levels(client, sku):
    return {
        level["location"]: (level["on_hand"], level["reserved"], level["available"])
        for level in client.get(f"/stock/{sku}").json()["locations"]
    }


def test_stock_totals_and_levels(client):
    body = client.get("/stock/GLV-NIT-L").json()

    assert (body["on_hand"], body["reserved"], body["available"]) == (200, 90, 110)
    assert levels(client, "GLV-NIT-L") == {
        "A-01-02": (120, 40, 80),
        "A-02-01": (30, 0, 30),
        "B-01-01": (50, 50, 0),
    }


def test_broken_sku_is_unavailable_and_unknown_sku_is_not_found(client):
    broken = client.get("/stock/SCN-01")
    unknown = client.get("/stock/NOPE")

    assert broken.status_code == 503
    assert broken.json() == {
        "detail": "The stock service failed for SCN-01. Try again later."
    }
    assert unknown.status_code == 404


def test_products_search_is_a_substring_match_and_hides_broken(client):
    gloves = client.get("/products", params={"q": "glov"}).json()

    assert [p["sku"] for p in gloves] == ["GLV-NIT-L", "GLV-NIT-XL", "GLV-LAT-L"]
    assert client.get("/products", params={"q": "gloves l"}).json() == []
    assert client.get("/products", params={"q": "scanner"}).json() == [
        {"sku": "SCN-01", "name": "Handheld barcode scanner"}
    ]


def test_locations_include_empty_ones(client):
    body = client.get("/locations").json()

    assert len(body) == 9
    assert {loc["location"] for loc in body if not loc["stock"]} == {
        "D-01-01",
        "D-01-02",
    }


def test_orders_filter_by_status(client):
    assert [
        o["id"] for o in client.get("/orders", params={"status": "new"}).json()
    ] == [1001, 1003]
    assert client.get("/orders", params={"status": "lost"}).status_code == 422
    assert client.get("/orders/42").status_code == 404


def test_reserve_fully(client):
    body = client.post("/orders/1001/reserve").json()

    assert body["order"]["status"] == "reserved"
    assert body["shortages"] == []
    assert levels(client, "GLV-NIT-XL") == {"A-01-01": (60, 20, 40)}


def test_reserve_partially_takes_locations_in_id_order(client):
    body = client.post("/orders/1003/reserve").json()

    assert body == {
        "order": {
            "id": 1003,
            "customer": "Northwind",
            "status": "partially_reserved",
            "lines": [
                {
                    "sku": "GLV-NIT-L",
                    "qty": 50,
                    "allocations": [{"location": "A-01-02", "qty": 50}],
                    "reserved": 50,
                },
                {
                    "sku": "TAPE-48",
                    "qty": 10,
                    "allocations": [{"location": "B-03-01", "qty": 5}],
                    "reserved": 5,
                },
            ],
        },
        "shortages": [{"sku": "TAPE-48", "missing": 5}],
    }
    assert levels(client, "GLV-NIT-L")["A-01-02"] == (120, 90, 30)


def test_reserve_again_with_nothing_new_conflicts_and_keeps_the_order(client):
    first = client.post("/orders/1003/reserve").json()["order"]
    second = client.post("/orders/1003/reserve")

    assert second.status_code == 409
    assert second.json() == {
        "detail": "Nothing reserved for order 1003: no available stock of TAPE-48."
    }
    assert client.get("/orders/1003").json() == first


def test_reserve_a_reserved_order_is_a_no_op(client):
    body = client.post("/orders/1002/reserve").json()

    assert body["order"]["status"] == "reserved"
    assert levels(client, "GLV-NIT-L")["A-01-02"] == (120, 40, 80)


def test_closed_orders_cant_change(client):
    reserve = client.post("/orders/999/reserve")
    cancel = client.post("/orders/999/cancel")

    assert reserve.status_code == cancel.status_code == 409
    assert reserve.json() == {"detail": "Order 999 is shipped; it can't be reserved."}


def test_cancel_releases_allocations(client):
    body = client.post("/orders/1002/cancel").json()

    assert body["status"] == "cancelled"
    assert body["lines"][0]["reserved"] == 0
    assert levels(client, "GLV-NIT-L")["A-01-02"] == (120, 0, 120)
    assert levels(client, "GLV-NIT-L")["B-01-01"] == (50, 0, 50)
    assert client.post("/orders/1001/cancel").json()["status"] == "cancelled"


def test_move_available_stock_into_an_empty_location(client):
    body = move(client, qty=80).json()

    assert (body["source"]["location"], body["destination"]["location"]) == (
        "A-01-02",
        "D-01-01",
    )
    assert levels(client, "GLV-NIT-L")["A-01-02"] == (40, 40, 0)
    assert levels(client, "GLV-NIT-L")["D-01-01"] == (80, 0, 80)


def test_move_that_empties_a_location_drops_its_row(client):
    move(client, sku="TAPE-48", source="B-03-01", qty=5)

    assert levels(client, "TAPE-48") == {"D-01-01": (5, 0, 5)}


def test_move_errors(client):
    too_many = move(client, qty=81)
    assert too_many.status_code == 409
    assert too_many.json() == {
        "detail": "Only 80 of GLV-NIT-L can move from A-01-02; the rest is reserved for orders or isn't there."
    }
    assert move(client, source="D-01-02").status_code == 409
    assert move(client, destination="D-09-09").status_code == 404
    assert move(client, sku="NOPE").status_code == 404
    assert move(client, qty=0).status_code == 422
    assert move(client, destination="A-01-02").status_code == 422


def test_reset_restores_the_seed(client):
    seed = client.get("/_state").json()
    client.post("/orders/1001/reserve")
    move(client, sku="BOX-M", source="C-01-01")

    assert client.get("/_state").json() != seed
    assert client.post("/_reset").json() == seed
    assert client.get("/_state").json() == seed


def test_state_exposes_the_test_only_flag(client):
    products = client.get("/_state").json()["products"]

    assert {p["sku"] for p in products if p["broken"]} == {"SCN-01"}
