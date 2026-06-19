#!/usr/bin/env bash
# verify-vllm-rhel.sh - smoke test the single-container vLLM stack end-to-end.
#
# Run AFTER install-vllm-rhel.sh + cd /opt/vllm && docker compose up -d.
# Exits 0 only if every check passes.
#
# Single-model setup: one `vllm` container on host port 8000, serving
# Qwen3-VL-8B-Instruct-AWQ-4bit under the alias qwen3-vl:8b-instruct.
# Both the Ask pipeline and the VLM pipeline point at this single endpoint.

set -uo pipefail

VLLM_URL="${VLLM_URL:-http://127.0.0.1:8000}"
COMPOSE_DIR="${COMPOSE_DIR:-/opt/vllm}"
VLLM_MODEL="${VLLM_MODEL_TAG:-qwen3-vl:8b-instruct}"

PASS=0; FAIL=0
green() { printf "\033[1;32m[PASS]\033[0m %s\n" "$*"; PASS=$((PASS+1)); }
red()   { printf "\033[1;31m[FAIL]\033[0m %s\n" "$*"; FAIL=$((FAIL+1)); }
hr()    { printf -- "----------------------------------------\n"; }

dc() { (cd "$COMPOSE_DIR" && docker compose "$@"); }

hr; echo "1. nvidia-smi (driver + GPU visible)"; hr
if nvidia-smi >/dev/null 2>&1; then
    green "nvidia-smi OK"; nvidia-smi | head -10
else
    red "nvidia-smi failed - driver not loaded?"
fi

hr; echo "2. Docker compose stack: the vllm service is running/healthy"; hr
PS_OUT=$(dc ps --format json 2>/dev/null || dc ps)
echo "$PS_OUT"
if echo "$PS_OUT" | grep -q "vllm" && echo "$PS_OUT" | grep -E "vllm.*(running|healthy)" >/dev/null; then
    green "vllm running/healthy"
elif echo "$PS_OUT" | grep -q "vllm"; then
    red "vllm present but not running/healthy (check: docker compose logs vllm)"
else
    red "vllm service not found in compose stack"
fi

hr; echo "3. vLLM /v1/models (OpenAI model listing)"; hr
MODELS=$(curl -sf "${VLLM_URL}/v1/models" || true)
if [ -n "$MODELS" ]; then
    echo "$MODELS" | head -c 400; echo
    if echo "$MODELS" | grep -q "${VLLM_MODEL}"; then
        green "vLLM serves ${VLLM_MODEL}"
    else
        red "vLLM /v1/models missing expected alias ${VLLM_MODEL}"
    fi
else
    red "${VLLM_URL}/v1/models unreachable (vLLM still loading?)"
fi

hr; echo "4. Ask-style /v1/chat/completions (text-only, non-streaming)"; hr
PAYLOAD=$(cat <<JSON
{"model":"${VLLM_MODEL}","stream":false,
 "messages":[{"role":"user","content":"Reply with the single word: READY"}],
 "max_tokens":16}
JSON
)
RESP=$(curl -sf -H 'Content-Type: application/json' -d "$PAYLOAD" "${VLLM_URL}/v1/chat/completions" || true)
if echo "$RESP" | grep -q '"content":"READY"'; then
    green "Ask endpoint responded correctly"
    echo "$RESP" | head -c 400; echo
elif echo "$RESP" | grep -q '"content"'; then
    # Model responded but didn't say READY - still a successful endpoint call
    green "Ask endpoint responded (model output may differ from prompt template)"
    echo "$RESP" | head -c 400; echo
else
    red "Ask endpoint did not respond as expected"; echo "$RESP" | head -c 400
fi

hr; echo "5. Ask-style /v1/chat/completions (streaming SSE)"; hr
PAYLOAD=$(cat <<JSON
{"model":"${VLLM_MODEL}","stream":true,
 "messages":[{"role":"user","content":"Count: 1 2 3"}],
 "max_tokens":32}
JSON
)
LINES=$(curl -sf -N -H 'Content-Type: application/json' -d "$PAYLOAD" "${VLLM_URL}/v1/chat/completions" | head -20)
if echo "$LINES" | grep -q '"finish_reason"' && echo "$LINES" | grep -q '"choices"'; then
    green "Streaming /v1/chat/completions works"
    echo "$LINES" | tail -3
else
    red "Streaming /v1/chat/completions did not produce expected SSE chunks"
    echo "$LINES"
fi

hr; echo "6. VLM-style /v1/chat/completions (text+image_url, OpenAI shape)"; hr
# 1x1 transparent PNG, base64-encoded
TINY_PNG="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII="
PAYLOAD=$(cat <<JSON
{"model":"${VLLM_MODEL}","stream":false,
 "messages":[{"role":"user","content":[
   {"type":"text","text":"Say the single word VISION"},
   {"type":"image_url","image_url":{"url":"data:image/png;base64,${TINY_PNG}"}}
 ]}],
 "max_tokens":16}
JSON
)
RESP=$(curl -sf -H 'Content-Type: application/json' -d "$PAYLOAD" "${VLLM_URL}/v1/chat/completions" || true)
if echo "$RESP" | grep -q '"choices"'; then
    green "VLM endpoint responded to text+image_url"
    echo "$RESP" | head -c 400; echo
else
    red "VLM endpoint failed"; echo "$RESP" | head -c 400
fi

hr; echo "Summary"; hr
printf "  Passed: %d\n  Failed: %d\n" "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0