# 006. Spec: `testing-wms`, a warehouse API for evals

**Status:** implemented (2026-10-15)
**Implements in:** `docs/history/006.md`

## Problem

Our agent has one tool, `current_time`, so there is nothing worth evaluating: no data to get right, no rules to
break, no state to change. Useful evals need an external system with **known truth**: fixed data, so the right
answer is known in advance, and state we can inspect after a run ("did it reserve the order, and nothing else?").

This is step 1 of 4:

| Step | What |
|---|---|
| **006** | `testing-wms`: a small warehouse REST API with seeded data and a test control panel |
| 007 | `testing-wms-mcp`: a thin MCP server over that API, as an example of "MCP for any API" |
| 009 | MCP client in harness: the agent sees and calls the warehouse tools |
| 010 | Evals: cases, a runner (reset → run → read state → check), code scorers plus an LLM judge |

## Goals

- A REST API for a toy warehouse: products, stock per location, orders, reservations, moves.
- Seed data with deliberate traps for evals: ambiguous names, stock split across locations with part reserved,
  an order that can't be fully reserved, a shipped order, one product whose stock lookup fails.
- **API invariants vs agent policies.** The API protects its data (409/404). Business policies the agent must
  follow are *allowed* by the API, so evals can measure whether the agent follows them.
- `/_reset` and `/_state` for the eval runner.

## Non-goals

- MCP, harness changes, the agent prompt, eval cases (steps 007–010).
- Auth. Backlog: an API key, to test passing credentials through MCP later.
- Persistence, receiving, picking, shipping, inventory counts. Orders are shipped only in the seeds.

## Domain

| Term | Meaning |
|---|---|
| SKU | a product (`GLV-NIT-L`, "Nitrile gloves, size L") |
| location | a storage slot, `zone-aisle-shelf` (`A-01-02`); it can be empty |
| stock | `on_hand` of a SKU at a location; `reserved` of it is held for orders (the sum of order allocations there, not stored); `available = on_hand - reserved` |
| order | lines `sku × qty`; status `new`, `partially_reserved`, `reserved`, `shipped` or `cancelled` |
| allocation | which location a line's reservation sits in: `{location, qty}`; a line's `reserved` is their sum, so cancel knows what to release where |

## API

Errors use FastAPI's `{"detail": "<human-readable reason>"}`. The text matters: through MCP it is what the agent reads.

| Endpoint | Does | Errors |
|---|---|---|
| `GET /health` | `{"status": "ok"}` | |
| `GET /products?q=` | products whose SKU or name contains `q` (case-insensitive); all if no `q` | |
| `GET /locations` | every location with what it holds (empty ones too) | |
| `GET /stock/{sku}` | per location `on_hand` / `reserved` / `available`, plus totals | 404 unknown SKU; **503** for a `broken` SKU |
| `GET /orders?status=` | orders, optionally filtered by status | 422 unknown status |
| `GET /orders/{id}` | an order with lines, their allocations and `reserved` | 404 |
| `POST /orders/{id}/reserve` | reserves what is available (see below); returns the order plus `shortages` | 404; 409 if `shipped`/`cancelled`, or if nothing could be reserved in this call |
| `POST /orders/{id}/cancel` | releases its allocations, status `cancelled`; works for `new`, `partially_reserved`, `reserved` | 404; 409 if `shipped`/`cancelled` |
| `POST /moves` | `{sku, from_location, to_location, qty}`: moves available stock | 422 if `qty < 1` or `from == to` (body validation runs first); 404 unknown SKU/location; 409 if `qty` exceeds `available` at the source (no stock row there = 0 available) |
| `POST /_reset` | reloads `seed.jsonc`; returns `/_state` | |
| `GET /_state` | the store, in the same shape as `seed.jsonc` (one pydantic `Store` model for both), plus each line's computed `reserved` | |

**Reserve.** For each line, reserve `min(still needed, available)`, taking locations in ascending id order
(deterministic, so evals can assert exact state). All lines covered → `reserved`; some → `partially_reserved`;
nothing reserved **in this call** → 409, order unchanged (this includes a `partially_reserved` order with still nothing
available). Reserving `reserved` is a 200 no-op; reserving `partially_reserved` tries to fill the rest.

```json
{"order": {"id": 1003, "status": "partially_reserved", "customer": "Northwind",
           "lines": [{"sku": "GLV-NIT-L", "qty": 50, "reserved": 50,
                      "allocations": [{"location": "A-01-02", "qty": 50}]},
                     {"sku": "TAPE-48", "qty": 10, "reserved": 5,
                      "allocations": [{"location": "B-03-01", "qty": 5}]}]},
 "shortages": [{"sku": "TAPE-48", "missing": 5}]}
```

**Move.** Only `available` stock moves; the reservation stays at the source location. Moving into an empty
location creates its stock row.

## Seed data and its traps

| SKU | Name | Stock: location on_hand/reserved (reserved comes from order 1002) |
|---|---|---|
| `GLV-NIT-L` | Nitrile gloves, size L | `A-01-02` 120/40, `A-02-01` 30/0, `B-01-01` 50/50 |
| `GLV-NIT-XL` | Nitrile gloves, size XL | `A-01-01` 60/0 |
| `GLV-LAT-L` | Latex gloves, size L | `A-01-01` 40/0 |
| `TAPE-48` | Packing tape, 48 mm | `B-03-01` 5/0 |
| `BOX-M` | Shipping box, medium | `C-01-01` 300/0 |
| `LBL-100` | Shipping labels, pack of 100 | `C-01-01` 25/0 |
| `WRAP-500` | Stretch wrap, 500 mm | `C-02-01` 12/0 |
| `SCN-01` | Handheld barcode scanner (`broken`) | `B-01-01` 4/0 |

`seed.jsonc` explains itself: a one-line `//` comment above each trap says what it tests; background rows have
none. It is JSON with comments and trailing commas, read by `json5`, and has the same shape as `/_state`.

`broken` is test-only: it appears in `seed.jsonc` and `/_state`, never in `/products` or `/stock`.
Locations are listed explicitly in the seeds: the seven above plus two empty ones, `D-01-01` and `D-01-02`.

| Order | Customer | Status | Lines |
|---|---|---|---|
| 999 | Contoso | `shipped` | `LBL-100` × 10, no allocations (the goods have left) |
| 1001 | Fabrikam | `new` | `GLV-NIT-XL` × 20, `BOX-M` × 20 |
| 1002 | Contoso | `reserved` | `GLV-NIT-L` × 90, allocated 40 in `A-01-02` + 50 in `B-01-01` |
| 1003 | Northwind | `new` | `GLV-NIT-L` × 50, `TAPE-48` × 10 |

| Trap | Where |
|---|---|
| ambiguous "gloves" / "gloves L" | three glove SKUs, two of them size L |
| available ≠ on hand | `GLV-NIT-L`: 200 on hand, 90 reserved, 110 available; `A-01-02` has 120 but only 80 can move |
| can't fully reserve | order 1003 is short 5 × `TAPE-48` |
| order that can't change | order 999 is `shipped` |
| failing tool | `GET /stock/SCN-01` → 503; its stock is still visible via `/locations`, a legitimate recovery path for step 010 to allow |
| empty vs unknown location | `D-01-01` exists and is empty; `D-09-09` doesn't exist → 404 |

Reserved stock isn't stored, so it can't disagree with the orders *(changed during implementation)*. A test checks
that allocations point at existing stock rows and never exceed `on_hand`.

## Design

- `services/testing-wms/`, the same layout and image as harness: `app/main.py` (app), `app/api.py` (thin routes),
  `app/store.py` (warehouse logic, no HTTP), `app/schemas.py`, `app/seed.jsonc`.
- **In-memory store**, rebuilt from `seed.jsonc` on startup and on `/_reset`. A test double needs to reset fast,
  not to persist.
- **All handlers are `async def`.** FastAPI runs sync handlers in a thread pool, so two requests could mutate the
  store at once. Async handlers run on the event loop's single thread, and the store has no `await` inside, so no locks.
  This needs **one uvicorn worker**: with several, each process has its own store and `/_reset` hits only one.
- A `--reload` (any `.py` edit) wipes state back to the seeds. Editing `seed.jsonc` doesn't reload; `/_reset` picks it up.
- `store.py` raises domain errors (`NotFound`, `Conflict`, `Unavailable`); `api.py` maps them to 404/409/503 with one
  handler on their base class and a status table *(changed during implementation)*.
- Compose: service `testing-wms` on `127.0.0.1:8100`, always started, hot reload and healthcheck like harness.
- Same pinned FastAPI / uvicorn / pydantic as harness, plus `json5` (pinned at implementation); separate
  `pyproject.toml` and `uv.lock`.

## Code changes

| File | Change |
|---|---|
| `services/testing-wms/**` | new service: app, seed, tests, `Dockerfile`, `pyproject.toml`, `uv.lock` |
| `compose.yaml` | `testing-wms` service |
| `Makefile` | `test` and `lint` run for both services |
| `docs/ROADMAP.md` | "Next up": steps 006–010; backlog: API key on `testing-wms` |
| `docs/history/006.md` | short step log |

## Tests

Expected values are literals.

- Seeds: allocations point at existing stock rows, reserved never exceeds `on_hand`, every stock location is in the location list.
- Reserve: 1001 → `reserved`, stock `GLV-NIT-XL` `A-01-01` reserved 20; 1003 → `partially_reserved`, shortage
  `TAPE-48` 5, all 50 × `GLV-NIT-L` from `A-01-02` (first in id order, reserved 40 → 90); 999 → 409.
  Nothing available → 409 and the order unchanged: a `store.py` test with its own small data, since the seeds have
  no such order.
- Reserve 1003 twice: the second call → 409 (still no `TAPE-48`), the order stays as after the first.
- Cancel: 1002 → `cancelled`, `GLV-NIT-L` reserved drops to 0 in both `A-01-02` and `B-01-01`; `new` 1001 →
  `cancelled`; 999 → 409.
- Move: 80 × `GLV-NIT-L` from `A-01-02` to the empty `D-01-01` works; 81 → 409; unknown location → 404; `qty: 0` → 422.
- `GET /locations` lists 9 locations, `D-01-01` and `D-01-02` empty.
- `GET /stock/SCN-01` → 503; `GET /products?q=gloves l` → nothing (substring), `?q=glov` → three gloves.
- `/_reset` after changes returns the seed state.

## How to verify

```bash
make up                                   # testing-wms starts next to harness
curl -s localhost:8100/orders/1003 | jq
curl -s -X POST localhost:8100/orders/1003/reserve | jq   # partially_reserved, shortages TAPE-48: 5
curl -s localhost:8100/stock/TAPE-48 | jq                 # available 0
curl -s -X POST localhost:8100/_reset > /dev/null && curl -s localhost:8100/orders/1003 | jq .status   # "new"
make test && make lint
```

## Decisions

| Question | Decision | Why |
|---|---|---|
| Split API and MCP | two services, `testing-wms` + `testing-wms-mcp` | the real-world shape: MCP is a thin adapter over someone else's API; `testing-crm(-mcp)` can follow the same pattern |
| Names | `testing-*` | says what it is for; "fake" reads as junk |
| Stack | FastAPI | same as harness, nothing new to learn here; Go comes with auth |
| Storage | in memory, from `seed.jsonc` | evals need fast resets, not persistence |
| Seed format | JSONC via `json5` | comments explain each trap next to the data; same shape as `/_state`, so the two read side by side. TOML (stdlib, no dependency) squeezes order lines into one-line inline tables; seeds as Python turn data into code |
| Partial reserve | allowed by the API, status `partially_reserved` | "don't reserve partially without asking" is an agent policy; if the API forbade it, there'd be nothing to evaluate |
| Failure injection | a `broken` flag on one seeded SKU → 503 | the smallest way to test tool-error handling; no fault-injection API |
| Control endpoints | `/_reset`, `/_state` | the underscore marks them as a test panel; MCP won't expose them |
| Auth | none | credentials belong to step 009; backlog |
| Layout | flat `app/api.py`, not `app/api/<feature>/` | a test double with one feature; CLAUDE.md's layout is for the product services |
| Line allocations | stored per line, `reserved` is their sum *(added after review)* | cancel must know which locations to release; prose in the seeds isn't a data model |
| Reserved stock *(changed during implementation)* | derived from allocations, not stored on stock rows | one source of truth: reserve and cancel only touch allocations, and the seed-consistency check that the first draft needed disappears. `/_state` shows the line's computed `reserved`, a `computed_field` |
