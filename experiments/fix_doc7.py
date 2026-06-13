"""Targeted fix for Doc7: orphan-value joiner. Run only on Doc7."""
import json, re
from pathlib import Path

OUT_DIR = Path(__file__).parent.parent / "extracted-json"
target = OUT_DIR / "vlm_ask__4df0e88f__NR_Doc7-BL.pdf.raw.txt"
if not target.exists():
    print("Doc7 raw not found")
    raise SystemExit(1)

text = target.read_text(encoding="utf-8")
print("Before:")
print(text[:500])
print()

# Strategy: for each "Shipping Information<n>" or similar key that is followed
# by a list of comma-separated plain values (not "key":"value" pairs), join
# them. We walk the string char-by-char to find the "key", then collect
# "value" strings until we hit another "key":"value" pair.
#
# Simpler approach: find the raw text between "Shipping Information1"<separator>
# and "Goods Description1" — treat everything in between as the value list.
# Then re-emit as a single string.

# Use regex with non-greedy + lookahead
KEY = r"(?:Company Name|Address|Shipping Information|Goods Description)"

def fix_orphan_values(t: str) -> str:
    # Pattern: "Key<n>","v1","v2",... up to next "Key<n+1>"
    # For each match, replace with "Key<n>":"joined v1, v2, ..."
    def repl(m):
        key = m.group(1)
        raw_values = m.group(2)
        # raw_values is everything between the key's `,"` and the next key's `","`
        # Extract all "..." strings
        values = re.findall(r'"([^"]*)"', raw_values)
        return f'"{key}":"{", ".join(values)}"'
    # Match: "Key<n>" followed by anything up to "Key<n+something>"
    # Use a pattern: "Key<n>","(any-non-key-value-stuff)","Key<other>"
    # Step-by-step: find "Key<n>", then the rest of the string, then split on
    # the next "Key<n+>" (any 4-section key) and replace.
    # Iterate over all 4-section keys in order
    pattern = re.compile(rf'"({KEY}\d+)"(.*?)(?="{KEY}\d+")', re.DOTALL)
    out = pattern.sub(repl, t)
    return out

fixed = fix_orphan_values(text)
print("After:")
print(fixed[:500])
print()

# Try parse
try:
    obj = json.loads(fixed)
    print("Parses OK!")
    print(json.dumps(obj, indent=2)[:500])
except Exception as e:
    print(f"Parse failed: {e}")
