from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.settings import LLMSettings


def make_model(settings: LLMSettings) -> BaseChatModel:
    # RouterAI speaks the OpenAI Chat Completions dialect, so the stock client works with another base_url
    return ChatOpenAI(
        model=settings.model,
        base_url=str(settings.base_url),
        api_key=settings.api_key,
    )
