"""OpenAI-compatible LLM provider adapter.

Wraps any backend that speaks the OpenAI Chat Completions API — most
notably vLLM running with its built-in OpenAI server, but also OpenAI
itself, llama.cpp's server, etc. Holds the base URL + default model id and
exposes a cheap `health_check` (GET /v1/models) that doesn't load any model.
"""
from __future__ import annotations

import logging

import httpx

from domain.value_objects import LLMProviderType

logger = logging.getLogger(__name__)

# OpenAI's /v1/models returns 200 with an empty list even on a fresh
# install — perfect for a "is the daemon up?" probe. The base URL already
# ends with `/v1` so we just append the suffix here.
_HEALTH_PATH = "/models"
_HEALTH_TIMEOUT_SECONDS = 1.5


class OpenAIProvider:
    """Provider adapter for any OpenAI Chat-Completions-compatible server.

    Use ``base_url`` to point at vLLM's OpenAI server (default
    ``http://localhost:8000/v1``), OpenAI's public API, or any other
    compatible endpoint. ``api_key`` is optional — vLLM doesn't require one
    but OpenAI does; pass through as a Bearer token if set.
    """

    def __init__(
        self,
        base_url: str,
        default_model_id: str,
        api_key: str | None = None,
    ) -> None:
        # Strip a trailing slash so URL concatenation always works.
        self._base_url = base_url.rstrip("/")
        self._default_model_id = default_model_id
        self._api_key = api_key or None

    @property
    def type(self) -> LLMProviderType:
        return LLMProviderType.OPENAI

    @property
    def host(self) -> str:
        # Strip the trailing /v1 if present so this property matches the
        # `OllamaProvider.host` shape (a bare base URL). Downstream code
        # that needs `/v1` (e.g. the chat streaming code) appends it.
        url = self._base_url
        if url.endswith("/v1"):
            url = url[: -len("/v1")]
        return url

    @property
    def base_url(self) -> str:
        """Full base URL including the ``/v1`` suffix."""
        return self._base_url

    @property
    def default_model_id(self) -> str:
        return self._default_model_id

    @property
    def api_key(self) -> str | None:
        return self._api_key

    def _auth_headers(self) -> dict[str, str]:
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    def health_check(self) -> bool:
        """Lightweight reachability probe via ``/v1/models``."""
        try:
            resp = httpx.get(
                f"{self._base_url}{_HEALTH_PATH}",
                headers=self._auth_headers(),
                timeout=_HEALTH_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as e:
            logger.debug("OpenAI health check failed for %s: %s", self._base_url, e)
            return False
        return resp.status_code == 200