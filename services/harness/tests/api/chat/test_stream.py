import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from app.api.chat.schemas import (
    ReasoningEvent,
    TextEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from app.api.chat.stream import _from_tokens, _from_updates

CALL = AIMessage("", tool_calls=[{"name": "current_time", "args": {}, "id": "c1"}])
RESULT = ToolMessage("12:00", tool_call_id="c1", name="current_time")


@pytest.mark.parametrize(
    "data",
    [
        {"agent": None},
        {"agent": {}},
        {"__interrupt__": ()},
        {"__metadata__": {"cached": True}},
    ],
)
def test_updates_without_messages_give_no_events(data):
    assert list(_from_updates(data)) == []


def test_updates_with_messages_in_every_shape():
    data = {
        "agent": {"messages": CALL},
        "tools": [{"messages": [RESULT]}],
    }

    assert list(_from_updates(data)) == [
        ToolCallEvent(id="c1", name="current_time", args={}),
        ToolResultEvent(tool_call_id="c1", name="current_time", content="12:00"),
    ]


@pytest.mark.parametrize(
    ("msg", "events"),
    [
        (
            AIMessageChunk(content="", additional_kwargs={"reasoning_content": "We"}),
            [ReasoningEvent(text="We")],
        ),
        (AIMessageChunk(content="391"), [TextEvent(text="391")]),
        # one chunk with both: reasoning comes first
        (
            AIMessageChunk(
                content="391", additional_kwargs={"reasoning_content": "We"}
            ),
            [ReasoningEvent(text="We"), TextEvent(text="391")],
        ),
        # a signature-only reasoning block (no text): skipped, not a KeyError
        (AIMessageChunk(content=[{"type": "reasoning"}]), []),
        (
            AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {"name": "current_time", "args": "", "id": "c1", "index": 0}
                ],
            ),
            [],
        ),
        (AIMessageChunk(content=""), []),
        (ToolMessage("12:00", tool_call_id="c1"), []),
    ],
)
def test_token_chunks_become_text_or_reasoning(msg, events):
    assert list(_from_tokens((msg, {}))) == events
