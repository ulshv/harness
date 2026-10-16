import { useChat } from "../chat/useChat";
import { Composer } from "../containers/Composer";
import { MessageList } from "../containers/MessageList";

export function ChatPage() {
  const { exchanges, busy, send } = useChat();

  return (
    <div className="mx-auto flex h-dvh max-w-3xl flex-col">
      <header className="border-b border-border px-4 py-3 font-semibold">harness</header>
      <main className="flex-1 overflow-y-auto px-4 py-6">
        <MessageList exchanges={exchanges} />
      </main>
      <footer className="border-t border-border p-4">
        <Composer busy={busy} onSend={send} />
      </footer>
    </div>
  );
}
