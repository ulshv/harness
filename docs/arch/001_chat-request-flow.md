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
  append_error_or_done ── api/chat/outcome.py: + done on success, exception → error
  ▼                                             ▼
  batch_events(window=0.05)                     batch_events(window=inf)
  │  api/chat/batching.py: merge adjacent same-kind text/reasoning events
  ▼                                             ▼
  one SSE frame per event                       200 ChatResponse(events=[..., done])
                                                or 500 ErrorEvent
```

Both routes share one pipeline. They differ only in the batching window and in how events are put on
the wire, so a test through `/invoke` checks the same mapping the UI gets through `/stream`.

## Pipeline stages

| Stage | Module | In → out | Knows about |
|---|---|---|---|
| translate | `api/chat/stream.py` | LangGraph `astream` parts → `ChatEvent` | LangGraph, messages |
| terminate | `api/chat/outcome.py` | `ChatEvent` → `ChatEvent` + `done` or `error` | exceptions, error codes |
| batch | `api/chat/batching.py` | `ChatEvent` → `ChatEvent` (fewer text/reasoning events) | time, `TextEvent`, `ReasoningEvent` |
| encode | `api/chat/chat.py` | `ChatEvent` → SSE frame / JSON | HTTP, SSE |

Each stage is an async generator over the previous one, so they compose like pipes and each can be
tested alone. `ChatEvent = TextEvent | ReasoningEvent | ToolCallEvent | ToolResultEvent | DoneEvent | ErrorEvent`
(`api/chat/schemas.py`) is a discriminated union on `type`; OpenAPI shows it as a named `ChatEvent` schema with `discriminator.mapping`.

## Translate: graph parts → events

`graph.astream(inputs, stream_mode=["messages", "updates"], version="v2")` yields two kinds of parts.
`_BY_MODE` picks a handler by stream mode; `functools.singledispatch` (`_from_message`) picks one by
message type.

| What happened in the graph | Stream mode | Handler | Event |
|---|---|---|---|
| the LLM produced another piece of text | `messages` | `_from_tokens` → `_BY_BLOCK["text"]` | `TextEvent` |
| the LLM produced another piece of reasoning | `messages` | `_from_tokens` → `_BY_BLOCK["reasoning"]` | `ReasoningEvent` |
| `agent` finished, the reply has `tool_calls` | `updates` | `_from_updates` → `_from_message(AIMessage)` | `ToolCallEvent` |
| `tools` returned a `ToolMessage` | `updates` | `_from_message(ToolMessage)` | `ToolResultEvent` |

`_from_tokens` reads `msg.content_blocks`, langchain-core's provider-neutral view of a message: text
becomes `{"type": "text"}`, and `additional_kwargs["reasoning_content"]` becomes `{"type": "reasoning"}`
(Anthropic's thinking would map to the same block). `_BY_BLOCK` maps block type to event; other blocks
(`tool_call_chunk`, …), empty strings, and reasoning blocks without text (signature-only; `reasoning` is
`NotRequired` in langchain-core) are skipped. Reasoning is optional: providers don't always send it, so a
client must not wait for it.

Two more subtleties:

- The finished `AIMessage` also arrives in `updates`, but its text has already gone out as `TextEvent`s.
  Only its `tool_calls` are taken, otherwise the answer would be duplicated.
- A node's output in `updates` isn't always `{"messages": [...]}`. It can be `None` (no writes), a list
  (several writes), a single message, or a service key like `__interrupt__`. `_written_messages`
  handles each shape with a flat `match`.

## Terminate: `done` or `error`

`append_error_or_done` passes events through and appends exactly one terminal event: `done` when the
source ends, `error` when it raises. It sits **before** batching. Both terminal events are non-text, so
batched text is flushed before them, and text that arrived before a failure still reaches the client.

| Exception (most specific class wins, via the MRO) | `code` |
|---|---|
| `ModelRateLimitError` (429) | `llm_rate_limited` |
| `ModelAPIError` (5xx), `ModelConnectionError`, `ModelTimeoutError` | `llm_unavailable` |
| `GraphRecursionError` | `recursion_limit` |
| anything else, including provider 4xx (bad key, unknown model, context overflow) | `internal` |

The classes are langchain-core's provider-neutral errors; langchain-openai (and `ChatDeepSeek`, built on it) raises subclasses of them. Only
what a retry can fix is `llm_*`.

The client gets the code and a fixed message. The exception and traceback go to the log only
(`logger.exception("chat run failed")`; with no logging config yet it goes through Python's
`logging.lastResort` to stderr, with no level or time, until roadmap step 9). A cancelled run (client gone) raises `CancelledError`, a
`BaseException`, so nothing is appended. A client should close its `EventSource` on `done` or `error`;
otherwise the browser reconnects and starts the agent again.

Limits of the guarantee: it covers the graph and the translator. An exception in batching or encoding
still ends the stream without a terminal event. An interrupted run (`GraphInterrupt`, future
human-in-the-loop) ends with `done` for now.

## Batch: fewer text and reasoning frames

The LLM streams roughly one token per chunk, so one frame per token is mostly SSE framing: about 32 B of
framing per ~5 B token, 87% of the wire. Reasoning is even chattier. `batch_events(events, window)`
buffers a run of the same kind (`TextEvent` or `ReasoningEvent`) and flushes it:

1. when a chunk arrives and the buffer is at least `window` old (counted from its first chunk);
2. when the kind changes (reasoning → text), before any other event, so order is preserved. Two AI messages never merge because the ReAct graph
   always puts a `tool_call` between them; batching itself only merges contiguous text;
3. at the end of the stream.

| Route | Window | Effect |
|---|---|---|
| `/chat/stream` | `FLUSH_INTERVAL = 0.05` s | ~20 frames/s; a ~120-word answer: ~174 text frames → 11–17; 668 chars of reasoning → 15 frames |
| `/chat/invoke` | `math.inf` | time never flushes: one `reasoning` / `text` event per contiguous block |

There is no timer. If the provider stalls mid-text, the last ≤50 ms of text waits for the next event.
The trade-off and the upgrade path are in [specs/003](../specs/003_chat-stream-invoke-batching.md#trade-off-provider-pauses).

## Encode: wire formats

SSE (`/chat/stream`): the event kind is the `event:` line, and `data` is the event without `type`, as
compact JSON (`raw_data=event.model_dump_json(exclude={"type"})`).

```
event: reasoning
data: {"text":"The user wants the current time; I should call current_time."}

event: tool_call
data: {"id":"call_1","name":"current_time","args":{}}

event: tool_result
data: {"tool_call_id":"call_1","name":"current_time","content":"2026-10-14T16:07:08+00:00"}

event: text
data: {"text":"It's 16:07 UTC on Oct"}

event: done
data: {}
```

On failure the stream ends with
`event: error` / `data: {"code":"llm_unavailable","message":"The language model provider is unavailable. Try again later."}`.

JSON (`/chat/invoke`): the same events with a `type` field, wrapped in an object so fields can be added
later.

```json
{"events": [
  {"type": "tool_call", "id": "call_1", "name": "current_time", "args": {}},
  {"type": "tool_result", "tool_call_id": "call_1", "name": "current_time", "content": "2026-…"},
  {"type": "text", "text": "It's 16:07 UTC on October 14, 2026."},
  {"type": "done"}
]}
```

On failure `/chat/invoke` returns `500` with the `ErrorEvent` as the body:
`{"type": "error", "code": "...", "message": "..."}`. `done` stays in the success body, so `/invoke`
remains the exact merged form of the stream.

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
   `with_config(recursion_limit=RECURSION_LIMIT)` (25 supersteps: 11 tool rounds plus the answer) caps a looping agent.
   LangGraph 1.2's default is 10007.
5. **`bind_tools`** only attaches the tools' JSON schemas to the request. The model *asks* for a call;
   the graph executes it.

## Wiring around the agent

- `main.py`: `create_app(graph_factory)` builds the graph in `lifespan`, once at startup, so a bad
  `.env` fails the boot rather than the first request. Tests pass a factory with a fake model.
- `api/deps.py`: `Graph = Annotated[CompiledStateGraph, Depends(get_graph)]`; routes just declare `graph: Graph`.
- `settings.py`: `LLMSettings` reads `LLM_*` env. The URL is validated, the model is non-empty, and the
  key is a `SecretStr`.
- `agent/llm.py`: `ChatDeepSeek` (langchain-deepseek) pointed at the OpenAI-compatible RouterAI `base_url`. It's a
  `BaseChatOpenAI` subclass on the `openai` SDK. Unlike `ChatOpenAI`, which drops non-standard fields, it lifts
  RouterAI's OpenRouter-style `delta.reasoning` into `additional_kwargs["reasoning_content"]`. Provider errors
  are still `langchain_core.exceptions.Model*Error` subclasses.

## Reading order

1. `agent/graph.py`: the whole agent, about 30 lines.
2. `api/chat/chat.py`: two routes, the pipeline in two lines each.
3. `api/chat/stream.py`: how the graph's progress becomes events.
4. `api/chat/outcome.py`: the terminal events and the error table.
5. `api/chat/batching.py`: one generator, about 20 lines.
6. `api/chat/schemas.py`, `main.py`, `api/deps.py`: contracts and wiring.
7. Tests: `tests/api/test_chat.py` runs the same flow with a scripted fake model ("call the tool", then
   "answer") and a streaming fake that can fail mid-stream; `tests/api/chat/` covers translator, outcome
   and batching alone.

To watch it live, keep `make up` running, temporarily add `print(part)` inside the `chat_events` loop,
and `curl -N` `/chat/stream`. The raw parts show up in the compose logs.

## Self-check

1. What happens if you remove the `tools → agent` edge?
   <details><summary>Answer</summary>After `tools` runs, the graph has nowhere to go and the run ends. The client gets `tool_call` and `tool_result` but no answer, because the model never sees the tool's result. `compile()` doesn't complain: a node without outgoing edges is a valid end of the run (verified on langgraph 1.2.15).</details>
2. Why does `/chat/invoke` fold the event pipeline instead of calling `graph.ainvoke()` and reading the final state?
   <details><summary>Answer</summary>To keep one source of truth. With `ainvoke`, `/invoke` would bypass the translator and the streaming request to the provider, and a test through `/invoke` could pass while `/stream` is broken. Folding the same pipeline with `window=inf` makes `/invoke` the exact merged form of what `/stream` sends.</details>
3. Why does `append_error_or_done` sit before `batch_events` and not after it?
   <details><summary>Answer</summary>When the source raises, batching would propagate the exception and drop its buffered text. Placed before batching, the exception becomes an `ErrorEvent`, a non-text event, and batching flushes the buffered text before passing it on. The partial answer reaches the client, then `error`.</details>
