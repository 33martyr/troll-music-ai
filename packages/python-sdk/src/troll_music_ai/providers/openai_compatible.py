"""Text adapter for any server that speaks the OpenAI chat-completions API.

That covers Ollama (``/v1``), LM Studio, vLLM, llama.cpp server, OpenRouter,
Groq, OpenAI itself and most other hosted LLM APIs.
"""

from __future__ import annotations

import httpx

from ..errors import ProviderResponseError, ProviderUnavailableError
from .base import (
    ProviderInfo,
    ProviderKind,
    ProviderStatus,
    TextGenerationProvider,
    TextRequest,
    TextResult,
)


class OpenAICompatibleProvider(TextGenerationProvider):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 120.0,
        name: str = "openai_compatible",
        max_tokens_param: str = "max_tokens",
        send_temperature: bool = True,
        extra_body: dict | None = None,
        min_max_tokens: int = 0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._name = name
        self._max_tokens_param = max_tokens_param
        self._send_temperature = send_temperature
        # Reasoning models spend output tokens on thinking before they answer,
        # so a preset can raise the token budget and pass extra request fields.
        self._extra_body = dict(extra_body or {})
        self._min_max_tokens = min_max_tokens
        self._transport = transport

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self._name,
            kind=ProviderKind.TEXT,
            model=self._model,
            endpoint=self._base_url,
        )

    def _client(self) -> httpx.AsyncClient:
        # A client per call keeps the adapter safe to use from the synchronous
        # facade, which runs each call in its own event loop.
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
            transport=self._transport,
        )

    async def generate_text(self, request: TextRequest) -> TextResult:
        payload: dict = {
            "model": self._model,
            "messages": [m.model_dump() for m in request.messages],
            self._max_tokens_param: max(request.max_tokens, self._min_max_tokens),
            **self._extra_body,
        }
        if self._send_temperature and request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            async with self._client() as client:
                response = await client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(
                f"{self._name} timed out after {self._timeout:.0f}s at {self._base_url}."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"Could not reach {self._name} at {self._base_url}. Is it running?"
            ) from exc

        if response.status_code >= 400:
            raise ProviderResponseError(
                f"{self._name} returned HTTP {response.status_code}: "
                f"{_error_snippet(response)}",
                status_code=response.status_code,
            )

        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError(
                f"{self._name} returned a response without message content."
            ) from exc
        if not isinstance(text, str) or not text.strip():
            raise ProviderResponseError(f"{self._name} returned an empty completion.")
        return TextResult(text=text, model=data.get("model") or self._model)

    async def check(self) -> ProviderStatus:
        try:
            async with self._client() as client:
                response = await client.get("/models", timeout=min(self._timeout, 10.0))
        except httpx.HTTPError:
            return ProviderStatus(ok=False, detail=f"Cannot reach {self._base_url}.")
        if response.status_code in (401, 403):
            return ProviderStatus(ok=False, detail="The API key was rejected.")
        if response.status_code >= 400:
            return ProviderStatus(
                ok=False, detail=f"Server answered HTTP {response.status_code}."
            )
        try:
            models = [m["id"] for m in response.json().get("data", []) if "id" in m]
        except (ValueError, AttributeError, TypeError):
            models = []
        if models and self._model not in models:
            return ProviderStatus(
                ok=False,
                detail=f"Reachable, but model '{self._model}' is not available there.",
                models=models,
            )
        return ProviderStatus(ok=True, detail="Reachable.", models=models)


def _error_snippet(response: httpx.Response) -> str:
    try:
        body = response.json()
        error = body.get("error", body) if isinstance(body, dict) else body
        message = error.get("message") if isinstance(error, dict) else error
        return str(message)[:300]
    except ValueError:
        return response.text[:300]
