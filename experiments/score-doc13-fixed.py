"""Score Doc13 deep extract against golden — corrected version."""
import json
import re
import sys
import openpyxl
from pathlib import Path

GOLDEN = Path(r"C:\Users\silwa\Projects\docling-Studio\extracted-json\model answer.xlsx")
MERGED_FILE = Path(r"C:\Users\silwa\AppData\Local\Temp\merged__doc13_v2.txt")

# Load golden
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

print("Golden sections:", list(golden.keys()))
for s, v in golden.items():
    print(f"  {s}: {len(v)} entries")
print()

# Load our deep extract result
merged = json.loads(MERGED_FILE.read_text(encoding="utf-8-sig"))
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

# Match using substring OR 70% word-overlap
def match_one(ours_v, golden_values):
    nv = " ".join(ours_v.lower().split())
    if not nv:
        return False
    nv_words = set(nv.split())
    for f, gv, _norm in golden_values:
        # Use the normalized primary key (which prefers `field`, falls
        # back to `value`). Some golden rows have an empty `value` cell
        # — the field column is the real search key.
        ng = " ".join(_norm.lower().split())
        if not ng:
            continue
        if nv in ng or ng in nv:
            return True
        ng_words = set(ng.split())
        if nv_words and ng_words:
            overlap = len(nv_words & ng_words) / min(len(nv_words), len(ng_words))
            if overlap >= 0.7:
                return True
    return False

total = 0
matched = 0
misses = []
for sec, items in golden.items():
    for f, gv, _norm in items:
        total += 1
        hit = False
        for ours_v in ours.get(sec, []):
            if match_one(ours_v, [(f, gv, _norm)]):
                hit = True
                matched += 1
                break
        if not hit:
            misses.append((sec, f, gv, _norm))

print(f"\nDoc13 deep extract (v1 prompt + sanitizer): {matched}/{total} = {100*matched/total:.1f}%")
print(f"  Output keys: {len(merged)}, Golden entries: {total}")
print()
print("Misses:")
for sec, f, gv, n in misses:
    print(f"  {sec}: {n!r}")
