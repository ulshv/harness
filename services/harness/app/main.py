from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from langgraph.graph.state import CompiledStateGraph

from app.agent.graph import build_graph
from app.agent.llm import make_model
from app.agent.mcp import load_mcp_tools
from app.agent.tools import TOOLS
from app.api import health
from app.api.chat import chat
from app.settings import AgentSettings, McpSettings, load_llm_settings

type GraphFactory = Callable[[], Awaitable[CompiledStateGraph]]


# async: loading MCP tools talks to the servers
async def default_graph() -> CompiledStateGraph:
    # settings first: a bad .env or prompt path fails the boot before any wait on MCP servers
    model = make_model(load_llm_settings())
    agent = AgentSettings()
    system_prompt = agent.system_prompt()
    mcp_tools = await load_mcp_tools(McpSettings().servers)
    return build_graph(
        model,
        [*TOOLS, *mcp_tools],
        system_prompt=system_prompt,
        recursion_limit=agent.recursion_limit,
    )


# the factory parameter is the seam for tests: they pass a graph with a fake model
def create_app(graph_factory: GraphFactory = default_graph) -> FastAPI:
    # lifespan: code before `yield` runs at startup, after it at shutdown
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # built once at startup: a bad config fails the boot, not the first request
        app.state.graph = await graph_factory()
        yield

    app = FastAPI(title="harness", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(chat.router)
    return app


# uvicorn's target (`app.main:app`); importing it reads no LLM_* env, lifespan does at startup
app = create_app()
