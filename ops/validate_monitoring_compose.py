"""Actual Docker Compose monitoring check with explicitly synthetic CPU API input."""
import json, os, secrets, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import httpx, psutil
from ops.run_model_comparison import ROOT, stop_owned, available

class Fixture(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        body={"data":[{"id":"cpu-contract-fixture"}]} if self.path=="/v1/models" else {"status":"ok"}
        encoded=json.dumps(body).encode();self.send_response(200);self.send_header("Content-Length",str(len(encoded)));self.end_headers();self.wfile.write(encoded)
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length","0")))
        self.send_response(200);self.send_header("Content-Type","text/event-stream");self.end_headers()
        for item in [{"choices":[{"delta":{"content":"fixture output"}}]},{"choices":[],"usage":{"completion_tokens":2}}]:
            self.wfile.write(("data: "+json.dumps(item)+"\n\n").encode());self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n");self.wfile.flush()

def main():
    output=ROOT/"Evidence/ci-validation";output.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ);env["GRAFANA_ADMIN_PASSWORD"]=secrets.token_urlsafe(32)
    cmd=["docker","compose","-p","modelops-validation-"+str(os.getpid()),"-f",str(ROOT/"deploy/monitoring/docker-compose.yml")]
    available(19782);available(19780);available(19790);available(19791)
    fixture=ThreadingHTTPServer(("127.0.0.1",19782),Fixture)
    thread=threading.Thread(target=fixture.serve_forever,daemon=True);thread.start()
    log=(output/"monitoring-runtime.log").open("w");proxy=None
    try:
        proxy=subprocess.Popen([sys.executable,"-m","ops.observability.server","--upstream","http://127.0.0.1:19782","--port","19780","--version","cpu-contract-fixture"],
                               cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        owned={"pid":proxy.pid,"create_time":psutil.Process(proxy.pid).create_time()}
        subprocess.run(cmd+["up","-d"],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
        for _ in range(90):
            try:
                if httpx.get("http://127.0.0.1:19791/api/health",timeout=2).status_code==200 and httpx.get("http://127.0.0.1:19790/-/ready",timeout=2).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(2)
        else:raise RuntimeError("Monitoring readiness failed")
        r=httpx.post("http://127.0.0.1:19780/v1/chat/completions",json={"model":"cpu-contract-fixture","messages":[],"stream":True},timeout=10);r.raise_for_status()
        if "fixture output" not in r.text:raise ValueError("Proxy contract failed")
        result=[]
        for _ in range(20):
            result=httpx.get("http://127.0.0.1:19790/api/v1/query",params={"query":"modelops_inference_output_tokens_total"},timeout=5).json()["data"]["result"]
            if result:break
            time.sleep(2)
        if not result or float(result[0]["value"][1])!=2:raise ValueError("Actual Compose scrape failed")
        uid=json.loads((ROOT/"deploy/monitoring/modelops-dashboard.json").read_text())["uid"]
        dash=httpx.get("http://127.0.0.1:19791/api/dashboards/uid/"+uid,auth=("admin",env["GRAFANA_ADMIN_PASSWORD"]),timeout=5);dash.raise_for_status()
        (output/"monitoring-validation.json").write_text(json.dumps({"status":"PASS","scope":"CPU synthetic OpenAI fixture + actual production proxy/Compose Prometheus/Grafana",
          "gpu_inference":"NOT_EXECUTED","dashboard_uid":uid,"scraped_token_count":2,"anonymous_access":False},indent=2)+"\n")
    finally:
        subprocess.run(cmd+["down","-v"],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=120)
        if proxy:stop_owned(proxy,owned,"ops.observability.server")
        fixture.shutdown();fixture.server_close();log.close()

if __name__=="__main__":main()
