"""Save a long-term memory entry for Mavis about Deep Extract v3 + stuck-job recovery."""
import subprocess

content = """### Deep Extract v3 + stuck-job recovery (2026-06-13)
Type: feature

Stuck-job fix (root cause of Doc1 8.5h hang):
- In-process Docling runs via asyncio.to_thread which asyncio.wait_for cannot cancel — the thread keeps running while the awaitable is killed. Container restart clears the in-memory asyncio.Task dict but leaves the DB row at RUNNING forever. Fixed by:
  - domain/ports.py::AnalysisRepository.fail_stale_running(older_than_seconds)
  - persistence/analysis_repo.py SQL sweep on RUNNING rows older than 2*CONVERSION_TIMEOUT+5min
  - main.py lifespan hook calls sweep at startup, wrapped in try/except
  - api/schemas.py::AnalysisResponse.is_stale: bool — UI can flag stuck jobs in the race window
  - docker-compose.dev.yml BATCH_PAGE_SIZE=5 (was 10) so 12-page docs get per-batch timeouts
  - End-to-end verified: injected 3h-old RUNNING row, restarted container, log says "Recovered 1 stale RUNNING analysis job(s)", row flipped to FAILED

Deep Extract v3 13-doc test:
- experiments/run-full-deep-test.py ran extractMode=deep on all 13 NR docs sequentially.
- 13/13 COMPLETED, 0 stuck. Doc1 (12 pages) finished in 444s with 61 merged keys.
- Total wall time ~18min.
- v3 score on 4-doc golden: 87.8% (up from 79.2% in v1/v2). Doc2 jumped 75% to 100%, Doc9 72.7% to 81.8%, Doc6 and Doc13 tied at 92.3% / 76.9%.

Pre-existing test failures NOT in my scope:
- test_analysis_service.py::TestMergeResults::test_single_result_passthrough and TestBatchedConversion::test_batch_failure_raises_with_enriched_message were failing on the wip checkpoint commit before my work.
- They need a follow-up: test_single_result_passthrough expects document_json is None after merge but impl keeps it; test_batch_failure_raises_with_enriched_message expects "Batch N/M (pages X-Y) failed: ..." prefix but the wrapper does not add it.

Threshold gotcha:
- CONVERSION_TIMEOUT=3600 in this env (not the 900 default). Threshold = 2*3600+300 = 7500s = 2h05min. Use the right threshold when injecting fake stale jobs in tests.

Files:
- extracted-json/deep_extract__FULL_REPORT.md — v3 report (13-doc run)
- extracted-json/deep_extract__SHIPPED_REPORT.md — v1/v2 history
- experiments/run-full-deep-test.py — full-13 runner
- experiments/score-deep-extract.py — scorer for single-dict merged output
"""

result = subprocess.run(
    ["C:\\Users\\silwa\\.mavis\\bin\\mavis.cmd", "memory", "append", "mavis", "--content", content],
    capture_output=True, text=True, shell=True
)
print("stdout:", result.stdout)
print("stderr:", result.stderr)
print("returncode:", result.returncode)
