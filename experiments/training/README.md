# Qwen2.5-3B managed QLoRA

The entrypoint uses the existing ModelOps TrainingJob and Transformers/PEFT GPU worker; it does not bypass job reconciliation or replace robotics Flow Matching.

## Actual completed run

- Model: Qwen/Qwen2.5-3B-Instruct revision aa8e72537993ba99e69dfaafa59ed015b17504d1.
- ModelOps Run: 7859def0-8be7-4931-a099-1193b790e709; MLflow Run: b127f8d1474b414db0025df3a611d5c7; registered version 1 READY.
- Frozen Dolly short-answer split: 64 train / 24 source-disjoint heldout, seed 9101.
- 32 optimizer updates, batch two, with-replacement sampler; not a deterministic full epoch.
- NF4 double quantization, BF16 compute, rank 8, alpha 16, LR 1e-5, sequence 384.
- Training-only 14.084 s; worker total 53.605 s; peak Torch allocation 7.655 GiB.
- Heldout F1 declined 0.763198 → 0.749309; no quality improvement claim.

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
