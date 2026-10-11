"""Validate VLA-Forge MuJoCo development receipts for ModelOps admission."""
import argparse
import json
import math
import statistics
from pathlib import Path

from pipelines.robotics.adapter import Registry, sha256_file, write


def admit(registry_root, version, condition, protocol_path, receipts_root):
    registry = Registry(registry_root)
    model = registry.resolve(version)
    protocol = json.loads(Path(protocol_path).read_text())
    if protocol["scope"] != "M05-development-only":
        raise ValueError("Only frozen M05 development protocol is admissible")
    expected = {(case["suite"], int(case["task"]), int(case["init"])) for case in protocol["development"]}
    if len(expected) != 8 or any(init in protocol["formal_test_forbidden_init_ids"] for _, _, init in expected):
        raise ValueError("Development plan overlaps M06 or has missing cases")
    rows, illegal, errors = [], 0, []
    for path in sorted(Path(receipts_root).glob(f"{condition}_*.json")):
        row = json.loads(path.read_text())
        key = (row["suite"], int(row["task"]), int(row["init"]))
        if key not in expected or row["condition"] != condition or row.get("checkpoint_sha256") != model["checkpoint_sha256"]:
            errors.append(f"identity mismatch: {path.name}")
            continue
        if row["status"] != "complete" or type(row.get("success")) is not bool:
            errors.append(f"unfinished episode: {path.name}")
            continue
        for role in ("video", "trajectory", "action_trace"):
            item = row.get(role, {})
            file = Path(item.get("path", ""))
            if not file.is_file() or sha256_file(file) != item.get("sha256"):
                errors.append(f"{role} integrity failure: {path.name}")
                break
        else:
            actions = json.loads(Path(row["action_trace"]["path"]).read_text())
            if len(actions) != row["steps"]:
                errors.append(f"step/action mismatch: {path.name}")
                continue
            for action in actions:
                vector = action.get("executed", [])
                if len(vector) != 7 or any(not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > 1.00001 for v in vector):
                    illegal += 1
            rows.append(row)
    actual = {(r["suite"], int(r["task"]), int(r["init"])) for r in rows}
    if actual != expected or len(rows) != len(expected):
        errors.append(f"coverage differs: unique {len(actual)}/{len(expected)}, receipts {len(rows)}/{len(expected)}")
    return {
        "scope": "M05-development",
        "passed": not errors and illegal == 0,
        "checkpoint_sha256": model["checkpoint_sha256"],
        "version": version,
        "training_run_id": model["run_id"],
        "dataset_sha256": model["dataset_sha256"],
        "processor_sha256": model["processor_sha256"],
        "total": len(rows),
        "success": sum(row["success"] for row in rows),
        "illegal_actions": illegal,
        "mean_chunk_ms": statistics.mean(row["chunk_mean_ms"] for row in rows) if rows else None,
        "peak_gpu_allocated_bytes": max((row["gpu_peak_allocated"] for row in rows), default=0),
        "errors": errors,
        "episode_receipt_sha256": {Path(row["video"]["path"]).stem: sha256_file(Path(receipts_root) / f"{condition}_{row['suite']}_t{row['task']:02d}_i{row['init']:02d}.json") for row in rows},
        "boundary": "Eight frozen M05 development initial states only; no M06 test opened or production release claim",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--condition", required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = admit(args.registry, args.version, args.condition, args.protocol, args.receipts)
    write(args.output, result)
    print(json.dumps({key: result[key] for key in ("version", "passed", "success", "total", "illegal_actions", "errors")}, indent=2))
    if not result["passed"]:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
