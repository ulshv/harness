from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# a client-chosen conversation id: safe to log and to use as a storage key later
ThreadId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    # omitted → a fresh thread per request, a single turn as before; default_factory instead of `| None` keeps
    # OpenAPI a plain optional string and rejects an explicit null
    thread_id: ThreadId = Field(default_factory=lambda: str(uuid4()))


class _Event(BaseModel):
    # `type` has a default, but it's always serialized: mark it required in the OpenAPI schema
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


# `type` tells events apart in JSON (/chat/invoke); in SSE the `event:` line carries it instead.
class TextEvent(_Event):
    type: Literal["text"] = "text"
    text: str


# the model's thinking before/between answers; the frontend shows it in a spoiler
class ReasoningEvent(_Event):
    type: Literal["reasoning"] = "reasoning"
    text: str


class ToolCallEvent(_Event):
    type: Literal["tool_call"] = "tool_call"
    id: str | None
    name: str
    args: dict[str, Any]


class ToolResultEvent(_Event):
    type: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    name: str | None
    content: str


# terminal events: every run ends with exactly one of these two
class DoneEvent(_Event):
    type: Literal["done"] = "done"


type ErrorCode = Literal[
    "llm_unavailable", "llm_rate_limited", "recursion_limit", "internal"
]


class ErrorEvent(_Event):
    type: Literal["error"] = "error"
    code: ErrorCode
    message: str


# discriminator → OpenAPI oneOf + mapping, so generated clients can narrow the union by `type`
type ChatEvent = Annotated[
    TextEvent
    | ReasoningEvent
    | ToolCallEvent
    | ToolResultEvent
    | DoneEvent
    | ErrorEvent,
    Field(discriminator="type"),
]


class ChatResponse(BaseModel):
    events: list[ChatEvent]
