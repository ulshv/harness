# harness

**English** · [Русский](README-ru.md)

**An open-source foundation for production AI agents.** The agent runs as a real service with streaming,
tools, skills, MCP integrations, an admin panel and grown-up auth. It's meant to be the base an enterprise or
a startup builds its own harness on.

![status](https://img.shields.io/badge/status-draft%20%2F%20WIP-orange)
![python](https://img.shields.io/badge/python-3.14-3776AB)
![fastapi](https://img.shields.io/badge/FastAPI-0.143-009688)
![langgraph](https://img.shields.io/badge/LangGraph-1.2-1C3C3C)
![license](https://img.shields.io/badge/license-Apache--2.0-blue)

**Started:** October 14th, 2026 · **Steps shipped:** [6](docs/history) · **Live demo:** coming soon

> **Status: draft (work in progress), not a PoC.** Every shipped step is production-grade: layered code,
> typed contracts, tests, docs and a reviewed design. Features land one at a time.

## Crafted, not vibe-coded

Today's coding LLMs write like mid-level developers who ship spaghetti unless someone watches every line.
Plenty of AI-assisted projects now follow a "spec → plan → AI review" flow. The process alone doesn't
make the code good. What makes the difference is the craft that goes into it.

I've spent the last two years building AI agent harnesses that run in enterprise production. This repo is
how I think the foundation of such a harness should be built. AI tools speed up the typing; I review every
line and rework it until it meets clean-code standards.

## What it's becoming

- **Chat UI and admin panel (React).** Streaming chat with tool calls and reasoning in a spoiler. Admin for
  skills, integrations, users and roles.
- **Skills library.** Create and edit agent skills from the admin panel; the agent picks them up without a restart.
- **Custom tools as plugins.** Extend the agent without touching its core.
- **External MCP integrations.** A registry of MCP servers with credentials; the agent discovers and calls
  their tools.
- **Dictionaries.** Skills stay portable across environments: a skill refers to `{{crm.deal_amount}}`, and each
  environment's dictionary says what that is there (`cf_12345` in one CRM, `UF_CRM_AMOUNT` in another).
  One skill, many installations.
- **Serious auth.** A Go microservice with argon2id passwords, short-lived EdDSA JWTs verified via JWKS,
  refresh-token rotation, httpOnly cookies, then RBAC. Multi-tenancy and SSO come later.
- **Event-driven agents.** Beyond chat, external systems such as a CRM or a messenger authenticate with OAuth
  client credentials or scoped API keys and trigger the agent through webhook endpoints.
- **RAG.** Knowledge bases managed from the admin panel: ingestion, pgvector in Postgres, hybrid search, and
  answers with citations. Per tenant.
- **Memory, deep agents, observability and evals.** Threads in Postgres, planning and subagents. Traces and
  evals live in one place, Langfuse: datasets built from real production traces, LLM-as-judge scoring, and a
  regression gate for agent quality.

## Architecture

<img src="./docs/imgs/architecture.svg" alt="harness architecture: clients (chat UI over SSE, admin panel over REST, external systems over webhooks) call harness APIs; chat goes through the event pipeline, webhooks start async runs; the agent runtime uses tools, plugins, MCP client, skills and dictionaries, memory and a RAG knowledge base; LLM providers, MCP servers, Postgres with pgvector, Langfuse for traces and evals; the Go auth service issues tokens and publishes JWKS keys to harness, with SSO" />

Solid green: shipped. Dashed: planned.

<details>
<summary>Mermaid version</summary>

```mermaid
flowchart TB
    subgraph clients["Clients"]
        chat_ui["Chat UI<br/>React"]
        admin_ui["Admin panel<br/>React"]
        ext_sys["External systems<br/>CRM · messengers"]
    end

    subgraph harness["harness · Python · FastAPI + LangGraph"]
        chat_api["Chat API · SSE<br/>stream · invoke"]
        admin_api["Admin API<br/>CRUD · hot reload"]
        hooks["Webhooks API<br/>OAuth · API keys"]
        pipeline["Event pipeline<br/>translate · batch"]
        agent["Agent runtime<br/>ReAct · deep agents"]
        tools["Built-in<br/>tools"]
        plugins["Tool<br/>plugins"]
        mcp_client["MCP<br/>client"]
        skills["Skills<br/>Dictionaries"]
        memory["Memory<br/>checkpoints"]
        rag["Knowledge<br/>RAG"]
    end

    subgraph auth_box["auth · Go"]
        auth["JWT + JWKS · RBAC<br/>service tokens · SSO"]
    end

    llm[("LLM<br/>providers")]
    mcp[("MCP<br/>servers")]
    pg[("Postgres<br/>pgvector")]
    idp[("Identity<br/>provider")]
    obs[("Langfuse<br/>traces · evals")]

    chat_ui -- "SSE" --> chat_api
    admin_ui -- "REST" --> admin_api
    ext_sys -- "webhooks · callbacks" --> hooks
    clients -- "login · OAuth" --> auth_box
    auth_box -. "JWKS keys" .-> harness

    chat_api --> pipeline --> agent
    hooks -- "async run" --> agent
    admin_api --> skills
    admin_api -- "ingest" --> rag
    agent --> tools
    agent --> plugins
    agent --> mcp_client
    agent --> skills
    agent --> memory
    agent --> rag

    agent --> llm
    mcp_client --> mcp
    skills --> pg
    memory --> pg
    rag --> pg
    auth_box --> pg
    auth_box --> idp
    agent -. "traces · scores" .-> obs

    classDef shipped fill:#e8f5e9,stroke:#2e7d32,color:#1b1b1b
    classDef planned fill:#fafafa,stroke:#9e9e9e,stroke-dasharray:5 4,color:#424242
    class chat_api,pipeline,agent,tools,llm shipped
    class chat_ui,admin_ui,ext_sys,admin_api,hooks,plugins,skills,mcp_client,memory,rag,auth,mcp,pg,idp,obs planned
    style clients fill:#ffffff,stroke:#bdbdbd
    style harness fill:#ffffff,stroke:#bdbdbd
    style auth_box fill:#ffffff,stroke:#bdbdbd
```

</details>

- **harness** (Python): the agent runtime. Three ways in: chat over SSE (through the event pipeline:
  translate graph output → append `done`/`error` → batch), the admin API, and webhooks from external systems,
  which start async runs and get results back via callbacks.
- **auth** (Go): issues tokens to people (login, SSO) and to systems (OAuth client credentials, API keys).
  harness verifies them locally via JWKS and never calls auth per request.
- **Clients**: the React chat and admin panel, plus external systems such as a CRM or a messenger.

A deeper walkthrough is in [`docs/arch/001_chat-request-flow.md`](docs/arch/001_chat-request-flow.md).

## Roadmap

**Shipped**

- [x] Foundation: monorepo, Docker Compose dev loop with hot reload, health checks
- [x] LangGraph ReAct agent with tools, configurable OpenAI-compatible provider
- [x] SSE streaming, from PoC to a production layout: layered API, typed events, fail-fast config
- [x] `/chat/stream` and `/chat/invoke` on one pipeline; text batching (~10× fewer frames)
- [x] Terminal `done` / `error` events with safe error codes and a recursion guard
- [x] Live `reasoning` stream

**Next**, in build order

- [ ] React chat UI: streaming, tool calls, reasoning spoiler
- [ ] Memory: conversation threads, Postgres checkpointer
- [ ] Deep agents: planning, virtual filesystem, subagents, with the agent's todo list in the UI
- [ ] Auth service in Go: argon2id, EdDSA JWT + JWKS, refresh rotation
- [ ] RBAC and the admin panel
- [ ] Skills library, managed from the admin panel and hot-reloaded
- [ ] Custom tools as plugins
- [ ] External MCP integrations: server registry, credentials
- [ ] Dictionaries: portable skills with per-environment values
- [ ] RAG: knowledge bases, pgvector, hybrid search, citations in the chat
- [ ] Observability: agent traces in Langfuse, trace-id across services
- [ ] Evals in Langfuse: datasets from production traces, LLM-as-judge, a regression gate in CI
- [ ] Multi-tenancy

**Later**

- [ ] Kubernetes: the same services and the same hot-reload dev loop, via kind/minikube + Tilt
- [ ] SSO / OAuth (OIDC)
- [ ] Inbound webhooks: external systems trigger agent runs, authenticated with OAuth client credentials or API keys
- [ ] Live demo

The foundation stays open source; some enterprise capabilities may ship separately. The working roadmap,
with the backlog and its reasons, is in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## What it does today

One real request: the model thinks, calls a tool, thinks again with the result, answers, and closes the
stream explicitly (repeated frames trimmed).

```bash
curl -N localhost:8000/chat/stream -H 'content-type: application/json' \
  -d '{"message":"How many minutes are left until midnight UTC?"}'
```

```
event: reasoning
data: {"text":"We need"}

event: reasoning
data: {"text":" answer needs current time. Use tool."}

event: tool_call
data: {"id":"call_00_qJxXBvCuuGrvvrCFXHIr9647","name":"current_time","args":{}}

event: tool_result
data: {"tool_call_id":"call_00_qJxXBvCuuGrvvrCFXHIr9647","name":"current_time","content":"2026-10-14T20:04:19+00:00"}

event: reasoning
data: {"text":"Current time"}

… 6 more reasoning frames: the model does the arithmetic

event: text
data: {"text":"At 20:04:19 UTC, there are **"}

… 3 more text frames

event: done
data: {}
```

- **A LangGraph ReAct agent** behind FastAPI, with any OpenAI-compatible provider. The default is DeepSeek
  via RouterAI.
- **One event pipeline, two endpoints.** `/chat/stream` sends SSE; `/chat/invoke` returns the same events
  merged into one JSON response. That makes tests exact and keeps the UI and the API honest with each other.
- **Typed event contract** (`reasoning`, `text`, `tool_call`, `tool_result`, `done`, `error`) published as
  a discriminated union in OpenAPI, ready for a generated frontend client.
- **Live reasoning.** Time to the first frame dropped from ~11.6 s of silence to ~1.4 s.
- **Safe failures.** Every stream ends with `done` or `error`. Error codes separate retryable provider
  outages from our own misconfiguration, and details stay in the logs.
- **A dev loop that just works.** `make up` starts Docker Compose with hot reload; `make test` and
  `make lint` run the checks. Unit tests use deterministic fake models; the live model runs only in smoke tests.

## Quick start

Requires Docker with Compose ≥ 2.22, `make`, and [`uv`](https://docs.astral.sh/uv/) for running tests locally.

```bash
git clone https://github.com/ulshv/harness.git && cd harness
cp .env.example .env        # set LLM_API_KEY (any OpenAI-compatible endpoint; defaults: RouterAI + DeepSeek)
make up                     # docker compose up --watch: edit code, the service reloads
curl -N localhost:8000/chat/stream -H 'content-type: application/json' -d '{"message":"hi"}'
make test && make lint
```

The OpenAPI UI is at `localhost:8000/docs`.

## How it's built

| Where | What |
|---|---|
| [`docs/specs/`](docs/specs) | a spec per step, written before code: problem, decisions, trade-offs |
| [`docs/history/`](docs/history) | what each step changed, how to verify it, gotchas found, review takeaways |
| [`docs/arch/`](docs/arch) | how the system works today |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | product steps, next up, backlog with the reasons for each item |

**Stack:** Python 3.14, FastAPI, LangGraph, LangChain, pydantic, uv, pytest, ruff · Go (auth) ·
React + Vite + TypeScript · Postgres · Docker Compose, later Kubernetes.

## License

[Apache-2.0](LICENSE)
