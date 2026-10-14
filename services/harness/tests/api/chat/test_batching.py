import asyncio
import math

from app.api.chat import batching
from app.api.chat.batching import batch_text_events
from app.api.chat.schemas import TextEvent, ToolCallEvent

CALL = ToolCallEvent(id="c1", name="current_time", args={})


def coalesce(events, window):
    async def source():
        for event in events:
            yield event

    async def run():
        return [event async for event in batch_text_events(source(), window)]

    return asyncio.run(run())


def test_zero_window_keeps_every_chunk():
    chunks = [TextEvent(text="a"), TextEvent(text="b")]

    assert coalesce(chunks, window=0) == [TextEvent(text="a"), TextEvent(text="b")]


def test_window_counts_from_the_first_buffered_chunk(monkeypatch):
    # the clock is read once per text event: a=0.00 b=0.03 c=0.06 (≥ 0.05 → flush "abc") d=0.07
    monkeypatch.setattr(batching, "monotonic", iter([0.00, 0.03, 0.06, 0.07]).__next__)
    chunks = [TextEvent(text=t) for t in "abcd"]

    assert coalesce(chunks, window=0.05) == [TextEvent(text="abc"), TextEvent(text="d")]


def test_other_events_flush_the_buffer_first():
    events = [TextEvent(text="a"), TextEvent(text="b"), CALL, TextEvent(text="c")]

    assert coalesce(events, window=math.inf) == [
        TextEvent(text="ab"),
        CALL,
        TextEvent(text="c"),
    ]
