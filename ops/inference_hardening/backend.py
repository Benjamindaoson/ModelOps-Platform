"""Explicit native serving adapter; historical launchers and hashes remain unchanged."""
import argparse,json,os,sys
from pathlib import Path
from pipelines.training.data_contract import verify_model_bundle
from .contracts import launch_args

def main():
    p=argparse.ArgumentParser();p.add_argument("--config",required=True);a=p.parse_args()
    c=json.loads(Path(a.config).read_text())
    verify_model_bundle(c["model"],c["model_sha"])
    args=launch_args(c)
    if c.get("kv_cache_bytes") and c["engine"]=="vllm":args += ["--kv-cache-memory-bytes",str(c["kv_cache_bytes"])]
    os.execv(sys.executable,[sys.executable]+args)

if __name__=="__main__":main()
