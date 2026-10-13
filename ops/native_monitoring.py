"""Start official native CPU monitoring services when this container has no Docker host."""
import argparse
import json
import os
import secrets
import socket
import subprocess
import time
from pathlib import Path
import httpx
import psutil

ROOT=Path(__file__).resolve().parents[1]
E=ROOT/"Evidence/llm-platform-finalization/monitoring"


def ready(url):
    try:return httpx.get(url,timeout=2).status_code==200
    except httpx.HTTPError:return False


def launch(name,argv,env,url,records):
    previous=records.get(name)
    if previous:
        try:
            p=psutil.Process(previous["pid"])
            if p.create_time()==previous["create_time"] and ready(url):return previous
        except psutil.Error:pass
        if ready(url):raise RuntimeError("Unexpected existing monitoring service; do not adopt")
    port=int(url.split(":")[2].split("/")[0])
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);probe.bind(("127.0.0.1",port))
    output=(E/(name+".log")).open("ab")
    p=subprocess.Popen(argv,cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
    row={"pid":p.pid,"create_time":psutil.Process(p.pid).create_time(),"argv":argv,"url":url,"scope":"Native CPU service, not Docker"}
    records[name]=row
    (E/"processes.json").write_text(json.dumps(records,indent=2)+"\n")
    for _ in range(120):
        if p.poll() is not None:raise RuntimeError(name+" exited before readiness")
        if ready(url):return row
        time.sleep(1)
    raise RuntimeError(name+" readiness timeout")


def main():
    E.mkdir(parents=True,exist_ok=True)
    record=E/"processes.json"
    records=json.loads(record.read_text()) if record.exists() else {}
    env={k:v for k,v in os.environ.items() if not any(w in k.upper() for w in ("TOKEN","PASSWORD","SECRET","API_KEY","PRIVATE_KEY"))}
    prom=ROOT/".tools/monitoring/prometheus-3.15.0.linux-amd64/prometheus"
    if not prom.exists():raise RuntimeError("Hash-verified Prometheus binary missing")
    launch("prometheus",[str(prom),"--config.file="+str(ROOT/"deploy/monitoring/prometheus.yml"),
           "--storage.tsdb.path="+str(E/"prometheus-data"),"--storage.tsdb.retention.time=7d","--web.listen-address=127.0.0.1:19790"],env,
           "http://127.0.0.1:19790/-/ready",records)
    homes=[p for p in (ROOT/".tools/monitoring").iterdir() if p.is_dir() and (p/"bin/grafana").is_file()]
    if not homes:
        print(json.dumps({"prometheus":"READY","grafana":"WAITING_OFFICIAL_BINARY"}));return
    home=homes[0]
    provision=E/"provisioning"
    (provision/"datasources").mkdir(parents=True,exist_ok=True)
    (provision/"dashboards").mkdir(exist_ok=True)
    (provision/"datasources/prometheus.yml").write_bytes((ROOT/"deploy/monitoring/provisioning/datasources/prometheus.yml").read_bytes())
    (provision/"dashboards/modelops.yml").write_text("apiVersion: 1\nproviders:\n  - name: ModelOps\n    orgId: 1\n    folder: ModelOps\n    type: file\n    options:\n      path: "+str(ROOT/"deploy/monitoring")+"\n")
    config=E/"grafana.ini"
    config.write_text("[server]\nhttp_addr=127.0.0.1\nhttp_port=19791\n[paths]\ndata="+str(E/"grafana-data")+"\nlogs="+str(E/"grafana-logs")+"\nplugins="+str(E/"grafana-plugins")+"\nprovisioning="+str(provision)+"\n[auth.anonymous]\nenabled=true\norg_role=Viewer\n[users]\nallow_sign_up=false\n[analytics]\nreporting_enabled=false\ncheck_for_updates=false\n")
    grafenv=dict(env)
    grafenv["GF_SECURITY_ADMIN_PASSWORD"]=secrets.token_urlsafe(32)
    # Password is generated only in memory; native anonymous Viewer is loopback-only diagnostic mode.
    launch("grafana",[str(home/"bin/grafana"),"server","--homepath",str(home),"--config",str(config)],grafenv,
           "http://127.0.0.1:19791/api/health",records)
    result={"status":"PASS","prometheus":records["prometheus"],"grafana":records["grafana"],
            "docker":"NOT_EXECUTED_ON_THIS_HOST","grafana_access":"Loopback diagnostic Viewer; Compose anonymous access disabled"}
    (E/"native-services.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":"PASS","prometheus":"READY","grafana":"READY","scope":"Native CPU runtime"}))


if __name__=="__main__":main()
