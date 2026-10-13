"""Real bounded Transformers/PEFT GPU SFT worker; JSON logs are never simulated."""
from __future__ import annotations
import argparse
import fcntl
import json
import math
import os
import random
import signal
import subprocess
import time
from pathlib import Path
from .data_contract import sha256, validate_manifest, encode_sample, write_json

_STOP=False
def stop(signum,frame):
    global _STOP
    _STOP=True

def train(config,resume=False):
    import torch
    import numpy as np
    from transformers import AutoModelForCausalLM,AutoTokenizer,BitsAndBytesConfig
    from peft import LoraConfig,TaskType,get_peft_model,prepare_model_for_kbit_training,PeftModel
    output=Path(config["output"]).resolve()
    output.mkdir(parents=True,exist_ok=True)
    if not torch.cuda.is_available():raise RuntimeError("A real CUDA GPU is required")
    if sha256(Path(config["base_model"])/"model.safetensors")!=config["base_sha256"]:
        raise ValueError("Frozen base checkpoint changed")
    rows,_=validate_manifest(config["dataset_manifest"],config["dataset_sha256"])
    seed=config["seed"]
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
    torch.backends.cuda.matmul.allow_tf32=False
    start=time.perf_counter()
    dtype=torch.bfloat16
    tokenizer=AutoTokenizer.from_pretrained(config["base_model"],local_files_only=True,trust_remote_code=False)
    encoded=[encode_sample(tokenizer,row,config["max_seq_length"]) for row in rows]
    kwargs={"local_files_only":True,"trust_remote_code":False,"use_safetensors":True,
            "torch_dtype":dtype,"attn_implementation":"sdpa"}
    quantized=config["method"]=="qlora"
    if quantized:
        kwargs.update(device_map={"":0},quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,bnb_4bit_quant_type="nf4",bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=dtype))
    model=AutoModelForCausalLM.from_pretrained(config["base_model"],**kwargs)
    if quantized:model=prepare_model_for_kbit_training(model,use_gradient_checkpointing=False)
    else:model=model.to("cuda")
    model=get_peft_model(model,LoraConfig(task_type=TaskType.CAUSAL_LM,r=config["lora_rank"],
        lora_alpha=config["lora_alpha"],lora_dropout=0.0,
        target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"]))
    model.config.use_cache=False
    parameters={name:p for name,p in model.named_parameters() if p.requires_grad}
    initial={name:p.detach().cpu().clone() for name,p in parameters.items()}
    optimizer=torch.optim.AdamW(parameters.values(),lr=config["lr"],weight_decay=0.01)
    scheduler=torch.optim.lr_scheduler.LambdaLR(optimizer,lambda step:max(0.0,1-step/config["steps"]))
    rng=random.Random(seed)
    step=0
    if resume:
        saved=torch.load(output/"resume.pt",map_location="cpu",weights_only=False)
        if saved["run_id"]!=config["run_id"] or saved["dataset_sha256"]!=config["dataset_sha256"]:
            raise ValueError("Resume identity mismatch")
        # Restore the active default adapter, not a second trainable adapter.
        from peft import set_peft_model_state_dict
        from safetensors.torch import load_file
        set_peft_model_state_dict(model,load_file(str(output/"adapter-latest/adapter_model.safetensors")))
        optimizer.load_state_dict(saved["optimizer"]);scheduler.load_state_dict(saved["scheduler"])
        rng.setstate(saved["sampler_rng"]);random.setstate(saved["python_rng"])
        np.random.set_state(saved["numpy_rng"]);torch.set_rng_state(saved["torch_rng"])
        torch.cuda.set_rng_state_all(saved["cuda_rng"]);step=saved["step"]
    model.train()
    model_load_s=time.perf_counter()-start
    train_start=time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    pad=tokenizer.pad_token_id or tokenizer.eos_token_id
    log_path=output/"steps.jsonl"
    with log_path.open("a") as log:
        while step<config["steps"]:
            tick=time.perf_counter()
            indices=[rng.randrange(len(encoded)) for _ in range(config["batch_size"])]
            samples=[encoded[i] for i in indices];length=max(len(s["input_ids"]) for s in samples)
            batch={key:torch.tensor([s[key]+([pad] if key=="input_ids" else [0] if key=="attention_mask" else [-100])*(length-len(s[key])) for s in samples],device="cuda")
                   for key in ["input_ids","attention_mask","labels"]}
            optimizer.zero_grad(set_to_none=True)
            torch.cuda.synchronize();fwd=time.perf_counter()
            loss=model(**batch).loss
            torch.cuda.synchronize();fwd_s=time.perf_counter()-fwd
            if not torch.isfinite(loss):raise RuntimeError("Nonfinite training loss")
            backward=time.perf_counter();loss.backward();torch.cuda.synchronize()
            bwd_s=time.perf_counter()-backward
            norm=torch.nn.utils.clip_grad_norm_(parameters.values(),1.0)
            if not torch.isfinite(norm):raise RuntimeError("Nonfinite gradients")
            opt=time.perf_counter();optimizer.step();scheduler.step();torch.cuda.synchronize()
            opt_s=time.perf_counter()-opt
            step+=1
            event={"run_id":config["run_id"],"step":step,"loss":float(loss.detach()),
                   "gradient_norm":float(norm),"lr":scheduler.get_last_lr()[0],
                   "sample_ids":[rows[i]["id"] for i in indices],
                   "samples":len(indices),"forward_s":fwd_s,"backward_s":bwd_s,
                   "optimizer_s":opt_s,"wall_s":time.perf_counter()-tick,
                   "precision":"bf16","gpu_allocated_bytes":torch.cuda.max_memory_allocated(),
                   "gpu_reserved_bytes":torch.cuda.max_memory_reserved()}
            log.write(json.dumps(event)+"\n");log.flush()
            write_json(output/"progress.json",event)
            if _STOP:break
    adapter=output/"adapter-latest";model.save_pretrained(adapter,safe_serialization=True)
    tokenizer.save_pretrained(adapter)
    torch.save({"run_id":config["run_id"],"dataset_sha256":config["dataset_sha256"],"step":step,
                "optimizer":optimizer.state_dict(),"scheduler":scheduler.state_dict(),
                "sampler_rng":rng.getstate(),"python_rng":random.getstate(),
                "numpy_rng":np.random.get_state(),"torch_rng":torch.get_rng_state(),
                "cuda_rng":torch.cuda.get_rng_state_all()},output/"resume.pt")
    change=max(float((p.detach().cpu()-initial[name]).abs().max()) for name,p in parameters.items())
    identity={"run_id":config["run_id"],"method":config["method"],"steps":step,
              "base_sha256":config["base_sha256"],"dataset_sha256":config["dataset_sha256"],
              "model_load_s":model_load_s,"training_wall_s":time.perf_counter()-train_start,
              "trainable_parameters":sum(p.numel() for p in parameters.values()),
              "parameter_delta_linf":change,"adapter":str(adapter),
              "adapter_sha256":sha256(adapter/"adapter_model.safetensors"),
              "resume_sha256":sha256(output/"resume.pt"),"gpu":torch.cuda.get_device_name(),
              "gpu_peak_allocated_bytes":torch.cuda.max_memory_allocated(),
              "source_sha256":sha256(__file__),"torch":torch.__version__}
    if _STOP and step<config["steps"]:
        write_json(output/"result.json",{**identity,"status":"PAUSED"})
        return
    if change<=0:raise RuntimeError("No parameter update measured")
    # Export QLoRA against the unquantized frozen base. Serving evaluates this
    # exact export; equality to the quantized training forward is not claimed.
    del model,optimizer,scheduler,parameters
    torch.cuda.empty_cache()
    base=AutoModelForCausalLM.from_pretrained(config["base_model"],local_files_only=True,
                                            torch_dtype=dtype,trust_remote_code=False,use_safetensors=True)
    merged=PeftModel.from_pretrained(base,str(adapter)).merge_and_unload(safe_merge=True)
    directory=output/"merged"
    merged.save_pretrained(directory,safe_serialization=True);tokenizer.save_pretrained(directory)
    checkpoint=directory/"model.safetensors"
    if not checkpoint.is_file():raise RuntimeError("Expected single-file 0.5B checkpoint export")
    identity.update(checkpoint=str(checkpoint),checkpoint_sha256=sha256(checkpoint),
                    status="COMPLETED",wall_s=time.perf_counter()-start)
    write_json(output/"result.json",identity)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config",required=True);p.add_argument("--resume",action="store_true")
    args=p.parse_args();config=json.loads(Path(args.config).read_text())
    output=Path(config["output"]);output.mkdir(parents=True,exist_ok=True)
    signal.signal(signal.SIGTERM,stop)
    from ops.gpu_lease import gpu_lease
    try:
        with gpu_lease():train(config,args.resume)
    except Exception as exc:
        write_json(output/"result.json",{"run_id":config["run_id"],"status":"FAILED",
                                         "reason":type(exc).__name__+": "+str(exc)})
        raise

if __name__=="__main__":main()
