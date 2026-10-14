import json

from langchain_core.messages import AIMessage


def sse_events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_tool_call_then_answer(make_client):
    client = make_client(
        [
            AIMessage(
                "", tool_calls=[{"name": "current_time", "args": {}, "id": "call_1"}]
            ),
            AIMessage("It is noon."),
        ]
    )

    resp = client.post("/chat", json={"message": "what time is it?"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = sse_events(resp.text)
    assert [name for name, _ in events] == ["tool_call", "tool_result", "token"]
    assert events[0][1] == {"id": "call_1", "name": "current_time", "args": {}}
    assert events[1][1]["tool_call_id"] == "call_1"
    assert events[1][1]["name"] == "current_time"
    assert events[2][1] == {"text": "It is noon."}


def test_answer_without_tools(make_client):
    client = make_client([AIMessage("Hi!")])

    resp = client.post("/chat", json={"message": "hello"})

    assert sse_events(resp.text) == [("token", {"text": "Hi!"})]


def test_empty_message_is_rejected(make_client):
    resp = make_client([AIMessage("unused")]).post("/chat", json={"message": ""})

    assert resp.status_code == 422
