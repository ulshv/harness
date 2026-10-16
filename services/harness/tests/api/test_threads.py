from langchain_core.messages import AIMessage

from tests.conftest import FakeToolModel


def texts(messages) -> list[str]:
    return [m.text for m in messages]


def ask(client, message: str, **body) -> list[dict]:
    resp = client.post("/chat/invoke", json={"message": message, **body})
    assert resp.status_code == 200
    return resp.json()["events"]


def test_a_thread_remembers_the_conversation(make_client):
    model = FakeToolModel(responses=[AIMessage("Hi, Sergey."), AIMessage("Sergey.")])
    client = make_client(model)

    ask(client, "My name is Sergey.", thread_id="t1")
    second = ask(client, "What is my name?", thread_id="t1")

    # the restored history isn't replayed: the second turn streams only its own run
    assert second == [{"type": "text", "text": "Sergey."}, {"type": "done"}]
    # [0] is the system prompt, prepended per call and never saved
    assert texts(model.inputs[1][1:]) == [
        "My name is Sergey.",
        "Hi, Sergey.",
        "What is my name?",
    ]
    state = client.app.state.graph.get_state({"configurable": {"thread_id": "t1"}})
    assert texts(state.values["messages"]) == [
        "My name is Sergey.",
        "Hi, Sergey.",
        "What is my name?",
        "Sergey.",
    ]


def test_without_a_thread_id_each_request_starts_fresh(make_client):
    model = FakeToolModel(responses=[AIMessage("Hi."), AIMessage("I don't know.")])
    client = make_client(model)

    ask(client, "My name is Sergey.")
    ask(client, "What is my name?")

    assert texts(model.inputs[1][1:]) == ["What is my name?"]


def test_thread_id_format(make_client):
    client = make_client([AIMessage("ok")])

    for bad in ["bad id!", "", "x" * 65, None]:
        resp = client.post("/chat/invoke", json={"message": "hi", "thread_id": bad})
        assert resp.status_code == 422, bad
