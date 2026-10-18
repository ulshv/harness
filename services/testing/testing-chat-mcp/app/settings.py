from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChatSettings(BaseSettings):
    # reads CHAT_URL; a missing or malformed value fails app startup
    model_config = SettingsConfigDict(env_prefix="CHAT_")

    url: HttpUrl


def load_chat_settings() -> ChatSettings:
    # fields come from env, which type checkers can't see: they flag the empty call. One ignore here
    return ChatSettings()  # pyright: ignore[reportCallIssue]
