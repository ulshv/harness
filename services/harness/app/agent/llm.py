from langchain_core.language_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek

from app.settings import LLMSettings


def make_model(settings: LLMSettings) -> BaseChatModel:
    # ChatOpenAI drops non-standard fields; ChatDeepSeek (same BaseChatOpenAI, same openai SDK) lifts
    # RouterAI's OpenRouter-style `delta.reasoning` into additional_kwargs["reasoning_content"]
    return ChatDeepSeek(
        model=settings.model,
        base_url=str(settings.base_url),
        api_key=settings.api_key,
    )
