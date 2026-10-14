"""Generate and freeze exact, shared synthetic token inputs; no model output fixtures."""
import json,random,hashlib
from pathlib import Path
from transformers import AutoTokenizer
from .runtime import ROOT,E

def main():
    E.mkdir(exist_ok=True);base=ROOT/".tools/assets/qwen3b-base";tokenizer=AutoTokenizer.from_pretrained(base,local_files_only=True)
    candidates=list(range(300,16000));special=set(tokenizer.all_special_ids);candidates=[x for x in candidates if x not in special]
    data={}
    for label,n,m in [("A",256,64),("B",2048,128),("C",512,512)]:
        rows=[]
        for i in range(96):
            rng=random.Random(8600+i);rows.append([rng.choice(candidates) for _ in range(n)])
        data[label]={"input_tokens":n,"output_tokens":m,"prompts":rows}
    payload=json.dumps(data,separators=(",",":")).encode()
    path=E/"prompts.json"
    if path.exists() and path.read_bytes()!=payload:raise ValueError("Frozen prompt protocol changed")
    path.write_bytes(payload)
    print("Frozen actual token IDs",hashlib.sha256(payload).hexdigest())

if __name__=="__main__":main()
