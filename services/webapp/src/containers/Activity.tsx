import { useState, type ReactNode } from "react";
import { Spinner } from "../components/Spinner";
import { TailScroll } from "../components/TailScroll";
import { describeActivity, type Part, type ToolPart } from "../chat/turn";

// the live block's height, padding included; `lh` is the element's own line height, so it's lines, not pixels
const ACTIVITY_MAX_LINES = 6;

// The agent's steps before the answer. While the agent works it's open and follows the newest step; once the
// answer starts (or the turn ends) it folds into one line that expands on click.
export function Activity({ parts, live }: { parts: Part[]; live: boolean }) {
  const [open, setOpen] = useState(false);
  const steps = parts.map((part, i) => (
    <Step key={i} part={part} live={live} last={i === parts.length - 1} />
  ));

  return (
    <section className="rounded-lg border border-border bg-surface text-sm">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-muted"
        disabled={live}
        aria-expanded={live || open}
        onClick={() => setOpen(!open)}
      >
        {live ? (
          <Spinner />
        ) : (
          <span aria-hidden className="w-3">
            {open ? "▾" : "▸"}
          </span>
        )}
        {describeActivity(parts)}
      </button>
      {live ? (
        <TailScroll
          className="border-t border-border px-3 py-2"
          style={{ maxHeight: `${ACTIVITY_MAX_LINES}lh` }}
        >
          {steps}
        </TailScroll>
      ) : (
        open && <div className="border-t border-border px-3 py-2">{steps}</div>
      )}
    </section>
  );
}

function Step({ part, live, last }: { part: Part; live: boolean; last: boolean }) {
  switch (part.kind) {
    case "reasoning":
      return <ReasoningStep text={part.text} thinking={live && last} />;
    case "text":
      // said before a tool call: an interim note, not the answer
      return <p className="whitespace-pre-wrap">{part.text}</p>;
    case "tool":
      return <ToolStep tool={part} live={live} />;
  }
}

// Thoughts fold under one line like a tool's result, so the steps stay scannable. Reasoning has no end event:
// it's over once anything follows it (or the block stops being live)
function ReasoningStep({ text, thinking }: { text: string; thinking: boolean }) {
  return (
    <Disclosure
      summary={
        <>
          {thinking ? <Spinner /> : <span className="w-3 text-success">✓</span>}
          <span className="text-muted">{thinking ? "Thinking…" : "Thinking"}</span>
        </>
      }
    >
      <p className="mt-1 mb-2 whitespace-pre-wrap text-muted italic">{text}</p>
    </Disclosure>
  );
}

// the call on the summary line, the result behind the toggle
function ToolStep({ tool, live }: { tool: ToolPart; live: boolean }) {
  const call = (
    <>
      <StatusMark tool={tool} live={live} />
      <code className="truncate">
        {tool.name}({formatArgs(tool.args)})
      </code>
    </>
  );
  if (!tool.result) {
    return (
      <div className="flex items-center gap-2">
        <span className="w-3" />
        {call}
      </div>
    );
  }

  return (
    <Disclosure summary={call}>
      <pre className="mt-1 mb-2 overflow-x-auto rounded bg-bg p-2 text-xs">
        {prettyJson(tool.result.content)}
      </pre>
    </Disclosure>
  );
}

// a step whose details open on click: a native <details> toggle, no state needed
function Disclosure({ summary, children }: { summary: ReactNode; children: ReactNode }) {
  return (
    <details className="group">
      {/* a flex <summary> loses the native marker (and Safari's needs hiding), so it draws its own */}
      <summary className="flex cursor-pointer list-none items-center gap-2 [&::-webkit-details-marker]:hidden">
        <span aria-hidden className="w-3 text-muted transition-transform group-open:rotate-90">
          ▸
        </span>
        {summary}
      </summary>
      {children}
    </details>
  );
}

function StatusMark({ tool, live }: { tool: ToolPart; live: boolean }) {
  switch (tool.result?.status) {
    case undefined:
      // no result and the turn moved on (an error, a dropped stream): it never finished, don't spin forever
      return live ? <Spinner /> : <span className="w-3 text-muted">–</span>;
    case "success":
      return <span className="w-3 text-success">✓</span>;
    case "error":
      return <span className="w-3 text-danger">✗</span>;
  }
}

// `wms_get_stock(sku: "TAPE-48")`: the values stay JSON so strings and numbers look different
function formatArgs(args: ToolPart["args"]): string {
  return Object.entries(args)
    .map(([key, value]) => `${key}: ${JSON.stringify(value)}`)
    .join(", ");
}

// MCP tools return the API body as a JSON string; indent it, show anything else as is
function prettyJson(content: string): string {
  try {
    return JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    return content;
  }
}
