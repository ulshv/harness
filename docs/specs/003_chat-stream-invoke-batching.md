# 003. Spec: `/chat/stream` + `/chat/invoke`, text batching

**Status:** implemented (2026-10-14)
**Implements in:** `docs/history/003.md`

## Problem

1. **Every token is its own SSE frame.** Measured on DeepSeek v4.1 flash via RouterAI, for an answer of
   about 120 words: 174 token frames at 160 frames/s, with an average token of 4.7 B and 32 B of SSE
   framing per frame (`event: token\ndata: {"text":""}\n\n`). That's 87% of the bytes on the wire. Each
   frame is also a separate TCP segment (asyncio sets `TCP_NODELAY`), plus TLS and HTTP/2 framing in
   prod. The frontend would re-render 160 times a second.
2. **A single `/chat` route only streams.** Tests and scripts that want the whole answer have to parse SSE.

## Goals

- Cut token frames about 10× without adding noticeable latency.
- Add a non-streaming route that returns the whole run as one JSON, built on the **same** event pipeline
  as the stream, so a test through it checks the same mapping the UI gets.
- Keep the code small: no tasks, queues or timers.

## Non-goals

- Guaranteed flush latency while the provider is silent (see [Trade-off](#trade-off-provider-pauses)).
- `error` / `done` events and mid-stream error handling (next step).
- Reasoning tokens, threads/memory, client-disconnect handling. On disconnect, the inner generators
  (`chat_events`, `astream`) are closed by asyncio's async-generator finalizer one loop tick later, not by
  an explicit `aclose()`.

## API

`POST /chat` is **removed**; there are no clients yet.

| Route | Request | Response |
|---|---|---|
| `POST /chat/stream` | `{"message": str}` (non-empty) | `text/event-stream`, batched events |
| `POST /chat/invoke` | `{"message": str}` (non-empty) | `application/json`, `ChatResponse` |

The names mirror LangChain's `Runnable.stream()` / `.invoke()`.

### Events

Each event gets a `type` field (`Literal`), replacing the `event: ClassVar`. The field is needed in JSON
(`/invoke`), where nothing else carries the event kind. In SSE the `event:` line already carries it, so
`type` is **not** duplicated into `data`: the route sends `event=event.type, raw_data=event.model_dump_json(exclude={"type"})`.
(`data=<dict>` would go through `json.dumps` and add spaces after `:` and `,`; a model or `raw_data` keeps pydantic's compact JSON.)

```
event: tool_call
data: {"id":"call_1","name":"current_time","args":{}}

event: tool_result
data: {"tool_call_id":"call_1","name":"current_time","content":"2026-10-14T16:07:08+00:00"}

event: text
data: {"text":"It's 16:07 UTC on Oct"}

event: text
data: {"text":"ober 14, 2026."}
```

`type ChatEvent = Annotated[TextEvent | ToolCallEvent | ToolResultEvent, Field(discriminator="type")]`. The
discriminator puts a named `ChatEvent` schema with `oneOf` and `discriminator.mapping` into OpenAPI, and
`json_schema_serialization_defaults_required` marks `type` as required. A generated TS client (step 2)
can then narrow the union by `type`. *(Changed after review: the first draft had no discriminator, and
OpenAPI showed a plain `anyOf` with an optional `type`.)*

### `/chat/invoke` response

```json
{
  "events": [
    {"type": "tool_call", "id": "call_1", "name": "current_time", "args": {}},
    {"type": "tool_result", "tool_call_id": "call_1", "name": "current_time", "content": "2026-…"},
    {"type": "text", "text": "It's 16:07 UTC on October 14, 2026."}
  ]
}
```

These are the same events as the stream, with text merged into one `text` event per contiguous AI text block.
The final answer is `events[-1].text`. A wrapper object rather than a bare array, so fields like `usage`
can be added later without breaking clients.

Failures: an LLM or tool error surfaces as FastAPI's default 500. A typed error body is out of scope.

## Batching

New module `app/api/chat/batching.py`, a transformer from `ChatEvent` to `ChatEvent` that knows nothing
about HTTP:

```python
# ~20 frames/s still reads as smooth typing; ~10x fewer frames than one per LLM token (measured on DeepSeek)
TEXT_FLUSH_INTERVAL = 0.05

async def batch_text_events(events: AsyncIterable[ChatEvent], window: float = TEXT_FLUSH_INTERVAL) -> AsyncIterator[ChatEvent]
```

Rules:

1. Adjacent `TextEvent`s are concatenated into a buffer.
2. When a `TextEvent` arrives and the buffer is at least `window` seconds old, counted from its first chunk, the
   buffer goes out as one `TextEvent`.
3. Any non-text event flushes the buffer first and is then passed through, so order is preserved.
4. The end of the source flushes the buffer.

`window=0` means one frame per LLM token (debugging). `window=math.inf` means time never flushes, which is
exactly the `/invoke` merge.

Expected effect from the measured gap distribution: 50 ms gives about 18 frames instead of 174 (9.7×),
and about 1.4 KB on the wire instead of 6.4 KB.

### Trade-off: provider pauses

There is no timer. The generator only runs when the next event arrives. If the provider goes silent
mid-text, the tail that arrived within the last `window` (usually a couple of words) waits for the next
token, event, or the end of the stream. Without batching the stream would be stalled anyway, so only that
tail is late. If the source then raises, the tail is lost along with the broken answer.

The longest mid-answer gap measured was 73 ms. DeepSeek's long silence (about 11.6 s) happens before the
first token, when the buffer is empty.

**Tool-call arguments are the same case, but the provider isn't silent.** When the model writes text and
then calls a tool, the argument chunks (`tool_call_chunks`) carry no text, so the translator emits nothing
for them. The text tail waits until the `tool_call` event, which comes after the whole argument JSON is
generated. With `current_time` (no args) this is invisible. With large args (deepagents' `write_file`,
step 4) it could take seconds.

**Upgrade trigger:** visible mid-text stalls in practice: tools with large arguments (step 4) or streamed reasoning. The upgrade
stays inside `batch_text_events`: one outstanding `anext()` task plus `asyncio.wait(timeout=...)`, which,
unlike `wait_for`, doesn't cancel it, plus `finally: cancel()`. Routes and tests don't change.

## Code changes

| File | Change |
|---|---|
| `app/api/chat/batching.py` | new: `TEXT_FLUSH_INTERVAL`, `batch_text_events` |
| `app/api/chat/schemas.py` | `event: ClassVar` → `type: Literal[...]`; `ChatResponse(events: list[ChatEvent])` |
| `app/api/chat/stream.py` | `chat_events(graph, message: str)` builds the `HumanMessage` itself |
| `app/api/chat/chat.py` | `stream()` and `invoke()` routes, each about 3 lines (SSE `data` excludes `type`); `/chat` removed |
| `docs/arch/001_chat-request-flow.md` | updated in place: batching stage, two routes (arch docs are AS-IS) |
| `docs/history/003.md` | step log |

## Tests

Expected values are literals.

- `tests/api/chat/test_batching.py` (new):
  - time window with a patched `monotonic` (`0, .03, .06, .07`): `a b c d` → `["abc", "d"]`;
  - `window=0`: `[TextEvent("a"), TextEvent("b")]` → unchanged;
  - `window=inf`: `[TextEvent("a"), TextEvent("b"), ToolCallEvent(c1), TextEvent("c")]` → `[TextEvent("ab"), ToolCallEvent(c1), TextEvent("c")]`.
- `tests/api/test_chat.py`, moved onto the new routes:
  - `/chat/stream` with tool call then answer: SSE event names `tool_call`, `tool_result`, `text`; `data` has no `type` key;
  - `/chat/invoke` with the same script: `resp.json() == {"events": [...]}` with literal events;
  - `/chat/invoke` with a plain answer: one `text` event;
  - an empty message gives 422 on both routes;
  - `POST /chat` gives 404 (route removed);
  - `/openapi.json`: `ChatEvent` has `discriminator.mapping` for the three types; `type` is required.

## How to verify

```bash
make test && make lint
make up   # or reuse the running loop
Q='{"message":"Explain in about 120 words why SSE is good for LLM streaming."}'
curl -sN localhost:8000/chat/stream -H 'content-type: application/json' -d "$Q" | grep -c '^event: text'
# ≈ 15–25 expected; 11 on the live run (was ≈ 170)
curl -s localhost:8000/chat/invoke -H 'content-type: application/json' -d '{"message":"what time is it in UTC?"}' | jq
# {"events": [tool_call, tool_result, one text event with the whole answer]}
# set TEXT_FLUSH_INTERVAL = 0 → frame count is back to ≈ 170
```

`/docs` shows both routes. `/chat/invoke` has the `ChatResponse` schema with the three event types.

## Decisions

| Question | Decision | Why |
|---|---|---|
| Name of the non-streaming route | `invoke` (not `wait` / `full`) | mirrors `Runnable.invoke()` / `.stream()` |
| How `/invoke` is built | fold the same event pipeline (`window=inf`), not `graph.ainvoke` | one source of truth; tests check what the stream sends |
| Batching approach | flush-on-arrival window, no timer | minimal code; the pause cost is a couple of words, rare |
| Window | 50 ms constant, not config | ~20 fps, ~10× fewer frames; move to config when it needs tuning without a release |
| `type` in SSE `data` | not duplicated, only the `event:` line | the SSE event name already carries it; `type` lives in JSON (`/invoke`) only |
| Old `POST /chat` | removed | no clients |
| Event name for text | `text` (renamed from `token` after implementation) | after batching, an event carries a chunk or a whole block of text, not a token |
| Python names | `TextEvent` / `ToolCallEvent` / `ToolResultEvent`, `batch_text_events` | symmetric; no clash with LangChain's `ToolCall`; the function batches exactly `TextEvent`s |
