from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class ErpSettings(BaseSettings):
    # reads ERP_URL; a missing or malformed value fails app startup
    model_config = SettingsConfigDict(env_prefix="ERP_")

    url: HttpUrl


def load_erp_settings() -> ErpSettings:
    # fields come from env, which type checkers can't see: they flag the empty call. One ignore here
    return ErpSettings()  # pyright: ignore[reportCallIssue]
