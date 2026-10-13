"""Real GPU-container validation; host-only evidence never passes the Docker gate."""
import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit
import urllib.request


def validate_probe_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Probe must target a credential-free loopback HTTP endpoint")
    return url.rstrip("/")


def command(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return {"argv": args, "exit": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"argv": args, "exit": None, "error": type(exc).__name__}


def save(root, result, gpu, api, logs):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    (root / "gpu-info.json").write_text(json.dumps(gpu, indent=2) + "\n")
    (root / "api-response.json").write_text(json.dumps(api, indent=2) + "\n")
    (root / "runtime-log.txt").write_text("\n".join(logs) + "\n")
    (root / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    (root / "validation-report.md").write_text("# GPU Docker runtime validation\n\nStatus: **" + result["status"] + "**\n\n" + result["reason"] + "\n\nHost CUDA/GPU evidence does not prove this Docker image ran. Unobserved container/API values are null.\n")
    return result


def host_probe(output_root, docker_command="docker"):
    host = command(["nvidia-smi", "--query-gpu=name,driver_version,memory.total,utilization.gpu", "--format=csv,noheader"])
    docker = command([docker_command, "info", "--format", "{{json .Runtimes}}"]) if shutil.which(docker_command) else {"argv": [docker_command, "info"], "exit": None, "error": "command_not_found"}
    result = {"status": "SKIPPED", "reason": "No authorized Docker GPU runtime invocation has been performed; use the provided Compose recipe on an authorized NVIDIA Docker host.",
              "checks": {"docker": docker.get("exit") == 0, "container_cuda": None, "vllm": None, "api": None}}
    return save(output_root, result, {"host_gpu": host, "docker_info": docker, "container_gpu": None},
                {"status": "SKIPPED", "response": None}, [json.dumps(host), json.dumps(docker)])


def container_probe(output_root, url, model, timeout=180):
    url = validate_probe_url(url); logs = []
    gpu = command(["nvidia-smi", "--query-gpu=name,driver_version,memory.total,utilization.gpu", "--format=csv,noheader"])
    import torch
    cuda = torch.cuda.is_available()
    checks = {"container_marker": Path("/.dockerenv").exists(), "nvidia_smi": gpu["exit"] == 0, "container_cuda": cuda, "vllm": False, "api": False}
    api = None
    try:
        if not all(checks[k] for k in ("container_marker", "nvidia_smi", "container_cuda")):
            raise RuntimeError("GPU container prerequisites failed")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url + "/health", timeout=3) as r:
                    checks["vllm"] = r.status == 200
                if checks["vllm"]: break
            except Exception: time.sleep(1)
        if not checks["vllm"]: raise RuntimeError("vLLM readiness timeout")
        with urllib.request.urlopen(url + "/v1/models", timeout=5) as response:
            models = json.load(response)
        if model not in [x["id"] for x in models["data"]]: raise RuntimeError("Loaded model identity differs")
        payload = {"model": model, "messages": [{"role": "user", "content": "What is the capital of France? Answer briefly."}], "temperature": 0, "max_tokens": 16}
        request = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response: api = json.load(response)
        checks["api"] = api.get("model") == model and bool(api.get("choices", [{}])[0].get("message", {}).get("content"))
    except Exception as exc: logs.append(type(exc).__name__ + ": " + str(exc))
    passed = all(checks.values())
    result = {"status": "PASS" if passed else "FAIL", "reason": "Actual in-container GPU/API probe" if passed else "Actual probe failed; see runtime log", "checks": checks}
    return save(output_root, result, {"container_gpu": gpu, "torch": torch.__version__, "cuda_available": cuda},
                {"status": result["status"], "response": api}, logs + [json.dumps(gpu)])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["host", "container"])
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default="modelops-qwen3b-qlora")
    args = parser.parse_args()
    result = host_probe(args.output_root) if args.mode == "host" else container_probe(args.output_root, args.url, args.model)
    print(json.dumps(result))
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
