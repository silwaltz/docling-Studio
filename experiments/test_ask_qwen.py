"""Test 1: Verify the Ask chat path through the OpenAI-compatible vLLM endpoint.

Calls /api/documents/ollama-status for connectivity, then directly hits the
vLLM OpenAI-compat /v1/chat/completions to confirm a text-only Ask-prompt
response comes back and parses as the 4-section JSON.
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.request
import urllib.error


VLLM_URL = "http://localhost:8000/v1/chat/completions"
DOC_PARSER = "http://localhost:8002"
MODEL = "qwen3-vl:8b-instruct"

# Tiny trade-shipping-like context (mimics what /api/documents/:id/chat sends).
ASK_SYSTEM = (
    'You are a trade-shipping document analyst. Read the document below and '
    'extract every distinct entity.\n\nOutput a single JSON object (NOT an '
    'array, NOT wrapped in code fences) with these exact key prefixes and a '
    'numeric suffix starting at 1:\n- "Company Name<n>" = the legal/registered '
    'name of a company, bank, agency, broker, or organization that appears '
    'in the document.\n- "Address<n>" = a postal or physical address.\n- '
    '"Shipping Information<n>" = routing and transport details.\n- '
    '"Goods Description<n>" = the product name only.\n\nRules:\n- Output ONLY '
    'the JSON object. No markdown, no code fences, no preamble, no commentary.\n'
    '- Every value MUST be a plain string.\n- Replace newlines inside values '
    'with a single space.\n- Normalize whitespace: collapse multiple spaces '
    'to one.\n\nDocument context: {context}'
)
CONTEXT = """
INVOICE

SHIPPER:
Acme Coffee Exporters Ltd
123 Bean Street
Lima, Peru

CONSIGNEE:
EuroBeans GmbH
Hauptstrasse 42
Hamburg, Germany

NOTIFY PARTY:
EuroBeans GmbH
Hauptstrasse 42
Hamburg, Germany

Shipping Information:
From: Callao, Peru
To: Hamburg, Germany
Via: MSC OSCAR, voyage 12W
Date: 2024-09-15

Goods Description:
WASHED GREEN COFFEE PERUVIAN ALTURA EURO PREPARATION (E.P.)
250 BAGS OF 69 KILOGRAMS NET EACH
""".strip()

# ---- Test A: ollama-status via document-parser --------------------------------
def test_status() -> None:
    print("=" * 70)
    print("Test A: document-parser /api/documents/ollama-status")
    print("=" * 70)
    url = f"{DOC_PARSER}/api/documents/ollama-status"
    with urllib.request.urlopen(url, timeout=5) as resp:
        body = resp.read().decode("utf-8-sig")
    data = json.loads(body)
    print(json.dumps(data, indent=2))
    assert data["reachable"], "vLLM not reachable via the document-parser!"
    assert data["provider"] == "openai", f"expected openai, got {data['provider']}"
    assert data["model"] == MODEL, f"expected {MODEL}, got {data['model']}"
    print("OK\n")


# ---- Test B: direct /v1/chat/completions to vLLM -----------------------------
def test_chat_completion() -> str:
    print("=" * 70)
    print("Test B: direct vLLM /v1/chat/completions (Ask-style prompt)")
    print("=" * 70)
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": ASK_SYSTEM.format(context=CONTEXT)},
            {"role": "user", "content": "Extract the JSON object."},
        ],
        "max_tokens": 2048,
        "temperature": 0.0,
    }
    req = urllib.request.Request(
        VLLM_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = resp.read().decode("utf-8")
    dt = time.time() - t0
    data = json.loads(body)
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    print(f"latency: {dt:.2f}s")
    print(f"usage:   {usage}")
    print(f"model:   {data.get('model')}")
    print("---response---")
    print(content)
    print("--------------")
    return content


# ---- Test C: streaming chat completion ---------------------------------------
def test_streaming_chat() -> str:
    print("\n" + "=" * 70)
    print("Test C: streaming vLLM /v1/chat/completions")
    print("=" * 70)
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": ASK_SYSTEM.format(context=CONTEXT)},
            {"role": "user", "content": "Extract the JSON object."},
        ],
        "max_tokens": 2048,
        "temperature": 0.0,
        "stream": True,
    }
    req = urllib.request.Request(
        VLLM_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    full: list[str] = []
    chunks = 0
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line or line == "data: [DONE]":
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            for choice in evt.get("choices") or []:
                delta = (choice.get("delta") or {}).get("content") or ""
                if delta:
                    full.append(delta)
                    chunks += 1
    dt = time.time() - t0
    out = "".join(full)
    print(f"latency: {dt:.2f}s, chunks: {chunks}")
    print("---response (streamed)---")
    print(out)
    print("--------------------------")
    return out


# ---- Test D: parse Ask output into a 4-section dict --------------------------
def _try_parse_obj(text: str) -> dict | None:
    """Best-effort parse of the Ask output into a dict."""
    t = text.strip()
    # Strip code fences.
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.startswith("json"):
            t = t[4:].strip()
    if t.startswith("{"):
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            pass
    # Brace-less: wrap if it looks like "key":"value" pairs.
    if t.startswith('"'):
        try:
            return json.loads("{" + t.rstrip(",").rstrip() + "}")
        except json.JSONDecodeError:
            return None
    return None


def test_parse(content: str) -> None:
    print("\n" + "=" * 70)
    print("Test D: parse 4-section JSON from Ask output")
    print("=" * 70)
    obj = _try_parse_obj(content)
    if not obj:
        print("FAIL: could not parse 4-section JSON")
        sys.exit(1)
    print(json.dumps(obj, indent=2))
    keys = list(obj.keys())
    sections = {"Company Name": 0, "Address": 0, "Shipping Information": 0, "Goods Description": 0}
    for k in keys:
        for prefix in sections:
            if k.startswith(prefix):
                sections[prefix] += 1
    print("\nSection counts:", sections)
    total = sum(sections.values())
    assert total >= 1, "no 4-section keys found at all"
    print("OK")


if __name__ == "__main__":
    test_status()
    content = test_chat_completion()
    test_streaming_chat()
    test_parse(content)
    print("\nALL SMOKE TESTS PASSED")
