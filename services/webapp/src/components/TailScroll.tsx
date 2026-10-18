import { useEffect, useRef, type ComponentProps } from "react";

// how close to the bottom still counts as "at the bottom": sub-pixel rounding makes an exact 0 unreliable
const PIN_SLACK_PX = 8;

type Props = Omit<ComponentProps<"div">, "ref" | "onScroll">;

// A scroll box that follows its content as it grows, like `tail -f`, until the user scrolls up; scrolling back
// to the bottom pins it again. A ResizeObserver on the content catches growth from any cause, not just renders.
export function TailScroll({ children, className = "", ...props }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const lastTop = useRef(0);

  useEffect(() => {
    const observer = new ResizeObserver(() => {
      const el = box.current;
      if (!el) return;
      // content that fits has nothing to scroll away from; shrinking (a cleared chat) clamps scrollTop without
      // a scroll event, so re-pin here
      if (el.scrollHeight <= el.clientHeight) {
        pinned.current = true;
        lastTop.current = 0;
      }
      if (pinned.current) el.scrollTop = el.scrollHeight;
    });
    if (content.current) observer.observe(content.current);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      {...props}
      ref={box}
      className={`overflow-y-auto ${className}`}
      onScroll={(e) => {
        const el = e.currentTarget;
        const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= PIN_SLACK_PX;
        // Only an upward scroll lets go: our own scroll event arrives a frame late, and content that grew in
        // between would look like "not at the bottom". Growth never moves scrollTop up, a user does.
        if (el.scrollTop < lastTop.current) pinned.current = atBottom;
        else if (atBottom) pinned.current = true;
        lastTop.current = el.scrollTop;
      }}
    >
      <div ref={content}>{children}</div>
    </div>
  );
}
