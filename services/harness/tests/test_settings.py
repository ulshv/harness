import pytest
from pydantic import ValidationError

from app.settings import AgentSettings, McpSettings, load_llm_settings

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


def test_agent_defaults(monkeypatch):
    monkeypatch.delenv("AGENT_SYSTEM_PROMPT_FILE", raising=False)
    monkeypatch.delenv("AGENT_RECURSION_LIMIT", raising=False)

    settings = AgentSettings()

    assert (
        settings.system_prompt()
        == "You are a concise assistant. Use tools when they help."
    )
    assert settings.recursion_limit == 25


def test_agent_prompt_from_file(monkeypatch, tmp_path):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("You are the operations assistant.")
    monkeypatch.setenv("AGENT_SYSTEM_PROMPT_FILE", str(prompt))
    monkeypatch.setenv("AGENT_RECURSION_LIMIT", "61")

    settings = AgentSettings()

    assert settings.system_prompt() == "You are the operations assistant."
    assert settings.recursion_limit == 61


@pytest.mark.parametrize("value", ["", "/nope/prompt.md"])
def test_bad_prompt_file_fails(monkeypatch, value):
    monkeypatch.setenv("AGENT_SYSTEM_PROMPT_FILE", value)

    with pytest.raises(ValidationError):
        AgentSettings()
