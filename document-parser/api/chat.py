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
import re

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from infra.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["chat"])

# Trade-shipping document extraction prompt. Iterated in
# `experiments/prompt-runs/FINAL_REPORT.md` — v1 variant, +1.5pp over the
# previous version. See also: experiments/prompts/v1.txt for the source file
# that gets pasted here.
_SYSTEM_PROMPT = (
    """
    You are a trade-shipping document analyst. Read the document below and extract every distinct entity.

    Output a single JSON object (NOT an array, NOT wrapped in code fences) with these exact key prefixes and a numeric suffix starting at 1:
    - "Company Name<n>" = the legal/registered name of a company, bank, agency, broker, or organization that appears in the document. Include SHIPPER, CONSIGNEE, NOTIFY PARTY, CARRIER, ISSUING BANK, INSURER, AGENT — every company mentioned.
    - "Address<n>" = a postal or physical address. Multi-line addresses get one Address<n> with single-space-joined lines. Map each address to the most relevant Company when possible (Shipper's address with the Shipper, Consignee's address with the Consignee, etc.). Don't list the same address twice for the same company.
    - "Shipping Information<n>" = routing and transport details. For each leg/segment, include ALL of: "From: <port/airport/code>", "To: <port/airport/code>", "Via: <vessel/flight name & number>" (include vessel name when present, even partial), and "Date: <shipped-on-board date>" when present. Combine one leg's details into ONE Shipping Information<n> value, not separate keys. If a value is unknown for a leg, omit that field for that leg, not the whole key.
    - "Goods Description<n>" = the product name only. NO quantities (e.g. "250 BAGS", "20.000 CBM", "399 BAGS"). NO codes (HS codes, FDA registration, FDA N, contract numbers, lot numbers, FLO ID, container numbers, seal numbers). NO logos, certifications, or organization names. NO weight or measurement. If a sentence like "250 BAGS OF 69 KILOGRAMS NET EACH OF WASHED GREEN COFFEE PERUVIAN ALTURA EURO PREPARATION (E.P.) OCIA CERTIFIED CROP 2007" appears, output ONLY "WASHED GREEN COFFEE PERUVIAN ALTURA EURO PREPARATION (E.P.)" (or the closest product-name phrase). One goods description per distinct product.

    Rules:
    - Output ONLY the JSON object. No markdown, no code fences, no preamble, no commentary.
    - Every value MUST be a plain string (no arrays, no nested objects).
    - Include every distinct company, address, shipping leg, and product. Do not deduplicate within a section.
    - If a section has no entries, omit its keys entirely.
    - Replace newlines inside values with a single space.
    - Normalize whitespace: collapse multiple spaces to one.
    - IMPORTANT: Do not stop early. Continue listing keys until you have captured every distinct entity in the document.
    - CRITICAL: Preserve the exact spelling and wording from the document. Do NOT correct OCR artefacts, typos, or unusual spellings. If the document reads "Wilhelminakade", output "Wilhelminakade" — NOT the proper-Dutch "Wilhelmijnakade". If a name appears as "DUPONT CHEMICAL" (all caps) in the source, keep it all caps. The downstream merge may show multiple spelling variants side by side; the user's downstream validation uses the document's wording as ground truth, so a "corrected" value would be wrong.

    Document context: {context}
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


async def _stream_openai_chat(
    messages: list[dict],
    model: str,
    base_url: str,
    api_key: str | None,
    num_predict: int = 8_192,
):
    """Generator that streams SSE-formatted events from an OpenAI-compatible
    Chat Completions endpoint (e.g. vLLM serving gemma4:e4b-it-qat).

    Translates the upstream SSE event shape (``data: {"choices":[{"delta":...}]}``
    with a terminating ``data: [DONE]``) into the same frontend-facing event
    shape used by ``_stream_ollama``:

        {"delta": "..."}        — incremental token
        {"done": true, ...}     — final summary
        {"error": "..."}        — error (stream ends)

    Keeping the event shape identical means the Ask tab UI doesn't need to
    know which backend is in play — it just consumes ``evt.delta`` /
    ``evt.done`` regardless.

    `num_predict` defaults to 8k (was 96k for the Ollama path) because vLLM
    deployments typically cap `max_model_len` at 32k or 64k — leaving 96k
    for output is a footgun that fails the request. 8k is plenty for the
    Ask-prompt JSON extraction (which is normally a few hundred to a few
    thousand tokens) and keeps the prompt budget roomy.
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "max_tokens": num_predict,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    total_tokens = 0
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    error_text = body.decode(errors="replace")[:200]
                    yield f"data: {json.dumps({'error': f'OpenAI-compatible backend returned {resp.status_code}: {error_text}'})}\n\n"
                    return

                async for raw_line in resp.aiter_lines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if not line or line == "[DONE]":
                        if line == "[DONE]":
                            yield f"data: {json.dumps({'done': True, 'model': model, 'total_tokens': total_tokens})}\n\n"
                            return
                        continue
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if evt.get("error"):
                        err = evt["error"]
                        if isinstance(err, dict):
                            err = err.get("message") or json.dumps(err)
                        yield f"data: {json.dumps({'error': str(err)})}\n\n"
                        return
                    for choice in evt.get("choices") or []:
                        delta = (choice.get("delta") or {}).get("content") or ""
                        if delta:
                            total_tokens += 1
                            yield f"data: {json.dumps({'delta': delta})}\n\n"
                        if choice.get("finish_reason"):
                            # The upstream OpenAI stream doesn't include a
                            # [DONE] when finish_reason is set; emit the
                            # summary now so the client knows the stream
                            # is done.
                            usage = evt.get("usage") or {}
                            yield f"data: {json.dumps({'done': True, 'model': model, 'total_tokens': usage.get('completion_tokens', total_tokens)})}\n\n"
                            return

    except httpx.ConnectError:
        yield f"data: {json.dumps({'error': f'Cannot connect to OpenAI-compatible backend at {base_url}. Is it running?'})}\n\n"
    except httpx.TimeoutException:
        yield f"data: {json.dumps({'error': 'OpenAI-compatible backend request timed out (300s).'})}\n\n"
    except Exception as e:
        logger.exception("Unexpected error streaming from OpenAI-compatible backend")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


async def run_ask_extraction(markdown: str, model: str | None = None) -> str | None:
    """Non-streaming Ask-LLM JSON extraction (used by Deep-Extract mode).

    Calls Ollama with the same trade-shipping prompt as the streaming
    `/chat` endpoint, but waits for the full response and returns the
    concatenated text. The caller is responsible for cleaning it into a
    JSON object (gemma4 drops the wrapping braces ~50% of the time and
    uses `<n>` suffixes; the `reparse-saved` helper at
    `experiments/reparse-saved.py` documents the workarounds).

    Returns the raw model text, or None if Ollama is unreachable / errors
    out. The caller should treat None as "Ask step skipped" and proceed
    with whatever other extraction paths produced content.
    """
    if not settings.chat_enabled:
        logger.warning("run_ask_extraction called while CHAT_ENABLED=false; skipping")
        return None
    if not markdown or not markdown.strip():
        return None

    context = markdown[:_MAX_CONTEXT_CHARS]
    if len(markdown) > _MAX_CONTEXT_CHARS:
        context += "\n\n[Document truncated for context window]"

    chosen_model = model or settings.chat_model_id
    context_chars = len(context)

    if settings.chat_provider == "openai":
        # OpenAI Chat Completions (vLLM, OpenAI public API, llama.cpp server, ...).
        url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": chosen_model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT.format(context=context)},
                # The streaming chat endpoint uses the user's first message as
                # the "ask" trigger. For a non-streaming JSON extraction we
                # want a single deterministic invocation: the model should
                # produce the JSON object immediately. The empty user
                # message is a no-op the model ignores; it just primes the
                # system prompt's behaviour.
                {"role": "user", "content": "Extract the JSON object for the document above."},
            ],
            "stream": False,
            # 8k output is plenty for the four-section JSON (a few hundred to
            # a few thousand tokens) and leaves room for the prompt within
            # typical 32k–64k vLLM context windows.
            "max_tokens": 8_192,
        }
        headers = {"Content-Type": "application/json"}
        if settings.openai_api_key:
            headers["Authorization"] = f"Bearer {settings.openai_api_key}"
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
        except httpx.ConnectError:
            logger.warning(
                "OpenAI-compatible backend unreachable at %s; Ask step skipped",
                settings.openai_base_url,
            )
            return None
        except httpx.TimeoutException:
            logger.warning("OpenAI-compatible Ask step timed out after 300s")
            return None
        except Exception:
            logger.exception("Unexpected error in run_ask_extraction (openai)")
            return None

        if resp.status_code != 200:
            logger.warning(
                "OpenAI-compatible backend returned %d for Ask extraction: %s",
                resp.status_code,
                resp.text[:200],
            )
            return None

        try:
            body = resp.json()
        except json.JSONDecodeError:
            logger.warning("OpenAI-compatible Ask response was not valid JSON")
            return None

        choices = body.get("choices") or []
        if not choices:
            logger.warning("OpenAI-compatible Ask response had no choices")
            return None
        content = (choices[0].get("message") or {}).get("content") or ""
        return content.strip() or None

    # Default: Ollama native NDJSON.
    payload = {
        "model": chosen_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT.format(context=context)},
            # The streaming chat endpoint uses the user's first message as
            # the "ask" trigger. For a non-streaming JSON extraction we
            # want a single deterministic invocation: the model should
            # produce the JSON object immediately. The empty user
            # message is a no-op the model ignores; it just primes the
            # system prompt's behaviour.
            {"role": "user", "content": "Extract the JSON object for the document above."},
        ],
        "stream": False,
        "options": {
            "num_ctx": 96_000,
            "num_predict": 96_000,
        },
    }

    url = f"{settings.ollama_host.rstrip('/')}/api/chat"
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(url, json=payload)
    except httpx.ConnectError:
        logger.warning("Ollama unreachable at %s; Ask step skipped", settings.ollama_host)
        return None
    except httpx.TimeoutException:
        logger.warning("Ollama Ask step timed out after 300s")
        return None
    except Exception:
        logger.exception("Unexpected error in run_ask_extraction")
        return None

    if resp.status_code != 200:
        logger.warning(
            "Ollama returned %d for Ask extraction: %s",
            resp.status_code,
            resp.text[:200],
        )
        return None

    try:
        body = resp.json()
    except json.JSONDecodeError:
        logger.warning("Ollama Ask response was not valid JSON")
        return None

    content = (body.get("message") or {}).get("content") or ""
    return content.strip() or None


def parse_ask_response(raw: str) -> str | None:
    """Best-effort parse of gemma4's Ask output into a clean JSON string.

    Gemma 4 (with the trade-shipping prompt) drops the wrapping `{ }`
    ~50% of the time, uses `key<1>` with angle brackets, and uses
    `key = value` lines. The frontend's `extractJson` only handles the
    brace-less case. This helper normalises all three quirks so the
    result is loadable JSON. Returns None if the input is empty.

    Logic ported from `experiments/reparse-saved.py` so the production
    deep-mode pipeline uses the same quirks handling as the offline
    scoring harness (single source of truth).
    """
    if not raw or not raw.strip():
        return None
    t = raw.strip()

    # Strip code fences.
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)```", t)
    if fenced:
        t = fenced.group(1).strip()

    # Strip leading preamble ("Here is the JSON object:", etc.).
    for prefix in (
        "Here is the JSON object:",
        "Here is the JSON:",
        "JSON:",
        "Output:",
    ):
        if t.startswith(prefix):
            t = t[len(prefix):].strip()
            break

    # Normalise `"key<1>"` -> `"key1"` and `"key":="value"` -> `"key":"value"`.
    t = re.sub(
        r'"(Company Name|Address|Shipping Information|Goods Description)<(\d+)>"',
        r'"\1\2"',
        t,
    )
    t = re.sub(r'"\s*:=\s*"', '":"', t)
    t = re.sub(r'"\s*=\s*"', '":"', t)

    # 1) Already a valid JSON object or array — return as-is.
    stripped = t.strip()
    if stripped.startswith("{") and stripped.rstrip().endswith("}"):
        try:
            return _sanitize_ask_values(json.loads(stripped))
        except json.JSONDecodeError:
            pass

    # 2) Brace-less: walk and find a matching close-brace.
    for open_c, close_c in (("[", "]"), ("{", "}")):
        start = stripped.find(open_c)
        if start < 0:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(stripped)):
            ch = stripped[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == open_c:
                depth += 1
            elif ch == close_c:
                depth -= 1
                if depth == 0:
                    cand = stripped[start : i + 1]
                    try:
                        return _sanitize_ask_values(json.loads(cand))
                    except json.JSONDecodeError:
                        pass
                    break

    # 3) Brace-less: count `"key":"value"` patterns and wrap.
    colon_count = len(re.findall(r'"[^"]+"\s*:\s*"', stripped))
    if stripped.startswith('"') and colon_count >= 2:
        wrapped = "{" + stripped.rstrip().rstrip(",") + "}"
        try:
            return _sanitize_ask_values(json.loads(wrapped))
        except json.JSONDecodeError:
            last_full = max(wrapped.rfind('",'), wrapped.rfind('":null'))
            if last_full > 0:
                cut = wrapped[: last_full + 1] + "}"
                try:
                    return _sanitize_ask_values(json.loads(cut))
                except json.JSONDecodeError:
                    pass

    # 4) "=" separator fallback: `"key"="value",` patterns.
    eq_count = len(re.findall(r'"[A-Za-z][^"]*"\s*=\s*"', stripped))
    if eq_count >= 2:
        normalized = re.sub(r'"([A-Za-z][^"]*?)"\s*=\s*"', r'"\1":"', stripped)
        wrapped = "{" + normalized.rstrip().rstrip(",") + "}"
        try:
            return _sanitize_ask_values(json.loads(wrapped))
        except json.JSONDecodeError:
            last_full = max(wrapped.rfind('",'), wrapped.rfind('":null'))
            if last_full > 0:
                cut = wrapped[: last_full + 1] + "}"
                try:
                    return _sanitize_ask_values(json.loads(cut))
                except json.JSONDecodeError:
                    pass

    # 5) Last resort: line-by-line "key": "value" / "key" = "value".
    obj: dict[str, str] = {}
    for line in stripped.splitlines():
        line = line.strip().rstrip(",")
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if "=" in line and '"' in line:
            k, v = line.split("=", 1)
            k = k.strip().strip('"').strip("'")
            v = v.strip().rstrip(",").strip()
            if v.startswith('"') and v.endswith('"'):
                v = v[1:-1]
            if k:
                obj[k] = v
            continue
        if ":" in line and '"' in line:
            k, v = line.split(":", 1)
            k = k.strip().strip('"').strip("'").rstrip(",")
            v = v.strip().rstrip(",").strip()
            if v.startswith('"') and v.endswith('"'):
                v = v[1:-1]
            if k:
                obj[k] = v
    if not obj:
        return None
    return _sanitize_ask_values(obj)


def _sanitize_ask_values(obj) -> str | None:
    """Coerce every value in the parsed Ask response to a string.

    Gemma 4 (and other small models) emit three shapes that need
    normalising:

    1. ``{"To": "CHINA"}`` — single-key dict value. Flatten to
       ``"To: CHINA"`` so the merge contract holds (every value is
       a flat string).
    2. ``{"Company Name": {"Company Name1": "A", "Company Name2": "B"}}``
       — NESTED SECTION. The outer key is the section name (matches
       one of the four canonical prefixes) and the inner dict is the
       list of per-section entries. This MUST be flattened to
       top-level keys ``"Company Name1": "A", "Company Name2": "B"``
       so the downstream merge (which buckets by key prefix) sees the
       entries individually — otherwise they all collapse into a
       single concatenated value under ``"Company Name1"``.
    3. Lists, ints, None — stringify.

    The naive pre-fix behaviour (always ``"; ".join(inner.items())``)
    silently corrupted shape 2 by emitting
    ``"Company Name1: A; Company Name2: B"`` as the value of
    ``"Company Name1"``, dropping the per-entry structure that
    ``merge_extractions`` depends on. The 2026-06-18 regression that
    surfaced this came from the VLM-direct runaway-defense fix: when
    VLM-direct fails to parse, the merged result falls back to the
    Ask JSON, which exposed the Ask-side bug.

    Returns None if the input is empty or not a dict. The list path
    is rejected because the merge contract expects a flat dict of
    string values.
    """
    if isinstance(obj, list):
        # Brace-less/array responses are not in the schema we want;
        # the merge contract expects a flat dict. Return None so the
        # caller falls back to a different path.
        return None
    if not obj:
        return None
    cleaned: dict[str, str] = {}
    for k, v in obj.items():
        if isinstance(v, str):
            cleaned[k] = v
        elif isinstance(v, dict):
            # Distinguish "section dict" (inner keys match the outer
            # key as a prefix) from "single-value dict" (inner keys
            # are unrelated). The trade-shipping prompt produces the
            # former; the gemma4 quirk test produces the latter
            # ({"To": "CHINA"}).
            #
            # The check is per-inner-key: a single-entry section like
            # ``{"Company Name": {"Company Name1": "X"}}`` is still a
            # section wrapper (the inner key shares the outer prefix)
            # and must be promoted to a top-level key, not kept as
            # ``"Company Name": "Company Name1: X"``.
            inner_keys_match_section = all(
                isinstance(ik, str) and ik.startswith(k) for ik in v
            )
            if inner_keys_match_section:
                # Section dict: flatten by promoting inner entries to
                # top-level keys. The merge logic (merge_extractions)
                # buckets by key-prefix, so per-entry keys are what
                # downstream consumers expect.
                for inner_k, inner_v in v.items():
                    if inner_v is None:
                        continue
                    cleaned[str(inner_k)] = str(inner_v).strip()
            else:
                # Single-value dict: flatten to "key: value" string
                # for the parent key. This is the original behaviour
                # covered by test_dict_value_flattened_to_string.
                parts = [f"{ik}: {iv}" for ik, iv in v.items() if iv is not None]
                cleaned[k] = "; ".join(parts) if parts else str(v)
        elif isinstance(v, list):
            cleaned[k] = ", ".join(str(x) for x in v)
        else:
            cleaned[k] = str(v)
    return json.dumps(cleaned, ensure_ascii=False, indent=2)


@router.get("/ollama-status")
async def ollama_status() -> dict:
    """Quick reachability probe — returns whether the active chat backend
    is accessible from the backend.

    The route is still named ``/ollama-status`` for backward compatibility
    (frontend depends on the URL); when ``CHAT_PROVIDER=openai`` it probes
    the OpenAI-compatible backend's ``/v1/models`` endpoint instead.
    """
    if settings.chat_provider == "openai":
        host = settings.openai_base_url
        url = f"{host.rstrip('/')}/models"
        headers: dict[str, str] = {}
        if settings.openai_api_key:
            headers["Authorization"] = f"Bearer {settings.openai_api_key}"
        reachable = False
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(url, headers=headers)
                reachable = resp.status_code == 200
        except Exception:
            pass
        return {
            "reachable": reachable,
            "host": host,
            "model": settings.chat_model_id,
            "provider": "openai",
        }

    host = settings.ollama_host
    reachable = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{host.rstrip('/')}/api/tags")
            reachable = resp.status_code == 200
    except Exception:
        pass
    return {
        "reachable": reachable,
        "host": host,
        "model": settings.chat_model_id,
        "provider": "ollama",
    }


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
        "Chat: doc=%s model=%s messages=%d context_chars=%d provider=%s",
        doc_id,
        model,
        len(body.messages),
        len(context),
        settings.chat_provider,
    )

    if settings.chat_provider == "openai":
        stream = _stream_openai_chat(
            ollama_messages,
            model,
            settings.openai_base_url,
            settings.openai_api_key or None,
        )
    else:
        stream = _stream_ollama(ollama_messages, model, settings.ollama_host)

    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
