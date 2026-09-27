import pytest

from app.ai import AIProvider, AIProviderError, AIRequest, MockAIProvider, create_ai_provider
from tests.conftest import SettingsFactory


def test_mock_provider_is_deterministic_and_records_requests() -> None:
    provider = MockAIProvider()
    provider.queue_response("extracted fields")

    first = provider.generate(AIRequest(prompt="read this invoice"))
    second = provider.generate(AIRequest(prompt="again"))

    assert first.text == "extracted fields"
    assert first.provider == "mock"
    assert first.input_tokens == 3
    assert second.text == "mock response"
    assert [r.prompt for r in provider.requests] == ["read this invoice", "again"]


def test_mock_provider_can_simulate_failures() -> None:
    provider = MockAIProvider()
    provider.queue_response(AIProviderError("rate limited"))

    with pytest.raises(AIProviderError):
        provider.generate(AIRequest(prompt="x"))


def test_factory_returns_mock_by_default(make_settings: SettingsFactory) -> None:
    provider: AIProvider = create_ai_provider(make_settings())

    assert provider.name == "mock"


def test_factory_rejects_unimplemented_provider(make_settings: SettingsFactory) -> None:
    settings = make_settings(ai_provider="anthropic", anthropic_api_key="placeholder")

    with pytest.raises(NotImplementedError):
        create_ai_provider(settings)
