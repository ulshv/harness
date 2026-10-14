from typing import Any, ClassVar

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


# SSE contract: `event` is the SSE event name, the model itself is the JSON `data`.
# ClassVar keeps the name out of the payload.
class Token(BaseModel):
    event: ClassVar[str] = "token"
    text: str


class ToolCall(BaseModel):
    event: ClassVar[str] = "tool_call"
    id: str | None
    name: str
    args: dict[str, Any]


class ToolResult(BaseModel):
    event: ClassVar[str] = "tool_result"
    tool_call_id: str
    name: str | None
    content: str


type ChatEvent = Token | ToolCall | ToolResult
