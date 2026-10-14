import math
from collections.abc import AsyncIterable

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.api.chat.batching import batch_text_events
from app.api.chat.schemas import ChatRequest, ChatResponse
from app.api.chat.stream import chat_events
from app.api.deps import Graph

router = APIRouter(prefix="/chat")


# an async generator + EventSourceResponse: each `yield` is flushed to the client as an SSE frame right away
@router.post("/stream", response_class=EventSourceResponse)
async def stream(req: ChatRequest, graph: Graph) -> AsyncIterable[ServerSentEvent]:
    async for event in batch_text_events(chat_events(graph, req.message)):
        # the SSE event name already says what it is, so `type` stays out of the payload;
        # raw_data + model_dump_json keeps pydantic's compact JSON (a dict would go through json.dumps, with spaces)
        yield ServerSentEvent(
            event=event.type, raw_data=event.model_dump_json(exclude={"type"})
        )


@router.post("/invoke")
async def invoke(req: ChatRequest, graph: Graph) -> ChatResponse:
    # infinite window: time never flushes, so each contiguous run of text merges into one event
    events = batch_text_events(chat_events(graph, req.message), window=math.inf)
    return ChatResponse(events=[event async for event in events])
