"""Google Gemini implementation of `AIProvider` (Gemini Developer API via google-genai)."""

import logging
from typing import Any

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.ai.provider import (
    AIEmptyResponse,
    AIInvalidOutput,
    AIProviderError,
    AIRequest,
    AITimeout,
    AIUnavailable,
    T,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 60_000
DEFAULT_MAX_ATTEMPTS = 2

# Gemini rejects some JSON-Schema bounds (e.g. `maxItems` on arrays of objects) as too
# complex. They are removed from the schema *sent* to the model only; the response is
# still validated against the full Pydantic model, so every bound is enforced.
_UNSUPPORTED_BOUNDS = frozenset({"maxItems", "minItems", "maxLength", "minLength"})


def gemini_response_schema(schema: type[BaseModel]) -> dict[str, Any]:
    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items() if k not in _UNSUPPORTED_BOUNDS}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    stripped: dict[str, Any] = strip(schema.model_json_schema())
    return stripped


class GeminiProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        client: genai.Client | None = None,
    ) -> None:
        """`client` is injectable so tests never construct a networked client."""
        self._model = model
        self._client = client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=timeout_ms,
                retry_options=types.HttpRetryOptions(attempts=DEFAULT_MAX_ATTEMPTS),
            ),
        )

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model(self) -> str:
        return self._model

    def generate_structured(self, request: AIRequest, schema: type[T]) -> T:
        parts: list[types.Part] = [
            types.Part.from_bytes(data=doc.data, mime_type=doc.mime_type)
            for doc in request.documents
        ]
        parts.append(types.Part.from_text(text=request.prompt))
        config = types.GenerateContentConfig(
            system_instruction=request.system_instruction,
            max_output_tokens=request.max_output_tokens,
            temperature=0.0,
            response_mime_type="application/json",
            response_json_schema=gemini_response_schema(schema),
        )
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=types.Content(role="user", parts=parts),
                config=config,
            )
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise AITimeout("Gemini request timed out") from exc
        except errors.APIError as exc:
            # Surface only the status; provider messages may echo request content.
            raise AIUnavailable(f"Gemini request failed with status {exc.code}") from exc
        except (httpx.HTTPError, OSError) as exc:
            raise AIUnavailable(f"Gemini transport error: {type(exc).__name__}") from exc
        except AIProviderError:
            raise
        except Exception as exc:  # SDK-internal errors must not break the pipeline
            raise AIUnavailable(f"Gemini client error: {type(exc).__name__}") from exc

        text = response.text
        if not text or not text.strip():
            raise AIEmptyResponse("Gemini returned no content (blocked or empty response)")
        try:
            return schema.model_validate_json(text)
        except ValidationError as exc:
            raise AIInvalidOutput(
                f"Gemini output failed schema validation ({exc.error_count()} errors)"
            ) from exc
