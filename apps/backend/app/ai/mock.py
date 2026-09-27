"""Deterministic in-process provider for development and automated tests.

Makes no network calls. Tests queue responses (a model instance, a JSON string to be
validated, or an exception). With nothing queued it raises `AIUnavailable`, so a stack
running with AI_PROVIDER=mock exercises the "AI unavailable" degradation path honestly
instead of inventing analysis.
"""

from collections import deque

from pydantic import BaseModel, ValidationError

from app.ai.provider import AIInvalidOutput, AIRequest, AIUnavailable, T


class MockAIProvider:
    def __init__(self) -> None:
        self.requests: list[AIRequest] = []
        self._queued: dict[str, deque[BaseModel | str | Exception]] = {}

    @property
    def name(self) -> str:
        return "mock"

    @property
    def model(self) -> str:
        return "mock-model"

    def queue(self, task: str, response: BaseModel | str | Exception) -> None:
        self._queued.setdefault(task, deque()).append(response)

    def generate_structured(self, request: AIRequest, schema: type[T]) -> T:
        self.requests.append(request)
        queue = self._queued.get(request.task)
        if not queue:
            raise AIUnavailable("Mock AI provider has no scripted response")
        item = queue.popleft()
        if isinstance(item, Exception):
            raise item
        raw = item if isinstance(item, str) else item.model_dump_json()
        try:
            return schema.model_validate_json(raw)
        except ValidationError as exc:
            raise AIInvalidOutput("Mock output failed schema validation") from exc
