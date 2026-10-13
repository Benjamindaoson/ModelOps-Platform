"""Build documentation directly from verified GPU/registry/lifecycle receipts."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "Evidence/llm-production-validation"
DOC = ROOT / "docs/evidence/llm-validation"


def read(path):
    return json.loads((ROOT / path).read_text())


def main():
    train = read("experiments/training/metrics.json")
    evaluation = read("docs/evidence/llm-validation/evaluation.json")
    registry = read("docs/evidence/llm-validation/registry/model_artifact.json")
    lifecycle = read("docs/evidence/llm-validation/serving/lifecycle.json")
    benchmark = read("benchmark/report.json")
    image = read("docs/evidence/llm-validation/docker-image-result.json")
    hardware = read("Evidence/llm-production-validation/hardware.json")
    if train["status"] != "COMPLETED" or lifecycle["status"] != "PASS":
        raise RuntimeError("Training/lifecycle receipt not passed")
    if benchmark["status"] != "PASS" or benchmark["valid_points"] != 45 or benchmark["valid_requests"] != 5760:
        raise RuntimeError("Benchmark coverage not verified")
    if registry["mlflow"]["run_id"] != train["mlflow_run_id"]:
        raise RuntimeError("Registry/training run mismatch")
    if image["build_status"] != "PASS":
        raise RuntimeError("Image build receipt missing")

    metadata = "import importlib.metadata as m,json,sys;names=['torch','transformers','peft','bitsandbytes','vllm','mlflow','psutil','PyYAML'];r={};\nfor n in names:\n try:r[n]=m.version(n)\n except m.PackageNotFoundError:pass\nprint(json.dumps({'python':sys.version.split()[0],'packages':r}))"
    versions = {}
    for name in (".venv", ".gpu-venv"):
        versions[name] = json.loads(subprocess.check_output([str(ROOT / name / "bin/python"), "-c", metadata], text=True))
    (DOC / "hardware.json").write_text(json.dumps(hardware, indent=2) + "\n")
    (DOC / "versions.json").write_text(json.dumps(versions, indent=2) + "\n")

    groups = benchmark["groups"]
    chosen = [x for x in groups if x["profile"] == "baseline" or x["concurrency"] == 32]
    table = ["| Profile | Concurrency | Requests/s | Output tokens/s | TTFT P50/P95/P99 ms | E2E P95 ms | Peak GPU MiB |",
             "|---|---:|---:|---:|---|---:|---:|"]
    for row in chosen:
        lat = row["latency_ms"]
        q = lambda key: lat[key]["mean_of_trial_percentiles"]
        table.append(f"| {row['profile']} | {row['concurrency']} | {row['requests_per_s_mean']:.3f} | {row['output_tokens_per_s_mean']:.2f} | {q('p50_ttft_ms'):.2f}/{q('p95_ttft_ms'):.2f}/{q('p99_ttft_ms'):.2f} | {q('p95_e2el_ms'):.2f} | {row['peak_gpu_used_mib']:.0f} |")
    table = "\n".join(table)
    base32 = next(x for x in groups if x["profile"] == "baseline" and x["concurrency"] == 32)
    batch32 = next(x for x in groups if x["profile"] == "batching-token-budget" and x["concurrency"] == 32)
    descriptive_delta = (batch32["output_tokens_per_s_mean"] / base32["output_tokens_per_s_mean"] - 1) * 100
    metrics = evaluation["metrics"]
    run_id = train["modelops_training_run_id"]
    mlflow_run = train["mlflow_run_id"]
    sha = train["checkpoint_sha256"]
    image_ref = image["registry"] + "@" + image["image_digest"]
    ram_gib = hardware["host_memory_bytes"] / (1024 ** 3)
    peak_gib = train["gpu_peak_allocated_bytes"] / (1024 ** 3)

    report = f"""# ModelOps LLM Production Validation Report

## Acceptance and scope

The revised sprint completed one actual managed Qwen2.5-3B QLoRA job, MLflow registration, independent heldout evaluation, native vLLM API loading and rollback, 45 valid serving measurements and an actual Docker image build. This proves a bounded model lifecycle; it does not certify enterprise production reliability or demonstrate better task quality.

Kubernetes GPU Pods were explicitly removed by the user. The rented GPU container has no authorized host Docker/Kubernetes runtime. Docker build and CPU image startup were executed in GitHub Actions; **GPU inference inside Docker remains unvalidated**. Native GPU vLLM inference is independently verified. AWQ and larger training are outside the revised scope.

## System architecture

```mermaid
flowchart LR
  D["Pinned Dolly short-answer dataset"] --> J["ModelOps TrainingJob"]
  J --> W["Transformers + PEFT QLoRA GPU worker"]
  W --> A["Private adapter / checkpoint / optimizer / RNG"]
  W --> T["MLflow Tracking"]
  T --> R["MLflow Registered Model"]
  A --> E["Independent heldout evaluation"]
  E --> G["ModelOps release gate"]
  G --> V["Native vLLM revisions / OpenAI API"]
  V --> B["Streamed benchmark + GPU telemetry"]
  V --> K["Version rollback"]
  B --> P["Hash-linked evidence report"]
  I["Digest-pinned Docker image built in CI"] -. "GPU-host launch documented; not executed here" .-> V
```

The existing Control API, registry, state reconciler, GPU worker, release gate and benchmark runner remain authoritative. Added scripts orchestrate those components; they do not replace SmolVLA with text training or build another platform.

## Hardware and exact software

- GPU: {hardware['gpu']}, {hardware['gpu_memory_mib']} MiB; NVIDIA driver 580.173.02.
- CPU: {hardware['host_logical_cpu']} logical and {hardware['affinity_cpu']} affinity CPUs.
- Visible RAM: {hardware['host_memory_bytes']:,} bytes ({ram_gib:.2f} GiB). No smaller memory/CPU cgroup quota was reported; this is environment visibility, not a guaranteed cloud SLA.
- GPU environment: {', '.join(f"{k} {v}" for k, v in versions['.gpu-venv']['packages'].items())}.
- Metadata/control environment: Python {versions['.venv']['python']}, MLflow {versions['.venv']['packages'].get('mlflow', 'unavailable')}.
- Exact receipts: [hardware](evidence/llm-validation/hardware.json), [versions](evidence/llm-validation/versions.json). The environments are project-local and separate.

## Training results

| Field | Actual value |
|---|---|
| Base model | Qwen/Qwen2.5-3B-Instruct |
| Frozen revision | aa8e72537993ba99e69dfaafa59ed015b17504d1 |
| ModelOps Run ID | {run_id} |
| MLflow Run ID | {mlflow_run} |
| Dataset | dolly-shortqa-v1: 64 training / 24 source-disjoint heldout examples |
| Recipe | NF4 double quantization, BF16 compute, rank 8, alpha 16, LR 1e-5, sequence limit 384, seed 9101 |
| Budget | 32 optimizer updates, batch 2, sampling with replacement |
| Trainable parameters | {train['trainable_parameters']:,} |
| Model load | {train['model_load_s']:.3f} s |
| Training-only wall time | {train['training_wall_s']:.3f} s |
| Worker wall time including load/export | {train['wall_s']:.3f} s |
| Training peak Torch allocated memory | {peak_gib:.3f} GiB |
| Parameter L-infinity update | {train['parameter_delta_linf']:.10f} |
| Adapter SHA-256 | {train['adapter_sha256']} |
| Merged checkpoint SHA-256 | {sha} |

This is real gradient-based QLoRA, evidenced by 32 step logs, changed trainable weights, actual adapter/merged weights and saved optimizer/scheduler/RNG state. Sampling 64 draws with replacement is **not** one deterministic complete epoch. Loading/exporting and upstream asset downloads are not folded into the 14-second training-only figure.

Weights remain in private cloud storage. All 11 source model files were independently checked against official Hugging Face Git/LFS identities after transport from the official Qwen ModelScope mirror. Transport problems and interrupted attempts remain in private logs. No new model weights or full source dataset are pushed to GitHub.

Receipts: [training metrics](../experiments/training/metrics.json), [step logs](evidence/llm-validation/training/training_log.json), [frozen config](../experiments/training/config.yaml), [official source identity](evidence/llm-validation/training/official-source.json).

## Evaluation and registry

| Metric, 24 heldout examples | Frozen base | Trained candidate |
|---|---:|---:|
| Token F1 | {metrics['base_token_f1']:.6f} | {metrics['candidate_token_f1']:.6f} |
| Exact match | 14/24 | 13/24 |

Candidate-minus-base F1 = **{metrics['delta_token_f1']:.6f}**. The unchanged engineering gate F1 >= 0.55 and delta >= -0.02 passed. **Quality declined; no improvement is claimed.** Twenty-four narrow short-answer examples do not establish general model quality, statistical superiority or production suitability.

Actual MLflow Registered Model **ModelOps-Qwen2.5-3B version 1** is READY and refers to Run {mlflow_run}. Hyperparameters, per-step metrics, evaluation metrics, real adapter files and a verified private merged-checkpoint reference are recorded. MLflow pyfunc serving is not claimed.

ModelOps initially registered the single checkpoint file, then registered version 2 for the full serving package used by evaluation. These are distinct packaging identities of the same measured weights, not modified checkpoints. The evaluated/deployed package has its own tree digest and lineage. Historical metadata fields are preserved; independent receipts, not an unverified DB flag alone, establish hashes.

![Actual MLflow training run](evidence/llm-validation/screenshots/mlflow-training.png)
![Actual MLflow registered model](evidence/llm-validation/screenshots/mlflow-registry.png)

Screenshots were captured from the running local MLflow server, with DOM text checks and zero page errors. Receipts: [registry](evidence/llm-validation/registry/model_artifact.json), [evaluation and predictions](evidence/llm-validation/evaluation.json), [screenshot validation](evidence/llm-validation/screenshots/validation.json).

## Serving and rollback

The actual native vLLM controller loaded base generation 1, trained generation 2 and base rollback generation 3. All three returned real OpenAI-compatible responses with the correct artifact IDs. Cold readiness was approximately 32.30 / 30.29 / 32.31 seconds; this is separate from warm request latency.

An actual curl request to the trained model answered “Paris”. The API smoke call, release approval, evaluation correlation and rollback response are retained in [lifecycle evidence](evidence/llm-validation/serving/lifecycle.json), [curl response](evidence/llm-validation/serving/curl_response.json) and [API response](evidence/llm-validation/serving/api_response.json).

```bash
curl --fail --max-time 60 http://127.0.0.1:18000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{{"model":"modelops-qwen3b-qlora","messages":[{{"role":"user","content":"What is the capital of France? Answer briefly."}}],"max_tokens":16,"temperature":0}}'
```

Use the actual served ID returned by /v1/models for a particular managed revision. Loopback exposure and separate development release principals were used; this is not a validated enterprise OIDC/human approval deployment. GPU processes were stopped after their owned measurements; the CPU MLflow metadata service can remain available for review.

## Inference benchmark

**45 valid trials, 5,760 streamed requests.** Each of three profiles runs 128 requests at concurrency 1/4/8/16/32, repeated three times. Input token budget 256, forced output 64, FP16, context bound 2048, same merged checkpoint and paired seeds 8100/8101/8102.

{table}

At concurrency 32, the token-budget profile measured {descriptive_delta:.2f}% higher mean output throughput than baseline on this workload. This is a descriptive result, not a guaranteed optimization gain. At concurrency 16 that profile was slower; retain the complete matrix instead of selecting only a favorable row.

TTFT/TPOT/end-to-end percentiles above are **means of three trial percentiles**, not pooled 384-request quantiles. Throughput has between-trial standard deviation in the JSON. GPU memory is NVML peak reservation, whereas training memory uses Torch peak allocation; these are different instruments. GPU mean utilization/power sampling includes CLI initialization, so it cannot be interpreted as decoder-only steady-state efficiency. The matrix is synthetic; no production SLO or maximum capacity is established.

vLLM already continuously batches. The batching profile changes max_num_batched_tokens to 4096; it does not enable a previously absent batching algorithm. The KV profile changes memory reservation from 0.90 to 0.95; no quantized KV cache or AWQ comparison was executed.

One valid first point was reused after repairing a summary-path mismatch. One 128-request point overlapped a validation curl, was retained and excluded, and only that cell was repeated. Excluded measurements/controller exceptions are preserved separately from the formal 5,760-request denominator.

![Real measured throughput and latency](evidence/llm-validation/benchmark/throughput_latency.png)

Full results: [benchmark report](../benchmark/report.md), [machine-readable results](../benchmark/report.json), [file hashes and coverage audit](evidence/llm-validation/benchmark/validation.json). Raw request outputs, per-request timings and GPU power/utilization samples remain under Evidence/llm-production-validation/benchmark.

## Docker image

An actual GitHub Actions build produced:

```text
{image_ref}
```

Build source revision: {image['source_revision']}; [actual build run]({image['github_run_url']}). The base image is immutable vLLM 0.10.2 digest {image['base_image'].split('@')[-1]}. A subsequent CPU container startup smoke also executed the hash-checking entrypoint in describe mode. It proves runnable startup code, not CUDA inference.

The image includes no model weights. UID 10001, read-only model mount, loopback binding, dropped capabilities, no-new-privileges and tmpfs cache are configured. Private model directory permissions must allow that UID to read the mounted files. GHCR authentication may be needed; anonymous visibility is not assumed.

```bash
docker build -f deploy/llm-validation/Dockerfile -t modelops-llm-validation:local .
export MODEL_DIR=/absolute/path/to/verified/merged
export MODEL_SHA256={sha}
docker compose -f deploy/llm-validation/docker-compose.yml up --build
# Equivalent direct GPU-host invocation (documented, not executed in this rented container):
docker run --rm --gpus all --read-only --tmpfs /tmp:uid=10001,gid=10001,mode=1777,size=8g \
  --cap-drop ALL --security-opt no-new-privileges \
  -p 127.0.0.1:18000:8000 --mount type=bind,src="$MODEL_DIR",dst=/model,readonly \
  -e MODEL_SHA256="$MODEL_SHA256" modelops-llm-validation:local
```

Artifacts: [Dockerfile](../deploy/llm-validation/Dockerfile), [Compose](../deploy/llm-validation/docker-compose.yml), [requirements](../deploy/llm-validation/requirements.txt), [build receipt](evidence/llm-validation/docker-image-result.json).

## Reproduction and recovery

Run from the existing cloud checkout with its separate .venv and .gpu-venv, frozen source dataset manifest and verified private model bundle:

```bash
.venv/bin/python experiments/training/train.py
.gpu-venv/bin/python -m ops.evaluate_llm_validation
.venv/bin/python -m ops.run_llm_lifecycle
.venv/bin/python benchmarks/llm-serving/run.py
.venv/bin/python -m ops.build_llm_validation_report
.venv/bin/python -m ops.build_llm_validation_docs
```

The existing completed training receipt is reused rather than starting another job; the resumable benchmark validates and skips complete points. A fresh machine must provision the frozen source dataset and authorized weights first. Public example data is not the full training dataset. Raw private metadata paths are recorded for provenance, not advertised as anonymous download links.

The CPU MLflow UI is local port 18791. Access through an authorized SSH tunnel:
```bash
ssh -N -L 18791:127.0.0.1:18791 -p 24138 root@175.155.64.171
```
No credentials are embedded. Lifecycle controllers acquire the existing GPU lease and stop only their own server processes; no robotics checkpoint or queue is changed.

## Engineering lessons and remaining limits

1. **Identity before lifecycle:** multi-shard base models need a complete bundle hash, while checkpoint-file and full serving-package identities must remain distinct. A syntactically valid registry record alone does not prove bytes.
2. **Quantization is phase-specific:** NF4/BF16 reduces trainable memory in QLoRA. The served merged model here is FP16; the experiment does not establish quantized inference equivalence.
3. **Performance depends on the workload:** more concurrency improved aggregate throughput but increased per-request duration. Raising KV reservation consumed additional VRAM with only a small descriptive throughput difference.
4. **Production claims require separate evidence:** native API/rollback, CPU image build and prior CPU Kubernetes contracts are different gates. No GPU Pod, GPU Docker, SGLang/TEI runtime, production OIDC, HA or commercial deployment was verified here.
5. **Costs are not inferred from throughput:** raw GPU power/time records and worker wall times are available; no cloud invoice or price-per-hour evidence was supplied. No monetary savings or billed GPU-hour claim is made.
6. **Review boundaries:** this side conversation permits no subagents. Final review is author review plus CI, not an independent security or infrastructure certification.

## Licensing and public evidence

The platform retains upstream Apache-2.0 notices. Qwen2.5-3B-Instruct uses the [Qwen research license](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/aa8e72537993ba99e69dfaafa59ed015b17504d1/LICENSE); do not infer unrestricted commercial use from this engineering result. Dolly examples require [CC BY-SA 3.0 attribution](https://huggingface.co/datasets/databricks/databricks-dolly-15k). Weight/model/dataset permissions are distinct from the source-code license.

GitHub receives code, bounded public examples, real metrics, hash manifests and actual MLflow screenshots. Full private weights, source datasets, MLflow DB and raw request outputs remain in the cloud worktree. This sprint does not publish a model or robotics dataset.

## Final verification evidence

[Final acceptance and hashes](evidence/llm-validation/validation.json) and [checked code-snapshot CI](evidence/llm-validation/ci.json) record the software check results separately from actual GPU experiments. The feature PR preserves public ancestry and a private local/public source correspondence receipt; it is left for review, not automatically merged.
"""
    (ROOT / "docs/modelops-validation-report.md").write_text(report)
    short = f"""
## LLM Production Validation Sprint

**Real Qwen2.5-3B QLoRA → MLflow → quality gate → vLLM API → benchmark → rollback.** This bounded RTX 3090 run extends the existing ModelOps lifecycle; it does not replace the platform with a standalone training demo.

```mermaid
flowchart LR
  D["Frozen dataset"] --> T["Managed QLoRA GPU job"]
  T --> M["MLflow Tracking / Registry"]
  T --> C["Private checkpoint"]
  C --> E["Independent evaluation gate"]
  E --> S["vLLM API / version rollback"]
  S --> B["Streamed benchmark / GPU telemetry"]
  B --> R["Evidence report"]
  I["Real Docker image build"] -. "GPU-host execution not yet validated" .-> S
```

| Delivery | Actual evidence |
|---|---|
| Training | 32 optimizer updates, 14,966,784 trainable parameters; training-only {train['training_wall_s']:.3f} s, worker {train['wall_s']:.3f} s; {peak_gib:.3f} GiB Torch peak allocation |
| Tracking / Registry | MLflow Run {mlflow_run}; ModelOps Run {run_id}; ModelOps-Qwen2.5-3B version 1 READY |
| Evaluation | 24 source-disjoint heldout examples; F1 {metrics['base_token_f1']:.6f} → {metrics['candidate_token_f1']:.6f}; **quality declined**, unchanged gate passed |
| Serving | Real base → trained → rollback API responses; trained curl response answered Paris |
| Benchmark | 45 valid trials / 5,760 requests, three FP16 profiles, three repeats, concurrency 1/4/8/16/32 |
| Docker | Real digest-pinned image build and CPU startup smoke in Actions; **GPU Docker execution unvalidated** |

{table}

Percentiles are means of three trial percentiles; traffic is synthetic. Default vLLM continuous batching was already active. Full trials include unfavorable tuning results; no production SLO, AWQ speedup, quality improvement or monetary savings is claimed. Kubernetes GPU deployment is out of the revised sprint scope.

![Actual MLflow training run](docs/evidence/llm-validation/screenshots/mlflow-training.png)
![Actual MLflow model version](docs/evidence/llm-validation/screenshots/mlflow-registry.png)
![Measured performance](docs/evidence/llm-validation/benchmark/throughput_latency.png)

Start with [training script/config/example](experiments/training/README.md), [full evidence report](docs/modelops-validation-report.md), [benchmark report](benchmark/report.md), [raw-result hash audit](docs/evidence/llm-validation/benchmark/validation.json), [Docker recipe](deploy/llm-validation/docker-compose.yml) and [actual image build receipt](docs/evidence/llm-validation/docker-image-result.json). Source revision and file hashes are linked in the report. Qwen research-license weights stay private; the repository code license does not grant commercial rights to the model.

```bash
# Run from the project with frozen private inputs and its isolated environments.
.venv/bin/python experiments/training/train.py
.venv/bin/python benchmarks/llm-serving/run.py
# Example against a running validated service; use the actual /v1/models ID:
curl --fail http://127.0.0.1:18000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{{"model":"modelops-qwen3b-qlora","messages":[{{"role":"user","content":"What is the capital of France?"}}],"max_tokens":16,"temperature":0}}'
```

On a GPU Docker host, build the image and use the [Compose recipe](deploy/llm-validation/docker-compose.yml) with a read-only private MODEL_DIR and measured MODEL_SHA256. A CPU image build is not a GPU container performance test. The previous v1.0 RC evidence below is a separate earlier experiment, not the denominator for this sprint.

"""
    def insert(path, heading, text):
        p = ROOT / path
        current = p.read_text()
        start = current.find("## LLM Production Validation Sprint")
        if start >= 0:
            finish = current.index(heading, start)
            current = current[:start] + current[finish:]
        at = current.index(heading)
        p.write_text(current[:at] + text.strip() + "\n\n" + current[at:])
    insert("README.md", "## v1.0 RC:", short)
    chinese = f"""
## LLM Production Validation Sprint

本轮证明的是可追溯的模型生命周期：真实 GPU 微调、独立评测、版本登记、推理 API、性能测量与回滚。沿用原有 ModelOps 控制面和执行器，模型与数据留在私有云端目录。

- **真实训练：** Qwen2.5-3B-Instruct，NF4 QLoRA、BF16 计算；32 次更新、batch 2、rank 8、alpha 16，14,966,784 个可训练参数。训练段 {train['training_wall_s']:.3f} 秒；含加载/导出的 worker 总耗时 {train['wall_s']:.3f} 秒；Torch 峰值分配 {peak_gib:.3f} GiB。替换抽样不等于完整遍历一个 epoch。
- **模型追踪：** ModelOps Run {run_id}，MLflow Run {mlflow_run}；实际注册 ModelOps-Qwen2.5-3B version 1 READY，关联 Adapter、Checkpoint、参数和评测。
- **质量证据：** 64 个训练样本，24 个来源隔离的开发验证样本；F1 {metrics['base_token_f1']:.6f} → {metrics['candidate_token_f1']:.6f}。结果略降，未修改原有准入门槛，不能写成质量提升。
- **服务闭环：** 实际完成 base → 微调模型 → rollback 三次 vLLM 加载和 OpenAI-compatible API 调用。
- **性能：** 45 个有效测量点、5,760 次真实流式请求；3 种 FP16 配置、每组 3 次重复、并发 1/4/8/16/32。
- **容器：** GitHub Actions 实际构建镜像并执行 CPU 启动合同检查；GPU 容器推理尚未验证。本轮按用户调整不做 Kubernetes。

{table}

表中延迟是三次试验分位数的均值，不是合并请求后的分位数。默认 vLLM 已启用连续批处理；调整的是 token 预算和显存预留。完整报告保留性能变差的配置与被排除的干扰测量，不声称生产 SLO、通用加速倍数或费用节省。

```mermaid
flowchart LR
  D["冻结数据"] --> T["ModelOps QLoRA GPU 作业"]
  T --> R["MLflow / 模型版本"]
  T --> C["私有 Checkpoint"]
  C --> E["独立评测准入"]
  E --> S["vLLM API / 回滚"]
  S --> B["流式 Benchmark / GPU 监控"]
  B --> P["真实证据报告"]
```

![实际 MLflow 训练记录](docs/evidence/llm-validation/screenshots/mlflow-training.png)
![实际 MLflow 模型版本](docs/evidence/llm-validation/screenshots/mlflow-registry.png)
![实测吞吐与延迟](docs/evidence/llm-validation/benchmark/throughput_latency.png)

查看 [完整实验报告](docs/modelops-validation-report.md)、[训练入口](experiments/training/README.md)、[全部性能数据](benchmark/report.md)、[证据与 Hash](docs/evidence/llm-validation/benchmark/validation.json)、[真实镜像构建记录](docs/evidence/llm-validation/docker-image-result.json) 和 [GPU 主机 Compose 启动方式](deploy/llm-validation/docker-compose.yml)。权重未上传到 GitHub；Qwen 模型研究许可证与平台 Apache-2.0 源码许可分别适用，不能据此声称可无限制商用。

"""
    insert("README.zh-CN.md", "## 五大功能模块", chinese)
    training_readme = f"""# Qwen2.5-3B managed QLoRA

The entrypoint uses the existing ModelOps TrainingJob and Transformers/PEFT GPU worker; it does not bypass job reconciliation or replace robotics Flow Matching.

## Actual completed run

- Model: Qwen/Qwen2.5-3B-Instruct revision aa8e72537993ba99e69dfaafa59ed015b17504d1.
- ModelOps Run: {run_id}; MLflow Run: {mlflow_run}; registered version 1 READY.
- Frozen Dolly short-answer split: 64 train / 24 source-disjoint heldout, seed 9101.
- 32 optimizer updates, batch two, with-replacement sampler; not a deterministic full epoch.
- NF4 double quantization, BF16 compute, rank 8, alpha 16, LR 1e-5, sequence 384.
- Training-only {train['training_wall_s']:.3f} s; worker total {train['wall_s']:.3f} s; peak Torch allocation {peak_gib:.3f} GiB.
- Heldout F1 declined {metrics['base_token_f1']:.6f} → {metrics['candidate_token_f1']:.6f}; no quality improvement claim.

## Files and execution

config.yaml freezes the recipe; train.py invokes the managed controller; metrics.json exports actual results; dataset_example.json is a small real attributed example, not the full training dataset.

```bash
.venv/bin/python experiments/training/train.py
.gpu-venv/bin/python -m ops.evaluate_llm_validation
.venv/bin/python -m ops.run_llm_lifecycle
```

Run from the project root with project-local .venv/.gpu-venv, verified private model bundle and frozen source dataset manifest. Completed controller receipts are reused. A fresh host must first restore the exact authorized private inputs; no model weight is bundled in Git.

[Full evidence and Docker/serving reproduction](../../docs/modelops-validation-report.md), [training logs](../../docs/evidence/llm-validation/training/training_log.json), [MLflow registry receipt](../../docs/evidence/llm-validation/registry/model_artifact.json).
The base is Qwen research-licensed; Dolly examples require CC BY-SA 3.0 attribution. Public metrics/source do not grant commercial model rights.
"""
    (ROOT / "experiments/training/README.md").write_text(training_readme)
    (DOC / "PHASE_05.md").write_text("# Phase 5 — PASS: real benchmark\n\n45 valid points, 5,760 requests, 3 profiles x 5 concurrency levels x 3 repeats. Raw/status/manifest/GPU trace hashes rechecked; excluded overlapping smoke measurement retained and only that cell repeated. See benchmark/result.json and benchmark/validation.json. Percentile aggregation and synthetic workload limits are explicit.\n")
    print(json.dumps({"report":"docs/modelops-validation-report.md","readmes":2,"valid_requests":5760,"descriptive_c32_token_budget_delta_percent":descriptive_delta}))


if __name__ == "__main__":
    main()
