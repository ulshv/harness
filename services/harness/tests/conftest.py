from collections.abc import Callable, Iterator
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk
from pydantic import Field

from app.agent.graph import build_graph
from app.main import create_app


# returns scripted replies in order, one per LLM call: [tool call, final answer] = one ReAct loop.
# It doesn't stream, so "messages" mode gets each reply as one whole message.
class FakeToolModel(FakeMessagesListChatModel):
    # the stock fakes raise on bind_tools; scripted replies already contain the tool calls
    def bind_tools(self, tools, **kwargs):
        return self


# streams scripted reasoning chunks, then text chunks, then optionally raises:
# the path a real model takes through "messages" mode
class StreamingFakeModel(BaseChatModel):
    chunks: list[str]
    reasoning: list[str] = Field(default_factory=list)
    error: Exception | None = None

    @property
    def _llm_type(self) -> str:
        return "streaming-fake"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise NotImplementedError("graph runs always stream")

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        # no on_llm_new_token here: langchain-core fires it for every chunk _astream yields
        for thought in self.reasoning:
            # the shape ChatDeepSeek produces from RouterAI's `delta.reasoning`
            reasoning = AIMessageChunk(
                content="", additional_kwargs={"reasoning_content": thought}
            )
            yield ChatGenerationChunk(message=reasoning)
        for text in self.chunks:
            yield ChatGenerationChunk(message=AIMessageChunk(content=text))
        if self.error:
            raise self.error


# a list of replies is a shortcut for the scripted, non-streaming FakeToolModel
type ClientFactory = Callable[[BaseChatModel | list[BaseMessage]], TestClient]


@pytest.fixture
def make_client() -> Iterator[ClientFactory]:
    with ExitStack() as stack:

        def factory(model: BaseChatModel | list[BaseMessage]) -> TestClient:
            if isinstance(model, list):
                model = FakeToolModel(responses=model)
            app = create_app(lambda: build_graph(model))
            # entering the client runs the app's lifespan, which builds the graph
            return stack.enter_context(TestClient(app))

        yield factory
