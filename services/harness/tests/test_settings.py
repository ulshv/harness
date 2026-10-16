import pytest
from pydantic import ValidationError

from app.settings import McpSettings, load_llm_settings

VALID_ENV = {
    "LLM_BASE_URL": "https://llm.example/v1",
    "LLM_API_KEY": "sk-test",
    "LLM_MODEL": "vendor/model",
}


def test_reads_prefixed_env(monkeypatch):
    for name, value in VALID_ENV.items():
        monkeypatch.setenv(name, value)

    settings = load_llm_settings()

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
        load_llm_settings()


def test_mcp_servers_from_json(monkeypatch):
    monkeypatch.setenv("MCP_SERVERS", '{"wms": "http://testing-wms-mcp:8101/mcp"}')

    assert {name: str(url) for name, url in McpSettings().servers.items()} == {
        "wms": "http://testing-wms-mcp:8101/mcp"
    }


def test_mcp_servers_default_to_none(monkeypatch):
    monkeypatch.delenv("MCP_SERVERS", raising=False)

    assert McpSettings().servers == {}


@pytest.mark.parametrize(
    "value",
    ['{"wms": "not a url"}', '{"bad name": "http://x/mcp"}', '{"WMS": "http://x/mcp"}'],
)
def test_invalid_mcp_servers_fail(monkeypatch, value):
    monkeypatch.setenv("MCP_SERVERS", value)

    with pytest.raises(ValidationError):
        McpSettings()
