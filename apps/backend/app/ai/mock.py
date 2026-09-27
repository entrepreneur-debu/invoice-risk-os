"""Deterministic in-process provider for development and automated tests.

Makes no network calls. Responses are either queued explicitly by a test or a
fixed default, and every request is recorded for assertions.
"""

from collections import deque

from app.ai.provider import AIRequest, AIResponse

DEFAULT_MOCK_TEXT = "mock response"


class MockAIProvider:
    def __init__(self) -> None:
        self.requests: list[AIRequest] = []
        self._queued: deque[str | Exception] = deque()

    @property
    def name(self) -> str:
        return "mock"

    def queue_response(self, response: str | Exception) -> None:
        self._queued.append(response)

    def generate(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        queued = self._queued.popleft() if self._queued else DEFAULT_MOCK_TEXT
        if isinstance(queued, Exception):
            raise queued
        return AIResponse(
            text=queued,
            provider=self.name,
            model="mock-model",
            input_tokens=len(request.prompt.split()),
            output_tokens=len(queued.split()),
        )
