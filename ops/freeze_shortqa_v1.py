"""One bounded, preregistered short-answer protocol; original negative runs retained."""
from pathlib import Path
import random,json
from transformers import AutoTokenizer
from pipelines.training.data_contract import encode_sample,normalize,write_json,sha256,validate_manifest
r=Path(__file__).resolve().parents[1]
source=r/".tools/assets/dolly/databricks-dolly-15k.jsonl"
tokenizer=AutoTokenizer.from_pretrained(r/".tools/assets/qwen-base",local_files_only=True)
raw=[json.loads(line) for line in source.read_text().splitlines() if line.strip()]
order=list(range(len(raw)));random.Random(1702).shuffle(order)
selected=[];seen=set()
for index in order:
    row=raw[index]
    if row.get("category")!="closed_qa":continue
    answer=row["response"]
    if not 1<=len(tokenizer(answer,add_special_tokens=False).input_ids)<=12:continue
    original=row["instruction"]+("\nContext:\n"+row["context"] if row.get("context") else "")
    prompt="Answer with one short phrase. Return only the answer, with no explanation.\n"+original
    if normalize(original) in seen:continue
    item={"id":f"dolly-{index}","prompt":prompt,"reference":answer,"source_index":index,"category":"closed_qa"}
    try:encode_sample(tokenizer,item,256)
    except ValueError:continue
    selected.append(item);seen.add(normalize(original))
    if len(selected)==88:break
if len(selected)!=88:raise ValueError("Insufficient preregistered eligible QA rows")
directory=r/"Evidence/v1/datasets/public/dolly-shortqa-v1";directory.mkdir(parents=True,exist_ok=True)
body={"schema":"modelops.sft-data.v1","source_file_sha256":sha256(source),
      "dataset_revision":"bdd27f4d94b9c1f951818a7da7fd7aeea5dbff1a","license":"cc-by-sa-3.0",
      "selection_seed":1702,"eligibility":"closed_qa; original reference <=12 tokenizer tokens; prompt fits256",
      "budget":"one LoRA run, 32 updates, seed9101; no seed search",
      "scope":"bounded lifecycle validation, not generalization or production business-quality evidence"}
for kind,rows in [("train",selected[:64]),("heldout",selected[64:])]:
    p=directory/(kind+".jsonl");p.write_text("".join(json.dumps(x)+"\n" for x in rows))
    body[kind+"_file"]=p.name;body[kind+"_sha256"]=sha256(p);body[kind+"_count"]=len(rows)
write_json(directory/"manifest.json",body)
validate_manifest(directory/"manifest.json",sha256(directory/"manifest.json"))
print("SHORTQA_FROZEN",sha256(directory/"manifest.json"))
