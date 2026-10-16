from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.tools import TOOLS

SYSTEM_PROMPT = "You are a concise assistant. Use tools when they help."
# LangGraph 1.2 defaults to 10007 supersteps; a tool round is 2 (agent + tools): 25 allows 11 rounds + the answer
RECURSION_LIMIT = 25


def build_graph(model: BaseChatModel) -> CompiledStateGraph:
    # bind_tools only attaches JSON schemas to each request; executing tools is the graph's job
    llm = model.bind_tools(TOOLS)

    # a node is just a function: gets the current state, returns a partial update
    async def agent(state: MessagesState):
        # system prompt is prepended per call, not stored in state (so it won't be checkpointed)
        reply = await llm.ainvoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]])
        # MessagesState's add_messages reducer appends this to the list instead of overwriting it
        return {"messages": [reply]}

    # the state schema defines channels; MessagesState = one channel `messages` with the add_messages reducer
    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent)
    # ToolNode runs every tool_call of the last AI message and answers each with a ToolMessage(tool_call_id=...)
    builder.add_node("tools", ToolNode(TOOLS))
    builder.add_edge(START, "agent")
    # tool_calls in the last AI message → "tools", otherwise → END; tools → agent closes the ReAct loop
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    # compile() validates the wiring and returns a runnable (invoke/astream). The checkpointer saves the state after
    # every step under the run's thread_id, and the next run on that thread starts from it
    graph = builder.compile(checkpointer=InMemorySaver())
    return graph.with_config(recursion_limit=RECURSION_LIMIT)
