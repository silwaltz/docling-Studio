"""Test deep extract pipeline on Doc2 (NR Doc2-invoice.pdf).

Posts an analysis with extract_mode=deep, polls until complete, then
verifies the merged content_json has the 4-section schema.
"""
from __future__ import annotations
import json
import sys
import time
import urllib.request

DOC_PARSER = "http://localhost:8002"
DOC2_ID = "083357d3-ae26-434d-b70c-aae892ea6b07"


def post_analysis() -> str:
    url = f"{DOC_PARSER}/api/analyses"
    payload = {
        "documentId": DOC2_ID,
        "pipelineOptions": {
            "extract_mode": "deep",
            "do_ocr": True,
            "do_table_structure": True,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8-sig")
    data = json.loads(body)
    aid = data.get("id") or data.get("analysisId")
    print(f"POST /api/analyses → {resp.status} (id={aid}, status={data.get('status')})")
    return aid


def poll(aid: str, timeout_s: int = 600) -> dict:
    url = f"{DOC_PARSER}/api/analyses/{aid}"
    t0 = time.time()
    last_status = None
    while time.time() - t0 < timeout_s:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8-sig"))
        st = data.get("status")
        if st != last_status:
            print(f"  t+{time.time()-t0:5.1f}s  status={st}  progress={data.get('progress')}")
            last_status = st
        if st in ("COMPLETED", "FAILED"):
            return data
        time.sleep(3)
    print("TIMEOUT")
    sys.exit(1)


def section_counts(content_json: dict | None) -> dict[str, int]:
    """Count 4-section keys in the merged deep-extract JSON."""
    if not isinstance(content_json, dict):
        return {}
    counts = {"Company Name": 0, "Address": 0, "Shipping Information": 0, "Goods Description": 0}
    for k in content_json:
        for prefix in counts:
            if k.startswith(prefix):
                counts[prefix] += 1
                break
    return counts


if __name__ == "__main__":
    print("=" * 70)
    print("Test: deep extract pipeline on Doc2 (extract_mode=deep)")
    print("=" * 70)
    aid = post_analysis()
    result = poll(aid)
    if result.get("status") != "COMPLETED":
        print("FAIL:", json.dumps(result, indent=2)[:2000])
        sys.exit(1)

    print(f"\nFinal status: {result.get('status')}")
    print(f"Final progress: {result.get('progress')}")

    cj = result.get("contentJson") or result.get("content_json")
    # The API returns contentJson as a JSON-encoded string, not a dict —
    # normalise before counting.
    if isinstance(cj, str):
        cj_parsed = json.loads(cj)
    else:
        cj_parsed = cj

    print(f"\ncontentJson keys ({len(cj_parsed) if isinstance(cj_parsed, dict) else 'n/a'}):")
    if isinstance(cj_parsed, dict):
        for k in cj_parsed:
            v = cj_parsed[k]
            preview = (v[:80] + "…") if isinstance(v, str) and len(v) > 80 else v
            print(f"  {k}: {preview}")
    print("\n--- raw contentJson (first 4 KB) ---")
    print(json.dumps(cj_parsed, indent=2, ensure_ascii=False)[:4096])

    counts = section_counts(cj_parsed)
    print("\n4-section counts:", counts)
    total = sum(counts.values())
    print(f"Total entities: {total}")
    if total < 1:
        print("FAIL: no 4-section keys")
        sys.exit(1)

    # Also list deep_extract_artifacts on disk
    print("\n--- artifacts on disk ---")
    import subprocess
    r = subprocess.run(
        ["docker", "exec", "docling-studio-document-parser-1", "ls", "-la", "/app/data/deep_extract_artifacts"],
        capture_output=True, text=True
    )
    print(r.stdout)
    print(r.stderr)
    print("\nDEEP EXTRACT OK")
