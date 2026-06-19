#!/bin/bash
# Start vLLM with Qwen3-VL-8B-Instruct-AWQ-4bit, single-model setup.
# Container: vllm, port 8000, served as `qwen3-vl:8b-instruct`.
docker rm -f vllm 2>/dev/null

docker run -d \
  --name vllm \
  --gpus all \
  -p 8000:8000 \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  --ipc=host \
  vllm/vllm-openai:latest \
  serve cyankiwi/Qwen3-VL-8B-Instruct-AWQ-4bit \
  --served-model-name qwen3-vl:8b-instruct \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.85 \
  --limit-mm-per-prompt '{"image":1}' \
  --dtype auto
