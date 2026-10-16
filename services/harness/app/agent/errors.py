"""How the graph answers a tool that fails."""

import logging

from langgraph.prebuilt.tool_node import ToolInvocationError

logger = logging.getLogger(__name__)

# what the model reads when a tool crashes: no exception text, which can carry internal URLs. Not "the service is
# down": a bug in a local tool lands here too, and the model would pass a wrong reason on to the user
TOOL_FAILED = "The tool failed to run."


# ToolNode reads the handler's parameter annotation to decide what it catches: `Exception` is everything a tool
# raises. The default handler catches only bad arguments, so a dead MCP server mid-run would end the whole run
def handle_tool_errors(e: Exception) -> str:
    # bad arguments: the model can fix its call, so it gets the details
    if isinstance(e, ToolInvocationError):
        return e.message
    logger.error("tool failed", exc_info=e)
    return TOOL_FAILED
