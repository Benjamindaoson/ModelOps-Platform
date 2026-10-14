"""Write first-screen evidence and readable reports only after actual acceptance passes."""
import json,re,statistics
from pathlib import Path
from .runtime import ROOT,E
from .report import P
def read(path):return json.loads(Path(path).read_text())
def replace_section(path,body):
    p=Path(path);s=p.read_text();start="<!-- INFERENCE_HARDENING_BEGIN -->";end="<!-- INFERENCE_HARDENING_END -->"
    block=start+"\n"+body+"\n"+end+"\n\n"
    if start in s:s=re.sub(re.escape(start)+r".*?"+re.escape(end)+r"\n*",block,s,flags=re.S)
    else:
        at=s.index("\n## ");s=s[:at]+"\n\n"+block+s[at:]
    p.write_text(s)
def append(path,body):
    p=Path(path);s=p.read_text();marker="\n## Advanced native execution — 2026-10-14\n"
    if marker in s:s=s[:s.index(marker)]
    p.write_text(s+marker+"\n"+body+"\n")
def main():
    status=read(P/"validation.json")
    if status["status"]!="PASS":raise ValueError("Do not publish final documentation before real acceptance")
    eng=read(P/"engine_comparison.json");quant=read(P/"quantization_comparison.json");prof=read(P/"profiling_summary.json");tr=read(P/"training_optimization.json")
    def point(model,w,c):return next(g for g in quant["models"][model]["groups"] if g["workload"]==w and g["concurrency"]==c)
    base=point("fp16","C",32);gptq=point("gptq","C",32);mem=1-gptq["peak_gpu_mib"]/base["peak_gpu_mib"];speed=gptq["output_tokens_s_mean"]/base["output_tokens_s_mean"]
    ratios=[r["output_tps_ratio"] for r in prof["pairs"]]
    no=tr["runs"]["no-checkpoint"];yes=tr["runs"]["checkpoint"];saved=1-yes["result"]["gpu_peak_allocated_bytes"]/no["result"]["gpu_peak_allocated_bytes"]
    en=f"""## Advanced GPU evidence — 2026-10-14

Single-host engineering validation: **PASS**. The current driver reports RTX4080 SUPER, CC8.9; old RTX3090 results below remain historical and are not mixed.

- **Two engines:** vLLM0.10.2 / SGLang0.4.10, 90 matched points and2,880 actual requests, three repeats at each workload/concurrency. Same pinned model/tokenizer/FP16/sampling/cache protocol.
- **Real quantization:** own GPTQ and AWQ W4A16 conversion, not downloaded ready-made weights. With the same3GiB KV budget, GPTQ C32 decode throughput is {gptq['output_tokens_s_mean']:.2f} vs {base['output_tokens_s_mean']:.2f} tokens/s ({speed:.2f}x); peak visible GPU memory is {gptq['peak_gpu_mib']:.0f} vs {base['peak_gpu_mib']:.0f}MiB ({mem:.1%} lower).
- **Quality gate:** GPTQ passed the frozen engineering policy on128 QA +24 smoke samples. AWQ failed quality and is rejected. This is not broad task-quality certification.
- **GPU profile:** real PyTorch/CUDA traces and a repeated-context prefix-cache A/B: {min(ratios):.2f}–{max(ratios):.2f}x throughput, 96/96 output texts identical. No custom kernel or measured HBM bandwidth claim.
- **Managed training:** two64-update BF16/NF4 QLoRA configurations plus a controlled interruption/resume. Checkpointing reduced Torch peak allocation by {saved:.1%}, with measured speed trade-offs. Resume weights/loss/sample sequence matched exactly.
- **Reliability:** actual loader, timeout, streaming, owned crash/restart and CUDA OOM faults; hash/version/quality/performance/telemetry guards fail closed. Native Prometheus/Grafana retained.
- **Boundaries:** GPU Docker and Nsight remain SKIPPED; no production business SLO, multi-node scale or domain-learning improvement is claimed.

[Current acceptance](docs/evidence/inference-hardening/validation_report.md) · [Engine results](benchmark/engine-comparison.md) · [Quantization](benchmark/quantization-comparison.md) · [GPU profile](docs/GPU_PERFORMANCE_PROFILING.md) · [Training/resume](experiments/training/optimization-report.md) · [Reproduction](deploy/llm-validation/native-hardening/README.md)
"""
    zh=f"""## 高级推理与训练实测｜2026-10-14

本轮单机工程验收：**PASS**。当前驱动报告 RTX4080 SUPER、CC8.9；下方 RTX3090 数字保留为历史结果，不混算。

- **双引擎对照：** vLLM0.10.2 与 SGLang0.4.10，90 个测量点、2,880 次真实请求；每个负载和并发均有三次重复，模型、Tokenizer、精度和请求协议冻结。
- **真实量化：** 从原始权重转换 GPTQ/AWQ W4A16。固定3GiB KV Cache 后，GPTQ 长输出 C32 吞吐为 {gptq['output_tokens_s_mean']:.2f} tokens/s，FP16 为 {base['output_tokens_s_mean']:.2f}，约 {speed:.2f} 倍；整卡峰值显存 {gptq['peak_gpu_mib']:.0f} vs {base['peak_gpu_mib']:.0f}MiB，下降 {mem:.1%}。
- **质量取舍：** GPTQ 在128条独立 QA 与24条 Smoke 上通过预设工程门槛；AWQ 未通过，保留负结果并拒绝发布。不能据此证明广泛质量不下降。
- **GPU 分析：** 真实 PyTorch/CUDA Trace；重复长上下文的 Prefix Cache 三次对照吞吐约 {min(ratios):.2f}–{max(ratios):.2f} 倍，96条输出完全一致。没有声称原创 CUDA Kernel 或已测得显存带宽瓶颈。
- **训练与恢复：** 两组64步 BF16/NF4 QLoRA 对照，检查点优化节省 {saved:.1%} 的 Torch 峰值分配，但也降低训练速度；另一次中断恢复与连续运行的权重、Loss、样本序列完全一致。
- **交付可靠性：** Hash、模型版本、质量、性能和缺失监控准入；真实 OOM、超时、流中断、服务重启检查。保留 Prometheus/Grafana。
- **尚未验证：** GPU Docker Runtime、Nsight 硬件计数器、生产业务 SLO 和多节点扩展。

[本轮验收](docs/evidence/inference-hardening/validation_report.md) · [引擎对照](benchmark/engine-comparison.md) · [量化对照](benchmark/quantization-comparison.md) · [GPU 分析](docs/GPU_PERFORMANCE_PROFILING.md) · [训练与恢复](experiments/training/optimization-report.md) · [复现入口](deploy/llm-validation/native-hardening/README.md)
"""
    replace_section(ROOT/"README.md",en);replace_section(ROOT/"README.zh-CN.md",zh)
    for filename in ["README.md","README.zh-CN.md"]:
        p=ROOT/filename;s=p.read_text()
        s=s.replace("> **Validation status:** the real single-host LLM lifecycle is validated on RTX3090."," > **Validation status:** historical lifecycle evidence is on RTX3090; current advanced native GPU evidence below is separately validated.").replace(" > **Validation status:"," > **Validation status:".lstrip())
        s=s.replace("> **实测边界：** 已验证 RTX3090 单机原生 LLM 生命周期；","> **实测边界：** RTX3090 是历史生命周期证据；本轮独立验证当前 GPU 的双引擎、量化、训练与恢复。")
        p.write_text(s)
    architecture="The existing FastAPI/Next.js/MLflow architecture is retained. Explicit native adapters now manage isolated vLLM/SGLang runtimes, immutable package verification, GPU lease/process ownership, fixed protocol benchmark, local INT4 conversion, controlled QLoRA resume and engineering quality/regression decisions. No new UI, Kubernetes cluster or diagram was introduced. SGLang/INT4 use the explicit adapter; the older NativeDeployment API's validation scope remains distinct. Raw weights, optimizer/RNG, prompts and traces stay private. Current acceptance: docs/evidence/inference-hardening/validation_report.md."
    append(ROOT/"ARCHITECTURE.md",architecture);append(ROOT/"docs/FINAL_ARCHITECTURE.md",architecture)
    p=ROOT/"CHANGELOG.md";s=p.read_text();entry="## Advanced inference and training — 2026-10-14\n\n- Added native dual-engine loading/identity adapters and90-point matched measurements.\n- Actually converted and evaluated GPTQ/AWQ; preserved AWQ quality rejection.\n- Captured CUDA/PyTorch traces and output-verified prefix/cache and configuration experiments.\n- Added token-weighted accumulation, checkpointing configuration, semantic resume identity and managed64-update comparisons.\n- Hardened Registry/online version, telemetry and quality/performance decisions with bounded real faults.\n- Fixed missing Registry revision and excessive Unix socket temp paths; retired an incorrect fault classification rather than claiming it as evidence.\n- Published safe summaries only; no raw weights/data, GPU Docker, Nsight, multi-node or business-SLO claims.\n\n"
    if "## Advanced inference and training — 2026-10-14" not in s:s=s.replace("## ModelOps LLM validation finalization",entry+"## ModelOps LLM validation finalization",1)
    p.write_text(s)
    profile_lines=["# Measured GPU profile and optimization","\nActual PyTorch/CUDA trace; Nsight unavailable. Summed overlapping event duration is not wall-clock attribution, bandwidth or occupancy.","\n|Hot kernel|Summed ms|","|---|---:|"]
    profile_lines += [f"|{name[:120].replace('|',' ')}|{duration/1000:.3f}|" for name,duration in prof["trace"]["kernel_duration_us"][:8]]
    profile_lines+=["\nThe measured trace contains substantial dense GEMM/GEMV work and attention. Repeated long-context prefill was selected for a cache experiment; this is an evidenced workload optimization, not certification that all decode is HBM-bound.","\n|Repeat|Output text identical|TTFT P50 ratio on/off|TPOT P50 ratio|Throughput ratio|","|---|---|---:|---:|---:|"]
    profile_lines += [f"|{r['repeat']}|{r['output_exact']}|{r['ttft_p50_ratio']:.4f}|{r['tpot_p50_ratio']:.4f}|{r['output_tps_ratio']:.4f}|" for r in prof["pairs"]]
    profile_lines+=["\nSame frozen FP16 weights,2048 input/128 output, C16,32 requests x3 repeats. Warmup3. Same context intentionally repeats; no general unique-context speedup claim. All96 request outputs match exactly. Native prefix caching is inherited; experiment coordination and verification are new.","\nOne-factor batch4096 / max-sequences32 / static-memory.60 tests for both engines retain every run. Full latency/memory/power/config results and failures: [profiling_summary.json](evidence/inference-hardening/profiling_summary.json).","\nRaw trace paths and SHA256:"]+[f"- {x['path']} — {x['sha256']}" for x in prof["trace"]["traces"]]
    (ROOT/"docs/GPU_PERFORMANCE_PROFILING.md").write_text("\n".join(profile_lines)+"\n")
    qlines=["# Actual INT4 conversion: quality and performance",
        "\nSame official Qwen2.5-3B revision,64 frozen calibration records, FP16 serving activations. Benchmark runs fix KV memory at3GiB. Statistics use three repeats/96 requests per point; peak GPU memory is NVML whole-device memory, while training allocation uses Torch separately.",
        "\n|Package|Weights GB|Conversion s|Load readiness s|A C1 output tokens/s|C C32 output tokens/s|Peak MiB|QA128 F1/EM|Quality policy|",
        "|---|---:|---:|---:|---:|---:|---:|---|---|"]
    for name,m in quant["models"].items():
        folder=ROOT/".tools/assets/qwen3b-base" if name=="fp16" else E/"quantization"/name/"model"
        weight_bytes=sum(f["bytes"] for f in read(folder/"modelops-files.json")["files"] if f["name"].endswith(".safetensors"))
        aa=point(name,"A",1);cc=point(name,"C",32);qa=m["quality"]["groups"]["squad128"]
        conversion=m.get("conversion") or {}
        qlines.append(f"|{name}|{weight_bytes/1e9:.3f}|{conversion.get('wall_s','Original')}|{aa['load_readiness_s']:.2f}|{aa['output_tokens_s_mean']:.2f}|{cc['output_tokens_s_mean']:.2f}|{cc['peak_gpu_mib']:.0f}|{qa['token_f1']:.5f}/{qa['exact_match']:.5f}|{m['quality_gate']['status']}|")
    qlines+=["\nMeasured recommendations: GPTQ passes the fixed2-percentage-point F1/EM policy on both the128 QA and24 smoke groups. It is faster and uses less visible memory in the observed short/decode points. AWQ runs successfully but fails quality, so it is not a publishable candidate under this policy.",
        "\nLong-context caveat: inspect B-C16/C32 TTFT/TPOT/P95/P99 in [full JSON](../docs/evidence/inference-hardening/quantization_comparison.json); quantization does not remove prefill latency, and some latency values regress. Largest tested concurrency is32; physical capacity/production SLO is not established. Startup time includes hashing/initialization/compile/readiness, not weight read time alone.",
        "\nSource-pinned SQuAD128 uses48 validation article groups, revision7b6d24c440a36b6815f21b70d25016731768db1f, CC-BY-SA4.0. Existing normalized token-overlap F1/EM differs from official SQuAD scoring. Dolly24 is a separate small smoke check, not a broad non-inferiority result. Raw text and all weights remain private."]
    (ROOT/"benchmark/quantization-comparison.md").write_text("\n".join(qlines)+"\n")
    tlines=["# Controlled64-update QLoRA and exact resume",
        "\nFrozen base/data/seed9102/effective batch4/rank8/alpha16/LR1e-5/max length384; BF16 compute, NF4 double quantization. Gradient checkpointing is the only efficiency factor. A third run intentionally pauses at17 and resumes to64. Sampling is with replacement, not an epoch claim.",
        "\n|Condition|Steps|Input tokens/s|Mean step s|Torch peak GiB|Training wall s|Final loss|QA128 F1|Dolly24 F1|Gate|",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for label,r in tr["runs"].items():
        result=r["result"];qa=r["quality"]["groups"]
        steps=[json.loads(x) for x in (Path(result["adapter"]).parent/"steps.jsonl").read_text().splitlines()]
        tlines.append(f"|{label}|{result['steps']}|{r['tokens_s']:.2f}|{1/r['steps_s']:.4f}|{result['gpu_peak_allocated_bytes']/2**30:.3f}|{result['training_wall_s']:.3f}|{steps[-1]['loss']:.6f}|{qa['squad128']['token_f1']:.6f}|{qa['dolly24']['token_f1']:.6f}|{r['quality_gate']['status']}|")
    tlines+=["\nResume audit: "+json.dumps(tr["resume_consistency"]),"\nAll three merged checkpoint and adapter SHA values match. Minor Dolly24 inference-score differences were observed despite identical checkpoint bytes; cause was not independently isolated. Do not present these differences as learning improvement. Expanded128 F1 is slightly below base, within the predeclared engineering threshold.",
        "\nCheckpointing saves memory but reduces observed tokens/s. Resume training_wall_s is only the resumed segment; full costs include the saved17-step prefix, two loads and export. Step logs reconstruct all64 updates. LR is logged after scheduler.step (next-step LR), so final logged LR0 is not the LR used for the final optimizer update.",
        "\nRun/MLflow/model/evaluation IDs, immutable SHA values and private output paths: [training_optimization.json](../../docs/evidence/inference-hardening/training_optimization.json). Required Registry revision and Unix IPC path failures were fixed and retained; completed GPU training was never repeated."]
    (ROOT/"experiments/training/optimization-report.md").write_text("\n".join(tlines)+"\n")
    print("Evidence-driven documentation written")

if __name__=="__main__":main()
