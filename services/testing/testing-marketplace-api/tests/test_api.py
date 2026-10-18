def test_the_order_due_in_six_hours(client):
    order = client.get("/orders/114-3349201").json()

    assert order == {
        "id": "114-3349201",
        "buyer": "Daniel Novak",
        "lines": [{"sku": "GRN-HOME", "qty": 6}],
        "ship_by": "2026-10-18T18:00:00Z",
        "status": "unshipped",
    }
    assert client.get("/orders/114-0000000").status_code == 404


def test_orders_filter_by_status(client):
    unshipped = client.get("/orders", params={"status": "unshipped"}).json()

    assert len(unshipped) == 6
    assert client.get("/orders", params={"status": "lost"}).status_code == 422


def test_set_a_listing_quantity(client):
    resp = client.put("/listings/KET-GOOSE/quantity", json={"quantity": 0})

    assert resp.json() == {
        "sku": "KET-GOOSE",
        "title": "Gooseneck Pour-Over Kettle",
        "price": "59.00",
        "quantity": 0,
    }
    assert client.get("/listings/KET-GOOSE").json()["quantity"] == 0


def test_listing_errors(client):
    assert (
        client.put("/listings/KET-GOOSE/quantity", json={"quantity": -1}).status_code
        == 422
    )
    unknown = client.put("/listings/NOPE/quantity", json={"quantity": 1})
    assert unknown.status_code == 404
    assert unknown.json() == {"detail": "No listing for NOPE."}


def test_listings_and_state(client):
    assert len(client.get("/listings").json()) == 10
    assert sorted(client.get("/_state").json()) == ["listings", "orders"]
