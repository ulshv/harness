"""Translates a LangGraph run into chat events. Knows nothing about HTTP or SSE."""

from collections.abc import AsyncIterator, Callable, Iterable
from functools import singledispatch
from itertools import chain
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from app.api.chat.schemas import ChatEvent, TextEvent, ToolCallEvent, ToolResultEvent


async def chat_events(
    graph: CompiledStateGraph, message: str
) -> AsyncIterator[ChatEvent]:
    inputs = {"messages": [HumanMessage(message)]}
    # "messages" = LLM tokens as they arrive, "updates" = each node's finished output;
    # version="v2" yields typed parts {"type": <mode>, "ns": ..., "data": ...}
    async for part in graph.astream(
        inputs, stream_mode=["messages", "updates"], version="v2"
    ):
        for event in _BY_MODE[part["type"]](part["data"]):
            yield event


# "messages" part data: (chunk, metadata); metadata says which node produced it (langgraph_node, langgraph_step)
def _from_tokens(data: tuple[BaseMessage, dict[str, Any]]) -> Iterable[ChatEvent]:
    msg, _metadata = data
    # "messages" also replays finished ToolMessages; only AI text becomes a TextEvent
    if isinstance(msg, AIMessage) and msg.text:
        yield TextEvent(text=msg.text)


# "updates" part data: {node_name: what that node returned}, e.g. {"tools": {"messages": [ToolMessage]}}
def _from_updates(data: dict[str, Any]) -> Iterable[ChatEvent]:
    messages = chain.from_iterable(map(_written_messages, data.values()))
    return chain.from_iterable(map(_from_message, messages))


# a node's output isn't always {"messages": [...]}: None (no writes), a list (several writes),
# a single message, or service keys like "__interrupt__" (a tuple); only message writes matter
def _written_messages(output: Any) -> Iterable[BaseMessage]:
    match output:
        case {"messages": BaseMessage() as msg}:
            return (msg,)
        case {"messages": list() as msgs}:
            return msgs
        case list() | tuple():
            return chain.from_iterable(map(_written_messages, output))
        case _:
            return ()


# singledispatch picks the implementation by the runtime type of `msg`; this base one covers the rest
@singledispatch
def _from_message(msg: BaseMessage) -> Iterable[ChatEvent]:
    return ()


# the finished AI message: its text already went out as TextEvents, so only tool calls are new here
@_from_message.register
def _(msg: AIMessage) -> Iterable[ChatEvent]:
    return (
        ToolCallEvent(id=c["id"], name=c["name"], args=c["args"])
        for c in msg.tool_calls
    )


@_from_message.register
def _(msg: ToolMessage) -> Iterable[ChatEvent]:
    return (
        ToolResultEvent(tool_call_id=msg.tool_call_id, name=msg.name, content=msg.text),
    )


_BY_MODE: dict[str, Callable[[Any], Iterable[ChatEvent]]] = {
    "messages": _from_tokens,
    "updates": _from_updates,
}
