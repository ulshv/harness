from langchain_core.messages import AIMessage
from langchain_core.tools import tool


@tool
def explode() -> str:
    """Always fails, like a tool whose service is down."""
    raise RuntimeError("secret http://internal-host:8101/mcp")


@tool
def double(x: int) -> int:
    """Double a number."""
    return x * 2


def call(name: str, args: dict) -> AIMessage:
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": "call_1"}])


def run(make_client, tools, first_call: AIMessage) -> list[dict]:
    client = make_client([first_call, AIMessage("Sorry, that failed.")], tools=tools)
    resp = client.post("/chat/invoke", json={"message": "go"})
    assert resp.status_code == 200
    return resp.json()["events"]


def test_a_crashing_tool_becomes_an_error_result_and_the_run_finishes(make_client):
    events = run(make_client, [explode], call("explode", {}))

    assert events[1] == {
        "type": "tool_result",
        "tool_call_id": "call_1",
        "name": "explode",
        "content": "The tool failed to run.",
        "status": "error",
    }
    assert events[-1] == {"type": "done"}


def test_bad_arguments_keep_their_details_for_the_model(make_client):
    events = run(make_client, [double], call("double", {"x": "abc"}))

    assert events[1]["status"] == "error"
    assert events[1]["content"].startswith("Error invoking tool 'double'")
    assert "valid integer" in events[1]["content"]
