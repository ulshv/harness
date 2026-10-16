import type { AssistantTurn } from "../chat/turn";

export function Reply({ turn }: { turn: AssistantTurn }) {
  return (
    <div className="flex flex-col gap-1">
      {turn.text ? (
        <p className="wrap-break-word whitespace-pre-wrap">{turn.text}</p>
      ) : (
        turn.status === "streaming" && <p className="text-muted">Working…</p>
      )}
      {turn.error && <p className="text-sm text-danger">{turn.error}</p>}
    </div>
  );
}
