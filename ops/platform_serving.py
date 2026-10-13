"""Reuse the existing vLLM launch contract for either frozen sharded base or trained weights."""
import os
import subprocess
import sys
from pathlib import Path
from pipelines.training.data_contract import verify_model_bundle
from ops.vllm_start import build_args


def comparison_args(env):
    if env.get("SERVING_HOST")!="127.0.0.1":raise ValueError("Native validation is loopback-only")
    return build_args(env)+["--no-enable-prefix-caching"]


def main():
    root=Path(os.environ["MODEL_PATH"]).resolve()
    digest=os.environ["MODEL_SHA256"]
    verify_model_bundle(root,digest)
    args=comparison_args(os.environ)
    if os.environ.get("SERVING_HOST")!="127.0.0.1":raise ValueError("Native validation is loopback-only")
    return subprocess.run([sys.executable]+args).returncode


if __name__=="__main__":raise SystemExit(main())
