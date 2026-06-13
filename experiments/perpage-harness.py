"""
Per-page Ask experiment.

Splits the document markdown by page markers (`## ` headings or page-break
indicators), runs the Ask prompt on each page separately, then merges the
per-page JSON outputs.

The hypothesis: gemma4:e4b has trouble with long contexts (24k+ tokens). For
multi-page documents, the per-page approach gives the model a tighter focus.
"""
import json
import re
from pathlib import Path
from typing import Optional

import sys
import importlib.util
_spec = importlib.util.spec_from_file_location("prompt_harness", Path(__file__).parent / "prompt-harness.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
OLLAMA_HOST = _mod.OLLAMA_HOST
DEFAULT_MODEL = _mod.DEFAULT_MODEL
BASELINE_PROMPT = _mod.BASELINE_PROMPT
USER_MESSAGE = _mod.USER_MESSAGE
call_ollama = _mod.call_ollama
extract_json = _mod.extract_json
parse_json_array = _mod.parse_json_array
score_doc = _mod.score_doc
load_golden = _mod.load_golden
GOLDEN_SHEETS = _mod.GOLDEN_SHEETS
GOLDEN_XLSX = _mod.GOLDEN_XLSX

DOCS_FILE = Path(__file__).parent / "docs_full.json"
RUNS_DIR = Path(__file__).parent / "prompt-runs"


def split_pages(md: str) -> list[str]:
    """Split markdown by page boundaries.

    The Qwen-VL output uses `## ` for headings, and some pages have image
    markers like `<!-- image -->`. We split by the strongest signal: the
    docling page marker if present, else by `## ` headings.
    """
    # Try docling-style page markers first: <!-- page -->
    if "<!-- page -->" in md:
        pages = [p.strip() for p in md.split("<!-- page -->") if p.strip()]
        if len(pages) > 1:
            return pages
    # Fall back: split on `<!-- image -->` + heading patterns
    # Many Qwen-VL outputs interleave: <image> then ## heading for that page
    parts = re.split(r"(?=\n## |\n<!-- image -->\n## )", md)
    pages = [p.strip() for p in parts if p.strip()]
    if len(pages) > 1:
        return pages
    # Single-page doc
    return [md]


def merge_json_objects(per_page: list[list[dict]]) -> list[dict]:
    """Merge per-page JSON arrays into one. We keep the flat-dict structure
    by collecting all per-page dicts and renumbering the suffix.

    Each per-page result is a single dict (one big object). We merge all keys
    into one dict, renumbering suffixes so they don't collide.
    """
    merged: dict[str, str] = {}
    counters = {"Company Name": 0, "Address": 0, "Shipping Information": 0, "Goods Description": 0}
    for page_objs in per_page:
        for obj in page_objs:
            for key, value in obj.items():
                if not value:
                    continue
                # Strip existing numeric suffix to get base key
                m = re.match(r"^(.*?)(\d+)$", key)
                if m:
                    base = m.group(1).strip()
                else:
                    base = key
                if base not in counters:
                    continue
                counters[base] += 1
                new_key = f"{base}{counters[base]}"
                merged[new_key] = str(value)
    return [merged]


def run_perpage_iteration(name: str, model: str, system_prompt_template: str, user_message: str):
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_dir = RUNS_DIR / name
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(DOCS_FILE) as f:
        docs = json.load(f)
    golden = load_golden()
    print(f"[{name}] PER-PAGE  model={model}  docs={len(docs)}")

    (run_dir / "config.json").write_text(json.dumps({
        "name": name, "model": model, "mode": "per-page",
        "system_prompt": system_prompt_template,
        "user_message": user_message, "ts": __import__("datetime").datetime.now().isoformat(),
    }, indent=2), encoding="utf-8")

    results = []
    for d in docs:
        md = d["md"]
        pages = split_pages(md)
        print(f"  - {d['filename']:55s} pages={len(pages)}  md={d['md_chars']:>6}c  ...", end=" ", flush=True)
        per_page_objs: list[list[dict]] = []
        all_meta = []
        for pi, page_md in enumerate(pages):
            if not page_md.strip():
                continue
            try:
                text, meta = call_ollama(model, system_prompt_template.format(context=page_md), user_message)
                all_meta.append(meta)
                json_str = extract_json(text)
                if json_str:
                    objs = parse_json_array(json_str)
                    per_page_objs.append(objs)
                    slug = re.sub(r"[^\w.-]+", "_", d["filename"])[:60]
                    (run_dir / f"{d['doc_id'][:8]}__p{pi+1}__{slug}.raw").write_text(text, encoding="utf-8")
            except Exception as e:
                print(f"\n    page {pi+1} error: {e}")
        merged = merge_json_objects(per_page_objs)
        slug = re.sub(r"[^\w.-]+", "_", d["filename"])[:80]
        (run_dir / f"{d['doc_id'][:8]}__{slug}.json").write_text(
            json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        score = None
        for sheet, fn_pattern in GOLDEN_SHEETS.items():
            if fn_pattern in d["filename"]:
                score = score_doc(merged, golden[sheet])
                break
        total_time = sum(m.get("elapsed_sec", 0) for m in all_meta)
        print(f"pages={len(pages)}  merged_keys={len(merged)}  {total_time:.1f}s  hit_rate={score['hit_rate']*100:.0f}%" if score else f"pages={len(pages)}  no-golden  {total_time:.1f}s")
        results.append({"doc": d, "score": score, "pages": len(pages), "merged_keys": len(merged), "all_meta": all_meta})

    scored = [r for r in results if r.get("score")]
    if scored:
        avg = sum(r["score"]["hit_rate"] for r in scored) / len(scored)
        print(f"\n[{name}] AGGREGATE: {len(scored)} golden-mapped docs, avg hit_rate = {avg*100:.1f}%")
    (run_dir / "scores.json").write_text(json.dumps({
        "name": name, "model": model, "mode": "per-page",
        "aggregate_avg_hit_rate": avg if scored else None,
        "per_doc": [
            {"doc_id": r["doc"]["doc_id"], "filename": r["doc"]["filename"],
             "pages": r["pages"], "merged_keys": r["merged_keys"],
             "score": r["score"], "total_time_sec": sum(m.get("elapsed_sec", 0) for m in r.get("all_meta", []))}
            for r in results
        ],
    }, indent=2, default=str), encoding="utf-8")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--user-message", default=USER_MESSAGE)
    args = parser.parse_args()
    if args.prompt:
        template = Path(args.prompt).read_text(encoding="utf-8")
    else:
        template = BASELINE_PROMPT
    run_perpage_iteration(args.name, args.model, template, args.user_message)
