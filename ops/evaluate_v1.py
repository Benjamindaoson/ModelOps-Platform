"""Real frozen checkpoint evaluation with hash-verified resume, using the existing evaluator."""
from pathlib import Path
import argparse,json,subprocess,sys
from transformers import AutoTokenizer
from ops.gpu_lease import gpu_lease
from pipelines.training.data_contract import sha256,validate_manifest
from pipelines.evaluation.run import sha256_artifact
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--dataset",choices=["broad","shortqa"],default="broad")
    args=parser.parse_args();e=ROOT/"Evidence/v1"
    name="dolly-shortqa-v1" if args.dataset=="shortqa" else "dolly-v1"
    manifest=e/"datasets/public"/name/"manifest.json";train,test=validate_manifest(manifest,sha256(manifest))
    tokenizer=AutoTokenizer.from_pretrained(ROOT/".tools/assets/qwen-base",local_files_only=True)
    folder=e/("evaluation-shortqa" if args.dataset=="shortqa" else "evaluation");folder.mkdir(exist_ok=True)
    for split,rows in [("train",train),("heldout",test)]:
        formatted=[{**row,"split":split,"prompt":tokenizer.apply_chat_template(
            [{"role":"user","content":row["prompt"]}],tokenize=False,add_generation_prompt=True)} for row in rows]
        content="".join(json.dumps(row)+"\n" for row in formatted)
        file=folder/(split+".jsonl")
        if file.exists() and file.read_text()!=content:raise RuntimeError("Frozen evaluation input drift")
        if not file.exists():file.write_text(content)
    records=json.loads((e/("native-qa-training-finished.json" if args.dataset=="shortqa" else "native-training-finished.json")).read_text())
    for job in records["jobs"]:
        candidate=e/"runtime/lab"/job["job_id"]/"artifacts/merged"
        out=folder/(job["method"]+".json")
        if out.exists():
            report=json.loads(out.read_text())
            if (report["artifact_sha256"]!=sha256_artifact(candidate) or
                report["heldout_sha256"]!=sha256(folder/"heldout.jsonl") or
                report.get("generation_success_rate")!=1 or report.get("train_overlap_count")!=0):
                raise RuntimeError("Saved heldout evidence does not verify")
            print("Saved independent evaluation verified",job["method"]);continue
        cmd=[sys.executable,"-m","pipelines.evaluation.run","run","--base-model",str(ROOT/".tools/assets/qwen-base"),
            "--candidate",str(candidate),"--train-data",str(folder/"train.jsonl"),"--heldout",str(folder/"heldout.jsonl"),
            "--min-samples","24","--max-new-tokens","16" if args.dataset=="shortqa" else "64","--output",str(out)]
        with gpu_lease(),(folder/(job["method"]+".log")).open("wb") as log:
            subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=600,check=True)
    return 0
if __name__=="__main__":raise SystemExit(main())
