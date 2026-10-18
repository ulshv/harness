from collections.abc import Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Send

from app.agent.errors import handle_tool_errors


def build_graph(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    *,
    system_prompt: str,
    recursion_limit: int,
) -> CompiledStateGraph:
    # bind_tools only attaches JSON schemas to each request; executing tools is the graph's job
    llm = model.bind_tools(tools)

    # a node is just a function: gets the current state, returns a partial update
    async def agent(state: MessagesState):
        # the system prompt goes in front of every call and never into the state, so it isn't checkpointed
        reply = await llm.ainvoke([SystemMessage(system_prompt), *state["messages"]])
        # MessagesState's add_messages reducer appends the reply instead of replacing the list
        return {"messages": [reply]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent)
    # answers each tool call with a ToolMessage(tool_call_id=...); a failing tool too, with status="error"
    builder.add_node("tools", ToolNode(tools, handle_tool_errors=handle_tool_errors))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", send_tool_calls, ["tools", END])
    builder.add_edge("tools", "agent")
    # the checkpointer saves the state after every step under the run's thread_id, and the next run on that thread
    # starts from it
    graph = builder.compile(checkpointer=InMemorySaver())
    return graph.with_config(recursion_limit=recursion_limit)


# Each tool call goes to "tools" as a task of its own. The calls still run in parallel, but each result streams
# out as soon as it's ready; a single ToolNode run for all of them would report them together, after the slowest
def send_tool_calls(state: MessagesState) -> list[Send] | str:
    last = state["messages"][-1]
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return END
    return [Send("tools", [call]) for call in last.tool_calls]
