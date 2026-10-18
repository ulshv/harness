from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class MarketplaceSettings(BaseSettings):
    # reads MARKETPLACE_URL; a missing or malformed value fails app startup
    model_config = SettingsConfigDict(env_prefix="MARKETPLACE_")

    url: HttpUrl


def load_marketplace_settings() -> MarketplaceSettings:
    # fields come from env, which type checkers can't see: they flag the empty call. One ignore here
    return MarketplaceSettings()  # pyright: ignore[reportCallIssue]
