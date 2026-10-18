# 011. Spec: the CoffeeSupplies demo, an agent across four systems

**Status:** implemented (2026-10-18)
**Implements in:** `docs/history/011.md`

## Problem

The README promises "ask the agent what it can do", and the agent answers well, but there is little to show: one
toy warehouse with eval traps, generic location codes (`A-01-02`), gloves and tape, no flows. A real operations
agent earns its keep at the seams between systems: an order paid in the ERP but never sent to the warehouse, a
marketplace listing selling stock that's gone. None of that exists yet.

The goal is a short README video (and a separate Russian take for `README-ru.md`): a user asks one question, the
agent walks four systems, finds what's stuck, proposes a plan, and on "go ahead" fixes it and tells the people who
need to know.

## Goals

- A believable company: **CoffeeSupplies LLC**, a foreign wholesale distributor of coffee, tea and barista
  equipment. It sells B2B by contract (cafés, hotels), to consumers through its own web shop, and on an
  Amazon-like marketplace. Data in English; names translate cleanly into Russian.
- Four testing systems, each a REST API plus a thin MCP server over it, in the existing `testing-wms` pattern:
  **WMS** (warehouse), **ERP** (customers, sales and purchase orders), **marketplace** (its orders and listings),
  **chat** (the team messenger).
- Five seeded stuck states that are only visible by joining data across systems (see "Scenarios"), each fixable
  with the write tools the systems expose.
- An operations-assistant system prompt for the demo: investigate across systems, propose a numbered plan, act only
  after the user says so, report, notify people in chat. Replies in the user's language.
- The testing systems leave `compose.yaml`: `make up` runs the bare harness, `make up:demo` adds the demo world.

## Non-goals

- Evals. They move to "Later" in the roadmap; the eval traps of 006 are dropped, not preserved.
- Human-in-the-loop approval (LangGraph interrupts, approve buttons). "Go ahead" in the chat is the approval.
- A chat UI for the testing messenger. Messages are checked via the chat API or the agent's own tools.
- Auth on testing systems, persistence, webhooks between systems. The systems don't call each other: keeping
  them in sync is the agent's job, which is the point of the demo.
- Recording the video (the user does that).

## Layout and run modes

```
services/testing/
  testing-wms-api/       # moved from services/testing-wms, rebuilt for the new world
  testing-wms-mcp/       # moved from services/testing-wms-mcp
  testing-erp-api/   testing-erp-mcp/
  testing-marketplace-api/   testing-marketplace-mcp/
  testing-chat-api/  testing-chat-mcp/
  demo-system-prompt.md
compose.yaml             # harness + webapp only
compose.testing.yaml     # the eight testing-* services; extends harness (MCP_SERVERS, depends_on, prompt)
```

| Service | Port (`127.0.0.1`) | MCP name in harness → tool prefix |
|---|---|---|
| `testing-wms-api` / `testing-wms-mcp` | 8100 / 8101 | `wms` → `wms_*` |
| `testing-erp-api` / `testing-erp-mcp` | 8110 / 8111 | `erp` → `erp_*` |
| `testing-marketplace-api` / `testing-marketplace-mcp` | 8120 / 8121 | `marketplace` → `marketplace_*` |
| `testing-chat-api` / `testing-chat-mcp` | 8130 / 8131 | `chat` → `chat_*` |

- `make up`: `docker compose up --watch --build`, as today. harness starts with no `MCP_SERVERS`: only
  `current_time`.
- `make up:demo`: `docker compose -f compose.yaml -f compose.testing.yaml up --watch --build`, foreground. The
  second file adds the testing services and merges into `harness`: `MCP_SERVERS` with all four servers,
  `depends_on` them (healthy), the demo prompt mounted read-only, `AGENT_SYSTEM_PROMPT_FILE` and
  `AGENT_RECURSION_LIMIT`. The Make target is `up\:demo` (escaped colon).
- **Reset = restart.** All state is in memory, loaded from each API's `seed.jsonc` at startup. Ctrl+C and
  `make up:demo` again give a fresh world for the next take. No `/_reset` endpoints *(WMS loses its own: the eval
  runner it served is deferred)*. Each API keeps `GET /_state` to inspect the world; MCP servers don't expose it.

## Time

Seeds store times as offsets from service startup, not absolute dates: `"+6h"`, `"-12d"`, `"+1d"` (pattern
`^[+-]\d+[hd]$`). Each API resolves them to UTC datetimes once, when it loads the seed, and the API returns ISO
8601. The agent's `current_time` stays real, and every take looks equally fresh ("ships by in 6 hours"). Each API
carries its own few-line resolver: they are separate projects, and a shared package would complicate four Docker
builds for ten lines.

## The world

**People** (chat handles; ERP uses the same names): Maria Lopez `@maria` (B2B account manager), Alex Reed `@alex`
(e-commerce and marketplace manager), Tom Becker `@tom` (warehouse lead), Nina Park `@nina` (purchasing). The agent
posts as `ops-assistant`. Channels: `#ops`, `#sales`, `#warehouse`, `#purchasing`.

**Products** (13, same SKUs in all systems): espresso, house blend and decaf beans 1 kg (`COF-ESP-1KG`,
`COF-HOU-1KG`, `COF-DEC-1KG`), green and black tea 100 bags (`TEA-GRN-100`, `TEA-BLK-100`), professional and home
grinders (`GRN-PRO`, `GRN-HOME`), electric milk frother (`FRT-ELEC`), gooseneck kettle (`KET-GOOSE`), V60 paper
filters (`FLT-V60-100`), 8 oz paper cups and lids, 1000 pcs (`CUP-PAP-8OZ`, `LID-8OZ`), vanilla syrup 1 l
(`SYR-VAN`).

**Warehouse zones**, with the zone in the location id: receiving dock `RECV-01..02`, pallet reserve `BULK-A-01..04`,
pick face `PICK-A-01..06` and `PICK-B-01..04`, dispatch `SHIP-01..02`. **Only PICK and BULK stock can be
reserved**: goods in receiving aren't put away yet, goods in dispatch are leaving. The builder fills the
background stock; the scenario rows below are fixed.

## Scenarios (the seeded stuck states)

Numbers are fixed; ids are the ones the seeds use.

| # | What's stuck | Data across systems | The fix the agent can apply |
|---|---|---|---|
| S1 | A marketplace order will miss its deadline because stock is held for an unpaid B2B order | marketplace `114-3349201`: 6 × `GRN-HOME`, ship by `+6h`, unshipped. ERP `SO-1052` (channel marketplace) → WMS `OUT-5052`, `new`. WMS `GRN-HOME`: 10 on hand in `PICK-A-05`, all reserved by `OUT-5041` ← ERP `SO-1041`, Hotel Aurora (B2B, `@maria`), delivery `+5d`, invoice due `-12d`, unpaid | WMS release `OUT-5041`; reserve `OUT-5052`; ERP hold `SO-1041` ("payment overdue"); chat `@maria` (and `#sales`) |
| S2 | A listing sells stock that doesn't exist (oversell risk) | marketplace listing `KET-GOOSE` shows 25. WMS: 2 on hand in `PICK-B-03`, both reserved by `OUT-5050` ← `SO-1050` ← marketplace `114-5520917` (2 × `KET-GOOSE`) | marketplace set listing quantity to 0; chat `@alex` |
| S3 | A marketplace order never reached the ERP or the warehouse | marketplace `114-7781302`: 3 × `COF-ESP-1KG`, ship by `+1d`, unshipped. No ERP order with that `marketplace_order_id`, no WMS order. Stock is plentiful | ERP create the sales order; WMS create the order with `ref`; reserve; ERP link the WMS order; chat `#ops` |
| S4 | A late purchase order blocks a B2B delivery | ERP `PO-2207`, Andes Coffee Importers, 200 × `COF-HOU-1KG`, expected `-3d`, open. ERP `SO-1045`, Blue Harbor Café (`@maria`), 40 × `COF-HOU-1KG`, delivery `+1d` → WMS `OUT-5045` partially reserved 15/40 (all the stock there is). Chat `#purchasing` `-4d`, `@nina`: "Andes confirmed PO-2207, arriving in 2 days." | chat `#purchasing` (chase the supplier), `@maria` (warn the customer, offer a partial delivery) |
| S5 | Goods sit in receiving while an order waits for them | WMS `RECV-01`: 48 × `FRT-ELEC`, received `-2d`. `PICK-B-02`: 2 × `FRT-ELEC`. `OUT-5048` ← ERP `SO-1048` (web shop, paid, delivery `+1d`) 6 × `FRT-ELEC`, partially reserved 2/6. Chat `#warehouse` `-2d`, `@tom`: "Frother pallet in, will put away tomorrow." | WMS move 48 `RECV-01` → `PICK-B-02`; reserve `OUT-5048` again; chat `#warehouse` |

Background: about ten healthy orders across channels (reserved, shipped, paid), a received purchase order, and some
ordinary chat history, so the stuck states aren't the only rows. The background must not create a sixth stuck
state by accident; a seed test checks the scenario rows and that background orders are consistent.

## APIs

Errors: FastAPI's `{"detail": "..."}`, written for the agent (the MCP layer passes them through as tool errors, as
in 007). Every API also has `GET /health` and `GET /_state`. Handlers are `async def`, one worker, in-memory
store, like 006.

**WMS** (changes to 006): locations become `{id, zone}`; stock rows in receiving carry `received_at`; order ids are
strings (`OUT-5041`) with `ref` (the ERP sales order) and `customer`; `/products` loses the `broken` flag.

| Endpoint | Does |
|---|---|
| `GET /products?q=`, `GET /locations`, `GET /stock/{sku}` | as in 006, plus zones; `available` counts only PICK and BULK |
| `GET /orders?status=`, `GET /orders/{id}` | as in 006, plus `ref` |
| `POST /orders` | `{ref, customer, lines}` → a `new` order with the next id; 409 if an order that isn't cancelled already has that `ref` *(changed during implementation: "open" would let a shipped ERP order be fulfilled twice)* |
| `POST /orders/{id}/reserve` | as in 006, allocating only from PICK then BULK, ascending location id |
| `POST /orders/{id}/release` | drops the order's allocations, status back to `new`; 409 if shipped/cancelled |
| `POST /orders/{id}/cancel`, `POST /moves` | as in 006; moving out of receiving is the put-away |

**ERP**

| Endpoint | Does |
|---|---|
| `GET /customers`, `GET /customers/{id}` | name, type (`b2b`/`consumer`/`marketplace`), account manager, payment terms |
| `GET /sales-orders?status=&channel=`, `GET /sales-orders/{id}` | lines, channel (`b2b`/`web`/`marketplace`), `marketplace_order_id`, `wms_order_id`, delivery date, invoice `{due, paid}` with computed `overdue`, status `open`/`on_hold`/`fulfilled`/`cancelled`, `hold_reason` |
| `POST /sales-orders` | creates an `open` order (used to import a marketplace order); 409 on a duplicate `marketplace_order_id` |
| `POST /sales-orders/{id}/hold` | `{reason}` → `on_hold`; 409 unless `open` |
| `POST /sales-orders/{id}/wms-order` | `{wms_order_id}` links the warehouse order; 409 if already linked |
| `GET /purchase-orders?status=`, `GET /purchase-orders/{id}` | supplier, lines, `expected_at`, status `open`/`received` |

**Marketplace**

| Endpoint | Does |
|---|---|
| `GET /orders?status=`, `GET /orders/{id}` | Amazon-style id, lines, `ship_by`, status `unshipped`/`shipped`/`cancelled` |
| `GET /listings`, `GET /listings/{sku}` | title, price, `quantity` (what buyers can order) |
| `PUT /listings/{sku}/quantity` | `{quantity}` (≥ 0) |

**Chat**

| Endpoint | Does |
|---|---|
| `GET /channels`, `GET /users` | channels with topics; users with name, handle, role |
| `GET /messages?to=` | messages in a channel (`#sales`) or a DM (`@maria`), oldest first |
| `POST /messages` | `{to, text}` from `ops-assistant`; 404 for an unknown channel or user |

## MCP servers

One tool per endpoint, minus `/health` and `/_state`, in the 007 pattern: the docstring is the description, facts
only (policies live in the prompt), the API body returned verbatim as text, API errors as `ToolError`. Each server
lists its own compose hostname in `TransportSecuritySettings.allowed_hosts`.

## harness changes

- `AgentSettings` (`AGENT_` prefix): `system_prompt_file: Path | None` (default: today's one-line prompt) and
  `recursion_limit: int = 25`. A set but unreadable file fails startup. The demo sets the limit to 61 (30 tool
  rounds): one investigation touches four systems, and parallel calls in a round help but don't guarantee it fits
  in 11.
- `compose.yaml`'s harness loses `MCP_SERVERS` and `depends_on`.

## The demo prompt

`services/testing/demo-system-prompt.md`, in English. It says: you are the operations assistant of CoffeeSupplies
LLC; the four systems and what each owns; investigate by joining data across systems before concluding; for
problems, give a numbered list (what, evidence, proposed fix) and **don't change anything until the user explicitly
agrees**; then apply, report what changed, and notify the right people in chat; don't retry a failing tool more
than once (the backlog item "A dead tool gets retried"); answer in the user's language, keep ids and SKUs as they
are; **posts to colleagues in chat are always in English** (the company's language, and the chat history is
English), whatever language the user speaks.

It also carries a few general operating rules of the company, the way a real ops team has them. They say what
counts as a problem and how to weigh one order against another, but name no scenario, order or SKU, so the agent
still has to find the stuck states in the data:

- a paid order with a near deadline comes before an unpaid order whose invoice is overdue; an overdue order is put
  on hold, not cancelled;
- stock is usable for orders only once it's put away (pick face or pallet reserve); goods shouldn't sit in
  receiving for more than a day;
- a marketplace listing must not offer more than the warehouse can still reserve;
- a purchase order past its expected date is late: chase the supplier, warn the customers who wait on it;
- every order the company accepted, on any channel, must exist in the ERP and the warehouse.

## Rehearsal (011.5): when the demo is done

- The "fix" column in "Scenarios" is one acceptable answer, not a script. Another fix that follows the operating
  rules and leaves the systems consistent counts.
- Done when, on the live model, the agent finds all five stuck states in **2 takes out of 3**, and "go ahead"
  leaves the systems consistent (checked through `/_state`).
- Allowed tuning when it misses: the prompt and the recursion limit. Seed data and tool descriptions may change
  only with a note in this spec ("changed during rehearsal").

## Substeps

| Substep | What you can poke at |
|---|---|
| 011.1 | Move to `services/testing/`, `compose.testing.yaml`, `make up:demo`, `AgentSettings`. `make up` → agent with `current_time` only; `make up:demo` → the old WMS tools |
| 011.2 | New WMS: zones, CoffeeSupplies seed with relative times, `POST /orders`, `release`; MCP tools updated |
| 011.3 | ERP API + MCP |
| 011.4 | Marketplace and chat, API + MCP each |
| 011.5 | Demo prompt, a full rehearsal of the scenario on the live model, README Quick start → `make up:demo` |

## Tests

Literal expected values; each API's store tested without HTTP, each MCP server against a mocked API (as in 007).

- Time resolver: `"+6h"`, `"-12d"` against a fixed `now`; a malformed offset fails the seed load.
- Seeds: every SKU exists in the systems that reference it; S1–S5 rows exactly as in the table; background
  orders are consistent (an ERP order's `wms_order_id` exists in the WMS seed, reserved never exceeds on hand).
- WMS: reserve skips `RECV-01` stock (S5 order stays 2/6), succeeds after the put-away move (6/6); release then
  reserve resolves S1 (`OUT-5052` reserved 6, `OUT-5041` back to `new`); `POST /orders` with a taken `ref` → 409.
- ERP: hold on `open` → `on_hold`, on `on_hold` → 409; duplicate `marketplace_order_id` → 409; `overdue` true for
  `SO-1041`.
- Marketplace: quantity `-1` → 422; set to 0 shows in `GET /listings/KET-GOOSE`.
- Chat: post to `#sales` appears in `GET /messages?to=%23sales` with author `ops-assistant`; unknown `@bob` → 404.
- harness: prompt file read; missing file fails settings; limit passes into the graph config.

## How to verify

```bash
make up            # bare harness: the agent has current_time only
make up:demo       # the CoffeeSupplies world
# localhost:8080: "Anything stuck across our systems today?" → the agent lists S1–S5 with evidence and a plan
# "Go ahead" → it applies the fixes and posts to chat
curl -s 'localhost:8130/messages?to=%23sales' | jq        # the agent's message is there
curl -s localhost:8100/orders/OUT-5052 | jq .status        # "reserved"
make test && make lint
```

## Code changes

| File | Change |
|---|---|
| `services/testing-wms*` → `services/testing/testing-wms-*` | moved (git mv), then rebuilt |
| `services/testing/testing-{erp,marketplace,chat}-{api,mcp}/` | new, the 006/007 layout |
| `services/testing/demo-system-prompt.md` | new |
| `compose.yaml`, `compose.testing.yaml` | testing services move to the second file |
| `Makefile` | `up\:demo`; `SERVICES` lists the new paths |
| `services/harness/app/settings.py`, `app/agent/graph.py`, `app/main.py` | `AgentSettings`, prompt and limit from settings |
| `docs/arch/003_demo-world.md` | new: the four systems, the run modes, how the agent joins them |
| `README.md`, `README-ru.md` | Quick start step → `make up:demo` |
| `docs/ROADMAP.md`, `docs/history/011.md`, `CLAUDE.md` (repo layout line) | step 011; evals → Later |

## Left to the builder (settled here so nobody guesses)

- Background listing quantities never exceed what the WMS can reserve for that SKU, so S2 stays the only oversell.
- Marketplace orders in the ERP belong to one customer, "Marketplace buyers" (type `marketplace`); the buyer's name
  stays in the marketplace.
- Request bodies are pydantic models next to the existing ones; field names follow the tables above.
- Receiving stock shows in `GET /stock/{sku}` with its zone, but `available` there is 0, so the totals match
  what `reserve` can take.
- 011.1 ships the prompt file mechanism with a one-line placeholder prompt; the real text lands in 011.5.

## Changed during implementation

- WMS `POST /orders` refuses a `ref` held by any order that isn't cancelled (the API table notes why).
- Nothing moves into receiving: a moved row would have no `received_at` to age by (011.2 review).
- A seed time must be an offset string; a number (a Unix timestamp) or an out-of-range offset fails the load.
- ERP: an imported order's invoice is due after the customer's payment terms, so a new unpaid order isn't overdue on
  arrival; `delivery_by` must carry a timezone; a marketplace order needs its `marketplace_order_id` (011.3 review).
- Marketplace listing prices equal the prices the ERP books for marketplace orders, so an import priced from the
  listing agrees with the ERP (011.4 review).
- The demo prompt (rehearsal): the proposal applies the operating rules instead of leaving decisions to people, and
  the go-ahead covers the approved steps, notifications included. Seed data and tool descriptions didn't change.

## Decisions

| Question | Decision | Why |
|---|---|---|
| Company | CoffeeSupplies LLC, coffee/tea/barista distributor, B2B + web shop + marketplace | the user's choice; channels share one stock, so cross-system conflicts arise naturally |
| Systems | WMS, ERP, marketplace, chat | the user's call; a CRM for cold calls adds a sales pipeline but almost no stock conflicts *(my call)* |
| Marketplace name | `marketplace` in code, Amazon-like mechanics | naming it `amazon` would read as a real integration *(my call)* |
| Deployment | a separate API and MCP service per system, all in `compose.testing.yaml` | the user's call; the real-world shape of "MCP over someone else's API" |
| Approval | "go ahead" in the chat, enforced by the prompt | the user's call; HITL needs interrupts and UI, a later step |
| Time | offsets from startup, resolved at load | `current_time` stays real and every take looks the same *(my call; a fixed date would contradict `current_time`)* |
| Reset | restart (`make up:demo`); no `/_reset` | the user's call |
| Eval traps of 006 | dropped | evals are deferred; one seed serves the demo |
| Systems talk to each other | never | syncing them is the agent's job: that's the demo |
| Business rules | general operating rules in the prompt, no scenario hints | the user's call; the agent still finds the stuck states, but weighs them like the company would, so takes don't drift |
| Chat language | always English | the user's call; a foreign company, English history; only the answer to the user follows their language |
| Prompt location | a file mounted into harness, chosen by `AGENT_SYSTEM_PROMPT_FILE` | the core stays generic; editing the prompt doesn't touch Python *(my call)* |
| Shared code between testing services | none, small duplication accepted | four independent Docker builds; the duplicated parts (time resolver, API client) are a few lines each *(my call)* |
