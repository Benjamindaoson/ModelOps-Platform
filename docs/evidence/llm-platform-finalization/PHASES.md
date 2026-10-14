# Phase evidence — 2026-10-13

This sprint reuses the completed GPU training run and does not retrain or edit its checkpoint. Source and private evidence live in the authorized cloud worktree.

| Phase | Result | Actual evidence / boundary |
|---|---|---|
| 1 GPU Docker | **SKIPPED** on cloud host | NVIDIA GPU exists, Docker host runtime does not. New image, Compose and container probe implemented. Native inference does not prove GPU container execution. [Receipt](../gpu-runtime-validation/validation-report.md). |
| 2 Release gate | **PASS, actual live check** | MLflow model v1 → training lineage → real hashes → independent heldout evaluation → loaded API identity → three matched C4 benchmark trials. [Decision](release_decision.json). |
| 3 Monitoring | **PASS, native runtime** | Official hash-verified Prometheus 3.15.0 / Grafana 13.2.3, actual vLLM SSE requests, GPU gauges and scrape queries, provisioned dashboard. Compose contract separately validated by CI when available. [Receipt](monitoring-validation.json). |
| 4 CI/CD | **PASS, actual Actions run** | Python lint/test/unittest, actual Compose CPU fixture, GPU image build + CPU startup contract and artifacts passed in run 38389379022. CI GPU inference stays SKIPPED. |
| 5 Comparison | **PASS, actual 1,536 requests** | 12 trials, Base and trained model, C4/C16 × 3 repeats × 128 requests. Frozen configuration and source/checkpoint hashes; negative throughput difference retained. [Report](../../../benchmark/model-comparison.md). |
| 6 Documentation | Completed with explicit boundaries | English/Chinese README, final architecture, upstream architecture preservation, changelog, reproducible commands. |
| 7 Quality | **467 pytest passed, 2 skipped; 62 unittest passed; 3 browser tests passed** | New gate and telemetry tests, full CPU suite, actual Next.js build and isolated FastAPI/browser flow. [Logs and hashes](test-evidence.json). Optional cluster tests and legacy Dify deployment scripts are not claimed. |

No full production-readiness claim follows from these checks. In particular, GPU Docker execution, Kubernetes GPU scheduling, multi-node reliability and business quality improvement are not validated here.

## Failure handling

The unsupported vLLM cache-reset endpoint failed before measured trials. Prefix caching was then disabled identically for both model conditions before measurement. A missing CLI PATH was repaired without reinstalling dependencies. The base trial set was complete when a TIME_WAIT-only port probe failed; the port probe was fixed and only missing trained trials resumed.

Official monitoring downloads required a hash-verified transfer relay; truncated archives were rejected and resumed. Re-extracting an already running monitoring binary failed with `Text file busy`; bootstrap now verifies matching installed executables rather than overwriting a live binary. These errors remain in private logs; they are not concealed as successful attempts.

## Evidence roots

- Public summaries: `docs/evidence/llm-platform-finalization/`, `benchmark/model-comparison.{json,md}`.
- Original measurements: `Evidence/llm-platform-finalization/`.
- Prior training/evaluation/rollback: `Evidence/llm-production-validation/`.
- No weights, raw request logs, access tokens, credentials, venvs or downloaded binaries are committed.
