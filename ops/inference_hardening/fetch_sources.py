"""Verified official small artifacts only; never accept truncated HTTP success as valid data."""
import hashlib,json,urllib.request,time
from pathlib import Path
from .runtime import ROOT,E
SOURCES=[
    {"path":"Evidence/inference-hardening/squad-validation.parquet","url":"https://huggingface.co/datasets/rajpurkar/squad/resolve/7b6d24c440a36b6815f21b70d25016731768db1f/plain_text/validation-00000-of-00001.parquet","sha":"8c6646d36bd5a95061e076788cf3161d11f6f3e7d625dac7a83bbed0a49f69f7","bytes":1819889},
    {"path":".sglang-venv/lib/python3.12/site-packages/sglang/srt/mem_cache/storage/hf3fs/hf3fs_utils.cpp","url":"https://raw.githubusercontent.com/sgl-project/sglang/v0.4.10/python/sglang/srt/mem_cache/storage/hf3fs/hf3fs_utils.cpp","sha":"74360fb7198be8e161132bff1ae4e0ce44c3a418dc0f410af24a619e7ede6867"}
]
def main():
    records=[]
    for source in SOURCES:
        path=(ROOT/source["path"]).resolve()
        assert path.is_relative_to(ROOT)
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==source["sha"]:records.append({**source,"verified":True,"reused":True});continue
        for attempt in range(3):
            try:
                with urllib.request.urlopen(source["url"],timeout=30) as r:data=r.read()
                if hashlib.sha256(data).hexdigest()!=source["sha"] or len(data)!=source.get("bytes",len(data)):raise ValueError("Official source hash/size mismatch")
                path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+".verified-download");temp.write_bytes(data);temp.replace(path)
                records.append({**source,"verified":True,"attempt":attempt+1});break
            except Exception:
                if attempt==2:raise
                time.sleep(1)
    (E/"source-download-validation.json").write_text(json.dumps(records,indent=2))
if __name__=="__main__":main()
