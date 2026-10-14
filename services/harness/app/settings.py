from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    # reads LLM_BASE_URL / LLM_API_KEY / LLM_MODEL; a missing or empty value fails app startup
    model_config = SettingsConfigDict(env_prefix="LLM_")

    base_url: HttpUrl
    # SecretStr keeps the key out of reprs, logs and tracebacks
    api_key: SecretStr = Field(min_length=1)
    model: str = Field(min_length=1)
