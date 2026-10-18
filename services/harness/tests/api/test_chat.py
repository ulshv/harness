import asyncio
import json

import pytest
from langchain_core.exceptions import ModelConnectionError
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from tests.conftest import StreamingFakeModel


# fresh objects per call: add_messages sets `id` on the message in place, and the same object
# added twice is *replaced* (same id), not appended, which would silently end the ReAct loop
def call_tool() -> AIMessage:
    return AIMessage(
        "", tool_calls=[{"name": "current_time", "args": {}, "id": "call_1"}]
    )


def tool_then_answer() -> list[AIMessage]:
    return [call_tool(), AIMessage("It is noon.")]


PROVIDER_DOWN = ModelConnectionError("connection refused")
LLM_UNAVAILABLE = {
    "code": "llm_unavailable",
    "message": "The language model provider is unavailable. Try again later.",
}


def sse_events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_stream_tool_call_then_answer(make_client):
    resp = make_client(tool_then_answer()).post(
        "/chat/stream", json={"message": "time?"}
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = sse_events(resp.text)
    assert [name for name, _ in events] == ["tool_call", "tool_result", "text", "done"]
    assert events[0][1] == {"id": "call_1", "name": "current_time", "args": {}}
    assert events[1][1]["tool_call_id"] == "call_1"
    assert events[2][1] == {"text": "It is noon."}
    assert events[3][1] == {}
    assert all("type" not in data for _, data in events)


@tool
async def slow_lookup() -> str:
    """Answers after a while."""
    await asyncio.sleep(0.2)
    return "slow"


@tool
async def fast_lookup() -> str:
    """Answers at once."""
    return "fast"


def test_parallel_tool_results_stream_as_each_one_finishes(make_client):
    calls = AIMessage(
        "",
        tool_calls=[
            {"name": "slow_lookup", "args": {}, "id": "call_slow"},
            {"name": "fast_lookup", "args": {}, "id": "call_fast"},
        ],
    )
    client = make_client([calls, AIMessage("Done.")], tools=[slow_lookup, fast_lookup])

    events = client.post("/chat/invoke", json={"message": "both"}).json()["events"]

    assert [(e["type"], e.get("id") or e.get("tool_call_id")) for e in events[:4]] == [
        ("tool_call", "call_slow"),
        ("tool_call", "call_fast"),
        ("tool_result", "call_fast"),
        ("tool_result", "call_slow"),
    ]


def test_invoke_returns_the_whole_run(make_client):
    resp = make_client(tool_then_answer()).post(
        "/chat/invoke", json={"message": "time?"}
    )

    assert resp.status_code == 200
    events = resp.json()["events"]
    assert events[1].pop("content")  # the real current time, not deterministic
    assert events == [
        {"type": "tool_call", "id": "call_1", "name": "current_time", "args": {}},
        {
            "type": "tool_result",
            "tool_call_id": "call_1",
            "name": "current_time",
            "status": "success",
        },
        {"type": "text", "text": "It is noon."},
        {"type": "done"},
    ]


def test_invoke_plain_answer(make_client):
    resp = make_client([AIMessage("Hi!")]).post(
        "/chat/invoke", json={"message": "hello"}
    )

    assert resp.json() == {
        "events": [{"type": "text", "text": "Hi!"}, {"type": "done"}]
    }


def test_stream_reasoning_then_answer(make_client):
    model = StreamingFakeModel(reasoning=["Let", " me"], chunks=["Hi"])

    resp = make_client(model).post("/chat/stream", json={"message": "hi"})

    assert sse_events(resp.text) == [
        ("reasoning", {"text": "Let me"}),
        ("text", {"text": "Hi"}),
        ("done", {}),
    ]


def test_invoke_merges_reasoning_like_text(make_client):
    model = StreamingFakeModel(reasoning=["Let", " me"], chunks=["H", "i"])

    resp = make_client(model).post("/chat/invoke", json={"message": "hi"})

    assert resp.json() == {
        "events": [
            {"type": "reasoning", "text": "Let me"},
            {"type": "text", "text": "Hi"},
            {"type": "done"},
        ]
    }


def test_stream_delivers_buffered_text_before_the_error(make_client):
    model = StreamingFakeModel(chunks=["Hel", "lo"], error=PROVIDER_DOWN)

    resp = make_client(model).post("/chat/stream", json={"message": "hi"})

    assert resp.status_code == 200
    assert sse_events(resp.text) == [
        ("text", {"text": "Hello"}),
        ("error", LLM_UNAVAILABLE),
    ]


def test_stream_error_before_any_event(make_client):
    model = StreamingFakeModel(chunks=[], error=PROVIDER_DOWN)

    resp = make_client(model).post("/chat/stream", json={"message": "hi"})

    assert resp.status_code == 200
    assert sse_events(resp.text) == [("error", LLM_UNAVAILABLE)]


def test_stream_reports_an_endless_tool_loop(make_client):
    # more tool rounds than DEFAULT_RECURSION_LIMIT=25 lets through (11 rounds + the answer)
    endless = [call_tool() for _ in range(30)]

    resp = make_client(endless).post("/chat/stream", json={"message": "loop"})

    assert sse_events(resp.text)[-1] == (
        "error",
        {
            "code": "recursion_limit",
            "message": "The agent took too many steps without finishing.",
        },
    )


def test_invoke_failure_is_500_with_the_error_event(make_client):
    model = StreamingFakeModel(chunks=["Hel"], error=PROVIDER_DOWN)

    resp = make_client(model).post("/chat/invoke", json={"message": "hi"})

    assert resp.status_code == 500
    assert resp.json() == {"type": "error", **LLM_UNAVAILABLE}


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
            "reasoning": "#/components/schemas/ReasoningEvent",
            "tool_call": "#/components/schemas/ToolCallEvent",
            "tool_result": "#/components/schemas/ToolResultEvent",
            "done": "#/components/schemas/DoneEvent",
            "error": "#/components/schemas/ErrorEvent",
        },
    }
    assert "type" in schemas["TextEvent"]["required"]
    invoke = resp.json()["paths"]["/chat/invoke"]["post"]["responses"]
    assert invoke["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorEvent"
    }
