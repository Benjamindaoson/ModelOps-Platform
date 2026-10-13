"""Pinned SFT data, source hashes and assistant-only action-free supervision."""
from __future__ import annotations
import hashlib
import json
import os
import random
from pathlib import Path

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1048576),b""):h.update(block)
    return h.hexdigest()

def write_json(path, body):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+".tmp")
    temp.write_text(json.dumps(body,indent=2,sort_keys=True))
    os.replace(temp,path)

def normalize(prompt):
    return " ".join(prompt.lower().split())

def validate_manifest(path, expected):
    path=Path(path).resolve()
    if sha256(path)!=expected:raise ValueError("Dataset manifest hash mismatch")
    body=json.loads(path.read_text())
    groups=[]
    for kind in ["train","heldout"]:
        source=(path.parent/body[kind+"_file"]).resolve()
        if not source.is_relative_to(path.parent):raise ValueError("Dataset path escapes owned root")
        if sha256(source)!=body[kind+"_sha256"]:raise ValueError("Dataset row hash mismatch")
        rows=[json.loads(line) for line in source.read_text().splitlines() if line.strip()]
        if any(not isinstance(row.get("prompt"),str) or not row["prompt"].strip()
               or not isinstance(row.get("reference"),str) or not row["reference"].strip()
               for row in rows):raise ValueError("Invalid SFT row")
        if len({row["id"] for row in rows})!=len(rows):raise ValueError("Duplicate source identity")
        groups.append(rows)
    train,test=groups
    if not train or len(test)<20:raise ValueError("Insufficient independent heldout rows")
    if {normalize(r["prompt"]) for r in train}&{normalize(r["prompt"]) for r in test}:
        raise ValueError("Training/heldout prompt overlap")
    if {r["id"] for r in train}&{r["id"] for r in test}:raise ValueError("Source identity overlap")
    return train,test

def encode_sample(tokenizer,row,max_length):
    prefix=tokenizer.apply_chat_template([{"role":"user","content":row["prompt"]}],
                                        tokenize=True,add_generation_prompt=True)
    completion=tokenizer(row["reference"],add_special_tokens=False).input_ids+[tokenizer.eos_token_id]
    if len(prefix)>=max_length-8:raise ValueError("Prompt leaves insufficient assistant supervision")
    completion=completion[:max_length-len(prefix)]
    ids=prefix+completion
    return {"input_ids":ids,"attention_mask":[1]*len(ids),"labels":[-100]*len(prefix)+completion}

def freeze_dolly(source,output,tokenizer,train_count=64,heldout_count=24,seed=1701,max_length=256):
    raw=[json.loads(line) for line in Path(source).read_text().splitlines() if line.strip()]
    order=list(range(len(raw)))
    random.Random(seed).shuffle(order)
    chosen=[];seen=set()
    for index in order:
        row=raw[index]
        prompt=row["instruction"]+("\nContext:\n"+row["context"] if row.get("context") else "")
        key=normalize(prompt)
        if key in seen:continue
        item={"id":f"dolly-{index}","prompt":prompt,"reference":row["response"],
              "category":row.get("category"),"source_index":index}
        try:encode_sample(tokenizer,item,max_length)
        except ValueError:continue
        seen.add(key);chosen.append(item)
        if len(chosen)==train_count+heldout_count:break
    if len(chosen)!=train_count+heldout_count:raise ValueError("Insufficient valid source rows")
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    body={"schema":"modelops.sft-data.v1","selection_seed":seed,
          "source_file_sha256":sha256(source),"license":"cc-by-sa-3.0",
          "source":"https://huggingface.co/datasets/databricks/databricks-dolly-15k"}
    for kind,rows in [("train",chosen[:train_count]),("heldout",chosen[train_count:])]:
        p=output/(kind+".jsonl")
        p.write_text("".join(json.dumps(row)+"\n" for row in rows))
        body[kind+"_file"]=p.name;body[kind+"_sha256"]=sha256(p);body[kind+"_count"]=len(rows)
    write_json(output/"manifest.json",body)
    validate_manifest(output/"manifest.json",sha256(output/"manifest.json"))
    return output/"manifest.json"
