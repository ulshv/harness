# 004. Spec: `error` and `done` events

**Status:** implemented (2026-10-14)
**Implements in:** `docs/history/004.md`

## Problem

When the LLM call fails (provider down, timeout, bad key, rate limit), a tool raises, or the agent hits
`GraphRecursionError`, `/chat/stream` has already sent `200` and the headers. The stream just ends, and
a client can't tell a finished answer from a dead one. A browser `EventSource` also auto-reconnects on
close, which would start the agent again. Batched text that was waiting in the buffer is lost along with
the exception. `/chat/invoke` returns a bare FastAPI 500 with no contract.

## Goals

- Every `/chat/stream` ends with exactly one terminal event: `done` or `error`.
- Text received before a failure still reaches the client, before the `error`.
- Errors are classified into a small set of codes. Internal details (exception text, provider URLs,
  tracebacks) go to logs only, never to the client.
- `/chat/invoke` uses the same events and the same error contract.
- A streaming fake model in tests: the suite currently has none.

## Non-goals

- Usage or cost in `done`. `ChatOpenAI` turns `stream_usage` off for a custom `base_url`, and usage would
  need summing across every LLM call in a run. Goes to the backlog.
- A `retryable` flag, per-tool error events, retries.
- Logging configuration and trace ids (roadmap step 9). For now we only call `logger.exception`; with no handler
  on the root logger, Python's `logging.lastResort` prints the message and traceback to stderr without level or time.
- Client-disconnect handling. `CancelledError` is a `BaseException`, so a dead socket produces no `error` event.
- Interrupts (human-in-the-loop). The root graph swallows `GraphInterrupt` and emits `__interrupt__` in `updates`,
  so an interrupted run currently ends with `done`. A future `interrupt` terminal event belongs to the step that
  adds interrupts.
- Errors raised after this stage (in batching or encoding) still end the stream without a terminal event;
  the guarantee covers the graph and the translator.

## API

### New events

| `type` / SSE event | `data` (SSE, without `type`) | Meaning |
|---|---|---|
| `done` | `{}` | the run finished normally; the client can close the stream |
| `error` | `{"code": "<code>", "message": "<safe text>"}` | the run failed; partial text above is final |

Both events join the `ChatEvent` discriminated union (`DoneEvent`, `ErrorEvent`).

```
event: text
data: {"text":"Hello"}

event: error
data: {"code":"llm_unavailable","message":"The language model provider is unavailable. Try again later."}
```

### Error codes

The code is picked by walking the exception's MRO against one table, so the most specific class wins:

| Exception | `code` | `message` |
|---|---|---|
| `ModelRateLimitError` (429) | `llm_rate_limited` | The language model provider is rate limiting requests. Try again later. |
| `ModelAPIError` (5xx), `ModelConnectionError`, `ModelTimeoutError` | `llm_unavailable` | The language model provider is unavailable. Try again later. |
| `langgraph.errors.GraphRecursionError` | `recursion_limit` | The agent took too many steps without finishing. |
| anything else, including provider 4xx: `ModelAuthenticationError` (401), `ModelPermissionDeniedError`, `ModelInvalidRequestError` (400), `ModelNotFoundError`, `ContextOverflowError` | `internal` | Internal error. |

The classes come from `langchain_core.exceptions` (provider-neutral; langchain-openai raises subclasses that
also inherit the `openai` SDK types). Only conditions a retry can fix are `llm_*`; a 4xx means our key,
model or request is wrong, so a "try again later" message would be a lie. *(Changed after review: the first
version keyed on `openai.APIError`, which put every 4xx under `llm_unavailable`.)*

### `/chat/invoke`

| Outcome | Status | Body |
|---|---|---|
| success | `200` | `{"events": [..., {"type": "done"}]}`, the same events as the stream, merged, including `done` |
| failure | `500` | the `ErrorEvent`: `{"type": "error", "code": "...", "message": "..."}` |

`done` stays in `/invoke` so it remains the exact merged form of the stream. Once `done` carries usage,
`/invoke` gets it for free. Every failure is a single `500`; the `code` field says why. OpenAPI documents
the `500` body via `responses={500: {"model": ErrorEvent}}`.

## Design

A new pipeline stage in `app/api/chat/outcome.py`, placed **before** batching:

```
chat_events → append_error_or_done → batch_text_events → encode (SSE / JSON)
```

```python
async def append_error_or_done(events: AsyncIterable[ChatEvent]) -> AsyncIterator[ChatEvent]:
    try:
        async for event in events:
            yield event
    except Exception as exc:  # not BaseException: a cancelled (disconnected) run emits nothing
        logger.exception("chat run failed")
        yield error_event(exc)
        return
    yield DoneEvent()
```

- **Order matters.** `error` and `done` are non-text events, so batching flushes the buffered text before
  them. The tail is delivered and no extra code is needed.
- **One error path for both routes.** `/invoke` runs the same `append_error_or_done`; if the last event is an
  `ErrorEvent`, it returns that event with status `500`. Catching, logging and classifying live in one place.
- `error_event(exc)`: `_ERRORS: dict[type[BaseException], tuple[code, message]]`, looked up with
  `next((...) for cls in type(exc).__mro__ if cls in _ERRORS)`, falling back to `internal`.

## Code changes

| File | Change |
|---|---|
| `app/api/chat/outcome.py` | new: `append_error_or_done`, `error_event`, the error table |
| `app/agent/graph.py` | *(added during implementation)* `RECURSION_LIMIT = 25` via `compile().with_config(recursion_limit=...)` |
| `app/api/chat/schemas.py` | `DoneEvent`, `ErrorEvent`; added to `ChatEvent` |
| `app/api/chat/chat.py` | both routes add `append_error_or_done`; `/invoke` returns `500` + `ErrorEvent` on failure |
| `tests/conftest.py` | `StreamingFakeModel`: yields scripted text chunks via `_astream`, optionally raises after them |
| `docs/arch/001_chat-request-flow.md` | updated in place: the new stage and terminal events |
| `docs/ROADMAP.md` | remove this item from "Next up"; backlog: usage in `done` |
| `docs/history/004.md` | step log |

## Tests

Expected values are literals.

- `tests/api/chat/test_outcome.py`:
  - a source that ends normally → events plus `DoneEvent()`;
  - a source that raises `RuntimeError("secret")` after one event → that event, then
    `ErrorEvent(code="internal", message="Internal error.")`, with no `"secret"` in it;
  - `error_event`: `ModelRateLimitError` → `llm_rate_limited`; `ModelAPIError`, `ModelConnectionError` and
    `ModelTimeoutError` → `llm_unavailable`; `ModelAuthenticationError` and `ContextOverflowError` → `internal`;
    `GraphRecursionError` → `recursion_limit`.
- `tests/api/test_chat.py`:
  - `/chat/stream` success: the last event is `done` with `data == {}`;
  - `/chat/stream`, streaming fake yields `"Hel"`, `"lo"` and then raises `APIConnectionError`:
    events are `text {"text":"Hello"}`, then `error {"code":"llm_unavailable", ...}`;
  - `/chat/stream`, streaming fake raises before any chunk: a lone `error` with status 200;
  - `/chat/stream`, a fake that always calls a tool → `error {"code":"recursion_limit", ...}`;
  - `/chat/invoke` success: `events[-1] == {"type": "done"}`;
  - `/chat/invoke` failure: `500` and the `ErrorEvent` body;
  - existing tests updated for the trailing `done`.

## How to verify

```bash
make test && make lint
curl -sN localhost:8000/chat/stream -H 'content-type: application/json' -d '{"message":"hi"}' | tail -3
# event: done
# data: {}
# error path without touching the dev loop: a second server with a wrong key (a 401 is ours → internal)
cd services/harness && set -a && . ../../.env && set +a
LLM_API_KEY=wrong uv run uvicorn app.main:app --port 8001 &
curl -sN localhost:8001/chat/stream -H 'content-type: application/json' -d '{"message":"hi"}'
# event: error
# data: {"code":"internal","message":"Internal error."}
curl -s -w '\n%{http_code}\n' localhost:8001/chat/invoke -H 'content-type: application/json' -d '{"message":"hi"}'
# {"type":"error","code":"internal","message":"Internal error."}
# 500
# the server's stderr: "chat run failed" + traceback (OpenAIAuthenticationError: 401)
kill %1
```

## Decisions

| Question | Decision | Why |
|---|---|---|
| Where errors are caught | a pipeline stage `append_error_or_done`, before batching | flushes buffered text before `error`; one place for catch, log and classify |
| `done` payload | empty `{}` | usage needs `stream_usage` plus summing; that's a backlog item |
| Error codes | 4: `llm_unavailable`, `llm_rate_limited`, `recursion_limit`, `internal` | enough to tell "provider", "agent loop" and "our bug" apart; no `retryable` yet |
| What the client sees | code plus a fixed message; details in logs only | exception text can carry provider URLs or request fragments |
| `/invoke` on failure | a single `500` with the `ErrorEvent` body | one status; `code` carries the reason |
| `done` in `/invoke` | kept | `/invoke` stays the merged stream; future usage lands there too |
| Disconnect | no event (`CancelledError` isn't caught) | nobody is listening |
| Error table keys *(changed after review)* | `langchain_core.exceptions` classes; only retryable ones are `llm_*` | provider-neutral; a 4xx with "try again later" would send users into endless retries |
| Explicit recursion limit *(added during implementation)* | `RECURSION_LIMIT = 25` on the compiled graph | LangGraph 1.2.15's default is 10007 supersteps, so `recursion_limit` was practically unreachable and a looping agent could make ~5000 LLM calls |
| Stage name | `append_error_or_done` | says what it does to the stream: passes events through and appends exactly one of the two (`or`, not `and`); catching is implied because `error` is appended, not raised |
