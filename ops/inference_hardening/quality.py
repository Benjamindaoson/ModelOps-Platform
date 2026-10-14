"""Private actual greedy QA outputs; shared existing token-F1 scoring, not a business quality claim."""
import asyncio,json,statistics,time
from pathlib import Path
import httpx
from pipelines.evaluation.run import score
from pipelines.training.data_contract import validate_manifest
from .runtime import ROOT,E
from .contracts import digest

def quality_rows():
    source=[json.loads(s) for s in (E/"expanded-heldout.jsonl").read_text().splitlines()]
    rows=[{"id":r["id"],"group":"squad128","prompt":"Answer the question using only the context. Return the shortest exact answer, without explanation.\nContext: "+r["context"]+"\nQuestion: "+r["question"],"references":r["answers"]} for r in source]
    old=json.loads((ROOT/"Evidence/llm-production-validation/runtime/lab/7859def0-8be7-4931-a099-1193b790e709/config.json").read_text())
    _,heldout=validate_manifest(old["dataset_manifest"],old["dataset_sha256"])
    rows += [{"id":r["id"],"group":"dolly24","prompt":r["prompt"],"references":[r["reference"]]} for r in heldout]
    return rows

async def evaluate(server,folder):
    folder.mkdir(parents=True,exist_ok=True);path=folder/"outputs.jsonl";spec={"model_sha":server.config["model_sha"],"data_sha":digest(E/"expanded-heldout.jsonl"),"calibration_sha":digest(E/"calibration.jsonl"),"source_sha":digest(Path(__file__)),"temperature":0,"max_new_tokens":64}
    receipt=folder/"quality.json"
    if receipt.exists():
        old=json.loads(receipt.read_text())
        if old.get("spec")==spec and old.get("status")=="PASS" and old.get("raw_sha")==digest(path):return old
    rows=[];sem=asyncio.Semaphore(4)
    async with httpx.AsyncClient(timeout=180) as client:
        async def one(row):
            async with sem:
                start=time.perf_counter()
                try:
                    r=await client.post(server.url+"/v1/chat/completions",json={"model":server.config["name"],"messages":[{"role":"user","content":row["prompt"]}],"temperature":0,"max_tokens":64,"seed":8802})
                    r.raise_for_status();result=r.json();text=result["choices"][0]["message"]["content"]
                    values=[score(ref,text) for ref in row["references"]]
                    return {**row,"output":text,"em":max(x[0] for x in values),"f1":max(x[1] for x in values),"usage":result.get("usage"),"wall_s":time.perf_counter()-start,"error":None}
                except Exception as ex:return {**row,"error":type(ex).__name__+": "+str(ex),"wall_s":time.perf_counter()-start}
        with path.open("w") as log:
            for done in asyncio.as_completed([one(r) for r in quality_rows()]):
                row=await done;rows.append(row);log.write(json.dumps(row)+"\n");log.flush()
    groups={}
    for group in ("squad128","dolly24"):
        selected=[r for r in rows if r["group"]==group];good=[r for r in selected if not r["error"]]
        groups[group]={"samples":len(selected),"errors":len(selected)-len(good),"token_f1":statistics.mean(r["f1"] for r in good) if good else None,"exact_match":statistics.mean(r["em"] for r in good) if good else None}
    result={"status":"PASS" if not any(r["error"] for r in rows) else "FAIL","spec":spec,"groups":groups,"raw_sha":digest(path),"scope":"Existing normalized token-overlap scoring; multi-reference max. Bounded QA, not semantic quality or production SLO."}
    receipt.write_text(json.dumps(result,indent=2)+"\n");return result
