"""AI provider boundary. Application code depends on `AIProvider`, never on a vendor SDK."""

from app.ai.factory import create_ai_provider
from app.ai.mock import MockAIProvider
from app.ai.provider import (
    AIDocument,
    AIEmptyResponse,
    AIInvalidOutput,
    AIProvider,
    AIProviderError,
    AIRequest,
    AITimeout,
    AIUnavailable,
)

__all__ = [
    "AIDocument",
    "AIEmptyResponse",
    "AIInvalidOutput",
    "AIProvider",
    "AIProviderError",
    "AIRequest",
    "AITimeout",
    "AIUnavailable",
    "MockAIProvider",
    "create_ai_provider",
]
