# GPU Docker runtime validation
This is an executable real NVIDIA container probe, not evidence that a rented container has Docker host authority. The GPU image starts the existing hash-checking vLLM entrypoint, then executes nvidia-smi, torch.cuda.is_available(), model readiness/identity and a real OpenAI chat request. Failure exits nonzero and saves logs. Weights are private read-only mounts; output UID10001 must have write access to its explicitly prepared evidence directory.

On an authorized NVIDIA Container Toolkit Docker host:
```bash
docker build -f deploy/llm-validation/gpu-runtime/Dockerfile -t modelops-gpu-runtime:local .
export MODEL_DIR=/absolute/path/to/verified/merged
export MODEL_SHA256=04f8b6f49494117020a2134de0422ad9a4f8d4c77fd2767eb70d362cb4b0225b
export GPU_EVIDENCE_DIR=/absolute/path/to/writable/evidence
docker compose -f deploy/llm-validation/gpu-runtime/docker-compose.gpu.yml up
# Equivalent actual host invocation:
docker run --rm --gpus all -p 127.0.0.1:18000:8000 \
  --mount type=bind,src="$MODEL_DIR",dst=/model,readonly \
  --mount type=bind,src="$GPU_EVIDENCE_DIR",dst=/evidence \
  -e MODEL_SHA256="$MODEL_SHA256" modelops-gpu-runtime:local
```
A host-only probe records SKIPPED with null container/API results:
```bash
.venv/bin/python -m ops.gpu_runtime_validation host --output-root docs/evidence/gpu-runtime-validation
```
Missing Docker/runtime is not bypassed. CPU image build/startup does not validate CUDA inference. No Kubernetes deployment is involved.
