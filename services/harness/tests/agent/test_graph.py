import asyncio

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent.graph import build_graph
from tests.conftest import FakeToolModel


def test_prompt_and_limit_reach_the_graph():
    model = FakeToolModel(responses=[AIMessage("Ok.")])

    graph = build_graph(model, [], system_prompt="X", recursion_limit=61)
    asyncio.run(
        graph.ainvoke(
            {"messages": [HumanMessage("Hi")]},
            {"configurable": {"thread_id": "t1"}},
        )
    )

    assert graph.config is not None
    assert graph.config.get("recursion_limit") == 61
    assert model.inputs[0][0] == SystemMessage("X")
