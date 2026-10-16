import { EventSourceParserStream } from "eventsource-parser/stream";
import type { components } from "./openapi.gen";

type Schemas = components["schemas"];
export type ChatRequest = Schemas["ChatRequest"];
export type ChatEvent = Schemas["ChatEvent"];

export class HttpError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`Request failed (${status})`);
    this.status = status;
  }
}

// EventSource can only GET, so: fetch → bytes → text → SSE messages. Unlike EventSource, fetch never reconnects
// on its own, so a dropped stream doesn't start the agent again.
export async function* streamChat(
  req: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok) throw new HttpError(res.status);
  if (!res.body) throw new Error("The response has no body");

  // the parser reassembles frames split across chunks and skips the keepalive comments (`: ping`)
  const reader = res.body
    .pipeThrough(new TextDecoderStream())
    .pipeThrough(new EventSourceParserStream())
    .getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) return;
      // harness sends the type as the SSE event name and keeps it out of `data`; put it back for the union.
      // Not validated: same origin, our own backend, typed from its OpenAPI.
      yield { type: value.event, ...JSON.parse(value.data) } as ChatEvent;
    }
  } finally {
    // a reader loop, unlike `for await` over the stream, doesn't cancel on an early exit (a throw, a `break` in
    // the consumer): without this the connection, and the agent run behind it, would stay open
    await reader.cancel().catch(() => {});
  }
}
