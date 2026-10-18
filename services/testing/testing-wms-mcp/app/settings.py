from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class WmsSettings(BaseSettings):
    # reads WMS_URL; a missing or malformed value fails app startup
    model_config = SettingsConfigDict(env_prefix="WMS_")

    url: HttpUrl


def load_wms_settings() -> WmsSettings:
    # fields come from env, which type checkers can't see: they flag the empty call. One ignore here
    return WmsSettings()  # pyright: ignore[reportCallIssue]
