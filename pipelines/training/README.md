# Training checkpoint promotion

The upstream `merge-upload` step did not merge adapters; it uploaded the LoRA adapter files as though they were a complete vLLM-loadable model. This module implements a real merge operation:

- **full**: validate and copy a full checkpoint.
- **lora/qlora**: reload the unquantized base model (on CPU), load the PEFT adapter, perform `merge_and_unload(safe_merge=True)`, save weights and tokenizer, then atomically publish the directory.
- **no silent success**: no checkpoint, missing adapter metadata, output name collision, import failure or incomplete model aborts.

CPU RAM requirement may be substantial; for a 7B base, allocate enough system memory before merging. A successful merge must also pass the independent held-out evaluation and quality gate in `pipelines/evaluation/` before routing traffic. Promotion is conditional on real weights, real quality measurements and explicit rollout approval.

```bash
python pipelines/training/merge.py --base /workspace/base-model \
  --trained /workspace/output --output /workspace/merged \
  --method lora --receipt /workspace/eval/merge_receipt.json
```
