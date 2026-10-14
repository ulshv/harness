import json

from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from app.agent import build_graph
from app.main import app, get_graph


class FakeToolModel(FakeMessagesListChatModel):
    # the stock fakes raise on bind_tools; scripted replies already contain the tool calls
    def bind_tools(self, tools, **kwargs):
        return self


def sse_events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_chat_calls_tool_and_streams_answer():
    model = FakeToolModel(
        responses=[
            AIMessage(
                "", tool_calls=[{"name": "current_time", "args": {}, "id": "call_1"}]
            ),
            AIMessage("It is noon."),
        ]
    )
    app.dependency_overrides[get_graph] = lambda: build_graph(model)
    try:
        resp = TestClient(app).post("/chat", json={"message": "what time is it?"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = sse_events(resp.text)
    assert [name for name, _ in events] == ["tool_call", "tool_result", "token"]
    assert events[0][1] == {"name": "current_time", "args": {}}
    assert events[1][1]["name"] == "current_time"
    assert events[2][1] == {"text": "It is noon."}
