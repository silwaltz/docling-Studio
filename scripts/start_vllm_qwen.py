"""Start vLLM with Qwen3-VL-8B-Instruct-AWQ-4bit, single-model setup.

Container: vllm, port 8000, served as `qwen3-vl:8b-instruct`.
"""
from __future__ import annotations
import subprocess
import sys

CMD = [
    "docker", "rm", "-f", "vllm",
]
subprocess.run(CMD, check=False, capture_output=True)

CMD = [
    "docker", "run", "-d",
    "--name", "vllm",
    "--gpus", "all",
    "-p", "8000:8000",
    "-v", f"{__import__('os').path.expanduser('~')}/.cache/huggingface:/root/.cache/huggingface",
    "--ipc=host",
    "vllm/vllm-openai:latest",
    "--model", "cyankiwi/Qwen3-VL-8B-Instruct-AWQ-4bit",
    "--served-model-name", "qwen3-vl:8b-instruct",
    "--max-model-len", "24576",
    "--gpu-memory-utilization", "0.92",
    "--limit-mm-per-prompt", '{"image":1}',
    "--dtype", "auto",
]
result = subprocess.run(CMD, capture_output=True, text=True)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)
print("RETURN:", result.returncode)
