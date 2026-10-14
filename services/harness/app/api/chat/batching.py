"""Merges adjacent text/reasoning events to cut per-frame SSE overhead. Knows nothing about HTTP."""

from collections.abc import AsyncIterable, AsyncIterator
from time import monotonic

from app.api.chat.schemas import ChatEvent, ReasoningEvent, TextEvent

# for text and reasoning runs alike: ~20 frames/s reads as smooth typing, ~10x fewer frames than one per LLM token
FLUSH_INTERVAL = 0.05

# streamed in many small chunks; runs of the same kind merge into one event
type _Mergeable = TextEvent | ReasoningEvent


async def batch_events(
    events: AsyncIterable[ChatEvent], window: float = FLUSH_INTERVAL
) -> AsyncIterator[ChatEvent]:
    # flush when a chunk finds the buffer `window` old, when the kind changes (reasoning → text),
    # before any other event, and at the end.
    # No timer: if the source stalls mid-text, buffered text waits for the next event.
    pending: _Mergeable | None = None
    started = 0.0
    async for event in events:
        if not isinstance(event, TextEvent | ReasoningEvent):
            if pending:
                yield pending
            pending = None
            yield event
            continue
        now = monotonic()
        if pending and type(pending) is type(event):
            pending = type(event)(text=pending.text + event.text)
        else:
            if pending:
                yield pending
            pending, started = event, now
        if now - started >= window:
            yield pending
            pending = None
    if pending:
        yield pending
