"""Owned, pinned 3B assets; upstream identities are fetched separately and frozen."""
from pathlib import Path
import argparse, concurrent.futures, fcntl, json, os, time, urllib.request
from ops.bootstrap_v1_assets import hashes
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/"Evidence/llm-production-validation"
CACHE=ROOT/".tools/assets/qwen3b-base"

def owned_destination(root,name):
    root=Path(root).resolve()
    if "/" in name or "\\" in name or name in {"",".",".."}:
        raise ValueError("Asset file must be a single safe filename")
    p=(root/name).resolve()
    if not p.is_relative_to(root):raise ValueError("Asset escaped owned cache")
    return p

def validate_file(record,path):
    p=Path(path)
    if not p.is_file():return False
    sha,git,size=hashes(p)
    lfs=record.get("lfs")
    return sha==lfs["sha256"] and size==lfs["size"] if lfs else git==record["blob"]

def download(source,record,verify_only=False):
    p=owned_destination(CACHE,record["name"])
    began=time.time()
    if not validate_file(record,p):
        if verify_only:raise RuntimeError("Frozen asset absent/corrupt: "+record["name"])
        p.parent.mkdir(parents=True,exist_ok=True)
        partial=p.with_name(p.name+".part")
        verified=False
        for host in ("https://modelscope.cn/models","https://hf-mirror.com","https://huggingface.co"):
            for attempt in range(3):
                offset=partial.stat().st_size if partial.exists() else 0
                revision="master" if host.endswith("/models") else source["revision"]
                req=urllib.request.Request(host+"/"+source["repo"]+"/resolve/"+revision+"/"+record["name"],headers={"Range":"bytes="+str(offset)+"-"} if offset else {})
                try:
                    with urllib.request.urlopen(req,timeout=30) as response:
                        resumed=offset>0 and response.status==206 and response.headers.get("Content-Range","").startswith("bytes "+str(offset)+"-")
                        with partial.open("ab" if resumed else "wb") as out:
                            while block:=response.read(1024*1024):out.write(block)
                    if not validate_file(record,partial):
                        partial.unlink(missing_ok=True)
                        raise ValueError("Upstream identity mismatch")
                    os.replace(partial,p);verified=True;break
                except Exception as exc:
                    print(json.dumps({"file":record["name"],"attempt":attempt+1,"error_type":type(exc).__name__,"partial_bytes":partial.stat().st_size if partial.exists() else 0}),flush=True)
                    time.sleep(1)
            if verified:break
        if not verified:raise RuntimeError("Pinned download failed: "+record["name"])
    sha,git,size=hashes(p)
    result={"file":str(p.relative_to(ROOT)),"sha256":sha,"git_blob_sha1":git,"bytes":size,"wall_s":time.time()-began}
    print(json.dumps({"verified":record["name"],"bytes":size}),flush=True)
    return result

def main():
    a=argparse.ArgumentParser();a.add_argument("--verify-only",action="store_true");args=a.parse_args()
    E.mkdir(parents=True,exist_ok=True)
    with (E/"assets.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        source=json.loads((ROOT/"docs/evidence/llm-validation/training/official-source.json").read_text())
        if source["repo"]!="Qwen/Qwen2.5-3B-Instruct" or len(source["revision"])!=40:raise ValueError("Unfrozen model source")
        began=time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            files=list(pool.map(lambda x:download(source,x,args.verify_only),source["files"]))
        receipt={"status":"PASS","repo":source["repo"],"revision":source["revision"],"license":source["license"],"files":files,"wall_s":time.time()-began}
        (E/"asset-validation.json").write_text(json.dumps(receipt,indent=2))
        (CACHE/"modelops-files.json").write_text(json.dumps({"repo":source["repo"],"revision":source["revision"],"files":[{"name":Path(f["file"]).name,"sha256":f["sha256"],"bytes":f["bytes"]} for f in files]},indent=2))
        print("ALL_FROZEN_3B_ASSETS_VERIFIED",flush=True)
if __name__=="__main__":main()
