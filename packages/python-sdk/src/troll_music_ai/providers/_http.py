"""Shared HTTP plumbing for hosted and local-server adapters."""

from __future__ import annotations

import httpx

from ..errors import ProviderResponseError, ProviderUnavailableError


class HttpAdapter:
    """Base for adapters that call an HTTP API. Maps failures to typed errors
    and keeps credentials out of every error message."""

    name = "http"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

    def _client(self) -> httpx.AsyncClient:
        # A client per call keeps adapters usable from the synchronous facade,
        # which runs each call in its own event loop.
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers(),
            timeout=self._timeout,
            transport=self._transport,
            follow_redirects=True,
        )

    async def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            async with self._client() as client:
                response = await client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(
                f"{self.name} timed out after {self._timeout:.0f}s at {self._base_url}."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"Could not reach {self.name} at {self._base_url}. Is it running?"
            ) from exc
        if response.status_code >= 400:
            raise ProviderResponseError(
                f"{self.name} returned HTTP {response.status_code}: {error_snippet(response)}",
                status_code=response.status_code,
            )
        return response

    async def _probe(self, url: str, *, ok_detail: str = "Reachable.") -> tuple[bool, str, httpx.Response | None]:
        """GET ``url`` for a health check. Never raises."""
        try:
            async with self._client() as client:
                response = await client.get(url, timeout=min(self._timeout, 10.0))
        except httpx.HTTPError:
            return False, f"Cannot reach {self._base_url}.", None
        if response.status_code in (401, 403):
            return False, "The API key was rejected.", response
        if response.status_code >= 400:
            return False, f"Server answered HTTP {response.status_code}.", response
        return True, ok_detail, response


def error_snippet(response: httpx.Response) -> str:
    try:
        body = response.json()
        error = body.get("error", body.get("detail", body)) if isinstance(body, dict) else body
        message = error.get("message") if isinstance(error, dict) else error
        return str(message)[:300]
    except ValueError:
        return response.text[:300]
