"""
Run all docs through the LIVE backend's /api/documents/:id/chat endpoint
using the v1 prompt that's now in production (chat.py), and save the
parsed JSON outputs to extracted-json/.

This is the "shipped" version of the pipeline — same code path the frontend
hits. Verifies that the v1 prompt is actually live in the backend and gives
the user artifacts they can open and inspect.
"""
import json
import re
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

BACKEND = "http://localhost:3000"
DOCS_FILE = Path(__file__).parent / "docs_full.json"
OUT_DIR = Path(__file__).parent.parent / "extracted-json"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Same query the frontend preset button sends
USER_QUERY = "Extrait toutes les adresses, noms de sociétés, informations de transport et descriptions des marchandises au format JSON."


def post_chat(doc_id: str) -> dict:
    """POST to /api/documents/:id/chat, parse the SSE stream, return full text + meta."""
    url = f"{BACKEND}/api/documents/{doc_id}/chat"
    body = json.dumps({
        "messages": [{"role": "user", "content": USER_QUERY}],
        "model": "gemma4:e4b-it-qat",  # explicit override — backend default in compose is "gemma4:e4b" which doesn't exist
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    full_text = ""
    final_meta = {}
    with urllib.request.urlopen(req, timeout=600) as resp:
        buf = ""
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            buf += chunk.decode("utf-8", errors="replace")
            # SSE frames split on blank line
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                for line in frame.splitlines():
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if not payload:
                        continue
                    try:
                        ev = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if "error" in ev:
                        return {"error": ev["error"], "elapsed": time.time() - t0, "text": full_text}
                    if "delta" in ev:
                        full_text += ev["delta"]
                    if "done" in ev and ev.get("done"):
                        final_meta = ev
    return {
        "elapsed": round(time.time() - t0, 2),
        "text": full_text,
        "meta": final_meta,
    }


def extract_json(text: str) -> str | None:
    """Frontend's extractJson logic + brace-less fallback for gemma4 streaming.

    gemma4:e4b-it-qat sometimes drops the wrapping { } in streaming output,
    leaving a sequence of "key":"value" pairs. We try to recover by wrapping
    such sequences and re-parsing.
    """
    # 1) Try fenced
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fenced:
        c = fenced.group(1).strip()
        try:
            json.loads(c)
            return c
        except Exception:
            pass
    # 2) Try brace/bracket matching
    for open_c, close_c in [("{", "}"), ("[", "]")]:
        start = text.find(open_c)
        if start < 0:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
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
                    cand = text[start : i + 1]
                    try:
                        json.loads(cand)
                        return cand
                    except Exception:
                        break
    # 3) Brace-less fallback: text starts with "key": pattern, treat as flat object
    stripped = text.strip()
    if stripped.startswith('"') and '":' in stripped:
        # Heuristic: contains at least 2 "key": patterns → wrap in { }
        if stripped.count('":') >= 2:
            # Strip trailing comma if any
            wrapped = "{" + stripped.rstrip().rstrip(",") + "}"
            try:
                json.loads(wrapped)
                return wrapped
            except Exception:
                # Try removing trailing partial key
                # Find last "key": "value" boundary
                last_full = max(
                    wrapped.rfind('",'),
                    wrapped.rfind('":null'),
                )
                if last_full > 0:
                    cut = wrapped[: last_full + 1] + "}"
                    try:
                        json.loads(cut)
                        return cut
                    except Exception:
                        pass
    return None


def main():
    with open(DOCS_FILE) as f:
        docs = json.load(f)
    print(f"Running {len(docs)} docs through LIVE /api/.../chat (v1 prompt)")
    print(f"Backend: {BACKEND}")
    print(f"Output dir: {OUT_DIR}\n")

    summary = []
    for d in docs:
        print(f"  - {d['filename']:55s} md={d['md_chars']:>6}c  ...", end=" ", flush=True)
        try:
            r = post_chat(d["doc_id"])
        except urllib.error.HTTPError as e:
            print(f"HTTP {e.code}: {e.reason}")
            summary.append({"doc_id": d["doc_id"], "filename": d["filename"], "error": f"HTTP {e.code}: {e.reason}"})
            continue
        except Exception as e:
            print(f"ERROR: {e}")
            summary.append({"doc_id": d["doc_id"], "filename": d["filename"], "error": str(e)})
            continue

        if r.get("error"):
            print(f"backend error: {r['error']}")
            summary.append({"doc_id": d["doc_id"], "filename": d["filename"], "error": r["error"]})
            continue

        text = r["text"]
        meta = r.get("meta", {})
        # Save raw stream
        slug = re.sub(r"[^\w.-]+", "_", d["filename"])[:80]
        raw_path = OUT_DIR / f"ask_v1__{d['doc_id'][:8]}__{slug}.raw.txt"
        raw_path.write_text(text, encoding="utf-8")
        # Save cleaned JSON
        json_str = extract_json(text)
        parsed_ok = False
        if json_str:
            cleaned = json_str.replace("\\_", " ")
            try:
                parsed = json.loads(cleaned)
                # Normalize: if dict, wrap in list; if list of dicts, keep
                if isinstance(parsed, dict):
                    arr = [parsed]
                elif isinstance(parsed, list):
                    arr = parsed
                else:
                    arr = []
                json_path = OUT_DIR / f"ask_v1__{d['doc_id'][:8]}__{slug}.json"
                json_path.write_text(json.dumps(arr, indent=2, ensure_ascii=False), encoding="utf-8")
                parsed_ok = True
                # Count keys
                key_count = sum(len(o) for o in arr)
            except Exception as e:
                json_path = OUT_DIR / f"ask_v1__{d['doc_id'][:8]}__{slug}.ERROR.json"
                json_path.write_text(f'{{"error": "{e}", "raw": "{json_str[:200]}"}}', encoding="utf-8")
                key_count = 0
        else:
            json_path = OUT_DIR / f"ask_v1__{d['doc_id'][:8]}__{slug}.NOPARSE.json"
            json_path.write_text("ERROR: no parseable JSON in response", encoding="utf-8")
            key_count = 0

        print(f"elapsed={r['elapsed']}s  tokens={meta.get('total_tokens', '?')}  keys={key_count}  parsed={parsed_ok}")
        summary.append({
            "doc_id": d["doc_id"],
            "filename": d["filename"],
            "md_chars": d["md_chars"],
            "elapsed_sec": r["elapsed"],
            "total_tokens": meta.get("total_tokens"),
            "model": meta.get("model"),
            "parsed_ok": parsed_ok,
            "key_count": key_count,
            "raw_path": str(raw_path),
            "json_path": str(json_path),
        })

    # Write run summary
    summary_path = OUT_DIR / "ask_v1__RUN_SUMMARY.json"
    summary_path.write_text(json.dumps({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "backend": BACKEND,
        "model": summary[0].get("model") if summary else None,
        "n_docs": len(summary),
        "n_parsed": sum(1 for s in summary if s.get("parsed_ok")),
        "results": summary,
    }, indent=2), encoding="utf-8")
    print(f"\nWrote {summary_path}")
    print(f"  parsed: {sum(1 for s in summary if s.get('parsed_ok'))} / {len(summary)}")


if __name__ == "__main__":
    main()
