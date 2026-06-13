"""Debug why matcher returns 0."""
import json
import re
from pathlib import Path

GOLDEN = Path(r"C:\Users\silwa\Projects\docling-Studio\extracted-json\model answer.xlsx")
MERGED_FILE = Path(r"C:\Users\silwa\AppData\Local\Temp\merged__doc13.txt")

import openpyxl
wb = openpyxl.load_workbook(GOLDEN, data_only=True)
ws = wb["13"]
golden = {}
for row in ws.iter_rows(min_row=2, values_only=True):
    sec = (row[0] or "").strip() if row[0] else ""
    field = (row[1] or "").strip() if row[1] else ""
    value = (row[2] or "").strip() if row[2] else ""
    if not sec:
        continue
    primary = field if field else value
    if not primary:
        continue
    normalized = re.sub(r"\s+", " ", primary).strip(" .,;:")
    golden.setdefault(sec, []).append((field, value, normalized))

merged = json.loads(MERGED_FILE.read_text(encoding="utf-8"))
SECTION_PREFIXES = ["Company Name", "Address", "Shipping Information", "Goods Description"]

def get_section(key):
    for p in SECTION_PREFIXES:
        if key.startswith(p):
            return p
    return None

ours = {p: [] for p in SECTION_PREFIXES}
for k, v in merged.items():
    sec = get_section(k)
    if sec and isinstance(v, str):
        ours[sec].append(v.strip())

# Manual debug: for each golden entry, print match status
for sec, items in golden.items():
    print(f"\n=== {sec} ===")
    for f, gv, _norm in items:
        # Try to match
        best_match = None
        for ours_v in ours.get(sec, []):
            nv = " ".join(ours_v.lower().split())
            ng = " ".join(gv.lower().split())
            in_substring = nv in ng or ng in nv
            nv_words = set(nv.split())
            ng_words = set(ng.split())
            common = nv_words & ng_words
            overlap = len(common) / min(len(nv_words), len(ng_words)) if nv_words and ng_words else 0
            if in_substring or overlap >= 0.7:
                best_match = ours_v
                break
        if best_match:
            print(f"  + {f!r:50s} -> {best_match!r}")
        else:
            # Show why
            print(f"  - {f!r:50s} value={gv!r}")
            for ours_v in ours.get(sec, []):
                nv = " ".join(ours_v.lower().split())
                ng = " ".join(gv.lower().split())
                nv_words = set(nv.split())
                ng_words = set(ng.split())
                common = nv_words & ng_words
                overlap = len(common) / min(len(nv_words), len(ng_words)) if nv_words and ng_words else 0
                print(f"        ours: {ours_v!r:60s}  overlap={overlap:.0f}%")
