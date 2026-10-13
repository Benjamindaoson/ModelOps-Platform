# Phase 4 — PASS (native Linux)

Real vLLM base generation 1, trained candidate generation 2, and rollback base generation 3 each became ready and returned real model output. A separate curl request returned Paris with the correct artifact ID. Native serving is validated; Kubernetes is out of scope and GPU Docker execution remains unvalidated. Full serving package version 2 includes tokenizer/config tree hashing; file artifact version 1 and checkpoint bytes remain unchanged.
