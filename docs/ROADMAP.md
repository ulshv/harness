# Roadmap: what's next

Everything about what's next: the product steps, the proposed "next up" list, and the backlog. I choose the order.

How this file is kept:

- When a review or debrief defers something, it goes into the backlog with why, when it starts to matter,
  and the source.
- An item that gets picked gets a spec in `docs/specs/`. When it's done, it leaves "Next up" or the
  backlog (`docs/history/` keeps the record), and its product step's status is updated.

## Product steps (draft)

| # | Step | Status |
|---|---|---|
| 0 | Skeleton: monorepo, `compose.yaml` with `develop.watch`, healthchecks, harness serves `/health` and reloads on file save | done: history 000 |
| 1 | First agent: LangGraph agent with one tool, token streaming over SSE, verify with `curl -N` | done: history 001; extended in 002 (production layout) and 003 (`/chat/stream` + `/chat/invoke`, batching) |
| 2 | React chat with streaming | — |
| 3 | Memory: threads and Postgres checkpointer, conversation continues after a restart | — |
| 4 | deepagents: planning, virtual FS, subagents; the agent's todo list visible in the UI | — |
| 5 | auth (Go): signup/login, passwords (argon2id), access JWT (EdDSA/RS256) + JWKS, refresh rotation, httpOnly cookie; harness validates tokens, anonymous gets 401 | — |
| 6 | RBAC: roles, protected `/admin`, 403 for `user` | — |
| 7 | Skills from the admin panel: CRUD in the DB, harness picks them up without a restart | — |
| 8 | External MCP from the admin panel: server registry, credentials, the agent sees and calls their tools | — |
| 9 | Observability: agent traces (Langfuse / OpenTelemetry), logs with trace-id across all services | — |
| 10 | Kubernetes: minikube/kind + Tilt, same services, same hot-reload | — |
| 11 | Evals: a dataset of cases and agent quality regression | — |

## Next up (proposed, in suggested order)

1. **`error` + `done` events in the stream.** Today the 200 and headers are already sent when the LLM or a
   tool fails mid-run, or when `GraphRecursionError` hits, so the stream just ends. The client can't tell a
   finished answer from a dead stream. Add typed `error` / `done` events (`done` can carry the same summary
   as `/chat/invoke`), plus a test with a *streaming* fake model, which the suite still lacks.
   *Source: history 002 and 003 debriefs.*
2. **`reasoning` event.** DeepSeek v4.1 flash takes ~11.6 s to the first token, and `ChatOpenAI` drops its
   reasoning, so the user stares at nothing. Stream reasoning as its own event. This is likely also the trigger
   for the batching timer upgrade (see the backlog).
   *Source: live measurement, spec 003.*
3. **React chat (roadmap step 2).** The event contract is ready for a frontend: a discriminated `ChatEvent`
   union in OpenAPI, `id` / `tool_call_id` pairing, batched text.
4. **Memory (roadmap step 3).** `thread_id` + checkpointer, so the agent remembers the conversation; start
   in memory, then Postgres.

## Backlog

| Idea | Why | When it starts to matter | Source |
|---|---|---|---|
| Batching timer (`asyncio.wait` on one outstanding `anext()` task) | text waits for the next event during provider stalls and while tool-call args stream | big-argument tools (step 4), streamed reasoning | spec 003, history 003 |
| Client-disconnect cleanup | a disconnect is noticed only on the next send (keepalive ping ≤15 s); inner generators are closed by the asyncgen finalizer, not an explicit `aclose()` | long tools / subagents (step 4) | history 002, 003 |
| Non-text tool results, `invalid_tool_calls` | `ToolResultEvent.content` uses `msg.text` and drops images/resources; invalid tool calls aren't surfaced | MCP (step 8) | history 002 |
| Non-root container user | the agent would act as root inside the container | filesystem tools (step 4) | history 000 |
| `init: true` in compose | nothing reaps zombie processes | MCP stdio subprocesses (step 8) | history 000 |
| `--timeout-graceful-shutdown` in the image `CMD` too | only the dev `command` has it; in prod an open SSE stream can delay shutdown | first prod-like deploy (step 10) | history 000 |
| `TEXT_FLUSH_INTERVAL` in config | it's a constant now | when it needs tuning without a release | spec 003 |
