import type { ChatEvent } from "../api/chat";

export type AssistantTurn = {
  text: string;
  status: "streaming" | "done" | "error";
  error?: string;
};

// one user message and the agent's turn that answers it
export type Exchange = { id: string; message: string; reply: AssistantTurn };

const CONNECTION_LOST = "Connection lost";

export function applyEvent(turn: AssistantTurn, event: ChatEvent): AssistantTurn {
  switch (event.type) {
    case "text":
      return { ...turn, text: turn.text + event.text };
    case "done":
      return { ...turn, status: "done" };
    case "error":
      return { ...turn, status: "error", error: event.message };
    default:
      // reasoning and tool events aren't shown yet
      return turn;
  }
}

// the stream is over; a turn that got no `done`/`error` was cut off
export function closeTurn(turn: AssistantTurn, error = CONNECTION_LOST): AssistantTurn {
  return turn.status === "streaming" ? { ...turn, status: "error", error } : turn;
}
