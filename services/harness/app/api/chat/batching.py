"""Merges adjacent text events to cut per-frame SSE overhead. Knows nothing about HTTP."""

from collections.abc import AsyncIterable, AsyncIterator
from time import monotonic

from app.api.chat.schemas import ChatEvent, TextEvent

# ~20 frames/s still reads as smooth typing; ~10x fewer frames than one per LLM token (measured on DeepSeek)
TEXT_FLUSH_INTERVAL = 0.05


async def batch_text_events(
    events: AsyncIterable[ChatEvent], window: float = TEXT_FLUSH_INTERVAL
) -> AsyncIterator[ChatEvent]:
    # flush when a text event finds the buffer `window` old, before any other event, and at the end.
    # No timer: if the source stalls mid-text, buffered text waits for the next event.
    text, started = "", 0.0
    async for event in events:
        if isinstance(event, TextEvent):
            now = monotonic()
            started = started if text else now
            text += event.text
            if now - started >= window:
                yield TextEvent(text=text)
                text = ""
            continue
        if text:
            yield TextEvent(text=text)
            text = ""
        yield event
    if text:
        yield TextEvent(text=text)
