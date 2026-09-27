"""AI provider boundary. Application code depends on `AIProvider`, never on a vendor SDK."""

from app.ai.factory import create_ai_provider
from app.ai.mock import MockAIProvider
from app.ai.provider import AIProvider, AIProviderError, AIRequest, AIResponse

__all__ = [
    "AIProvider",
    "AIProviderError",
    "AIRequest",
    "AIResponse",
    "MockAIProvider",
    "create_ai_provider",
]
