"""Run the existing browser flow against an isolated real development API."""
import json, os, secrets, socket, subprocess, time
from pathlib import Path
from datetime import datetime, timedelta, timezone
import httpx, jwt, psutil
from ops.run_model_comparison import stop_owned, available, ROOT, E

def main():
    folder=E/"console";folder.mkdir(exist_ok=True)
    env=dict(os.environ);env.update(PATH=str(ROOT/".tools/node-v22.19.0-linux-x64/bin")+os.pathsep+env.get("PATH",""),
        NEXT_TELEMETRY_DISABLED="1",MODELOPS_API_URL="http://127.0.0.1:8080",MODELOPS_PUBLIC_ORIGIN="http://localhost:3000",
        PLAYWRIGHT_BROWSERS_PATH=str(ROOT/".tools/playwright-browsers"),
        LD_LIBRARY_PATH=str(ROOT/".tools/browser-libs/root/usr/lib/x86_64-linux-gnu"))
    results={}
    for name,args in [("typecheck",["npm","run","typecheck"]),("build",["npm","run","build"])]:
        with (folder/(name+".log")).open("w") as log:
            result=subprocess.run(args,cwd=ROOT/"console",env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        results[name]=result.returncode
        if result.returncode:raise RuntimeError(name+" failed")
    available(8080);available(3000)
    secret=secrets.token_urlsafe(48)
    env.update(MODELOPS_ENV="development",MODELOPS_AUTH_MODE="dev",MODELOPS_RUNTIME="disabled",
               MODELOPS_JWT_SECRET=secret,MODELOPS_DATABASE_URL="sqlite:///"+str(folder/("runtime-"+str(int(time.time()))+".sqlite")))
    now=datetime.now(timezone.utc)
    token=jwt.encode({"iss":"modelops-local","aud":"modelops-dev","sub":"browser-validation","tenant":"browser","role":"admin",
                     "iat":now,"exp":now+timedelta(minutes=30)},secret,algorithm="HS256")
    api=None;ui=None
    try:
        api_log=(folder/"api.log").open("ab")
        api=subprocess.Popen([str(ROOT/".venv/bin/python"),"-m","uvicorn","modelops.main:app","--host","127.0.0.1","--port","8080"],
                            cwd=ROOT/"control-plane",env=env,stdout=api_log,stderr=subprocess.STDOUT,start_new_session=True)
        apiown={"pid":api.pid,"create_time":psutil.Process(api.pid).create_time()}
        ui_log=(folder/"next.log").open("ab")
        ui=subprocess.Popen(["npm","run","start","--","--hostname","127.0.0.1"],cwd=ROOT/"console",env=env,stdout=ui_log,
                             stderr=subprocess.STDOUT,start_new_session=True)
        uiown={"pid":ui.pid,"create_time":psutil.Process(ui.pid).create_time()}
        for _ in range(100):
            if api.poll() is not None or ui.poll() is not None:raise RuntimeError("Owned frontend/API exited")
            try:
                if httpx.get("http://127.0.0.1:8080/readyz").status_code==200 and httpx.get("http://localhost:3000").status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(1)
        else:raise RuntimeError("Frontend readiness failed")
        env["MODELOPS_E2E_TOKEN"]=token
        with (folder/"e2e.log").open("w") as log:
            r=subprocess.run(["npm","run","test:e2e"],cwd=ROOT/"console",env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
        results["e2e"]=r.returncode
        if r.returncode:raise RuntimeError("Actual browser flow failed")
        (folder/"validation.json").write_text(json.dumps({"status":"PASS","commands":results,
            "scope":"Real Next.js production build + isolated FastAPI metadata API; not GPU deployment","auth":"Ephemeral identity only in child process environment"},indent=2)+"\n")
        print("Console typecheck/build/browser PASS",flush=True)
    finally:
        if ui:stop_owned(ui,uiown,"npm")
        if api:stop_owned(api,apiown,"uvicorn")

if __name__=="__main__":main()
