"""Full Doc1-13 deep-extract (extractMode=deep) test.

For each of the 13 NR docs:
  1. POST /api/analyses with extractMode=deep
  2. Poll for completion (long timeout — Doc1 is 12 pages)
  3. Capture: timing, status, content_json, error_message, isStale
  4. Save to extracted-json/deep_extract__<slug>.json
  5. Mark isStale at any point the row is in RUNNING for too long

Output: extracted-json/deep_extract__FULL_REPORT.md with timing/score table.
"""
import json
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

BACKEND = "http://localhost:8000"
DOCS_FILE = Path(__file__).parent / "docs_full.json"
OUT_DIR = Path(__file__).parent.parent / "extracted-json"
OUT_DIR.mkdir(exist_ok=True)


def post(url, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    return json.loads(urllib.request.urlopen(req, timeout=600).read())


def get(url):
    return json.loads(urllib.request.urlopen(url, timeout=60).read())


def trigger_deep_extract(doc_id: str) -> str:
    body = {
        "documentId": doc_id,
        "pipelineOptions": {
            "extractMode": "deep",
            "doOcr": True,
            "doTableStructure": True,
        },
    }
    r = post(f"{BACKEND}/api/analyses", body)
    return r["id"]


def wait_for_completion(analysis_id: str, timeout_sec: int = 2400) -> dict:
    """Long timeout — Doc1 is 12 pages and deep runs both pipelines."""
    t0 = time.time()
    last_status = None
    while time.time() - t0 < timeout_sec:
        try:
            a = get(f"{BACKEND}/api/analyses/{analysis_id}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Job was deleted by the user / stuck-job sweep.
                return {"status": "DELETED", "id": analysis_id}
            raise
        if a["status"] != last_status:
            print(
                f"    t+{time.time()-t0:.0f}s  status={a['status']} "
                f"progress={a.get('progressCurrent', '?')}/{a.get('progressTotal', '?')}"
                f"{'  isStale=YES' if a.get('isStale') else ''}",
                flush=True,
            )
            last_status = a["status"]
        if a["status"] in ("COMPLETED", "FAILED"):
            return a
        time.sleep(5)
    return {"status": "TIMEOUT", "id": analysis_id}


def slugify(name: str) -> str:
    s = name.replace(" (FULL)(LC,Inv,BL,AWB, insurance policy)", "_FULL")
    for ch in " (),":
        s = s.replace(ch, "_")
    s = s.replace(".pdf", "").replace("__", "_").strip("_")
    return s


def main():
    with open(DOCS_FILE) as f:
        docs = json.load(f)
    print(
        f"Deep-Extract (extractMode=deep) full test — {len(docs)} docs\n"
        f"Backend: {BACKEND}\n"
    )

    summary = []
    for d in docs:
        slug = slugify(d["filename"])
        out_path = OUT_DIR / f"deep_extract__{slug}.json"
        print(f"\n=== {d['filename']} (pages={d['page_count']}) ===")
        try:
            t0 = time.time()
            aid = trigger_deep_extract(d["doc_id"])
            print(f"  analysis_id={aid}")
            result = wait_for_completion(aid)
            elapsed = time.time() - t0
            print(
                f"  DONE in {elapsed:.0f}s  status={result['status']}"
                f"  error={result.get('errorMessage')}"
            )
            summary.append(
                {
                    "filename": d["filename"],
                    "pages": d["page_count"],
                    "elapsed_sec": round(elapsed),
                    "status": result["status"],
                    "error": result.get("errorMessage"),
                    "analysis_id": aid,
                    "has_content_json": bool(result.get("contentJson")),
                    "key_count": (
                        len(json.loads(result["contentJson"]))
                        if result.get("contentJson")
                        else 0
                    ),
                }
            )
            # Save the full result
            out_path.write_text(
                json.dumps(
                    {
                        "filename": d["filename"],
                        "doc_id": d["doc_id"],
                        "analysis_id": aid,
                        "elapsed_sec": round(elapsed),
                        "result": result,
                    },
                    indent=2,
                    default=str,
                )
            )
            print(f"  saved → {out_path}")
        except Exception as e:
            elapsed = time.time() - t0 if "t0" in dir() else 0
            print(f"  EXCEPTION: {e!r}")
            summary.append(
                {
                    "filename": d["filename"],
                    "pages": d["page_count"],
                    "elapsed_sec": round(elapsed),
                    "status": "EXCEPTION",
                    "error": repr(e),
                }
            )

    # Write a summary
    out_summary = OUT_DIR / "deep_extract__FULL_SUMMARY.json"
    out_summary.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nSummary written to {out_summary}")
    print()
    for s in summary:
        print(
            f"  {s['filename']:55s} {s.get('status', '?'):>10s}  "
            f"{s.get('elapsed_sec', 0):>5d}s  "
            f"keys={s.get('key_count', 0):>3d}  "
            f"{s.get('error') or ''}"
        )


if __name__ == "__main__":
    main()
