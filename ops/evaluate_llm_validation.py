"""Reuse the existing independent heldout evaluator for the true 3B merged checkpoint."""
from pathlib import Path
import json,subprocess,sys
from transformers import AutoTokenizer
from ops.gpu_lease import gpu_lease
from pipelines.training.data_contract import sha256,validate_manifest
from pipelines.evaluation.run import sha256_artifact
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/"Evidence/llm-production-validation"
def main():
    record=json.loads((E/"training-finished.json").read_text())
    base=ROOT/".tools/assets/qwen3b-base"
    candidate=Path(record["result"]["checkpoint"]).parent
    folder=E/"evaluation";folder.mkdir(exist_ok=True)
    manifest=ROOT/"Evidence/v1/datasets/public/dolly-shortqa-v1/manifest.json"
    train,test=validate_manifest(manifest,sha256(manifest))
    tokenizer=AutoTokenizer.from_pretrained(base,local_files_only=True,trust_remote_code=False)
    for split,rows in (("train",train),("heldout",test)):
        body=[{**r,"split":split,"prompt":tokenizer.apply_chat_template([{"role":"user","content":r["prompt"]}],tokenize=False,add_generation_prompt=True)} for r in rows]
        text="".join(json.dumps(r)+"\n" for r in body)
        p=folder/(split+".jsonl")
        if p.exists() and p.read_text()!=text:raise ValueError("Frozen evaluation input drift")
        p.write_text(text)
    out=folder/"evaluation.json"
    if out.exists():
        x=json.loads(out.read_text())
        if x["artifact_sha256"]!=sha256_artifact(candidate) or x["heldout_sha256"]!=sha256(folder/"heldout.jsonl"):
            raise ValueError("Saved independent evaluator identity drift")
        print("Saved real independent evaluation verified");return
    cmd=[sys.executable,"-m","pipelines.evaluation.run","run","--base-model",str(base),"--candidate",str(candidate),
         "--train-data",str(folder/"train.jsonl"),"--heldout",str(folder/"heldout.jsonl"),"--min-samples","24",
         "--max-new-tokens","16","--output",str(out)]
    with gpu_lease(),(folder/"evaluation.log").open("wb") as log:
        subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=900,check=True)
    print("REAL_3B_INDEPENDENT_EVALUATION_COMPLETE",flush=True)
if __name__=="__main__":main()
