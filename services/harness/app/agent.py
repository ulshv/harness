import os
from datetime import UTC, datetime

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

SYSTEM_PROMPT = "You are a concise assistant. Use tools when they help."


@tool
def current_time() -> str:
    """Return the current UTC date and time in ISO 8601."""
    # the docstring above is what the LLM sees as the tool description
    return datetime.now(UTC).isoformat(timespec="seconds")


TOOLS = [current_time]


def make_model() -> BaseChatModel:
    # RouterAI speaks the OpenAI Chat Completions dialect, so the stock client works with another base_url
    return ChatOpenAI(
        model=os.environ["LLM_MODEL"],
        base_url=os.environ["LLM_BASE_URL"],
        api_key=os.environ["LLM_API_KEY"],
    )


def build_graph(model: BaseChatModel):
    # bind_tools only attaches JSON schemas to each request; executing tools is the graph's job
    llm = model.bind_tools(TOOLS)

    async def agent(state: MessagesState):
        reply = await llm.ainvoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]])
        # MessagesState's add_messages reducer appends this to the list instead of overwriting it
        return {"messages": [reply]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(TOOLS))
    builder.add_edge(START, "agent")
    # tool_calls in the last AI message → "tools", otherwise → END; tools → agent closes the ReAct loop
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile()
