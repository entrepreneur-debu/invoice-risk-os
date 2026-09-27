"""Provider-neutral AI interface.

Deliberately minimal: it will be extended (structured output, documents, usage
accounting) when invoice analysis is designed in a later step.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AIRequest:
    prompt: str
    system: str | None = None
    max_output_tokens: int = 1024


@dataclass(frozen=True)
class AIResponse:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


class AIProviderError(Exception):
    """Raised by providers for failures callers may handle (timeouts, refusals, quota)."""


class AIProvider(Protocol):
    @property
    def name(self) -> str: ...

    def generate(self, request: AIRequest) -> AIResponse: ...
