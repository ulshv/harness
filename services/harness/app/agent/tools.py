from datetime import UTC, datetime

from langchain_core.tools import tool


@tool
def current_time() -> str:
    """Return the current UTC date and time in ISO 8601."""
    # the docstring above is what the LLM sees as the tool description
    return datetime.now(UTC).isoformat(timespec="seconds")


TOOLS = [current_time]
