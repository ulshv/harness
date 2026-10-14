from langchain_core.messages import AIMessage


def test_health(make_client):
    resp = make_client([AIMessage("unused")]).get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
