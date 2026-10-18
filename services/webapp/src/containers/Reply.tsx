import { memo } from "react";
import { Markdown } from "../components/Markdown";
import { splitTurn, type AssistantTurn } from "../chat/turn";
import { Activity } from "./Activity";

// memo: every event re-renders the list, but useChat keeps finished turns' identity, so only the streaming
// reply re-parses its Markdown instead of every answer in the chat
export const Reply = memo(function Reply({ turn }: { turn: AssistantTurn }) {
  const { activity, answer } = splitTurn(turn.parts);
  const streaming = turn.status === "streaming";

  return (
    <div className="flex flex-col gap-2">
      {activity.length > 0 && <Activity parts={activity} live={streaming && !answer} />}
      {answer ? (
        <Markdown>{answer}</Markdown>
      ) : (
        streaming && activity.length === 0 && <p className="text-muted">Working…</p>
      )}
      {turn.error && <p className="text-sm text-danger">{turn.error}</p>}
    </div>
  );
});
