"""Compare identical native and ModelOps-managed SmolVLA update budgets."""
import argparse
import json
from pathlib import Path

from pipelines.robotics.adapter import sha256_file, write

RECIPE_FIELDS = (
    "dataset", "seed", "steps", "precision", "microbatch", "accumulation",
    "optimizer", "lr", "weight_decay", "lora_r", "lora_alpha", "lora_dropout",
    "gradient_checkpointing", "fused", "video_backend",
)


def rows(path):
    result = [json.loads(line) for line in path.read_text().splitlines() if line]
    if [row["step"] for row in result] != list(range(1, len(result) + 1)):
        raise ValueError("Step history is missing or duplicated")
    return result


def compare(native_dir, native_config, managed_dir):
    native_dir, native_config, managed_dir = map(Path, (native_dir, native_config, managed_dir))
    nc = json.loads(native_config.read_text())
    mc = json.loads((managed_dir / "config.json").read_text())
    match = {key: nc.get(key) == mc.get(key) for key in RECIPE_FIELDS}
    if not all(match.values()):
        raise ValueError(f"Unmatched recipes: {match}")
    n = json.loads((native_dir / "result.json").read_text())
    m = json.loads((managed_dir / "artifacts/result.json").read_text())
    nr = rows(native_dir / "steps.jsonl")
    mr = rows(managed_dir / "artifacts/steps.jsonl")
    if len(nr) != len(mr) or n["status"] != "COMPLETED" or m["status"] != "COMPLETED":
        raise ValueError("Both runs must finish the same update budget")
    pause = json.loads((managed_dir / "pause_receipt.json").read_text())
    attempts = json.loads((managed_dir / "job.json").read_text())["attempts"]
    native_weight = Path(n["adapter"]) / "adapter_model.safetensors"
    managed_weight = Path(m["adapter"]) / "adapter_model.safetensors"
    if sha256_file(native_weight) != n["adapter_sha256"] or sha256_file(managed_weight) != m["adapter_sha256"]:
        raise ValueError("Adapter integrity failure")
    fields = ("loss", "gradient_norm", "lr", "update_wall_s", "decode_s", "processor_h2d_s", "forward_s", "backward_s", "optimizer_s")
    differences = {field: max(abs(a[field] - b[field]) for a, b in zip(nr, mr)) for field in fields}
    exposure_match = all(a["indices"] == b["indices"] for a, b in zip(nr, mr))
    pause_wall = pause["state"]["result"]["wall_s"]
    managed_wall = pause_wall + m["wall_s"]
    return {
        "scope": "real RTX3090 same recipe and seed, 20 optimizer updates, one deliberate ModelOps pause/resume",
        "recipe_match": match,
        "sample_indices_exact": exposure_match,
        "adapter_sha256_exact": n["adapter_sha256"] == m["adapter_sha256"],
        "numeric_max_absolute_differences": differences,
        "native": {"run_id": n["run_id"], "wall_s": n["wall_s"], "allocated_peak_bytes": n["allocated_peak"], "adapter_sha256": n["adapter_sha256"]},
        "managed": {"run_id": m["run_id"], "wall_s_including_two_processes": managed_wall, "first_segment_wall_s": pause_wall, "second_segment_wall_s": m["wall_s"], "allocated_peak_bytes": m["allocated_peak"], "attempts": len(attempts), "adapter_sha256": m["adapter_sha256"], "resume_checkpoint_sha256": pause["resume_sha256"]},
        "wall_overhead_s": managed_wall - n["wall_s"],
        "wall_overhead_fraction": managed_wall / n["wall_s"] - 1,
        "provenance": {"native_config": str(native_config), "managed_config": str(managed_dir / "config.json"), "native_steps": str(native_dir / "steps.jsonl"), "managed_steps": str(managed_dir / "artifacts/steps.jsonl")},
        "passed": exposure_match and n["adapter_sha256"] == m["adapter_sha256"] and all(differences[key] == 0 for key in ("loss", "gradient_norm", "lr")) and len(attempts) == 2,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--native-dir", type=Path, required=True)
    p.add_argument("--native-config", type=Path, required=True)
    p.add_argument("--managed-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    x = p.parse_args()
    result = compare(x.native_dir, x.native_config, x.managed_dir)
    write(x.output, result)
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
