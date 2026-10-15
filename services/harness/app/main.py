from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from langgraph.graph.state import CompiledStateGraph

from app.agent.graph import build_graph
from app.agent.llm import make_model
from app.api import health
from app.api.chat import chat
from app.settings import load_llm_settings

type GraphFactory = Callable[[], CompiledStateGraph]


def default_graph() -> CompiledStateGraph:
    return build_graph(make_model(load_llm_settings()))


# the factory parameter is the seam for tests: they pass a graph with a fake model
def create_app(graph_factory: GraphFactory = default_graph) -> FastAPI:
    # lifespan: code before `yield` runs at startup, after it at shutdown
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # built once at startup: a bad config fails the boot, not the first request
        app.state.graph = graph_factory()
        yield

    app = FastAPI(title="harness", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(chat.router)
    return app


# uvicorn's target (`app.main:app`); importing it reads no LLM_* env, lifespan does at startup
app = create_app()
