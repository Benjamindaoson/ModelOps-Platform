"""CPU-only contracts for real inference experiments and hash-bound resumption."""
import hashlib,math
from pathlib import Path

def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(2**20),b""):h.update(block)
    return h.hexdigest()

def launch_args(c):
    engine=c["engine"]
    if engine not in ("vllm","sglang"):raise ValueError("Unsupported real serving engine")
    memory=c.get("memory_fraction",.7)
    if not isinstance(memory,(float,int)) or not .1<=memory<=.9:raise ValueError("Unsafe memory budget")
    context=c.get("max_context",4096);seqs=c.get("max_sequences",64);tokens=c.get("batch_tokens",2048)
    if not 512<=context<=16384 or not 1<=seqs<=128 or not 512<=tokens<=16384:raise ValueError("Invalid context/batching budget")
    model=str(Path(c["model"]).resolve());name=c.get("name","modelops-frozen");port=str(c.get("port",19801))
    if engine=="vllm":
        args=["-m","vllm.entrypoints.openai.api_server","--model",model,"--served-model-name",name,"--host","127.0.0.1","--port",port,
              "--dtype","half","--gpu-memory-utilization",str(memory),"--max-model-len",str(context),"--max-num-seqs",str(seqs),
              "--max-num-batched-tokens",str(tokens),"--enable-chunked-prefill"]
        args+=["--enable-prefix-caching" if c.get("prefix_cache") else "--no-enable-prefix-caching"]
    else:
        args=["-m","sglang.launch_server","--model-path",model,"--served-model-name",name,"--host","127.0.0.1","--port",port,
              "--dtype","float16","--mem-fraction-static",str(memory),"--context-length",str(context),"--max-running-requests",str(seqs),
              "--chunked-prefill-size",str(tokens)]
        if not c.get("prefix_cache"):args+=["--disable-radix-cache"]
        if c.get("attention_backend"):args+=["--attention-backend",c["attention_backend"]]
        if c.get("sampling_backend"):args+=["--sampling-backend",c["sampling_backend"]]
    if c.get("quantization"):args+=["--quantization",c["quantization"]]
    return args

def trial_valid(row):
    try:
        return (row["status"]=="PASS" and row["requests"]>=32 and row["errors"]==0 and row["gpu_samples"]>0
                and row["output_tokens"]==row["requests"]*row["expected_output_tokens"])
    except (KeyError,TypeError):return False

def resume_valid(receipt,raw,source_sha,protocol_sha):
    try:
        return receipt["status"]=="PASS" and receipt["source_sha"]==source_sha and receipt["protocol_sha"]==protocol_sha and receipt["raw_sha"]==digest(raw)
    except (KeyError,OSError,TypeError):return False
