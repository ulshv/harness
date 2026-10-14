import math
from collections.abc import AsyncIterable

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.api.chat.batching import batch_events
from app.api.chat.outcome import append_error_or_done
from app.api.chat.schemas import ChatRequest, ChatResponse, ErrorEvent
from app.api.chat.stream import chat_events
from app.api.deps import Graph

router = APIRouter(prefix="/chat")


# an async generator + EventSourceResponse: each `yield` is flushed to the client as an SSE frame right away
@router.post("/stream", response_class=EventSourceResponse)
async def stream(req: ChatRequest, graph: Graph) -> AsyncIterable[ServerSentEvent]:
    # append_error_or_done sits before batching: done/error are non-text events, so buffered text flushes first
    events = batch_events(append_error_or_done(chat_events(graph, req.message)))
    async for event in events:
        # the SSE event name already says what it is, so `type` stays out of the payload;
        # raw_data + model_dump_json keeps pydantic's compact JSON (a dict would go through json.dumps, with spaces)
        yield ServerSentEvent(
            event=event.type, raw_data=event.model_dump_json(exclude={"type"})
        )


# explicit response_model: FastAPI can't infer one from a `ChatResponse | JSONResponse` annotation
@router.post(
    "/invoke", response_model=ChatResponse, responses={500: {"model": ErrorEvent}}
)
async def invoke(req: ChatRequest, graph: Graph) -> ChatResponse | JSONResponse:
    # infinite window: time never flushes, so each contiguous text/reasoning run merges into one event
    stream = batch_events(
        append_error_or_done(chat_events(graph, req.message)), window=math.inf
    )
    events = [event async for event in stream]
    if isinstance(events[-1], ErrorEvent):
        return JSONResponse(events[-1].model_dump(), status_code=500)
    return ChatResponse(events=events)
