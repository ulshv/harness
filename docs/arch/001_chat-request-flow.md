# 001. Chat request flow: from HTTP to the agent graph and back

How a chat request travels through harness today, and the LangGraph concepts it relies on.
This doc describes the system **as it is**; it is updated together with the code.

## The path

```
POST /chat/stream                             POST /chat/invoke
  │                                             │
  ▼  api/chat/chat.py — HTTP (router prefix /chat)
  │  FastAPI takes the compiled graph from app.state (api/deps.py; built at startup in main.py)
  ▼                                             ▼
  chat_events(graph, message)  ── api/chat/stream.py: graph parts → ChatEvent
  │         │
  │         └── graph.astream(...) ──┐
  │                                  ▼
  │            agent/graph.py — the agent (ReAct loop)
  │            START → [agent] ── LLM: "I want to call current_time"
  │                       │ tools_condition: any tool_calls?
  │                       ├─ yes → [tools] runs the tool → back to [agent]
  │                       └─ no  → END
  ▼                                             ▼
  batch_text_events(window=0.05)                batch_text_events(window=inf)
  │  api/chat/batching.py: merge adjacent TextEvents
  ▼                                             ▼
  one SSE frame per event                       ChatResponse(events=[...]) → one JSON
```

Both routes share one pipeline. They differ only in the batching window and in how events are put on
the wire, so a test through `/invoke` checks the same mapping the UI gets through `/stream`.

## Pipeline stages

| Stage | Module | In → out | Knows about |
|---|---|---|---|
| translate | `api/chat/stream.py` | LangGraph `astream` parts → `ChatEvent` | LangGraph, messages |
| batch | `api/chat/batching.py` | `ChatEvent` → `ChatEvent` (fewer `TextEvent`s) | time, `TextEvent` |
| encode | `api/chat/chat.py` | `ChatEvent` → SSE frame / JSON | HTTP, SSE |

Each stage is an async generator over the previous one, so they compose like pipes and each can be
tested alone. `ChatEvent = TextEvent | ToolCallEvent | ToolResultEvent` (`api/chat/schemas.py`) is a
discriminated union on `type`; OpenAPI shows it as a named `ChatEvent` schema with `discriminator.mapping`.

## Translate: graph parts → events

`graph.astream(inputs, stream_mode=["messages", "updates"], version="v2")` yields two kinds of parts.
`_BY_MODE` picks a handler by stream mode; `functools.singledispatch` (`_from_message`) picks one by
message type.

| What happened in the graph | Stream mode | Handler | Event |
|---|---|---|---|
| the LLM produced another piece of text | `messages` | `_from_tokens` | `TextEvent` |
| `agent` finished, the reply has `tool_calls` | `updates` | `_from_updates` → `_from_message(AIMessage)` | `ToolCallEvent` |
| `tools` returned a `ToolMessage` | `updates` | `_from_message(ToolMessage)` | `ToolResultEvent` |

Two subtleties:

- The finished `AIMessage` also arrives in `updates`, but its text has already gone out as `TextEvent`s.
  Only its `tool_calls` are taken, otherwise the answer would be duplicated.
- A node's output in `updates` isn't always `{"messages": [...]}`. It can be `None` (no writes), a list
  (several writes), a single message, or a service key like `__interrupt__`. `_written_messages`
  handles each shape with a flat `match`.

## Batch: fewer text frames

The LLM streams roughly one token per chunk, so one frame per token is mostly SSE framing: about 32 B of
framing per ~5 B token, 87% of the wire. `batch_text_events(events, window)` buffers text and flushes it:

1. when a `TextEvent` arrives and the buffer is at least `window` old (counted from its first chunk);
2. before any non-text event, so order is preserved. Two AI messages never merge because the ReAct graph
   always puts a `tool_call` between them; batching itself only merges contiguous text;
3. at the end of the stream.

| Route | Window | Effect |
|---|---|---|
| `/chat/stream` | `TEXT_FLUSH_INTERVAL = 0.05` s | ~20 frames/s; a ~120-word answer: ~174 frames → 11 |
| `/chat/invoke` | `math.inf` | time never flushes: one `text` event per contiguous AI text block |

There is no timer. If the provider stalls mid-text, the last ≤50 ms of text waits for the next event.
The trade-off and the upgrade path are in [specs/003](../specs/003_chat-stream-invoke-batching.md#trade-off-provider-pauses).

## Encode: wire formats

SSE (`/chat/stream`): the event kind is the `event:` line, and `data` is the event without `type`, as
compact JSON (`raw_data=event.model_dump_json(exclude={"type"})`).

```
event: tool_call
data: {"id":"call_1","name":"current_time","args":{}}

event: tool_result
data: {"tool_call_id":"call_1","name":"current_time","content":"2026-10-14T16:07:08+00:00"}

event: text
data: {"text":"It's 16:07 UTC on Oct"}
```

JSON (`/chat/invoke`): the same events with a `type` field, wrapped in an object so fields can be added
later.

```json
{"events": [
  {"type": "tool_call", "id": "call_1", "name": "current_time", "args": {}},
  {"type": "tool_result", "tool_call_id": "call_1", "name": "current_time", "content": "2026-…"},
  {"type": "text", "text": "It's 16:07 UTC on October 14, 2026."}
]}
```

`id` / `tool_call_id` let a client pair a call with its result.

## The agent graph (LangGraph concepts)

1. **State and reducer.** The graph state is `{"messages": [...]}` (`MessagesState`). A node returns
   only *new* messages, and the `add_messages` reducer appends them to the list.
2. **A node is a plain function.** It takes the state and returns a partial update. `agent` calls the
   LLM (the system prompt is prepended per call, not stored in state). `ToolNode` executes every tool
   call of the last AI message and answers each with a `ToolMessage(tool_call_id=...)`.
3. **Edges.** `tools → agent` is a normal edge and always fires. `tools_condition` is a conditional edge:
   tool calls → `tools`, none → `END`. Together they form the ReAct loop.
4. **`compile()`** turns the description into a runnable (`invoke` / `astream`). One compiled graph
   serves all requests concurrently, because each `astream()` call carries its own run state. That's why
   it lives once in `app.state`. There is no checkpointer yet, so no memory between requests.
5. **`bind_tools`** only attaches the tools' JSON schemas to the request. The model *asks* for a call;
   the graph executes it.

## Wiring around the agent

- `main.py`: `create_app(graph_factory)` builds the graph in `lifespan`, once at startup, so a bad
  `.env` fails the boot rather than the first request. Tests pass a factory with a fake model.
- `api/deps.py`: `Graph = Annotated[CompiledStateGraph, Depends(get_graph)]`; routes just declare `graph: Graph`.
- `settings.py`: `LLMSettings` reads `LLM_*` env. The URL is validated, the model is non-empty, and the
  key is a `SecretStr`.
- `agent/llm.py`: `ChatOpenAI` pointed at the OpenAI-compatible RouterAI `base_url`.

## Reading order

1. `agent/graph.py`: the whole agent, about 30 lines.
2. `api/chat/chat.py`: two routes, the pipeline in two lines each.
3. `api/chat/stream.py`: how the graph's progress becomes events.
4. `api/chat/batching.py`: one generator, about 15 lines.
5. `api/chat/schemas.py`, `main.py`, `api/deps.py`: contracts and wiring.
6. Tests: `tests/api/test_chat.py` runs the same flow with a scripted fake model ("call the tool", then
   "answer"); `tests/api/chat/` covers the translator and batching alone.

To watch it live, keep `make up` running, temporarily add `print(part)` inside the `chat_events` loop,
and `curl -N` `/chat/stream`. The raw parts show up in the compose logs.

## Self-check

1. What happens if you remove the `tools → agent` edge?
   <details><summary>Answer</summary>After `tools` runs, the graph has nowhere to go and the run ends. The client gets `tool_call` and `tool_result` but no answer, because the model never sees the tool's result. `compile()` doesn't complain: a node without outgoing edges is a valid end of the run (verified on langgraph 1.2.15).</details>
2. Why does `/chat/invoke` fold the event pipeline instead of calling `graph.ainvoke()` and reading the final state?
   <details><summary>Answer</summary>To keep one source of truth. With `ainvoke`, `/invoke` would bypass the translator and the streaming request to the provider, and a test through `/invoke` could pass while `/stream` is broken. Folding the same pipeline with `window=inf` makes `/invoke` the exact merged form of what `/stream` sends.</details>
