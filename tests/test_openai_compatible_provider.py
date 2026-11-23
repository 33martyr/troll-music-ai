"""The HTTP adapter, exercised against an in-memory transport (no network)."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from troll_music_ai import ProviderResponseError, ProviderUnavailableError
from troll_music_ai.providers import ChatMessage, OpenAICompatibleProvider, TextRequest

REQUEST = TextRequest(messages=[ChatMessage(role="user", content="hi")], json_mode=True)


def provider_for(handler, **kwargs) -> OpenAICompatibleProvider:
    options = {"base_url": "http://llm.test/v1/", "model": "tiny", "api_key": "sk-secret"}
    return OpenAICompatibleProvider(**{**options, **kwargs}, transport=httpx.MockTransport(handler))


def test_sends_a_chat_completion_request_and_returns_the_text():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"model": "tiny-v2", "choices": [{"message": {"content": "hello"}}]}
        )

    result = asyncio.run(provider_for(handler).generate_text(REQUEST))

    assert result.text == "hello" and result.model == "tiny-v2"
    assert seen["url"] == "http://llm.test/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-secret"
    assert seen["body"]["model"] == "tiny"
    assert seen["body"]["messages"] == [{"role": "user", "content": "hi"}]
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["max_tokens"] == 2500 and "temperature" in seen["body"]


def test_openai_style_parameters_can_be_switched():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = provider_for(handler, max_tokens_param="max_completion_tokens", send_temperature=False)
    asyncio.run(provider.generate_text(REQUEST))
    assert "max_completion_tokens" in seen
    assert "max_tokens" not in seen and "temperature" not in seen


def test_http_errors_surface_the_server_message_but_never_the_key():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "model 'tiny' not found"}})

    with pytest.raises(ProviderResponseError) as caught:
        asyncio.run(provider_for(handler).generate_text(REQUEST))
    assert caught.value.status_code == 404
    assert "model 'tiny' not found" in caught.value.message
    assert "sk-secret" not in caught.value.message


@pytest.mark.parametrize(
    "error", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")]
)
def test_network_failures_become_provider_unavailable(error):
    def handler(_: httpx.Request) -> httpx.Response:
        raise error

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(provider_for(handler).generate_text(REQUEST))


@pytest.mark.parametrize("payload", [{"choices": []}, {"choices": [{"message": {"content": "  "}}]}, {}])
def test_empty_or_malformed_completions_are_errors(payload):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(ProviderResponseError):
        asyncio.run(provider_for(handler).generate_text(REQUEST))


def test_check_reports_reachability_and_missing_models():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"data": [{"id": "other-model"}]})

    status = asyncio.run(provider_for(handler).check())
    assert status.ok is False and "tiny" in status.detail and status.models == ["other-model"]

    status = asyncio.run(provider_for(handler, model="other-model").check())
    assert status.ok is True


def test_check_never_raises():
    def refuse(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    def unauthorized(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={})

    assert asyncio.run(provider_for(refuse).check()).ok is False
    assert "key" in asyncio.run(provider_for(unauthorized).check()).detail


def test_rate_limits_are_waited_out_when_the_server_says_how_long():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(402, text="Free limit reached: 1 reply every 45 seconds per IP. Retry after 0s")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    assert asyncio.run(provider_for(handler).generate_text(REQUEST)).text == "ok" and len(calls) == 2

    # Too long a wait, or no retries left: fail with the server's message.
    slow = lambda request: httpx.Response(429, headers={"retry-after": "600"}, text="busy")  # noqa: E731
    with pytest.raises(ProviderResponseError, match="HTTP 429"):
        asyncio.run(provider_for(slow).generate_text(REQUEST))
    payment = lambda request: httpx.Response(402, text="pay up")  # noqa: E731  (402 without a wait is not retried)
    with pytest.raises(ProviderResponseError, match="HTTP 402"):
        asyncio.run(provider_for(payment).generate_text(REQUEST))
