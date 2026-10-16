# 008. Spec: conversations by `thread_id`

**Status:** implemented (2026-10-16)
**Implements in:** `docs/history/008.md`

## Problem

Every request starts from scratch: the agent forgets the previous message, so a dialog ("is order 1003 ready?" →
"why not?") is impossible. Real threads (per user, in Postgres, a chats/threads API) are roadmap step 3; this is
its first slice: the client names a thread, and harness remembers it in memory.

## Goals

- A request with a `thread_id` continues that conversation; without one it is a single turn, as today.

## Non-goals

- A chats/threads API (list, rename, delete), threads per user, Postgres (roadmap step 3).
- Returning a server-generated id: a client that wants a dialog picks its own.
- Repairing a thread broken by an interrupted run (see Known limits).

## API

`ChatRequest` gains an optional `thread_id`, for both `/chat/stream` and `/chat/invoke`:

```json
{"message": "Which of its products is short?", "thread_id": "sergey-1"}
```

- 1–64 characters of `[A-Za-z0-9_-]`; anything else, `null` included, is a 422.
- Omitted: a fresh thread per request (a random UUID), so `{"message": "hi"}` behaves as before. The UUID is the
  field's `default_factory`, so OpenAPI shows a plain optional string and both routes get it for free *(changed
  after review: not `ThreadId | None`, which adds a `null` branch to the schema)*.
- Events don't change.

## Design

### Threads

`build_graph` compiles with `InMemorySaver()`, a checkpointer: after each step it saves the graph state under a
`thread_id`, and the next run on that thread starts from it. `MessagesState`'s reducer appends the new
`HumanMessage` to the saved history. The router passes the request's `thread_id` to `chat_events`,
which puts it into the run config (a checkpointed graph refuses to run without one).

What gets saved is what nodes return: the human message, the model's replies, the tool results. The system prompt is
prepended to the LLM call and never stored, so it isn't duplicated per turn, and a changed prompt applies to an
existing conversation on its next turn. Streaming doesn't change: on the second turn `updates` and `messages`
carry only the new run, not the history.

### Known limits

By design for now:

- **An interrupted run breaks its thread.** A run that stops between the model's tool call and the tool's answer
  (hitting `recursion_limit`, a client disconnect mid-tool, two requests on one thread at once) leaves an
  `AIMessage` with `tool_calls` and no `ToolMessage` in the saved state. The next message is appended after it, and
  providers reject such a history (every tool call must be answered right after it), so every later request on that
  thread ends with `error: internal`. The client starts a new `thread_id`. Neither the provider APIs, LangGraph nor
  LangChain's `create_agent` repair this; deepagents does, with `PatchToolCallsMiddleware`, which
  `create_deep_agent` enables by default, so moving to deepagents (roadmap step 4) fixes it without our own code
  *(changed after review: a repair of our own was specced, then dropped as too much code for a rare case now that a
  broken thread affects one conversation, not everybody)*.

- Anyone who knows a `thread_id` can read and continue that conversation. Fine while there is no auth; threads get
  an owner with auth (roadmap step 5).
- Threads live in process memory: a restart or any hot reload of `app/` forgets them, and every request without a
  `thread_id` leaves a thread nobody reads again, so memory grows until a restart. `InMemorySaver` keeps every
  checkpoint, a full copy of the history per step, so a thread's footprint grows roughly with the square of its
  turns *(noted after review)*. Postgres with a TTL is roadmap step 3; deleting anonymous threads after their run
  is a small fix if it starts to matter (evals in 010 send many requests).
- Two requests on one thread at the same time: the later run starts from the other's unfinished state, and the
  thread keeps only one run's answer (last writer wins).
- A thread's history grows without bound.

## Code changes

| File | Change |
|---|---|
| `app/api/chat/schemas.py` | `ChatRequest.thread_id: ThreadId` with a UUID `default_factory` |
| `app/agent/graph.py` | `InMemorySaver` created inside `build_graph`, so each test app gets its own |
| `app/api/chat/stream.py` / `chat.py` | `thread_id` from the request into the run config |
| `tests/conftest.py` | a fake model that records its inputs |
| `docs/arch/001_chat-request-flow.md` | the checkpointer and threads |
| `docs/ROADMAP.md` | backlog: threads with an owner, Postgres + TTL (roadmap steps 3, 5); interrupted runs break their thread (fixed by deepagents, step 4) |
| `docs/history/008.md` | short step log |

## Tests

Fake models only. A recording fake (a `FakeToolModel` subclass that keeps each input) shows what the model was sent;
`app.state.graph.get_state({"configurable": {"thread_id": "t1"}})` shows what was saved.

- Two `/chat/invoke` calls with `thread_id: "t1"`: the second call's model input contains the first exchange, and
  the state for `t1` holds four messages.
- Two calls without `thread_id`: the second call's model input has only its own message.
- `thread_id: "bad id!"` → 422.

## How to verify

```bash
make test && make lint
chat() { curl -sN localhost:8000/chat/stream -H 'content-type: application/json' -d "$1"; }
chat '{"message":"My name is Sergey.","thread_id":"demo"}'
chat '{"message":"What is my name?","thread_id":"demo"}'   # text: …Sergey…
chat '{"message":"What is my name?"}'                      # a fresh thread: it doesn't know
```

## Decisions

| Question | Decision | Why |
|---|---|---|
| Who names the thread | the client, an optional `thread_id` in the request | dialogs now, and evals (010) get a clean thread per case for free; a chats API comes with roadmap step 3 |
| No `thread_id` | a fresh UUID per request | `{"message": …}` keeps working as a single turn; the alternatives were a required field (breaks every example) or a shared default thread (one conversation for everybody) |
| Thread id format | 1–64 of `[A-Za-z0-9_-]` | safe to log and to use as a key later; anything else is a 422 |
| Storage | `InMemorySaver` | the smallest change; Postgres with a TTL is roadmap step 3 |
| Interrupted runs *(changed after review)* | not repaired: the thread breaks, the client starts a new one | rare, and it hits one conversation now; deepagents (step 4) repairs it out of the box. The dropped repair needed positional matching and `invalid_tool_calls` handling to be correct |
