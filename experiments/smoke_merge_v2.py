"""Smoke test the new dedup strategy."""
import sys
sys.path.insert(0, "/app")
import json
import types

# Stub pytest
def _noop(*a, **k):
    if len(a) == 1 and callable(a[0]) and not k: return a[0]
    def w(f): return f
    return w
pytest_stub = types.ModuleType("pytest")
pytest_stub.mark = types.SimpleNamespace(asyncio=_noop)
sys.modules["pytest"] = pytest_stub

from domain.services import merge_extractions, _dedup_exact_only

# Test 1: Substring variants preserved
r = merge_extractions(
    '{"Company Name1": "FLUID LIMITED"}',
    '{"Company Name1": "FLUID LIMITED CO"}',
)
print("Test 1 (substring preserved):", json.loads(r))
assert json.loads(r) == {"Company Name1": "FLUID LIMITED", "Company Name2": "FLUID LIMITED CO"}

# Test 2: Exact dup removed
r2 = merge_extractions('{"Company Name1": "A"}', '{"Company Name1": "a"}')
print("Test 2 (case-insensitive exact removed):", json.loads(r2))
assert json.loads(r2) == {"Company Name1": "A"}

# Test 3: Whitespace variants
r3 = merge_extractions('{"Company Name1": "FLUID  LIMITED"}', '{"Company Name1": "FLUID LIMITED"}')
print("Test 3 (whitespace exact removed):", json.loads(r3))
assert json.loads(r3) == {"Company Name1": "FLUID  LIMITED"}

# Test 4: Case + spelling variants BOTH preserved
r4 = merge_extractions(
    '{"Address1": "Wilhelminakade 953 A Rotterdam"}',
    '{"Address1": "Wilhelmijnakade 953 A Rotterdam"}',
)
print("Test 4 (spelling variants preserved):", json.loads(r4))
assert len(json.loads(r4)) == 2  # both kept

# Test 5: Three different sources
r5 = merge_extractions(
    '{"Goods Description1": "WIDGETS"}',
    '{"Goods Description1": "WIDGETS"}',  # exact dup
    '{"Goods Description1": "WIDGET"}',  # substring
)
print("Test 5 (mixed):", json.loads(r5))
parsed = json.loads(r5)
assert len(parsed) == 2  # 1 dup dropped, 1 substring kept

import json
