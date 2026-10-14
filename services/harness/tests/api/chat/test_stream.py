import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.api.chat.schemas import ToolCall, ToolResult
from app.api.chat.stream import _from_updates

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
        ToolCall(id="c1", name="current_time", args={}),
        ToolResult(tool_call_id="c1", name="current_time", content="12:00"),
    ]
