# 003. The demo world: an agent across four systems

How `make up:demo` turns the bare harness into the operations assistant of CoffeeSupplies LLC, and how the four
testing systems in `services/testing/` are built. This doc describes the world **as it is**; it is updated together
with the code. Why it looks this way is in [specs/011](../specs/011_coffeesupplies-demo.md).

## Two run modes

```
make up        compose.yaml                         harness + webapp; the agent has current_time only
make up:demo   compose.yaml + compose.testing.yaml  + 8 testing services; compose merges into harness:
                                                      MCP_SERVERS (4 servers), depends_on them,
                                                      AGENT_SYSTEM_PROMPT_FILE (mounted), AGENT_RECURSION_LIMIT=61
```

The core stays generic: harness knows nothing about coffee. The role, the company's rules and the tool list
come from configuration (`AgentSettings`, `McpSettings`), so another deployment swaps the world without touching
code. The prompt is read once at startup: after editing `services/testing/demo-system-prompt.md`,
`docker compose restart harness`.

## The systems

```
                       harness (agent)
      ┌──────────────┬───────┴──────┬────────────────┐
   wms_* (8101)   erp_* (8111)  marketplace_* (8121)  chat_* (8131)      MCP servers: thin adapters
      │              │              │                  │
 testing-wms-api  testing-erp-api  testing-marketplace-api  testing-chat-api   REST APIs, state in memory
   (8100)          (8110)            (8120)                  (8130)
```

| System | Owns | Writes the agent can make |
|---|---|---|
| WMS | products, locations by zone (RECV, BULK, PICK, SHIP), stock, warehouse orders `OUT-…` with reservations; each fulfils an ERP order (`ref`) | create an order, reserve, release, cancel, move stock (out of RECV = put-away; nothing moves into RECV) |
| ERP | customers, sales orders `SO-…` from every channel with invoices (`overdue` computed on read), purchase orders `PO-…` | create a sales order (import), hold, link the warehouse order |
| Marketplace | the seller's orders `114-…` with `ship_by`, listings with the quantity buyers can order | set a listing's quantity |
| Chat | people (`@maria`), channels (`#sales`), messages | post as `ops-assistant` |

**The systems never call each other.** The links between them are ids: an ERP order's `marketplace_order_id`
and `wms_order_id`, a warehouse order's `ref`. Keeping them consistent is the agent's job, which is what the demo
shows. Only PICK and BULK stock can be reserved, so `available` is 0 in receiving even when stock is there.

Each pair copies the 006/007 pattern: an API with thin routes over a store that knows nothing about HTTP, one
uvicorn worker and `async def` handlers (no locks), domain errors mapped to 404/409 with messages written for the
model; an MCP server (`mcp` 2.3.0, stateless Streamable HTTP) with one tool per endpoint that returns the API's
body verbatim and turns API errors into `ToolError`. Every API has `GET /_state`; the MCP servers don't expose it.
Every API answers after a random 0.3–1.0 s (`LATENCY_SECONDS` in its `app/main.py`, from history 010.4), like a real
backend would: the chat's spinners show, and parallel tool results come back out of order. Tests build the apps
without it.

## Time and reset

Seeds store times as offsets from startup (`"+6h"`, `"-12d"`). `app/clock.py` defines `Moment`, a datetime that,
when the seed is validated with `context={"now": now}`, must be an offset and resolves against `now`. So the
agent's real `current_time` and the data always agree, and every run looks equally fresh. State lives in memory:
restarting a service (`make up:demo` again, or
`docker compose -f compose.yaml -f compose.testing.yaml restart testing-erp-api`) reloads its seed. Editing a
`seed.jsonc` alone reloads nothing.

## The stuck states

Five seeded problems only show when data from several systems is joined: a marketplace deadline against stock
held for an unpaid B2B order (S1), a listing selling stock that's gone (S2), a marketplace order that never reached
the ERP or the warehouse (S3), a late purchase order behind a B2B delivery (S4), goods left in receiving while an
order waits (S5). The seeds mark each row with its scenario; `testing-erp-api/tests/test_world.py` checks the four
seeds against each other, so the only inconsistencies are these five.

## The agent's side

The demo prompt gives the role, what each system owns, five operating rules (what counts as a problem, which
order wins), and the way of working: investigate across systems, report a numbered plan, change nothing until the
user agrees, then apply all of it and notify people in chat (always in English). There's no human-in-the-loop
mechanism: the approval is the user's next message on the same thread.

## Reading order

`compose.testing.yaml` → `services/testing/demo-system-prompt.md` → any `*-api/app/seed.jsonc` →
`testing-wms-api/app/store.py` (zones, reserve) → `testing-erp-api/tests/test_world.py`.
