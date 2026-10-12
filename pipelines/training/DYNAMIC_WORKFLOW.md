# Per-job Dynamic Argo Fine-Tuning

This workflow runs genuine HuggingFace model download, cryptographically checked dataset manifests, independent train/heldout splits, parameterized LLaMA-Factory SFT, PEFT merge, real checkpoint evaluation, fail-closed quality gate, and S3/MLflow publication.

`modelops-finetune-dynamic` is a real Argo WorkflowTemplate installed by the finetune subchart. A submitted workflow remains `Pending` until Kubernetes/Argo reports its observed phase. CPU unit tests validate the contract and do **not** claim trained checkpoints exist.

## Versioned dataset format

```
s3://bucket/path/
  dataset_manifest.json  # SHA-256 digest recorded in Dataset Registry
  train.json             # List of instruction/response examples
  heldout.jsonl          # Independently split examples: id/prompt/reference/split
```

`dataset_manifest.json` must include a `files` map with exact per-file SHA-256 hashes for `train.json` and `heldout.jsonl`. No evaluation file is ever auto-selected as the training set. For HuggingFace dataset sources use `hf://org/dataset@commit` and the same manifest.

Runtime setup: tenant namespace, Argo CRDs, network access to base HuggingFace model revision, `modelops-objectstore` Secret (endpoint/accessKey/secretKey keys), MinIO `models` bucket, MLflow registry endpoint. Use a consistent deployment release; do not trust legacy fixed-config template for dynamic workflows. Default GPU count is set by each job; real GPU training and end-to-end publication must be tested separately before claiming reliability.

Security caution: this first-pass dynamic template depends on upstream LLaMA-Factory image and runtime packages. Lock model/training/runtime image digests and harden pod security before production. Dataset and model content are untrusted; use safetensors and an isolated runner with restricted egress.
