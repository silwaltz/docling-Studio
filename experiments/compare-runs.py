"""Build a comparison report across all runs."""
import json
from pathlib import Path

RUNS_DIR = Path(__file__).parent / "prompt-runs"
runs = {}
for d in sorted(RUNS_DIR.iterdir()):
    if not d.is_dir():
        continue
    scores_file = d / "scores.json"
    if not scores_file.exists():
        continue
    runs[d.name] = json.loads(scores_file.read_text(encoding="utf-8"))

with open(Path(__file__).parent / "docs_full.json") as f:
    docs = json.load(f)
sizes = {d["doc_id"]: d["md_chars"] for d in docs}

# Build (run, doc) -> hit_rate table
table = {}
for rn, data in runs.items():
    for p in data.get("per_doc", []):
        if p.get("score") is None:
            continue
        doc_id = p["doc_id"]
        sz = sizes.get(doc_id, 0)
        if p["filename"] == "NR Doc6-BL.pdf":
            key = f"NR Doc6-BL.pdf ({sz}c)"
        else:
            key = p["filename"]
        table[(rn, key)] = p["score"]["hit_rate"]

# Determine doc columns
doc_keys = []
seen = set()
for (rn, dk) in table.keys():
    if dk not in seen:
        seen.add(dk)
        doc_keys.append(dk)

# Sort doc_keys: by sheet order (2, 6, 9, 13) for the golden-mapped ones
sheet_order = {
    "NR Doc2-invoice.pdf": 0,
    "NR Doc6-BL.pdf (5315c)": 1,
    "NR Doc6-BL.pdf (3825c)": 2,
    "NR Doc9-AWB.pdf": 3,
    "NR Doc13-Insurancepolicy.pdf": 4,
}
def sort_key(dk):
    return sheet_order.get(dk, 99)
doc_keys.sort(key=sort_key)

# Run columns in consistent order
run_order = ["baseline", "v1", "v2", "v3", "v4", "v5", "v1_qwen", "perpage_v1"]
run_names = [rn for rn in run_order if rn in runs] + [rn for rn in runs if rn not in run_order]

# Print to stdout
header = f"{'Doc':<35s}" + "".join(f"{n:>14s}" for n in run_names)
print(header)
for dk in doc_keys:
    line = f"{dk:<35s}"
    for rn in run_names:
        v = table.get((rn, dk))
        line += f"{v*100:>13.0f}%" if v is not None else f"{'--':>14s}"
    print(line)
agg_line = f"{'AGGREGATE':<35s}"
for rn in run_names:
    avg = runs[rn].get("aggregate_avg_hit_rate")
    agg_line += f"{avg*100:>13.1f}%" if avg is not None else f"{'--':>14s}"
print(agg_line)

# Save markdown report
lines = [
    "# Ask-pipeline iteration report\n",
    f"Comparing **{len(run_names)}** prompt/model variants on the 13 NR sample documents (4 sheets in the golden xlsx).\n",
    "All runs use temperature=0, num_ctx=96k, num_predict=96k (matches production chat.py).\n",
    "Scoring: substring match of golden xlsx's `Field` column against the values produced by the model. Prefix and word-level fallback matchers also used.\n",
    "\n## Per-doc hit rate (vs golden xlsx)\n",
    "| Doc | " + " | ".join(run_names) + " |",
    "|" + "---|" * (len(run_names) + 1),
]
for dk in doc_keys:
    row = f"| {dk} | " + " | ".join(
        f"{table.get((rn, dk))*100:.0f}%" if table.get((rn, dk)) is not None else "—"
        for rn in run_names
    ) + " |"
    lines.append(row)
lines.append("| **AGGREGATE** | " + " | ".join(
    f"**{runs[rn]['aggregate_avg_hit_rate']*100:.1f}%**" if runs[rn].get('aggregate_avg_hit_rate') is not None else "—"
    for rn in run_names
) + " |")

# Add the model column info
lines.append("\n## Model + prompt summary\n")
lines.append("| Run | Model | Prompt |")
lines.append("|" + "---|" * 3)
prompt_info = {
    "baseline": ("gemma4:e4b-it-qat", "current production _SYSTEM_PROMPT (chat.py)"),
    "v1": ("gemma4:e4b-it-qat", "v1: flat-dict, goods cleaned (no quantities/codes/certs), shipping 'From/To/Via/Date'"),
    "v2": ("gemma4:e4b-it-qat", "v2: array-of-objects structure (regressed)"),
    "v3": ("gemma4:e4b-it-qat", "v3: v1 + verbose content rules (model produced YAML)"),
    "v4": ("gemma4:e4b-it-qat", "v4: v1 + compressed rules (no change)"),
    "v5": ("gemma4:e4b-it-qat", "v5: v1 + minor clarifications"),
    "v1_qwen": ("qwen2.5:7b-instruct", "v1 prompt"),
    "perpage_v1": ("gemma4:e4b-it-qat", "v1 prompt, per-page split + merge"),
}
for rn in run_names:
    model, prompt = prompt_info.get(rn, ("?", "?"))
    lines.append(f"| {rn} | {model} | {prompt} |")

with open(RUNS_DIR / "REPORT.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"\nWrote {RUNS_DIR / 'REPORT.md'}")
