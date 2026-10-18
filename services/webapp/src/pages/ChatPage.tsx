import { useChat } from "../chat/useChat";
import { Button } from "../components/Button";
import { TailScroll } from "../components/TailScroll";
import { Composer } from "../containers/Composer";
import { MessageList } from "../containers/MessageList";

export function ChatPage() {
  const { exchanges, busy, threadId, send, newChat } = useChat();

  return (
    <div className="mx-auto flex h-dvh max-w-3xl flex-col">
      <header className="flex items-center justify-between border-b border-border px-4 py-2">
        <span className="font-semibold">harness</span>
        <Button variant="quiet" disabled={exchanges.length === 0} onClick={newChat}>
          New chat
        </Button>
      </header>
      {/* follows the streaming answer down the page while you're at the bottom; scroll up to read and it stays */}
      <main className="flex min-h-0 flex-1 flex-col">
        <TailScroll className="flex-1 px-4 py-6">
          <MessageList exchanges={exchanges} />
        </TailScroll>
      </main>
      <footer className="border-t border-border p-4">
        {/* keyed by thread: "New chat" remounts it, which clears the draft and puts the cursor back in it */}
        <Composer key={threadId} busy={busy} onSend={send} />
      </footer>
    </div>
  );
}
