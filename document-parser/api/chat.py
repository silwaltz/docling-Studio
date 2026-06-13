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

    Gemma 4 (and other small models) occasionally emit a value as a
    Python-dict literal or list instead of a flat string — e.g.
    `{"To": "CHINA"}` instead of `"To: CHINA"`. The Deep-Extract
    merge contract requires string-only values (the merge logic and
    the downstream `content_json` schema both assume `str`), so
    flatten any non-string value to a `key: value; key: value`
    representation before serialising. Returns None if the dict is
    empty. Accepts either a dict or a list (other shapes are rejected
    by the caller before this is called).
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
            # Flatten `{"To": "CHINA"}` → `"To: CHINA"`.
            parts = [f"{ik}: {iv}" for ik, iv in v.items() if iv is not None]
            cleaned[k] = "; ".join(parts) if parts else str(v)
        elif isinstance(v, list):
            cleaned[k] = ", ".join(str(x) for x in v)
        else:
            cleaned[k] = str(v)
    return json.dumps(cleaned, ensure_ascii=False, indent=2)


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
