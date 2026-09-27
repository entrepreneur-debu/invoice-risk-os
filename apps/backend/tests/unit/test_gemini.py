"""GeminiProvider tests use a fake client: no network calls, no real API key."""

from types import SimpleNamespace
from typing import Any, cast

import pytest
from google import genai
from google.genai import errors

from app.ai import AIProviderError, AIRequest, create_ai_provider
from app.ai.gemini import GeminiProvider
from tests.conftest import SettingsFactory


class FakeModels:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def _provider(models: FakeModels) -> GeminiProvider:
    client = cast(genai.Client, SimpleNamespace(models=models))
    return GeminiProvider(api_key="unused", model="gemini-test", client=client)


def _response(text: str | None, prompt_tokens: int = 7, output_tokens: int = 3) -> Any:
    usage = SimpleNamespace(prompt_token_count=prompt_tokens, candidates_token_count=output_tokens)
    return SimpleNamespace(text=text, usage_metadata=usage)


def test_generate_maps_request_and_response() -> None:
    models = FakeModels(response=_response("invoice looks fine"))

    result = _provider(models).generate(
        AIRequest(prompt="check this", system="be strict", max_output_tokens=256)
    )

    assert result.text == "invoice looks fine"
    assert result.provider == "gemini"
    assert result.model == "gemini-test"
    assert (result.input_tokens, result.output_tokens) == (7, 3)
    call = models.calls[0]
    assert call["model"] == "gemini-test"
    assert call["contents"] == "check this"
    assert call["config"].system_instruction == "be strict"
    assert call["config"].max_output_tokens == 256


def test_api_errors_become_provider_errors_without_details() -> None:
    error = errors.ClientError(429, {"error": {"message": "quota for prompt 'secret invoice'"}})
    models = FakeModels(error=error)

    with pytest.raises(AIProviderError) as exc_info:
        _provider(models).generate(AIRequest(prompt="x"))

    assert "429" in str(exc_info.value)
    assert "secret invoice" not in str(exc_info.value)


def test_empty_response_is_an_error() -> None:
    with pytest.raises(AIProviderError, match="no text"):
        _provider(FakeModels(response=_response(None))).generate(AIRequest(prompt="x"))


def test_factory_builds_gemini_provider(make_settings: SettingsFactory) -> None:
    settings = make_settings(
        ai_provider="gemini", gemini_api_key="placeholder-not-a-key", gemini_model="gemini-x"
    )

    provider = create_ai_provider(settings)

    assert provider.name == "gemini"
    assert isinstance(provider, GeminiProvider)
