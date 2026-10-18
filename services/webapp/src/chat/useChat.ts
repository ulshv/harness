import { useRef, useState } from "react";
import { HttpError, streamChat } from "../api/chat";
import { applyEvent, closeTurn, type AssistantTurn, type Exchange } from "./turn";

// a fresh conversation id; a UUID fits harness's ThreadId (`[A-Za-z0-9_-]{1,64}`)
const newThreadId = () => crypto.randomUUID();

export function useChat() {
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  // one thread per conversation: harness keeps the history under this id, so follow-ups have context
  const [threadId, setThreadId] = useState(newThreadId);
  const running = useRef<AbortController | null>(null);
  // one turn at a time: sending waits until the last one ends
  const busy = exchanges.at(-1)?.reply.status === "streaming";

  async function send(message: string) {
    const id = crypto.randomUUID();
    const controller = new AbortController();
    running.current = controller;
    // functional updates: this loop outlives the render that started it, so a captured `exchanges` goes stale
    const updateReply = (change: (turn: AssistantTurn) => AssistantTurn) =>
      setExchanges((all) => all.map((x) => (x.id === id ? { ...x, reply: change(x.reply) } : x)));

    setExchanges((all) => [...all, { id, message, reply: { parts: [], status: "streaming" } }]);
    try {
      for await (const event of streamChat({ message, thread_id: threadId }, controller.signal)) {
        updateReply((turn) => applyEvent(turn, event));
      }
      updateReply((turn) => closeTurn(turn));
    } catch (err) {
      // aborted by newChat(): the exchange is already gone, there's nothing to show
      if (controller.signal.aborted) return;
      // a non-2xx has a status worth showing; anything else reads as a lost connection to the user, but a bug
      // in our own code would hide behind it, so it goes to the console too
      if (!(err instanceof HttpError)) console.error(err);
      updateReply((turn) => closeTurn(turn, err instanceof HttpError ? err.message : undefined));
    }
  }

  // Aborting the fetch closes the connection, so harness cancels the run instead of finishing it for nobody.
  // The old thread stays in harness's memory until a restart (see the ROADMAP backlog).
  function newChat() {
    running.current?.abort();
    setExchanges([]);
    setThreadId(newThreadId());
  }

  return { exchanges, busy, threadId, send, newChat };
}
