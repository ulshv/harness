import type { ChatEvent } from "../api/chat";

type ToolCallEvent = Extract<ChatEvent, { type: "tool_call" }>;
type ToolResultEvent = Extract<ChatEvent, { type: "tool_result" }>;

export type ToolPart = {
  kind: "tool";
  id: string | null;
  name: string;
  args: ToolCallEvent["args"];
  result?: Pick<ToolResultEvent, "content" | "status">;
};

// what the agent produced, in order; adjacent text or reasoning fragments merge into one part
export type Part = { kind: "reasoning"; text: string } | { kind: "text"; text: string } | ToolPart;

export type AssistantTurn = {
  parts: Part[];
  status: "streaming" | "done" | "error";
  error?: string;
};

// one user message and the agent's turn that answers it
export type Exchange = { id: string; message: string; reply: AssistantTurn };

const CONNECTION_LOST = "Connection lost";

export function applyEvent(turn: AssistantTurn, event: ChatEvent): AssistantTurn {
  switch (event.type) {
    case "text":
    case "reasoning":
      return { ...turn, parts: appendText(turn.parts, event.type, event.text) };
    case "tool_call":
      return {
        ...turn,
        parts: [...turn.parts, { kind: "tool", id: event.id, name: event.name, args: event.args }],
      };
    case "tool_result":
      return { ...turn, parts: addResult(turn.parts, event) };
    case "done":
      return { ...turn, status: "done" };
    case "error":
      return { ...turn, status: "error", error: event.message };
    default:
      // every known type is handled above (a new one fails here at compile time); at runtime a newer harness
      // may send a type this build doesn't know: skip it rather than break the turn
      event satisfies never;
      return turn;
  }
}

// the stream is over; a turn that got no `done`/`error` was cut off
export function closeTurn(turn: AssistantTurn, error = CONNECTION_LOST): AssistantTurn {
  return turn.status === "streaming" ? { ...turn, status: "error", error } : turn;
}

// The answer is the text after the agent's last step: text is final only when no tool call follows it, so this
// is derived on every render, never stored. Text merges, so the answer is at most the last part; whitespace
// alone (a model's "\n\n" before a tool call) doesn't start one.
export function splitTurn(parts: Part[]): { activity: Part[]; answer: string } {
  const last = parts.at(-1);
  return last?.kind === "text" && last.text.trim()
    ? { activity: parts.slice(0, -1), answer: last.text }
    : { activity: parts, answer: "" };
}

// the one-line summary of a folded activity block: "Reasoning · 3 tool calls · 1 failed"
export function describeActivity(parts: Part[]): string {
  const tools = parts.filter((p) => p.kind === "tool");
  const failed = tools.filter((t) => t.result?.status === "error").length;
  return [
    parts.some((p) => p.kind === "reasoning") && "Reasoning",
    tools.length > 0 && `${tools.length} tool call${tools.length === 1 ? "" : "s"}`,
    failed > 0 && `${failed} failed`,
  ]
    .filter(Boolean)
    .join(" · ");
}

function appendText(parts: Part[], kind: "text" | "reasoning", text: string): Part[] {
  const last = parts.at(-1);
  return last?.kind === kind
    ? [...parts.slice(0, -1), { kind, text: last.text + text }]
    : [...parts, { kind, text }];
}

// parallel calls resolve in any order, so a result finds its call by id; one with no call gets its own part
function addResult(parts: Part[], event: ToolResultEvent): Part[] {
  const result = { content: event.content, status: event.status };
  const i = parts.findIndex((p) => p.kind === "tool" && p.id === event.tool_call_id && !p.result);
  if (i === -1) {
    return [
      ...parts,
      { kind: "tool", id: event.tool_call_id, name: event.name ?? "", args: {}, result },
    ];
  }
  return parts.map((p, j) => (j === i && p.kind === "tool" ? { ...p, result } : p));
}
