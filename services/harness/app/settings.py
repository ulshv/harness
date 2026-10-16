from typing import Annotated

from pydantic import Field, HttpUrl, SecretStr, StringConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    # reads LLM_BASE_URL / LLM_API_KEY / LLM_MODEL; a missing or empty value fails app startup
    model_config = SettingsConfigDict(env_prefix="LLM_")

    base_url: HttpUrl
    # SecretStr keeps the key out of reprs, logs and tracebacks
    api_key: SecretStr = Field(min_length=1)
    model: str = Field(min_length=1)


def load_llm_settings() -> LLMSettings:
    # fields come from env, which type checkers can't see: they read the signature as LLMSettings(base_url, api_key,
    # model) and flag the empty call. One ignore here instead of one at every call site
    return LLMSettings()  # pyright: ignore[reportCallIssue]


# the name prefixes its tools (`wms_get_order`); providers accept tool names of ^[a-zA-Z0-9_-]{1,64}$, so at
# least the prefix stays valid (the server's own tool names aren't checked)
ServerName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,15}$")]


class McpSettings(BaseSettings):
    # reads MCP_SERVERS as JSON: {"wms": "http://testing-wms-mcp:8101/mcp"}; a bad name or URL fails startup
    model_config = SettingsConfigDict(env_prefix="MCP_")

    servers: dict[ServerName, HttpUrl] = Field(default_factory=dict)
