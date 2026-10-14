# Controlled64-update QLoRA and exact resume

Frozen base/data/seed9102/effective batch4/rank8/alpha16/LR1e-5/max length384; BF16 compute, NF4 double quantization. Gradient checkpointing is the only efficiency factor. A third run intentionally pauses at17 and resumes to64. Sampling is with replacement, not an epoch claim.

|Condition|Steps|Input tokens/s|Mean step s|Torch peak GiB|Training wall s|Final loss|QA128 F1|Dolly24 F1|Gate|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
|checkpoint|64|828.21|0.8621|3.729|55.671|1.398866|0.811999|0.747255|PASS|
|no-checkpoint|64|1328.95|0.5372|7.686|34.891|1.398866|0.811999|0.746141|PASS|
|resume|64|1347.58|0.5298|7.694|25.281|1.398866|0.811999|0.741573|PASS|

Resume audit: {"max_abs_error": 0.0, "max_loss_error": 0.0, "same_keys": true, "sample_sequence_equal": true, "status": "PASS"}

All three merged checkpoint and adapter SHA values match. Minor Dolly24 inference-score differences were observed despite identical checkpoint bytes; cause was not independently isolated. Do not present these differences as learning improvement. Expanded128 F1 is slightly below base, within the predeclared engineering threshold.

Checkpointing saves memory but reduces observed tokens/s. Resume training_wall_s is only the resumed segment; full costs include the saved17-step prefix, two loads and export. Step logs reconstruct all64 updates. LR is logged after scheduler.step (next-step LR), so final logged LR0 is not the LR used for the final optimizer update.

Run/MLflow/model/evaluation IDs, immutable SHA values and private output paths: [training_optimization.json](../../docs/evidence/inference-hardening/training_optimization.json). Required Registry revision and Unix IPC path failures were fixed and retained; completed GPU training was never repeated.
