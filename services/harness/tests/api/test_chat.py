import json

import pytest
from langchain_core.messages import AIMessage

TOOL_THEN_ANSWER = [
    AIMessage("", tool_calls=[{"name": "current_time", "args": {}, "id": "call_1"}]),
    AIMessage("It is noon."),
]


def sse_events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_stream_tool_call_then_answer(make_client):
    resp = make_client(TOOL_THEN_ANSWER).post("/chat/stream", json={"message": "time?"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = sse_events(resp.text)
    assert [name for name, _ in events] == ["tool_call", "tool_result", "text"]
    assert events[0][1] == {"id": "call_1", "name": "current_time", "args": {}}
    assert events[1][1]["tool_call_id"] == "call_1"
    assert events[2][1] == {"text": "It is noon."}
    assert all("type" not in data for _, data in events)


def test_invoke_returns_the_whole_run(make_client):
    resp = make_client(TOOL_THEN_ANSWER).post("/chat/invoke", json={"message": "time?"})

    assert resp.status_code == 200
    events = resp.json()["events"]
    assert events[1].pop("content")  # the real current time, not deterministic
    assert events == [
        {"type": "tool_call", "id": "call_1", "name": "current_time", "args": {}},
        {"type": "tool_result", "tool_call_id": "call_1", "name": "current_time"},
        {"type": "text", "text": "It is noon."},
    ]


def test_invoke_plain_answer(make_client):
    resp = make_client([AIMessage("Hi!")]).post(
        "/chat/invoke", json={"message": "hello"}
    )

    assert resp.json() == {"events": [{"type": "text", "text": "Hi!"}]}


@pytest.mark.parametrize("route", ["/chat/stream", "/chat/invoke"])
def test_empty_message_is_rejected(make_client, route):
    resp = make_client([AIMessage("unused")]).post(route, json={"message": ""})

    assert resp.status_code == 422


def test_old_chat_route_is_gone(make_client):
    resp = make_client([AIMessage("unused")]).post("/chat", json={"message": "hi"})

    assert resp.status_code == 404


def test_invoke_schema_discriminates_events_by_type(make_client):
    resp = make_client([AIMessage("unused")]).get("/openapi.json")
    schemas = resp.json()["components"]["schemas"]

    assert schemas["ChatResponse"]["properties"]["events"]["items"] == {
        "$ref": "#/components/schemas/ChatEvent"
    }
    assert schemas["ChatEvent"]["discriminator"] == {
        "propertyName": "type",
        "mapping": {
            "text": "#/components/schemas/TextEvent",
            "tool_call": "#/components/schemas/ToolCallEvent",
            "tool_result": "#/components/schemas/ToolResultEvent",
        },
    }
    assert "type" in schemas["TextEvent"]["required"]
