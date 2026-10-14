from typing import Annotated

from fastapi import Depends, Request
from langgraph.graph.state import CompiledStateGraph


# one compiled graph serves all requests concurrently: it's a stateless recipe,
# each astream() call carries its own run state
def get_graph(request: Request) -> CompiledStateGraph:
    return request.app.state.graph


# routes declare `graph: Graph` and FastAPI resolves Depends(get_graph) per request
Graph = Annotated[CompiledStateGraph, Depends(get_graph)]
