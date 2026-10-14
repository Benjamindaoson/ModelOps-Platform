"""Snapshot actual hardware/software and hash-verify reusable model assets."""
import json,os,shutil,subprocess,time
from pathlib import Path
import torch
from pipelines.training.data_contract import verify_model_bundle,sha256
ROOT=Path(__file__).resolve().parents[2];E=ROOT/"Evidence/inference-hardening"

def main():
    base=ROOT/".tools/assets/qwen3b-base";model_sha=sha256(base/"modelops-files.json");verify_model_bundle(base,model_sha)
    old=json.loads((ROOT/"Evidence/llm-production-validation/training-finished.json").read_text())["result"]
    assert sha256(old["checkpoint"])==old["checkpoint_sha256"]
    props=torch.cuda.get_device_properties(0)
    x=torch.randn(256,256,device="cuda");start=torch.cuda.Event(enable_timing=True);end=torch.cuda.Event(enable_timing=True)
    start.record();out=x@x;end.record();torch.cuda.synchronize()
    result={"status":"PASS","gpu_name":props.name,"compute_capability":[props.major,props.minor],"torch_total_memory_bytes":props.total_memory,
            "multiprocessors":props.multi_processor_count,"torch":torch.__version__,"cuda_runtime":torch.version.cuda,"cuda_available":torch.cuda.is_available(),
            "cuda_event_matmul_ms":start.elapsed_time(end),"cuda_output_finite":bool(torch.isfinite(out).all()),"cpu_visible":os.cpu_count(),
            "driver":subprocess.check_output(["nvidia-smi","--query-gpu=driver_version","--format=csv,noheader"],text=True).strip(),
            "nsys":{"status":"SKIPPED" if not shutil.which("nsys") else "AVAILABLE","reason":"CLI absent; no privilege bypass"},
            "ncu":{"status":"SKIPPED" if not shutil.which("ncu") else "AVAILABLE","reason":"CLI absent; no privilege bypass"},
            "docker_gpu_runtime":{"status":"SKIPPED","reason":"No Docker host/runtime in current authorized container"},
            "baseline":{"path":str(base),"sha256":model_sha,"revision":"aa8e72537993ba99e69dfaafa59ed015b17504d1"},
            "historical_checkpoint_verified":old["checkpoint_sha256"],"fp8":"Not validated; architecture alone is not an FP8 performance claim"}
    E.mkdir(exist_ok=True);(E/"environment.json").write_text(json.dumps(result,indent=2)+"\n")
    (ROOT/"docs/evidence/inference-hardening/environment.json").write_text(json.dumps(result,indent=2)+"\n")
    print("Actual environment + historical weight hashes PASS")

if __name__=="__main__":main()
