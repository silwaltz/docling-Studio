"""Document Q&A chat — POST /api/documents/:id/chat

Streams an SSE response using the document's extracted markdown as context,
forwarding the conversation to a local Ollama instance via /api/chat.
No extra deps beyond httpx (already in requirements).

Each SSE event is a JSON object:
  {"delta": "..."} — incremental token
  {"done": true, "model": "...", "total_tokens": N} — final summary
  {"error": "..."} — error (stream ends)
"""

from __future__ import annotations

import json
import logging

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from infra.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["chat"])

# Aligned with `vlm_ollama_prompt` in `infra/settings.py` — single prompt template
# used by both VLM-direct and standard-pipeline-→-Ask paths so the user sees
# consistent output regardless of which pipeline produced the document. (#Ask prompt)
_SYSTEM_PROMPT = (
    """
    Extract every distinct entity from this page and return a single JSON object. "
    "Use exactly these four key prefixes with a numeric suffix starting at "
    "1 (Company Name1, Address1, Shipping Information1, Goods Description1, etc.): "
    "\"Company Name<n>\" = a company, bank, agency, or organization name; "
    "\"Address<n>\" = a postal or physical address (one line per key, multi-line "
    "addresses get multiple Address<n>); "
    "\"Shipping Information<n>\" = port, vessel, container, B/L, AWB, or routing info; "
    "\"Goods Description<n>\" = a description of goods, items, or cargo. "
    "Rules: Output ONLY the JSON object - no markdown, no code fences, no commentary. "
    "Every value MUST be a plain string (no arrays, no nested objects). "
    "Include every distinct entity you find; do not deduplicate. "
    "If a section has no entries on this page, omit its keys entirely. "
    "Replace newlines inside values with a single space. "
    "Document context: {context}"
    """
)

_MAX_CONTEXT_CHARS = 96_000  # ~24k tokens of document text. The model context window
# (see num_ctx in _stream_ollama) is the real ceiling; this cap is just to
# keep the prompt small enough that the system + history + output budget all
# fit comfortably. With 12+ pages of markdown (VLM pipeline) we routinely see
# 20-25k chars, and 32k used to truncate mid-document and force the model
# to "answer about the truncated end" — a classic cut-off symptom.


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None  # overrides CHAT_MODEL_ID for this call


async def _stream_ollama(
    messages: list[dict],
    model: str,
    ollama_host: str,
):
    """Generator that streams SSE-formatted events from Ollama /api/chat."""
    url = f"{ollama_host.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            # gemma4:e4b-it-qat supports up to 128k context. 96k leaves headroom
            # for system prompt + history + output. The previous 32k value was
            # the cutoff that caused 12-page docs to lose the tail of the
            # markdown before the model even started answering.
            "num_ctx": 96_000,
            # The Ask prompt asks the model to enumerate every distinct entity
            # across the document — a 12-page trade/shipping doc can produce
            # tens of thousands of tokens of JSON output, well past the old
            # 4k cap and still past 16k on dense docs. 96k ≈ ~70k words of
            # output, enough for the biggest expected JSON enumeration plus
            # free-form Q&A. Ollama clamps this to num_ctx if it would
            # overflow the context window, so it stays safe even on smaller
            # models.
            "num_predict": 96_000,
        },
    }

    total_tokens = 0
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", url, json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    error_text = body.decode(errors="replace")[:200]
                    yield f"data: {json.dumps({'error': f'Ollama returned {resp.status_code}: {error_text}'})}\n\n"
                    return

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if chunk.get("error"):
                        yield f"data: {json.dumps({'error': chunk['error']})}\n\n"
                        return

                    delta = chunk.get("message", {}).get("content", "")
                    if delta:
                        total_tokens += 1
                        yield f"data: {json.dumps({'delta': delta})}\n\n"

                    if chunk.get("done"):
                        eval_count = chunk.get("eval_count", total_tokens)
                        yield f"data: {json.dumps({'done': True, 'model': model, 'total_tokens': eval_count})}\n\n"
                        return

    except httpx.ConnectError:
        yield f"data: {json.dumps({'error': f'Cannot connect to Ollama at {ollama_host}. Is it running?'})}\n\n"
    except httpx.TimeoutException:
        yield f"data: {json.dumps({'error': 'Ollama request timed out (300s).'})}\n\n"
    except Exception as e:
        logger.exception("Unexpected error streaming from Ollama")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


@router.get("/ollama-status")
async def ollama_status() -> dict:
    """Quick reachability probe — returns whether Ollama is accessible from the backend."""
    host = settings.ollama_host
    reachable = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{host.rstrip('/')}/api/tags")
            reachable = resp.status_code == 200
    except Exception:
        pass
    return {"reachable": reachable, "host": host, "model": settings.chat_model_id}


@router.post("/{doc_id}/chat")
async def chat(doc_id: str, body: ChatRequest, request: Request) -> StreamingResponse:
    if not settings.chat_enabled:
        raise HTTPException(
            status_code=503,
            detail="Document chat disabled (CHAT_ENABLED=false)",
        )

    analysis_repo = getattr(request.app.state, "analysis_repo", None)
    if analysis_repo is None:
        raise HTTPException(status_code=500, detail="AnalysisRepository not wired")

    latest = await analysis_repo.find_latest_completed_by_document(doc_id)
    if latest is None or not latest.content_markdown:
        raise HTTPException(
            status_code=404,
            detail=(
                "No completed analysis found for this document. "
                "Run an analysis first to enable the Ask feature."
            ),
        )

    context = latest.content_markdown[:_MAX_CONTEXT_CHARS]
    if len(latest.content_markdown) > _MAX_CONTEXT_CHARS:
        context += "\n\n[Document truncated for context window]"

    model = body.model or settings.chat_model_id

    system_message = {"role": "system", "content": _SYSTEM_PROMPT.format(context=context)}
    history = [{"role": m.role, "content": m.content} for m in body.messages]
    ollama_messages = [system_message] + history

    logger.info(
        "Chat: doc=%s model=%s messages=%d context_chars=%d",
        doc_id,
        model,
        len(body.messages),
        len(context),
    )

    return StreamingResponse(
        _stream_ollama(ollama_messages, model, settings.ollama_host),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
