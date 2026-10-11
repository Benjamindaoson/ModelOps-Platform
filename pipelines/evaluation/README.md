# Independent model evaluation and promotion

This directory provides a **fail-closed** evaluation for real fine-tune-to-serve deployments. The `run` command uses locally available Transformers checkpoints (not the *old* gateway model). The `gate` command then recomputes hashes and rejects weak or missing evidence.

Example (after real LoRA/QLoRA merge on the GPU node):

```bash
python pipelines/evaluation/run.py run \
  --base-model /workspace/base-model --candidate /workspace/merged \
  --train-data /workspace/data/train.json \
  --heldout /workspace/data/heldout.jsonl \
  --output /workspace/eval/results.json --min-samples 20
python pipelines/evaluation/run.py gate \
  --candidate /workspace/merged \
  --train-data /workspace/data/train.json \
  --heldout /workspace/data/heldout.jsonl \
  --report /workspace/eval/results.json --approval /workspace/eval/APPROVED.json \
  --min-samples 20 --min-f1 0.55 --min-delta -0.02
```

Holdout JSONL records require `id`, `prompt`, `reference`, `split: heldout`. The train and heldout prompts must not overlap. Prompts/predictions are omitted from persisted reports. Token-F1/exact-match are **lexical** metrics and must not be mislabeled semantic faithfulness. They are only appropriate for tasks with predictable target strings; extend for structured SQL/function-calling task metrics when appropriate.

The test harness injects fake predictors **only** in isolated offline unit tests. Neither production CLI accepts fake results or a `--dry-run` PASS mode.

Limitations: exact prompt hashing cannot detect semantic train/validation contamination; additional dedup checks are required for sensitive deployments. One test dataset is not evidence of general-world model quality. The gate checks integrity and internally coherent metrics, not an adversarially signed attestation. In production, restrict who can write reports and evaluate with an independent service account.
