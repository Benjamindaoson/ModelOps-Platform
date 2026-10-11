# SmolVLA Linux adapter v1
A separate single-host execution type for VLA-Forge official Flow Matching. The existing text SFT/Argo pipeline is unchanged. CPU contract tests do not prove GPU results.

Run `python -m pipelines.robotics.adapter --help`. Create from a frozen VLA JSON recipe, then start/query/stop/resume. A process is signalled only after PID creation time and runner command match. Checkpoints retain optimizer/scheduler/sampler/RNG in the authoritative VLA artifact directory. Immutable registry rejects mutation; deployment requires a matching M05 simulation evaluation. M06 promotion and Kubernetes scheduling are unsupported.

Local CPU test: `.venv/bin/python -m pytest pipelines/robotics/test_adapter.py -q`. GPU records are private under `/data/VLA-Forge/Evidence/M05/modelops/`; no model, image or dataset copying into this repository.
