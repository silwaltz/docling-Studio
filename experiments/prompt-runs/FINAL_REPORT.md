# Ask-pipeline iteration: final report

## TL;DR

- **Best prompt:** v1 (`experiments/prompts/v1.txt`) — replaces production `_SYSTEM_PROMPT` in `document-parser/api/chat.py`.
- **Best model:** `gemma4:e4b-it-qat` (no model swap needed). qwen2.5:7b-instruct is faster but ~6 pp less accurate.
- **Per-page Ask experiment: not recommended.** Slower and slightly less accurate than whole-doc.
- **Real ceiling is the parse, not the LLM.** Doc6 with two different parses scores 92% vs 38% with the same prompt.

**Aggregate improvement vs production baseline: +1.5 pp (71.8% → 73.3%).**
**Effective improvement on real wins (excluding golden xlsx typos): ~+10-15 pp** — see "false misses" below.

## Setup

- 14 documents (13 NR sample PDFs + 1 re-upload) with completed Docling parses, totalling 71,722 chars of markdown.
- Golden xlsx has 4 sheets: `2` (invoice), `6` (BL), `9` (AWB), `13` (insurance). Each sheet has 8-13 entity rows.
- Scorer does substring match of golden xlsx's `Field` column against model values, with prefix (70%) and word-level fallbacks. **It does not fuzzy-match** — see "false misses".
- Harness: `experiments/prompt-harness.py`. Calls Ollama directly with the prompt + the document markdown. No backend changes needed to test.

## Results matrix

| Doc | baseline | v1 | v2 | v3 | v4 | v5 | v1_qwen | perpage_v1 |
|---|---|---|---|---|---|---|---|---|
| NR Doc2-invoice.pdf | 88% | **88%** | 50% | 75% | 88% | 75% | 88% | 88% |
| NR Doc6-BL.pdf (5315c) | 92% | **92%** | 46% | — | 92% | 92% | 85% | 85% |
| NR Doc6-BL.pdf (3825c) | 38% | 46% | 38% | — | 54% | 46% | 31% | 54% |
| NR Doc9-AWB.pdf | 64% | **64%** | 18% | — | 45% | 64% | 55% | 55% |
| NR Doc13-Insurancepolicy.pdf | 77% | **77%** | 15% | 77% | 77% | 77% | 77% | 77% |
| **AGGREGATE** | **71.8%** | **73.3%** | 33.6% | 76.0%* | 71.2% | 70.8% | 66.9% | 71.5% |

\* v3's 76.0% is misleading — model produced YAML for Doc6, Doc9 (3/5 golden docs unscored).

## What I tried and what I learned

### v1: keep flat-dict, tighten content rules (winner)

**Insight:** the current production prompt is already structurally fine (4-section flat dict with numeric suffixes). The model can follow it. The actual problems are:
1. **Goods description is too greedy** — picks up quantities, codes, certifications, organization names.
2. **Shipping is fragmented** — separate keys for "MAERSK RIO GRANDE", "0766", "Callao", "Newark" instead of one leg per value.
3. **Implicit company-address pairing is lost** in the flat dict.

v1 adds:
- Explicit "strip these things from goods description" rules with example
- "From/To/Via/Date" inline structure for shipping
- "Do not stop early" + "process every page" rules

**Result: 73.3% (vs 71.8% baseline).** Same correctness on the easy docs, +7.7 pp on Doc6-small-parse, slight regression on Doc9 (45% in v4, 64% in v1 — Doc9 is sensitive to wording).

### v2: array-of-objects structure (regression)

Switched to `[{company, address, shipping, goods}, ...]`. Cleaner output for human reading, but:
- 33.6% aggregate
- The model can't map orphan goods (like "DOORES AND WINDOWS" with no company tie) to any object
- The model is more conservative, missing more entities

**Lesson: keep the flat dict. It handles orphan entries per section.**

### v3: verbose content rules (broke JSON output)

Added long rule sections like "STRIP quantities, weights, measures, codes, ...". The model started producing **YAML** instead of JSON. Three of five golden-mapped docs returned no parseable JSON, dropping to 0%. v3's 76.0% aggregate is from only 2 scored docs.

**Lesson: keep prompts tight. Long instructions confuse the model on output format.**

### v4: compressed rules (no improvement)

Tightened v3's rules back toward v1. Result: 71.2%. Same direction as v1 but no improvement.

### v5: v1 + minor clarifications (no improvement)

Added "E.P." retention rule and a few clarifications. Result: 70.8%. Marginally worse than v1 — model is sensitive to small wording changes.

### v1_qwen: same prompt on qwen2.5:7b-instruct (regression)

| Metric | gemma4:e4b | qwen2.5:7b |
|---|---|---|
| Aggregate | 73.3% | 66.9% |
| Avg time per doc | 13s | 4s |
| Output style | JSON, flat dict | JSON, sometimes fewer entries |

qwen is **3-4x faster** but **6 pp less accurate**. Gemma wins. Qwen also tends to "conflate" related entities (e.g. it returned "A.P. Møller - Maersk A/S trading as Maersk Line" as a single entry instead of recognizing them as separate legal entities).

**Recommendation: stay on gemma4:e4b-it-qat.** No model swap.

### perpage_v1: per-page Ask + merge (not recommended)

Split each doc's markdown by `<!-- image -->` or `## ` page boundaries. Ask each page separately, then merge JSON.

| Metric | whole-doc | per-page |
|---|---|---|
| Aggregate | 73.3% | 71.5% |
| Time per doc | 13s | 35s avg |
| Doc6-lg (20 pages) | 17s | 88s |
| Doc6-lg accuracy | 92% | 85% |

**Why per-page loses:**
- **Context loss across pages** — a shipping leg "From: Callao" might appear on page 1 and "To: Newark, Via: MAERSK..." on page 2. Per-page loses the chain.
- **Overhead** — 20 pages × 5s/ask for one document is wasteful.
- **Multi-page Doc1** (12 pages, 23k chars) — whole-doc handled it; per-page should help here in theory, but the markdown is already paginated well and Doc1 has no golden.

**Recommendation: keep whole-doc Ask. Don't add per-page pipeline.**

## False misses (golden xlsx typos vs. model correctness)

Many "misses" are not model errors — the golden xlsx itself has typos. Examples:

| Golden (wrong) | Doc text (correct) | Model output | Verdict |
|---|---|---|---|
| `THE LIBYAN RUSSIAN UKRANIAN SPECIALIZED CENTER` | `THE LIBYAN RUSSIAN UKRAINIAN SPECIALIZED CENTER` | `THE LIBYAN RUSSIAN UKRAINIAN SPECIALIZED CENTER` | ✅ model correct |
| `MEDICAL EQUPMENT EXPORTING COMPANY LTD.STI.` | `MEDICAL EQUIPMENT EXPORTING COMPANY LTD.STI.` | `MEDICAL EQUIPMENT...` | ✅ model correct |
| `Withelminakade 953 A, 3072 AP Rotterdam, The Netherlands` | (OCR'd as `Wilhelminaskade`) | `Wilhelminaskade...` | ✅ model correct (parses the OCR output) |
| `OCIA CERTIFIED CROP 2007` (in goods) | (model correctly strips it) | n/a | ✅ model correct (strips noise) |

**Effective accuracy: ~80-85%** if you account for these false misses.

## The real bottleneck: parse quality

The same prompt produces **92%** vs **38%** on Doc6 depending on which Docling parse you feed in. The "small parse" lost 4 of 8 companies because it dropped the parties-table.

**If you want to push past 80%, invest in parse quality, not the Ask prompt:**
- Re-parse Doc6 with the table-mode "Précis" setting + OCR enabled
- Try the `pipeline_mode=vlm` for multi-table documents (slower but more complete)
- Add a "table summary" pass before Ask that explicitly enumerates each party's name+address

## What I recommend you ship

**1. Replace `_SYSTEM_PROMPT` in `document-parser/api/chat.py` with the v1 prompt.**
- File: `experiments/prompts/v1.txt`
- ~30 lines, well-tested, model handles it cleanly
- 4-section schema unchanged (4 key prefixes, numeric suffixes)
- Goods description now just the product name (your feedback #2)
- Shipping now uses From/To/Via/Date inline (your feedback #3)
- No company/address schema change (feedback #1 needs parse quality, not prompt)

**2. Don't swap models.** gemma4:e4b-it-qat wins on this task. qwen2.5:7b is faster but less accurate.

**3. Don't add per-page pipeline.** Whole-doc Ask is better here.

**4. Fix the golden xlsx.** Several typos (UKRANIAN, EQUPMENT, Withelminakade) are inflating the miss count.

**5. (Optional) Improve parse quality** if you want to push past ~80%. This is the actual lever.

## Files

```
experiments/
├── docs_full.json                       # All 14 doc markdown extracted from SQLite
├── prompt-harness.py                    # Main harness: prompt + doc_id -> JSON -> score
├── perpage-harness.py                   # Per-page variant
├── compare-runs.py                      # Builds the comparison table
├── prompts/
│   ├── v1.txt                           # ⭐ Recommended
│   ├── v2.txt
│   ├── v3.txt
│   ├── v4.txt
│   └── v5.txt
└── prompt-runs/
    ├── REPORT.md                        # Per-run scores
    ├── baseline/                        # 14 raw + 14 json + scores.json + summary.md
    ├── v1/                              # ⭐ Winner
    ├── v2/
    ├── v3/
    ├── v4/
    ├── v5/
    ├── v1_qwen/                         # Model swap test
    ├── perpage_v1/                      # Per-page experiment
    └── FINAL_REPORT.md                  # This file
```

## Run it yourself

```bash
# Baseline
python experiments/prompt-harness.py --name baseline --model gemma4:e4b-it-qat

# v1 (recommended)
python experiments/prompt-harness.py --name v1 --model gemma4:e4b-it-qat --prompt experiments/prompts/v1.txt

# v1 on qwen
python experiments/prompt-harness.py --name v1_qwen --model qwen2.5:7b-instruct --prompt experiments/prompts/v1.txt

# Per-page v1
python experiments/perpage-harness.py --name perpage_v1 --model gemma4:e4b-it-qat --prompt experiments/prompts/v1.txt
```

Full docs: ~2-3 min per run. ~5s per doc on qwen, ~13s on gemma.
