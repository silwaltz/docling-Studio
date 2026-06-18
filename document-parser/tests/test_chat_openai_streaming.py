"""Tests for the OpenAI-compatible SSE streaming path in `api/chat.py`.

Covers `_stream_openai_chat`'s translation of vLLM's OpenAI SSE event
shape into the frontend-facing `{delta|done|error}` event shape that the
Ask tab UI consumes. The frontend is unaware of which backend is in play;
these tests pin the wire contract.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from api.chat import _stream_openai_chat

if TYPE_CHECKING:
    pass


async def _collect_events(stream) -> list[dict]:
    """Drain an async generator into a list of decoded event dicts."""
    out: list[dict] = []
    async for line in stream:
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        try:
            out.append(json.loads(payload))
        except json.JSONDecodeError:
            pass
    return out


def _make_fake_stream(status_code: int, sse_lines: list[str]):
    """Build a minimal async-context-manager stream that yields SSE lines."""

    class _FakeAsyncStream:
        def __init__(self):
            self.status_code = status_code

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aread(self):
            return b""

        async def aiter_lines(self):
            for line in sse_lines:
                yield line

    return _FakeAsyncStream


def _patch_httpx_with_stream(monkeypatch, sse_lines: list[str], status_code: int = 200):
    """Replace ``httpx.AsyncClient`` with a fake that streams the given SSE
    bytes and captures the request payload + headers.

    Returns a dict the caller can inspect post-call.
    """
    import httpx as _httpx

    captured: dict[str, object] = {}
    fake_stream = _make_fake_stream(status_code, sse_lines)

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["init_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, json=None, headers=None):
            captured["url"] = url
            captured["payload"] = json
            captured["headers"] = headers or {}
            return fake_stream()

    monkeypatch.setattr(_httpx, "AsyncClient", _FakeAsyncClient)
    return captured


@pytest.mark.asyncio
async def test_translates_openai_sse_delta_to_frontend_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI streams ``data: {"choices":[{"delta":{"content":"..."}}]}``
    lines; the function must emit ``{"delta": "..."}`` events in order."""

    sse_lines = [
        'data: {"id":"x","choices":[{"index":0,"delta":{"content":"Hello"}}]}\n\n',
        'data: {"id":"x","choices":[{"index":0,"delta":{"content":", world"}}]}\n\n',
        'data: {"id":"x","choices":[{"index":0,"delta":{"content":"!"}}]}\n\n',
        'data: {"id":"x","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],'
        '"usage":{"completion_tokens":3}}\n\n',
    ]
    captured = _patch_httpx_with_stream(monkeypatch, sse_lines)

    stream = _stream_openai_chat(
        messages=[{"role": "user", "content": "hi"}],
        model="gemma4:e4b-it-qat",
        base_url="http://localhost:8000/v1",
        api_key=None,
    )
    events = await _collect_events(stream)

    deltas = [e.get("delta") for e in events if "delta" in e]
    done = [e for e in events if e.get("done")]

    assert deltas == ["Hello", ", world", "!"]
    assert len(done) == 1
    assert done[0]["model"] == "gemma4:e4b-it-qat"
    assert done[0]["total_tokens"] == 3

    # Wire shape: POST to /v1/chat/completions with the streamed flag set.
    assert captured["url"] == "http://localhost:8000/v1/chat/completions"
    assert captured["payload"]["model"] == "gemma4:e4b-it-qat"
    assert captured["payload"]["stream"] is True
    # Default max_tokens — 8k is enough for the Ask JSON output and leaves
    # room for the prompt within typical 32k–64k vLLM context windows.
    assert captured["payload"]["max_tokens"] == 8_192


@pytest.mark.asyncio
async def test_sends_bearer_when_api_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI public API requires Bearer auth; the function must pass it
    through when ``api_key`` is set."""

    sse_lines = [
        'data: {"choices":[{"index":0,"delta":{"content":"hi"},"finish_reason":"stop"}]}\n\n',
    ]
    captured = _patch_httpx_with_stream(monkeypatch, sse_lines)

    stream = _stream_openai_chat(
        messages=[{"role": "user", "content": "hi"}],
        model="m",
        base_url="http://localhost:8000/v1",
        api_key="sk-test",
    )
    await _collect_events(stream)

    assert captured["headers"]["Authorization"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_emits_error_on_non_200(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backend returning non-200 must surface as `{"error": ...}` SSE event."""

    captured = _patch_httpx_with_stream(
        monkeypatch, sse_lines=[], status_code=502
    )
    # Patch the fake to return an `aread` that yields body bytes for the error path.
    import httpx as _httpx

    class _FakeAsyncStream2:
        status_code = 502

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aread(self):
            return b"upstream gone"

        async def aiter_lines(self):
            return
            yield  # pragma: no cover

    class _FakeAsyncClient2:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, json=None, headers=None):
            return _FakeAsyncStream2()

    monkeypatch.setattr(_httpx, "AsyncClient", _FakeAsyncClient2)

    stream = _stream_openai_chat(
        messages=[{"role": "user", "content": "hi"}],
        model="m",
        base_url="http://localhost:8000/v1",
        api_key=None,
    )
    events = await _collect_events(stream)

    assert len(events) == 1
    assert "error" in events[0]
    assert "502" in events[0]["error"]


@pytest.mark.asyncio
async def test_emits_error_on_connect_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """ConnectError must surface as `{"error": "Cannot connect ..."}` SSE event."""

    import httpx as _httpx

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, json=None, headers=None):
            raise _httpx.ConnectError("connection refused")

    monkeypatch.setattr(_httpx, "AsyncClient", _FakeAsyncClient)

    stream = _stream_openai_chat(
        messages=[{"role": "user", "content": "hi"}],
        model="m",
        base_url="http://nowhere:8000/v1",
        api_key=None,
    )
    events = await _collect_events(stream)

    assert len(events) == 1
    assert "error" in events[0]
    assert "Cannot connect" in events[0]["error"]