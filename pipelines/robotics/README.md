# SmolVLA Linux adapter v1
A separate single-host execution type for VLA-Forge official Flow Matching. The existing text SFT/Argo pipeline is unchanged. CPU contract tests do not prove GPU results.

Run `python -m pipelines.robotics.adapter --help`. Create from a frozen VLA JSON recipe, then start/query/stop/resume. A process is signalled only after PID creation time and runner command match. Checkpoints retain optimizer/scheduler/sampler/RNG in the authoritative VLA artifact directory. Immutable registry rejects mutation; deployment requires a matching M05 simulation evaluation. M06 promotion and Kubernetes scheduling are unsupported.

Local CPU test: `.venv/bin/python -m pytest pipelines/robotics/test_adapter.py -q`. GPU records are private under `/data/VLA-Forge/Evidence/M05/modelops/`; no model, image or dataset copying into this repository.

## Verified M05 workflow on the authorized 3090

The ModelOps runner launches the exact VLA-Forge training entry point in the VLA project's `.venv`. The platform keeps only job metadata, CPU-side tracking, and immutable file references; the VLA repository remains the implementation of Flow Matching, simulation, and action processing. Both repositories retain separate Git histories. The evidence root is `/data/VLA-Forge/Evidence/M05`.

```bash
cd /data/ModelOps-Platform
.venv/bin/python -m pipelines.robotics.adapter query --root /data/VLA-Forge/Evidence/M05/modelops/jobs --vla-root /data/VLA-Forge/project/robot-vla --run-id m05-corrective-cam180-s5501
.venv/bin/python -m pipelines.robotics.adapter track --root /data/VLA-Forge/Evidence/M05/modelops/jobs --vla-root /data/VLA-Forge/project/robot-vla --run-id m05-corrective-cam180-s5501 --tracking-uri file:///data/VLA-Forge/Evidence/M05/modelops/mlruns
.venv/bin/python -m pipelines.robotics.compare_runs --native-dir /data/VLA-Forge/Evidence/M05/training/ab-native-cam180 --native-config /data/VLA-Forge/Evidence/M05/training/configs/m05-ab-native-cam180-s5701.json --managed-dir /data/VLA-Forge/Evidence/M05/modelops/jobs/m05-ab-managed-cam180-s5701 --output /data/VLA-Forge/Evidence/M05/modelops/ab_comparison.json
```

Register versions from reviewed record JSON files using `python -m pipelines.robotics.registry_cli register --root <private-registry> --record <record.json>`. `deploy` requires a real M05 development evaluation JSON with zero illegal actions. Once a version is qualified and active, start the simulation-only action API with the VLA environment:

```bash
cd /data/ModelOps-Platform
/data/VLA-Forge/project/robot-vla/.venv/bin/python -m pipelines.robotics.serve --registry /data/VLA-Forge/Evidence/M05/modelops/registry --backend eager --log /data/VLA-Forge/Evidence/M05/modelops/serving.jsonl --host 127.0.0.1 --port 18767
```

The service accepts raw 256×256 dual camera RGB observations, an 8D robot state, a task instruction, and a simulation-only scope; it returns a 50×7 continuous action chunk. Version changes load and hash-check the candidate before the registry is activated. Rollback returns to a previously qualified revision. It is not a language-model chat endpoint or a hardware robot controller. The server listens only on loopback.
