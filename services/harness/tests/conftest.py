from collections.abc import Callable, Iterator
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import BaseMessage

from app.agent.graph import build_graph
from app.main import create_app


# returns scripted replies in order, one per LLM call: [tool call, final answer] = one ReAct loop.
# It doesn't stream, so "messages" mode gets each reply as one whole message.
class FakeToolModel(FakeMessagesListChatModel):
    # the stock fakes raise on bind_tools; scripted replies already contain the tool calls
    def bind_tools(self, tools, **kwargs):
        return self


type ClientFactory = Callable[[list[BaseMessage]], TestClient]


@pytest.fixture
def make_client() -> Iterator[ClientFactory]:
    with ExitStack() as stack:

        def factory(replies: list[BaseMessage]) -> TestClient:
            app = create_app(lambda: build_graph(FakeToolModel(responses=replies)))
            # entering the client runs the app's lifespan, which builds the graph
            return stack.enter_context(TestClient(app))

        yield factory
