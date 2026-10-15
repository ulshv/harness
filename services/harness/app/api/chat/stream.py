"""Translates a LangGraph run into chat events. Knows nothing about HTTP or SSE."""

from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from app.api.chat.schemas import (
    ChatEvent,
    ReasoningEvent,
    TextEvent,
    ToolCallEvent,
    ToolResultEvent,
)


async def chat_events(
    graph: CompiledStateGraph, message: str
) -> AsyncIterator[ChatEvent]:
    inputs = {"messages": [HumanMessage(message)]}
    # two views of one run: "messages" streams the LLM's output piece by piece (live text),
    # "updates" reports each finished step (whole tool calls and results); v2 tags each part with its mode
    async for part in graph.astream(
        inputs, stream_mode=["messages", "updates"], version="v2"
    ):
        for event in _BY_MODE[part["type"]](part["data"]):
            yield event


# Live LLM output: every piece becomes text or reasoning, so the user watches the answer being typed.
def _chunk_events(data: tuple[BaseMessage, dict[str, Any]]) -> Iterator[ChatEvent]:
    msg, _metadata = data
    # tool results pass through here too; they're taken from "updates" instead
    if not isinstance(msg, AIMessage):
        return
    # content_blocks look the same for every provider: DeepSeek's reasoning and Anthropic's thinking are
    # both "reasoning"; pieces of tool calls are skipped, they arrive whole in "updates"
    for block in msg.content_blocks:
        match block:
            case {"type": "text", "text": str(text)} if text:
                yield TextEvent(text=text)
            # some providers send reasoning without text (only a signature): nothing to show
            case {"type": "reasoning", "reasoning": str(text)} if text:
                yield ReasoningEvent(text=text)


# Finished steps: tool calls arrive here with complete arguments, tool results as a whole.
def _update_events(data: dict[str, Any]) -> Iterator[ChatEvent]:
    for output in data.values():
        for msg in _written_messages(output):
            yield from _message_events(msg)


def _message_events(msg: BaseMessage) -> Iterator[ChatEvent]:
    match msg:
        # the agent's finished reply: its text already went out live, only the tool calls are new
        case AIMessage(tool_calls=calls):
            for c in calls:
                yield ToolCallEvent(id=c["id"], name=c["name"], args=c["args"])
        case ToolMessage():
            yield ToolResultEvent(
                tool_call_id=msg.tool_call_id, name=msg.name, content=msg.text
            )


# Nodes report what they wrote in different shapes: nothing, one message, a list, or a batch of
# several writes. Dig out the messages and ignore the rest (interrupts, cache metadata).
def _written_messages(output: Any) -> Iterator[BaseMessage]:
    match output:
        case {"messages": BaseMessage() as msg}:
            yield msg
        case {"messages": list() as msgs}:
            yield from msgs
        case list() | tuple():
            for item in output:
                yield from _written_messages(item)


_BY_MODE: dict[str, Callable[[Any], Iterator[ChatEvent]]] = {
    "messages": _chunk_events,
    "updates": _update_events,
}
