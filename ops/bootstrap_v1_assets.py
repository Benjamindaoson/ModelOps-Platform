"""Download/verify public frozen assets with upstream Git/LFS identities; no credentials required."""
from pathlib import Path
import argparse,json,hashlib,urllib.request,time
ROOT=Path(__file__).resolve().parents[1]
ALLOWED={"model":{"LICENSE","README.md","config.json","generation_config.json","merges.txt","model.safetensors","tokenizer.json","tokenizer_config.json","vocab.json"},
    "dataset":{"README.md","databricks-dolly-15k.jsonl"},
    "embedding":{"README.md","config.json","model.safetensors","special_tokens_map.json","tokenizer.json","tokenizer_config.json","vocab.txt"}}
DIRECTORY={"model":"qwen-base","dataset":"dolly","embedding":"embedding-base"}
def hashes(path):
    size=path.stat().st_size;git=hashlib.sha1(("blob "+str(size)+"\0").encode());sha=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1048576),b""):git.update(block);sha.update(block)
    return sha.hexdigest(),git.hexdigest(),size
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--verify-only",action="store_true");args=parser.parse_args()
    receipt=[];cache=(ROOT/".tools/assets").resolve()
    for source in json.loads((ROOT/"docs/v1/official_sources.json").read_text()):
        for f in source["files"]:
            if f["name"] not in ALLOWED[source["kind"]]:continue
            dest=cache/DIRECTORY[source["kind"]]/f["name"]
            if not dest.resolve().is_relative_to(cache):raise RuntimeError("Unsafe asset path")
            def valid():
                if not dest.is_file():return False
                sha,git,size=hashes(dest)
                return sha==f["lfs"]["sha256"] and size==f["lfs"]["size"] if f.get("lfs") else git==f["blob"]
            if not valid():
                if args.verify_only:raise RuntimeError("Frozen asset missing/corrupt: "+str(dest))
                dest.parent.mkdir(parents=True,exist_ok=True);tmp=dest.with_suffix(dest.suffix+".part")
                verified=False
                for host in ["https://huggingface.co","https://hf-mirror.com"]:
                    url=host+"/"+("datasets/" if source["kind"]=="dataset" else "")+source["repo"]+"/resolve/"+source["revision"]+"/"+f["name"]
                    try:
                        with urllib.request.urlopen(url,timeout=30) as response,tmp.open("wb") as output:
                            while True:
                                block=response.read(1048576)
                                if not block:break
                                output.write(block)
                        sha,git,size=hashes(tmp)
                        okay=sha==f["lfs"]["sha256"] and size==f["lfs"]["size"] if f.get("lfs") else git==f["blob"]
                        if not okay:raise RuntimeError("Upstream identity mismatch")
                        tmp.replace(dest);verified=True;break
                    except Exception:tmp.unlink(missing_ok=True)
                if not verified:raise RuntimeError("Official pinned download failed: "+f["name"])
            sha,git,size=hashes(dest)
            receipt.append({"repo":source["repo"],"revision":source["revision"],"file":str(dest.relative_to(ROOT)),
                "sha256":sha,"git_blob_sha1":git,"bytes":size,"declared_upstream_license":source["license"]})
    e=ROOT/"Evidence/v1";e.mkdir(parents=True,exist_ok=True)
    (e/"asset-validation.json").write_text(json.dumps({"status":"PASS","files":receipt},indent=2))
    print("FROZEN_ASSETS_VERIFIED",len(receipt))
if __name__=="__main__":main()
