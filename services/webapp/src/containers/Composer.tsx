import { useState } from "react";
import { Button } from "../components/Button";
import { TextArea } from "../components/TextArea";

type Props = { busy: boolean; onSend: (message: string) => void };

// typing stays open while the agent works; only sending waits for the turn to end
export function Composer({ busy, onSend }: Props) {
  const [draft, setDraft] = useState("");
  const message = draft.trim();
  const canSend = !busy && message !== "";

  function submit() {
    if (!canSend) return;
    onSend(message);
    setDraft("");
  }

  return (
    <form
      className="flex items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <TextArea
        className="flex-1"
        rows={2}
        placeholder="Ask the agent…"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          // Enter sends, Shift+Enter is a newline; an Enter that confirms an IME candidate isn't a send
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <Button type="submit" disabled={!canSend}>
        Send
      </Button>
    </form>
  );
}
