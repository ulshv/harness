import { Bubble } from "../components/Bubble";
import type { Exchange } from "../chat/turn";
import { Reply } from "./Reply";

export function MessageList({ exchanges }: { exchanges: Exchange[] }) {
  return (
    <ol className="flex flex-col gap-6">
      {exchanges.map((x) => (
        <li key={x.id} className="flex flex-col gap-3">
          <Bubble>{x.message}</Bubble>
          <Reply turn={x.reply} />
        </li>
      ))}
    </ol>
  );
}
