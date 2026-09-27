"""Provider-neutral AI interface.

Application code depends on `AIProvider` only. Every call returns output validated
against a Pydantic schema; free-form text is never used as application logic.
AI output is advisory: it is stored and displayed as AI-generated, and never drives
arithmetic, duplicate determination, authorization, approval or payment.
"""

from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class AIDocument:
    data: bytes
    mime_type: str


@dataclass(frozen=True)
class AIRequest:
    task: str  # e.g. "invoice_extraction", "risk_explanation" (for logs/metrics)
    system_instruction: str
    prompt: str
    documents: tuple[AIDocument, ...] = field(default_factory=tuple)
    max_output_tokens: int = 4096


class AIProviderError(Exception):
    """Base class. `code` is stored on the record so reviewers can see why AI failed."""

    code = "ai_error"


class AITimeout(AIProviderError):
    code = "ai_timeout"


class AIUnavailable(AIProviderError):
    code = "ai_unavailable"


class AIInvalidOutput(AIProviderError):
    code = "ai_invalid_output"


class AIEmptyResponse(AIProviderError):
    code = "ai_empty_response"


class AIProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    def generate_structured(self, request: AIRequest, schema: type[T]) -> T:
        """Returns output validated against `schema` or raises an `AIProviderError`."""
        ...
