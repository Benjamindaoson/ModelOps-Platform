"""Package only observed real-endpoint results; no generated performance values."""
from pathlib import Path
import csv,json,platform,os,hashlib
ROOT=Path(__file__).resolve().parents[1]
def main():
    e=ROOT/"Evidence/v1";r=e/"benchmark/qwen-qa-fixed-v1"
    status=json.loads((r/"status.json").read_text())
    if status["status"]!="PASS":raise RuntimeError("Cannot publish a failed benchmark as passing")
    raw=json.loads((r/"raw-benchmark.json").read_text());manifest=json.loads((r/"manifest.json").read_text())
    inference=json.loads((e/"inference-llm.json").read_text())
    if inference["status"]!="PASS" or inference["model"]["id"]!=manifest["model"]:
        raise RuntimeError("Benchmark and loaded model identities disagree")
    rows=list(csv.DictReader((r/"gpu-telemetry.csv").open()))
    gpu={"samples":len(rows),"peak_used_mib":max(float(x["memory_used_mib"]) for x in rows),
        "mean_utilization_percent":sum(float(x["utilization_percent"]) for x in rows)/len(rows),
        "peak_utilization_percent":max(float(x["utilization_percent"]) for x in rows),
        "sample_interval_s":.25,"scope":"whole GPU during benchmark subprocess, includes client initialization"}
    cpu=next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines()
        if l.startswith('model name')),"unknown")
    hardware={"gpu_snapshot":manifest["gpu_snapshot"],"cpu_model":cpu,"logical_cpus":os.cpu_count(),
        "os":platform.platform(),"gpu_measurements":gpu}
    result={"status":"PASS","completed_requests":raw["completed"],
        "unsuccessful_planned_requests":manifest["prompts"]-raw["completed"],
        "wall_s":raw["duration"],"requests_per_s":raw["request_throughput"],
        "output_tokens_per_s":raw["output_throughput"],
        "latency_ms":{k:raw[k] for k in raw if k.startswith(("p50_","p95_","p99_"))},
        "gpu":gpu,"interpretation":"40 synthetic requests, C4, 64 input/32 max output tokens; not production SLO"}
    files={"model.json":inference["model"],"hardware.json":hardware,"config.json":manifest,"result.json":result}
    for name,value in files.items():(r/name).write_text(json.dumps(value,indent=2))
    (r/"report.md").write_text(
        "# Real vLLM inference benchmark\n\n"
        f"{raw['completed']}/{manifest['prompts']} requests completed; {raw['request_throughput']:.3f} requests/s; "
        f"{raw['output_throughput']:.3f} output tokens/s.\n\n"
        f"TTFT P50/P95/P99: {raw['p50_ttft_ms']:.3f}/{raw['p95_ttft_ms']:.3f}/{raw['p99_ttft_ms']:.3f} ms.\n\n"
        "This is the official pinned vLLM 0.10.2 synthetic serving benchmark, with real streamed output. "
        "Tails from 40 requests are descriptive, not a production SLO estimate. GPU samples include client startup. "
        "The earlier incorrect endpoint-type attempt is retained as FAIL_BENCHMARK.\n")
    seal={name:hashlib.sha256((r/name).read_bytes()).hexdigest() for name in [*files,"raw-benchmark.json","gpu-telemetry.csv","report.md"]}
    (r/"bundle_hashes.json").write_text(json.dumps(seal,indent=2));print(json.dumps(result)[:700])
if __name__=="__main__":main()
