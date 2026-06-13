"""Trace match_one directly."""
import json
import re
import openpyxl
from pathlib import Path

GOLDEN = Path(r"C:\Users\silwa\Projects\docling-Studio\extracted-json\model answer.xlsx")
MERGED_FILE = Path(r"C:\Users\silwa\AppData\Local\Temp\merged__doc13.txt")

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

# Direct check: take first Company Name golden entry
items = golden["Company Name"]
print("First golden Company Name entry:", items[0])
print("Our Company Name entries:", ours["Company Name"])

def match_one(ours_v, golden_values):
    nv = " ".join(ours_v.lower().split())
    if not nv:
        return False
    nv_words = set(nv.split())
    print(f"  nv = {nv!r}")
    for f, gv, _norm in golden_values:
        ng = " ".join(gv.lower().split())
        print(f"    trying gv = {gv!r}, ng = {ng!r}")
        if not ng:
            continue
        if nv in ng or ng in nv:
            print(f"    SUBSTRING MATCH")
            return True
        ng_words = set(ng.split())
        if nv_words and ng_words:
            overlap = len(nv_words & ng_words) / min(len(nv_words), len(ng_words))
            print(f"    overlap = {overlap}")
            if overlap >= 0.7:
                return True
    return False

print()
print("Testing our 'TT Club Mutual Insurance' against golden 'TT Club Mutual Insurance':")
result = match_one("TT Club Mutual Insurance", [items[0]])
print(f"Result: {result}")
