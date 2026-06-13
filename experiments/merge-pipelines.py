"""Merge two 4-section flat-dict JSON outputs into one.

Inputs: two list-of-dict structures (output of standard+Ask vs VLM-json).
Output: a single list-of-dict with the union of all entities, deduped
case-insensitively, with the longer/more-detailed value winning ties.

Strategy:
- Both inputs are expected to be `[{"Company Name1": ..., "Address1": ..., ...}]`
- Iterate over all keys from both, collect all values
- Group by section (Company Name / Address / Shipping Information / Goods Description)
- Within each section, dedupe by normalized value
- Renumber suffix to be sequential within each section
- Return as a single dict
"""
import re
import json
from pathlib import Path
from typing import Iterable

SECTION_PREFIXES = ("Company Name", "Address", "Shipping Information", "Goods Description")


def get_section(key: str) -> str | None:
    """Return the section prefix for a key, or None if not a 4-section key."""
    for p in SECTION_PREFIXES:
        if key.startswith(p):
            return p
    return None


def normalize_value(v: str) -> str:
    """Lowercase + collapse whitespace + strip punctuation for dedup."""
    return re.sub(r"[\s.,;:]+", " ", (v or "").strip().lower())


def is_substring_of(a_norm: str, b_norm: str) -> bool:
    """True if a is a substring of b (or equal)."""
    return a_norm == b_norm or (a_norm and a_norm in b_norm)


def is_substring_dedup_keep(values: list[str]) -> list[str]:
    """Given a list of raw values, dedupe by:
    - If two values are substring-equivalent, keep the longer one
    - Otherwise, keep all
    Return ordered list (preserve first-seen order).
    """
    kept: list[tuple[str, str]] = []  # (raw, normalized)
    for v in values:
        if not v or not v.strip():
            continue
        nv = normalize_value(v)
        replace_idx = -1
        skip = False
        for i, (_, kept_n) in enumerate(kept):
            if is_substring_dedup(nv, kept_n):
                skip = True
                break
            elif is_substring_dedup(kept_n, nv):
                replace_idx = i
                break
        if skip:
            continue
        if replace_idx >= 0:
            kept[replace_idx] = (v.strip(), nv)
        else:
            kept.append((v.strip(), nv))
    return [raw for raw, _ in kept]


def is_substring_dedup(a: str, b: str) -> bool:
    """True if a is a substring of b."""
    return bool(a) and bool(b) and a in b


def merge_outputs(standard_objs: list[dict], vlm_objs: list[dict]) -> list[dict]:
    """Merge two pipeline outputs. Each input is a list of one dict (4-section flat).
    Returns a single dict with sections merged.
    """
    # Flatten to per-section lists
    by_section: dict[str, list[str]] = {p: [] for p in SECTION_PREFIXES}
    for obj_list in (standard_objs, vlm_objs):
        for obj in obj_list:
            for k, v in obj.items():
                sec = get_section(k)
                if sec is None or v is None:
                    continue
                vs = str(v).strip()
                if vs:
                    by_section[sec].append(vs)
    # Dedup each section
    merged: dict[str, str] = {}
    for sec, vals in by_section.items():
        deduped = is_substring_dedup_keep(vals)
        for i, v in enumerate(deduped, start=1):
            merged[f"{sec}{i}"] = v
    return [merged]


if __name__ == "__main__":
    # Smoke test: merge the Doc2 outputs
    OUT = Path(__file__).parent.parent / "extracted-json"
    std = json.loads((OUT / "ask_v1__12757426__NR_Doc2-invoice.pdf.json").read_text(encoding="utf-8"))
    vlm = json.loads((OUT / "vlm_json__0e8422ea__NR_Doc2-invoice.pdf.json").read_text(encoding="utf-8"))
    print("=== Standard Doc2 ===")
    print(json.dumps(std, indent=2)[:600])
    print()
    print("=== VLM-json Doc2 ===")
    print(json.dumps(vlm, indent=2)[:600])
    print()
    print("=== MERGED Doc2 ===")
    merged = merge_outputs(std, vlm)
    print(json.dumps(merged, indent=2))
    print(f"\nTotal keys: {len(merged[0])}")
    for sec in SECTION_PREFIXES:
        n = sum(1 for k in merged[0] if k.startswith(sec))
        print(f"  {sec}: {n} keys")
