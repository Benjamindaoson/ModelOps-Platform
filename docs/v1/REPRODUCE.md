# Reproduce the v1.0 RC validation

Run inside the existing repository on an authorized Linux GPU host. Code, environments, weights and private receipts stay inside the project. The retained VLA assets are external references to the existing authorized VLA-Forge project; do not download or expose private robot material.

## Environments
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e 'control-plane[dev,postgres,robotics]' pyyaml
python3 -m venv .gpu-venv
.gpu-venv/bin/python -m pip install torch==2.8.0 transformers==4.55.4 peft==0.17.1 accelerate==1.10.1 bitsandbytes==0.47.0 datasets==4.0.0 vllm==0.10.2 psutil httpx pyyaml prometheus-client
.venv/bin/python -m ops.bootstrap_v1_assets
```
The observed CPU/GPU distributions are recorded in requirements-cpu.lock and requirements-gpu.lock. They are environment snapshots; install the project itself from the current checkout. CUDA 12.8 and an RTX 3090 were used. The worker fails if no CUDA device is available.

## Frozen data and real training
```bash
.venv/bin/python -c "from pathlib import Path; from pipelines.training.data_contract import freeze_dolly; freeze_dolly(Path('.tools/assets/dolly/databricks-dolly-15k.jsonl'), Path('Evidence/v1/datasets/public/dolly-v1'))"
.venv/bin/python -m ops.freeze_shortqa_v1
.venv/bin/python -m ops.run_v1_training
.venv/bin/python -m ops.run_v1_training --dataset shortqa
.gpu-venv/bin/python -m ops.evaluate_v1
.gpu-venv/bin/python -m ops.evaluate_v1 --dataset shortqa
```
Broad and short-answer splits have distinct frozen source IDs. The recipes live in pipelines/training/qwen_sft.yaml and qwen_qlora.yaml. The broad candidates are rejected by the unchanged release gate. The short-answer candidate passes without a measured quality improvement. Completed runs and evaluation files are rehashed and reused.

## Lifecycle and inference
```bash
.venv/bin/python -m ops.bootstrap_v1_db
.venv/bin/python -m ops.run_v1_lifecycle
.venv/bin/python -m ops.run_v1_inference --kind llm
.venv/bin/python -m ops.run_v1_inference --kind embedding
.venv/bin/python -m ops.run_v1_inference --kind vla
.venv/bin/python -m ops.run_v1_resume
.venv/bin/python -m ops.import_robotics_registry_v1
.venv/bin/python -m ops.build_v1_benchmark_bundle
.venv/bin/python -m ops.validate_native_recovery
```
The development control plane and model servers listen only on loopback. JWT/signing credentials are generated in process memory and never saved. Policy observations must specify scope=simulation. No real robot commands are sent. The inference harness retains technical failures and uses separate evidence paths for retries.

For a fresh run, use a fresh owned Evidence directory and a new job/deployment name if the existing SQL version already exists. Do not clear verified receipts or checkpoints to make a run look clean.

## Software checks
```bash
.venv/bin/python -m ops.verify_v1
```
The cloud check used project-local Node 22.19.0, Go 1.25.0, Helm 3.20.1 and envtest Kubernetes API 1.35.0. Supply equivalent tools through PATH or the documented .tools paths. Envtest does not run GPU Pods. The full Docker/kind suite remains a separate required production-infrastructure check.

## Production
The Linux backend is deliberately rejected in production mode. Production requires real Kubernetes, PostgreSQL, HTTPS OIDC, Ed25519 evaluation verification, provisioned tenants, private S3 bundles and immutable OCI images. Use the existing production preflight and deployment guides. No production credentials or dummy fixture images are deployment-ready.
