"""Private, source-pinned calibration and expanded heldout data; no public raw text."""
import json,random,hashlib,os
from pathlib import Path
from datasets import Dataset
from pipelines.training.data_contract import validate_manifest
ROOT=Path(__file__).resolve().parents[2];E=ROOT/"Evidence/inference-hardening"

def main():
    os.environ["HF_HOME"]=str(ROOT/".tools/hf-hardening")
    manifest=ROOT/"Evidence/v1/datasets/public/dolly-shortqa-v1/manifest.json"
    expected_manifest="71a383c9cd4a77204ba0d1c65b6fd10966e6c8ba6f98c04d35ca1641e242b687"
    rows,_=validate_manifest(manifest,expected_manifest)
    cal=E/"calibration.jsonl";cal.write_text("".join(json.dumps(r)+"\n" for r in rows))
    source=E/"squad-validation.parquet"; receipt=json.loads(source.with_suffix(".parquet.receipt.json").read_text())
    revision="7b6d24c440a36b6815f21b70d25016731768db1f"
    expected="8c6646d36bd5a95061e076788cf3161d11f6f3e7d625dac7a83bbed0a49f69f7"
    assert receipt["revision"]==revision and receipt["sha256"]==expected
    assert hashlib.sha256(source.read_bytes()).hexdigest()==expected
    ds=Dataset.from_parquet(str(source))
    groups={}
    for r in ds:groups.setdefault(r["title"],[]).append(r)
    rng=random.Random(8801);titles=sorted(groups);rng.shuffle(titles)
    selected=[];round_index=0
    while len(selected)<128:
        for title in titles:
            if len(selected)>=128:break
            if round_index<len(groups[title]):selected.append(groups[title][round_index])
        round_index+=1
    expanded=[{"id":r["id"],"source_id":"squad:"+r["title"],"question":r["question"],"context":r["context"],"answers":r["answers"]["text"]} for r in selected]
    path=E/"expanded-heldout.jsonl";payload="".join(json.dumps(r)+"\n" for r in expanded)
    if path.exists() and path.read_text()!=payload:raise ValueError("Frozen evaluation selection changed")
    path.write_text(payload)
    source_ids={"dolly:"+str(r.get("source_index",r["id"])) for r in rows};assert not source_ids.intersection(r["source_id"] for r in expanded)
    result={"status":"PASS","repo":"rajpurkar/squad","revision":revision,"license":"CC-BY-SA-4.0","url":"https://huggingface.co/datasets/rajpurkar/squad",
        "selection":"Seed8801 round-robin across shuffled validation article titles;128 rows","samples":128,"source_groups":len(set(r["source_id"] for r in expanded)),
        "heldout_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"calibration_sha256":hashlib.sha256(cal.read_bytes()).hexdigest(),
        "calibration_samples":len(rows),"calibration_source_manifest":expected_manifest,"source_record_namespace_overlap_count":0,"source_sha256":expected,"semantic_overlap":"Not asserted; namespaces differ, no shared source records",
        "scope":"Bounded extractive-QA quality comparison, not broad quality certification","raw_text_publication":False}
    (E/"data-manifest.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ["status","revision","samples","source_groups","calibration_samples"]}))

if __name__=="__main__":main()
