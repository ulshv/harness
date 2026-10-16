# 009. Spec: MCP tools in harness

**Status:** implemented (2026-10-16)
**Implements in:** `docs/history/009.md`

## Problem

The agent has one built-in tool. `testing-wms-mcp` (007) serves eight warehouse tools over MCP, but harness can't
reach them.

Step 3 of 4: API (006) → MCP server (007) → **MCP client in harness** → evals (010). It is also the first slice of
roadmap step 8 (MCP).

## Goals

- Tools from configured MCP servers join the agent's tools at startup, named `<server>_<tool>`.
- A dead MCP server never kills harness: not at startup, not in the middle of a run.
- `tool_result` says whether the tool failed.

## Non-goals

- A server registry in the admin panel, hot reload of tools, credentials (roadmap step 8).
- Warehouse policies in the system prompt (010, so evals can compare with and without).

## API

`ToolResultEvent` gains `status`, so a client can show a failed tool without parsing its text:

```
event: tool_result
data: {"tool_call_id":"call_1","name":"wms_get_stock","content":"Error executing tool get_stock: The stock service failed for SCN-01. Try again later.","status":"error"}
```

`status` is `"success"` or `"error"`, taken from `ToolMessage.status`. The request body doesn't change.

## Design

### Configuration

`MCP_SERVERS`, a JSON object of server name → Streamable HTTP URL, read by pydantic-settings into
`dict[ServerName, HttpUrl]` (a malformed URL or name fails startup). Default `{}`: no MCP tools. compose sets
`MCP_SERVERS={"wms": "http://testing-wms-mcp:8101/mcp"}`; it is dev wiring, not a secret, so it lives in
`compose.yaml`. The server name becomes the tool prefix, and providers accept tool names matching
`^[a-zA-Z0-9_-]{1,64}$`, so `ServerName` is `^[a-z][a-z0-9_]{0,15}$`. An empty `MCP_SERVERS=` isn't `{}` but a
startup error, so `.env.example` only has it commented out.

### Loading tools: `app/agent/mcp.py`

At startup (the lifespan already builds the graph there), via `langchain-mcp-adapters` 0.3.2:

```python
# url as str: an HttpUrl object makes httpx raise inside a task group, which looks like a dead server
connections = {name: {"transport": "streamable_http", "url": str(url)} for name, url in servers.items()}
client = MultiServerMCPClient(connections, tool_name_prefix=True)
for name in connections:            # one server at a time: get_tools() for all of them fails as a whole
    try:
        tools += await client.get_tools(server_name=name)
    except Exception:
        logger.warning("MCP server %s is unavailable; starting without its tools", name, exc_info=True)
```

The tool list is fixed until restart. Each tool call opens its own MCP session (the adapters' default), which suits
a stateless server. The graph factory becomes async, since loading awaits.

### A tool that blows up mid-run

`ToolNode`'s default handler only turns bad-argument errors into a message; anything else propagates and ends the
run with `error: internal`. A dead MCP server mid-run would kill an answer the agent could have given. `ToolNode`
gets a handler that:

- keeps a bad-argument error's own message (the model can fix its arguments);
- for anything else, logs the traceback and returns a fixed text, `"The tool failed to run."`, so no internal URLs
  or exception text reach the model *(changed after review: not "its service is unavailable", which a local tool's
  bug would turn into a false reason for the user)*.

Every connection gets a 15 s timeout for connecting and for each response *(added after review)*: the adapters'
defaults are 30 s and 5 minutes, so a server that accepts TCP but never answers would stall startup (one server at a
time) and every call to it. A timeout is an ordinary exception: skipped at startup, `TOOL_FAILED` mid-run.

Either way the `ToolMessage` gets `status="error"`. MCP tool errors (`is_error: true`) already arrive that way
through the adapters, with the server's message.

## Code changes

| File | Change |
|---|---|
| `pyproject.toml` / `uv.lock` | `langchain-mcp-adapters==0.3.2` (brings `mcp` 1.30.0) |
| `app/settings.py` | `McpSettings` (`MCP_SERVERS`) and its loader |
| `app/agent/mcp.py` | new: load tools per server, prefixed, skipping dead servers |
| `app/agent/graph.py` | `build_graph(model, tools)`; `ToolNode(handle_tool_errors=handle_tool_errors)` |
| `app/agent/errors.py` | `handle_tool_errors` and `TOOL_FAILED` *(during implementation: moved out of `graph.py`)* |
| `app/main.py` | async graph factory: built-in tools + MCP tools |
| `app/api/chat/schemas.py` / `stream.py` | `ToolResultEvent.status` |
| `tests/conftest.py`, `tests/api/test_chat.py`, `tests/api/chat/test_stream.py` | the factory is async and `build_graph` takes tools; expected `tool_result`s gain `status` |
| `compose.yaml` | harness: `MCP_SERVERS`, `depends_on: testing-wms-mcp` healthy |
| `.env.example` | a commented `MCP_SERVERS` line for running harness outside compose |
| `docs/arch/001_chat-request-flow.md` | tools from MCP, `status` |
| `docs/history/009.md` | short step log |

## Tests

Fake models and fake tools only; the live MCP server runs in the smoke test.

- `MCP_SERVERS`: parses `{"wms": "http://x/mcp"}`; a malformed URL fails; a server name `"bad name"` fails; empty
  by default.
- Loading: a fake client where server `a` returns tools and `b` raises → `a`'s tools only, one warning logged.
- A tool raising `RuntimeError("secret")` → `tool_result` with `status: "error"` and the fixed text, no `secret`;
  the run still ends with `done`. A normal tool → `status: "success"`.

## How to verify

```bash
make test && make lint
make up    # restart it: harness now waits for testing-wms-mcp
chat() { curl -sN localhost:8000/chat/stream -H 'content-type: application/json' -d "$1"; }
chat '{"message":"Can we fully reserve order 1003?","thread_id":"wms"}'
# tool_call wms_get_order → tool_result … → tool_call wms_get_stock … → text: short 5 × TAPE-48
docker compose stop testing-wms-mcp
chat '{"message":"How much WRAP-500 is in stock?","thread_id":"wms"}'
# something it hasn't looked up yet, or it may answer from the thread's history (008):
# tool_result with status "error", the agent says the tool failed, the stream ends with done
```

## Decisions

| Question | Decision | Why |
|---|---|---|
| Where servers come from | `MCP_SERVERS` JSON env | the registry is roadmap step 8; config validated at startup now |
| Tool names | `<server>_<tool>` (`tool_name_prefix=True`) | no collisions once a second server arrives; the model sees where a tool comes from |
| When tools load | at startup, fixed until restart | the graph is built there; hot reload belongs to the admin panel |
| Dead server at startup | skip it, warn, start | one integration must not take the agent down |
| Tool failure mid-run | `ToolNode` handler: fixed message, `status="error"`, traceback in the log | the agent can still answer; no internals reach the model |
| `tool_result.status` | added, from `ToolMessage.status` | UI and evals see failures without parsing text |
| System prompt | unchanged | policies come with evals in 010 |
