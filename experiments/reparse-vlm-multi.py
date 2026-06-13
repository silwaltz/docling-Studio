"""Reparse vlm_ask__ raw files with smarter multi-object handling.

Gemma4 sometimes emits multiple flat-dict JSONs on separate lines (no braces,
no commas) when the document has many entities. Each line is its own dict.
"""
import json
import re
from pathlib import Path
from datetime import datetime

OUT_DIR = Path(__file__).parent.parent / "extracted-json"


def extract_one_obj(text: str) -> tuple[list[str], int]:
    """Try to extract one brace-less or braced JSON object from text.
    Returns (list of candidate text-strings, position to start next search).
    Multiple candidates are returned if we found one braced JSON object — the
    rest of the text may have more objects after it.
    """
    candidates = []
    # Try braced
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
                        return [cand], i + 1
                    except Exception:
                        break
    # Try brace-less
    stripped = text.lstrip()
    colon_count = len(re.findall(r'"[^"]+"\s*:\s*"', stripped))
    eq_count = len(re.findall(r'"[A-Za-z][^"]*"\s*=\s*"', stripped))
    if colon_count >= 2 or eq_count >= 2:
        # Find the line span: start at first " or first '=', end at last " or '=,
        if stripped.startswith('"'):
            # One line that starts with "key":..., may have wrapping commas
            end = max(stripped.rfind('",'), stripped.rfind('":null'))
            if end > 0:
                cand = stripped[: end + 1]
                wrapped = "{" + (cand if not cand.startswith("{") else cand) + "}"
                # If cand already ends with } don't re-wrap
                if cand.rstrip().endswith("}"):
                    wrapped = cand
                try:
                    json.loads(wrapped)
                    return [wrapped], len(stripped)
                except Exception:
                    pass
    return candidates, 0


def split_brace_less_objects(text: str) -> list[str]:
    """Split text into individual flat-dict chunks when there are multiple.

    Strategy:
    - If text already has { } or [ ], return as-is (single chunk).
    - Otherwise, split on newlines that are followed by a quote starting a new
      "key": pattern AND the previous line ended with a string value.
    - A safe pattern: split on any \n that is between two complete
      "key": "value" pairs. Heuristic: split on `"\n"Company Name` /
      `"\n"Address` / `"\n"Shipping` / `"\n"Goods`.
    """
    stripped = text.strip()
    if not stripped:
        return [text]
    if stripped.startswith("{") or stripped.startswith("["):
        return [text]
    # Heuristic: if the model emitted "key": patterns, count them
    key_count = len(re.findall(r'"(?:Company Name|Address|Shipping Information|Goods Description)\d*"\s*:\s*"', text))
    if key_count < 8:
        return [text]  # small enough to be one object
    # Split on newlines followed by a 4-section key
    parts = re.split(r'\n(?="(?:Company Name|Address|Shipping Information|Goods Description)\d*"\s*:)', text)
    return [p.strip() for p in parts if p.strip()]


def parse_brace_less_object(text: str) -> dict | None:
    """Parse a chunk of text that's a flat-dict JSON without braces into a dict."""
    t = text.strip()
    if not t:
        return None
    # Strip trailing comma
    t = t.rstrip().rstrip(",")
    # Normalize angle brackets in keys
    t = re.sub(r'"(Company Name|Address|Shipping Information|Goods Description)<(\d+)>"', r'"\1\2"', t)
    # Normalize `","` (typo for `":"` from gemma4) to `":"` — but ONLY when
    # preceded by a 4-section key. Otherwise we'd break legitimate JSON
    # between objects.
    t = re.sub(
        r'((?:Company Name|Address|Shipping Information|Goods Description)\d*)",\s*"',
        r'\1":"',
        t,
    )
    # If already braced, return as-is
    if t.startswith("{") and t.endswith("}"):
        try:
            return json.loads(t)
        except Exception:
            pass
    # Try = to : conversion
    if "=" in t and ":" not in t:
        normalized = re.sub(r'"([A-Za-z][^"]*?)"\s*=\s*"', r'"\1":"', t)
        wrapped = "{" + normalized + "}"
        try:
            return json.loads(wrapped)
        except Exception:
            return None
    # Try with : (braces-less)
    colon_count = len(re.findall(r'"[^"]+"\s*:\s*"', t))
    if colon_count >= 1:
        wrapped = "{" + t + "}"
        try:
            return json.loads(wrapped)
        except Exception:
            return None
    return None


def main():
    raw_files = sorted(OUT_DIR.glob("vlm_ask__*.raw.txt"))
    print(f"Re-parsing {len(raw_files)} VLM raw files (multi-object aware)\n")
    fixed = 0
    for raw in raw_files:
        text = raw.read_text(encoding="utf-8")
        json_name = raw.name.replace(".raw.txt", ".json")
        json_path = OUT_DIR / json_name
        # Detect multi-object
        chunks = split_brace_less_objects(text)
        print(f"  {raw.name[:60]:60s}  chunks={len(chunks)}", end="")
        if len(chunks) > 1:
            # Parse each chunk, then merge into a single logical object
            # (gemma4 streams the response in groups when the doc is large;
            # logically they should all be one extraction)
            merged: dict = {}
            for c in chunks:
                obj = parse_brace_less_object(c)
                if obj:
                    # Renumber to avoid key collisions: e.g. "Company Name1" in
                    # both chunks would collide; shift second chunk's indices
                    for key, val in obj.items():
                        if key in merged:
                            # find next available index
                            m = re.match(r"^(.*?)(\d+)$", key)
                            if m:
                                base, _ = m.group(1), m.group(2)
                                n = 1
                                while f"{base}{n}" in merged:
                                    n += 1
                                key = f"{base}{n}"
                            else:
                                n = 1
                                while f"{key}{n}" in merged:
                                    n += 1
                                key = f"{key}{n}"
                        merged[key] = val
            if merged:
                json_path.write_text(json.dumps([merged], indent=2, ensure_ascii=False), encoding="utf-8")
                noparse = OUT_DIR / json_name.replace(".json", ".NOPARSE.json")
                if noparse.exists():
                    noparse.unlink()
                print(f"  -> merged into 1 object, {len(merged)} keys [FIXED]")
                fixed += 1
            else:
                print(f"  -> parse failed")
        else:
            print(f"  -> single chunk, skipped")
    print(f"\nFixed {fixed} files")


if __name__ == "__main__":
    main()
