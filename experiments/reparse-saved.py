"""Re-parse saved raw responses with the improved brace-less fallback.

Reads ask_v1__*.raw.txt files, applies the new extract_json, writes
the .json files and updates RUN_SUMMARY.json.
"""
import json
import re
from pathlib import Path
from datetime import datetime

OUT_DIR = Path(__file__).parent.parent / "extracted-json"


def extract_json(text: str) -> str | None:
    # 0) Normalize gemma4 quirks
    t = text
    # Replace `=` as key/value separator (some gemma4 outputs use "key"="value")
    # Only do this if the standard ':' form is absent, to avoid corrupting valid JSON
    if '":=' in t and '":' not in t:
        t = t.replace('":=', '":"')  # close value quote, open next
        # We need a smarter fix: walk and replace '=' between quotes
    # Strip angle brackets from key suffixes: "Company Name<1>" -> "Company Name1"
    t = re.sub(r'"(Company Name|Address|Shipping Information|Goods Description)<(\d+)>"', r'"\1\2"', t)

    # 1) Try fenced
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)```", t)
    if fenced:
        c = fenced.group(1).strip()
        try:
            json.loads(c)
            return c
        except Exception:
            pass
    # 2) Try brace/bracket matching
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
    # 3) Brace-less fallback: text starts with "key": pattern (with or without spaces)
    stripped = t.strip()
    colon_count = len(re.findall(r'"[^"]+"\s*:\s*"', stripped))
    if stripped.startswith('"') and colon_count >= 2:
        wrapped = "{" + stripped.rstrip().rstrip(",") + "}"
        try:
            json.loads(wrapped)
            return wrapped
        except Exception:
            last_full = max(wrapped.rfind('",'), wrapped.rfind('":null'))
            if last_full > 0:
                cut = wrapped[: last_full + 1] + "}"
                try:
                    json.loads(cut)
                    return cut
                except Exception:
                    pass
    # 4) "=" separator fallback (gemma4 another quirk)
    # Forms seen: "key"="value"   or   "key":="value"  (no quotes around value if simple)
    if stripped.startswith('"'):
        # Check if there are >= 2 `"="` patterns
        eq_count = len(re.findall(r'"[A-Za-z][^"]*"\s*=\s*"', stripped))
        if eq_count >= 2:
            # Replace `"key"="value",` with `"key":"value",`
            normalized = re.sub(r'"([A-Za-z][^"]*?)"\s*=\s*"', r'"\1":"', stripped)
            wrapped = "{" + normalized.rstrip().rstrip(",") + "}"
            try:
                json.loads(wrapped)
                return wrapped
            except Exception:
                # Trim trailing partial entry
                last_full = max(wrapped.rfind('",'), wrapped.rfind('":null'))
                if last_full > 0:
                    cut = wrapped[: last_full + 1] + "}"
                    try:
                        json.loads(cut)
                        return cut
                    except Exception:
                        pass
    return None


def main():
    raw_files = sorted(list(OUT_DIR.glob("ask_v1__*.raw.txt")) + list(OUT_DIR.glob("vlm_ask__*.raw.txt")))
    print(f"Re-parsing {len(raw_files)} raw responses with brace-less fallback\n")
    results = []
    for raw in raw_files:
        text = raw.read_text(encoding="utf-8")
        json_str = extract_json(text)
        # Derive json filename from raw filename
        json_path = raw.with_suffix("").with_suffix(".json")  # .raw.txt -> .raw -> .json
        # actually we want ask_v1__*.raw.txt -> ask_v1__*.json
        json_name = raw.name.replace(".raw.txt", ".json")
        json_path = OUT_DIR / json_name
        # Remove old error/duplicate JSONs
        for old in (OUT_DIR.glob(json_name.replace(".json", ".*.json"))):
            if old != json_path and old.name.startswith(json_name.split(".json")[0]):
                old.unlink()
        if json_str:
            cleaned = json_str.replace("\\_", " ")
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    arr = [parsed]
                elif isinstance(parsed, list):
                    arr = parsed
                else:
                    arr = []
                json_path.write_text(json.dumps(arr, indent=2, ensure_ascii=False), encoding="utf-8")
                key_count = sum(len(o) for o in arr)
                status = "OK"
            except Exception as e:
                json_path.write_text(f'{{"error": "{e}"}}', encoding="utf-8")
                key_count = 0
                status = f"PARSE_ERR: {e}"
        else:
            json_path.write_text("ERROR: no parseable JSON in response", encoding="utf-8")
            key_count = 0
            status = "NOPARSE"
        # Parse doc_id from filename: ask_v1__<8hex>__<slug>
        m = re.match(r"ask_v1__([0-9a-f]+)__(.+)", raw.name)
        doc_id_short = m.group(1) if m else "?"
        slug = m.group(2) if m else raw.name
        print(f"  - {slug:55s}  {status:>12s}  keys={key_count}")
        results.append({"raw": raw.name, "json": json_path.name, "status": status, "key_count": key_count})

    # Update RUN_SUMMARY
    summary_path = OUT_DIR / "ask_v1__RUN_SUMMARY.json"
    if summary_path.exists():
        s = json.loads(summary_path.read_text(encoding="utf-8"))
        n_ok = sum(1 for r in results if r["status"] == "OK")
        s["reparse_ts"] = datetime.now().isoformat(timespec="seconds")
        s["n_parsed_after_reparse"] = n_ok
        # Update per-doc parsed_ok
        for r in results:
            for entry in s.get("results", []):
                if r["raw"].replace(".raw.txt", "") in entry.get("raw_path", ""):
                    entry["parsed_ok_after_reparse"] = (r["status"] == "OK")
                    entry["key_count_after_reparse"] = r["key_count"]
                    break
        summary_path.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReparsed: {sum(1 for r in results if r['status'] == 'OK')} / {len(results)}")
    print(f"Updated {summary_path}")


if __name__ == "__main__":
    main()
