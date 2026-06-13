"""
VLM-direct JSON-mode test (qwen3-vl:8b-instruct, json output mode).

Per user request: skip the Ask step. qwen3-vl's output IS the final answer.
Reads content_json directly, no Gemma 4 needed.

For each doc:
1. POST /api/analyses with forceVlmPipeline=true, vlmBackend=ollama, vlmOutputMode=json
2. Poll for completion
3. Save content_json as the final extraction
4. Score against golden xlsx
"""
import json
import re
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

BACKEND = "http://localhost:3000"
DOCS_FILE = Path(__file__).parent / "docs_full.json"
OUT_DIR = Path(__file__).parent.parent / "extracted-json"


def post(url, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=600).read())


def get(url):
    return json.loads(urllib.request.urlopen(url, timeout=60).read())


def trigger_vlm_json(doc_id: str) -> str:
    body = {
        "documentId": doc_id,
        "pipelineOptions": {
            "forceVlmPipeline": True,
            "vlmBackend": "ollama",
            "vlmOutputMode": "json",  # qwen3-vl produces JSON
            "vlmImageScale": 2.0,
        },
    }
    r = post(f"{BACKEND}/api/analyses", body)
    return r["id"]


def wait_for_completion(analysis_id: str, timeout_sec: int = 600) -> dict:
    t0 = time.time()
    last_status = None
    while time.time() - t0 < timeout_sec:
        a = get(f"{BACKEND}/api/analyses/{analysis_id}")
        if a["status"] != last_status:
            print(f"    status={a['status']} progress={a.get('progressCurrent', '?')}/{a.get('progressTotal', '?')}", flush=True)
            last_status = a["status"]
        if a["status"] in ("COMPLETED", "FAILED"):
            return a
        time.sleep(5)
    raise TimeoutError(f"Analysis {analysis_id} did not finish in {timeout_sec}s")


def parse_content_json(cj_str: str) -> list[dict] | None:
    """Parse content_json into a list of dicts (frontend-friendly)."""
    if not cj_str or not cj_str.strip():
        return None
    try:
        cleaned = cj_str.replace("\\_", " ")
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return [parsed]
        if isinstance(parsed, list):
            return parsed
        return None
    except Exception as e:
        # Try brace-less fallback
        try:
            t = cleaned.strip()
            if t.startswith('"') and '":' in t:
                wrapped = "{" + t.rstrip().rstrip(",") + "}"
                parsed = json.loads(wrapped)
                if isinstance(parsed, dict):
                    return [parsed]
        except Exception:
            pass
        return None


def main():
    with open(DOCS_FILE) as f:
        docs = json.load(f)
    print(f"VLM-direct JSON-mode test: qwen3-vl:8b-instruct, NO Ask step")
    print(f"Backend: {BACKEND}\n")

    summary = []
    for d in docs:
        print(f"\n=== {d['filename']} (pages={d['page_count']}) ===")
        try:
            aid = trigger_vlm_json(d["doc_id"])
        except Exception as e:
            print(f"  trigger FAILED: {e}")
            summary.append({"doc_id": d["doc_id"], "filename": d["filename"], "error": str(e)})
            continue
        try:
            final = wait_for_completion(aid, timeout_sec=600)
        except Exception as e:
            print(f"  wait FAILED: {e}")
            summary.append({"doc_id": d["doc_id"], "filename": d["filename"], "error": str(e), "analysis_id": aid})
            continue
        if final["status"] != "COMPLETED":
            print(f"  status={final['status']} err={final.get('errorMessage')}")
            summary.append({"doc_id": d["doc_id"], "filename": d["filename"], "status": final["status"], "error": final.get("errorMessage"), "analysis_id": aid})
            continue

        cj = final.get("contentJson") or ""
        cm = final.get("contentMarkdown") or ""
        print(f"  content_json: {len(cj)} chars, content_markdown: {len(cm)} chars")

        # Save both for inspection
        slug = re.sub(r"[^\w.-]+", "_", d["filename"])[:80]
        cj_path = OUT_DIR / f"vlm_json__{d['doc_id'][:8]}__{slug}.json"
        # Parse and save canonical form
        parsed = parse_content_json(cj)
        if parsed:
            cj_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
            key_count = sum(len(o) for o in parsed)
            print(f"  saved: {cj_path.name} ({key_count} keys)")
        else:
            cj_path.write_text(f'{{"error": "parse failed", "raw": "{cj[:200]}"}}', encoding="utf-8")
            key_count = 0
            print(f"  parse FAILED")
        # Also save raw
        raw_path = OUT_DIR / f"vlm_json__{d['doc_id'][:8]}__{slug}.raw.json"
        raw_path.write_text(cj, encoding="utf-8")

        summary.append({
            "doc_id": d["doc_id"],
            "filename": d["filename"],
            "analysis_id": aid,
            "cj_chars": len(cj),
            "cm_chars": len(cm),
            "parsed_ok": parsed is not None,
            "key_count": key_count,
        })
        (OUT_DIR / "vlm_json__RUN_SUMMARY.json").write_text(
            json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "n": len(summary), "results": summary}, indent=2),
            encoding="utf-8",
        )

    parsed_count = sum(1 for s in summary if s.get("parsed_ok"))
    print(f"\n=== Done. {parsed_count}/{len(summary)} parsed ===")
    (OUT_DIR / "vlm_json__RUN_SUMMARY.json").write_text(
        json.dumps({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "n": len(summary),
            "n_parsed": parsed_count,
            "results": summary,
        }, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
