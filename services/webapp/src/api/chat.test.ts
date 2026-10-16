import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpError, streamChat } from "./chat";

// a response whose body arrives in exactly these chunks; bytes, to split a multi-byte character
function sseResponse(...chunks: (string | Uint8Array)[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      }
      controller.close();
    },
  });
  return new Response(body, { headers: { "content-type": "text/event-stream" } });
}

async function collect<T>(events: AsyncIterable<T>): Promise<T[]> {
  const all: T[] = [];
  for await (const event of events) all.push(event);
  return all;
}

afterEach(() => vi.unstubAllGlobals());

describe("streamChat", () => {
  it("posts the request and restores `type` from the event name", async () => {
    const fetch = vi.fn(async () =>
      sseResponse(
        'event: text\ndata: {"text":"Hel',
        'lo"}\n\n: ping\n\nevent: tool_call\ndata: {"id":"c1","name":"wms_get_order","args":{"order_id":1003}}\n\n',
        "event: done\ndata: {}\n\n",
      ),
    );
    vi.stubGlobal("fetch", fetch);

    const events = await collect(streamChat({ message: "hi" }));

    expect(events).toEqual([
      { type: "text", text: "Hello" },
      {
        type: "tool_call",
        id: "c1",
        name: "wms_get_order",
        args: { order_id: 1003 },
      },
      { type: "done" },
    ]);
    expect(fetch).toHaveBeenCalledWith("/api/chat/stream", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: '{"message":"hi"}',
      signal: undefined,
    });
  });

  it("decodes a character split across chunks", async () => {
    const encoder = new TextEncoder();
    const bytes = encoder.encode('event: text\ndata: {"text":"мой"}\n\n');
    // cut between the two bytes of "й"
    const cut = encoder.encode('event: text\ndata: {"text":"мо').length + 1;
    vi.stubGlobal("fetch", async () => sseResponse(bytes.slice(0, cut), bytes.slice(cut)));

    expect(await collect(streamChat({ message: "hi" }))).toEqual([{ type: "text", text: "мой" }]);
  });

  it("throws HttpError on a non-2xx response", async () => {
    vi.stubGlobal("fetch", async () => new Response("Bad Gateway", { status: 502 }));

    const error = await collect(streamChat({ message: "hi" })).catch((err: unknown) => err);

    expect(error).toBeInstanceOf(HttpError);
    expect(error).toMatchObject({
      status: 502,
      message: "Request failed (502)",
    });
  });
});
