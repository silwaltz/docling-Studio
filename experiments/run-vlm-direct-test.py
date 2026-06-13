"""
VLM-direct pipeline test: qwen3-vl:8b (markdown mode) > aggregated markdown > Gemma 4 Ask.

For each doc:
1. POST /api/analyses with forceVlmPipeline=true, vlmBackend='ollama', vlmOutputMode='markdown'
2. Poll for completion
3. Save the new content_markdown for inspection
4. Run the same v1 Ask prompt via /api/.../chat
5. Save the Ask JSON output
6. Score against golden xlsx

Compare to standard-pipeline results.
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
USER_QUERY = "Extrait toutes les adresses, noms de sociétés, informations de transport et descriptions des marchandises au format JSON."


def post(url, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    return json.loads(urllib.request.urlopen(req, timeout=600).read())


def get(url):
    return json.loads(urllib.request.urlopen(url, timeout=60).read())


def trigger_vlm_analysis(doc_id: str) -> str:
    """Create a VLM-direct analysis. Returns analysis_id."""
    body = {
        "documentId": doc_id,
        "pipelineOptions": {
            "forceVlmPipeline": True,
            "vlmBackend": "ollama",
            "vlmOutputMode": "markdown",
            "vlmImageScale": 2.0,
        },
    }
    r = post(f"{BACKEND}/api/analyses", body)
    return r["id"]


def wait_for_completion(analysis_id: str, timeout_sec: int = 600) -> dict:
    """Poll until status is COMPLETED or FAILED. Returns final analysis dict."""
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


def post_chat(doc_id: str) -> dict:
    url = f"{BACKEND}/api/documents/{doc_id}/chat"
    body = json.dumps({
        "messages": [{"role": "user", "content": USER_QUERY}],
        "model": "gemma4:e4b-it-qat",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    full_text = ""
    meta = {}
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as resp:
        buf = ""
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            buf += chunk.decode("utf-8", errors="replace")
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                for line in frame.splitlines():
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue
                    try:
                        ev = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    if "error" in ev:
                        return {"error": ev["error"], "elapsed": time.time() - t0, "text": full_text}
                    if "delta" in ev:
                        full_text += ev["delta"]
                    if ev.get("done"):
                        meta = ev
    return {"elapsed": round(time.time() - t0, 2), "text": full_text, "meta": meta}


def extract_json(text: str) -> str | None:
    t = text
    t = re.sub(r'"(Company Name|Address|Shipping Information|Goods Description)<(\d+)>"', r'"\1\2"', t)
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)```", t)
    if fenced:
        try:
            json.loads(fenced.group(1).strip())
            return fenced.group(1).strip()
        except Exception:
            pass
    for open_c, close_c in [("{", "}"), ("[", "]")]:
        start = t.find(open_c)
        if start < 0:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(t)):
            ch = t[i]
            if esc:
                esc = False
                continue
            if in_str:
                if ch == "\\":
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
                    cand = t[start : i + 1]
                    try:
                        json.loads(cand)
                        return cand
                    except Exception:
                        break
    stripped = t.strip()
    colon_count = len(re.findall(r'"[^"]+"\s*:\s*"', stripped))
    if stripped.startswith('"') and colon_count >= 2:
        wrapped = "{" + stripped.rstrip().rstrip(",") + "}"
        try:
            json.loads(wrapped)
            return wrapped
        except Exception:
            pass
    eq_count = len(re.findall(r'"[A-Za-z][^"]*"\s*=\s*"', stripped))
    if stripped.startswith('"') and eq_count >= 2:
        normalized = re.sub(r'"([A-Za-z][^"]*?)"\s*=\s*"', r'"\1":"', stripped)
        wrapped = "{" + normalized.rstrip().rstrip(",") + "}"
        try:
            json.loads(wrapped)
            return wrapped
        except Exception:
            pass
    return None


def main():
    with open(DOCS_FILE) as f:
        docs = json.load(f)
    print(f"VLM-direct test: qwen3-vl:8b markdown mode -> Gemma 4 Ask")
    print(f"Backend: {BACKEND}")
    print(f"Docs: {len(docs)}\n")

    summary = []
    for d in docs:
        print(f"\n=== {d['filename']} (chars={d['md_chars']}) ===")
        # 1) Trigger VLM analysis
        try:
            aid = trigger_vlm_analysis(d["doc_id"])
            print(f"  triggered analysis: {aid}")
        except Exception as e:
            print(f"  trigger FAILED: {e}")
            summary.append({"doc_id": d["doc_id"], "filename": d["filename"], "error": str(e)})
            continue
        # 2) Wait
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
        # 3) Save new markdown
        new_md = final.get("contentMarkdown") or ""
        print(f"  VLM markdown: {len(new_md)} chars")
        slug = re.sub(r"[^\w.-]+", "_", d["filename"])[:80]
        md_path = OUT_DIR / f"vlm__{d['doc_id'][:8]}__{slug}.md"
        md_path.write_text(new_md, encoding="utf-8")
        # 4) Run Ask
        try:
            r = post_chat(d["doc_id"])
        except Exception as e:
            print(f"  Ask FAILED: {e}")
            summary.append({"doc_id": d["doc_id"], "filename": d["filename"], "error": str(e), "vlm_md_chars": len(new_md), "analysis_id": aid})
            continue
        if r.get("error"):
            print(f"  Ask error: {r['error']}")
            summary.append({"doc_id": d["doc_id"], "filename": d["filename"], "error": r["error"], "vlm_md_chars": len(new_md), "analysis_id": aid})
            continue
        text = r["text"]
        meta = r.get("meta", {})
        raw_path = OUT_DIR / f"vlm_ask__{d['doc_id'][:8]}__{slug}.raw.txt"
        raw_path.write_text(text, encoding="utf-8")
        # 5) Parse + save
        parsed_ok = False
        key_count = 0
        json_str = extract_json(text)
        if json_str:
            cleaned = json_str.replace("\\_", " ")
            try:
                parsed = json.loads(cleaned)
                arr = parsed if isinstance(parsed, list) else [parsed]
                json_path = OUT_DIR / f"vlm_ask__{d['doc_id'][:8]}__{slug}.json"
                json_path.write_text(json.dumps(arr, indent=2, ensure_ascii=False), encoding="utf-8")
                parsed_ok = True
                key_count = sum(len(o) for o in arr)
            except Exception as e:
                (OUT_DIR / f"vlm_ask__{d['doc_id'][:8]}__{slug}.ERROR.json").write_text(str(e), encoding="utf-8")
        else:
            (OUT_DIR / f"vlm_ask__{d['doc_id'][:8]}__{slug}.NOPARSE.json").write_text("ERROR", encoding="utf-8")
        print(f"  Ask: {r['elapsed']}s tokens={meta.get('total_tokens', '?')} keys={key_count} parsed={parsed_ok}")
        summary.append({
            "doc_id": d["doc_id"],
            "filename": d["filename"],
            "analysis_id": aid,
            "vlm_md_chars": len(new_md),
            "ask_elapsed_sec": r["elapsed"],
            "ask_total_tokens": meta.get("total_tokens"),
            "parsed_ok": parsed_ok,
            "key_count": key_count,
        })
        # Save summary progressively
        (OUT_DIR / "vlm__RUN_SUMMARY.json").write_text(
            json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "n": len(summary), "results": summary}, indent=2),
            encoding="utf-8",
        )
    print(f"\n=== Done. {sum(1 for s in summary if s.get('parsed_ok'))}/{len(summary)} parsed ===")
    (OUT_DIR / "vlm__RUN_SUMMARY.json").write_text(
        json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "n": len(summary), "n_parsed": sum(1 for s in summary if s.get("parsed_ok")), "results": summary}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
