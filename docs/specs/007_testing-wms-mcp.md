# 007. Spec: `testing-wms-mcp`, an MCP server over the warehouse API

**Status:** implemented (2026-10-15)
**Implements in:** `docs/history/007.md`

## Problem

`testing-wms` (006) is a REST API. An agent doesn't call REST APIs; it calls tools. MCP is the standard way to hand
tools to any agent, and in real life an MCP server is usually a thin adapter over someone else's API. This step
builds that adapter, as the example of "MCP for any API" that `testing-crm-mcp` and others can copy later.

Step 2 of 4: 006 API → **007 MCP server** → 008 MCP client in harness → 009 evals.

## Goals

- An MCP server with one tool per warehouse operation, described for a model: what it does, what the arguments
  mean, what can come back.
- API errors reach the model as readable tool errors, not crashes.
- Reachable from other compose services (harness in 008) over Streamable HTTP.
- Proof before 008 that harness's MCP client generation can talk to it (see "Two SDK generations").

## Non-goals

- Connecting harness (008), the agent prompt and evals (009).
- `/_reset`, `/_state`: the eval runner calls the API directly; the agent never needs them.
- Auth, resources, prompts, elicitation.

## Two SDK generations

`mcp` 2.x (current: 2.3.0) is a rewrite: `FastMCP` became `MCPServer`, there's a first-class `Client`, and it
speaks protocol revision **2026-07-28**, which drops the `initialize` handshake and sessions: every request is
self-contained. It also still serves 2025-era clients through `initialize`, from the same app, with no flag.

harness will use `langchain-mcp-adapters` 0.3.2 (the latest), which requires `mcp<2`. So: **the server is on
`mcp` 2.3.0, harness stays on 1.x** until the adapters move (backlog). A smoke check in this step connects to the
server with the adapters themselves, so 008 starts from a known-good pair.

## Tools

The tools mirror the API one to one: it is already small and task-shaped. The curation is in names, argument
docs and errors. Descriptions state **facts only**; policies ("don't reserve partially without asking") belong to
the agent's prompt in 009, otherwise evals would measure the tool description instead of the agent.

| Tool | Arguments | API | Description, in short |
|---|---|---|---|
| `search_products` | `query: str` | `GET /products?q=` | products whose SKU or name contains `query` (case-insensitive substring) |
| `list_locations` | — | `GET /locations` | every location and what it holds, empty ones included |
| `get_stock` | `sku: str` | `GET /stock/{sku}` | on hand, reserved and available, in total and per location |
| `list_orders` | `status: OrderStatus \| None` | `GET /orders?status=` | orders, optionally by status |
| `get_order` | `order_id: int` | `GET /orders/{id}` | an order with its lines and where each line is reserved |
| `reserve_order` | `order_id: int` | `POST /orders/{id}/reserve` | reserves available stock; if stock is short it reserves what it can, the order becomes `partially_reserved` and `shortages` says what's missing; if nothing is available it fails and nothing changes; an already reserved order is a no-op |
| `cancel_order` | `order_id: int` | `POST /orders/{id}/cancel` | cancels and releases its reservations; shipped or cancelled orders can't be cancelled |
| `move_stock` | `sku, from_location, to_location: str`, `qty: PositiveInt` | `POST /moves` | moves available (not reserved) stock between locations |

A tool returns the API's response body as a `str`: exactly the JSON the API sent, in one text block. Models read
JSON well, and typed output schemas would duplicate every API model. *(Changed after review: returning the parsed
`dict`/`list` breaks for lists. The SDK turns a list into one content block per item, so an empty search result
becomes `content=[]`, and `langchain-mcp-adapters` hands the model only `content`.)*

## Errors

| What happened | Tool raises | The model sees |
|---|---|---|
| API answered 4xx/5xx | `ToolError(detail)`: `detail` when it is a string, otherwise the raw body (a 422's `detail` is a list; a crash 500 is plain text) | `is_error: true`, `"Error executing tool move_stock: Only 80 of GLV-NIT-L can move from A-01-02; …"` |
| API unreachable or timed out | `ToolError("The warehouse API is unreachable. Try again later.")` | the same shape |
| anything else (our bug) | not caught | `is_error: true` with a generic message; the traceback goes to the server log |

`ToolError` is how a v2 tool talks to the model; any other exception is sanitized. `MCPError` (a protocol error,
no result at all) isn't used: every warehouse failure is something the model can react to.

## Design

- `services/testing-wms-mcp/`, the same image and dev loop as the other services:
  - `app/server.py`: `MCPServer("testing-wms")` and the eight tools;
  - `app/wms.py`: one function that calls the API and turns failures into `ToolError`;
  - `app/settings.py`: `WMS_URL` (pydantic-settings, fails at startup if missing);
  - `app/main.py`: `create_app()` returns `server.streamable_http_app(...)` plus `GET /health` via `custom_route`;
    uvicorn runs it with `--factory` and `--reload`. *(Changed during implementation: no module-level `app`, so
    importing the module reads no env and tests need no `WMS_URL`.)*
- **Transport:** Streamable HTTP at `/mcp`, `stateless_http=True`: no sessions for 2025-era clients either. Each
  call is one request to the API; there is nothing to keep between calls.
- **Host allowlist.** Without `transport_security`, `streamable_http_app()` assumes localhost and rejects any other
  `Host` with **421 Invalid Host header**, which a client only reports as a generic transport error. harness will
  call `http://testing-wms-mcp:8101/mcp`, so the app allowlists hosts `testing-wms-mcp:*`, `localhost:*`,
  `127.0.0.1:*`. An explicit setting also empties `allowed_origins`, and any request with an `Origin` header (only
  browsers send one) gets 403, so origins `http://localhost:*` and `http://127.0.0.1:*` are listed too. The
  Inspector is used in its default proxy mode.
- `custom_route("/health")` is registered before `streamable_http_app()` is called: the routes are copied at that
  call. `/health` isn't behind the Host check.
- **HTTP client:** `httpx2` (the SDK already depends on it), a new `AsyncClient` per call with a 10 s timeout
  constant. A pooled client would need a lifespan hook; for a test double one connection per call is fine. The
  seam for tests is a `Wms(base_url, transport)` object passed to `build_server(wms)`; the tools close over it, and
  tests pass `httpx2.MockTransport`. *(Changed during implementation: an injected object instead of a module-level
  global that tests patch.)*
- `app/main.py` has a `create_app()` factory: a session manager can `run()` only once, so each HTTP-level test
  builds its own app.
- Compose: `testing-wms-mcp` on `127.0.0.1:8101`, `WMS_URL=http://testing-wms:8100`, `depends_on` testing-wms
  healthy, its own healthcheck on `/health` (harness will depend on it in 008).

## Code changes

| File | Change |
|---|---|
| `services/testing-wms-mcp/**` | new service: app, tests, `Dockerfile`, `pyproject.toml` (`mcp==2.3.0`, `httpx2==2.13.1`, `pydantic-settings==2.16.0`, `uvicorn[standard]==0.54.0`; dev: pytest, ruff, basedpyright as in harness), `uv.lock` |
| `compose.yaml` | `testing-wms-mcp` service |
| `Makefile` | `testing-wms-mcp` in `SERVICES` |
| `CLAUDE.md` | pinned `mcp` 2.3.0 for the server; `langchain-mcp-adapters` row notes `mcp<2` |
| `docs/ROADMAP.md` | backlog: move harness to `mcp` 2 when the adapters support it |
| `docs/SETUP.md` | the MCP Inspector command |
| `docs/history/007.md` | short step log |

## Tests

In memory: `Client(server)` from the SDK talks to the server object with no transport (`@pytest.mark.anyio` plus an
`anyio_backend` fixture; the plugin ships with anyio). The API is replaced by `httpx2.MockTransport` returning
literal responses.

- `list_tools` returns the eight names, and `reserve_order`'s input schema requires an integer `order_id`.
- A successful call returns the API body as one text block (`get_order` → the literal order); an empty
  `search_products` result is the text `[]`, not empty content.
- API 409 → `is_error` and the `detail` text in `content`; API 503 → the same; a 500 with a plain-text body →
  that text; connection error → the "unreachable" message. `move_stock` with `qty: 0` is rejected by the SDK
  before any API call.
- The Host allowlist, over HTTP with `with TestClient(create_app())` (the lifespan starts the session manager) and
  `Content-Type: application/json` (otherwise a 400 fires before the Host check): `Host: testing-wms-mcp:8101`
  passes, `Host: evil.example` gets 421.

## How to verify

```bash
make test && make lint
make up                    # restart: compose watch doesn't pick up new services
npx @modelcontextprotocol/inspector   # transport "Streamable HTTP", URL http://localhost:8101/mcp
# list tools → 8 with descriptions; call reserve_order {"order_id": 1003} → partially_reserved, shortages TAPE-48: 5
# call get_stock {"sku": "SCN-01"} → is_error with "The stock service failed for SCN-01. Try again later."
```

Generation check (scratch environment, not committed): `langchain-mcp-adapters` 0.3.2 with `mcp` 1.x loads the
eight tools from `http://localhost:8101/mcp` and calls `get_order`.

## Decisions

| Question | Decision | Why |
|---|---|---|
| SDK | official `mcp` 2.3.0, `MCPServer` | the current stable line; a new server on the removed v1 API would be legacy on day one |
| harness side | stays on `mcp` 1.x via `langchain-mcp-adapters` | the adapters require `mcp<2`; a v2 server serves 2025-era clients too |
| Transport | Streamable HTTP, stateless | stdio can't cross containers; SSE is deprecated; nothing to keep between calls |
| Host allowlist | explicit `transport_security` | the localhost default answers 421 to every call from another container |
| Tool set | one per API operation | the API is already task-shaped; every tool has a trap that needs it |
| Descriptions | facts, no policies | evals must measure the agent, not the tool text |
| Output *(changed after review)* | the API body as `str` | one text block with the exact JSON; parsed lists would split into blocks and vanish when empty |
| Errors | `ToolError` with the API's `detail` | the model reads it and can recover; other exceptions get sanitized |
| HTTP client | `httpx2`, new client per call | already an SDK dependency; no lifespan plumbing for a test double |
