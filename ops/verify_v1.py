"""Project-local verification. Optional runtime suites are reported, never called GPU proof."""
from pathlib import Path
import subprocess,os,json,sys,time
ROOT=Path(__file__).resolve().parents[1]
def main():
    e=ROOT/"Evidence/v1";e.mkdir(parents=True,exist_ok=True)
    python=str(ROOT/".venv/bin/python")
    env=os.environ.copy()
    env.update(PATH=str(ROOT/".tools/node-v22.19.0-linux-x64/bin")+":"+str(ROOT/".tools/go/bin")+":"+env["PATH"],
        GOTOOLCHAIN="local",GOMODCACHE=str(ROOT/".tools/gomodcache"),GOCACHE=str(ROOT/".tools/gocache"),
        GOPATH=str(ROOT/".tools/gopath"),GOPROXY="https://goproxy.cn,direct",GOMAXPROCS="2",
        KUBEBUILDER_ASSETS=str(ROOT/"operator/bin/k8s/1.35.0-linux-amd64"),
        NEXT_TELEMETRY_DISABLED="1",MODELOPS_API_URL="http://127.0.0.1:8080",
        MODELOPS_PUBLIC_ORIGIN="http://localhost:3000")
    groups=[("core", [python,"-m","pytest","-q"],ROOT),
      ("data-contract",[python,"-m","pytest","-q","pipelines/training/test_data_contract.py"],ROOT)]
    groups += [(name,[python,"-m","unittest","discover","-s",folder,"-p","test_*.py","-v"],ROOT)
        for name,folder in [("training","pipelines/training"),("evaluation","pipelines/evaluation"),
            ("benchmark","benchmarks/inference"),("ops","ops")]]
    groups += [("model-loader",[python,"-m","pytest","-q","test_loader.py"],ROOT/"images/model-loader")]
    go=str(ROOT/".tools/go/bin/go")
    packages=subprocess.run([go,"list","./..."],cwd=ROOT/"operator",env=env,capture_output=True,text=True,check=True).stdout.splitlines()
    groups += [("operator-envtest",[go,"test","-p","2",*[p for p in packages if not p.endswith("/test/e2e")]],ROOT/"operator"),
        ("console-types",["npm","run","typecheck"],ROOT/"console"),
        ("console-build",["npm","run","build"],ROOT/"console"),
        ("helm",[str(ROOT/".tools/helm/linux-amd64/helm"),"lint","charts/modelops-control",
            "-f","charts/modelops-control/values-ci.yaml","-f","charts/modelops-control/values-v1-contract.yaml"],ROOT)]
    results=[]
    for name,command,cwd in groups:
        start=time.perf_counter()
        with (e/("verify-"+name+".log")).open("w") as log:
            try:r=subprocess.run(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900);rc=r.returncode
            except subprocess.TimeoutExpired:rc=124
        row={"group":name,"command":command,"cwd":str(cwd),"exit":rc,"wall_s":time.perf_counter()-start}
        results.append(row);(e/"verification.json").write_text(json.dumps(results,indent=2));print(name,rc,flush=True)
    (e/"verification.json").write_text(json.dumps({"groups":results,"passed":all(r["exit"]==0 for r in results),
        "excluded_runtime_suite":"operator/test/e2e requires Docker/kind, unavailable; full attempt retained in go-tests-final.log",
        "scope":"software and local runtime checks; GPU receipts are separate"},indent=2))
    return int(any(r["exit"] for r in results))
if __name__=="__main__":raise SystemExit(main())
