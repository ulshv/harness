import pytest
from pydantic import ValidationError

from app.settings import LLMSettings

VALID_ENV = {
    "LLM_BASE_URL": "https://llm.example/v1",
    "LLM_API_KEY": "sk-test",
    "LLM_MODEL": "vendor/model",
}


def test_reads_prefixed_env(monkeypatch):
    for name, value in VALID_ENV.items():
        monkeypatch.setenv(name, value)

    settings = LLMSettings()

    assert str(settings.base_url) == "https://llm.example/v1"
    assert settings.api_key.get_secret_value() == "sk-test"
    assert settings.model == "vendor/model"
    assert "sk-test" not in repr(settings)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LLM_API_KEY", ""),
        ("LLM_MODEL", ""),
        ("LLM_BASE_URL", ""),
        ("LLM_BASE_URL", "routerai.ru/api/v1"),
    ],
)
def test_invalid_value_fails(monkeypatch, name, value):
    for env_name, env_value in VALID_ENV.items():
        monkeypatch.setenv(env_name, env_value)
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError):
        LLMSettings()
