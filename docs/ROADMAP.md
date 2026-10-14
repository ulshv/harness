# Roadmap: what's next

Everything about what's next: the product steps, the proposed "next up" list, and the backlog. I choose the order.

How this file is kept:

- When a review or debrief defers something, it goes into the backlog with why, when it starts to matter,
  and the source.
- An item that gets picked gets a spec in `docs/specs/`. When it's done, it leaves "Next up" or the
  backlog (`docs/history/` keeps the record), and its product step's status is updated.

## Product steps (draft)

Numbers are stable IDs (history, specs and backlog refer to them), not the build order. The README shows the
suggested order.

| # | Step | Status |
|---|---|---|
| 0 | Skeleton: monorepo, `compose.yaml` with `develop.watch`, healthchecks, harness serves `/health` and reloads on file save | done: history 000 |
| 1 | First agent: LangGraph agent with one tool, token streaming over SSE, verify with `curl -N` | done: history 001; extended in 002 (production layout), 003 (`/chat/stream` + `/chat/invoke`, batching) 004 (`error` / `done` events) and 005 (`reasoning` event) |
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
| 12 | Custom tools as plugins: tools packaged and registered without touching the agent core | — |
| 13 | Dictionaries: per-environment values that skills reference by name. One skill (say "update the deal amount") works across environments where the same MCP server exposes different internals (`cf_12345` in one CRM, `UF_CRM_AMOUNT` in another) | — |
| 14 | Multi-tenancy: tenant isolation for threads, skills, dictionaries, MCP credentials | — |
| 15 | SSO / OAuth (OIDC) on top of the Go auth service | — |
| 16 | Inbound integrations: external systems (CRM, messengers, internal services) authenticate to harness with OAuth 2.0 client credentials or scoped, per-tenant API keys (service tokens issued by auth), and trigger agent runs via `/webhooks/...` endpoints. Includes signature verification, idempotency keys, async runs with results delivered by callback or polling, and rate limits | — |

Distribution: open core. The foundation stays open source (Apache-2.0); some enterprise capabilities may
ship separately.

## Next up (proposed, in suggested order)

1. **React chat (roadmap step 2).** The event contract is ready for a frontend: a discriminated `ChatEvent`
   union in OpenAPI, `id` / `tool_call_id` pairing, batched text, `reasoning` for a spoiler, `done` / `error`.
2. **Memory (roadmap step 3).** `thread_id` + checkpointer, so the agent remembers the conversation; start
   in memory, then Postgres.

## Backlog

| Idea | Why | When it starts to matter | Source |
|---|---|---|---|
| Batching timer (`asyncio.wait` on one outstanding `anext()` task) | text waits for the next event during provider stalls and while tool-call args stream | big-argument tools (step 4); streamed reasoning showed no stalls (history 005) | spec 003, history 003 |
| Client-disconnect cleanup | a disconnect is noticed only on the next send (keepalive ping ≤15 s); inner generators are closed by the asyncgen finalizer, not an explicit `aclose()` | long tools / subagents (step 4) | history 002, 003 |
| Non-text tool results, `invalid_tool_calls` | `ToolResultEvent.content` uses `msg.text` and drops images/resources; invalid tool calls aren't surfaced | MCP (step 8) | history 002 |
| Non-root container user | the agent would act as root inside the container | filesystem tools (step 4) | history 000 |
| `init: true` in compose | nothing reaps zombie processes | MCP stdio subprocesses (step 8) | history 000 |
| `--timeout-graceful-shutdown` in the image `CMD` too | only the dev `command` has it; in prod an open SSE stream can delay shutdown | first prod-like deploy (step 10) | history 000 |
| `FLUSH_INTERVAL` in config | it's a constant now | when it needs tuning without a release | spec 003 |
| Usage / cost in `done` | `done` is `{}`. RouterAI sends usage in the last chunk on its own, so `usage_metadata` per LLM call is already there, including `output_token_details.reasoning`. Our class doesn't request it: `_should_stream_usage()` is `False` for a custom `base_url`. What's left is summing it across the calls in a run | cost visibility in the UI or admin | spec 004, history 005 |
| Reasoning settings (effort, on/off) | reasoning is whatever the provider sends by default; no per-request or config control. Also, one live run came back without reasoning (provider variance) | cost/latency tuning, or a "fast mode" toggle in the UI | spec 005 non-goals, history 005 |
| Echo reasoning back within a ReAct loop | DeepSeek docs: within a turn with `tools`, `reasoning_content` "must be fully passed back… otherwise 400"; across turns it's ignored, so there's no context bloat. `ChatDeepSeek` 1.1.1 never sends it back. RouterAI tolerates that. The answer after a tool came without reasoning once, though other runs did reason after `tool_result`. Plan: echo within a turn, drop across turns | long tool chains (step 4) or a switch to the native DeepSeek API | history 005 |
| `interrupt` terminal event | the root graph swallows `GraphInterrupt` and emits `__interrupt__` in `updates`, so a paused run ends with `done` | human-in-the-loop (with deepagents, step 4) | history 004 |
| Error code for context overflow | `ContextOverflowError` is `internal` now; the user can't act on that | memory (step 3) makes long histories common | history 004 |
| Streaming fake with tool calls | `StreamingFakeModel` streams text only, so tool-call chunk streaming (`tool_call_chunks`) is untested | big-argument tools (step 4) | history 004 |
