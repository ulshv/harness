import { useState } from "react";
import { HttpError, streamChat } from "../api/chat";
import { applyEvent, closeTurn, type AssistantTurn, type Exchange } from "./turn";

export function useChat() {
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  // one turn at a time: sending waits until the last one ends
  const busy = exchanges.at(-1)?.reply.status === "streaming";

  async function send(message: string) {
    const id = crypto.randomUUID();
    // functional updates: this loop outlives the render that started it, so a captured `exchanges` goes stale
    const updateReply = (change: (turn: AssistantTurn) => AssistantTurn) =>
      setExchanges((all) => all.map((x) => (x.id === id ? { ...x, reply: change(x.reply) } : x)));

    setExchanges((all) => [...all, { id, message, reply: { text: "", status: "streaming" } }]);
    try {
      for await (const event of streamChat({ message })) {
        updateReply((turn) => applyEvent(turn, event));
      }
      updateReply((turn) => closeTurn(turn));
    } catch (err) {
      // a non-2xx has a status worth showing; anything else reads as a lost connection to the user, but a bug
      // in our own code would hide behind it, so it goes to the console too
      if (!(err instanceof HttpError)) console.error(err);
      updateReply((turn) => closeTurn(turn, err instanceof HttpError ? err.message : undefined));
    }
  }

  return { exchanges, busy, send };
}
