"""Google Gemini implementation of `AIProvider` (Gemini Developer API via google-genai)."""

import logging

import httpx
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

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
            response_schema=schema,
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
