#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
# These must be project-local environments. No global dependency install.
.venv/bin/python -m ops.bootstrap_llm_validation_assets --verify-only
.venv/bin/python -m ops.inference_hardening.fetch_sources
.quant-venv/bin/python -m ops.inference_hardening.data
.gpu-venv/bin/python -m ops.inference_hardening.freeze_prompts
.venv/bin/python -m ops.run_inference_hardening --stage all
