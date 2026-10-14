"""Ends every chat run with exactly one terminal event: `done` or `error`. Knows nothing about HTTP."""

import logging
from collections.abc import AsyncIterable, AsyncIterator

from langchain_core.exceptions import (
    ModelAPIError,
    ModelConnectionError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from langgraph.errors import GraphRecursionError

from app.api.chat.schemas import ChatEvent, DoneEvent, ErrorCode, ErrorEvent

logger = logging.getLogger(__name__)

_UNAVAILABLE: tuple[ErrorCode, str] = (
    "llm_unavailable",
    "The language model provider is unavailable. Try again later.",
)
# langchain-core's provider-neutral errors; langchain-openai raises subclasses of them.
# Only conditions a retry can fix are "llm_*". 4xx (bad key, unknown model, context overflow) are ours: internal.
# error_event walks the exception's MRO, so the most specific class wins.
_ERRORS: dict[type[BaseException], tuple[ErrorCode, str]] = {
    ModelRateLimitError: (
        "llm_rate_limited",
        "The language model provider is rate limiting requests. Try again later.",
    ),
    ModelAPIError: _UNAVAILABLE,
    ModelConnectionError: _UNAVAILABLE,
    ModelTimeoutError: _UNAVAILABLE,
    GraphRecursionError: (
        "recursion_limit",
        "The agent took too many steps without finishing.",
    ),
}
_INTERNAL: tuple[ErrorCode, str] = ("internal", "Internal error.")


async def append_error_or_done(
    events: AsyncIterable[ChatEvent],
) -> AsyncIterator[ChatEvent]:
    try:
        async for event in events:
            yield event
    # Exception, not BaseException: a cancelled run (client gone) appends nothing
    except Exception as exc:
        # details stay in the log; the client gets a fixed code and message only
        logger.exception("chat run failed")
        yield error_event(exc)
        return
    yield DoneEvent()


def error_event(exc: BaseException) -> ErrorEvent:
    code, message = next(
        (_ERRORS[cls] for cls in type(exc).__mro__ if cls in _ERRORS), _INTERNAL
    )
    return ErrorEvent(code=code, message=message)
