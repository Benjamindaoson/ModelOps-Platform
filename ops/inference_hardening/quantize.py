"""Real local GPTQ/AWQ W4A16 conversion using a frozen private calibration set."""
import argparse,json,os,time,hashlib
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from datasets import Dataset
from llmcompressor import oneshot
from llmcompressor.modifiers.quantization import GPTQModifier
from llmcompressor.modifiers.awq import AWQModifier
from pipelines.training.data_contract import verify_model_bundle,sha256
ROOT=Path(__file__).resolve().parents[2];E=ROOT/"Evidence/inference-hardening"

def main():
    p=argparse.ArgumentParser();p.add_argument("--method",choices=["gptq","awq"],required=True);a=p.parse_args()
    base=ROOT/".tools/assets/qwen3b-base";base_sha=sha256(base/"modelops-files.json");verify_model_bundle(base,base_sha)
    folder=E/"quantization"/a.method;folder.mkdir(parents=True,exist_ok=True)
    receipt=folder/"conversion.json"
    if receipt.exists():
        old=json.loads(receipt.read_text())
        if old["status"]=="PASS":
            verify_model_bundle(folder/"model",old["model_sha"]);print("Hash-verified quantization reused");return
    rows=[json.loads(x) for x in (E/"calibration.jsonl").read_text().splitlines()]
    tokenizer=AutoTokenizer.from_pretrained(base,local_files_only=True)
    processed=[]
    for r in rows:
        messages=r.get("messages")
        if messages is None:messages=[{"role":"user","content":r.get("prompt") or r.get("instruction")},{"role":"assistant","content":r.get("reference") or r.get("response") or r.get("answer")}]
        text=tokenizer.apply_chat_template(messages,tokenize=False)
        processed.append(tokenizer(text,truncation=True,max_length=512,add_special_tokens=False))
    calibration=Dataset.from_list(processed)
    torch.manual_seed(8901);torch.cuda.reset_peak_memory_stats();start=time.perf_counter()
    model=AutoModelForCausalLM.from_pretrained(base,torch_dtype=torch.float16,device_map="auto",local_files_only=True,trust_remote_code=False)
    cls=GPTQModifier if a.method=="gptq" else AWQModifier
    modifier=cls(targets="Linear",scheme="W4A16",ignore=["lm_head"],sequential_targets=["Qwen2DecoderLayer"])
    oneshot(model=model,dataset=calibration,recipe=modifier,max_seq_length=512,num_calibration_samples=len(rows))
    modeldir=folder/"model";model.save_pretrained(modeldir,save_compressed=True);tokenizer.save_pretrained(modeldir)
    files=[]
    for f in sorted(modeldir.iterdir()):
        if f.is_file() and f.name!="modelops-files.json":files.append({"name":f.name,"sha256":sha256(f),"bytes":f.stat().st_size})
    manifest={"repo":"Qwen/Qwen2.5-3B-Instruct","revision":"aa8e72537993ba99e69dfaafa59ed015b17504d1","quantization":a.method,"files":files}
    (modeldir/"modelops-files.json").write_text(json.dumps(manifest,indent=2)+"\n")
    result={"status":"PASS","algorithm":a.method,"precision":"W4A16-G128; lm_head excluded","base_sha":base_sha,"model_sha":sha256(modeldir/"modelops-files.json"),
        "calibration_sha":sha256(E/"calibration.jsonl"),"calibration_samples":len(rows),"max_sequence_length":512,"seed":8901,
        "wall_s":time.perf_counter()-start,"peak_allocated_bytes":torch.cuda.max_memory_allocated(),"model_bytes":sum(f["bytes"] for f in files),
        "weights":[f for f in files if f["name"].endswith(".safetensors")],"torch":torch.__version__,"llmcompressor":"0.6.0","source_sha":sha256(__file__)}
    receipt.write_text(json.dumps(result,indent=2)+"\n");print(json.dumps({k:result[k] for k in ["status","algorithm","wall_s","model_bytes","peak_allocated_bytes"]}))

if __name__=="__main__":main()
