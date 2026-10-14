# 001. Chat request flow: from `curl` to the last token

How one `POST /chat` travels through harness, and the LangGraph concepts it relies on.
State of the code: history step 002 (production layout).

## The path

```
curl POST /chat {"message": "what time is it?"}
 │
 ▼  api/chat/chat.py — HTTP: accept JSON, return SSE
 chat(req, graph)
 │   FastAPI takes the graph from app.state (api/deps.py; built at startup in main.py)
 ▼
 api/chat/stream.py — translator: "what happens in the graph" → "events for the client"
 chat_events() ── graph.astream(...) ──┐
                                       ▼
                 agent/graph.py — the agent itself (ReAct loop)
                 START → [agent] ── LLM: "I want to call current_time"
                            │ tools_condition: any tool_calls?
                            ├─ yes → [tools] runs current_time → back to [agent]
                            └─ no  → END
```

## From stream parts to SSE events

While the graph runs, `astream(stream_mode=["messages", "updates"], version="v2")` yields two kinds of parts:

| What happened in the graph | Stream mode | Handler | SSE event |
|---|---|---|---|
| `agent` finished, the model reply has `tool_calls` | `updates` | `_from_updates` → `_from_message(AIMessage)` | `tool_call` |
| `tools` returned a `ToolMessage` | `updates` | `_from_message(ToolMessage)` | `tool_result` |
| the LLM produced another piece of text | `messages` | `_from_tokens` | `token` |

Subtlety: the final `AIMessage` also arrives in `updates`, but its text has already gone out as tokens.
So only `tool_calls` are taken from it; otherwise the answer would be duplicated.

Dispatch instead of nesting: `_BY_MODE` picks a handler by stream mode, `functools.singledispatch`
picks one by message type. A new event kind is one new function, not one more indentation level.

## LangGraph concepts

1. **State and reducer.** The graph state is `{"messages": [...]}` (`MessagesState`). A node returns
   only *new* messages; the `add_messages` reducer appends them to the list.
2. **A node is a plain function.** It takes the state and returns a partial update.
   `agent` calls the LLM, `ToolNode` executes tools and answers each call with a `ToolMessage(tool_call_id=...)`.
3. **Edges.** `tools → agent` is a normal edge, it always fires. `tools_condition` is a conditional edge:
   it looks at the last message — tool calls → `tools`, none → `END`. Together they form the ReAct loop.
4. **`compile()`** turns the graph description into a runnable (`invoke` / `astream`). One compiled graph
   serves all requests concurrently: each `astream()` call carries its own run state. That's why it lives
   once in `app.state`.
5. **`bind_tools`** only attaches the tools' JSON schemas to the request. The model doesn't call tools,
   it *asks* for a call; the graph executes it.

## Wiring outside the agent

- `main.py`: `create_app(graph_factory)` builds the graph in `lifespan`, once at startup, so a bad `.env`
  fails the boot, not the first request. Tests pass a factory with a fake model.
- `api/deps.py`: `Graph = Annotated[CompiledStateGraph, Depends(get_graph)]`; routes just declare `graph: Graph`.
- `settings.py`: `LLMSettings` reads `LLM_*` env; the key is a `SecretStr`.

## Reading order

1. `agent/graph.py` — the whole agent, ~30 lines.
2. `api/chat/stream.py` — how the graph's progress becomes events.
3. `api/chat/chat.py` and `schemas.py` — HTTP and the event format.
4. `main.py` and `deps.py` — how the graph is created at startup and reaches the endpoint.
5. `tests/api/test_chat.py` — the same flow with a scripted fake model ("call the tool", then "answer").

To watch it live: keep `make up` running, temporarily add `print(part)` inside the `chat_events` loop,
and `curl -N` the endpoint — the raw parts show up in the compose logs.

## Self-check

What happens if you remove the `tools → agent` edge?

<details><summary>Answer</summary>

After `tools` runs, the graph has nowhere to go and the run ends. The client gets `tool_call` and
`tool_result`, but no answer: the model never sees the tool's result. (`compile()` doesn't complain:
a node without outgoing edges is a valid end of the run.)

</details>
