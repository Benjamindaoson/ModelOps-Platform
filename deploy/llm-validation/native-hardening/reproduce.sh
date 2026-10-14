#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
# These must be project-local environments. No global dependency install.
.venv/bin/python -c 'from pipelines.training.data_contract import verify_model_bundle;verify_model_bundle(".tools/assets/qwen3b-base","d103a4c22820105e2698beccfbe641a3f02d3c7d517d280da8226de13d15ee7c");print("Frozen assets verified without rewriting manifest")'
.venv/bin/python -m ops.inference_hardening.fetch_sources
.quant-venv/bin/python -m ops.inference_hardening.data
.gpu-venv/bin/python -m ops.inference_hardening.freeze_prompts
.venv/bin/python -m ops.run_inference_hardening --stage all
