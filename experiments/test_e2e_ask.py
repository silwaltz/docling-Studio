"""Test 2: end-to-end Ask path against an existing analysis.

Uses the document_id of an existing completed analysis (NR Doc2-invoice.pdf
in the golden set) and runs the chat endpoint. Verifies:
  - SSE stream parses
  - Response is a 4-section JSON object
  - Qwen produces output for real trade-shipping markdown
"""
from __future__ import annotations
import json
import sys
import time
import urllib.request
import urllib.error

DOC_PARSER = "http://localhost:8002"
DOC2_ID = "083357d3-ae26-434d-b70c-aae892ea6b07"
DOC2_ANALYSIS = "864a573a-35d2-40b0-bc09-a51b3d886901"


def run_chat() -> str:
    print("=" * 70)
    print("Chat: doc2 (NR Doc2-invoice.pdf) via /api/documents/:id/chat")
    print("=" * 70)
    url = f"{DOC_PARSER}/api/documents/{DOC2_ID}/chat"
    payload = {
        "messages": [
            {"role": "user", "content": "Extract the JSON object for the document above."},
        ],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    full: list[str] = []
    events: list[dict] = []
    done = None
    with urllib.request.urlopen(req, timeout=600) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            events.append(evt)
            if "delta" in evt:
                full.append(evt["delta"])
            if "done" in evt:
                done = evt
            if "error" in evt:
                print("ERROR from chat:", evt["error"])
                sys.exit(1)
    dt = time.time() - t0
    out = "".join(full)
    print(f"latency: {dt:.2f}s, delta events: {sum(1 for e in events if 'delta' in e)}")
    print(f"done: {done}")
    print("---response---")
    print(out)
    print("--------------")
    return out


def parse_sections(text: str) -> dict[str, int]:
    """Count 4-section keys."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.startswith("json"):
            t = t[4:].strip()
    obj = None
    if t.startswith("{"):
        try:
            obj = json.loads(t)
        except json.JSONDecodeError:
            pass
    if obj is None and t.startswith('"'):
        try:
            obj = json.loads("{" + t.rstrip(",").rstrip() + "}")
        except json.JSONDecodeError:
            return {}
    if obj is None:
        return {}
    counts = {"Company Name": 0, "Address": 0, "Shipping Information": 0, "Goods Description": 0}
    for k in obj:
        for prefix in counts:
            if k.startswith(prefix):
                counts[prefix] += 1
    return counts


if __name__ == "__main__":
    out = run_chat()
    print("\n" + "=" * 70)
    print("Parse 4-section counts")
    print("=" * 70)
    counts = parse_sections(out)
    if not counts:
        print("FAIL: could not parse JSON")
        sys.exit(1)
    print(counts)
    total = sum(counts.values())
    print(f"Total entities: {total}")
    assert total >= 1, "no 4-section keys extracted"
    print("OK")
