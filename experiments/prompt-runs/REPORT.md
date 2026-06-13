# Ask-pipeline iteration report

Comparing **8** prompt/model variants on the 13 NR sample documents (4 sheets in the golden xlsx).

All runs use temperature=0, num_ctx=96k, num_predict=96k (matches production chat.py).

Scoring: substring match of golden xlsx's `Field` column against the values produced by the model. Prefix and word-level fallback matchers also used.


## Per-doc hit rate (vs golden xlsx)

| Doc | baseline | v1 | v2 | v3 | v4 | v5 | v1_qwen | perpage_v1 |
|---|---|---|---|---|---|---|---|---|
| NR Doc2-invoice.pdf | 88% | 88% | 50% | 75% | 88% | 75% | 88% | 88% |
| NR Doc6-BL.pdf (5315c) | 92% | 92% | 46% | — | 92% | 92% | 85% | 85% |
| NR Doc6-BL.pdf (3825c) | 38% | 46% | 38% | — | 54% | 46% | 31% | 54% |
| NR Doc9-AWB.pdf | 64% | 64% | 18% | — | 45% | 64% | 55% | 55% |
| NR Doc13-Insurancepolicy.pdf | 77% | 77% | 15% | 77% | 77% | 77% | 77% | 77% |
| **AGGREGATE** | **71.8%** | **73.3%** | **33.6%** | **76.0%** | **71.2%** | **70.8%** | **66.9%** | **71.5%** |

## Model + prompt summary

| Run | Model | Prompt |
|---|---|---|
| baseline | gemma4:e4b-it-qat | current production _SYSTEM_PROMPT (chat.py) |
| v1 | gemma4:e4b-it-qat | v1: flat-dict, goods cleaned (no quantities/codes/certs), shipping 'From/To/Via/Date' |
| v2 | gemma4:e4b-it-qat | v2: array-of-objects structure (regressed) |
| v3 | gemma4:e4b-it-qat | v3: v1 + verbose content rules (model produced YAML) |
| v4 | gemma4:e4b-it-qat | v4: v1 + compressed rules (no change) |
| v5 | gemma4:e4b-it-qat | v5: v1 + minor clarifications |
| v1_qwen | qwen2.5:7b-instruct | v1 prompt |
| perpage_v1 | gemma4:e4b-it-qat | v1 prompt, per-page split + merge |