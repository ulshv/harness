from collections.abc import AsyncIterable

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent
from langchain_core.messages import HumanMessage

from app.api.chat.schemas import ChatRequest
from app.api.chat.stream import chat_events
from app.api.deps import Graph

router = APIRouter()


# an async generator + EventSourceResponse: each `yield` is flushed to the client as an SSE frame right away
@router.post("/chat", response_class=EventSourceResponse)
async def chat(req: ChatRequest, graph: Graph) -> AsyncIterable[ServerSentEvent]:
    async for event in chat_events(graph, {"messages": [HumanMessage(req.message)]}):
        yield ServerSentEvent(event=event.event, data=event)
