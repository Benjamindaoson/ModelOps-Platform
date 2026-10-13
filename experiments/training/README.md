# Qwen2.5-3B managed QLoRA

Uses the existing ModelOps TrainingJob and Transformers/PEFT worker. The 32-update, batch-two sampler draws with replacement; it is not reported as a complete deterministic epoch. Frozen source-disjoint Dolly short-answer split: 64 train, 24 heldout. All metrics are filled only from real completed GPU receipts. Weights stay private; the base uses the Qwen research license. See docs/evidence/llm-validation for versions, hashes and evidence.
