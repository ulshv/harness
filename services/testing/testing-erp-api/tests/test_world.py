"""The four seeds tell one story: every link between systems points at something that exists, and the only
inconsistencies are the demo's stuck states. The ERP is the hub, so the cross-system check lives here."""

from pathlib import Path

import json5

TESTING = Path(__file__).resolve().parents[2]
RESERVABLE_ZONES = ("PICK-", "BULK-")


def seed(service: str) -> dict:
    return json5.loads((TESTING / service / "app" / "seed.jsonc").read_text())


def test_erp_orders_point_at_their_warehouse_orders():
    wms = {o["id"]: o for o in seed("testing-wms-api")["orders"]}
    erp = seed("testing-erp-api")["sales_orders"]

    for order in erp:
        fulfilment = wms[order["wms_order_id"]]
        assert fulfilment["ref"] == order["id"]
        assert [(line["sku"], line["qty"]) for line in fulfilment["lines"]] == [
            (line["sku"], line["qty"]) for line in order["lines"]
        ]
    assert {o["ref"] for o in wms.values()} == {o["id"] for o in erp}


def test_every_sku_is_a_warehouse_product():
    skus = {p["sku"] for p in seed("testing-wms-api")["products"]}
    erp = seed("testing-erp-api")

    for order in erp["sales_orders"] + erp["purchase_orders"]:
        assert {line["sku"] for line in order["lines"]} <= skus


def test_marketplace_orders_reach_the_erp_except_the_lost_one():
    marketplace = seed("testing-marketplace-api")
    erp = seed("testing-erp-api")["sales_orders"]
    imported = {o["marketplace_order_id"] for o in erp if o.get("marketplace_order_id")}

    assert imported <= {o["id"] for o in marketplace["orders"]}
    by_id = {o["id"]: o for o in marketplace["orders"]}
    prices = {x["sku"]: x["price"] for x in marketplace["listings"]}
    for order in erp:
        if source := by_id.get(order.get("marketplace_order_id")):
            assert [(x["sku"], x["qty"]) for x in source["lines"]] == [
                (x["sku"], x["qty"]) for x in order["lines"]
            ]
            assert (source["status"] == "shipped") == (
                order.get("status") == "fulfilled"
            )
            # the agent prices an imported order from the listing: it must agree with the ERP
            assert all(x["unit_price"] == prices[x["sku"]] for x in order["lines"])
    # S3: the one order the sync lost
    assert [o["id"] for o in marketplace["orders"] if o["id"] not in imported] == [
        "114-7781302"
    ]


def test_listings_offer_only_reservable_stock_except_the_kettles():
    wms = seed("testing-wms-api")
    listings = seed("testing-marketplace-api")["listings"]
    reserved: dict[tuple[str, str], int] = {}
    for order in wms["orders"]:
        for line in order["lines"]:
            for a in line.get("allocations", []):
                key = (line["sku"], a["location"])
                reserved[key] = reserved.get(key, 0) + a["qty"]
    reservable: dict[str, int] = {}
    for row in wms["stock"]:
        if row["location"].startswith(RESERVABLE_ZONES):
            free = row["on_hand"] - reserved.get((row["sku"], row["location"]), 0)
            reservable[row["sku"]] = reservable.get(row["sku"], 0) + free

    oversold = {
        listing["sku"]: (listing["quantity"], reservable.get(listing["sku"], 0))
        for listing in listings
        if listing["quantity"] > reservable.get(listing["sku"], 0)
    }

    # S2: the kettles listing offers 25 of none
    assert oversold == {"KET-GOOSE": (25, 0)}


def test_shipped_in_the_warehouse_means_fulfilled_in_the_erp():
    shipped = {
        o["ref"] for o in seed("testing-wms-api")["orders"] if o["status"] == "shipped"
    }
    fulfilled = {
        o["id"]
        for o in seed("testing-erp-api")["sales_orders"]
        if o.get("status") == "fulfilled"
    }

    assert shipped == fulfilled
