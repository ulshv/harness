from collections.abc import AsyncIterable
from functools import cache
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.sse import EventSourceResponse, ServerSentEvent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from app.agent import build_graph, make_model

app = FastAPI(title="harness")


# a cached dependency: the graph is built once on first request, and tests swap it via dependency_overrides
@cache
def get_graph():
    return build_graph(make_model())


class ChatRequest(BaseModel):
    message: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_class=EventSourceResponse)
async def chat(
    req: ChatRequest, graph: Annotated[CompiledStateGraph, Depends(get_graph)]
) -> AsyncIterable[ServerSentEvent]:
    inputs = {"messages": [HumanMessage(req.message)]}
    # "messages" yields LLM tokens as they arrive, "updates" yields each node's finished output
    async for mode, data in graph.astream(inputs, stream_mode=["messages", "updates"]):
        if mode == "messages":
            msg, _meta = data
            if isinstance(msg, AIMessage) and msg.text:
                yield ServerSentEvent(event="token", data={"text": msg.text})
            continue
        for update in data.values():
            for msg in update["messages"]:
                if isinstance(msg, AIMessage):
                    for call in msg.tool_calls:
                        yield ServerSentEvent(
                            event="tool_call",
                            data={"name": call["name"], "args": call["args"]},
                        )
                elif isinstance(msg, ToolMessage):
                    yield ServerSentEvent(
                        event="tool_result",
                        data={"name": msg.name, "content": msg.content},
                    )
