def test_seeded_history_in_a_channel(client):
    warehouse = client.get("/messages", params={"to": "#warehouse"}).json()

    assert warehouse[0] == {
        "id": 4,
        "to": "#warehouse",
        "author": "@tom",
        "text": "Frother pallet in, will put away tomorrow.",
        "sent_at": "2026-10-16T12:00:00Z",
    }
    assert [m["id"] for m in warehouse] == [4, 5]


def test_the_late_supplier_promise(client):
    assert client.get("/messages", params={"to": "#purchasing"}).json() == [
        {
            "id": 2,
            "to": "#purchasing",
            "author": "@nina",
            "text": "Andes confirmed PO-2207, arriving in 2 days.",
            "sent_at": "2026-10-14T12:00:00Z",
        }
    ]


def test_post_to_a_channel(client):
    posted = client.post(
        "/messages", json={"to": "#sales", "text": "SO-1041 is on hold."}
    )
    thread = client.get("/messages", params={"to": "#sales"}).json()

    assert posted.status_code == 201
    assert (posted.json()["id"], posted.json()["author"]) == (7, "ops-assistant")
    assert thread[-1]["text"] == "SO-1041 is on hold."


def test_direct_message(client):
    client.post(
        "/messages", json={"to": "@maria", "text": "Hotel Aurora is 12 days overdue."}
    )

    assert [
        m["text"] for m in client.get("/messages", params={"to": "@maria"}).json()
    ] == ["Hotel Aurora is 12 days overdue."]


def test_unknown_target_and_empty_text(client):
    unknown = client.post("/messages", json={"to": "@bob", "text": "Hi"})

    assert unknown.status_code == 404
    assert unknown.json() == {
        "detail": "No channel or user @bob. Channels start with #, people with @."
    }
    assert client.get("/messages", params={"to": "#random"}).status_code == 404
    assert client.post("/messages", json={"to": "#ops", "text": ""}).status_code == 422


def test_people_and_channels(client):
    assert [u["handle"] for u in client.get("/users").json()] == [
        "@maria",
        "@alex",
        "@tom",
        "@nina",
    ]
    assert [c["name"] for c in client.get("/channels").json()] == [
        "#ops",
        "#sales",
        "#warehouse",
        "#purchasing",
    ]
    assert sorted(client.get("/_state").json()) == ["channels", "messages", "users"]
