# 010. Spec: React chat

**Status:** approved (2026-10-16)
**Implements in:** `docs/history/010.md`

## Problem

`/chat/stream` is only readable through `curl`. One warehouse question ("Can we fully reserve order 1003?") is
20 frames in 4.8 s: 5 `reasoning`, 3 `tool_call`, 3 `tool_result` (319–527 B of escaped JSON each), 8 `text`,
`done`. The answer is a Markdown table with bold and code spans; in a terminal it's raw pipes and asterisks. Tool
calls and their results are paired only by matching ids by eye.

This is roadmap step 2. Evals move after it.

## Goals

- A chat page at `localhost:8080`: type a message, watch the answer stream in.
- The agent's work (reasoning, tool calls and their results) fills one compact activity block that scrolls along
  while the agent works and folds into a one-line summary once the answer starts. The answer renders as Markdown.
- One input at a time: sending is disabled until the run ends with `done` or `error`.
- A frontend that can be reskinned without touching components: colors, radii and fonts are tokens in one CSS file.
- Components, domain logic and transport live in separate layers.

## Non-goals

- Stop button / cancelling a run, thread list, routing, `/admin` (steps 3, 6).
- Auth (step 5), a production image (nginx/static build), CORS.
- Component tests in a DOM; runtime validation of events (same-origin, our own backend).
- A component library (shadcn/Radix). Revisit when the admin panel needs dialogs, selects, tables.

## API

No harness changes. The browser talks to `/api/*`; the Vite dev server proxies it to harness with the prefix
stripped (`/api/chat/stream` → `harness:8000/chat/stream`), so there's no CORS. The request is the existing
`ChatRequest` (`message`, `thread_id`).

## Design

### Layers

```
services/webapp/src/
  api/          transport: streamChat(), generated OpenAPI types. No React.
  chat/         domain: the turn model, a pure reducer over ChatEvents, the useChat() hook. No JSX.
  components/   UI kit: props in, JSX out. Imports nothing from api/ or chat/.
  containers/   glue: map the turn model to components (MessageList, Reply, Activity, Composer).
  pages/        ChatPage: owns useChat() and hands each container its slice.
  index.css     Tailwind + design tokens: the only place with colors.
```

Imports go one way: `pages → containers → components`, `containers → chat → api`. Business rules (what is an
answer, what goes into the activity block) live in `chat/` as pure functions, so they're tested without a browser.

### Transport: `api/chat.ts`

`EventSource` only does GET, and the request is a POST with a body. So: `fetch` → `response.body` →
`TextDecoderStream` → `EventSourceParserStream` (`eventsource-parser/stream`) → async iterator of messages.
The parser handles chunk splits and the keepalive comments (`: ping`). harness sends the type as the SSE event
name and keeps it out of `data`, so the client puts it back: `{type: msg.event, ...JSON.parse(msg.data)}`.

```ts
streamChat(req: ChatRequest, signal?: AbortSignal): AsyncGenerator<ChatEvent>
```

A non-2xx response throws `HttpError(status)`. A stream that ends without `done`/`error` is reported by the
reducer, not the transport (see Errors). Unlike `EventSource`, `fetch` never reconnects on its own, so a dropped
stream doesn't restart the agent.

### Event types: generated

`ChatEvent`, `ChatRequest` and friends come from harness's OpenAPI via `openapi-typescript` 7.13.0 into
`src/api/openapi.gen.ts` (committed). `make api-types` dumps the schema with `app.openapi()` (no running server,
no LLM env) and runs the generator through a pinned `npx`: it isn't a project dependency because it wants
`typescript@^5` as a peer, and we're on 6.

### Turn model: `chat/turn.ts`

A user turn is the message text. An assistant turn is an ordered list of parts plus a status:

```ts
type Part =
  | { kind: "reasoning"; text: string }
  | { kind: "text"; text: string }
  | { kind: "tool"; id: string | null; name: string; args: Record<string, unknown>;
      result?: { content: string; status: "success" | "error" } }
type AssistantTurn = { parts: Part[]; status: "streaming" | "done" | "error"; error?: string }
```

`applyEvent(turn, event)` is the reducer: `text`/`reasoning` append to the last part when it's the same kind
(batched frames are fragments), `tool_call` adds a tool part, `tool_result` fills the tool part with the same id
(a result with no matching call becomes its own tool part), `done`/`error` set the status.

**What's the answer.** The model can say something, call a tool, and say more; text isn't final until no tool
call follows it. So `splitTurn(parts)` derives it instead of storing it: the answer is the trailing run of `text`
parts after the last non-text part; everything before goes into the activity block (earlier text included, shown
as an interim note). When a tool call arrives after some text, that text moves into the block. In the measured run
the order is `reasoning, call, result, reasoning, call, call, result, result, reasoning, text…`, so the block
holds 6 parts (3 reasoning, 3 tools) and the answer is one text part built from 8 frames.

### Activity block

- **Live** (turn streaming and no answer yet): expanded, max height `ACTIVITY_MAX_LINES = 6` lines, scrolls to the
  newest part as it grows; the user can scroll up, and auto-scroll resumes when they're back at the bottom.
- **Folded** (answer started, or the turn ended): one line, e.g. `Reasoning · 3 tool calls · 1 failed`; a click
  expands it to full height.
- Parts: reasoning as muted text; a tool part as `name(args)` with a spinner until its result, then a status mark;
  the result content (pretty-printed when it's JSON) is behind a per-tool toggle. Parallel calls (`call, call,
  result, result`) show as two pending tools that resolve independently.

### Answer and composer

- The answer: `react-markdown` + `remark-gfm` (tables), raw HTML off (the default), styled by
  `@tailwindcss/typography` with its colors mapped to our tokens.
- Composer: a textarea; Enter sends, Shift+Enter is a newline. While a turn streams the send button and Enter are
  disabled. The message list sticks to the bottom while streaming unless the user scrolled up.
- Thread: `crypto.randomUUID()` per page load (matches `ThreadId`), so follow-ups continue the conversation. A
  "New chat" button clears the list and takes a fresh id.

### Errors

| What | Where it's caught | What the user sees |
|---|---|---|
| `error` event | reducer | the turn's status is `error`, the message is shown under the turn |
| non-2xx (422; 5xx from the proxy when harness is down) | `streamChat` throws `HttpError` | "Request failed (<status>)" |
| network error, or the stream ends without `done`/`error` | `useChat` | "Connection lost" |
| tool `status: "error"` | activity block | a red mark on that tool; the run goes on |

In every case the turn ends and the composer is enabled again.

### Theming

Tailwind 4 is configured in CSS. `index.css` resets the default palette (`--color-*: initial`) and defines
semantic color tokens in `@theme`: `bg`, `surface`, `border`, `fg`, `muted`, `accent`, `on-accent`, `danger`,
`success`. Radius and font stay Tailwind's defaults until a design needs its own. Components can only use `bg-surface`, `text-muted`, …: a raw `bg-gray-100` doesn't exist, so a
reskin is editing one file. Dark mode overrides the same variables under `prefers-color-scheme: dark`.

### Dev loop

A `webapp` service in `compose.yaml` on `node:22.22.3-alpine`: `npm ci` in the image, `vite --host` as the
command, `127.0.0.1:8080`, `develop.watch` syncing `src/` (Vite's HMR picks it up) and rebuilding on
`package.json` / `package-lock.json` / `vite.config.ts` / `index.html`. The port is Vite's `server.port: 8080` with `strictPort`: a busy port fails
the start instead of silently moving to 8081. The proxy target is `HARNESS_URL` (compose: `http://harness:8000`;
default `http://localhost:8000`, so `npm run dev` on the host works against `make up` too).

## Substeps

| # | Result you can poke | Contents |
|---|---|---|
| 010.1 | type a message at `:8080`, the answer streams in as plain text; a failed request shows its error | scaffold, compose service, proxy, tokens, `streamChat`, generated types, a text-only turn that always ends (`closeTurn`), `make lint`/`make test` |
| 010.2 | the activity block fills, scrolls and folds; the answer is Markdown | turn model with parts, `splitTurn`, Activity container, Markdown |
| 010.3 | "New chat"; follow-ups on one thread; the list follows the stream | thread id, stick-to-bottom |

## Code changes

- New `services/webapp/`: `package.json` (+ lock), `vite.config.ts`, `tsconfig*.json`, `.oxlintrc.json`,
  `.prettierrc.json`, `Dockerfile`, `index.html`, `src/` as in Layers.
- `compose.yaml`: the `webapp` service.
- `Makefile`: webapp in `test` and `lint`; `api-types`.
- `CLAUDE.md`: layout (`services/webapp` instead of `web/`), pinned versions.
- `docs/arch/002_webapp.md`: layers, the event → turn flow, the activity block states.
- `docs/ROADMAP.md`: step 2 status, Next up.

## Tests

Vitest in the node environment (no DOM), expected values as literals.

- `streamChat`: a `Response` whose body is SSE text split mid-frame, with a `: ping` comment → events with `type`
  restored; a 502 → `HttpError` with status 502.
- `applyEvent`: text fragments merge; reasoning then text are two parts; `tool_call` + `tool_result` pair by id,
  including two parallel calls resolved in reverse order; a result with an unknown id; `error` sets status and
  message.
- `splitTurn`: the measured order above → 6 activity parts and the answer; text followed by a tool call moves into
  the activity; no tool calls → empty activity.

## How to verify

```bash
make up                      # now also starts webapp
open http://localhost:8080
```

1. "Can we fully reserve order 1003? Just check." → the activity block fills (reasoning, `wms_get_order`, two
   `wms_get_stock` resolving), then folds to a summary; the answer table renders; send is disabled until `done`.
2. "Which product is short?" → answered on the same thread.
3. `docker compose stop testing-wms-mcp`, ask about WRAP-500 → red tool marks, an answer, the composer comes back.
4. `docker compose stop harness`, send → "Request failed (…)" with the proxy's status.
5. Change `--color-accent` in `index.css` → the page restyles without a reload.

## Decisions

| # | Decision | Chosen | Alternatives and why not |
|---|---|---|---|
| 1 | Location | `services/webapp` | `web/` (CLAUDE.md's original): every deployable lives in `services/` |
| 2 | Toolchain | Vite 8.3 + React 19.3 + TypeScript 6.0 | TS 7.0 (Go port): `create-vite` still pins 6.0, and tools that use the compiler API (openapi-typescript) don't support it yet; Next.js: no SSR need |
| 3 | Styling | Tailwind 4.3, semantic tokens, default palette reset | plain CSS: no design scale to extend; shadcn/Radix: deps we don't need for one page |
| 4 | Transport | `fetch` + `eventsource-parser` 4.1 | `EventSource`: GET only; `@microsoft/fetch-event-source`: unmaintained; own parser: SSE has edge cases (CRLF, multi-line `data`, comments) |
| 5 | Event types | generated from OpenAPI, committed | handwritten: drifts silently from `schemas.py` |
| 6 | State | pure reducer + one hook | zustand/redux: one page, one stream |
| 7 | Answer vs activity | derived by `splitTurn` (trailing text) | a flag set on the first text: wrong when the model talks, then calls a tool |
| 8 | Markdown | react-markdown 10 + remark-gfm 4, typography plugin | plain text: the agent answers in tables |
| 9 | Lint / format / test | oxlint (template default) + Prettier with the Tailwind plugin; `tsc -b`; Vitest 5 | ESLint: slower, more config; Biome: formatter is fine, but we'd drop the template's linter |
| 10 | Dev loop | compose service with watch | host-only `npm run dev`: one more terminal, breaks "`make up` brings it all" |

## Deviations

Recorded during 010.1:

- **`fg`, not `text`**: a `text` color token makes `text-text`. `on-accent` was added for text on accent buttons
  (the reset removes `white`). Radius and font tokens were dropped: Tailwind's defaults until a design asks.
- **The page owns `useChat()`.** Two containers calling the hook would get two separate chats; the page calls it
  once and passes `exchanges`, `busy` and `send` down.
- **Turn endings moved to 010.1.** Without them a failed request leaves the composer disabled forever, so
  `closeTurn` (a turn with no `done`/`error` becomes "Connection lost") and the `HttpError` message ship with the
  first stream. 010.3 keeps the thread and the scrolling.
- **A text-only turn is `{text, status, error}`**, not parts: with one kind of part the array is premature. 010.2
  turns it into parts.
- **Prettier `printWidth: 100`**: at 80, Tailwind class lists and typed props wrap on almost every line.
- **The dev proxy cuts a broken stream.** Found in review: when harness dies mid-stream, Vite's proxy (http-proxy-3)
  never ends the browser's response, so the turn would stay "streaming" forever. `configure` destroys the
  response when the upstream one closes incomplete. A client-side idle watchdog would also cover half-open TCP
  and a prod reverse proxy; it's in the backlog.
