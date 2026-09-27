"""Selects the configured AI provider."""

from app.ai.mock import MockAIProvider
from app.ai.provider import AIProvider
from app.core.config import AIProviderName, Settings


def create_ai_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider is AIProviderName.GEMINI:
        # Imported lazily so the SDK loads only when Gemini is actually selected.
        from app.ai.gemini import GeminiProvider

        assert settings.gemini_api_key is not None  # noqa: S101  (enforced by Settings)
        return GeminiProvider(
            api_key=settings.gemini_api_key.get_secret_value(),
            model=settings.gemini_model,
            timeout_ms=settings.ai_request_timeout_seconds * 1000,
        )
    return MockAIProvider()
