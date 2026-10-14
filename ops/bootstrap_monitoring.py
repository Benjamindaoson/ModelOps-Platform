"""Install official hash-verified native monitoring binaries inside this project only."""
import hashlib
import json
import re
import tarfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
E=ROOT/"Evidence/llm-platform-finalization"
PACKAGES=[
 {"name":"prometheus","version":"3.15.0","file":"prometheus-3.15.0.linux-amd64.tar.gz","url":"https://github.com/prometheus/prometheus/releases/download/v3.15.0/prometheus-3.15.0.linux-amd64.tar.gz","sums":"https://github.com/prometheus/prometheus/releases/download/v3.15.0/sha256sums.txt","sha256":"2a542df32eac02ee17b9d844fb2aa1de00dafa5476579ba8a3ba862e9d572ea0"},
 {"name":"grafana","version":"13.2.3","file":"grafana_13.2.3_36482603486_linux_amd64.tar.gz","url":"https://dl.grafana.com/grafana/release/13.2.3/grafana_13.2.3_36482603486_linux_amd64.tar.gz","source":"https://grafana.com/grafana/download/13.2.3?edition=oss&platform=linux","sha256":"6107ad27016296aac38e0d7ffa8753ab540b5541ad27e94790f771289d733235"}
]

def fetch(url,path):
 for attempt in range(3):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"ModelOps-Validation"}),timeout=60) as r,path.open("wb") as out:
    while data:=r.read(1024*1024):out.write(data)
   return
  except Exception:
   if attempt==2:raise
   time.sleep(2)

def install(item):
 target=ROOT/".tools/monitoring";target.mkdir(parents=True,exist_ok=True)
 archive=target/item["file"];sums=target/(item["name"]+"-sums.txt")
 if item.get("sha256"):
  expected=item["sha256"]
 else:
  fetch(item["sums"],sums)
  rows=sums.read_text().splitlines()
  matches=[x for x in rows if item["file"] in x]
  if len(matches)!=1:raise ValueError("Exact official checksum row missing")
  expected=re.search(r"\b[a-fA-F0-9]{64}\b",matches[0])
  if not expected:raise ValueError("Official checksum unavailable")
  expected=expected.group().lower()
 def digest():
  h=hashlib.sha256()
  with archive.open("rb") as stream:
   for block in iter(lambda:stream.read(1024*1024),b""):h.update(block)
  return h.hexdigest()
 if not archive.exists() or digest()!=expected:fetch(item["url"],archive)
 actual=digest()
 if actual!=expected:raise ValueError("Official archive checksum mismatch")
 with tarfile.open(archive) as tar:
  members=[m for m in tar.getmembers() if m.isfile() and (m.name.endswith("/bin/grafana") or (item["name"]=="prometheus" and m.name.endswith("/prometheus")))]
  if len(members)!=1:raise ValueError("Official executable member missing")
  member=members[0];installed=target/member.name
  if installed.exists():
   h=hashlib.sha256()
   with tar.extractfile(member) as source:
    for block in iter(lambda:source.read(1024*1024),b""):h.update(block)
   actual_installed=hashlib.file_digest(installed.open("rb"),"sha256").hexdigest()
   if actual_installed!=h.hexdigest():raise ValueError("Installed binary differs; stop owned service before replacement")
  else:tar.extractall(target,filter="data")
 result={**item,"status":"PASS","sha256":actual,"bytes":archive.stat().st_size,"source":"Official release archive and checksum"}
 (E/(item["name"]+"-install.json")).write_text(json.dumps(result,indent=2)+"\n")
 print(json.dumps(result),flush=True)
 return result

def main():
 E.mkdir(parents=True,exist_ok=True)
 with ThreadPoolExecutor(max_workers=2) as pool:
  results=list(pool.map(install,PACKAGES))
 (E/"monitoring-binaries.json").write_text(json.dumps(results,indent=2)+"\n")

if __name__=="__main__":main()
