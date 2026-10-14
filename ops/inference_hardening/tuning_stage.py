"""Bounded one-factor configuration experiments; same frozen B workload, C16, three repeats."""
import asyncio,json,time,traceback
from pathlib import Path
from .runtime import ROOT,E,Server
from .contracts import digest,resume_valid
from .resume import valid_receipt
from .benchmark import measure
from .quality import evaluate
def main():
    folder=E/"tuning";folder.mkdir(exist_ok=True);sp=folder/"progress.json"
    state=json.loads(sp.read_text()) if sp.exists() else {"trials":[],"failures":[]}
    source=json.loads((E/"engine-progress.json").read_text())
    data=json.loads((E/"prompts.json").read_text())["B"]
    baseline=[r for r in source["trials"] if r["workload"]=="B" and r["concurrency"]==16 and r["status"]=="PASS"]
    variants={"batch4096":{"batch_tokens":4096},"seq32":{"max_sequences":32},"memory60":{"memory_fraction":.6}}
    for engine in ["vllm","sglang"]:
        refs=[r for r in baseline if r["engine"]==engine]
        if len(refs)!=3:state["failures"].append({"engine":engine,"error":"Three verified reference points unavailable"});continue
        if engine=="sglang" and not state.get("baseline_quality",{}).get("status")=="PASS":
            with Server({**refs[0]["config"],"label":"sglang-quality-baseline"}) as server:
                state["baseline_quality"]=asyncio.run(evaluate(server,folder/"sglang-quality"))
            sp.write_text(json.dumps(state,indent=2))
        for variant,change in variants.items():
            cfg={**refs[0]["config"],**change,"label":engine+"-tuning-"+variant}
            todo=[]
            for rep in range(3):
                prior=next((r for r in reversed(state["trials"]) if r["engine"]==engine and r["variant"]==variant and r["repeat"]==rep and r["status"]=="PASS"),None)
                if prior and valid_receipt(prior,Path(prior["path"]),refs[rep]["source_sha"],refs[rep]["protocol_sha"]):continue
                todo.append(rep)
            if not todo:continue
            try:
                with Server(cfg) as server:
                    for rep in todo:
                        ref=next(r for r in refs if r["repeat"]==rep)
                        target=folder/f"{engine}-{variant}-r{rep}"
                        if target.exists():target=target.with_name(target.name+"-retry-"+str(time.time_ns()))
                        rec=asyncio.run(measure(server,data["prompts"][rep*32:(rep+1)*32],128,16,8700+rep,target,ref["protocol_sha"],ref["source_sha"]))
                        state["trials"].append({"engine":engine,"variant":variant,"repeat":rep,"path":str(target),"reference":ref["path"],**rec})
                        sp.write_text(json.dumps(state,indent=2));print("TUNING",engine,variant,rep,rec["status"],flush=True)
            except Exception as exc:
                state["failures"].append({"engine":engine,"variant":variant,"error":str(exc)});(folder/(engine+"-"+variant+"-failure.log")).write_text(traceback.format_exc())
            sp.write_text(json.dumps(state,indent=2))
    state["status"]="PASS" if len({(r["engine"],r["variant"],r["repeat"]) for r in state["trials"] if r["status"]=="PASS"})==18 else "FAIL"
    state["scope"]="Native framework knobs; actual output lengths checked. Quality certification is separate."
    sp.write_text(json.dumps(state,indent=2))
if __name__=="__main__":main()
