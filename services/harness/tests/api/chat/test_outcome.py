import asyncio

import pytest
from langchain_core.exceptions import (
    ContextOverflowError,
    ModelAPIError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from langgraph.errors import GraphRecursionError

from app.api.chat.outcome import append_error_or_done, error_event
from app.api.chat.schemas import DoneEvent, ErrorEvent, TextEvent


def run(*events, error=None):
    async def source():
        for event in events:
            yield event
        if error:
            raise error

    async def collect():
        return [event async for event in append_error_or_done(source())]

    return asyncio.run(collect())


def test_normal_end_appends_done():
    assert run(TextEvent(text="hi")) == [TextEvent(text="hi"), DoneEvent()]


def test_failure_appends_a_safe_error_and_nothing_after():
    events = run(TextEvent(text="hi"), error=RuntimeError("secret key sk-123"))

    assert events == [
        TextEvent(text="hi"),
        ErrorEvent(code="internal", message="Internal error."),
    ]
    assert "secret" not in events[-1].model_dump_json()


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (ModelRateLimitError("slow down"), "llm_rate_limited"),
        (ModelAPIError("502"), "llm_unavailable"),
        (ModelConnectionError("unreachable"), "llm_unavailable"),
        (ModelTimeoutError("timeout"), "llm_unavailable"),
        # 4xx: a retry won't help, it's our key/model/request
        (ModelAuthenticationError("401"), "internal"),
        (ContextOverflowError("too long"), "internal"),
        (GraphRecursionError("too deep"), "recursion_limit"),
        (ValueError("bug"), "internal"),
    ],
)
def test_error_codes_by_exception_type(exc, code):
    assert error_event(exc).code == code
