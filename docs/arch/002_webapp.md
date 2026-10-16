# 002. webapp: the React chat

How the frontend in `services/webapp` is put together and how a chat event becomes pixels. This doc describes
the app **as it is**; it is updated together with the code. The server side of the same request is in
[arch/001](001_chat-request-flow.md).

## Layers

```
src/
  pages/        ChatPage ── owns useChat(), lays out the containers
     │
  containers/   MessageList, Reply, Composer ── map the turn model to components
     │      │
     │   components/   Button, TextArea, Bubble ── props in, JSX out; no api/ or chat/ imports
     ▼
  chat/         useChat() hook; turn.ts: applyEvent, closeTurn (pure)
     │
  api/          streamChat(), HttpError; openapi.gen.ts (generated)
  index.css     Tailwind + design tokens
```

Imports point down only. What the chat *means* (when a turn is over, what counts as an error) is in `chat/turn.ts`
as pure functions, tested without a DOM. Components know nothing about chats, so they can be restyled or reused in
`/admin` later.

## The path of one message

```
Composer: Enter ──▶ useChat.send(message)
                      │  appends {id, message, reply: {text: "", status: "streaming"}}  → busy = true
                      ▼
                    streamChat({message})                      api/chat.ts
                      │  fetch POST /api/chat/stream
                      │    └─ Vite proxy: strips /api ──▶ harness:8000/chat/stream
                      │  body → TextDecoderStream → EventSourceParserStream
                      │  each SSE message → {type: event name, ...data} as ChatEvent
                      ▼
                    applyEvent(turn, event)                    chat/turn.ts
                      │  text → append · done → "done" · error → "error" + message · others ignored
                      ▼
                    closeTurn(turn[, error])
                      │  the stream ended (or threw) and the turn is still "streaming" → "error"
                      ▼
                    status ≠ "streaming" → busy = false → Send is enabled again
```

`busy` isn't stored: it's "the last exchange is still streaming", so it can't drift from the turns.
`send` updates state with functional `setExchanges` because the loop outlives the render that started it.

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

## Dev loop

| Mode | How | Proxy target |
|---|---|---|
| `make up` | `webapp` service, `node:22.22.3-alpine`, `vite --host 0.0.0.0` on `127.0.0.1:8080`; watch syncs `src/` (HMR), rebuilds on `package*.json`, `vite.config.ts`, `index.html` | `HARNESS_URL=http://harness:8000` |
| host | `npm --prefix services/webapp run dev` | default `http://localhost:8000` |

`strictPort`: a busy 8080 fails the start instead of moving to 8081. Event types come from harness's OpenAPI:
after changing `app/api/chat/schemas.py`, run `make api-types` and commit `src/api/openapi.gen.ts`.

## Reading order

`src/api/chat.ts` → `src/chat/turn.ts` (+ its test) → `src/chat/useChat.ts` → `src/pages/ChatPage.tsx` →
`src/containers/` → `src/index.css`.
