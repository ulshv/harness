from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class _Event(BaseModel):
    # `type` has a default, but it's always serialized: mark it required in the OpenAPI schema
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


# `type` tells events apart in JSON (/chat/invoke); in SSE the `event:` line carries it instead.
class TextEvent(_Event):
    type: Literal["text"] = "text"
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


# discriminator → OpenAPI oneOf + mapping, so generated clients can narrow the union by `type`
type ChatEvent = Annotated[
    TextEvent | ToolCallEvent | ToolResultEvent, Field(discriminator="type")
]


class ChatResponse(BaseModel):
    events: list[ChatEvent]
