"""Google Gemini implementation of `AIProvider` (Gemini Developer API via google-genai)."""

from google import genai
from google.genai import errors, types

from app.ai.provider import AIProviderError, AIRequest, AIResponse

DEFAULT_TIMEOUT_MS = 60_000
DEFAULT_MAX_ATTEMPTS = 3


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

    def generate(self, request: AIRequest) -> AIResponse:
        config = types.GenerateContentConfig(
            system_instruction=request.system,
            max_output_tokens=request.max_output_tokens,
        )
        try:
            response = self._client.models.generate_content(
                model=self._model, contents=request.prompt, config=config
            )
        except errors.APIError as exc:
            # Surface only the status; provider messages may echo request content.
            raise AIProviderError(f"Gemini request failed with status {exc.code}") from exc

        text = response.text
        if text is None:
            raise AIProviderError("Gemini returned no text (blocked or empty response)")
        usage = response.usage_metadata
        return AIResponse(
            text=text,
            provider=self.name,
            model=self._model,
            input_tokens=(usage.prompt_token_count or 0) if usage else 0,
            output_tokens=(usage.candidates_token_count or 0) if usage else 0,
        )
