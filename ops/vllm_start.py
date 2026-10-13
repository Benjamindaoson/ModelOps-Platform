"""Shared explicit vLLM launch contract for native experiments and the Docker image."""
from pathlib import Path
import argparse,hashlib,json,os,sys

def build_args(env):
    model=env.get("MODEL_PATH","/model")
    name=env.get("SERVED_MODEL_NAME","modelops-qwen3b-qlora")
    memory=float(env.get("GPU_MEMORY_UTILIZATION","0.90"))
    length=int(env.get("MAX_MODEL_LEN","2048"))
    if not 0.1<=memory<=0.95 or not 320<=length<=32768:raise ValueError("Invalid serving resource budget")
    args=["-m","vllm.entrypoints.openai.api_server","--model",model,"--served-model-name",name,
          "--dtype","half","--max-model-len",str(length),"--gpu-memory-utilization",str(memory),
          "--host",env.get("SERVING_HOST","0.0.0.0"),"--port",str(int(env.get("SERVING_PORT","8000")))]
    if env.get("MAX_NUM_BATCHED_TOKENS"):
        tokens=int(env["MAX_NUM_BATCHED_TOKENS"])
        if not 320<=tokens<=32768:raise ValueError("Invalid batching token budget")
        args+=["--max-num-batched-tokens",str(tokens)]
    if env.get("MAX_NUM_SEQS"):
        count=int(env["MAX_NUM_SEQS"])
        if not 1<=count<=256:raise ValueError("Invalid sequence budget")
        args+=["--max-num-seqs",str(count)]
    return args

def verify_checkpoint(env):
    path=Path(env.get("MODEL_PATH","/model")).resolve()/"model.safetensors"
    expected=env.get("MODEL_SHA256","")
    if len(expected)!=64 or not path.is_file():raise ValueError("Exact trained checkpoint digest and mounted file required")
    h=hashlib.sha256()
    with path.open("rb") as stream:
        while block:=stream.read(1048576):h.update(block)
    if h.hexdigest()!=expected:raise ValueError("Mounted checkpoint digest changed")
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--describe",action="store_true");a=parser.parse_args()
    args=build_args(os.environ)
    if a.describe:
        print(json.dumps({"argv":args,"weights_in_image":False,"checkpoint_verification_required":True}));return
    verify_checkpoint(os.environ)
    os.execv(sys.executable,[sys.executable]+args)
if __name__=="__main__":main()
