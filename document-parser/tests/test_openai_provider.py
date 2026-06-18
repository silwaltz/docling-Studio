"""Tests for `infra.llm.openai_provider.OpenAIProvider`.

Network is stubbed via `httpx` MockTransport so the tests don't depend on a
running vLLM / OpenAI instance.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from domain.ports import LLMProvider
from domain.value_objects import LLMProviderType
from infra.llm.openai_provider import OpenAIProvider

if TYPE_CHECKING:
    import pytest


def test_provider_satisfies_llmprovider_protocol() -> None:
    """R13 — `OpenAIProvider` is structurally a `LLMProvider`."""
    p = OpenAIProvider(base_url="http://localhost:8000/v1", default_model_id="m")
    assert isinstance(p, LLMProvider)


def test_provider_exposes_type_host_default_model_id() -> None:
    p = OpenAIProvider(
        base_url="http://vllm:8000/v1",
        default_model_id="gemma4:e4b-it-qat",
    )
    assert p.type is LLMProviderType.OPENAI
    assert p.host == "http://vllm:8000"  # trailing /v1 stripped
    assert p.base_url == "http://vllm:8000/v1"
    assert p.default_model_id == "gemma4:e4b-it-qat"


def test_base_url_trailing_slash_is_stripped() -> None:
    p = OpenAIProvider(base_url="http://localhost:8000/v1/", default_model_id="m")
    assert p.base_url == "http://localhost:8000/v1"


def test_host_when_v1_already_stripped() -> None:
    """If the caller passes a URL without `/v1`, `.host` returns it as-is."""
    p = OpenAIProvider(base_url="http://localhost:8000", default_model_id="m")
    assert p.host == "http://localhost:8000"
    assert p.base_url == "http://localhost:8000"


def test_api_key_is_none_when_empty() -> None:
    p = OpenAIProvider(
        base_url="http://localhost:8000/v1", default_model_id="m", api_key=""
    )
    assert p.api_key is None


def test_api_key_passed_through() -> None:
    p = OpenAIProvider(
        base_url="http://localhost:8000/v1",
        default_model_id="m",
        api_key="sk-test",
    )
    assert p.api_key == "sk-test"


def test_health_check_returns_true_on_200(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"object": "list", "data": []})

    transport = httpx.MockTransport(handler)
    real_get = httpx.get

    def fake_get(url: str, **kwargs):  # type: ignore[no-untyped-def]
        with httpx.Client(transport=transport) as client:
            return client.get(url, **kwargs)

    monkeypatch.setattr(httpx, "get", fake_get)
    p = OpenAIProvider(base_url="http://localhost:8000/v1", default_model_id="m")
    assert p.health_check() is True

    # Restore (defensive, MonkeyPatch handles it but explicit is fine)
    monkeypatch.setattr(httpx, "get", real_get)


def test_health_check_returns_false_on_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, **kwargs):  # type: ignore[no-untyped-def]
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", fake_get)
    p = OpenAIProvider(base_url="http://nowhere:8000/v1", default_model_id="m")
    assert p.health_check() is False


def test_health_check_returns_false_on_non_200(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)

    def fake_get(url: str, **kwargs):  # type: ignore[no-untyped-def]
        with httpx.Client(transport=transport) as client:
            return client.get(url, **kwargs)

    monkeypatch.setattr(httpx, "get", fake_get)
    p = OpenAIProvider(base_url="http://localhost:8000/v1", default_model_id="m")
    assert p.health_check() is False


def test_health_check_sends_bearer_when_api_key_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"object": "list", "data": []})

    transport = httpx.MockTransport(handler)
    real_get = httpx.get

    def fake_get(url: str, **kwargs):  # type: ignore[no-untyped-def]
        with httpx.Client(transport=transport) as client:
            return client.get(url, **kwargs)

    monkeypatch.setattr(httpx, "get", fake_get)
    p = OpenAIProvider(
        base_url="http://localhost:8000/v1",
        default_model_id="m",
        api_key="sk-test",
    )
    assert p.health_check() is True
    assert captured["auth"] == "Bearer sk-test"

    monkeypatch.setattr(httpx, "get", real_get)