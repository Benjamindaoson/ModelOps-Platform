# ModelOps Platform v1.0 RC — execution and acceptance report

The repository now includes a real single-host model lifecycle and the existing Kubernetes control plane in one code line. The production infrastructure acceptance gate is still OPEN.

## Scope and identities
- Cloud worktree: /data/ModelOps-Platform/tmp/v1-production-readiness
- Private evidence: /data/ModelOps-Platform/tmp/v1-production-readiness/Evidence/v1
- Existing branch: codex/v1-production-readiness
- Source histories: main 73e6a246; SmolVLA 9b2df487; published M06 92d9ee614; preserved local merge 4a1df727.
- New GPU jobs: 4; actual optimizer updates: 160; RTX 3090, Torch 2.8.0+cu128.
- Dataset splits: frozen 64 training / 24 source-disjoint heldout examples per task. No larger-model training.

## Seven-phase execution
| Phase | Actual implementation and validation |
|---|---|
| 01 | Integrated main and published M06/SmolVLA ancestry; local merge 4a1df727. No force push. GitHub publication is recorded separately. |
| 02 | Unified four model types and ten requested metadata fields; reversible Alembic 0004/0005/0006; legacy VLA versions imported by verified references. Deployment status derives from actual owned backend readiness. |
| 03 | Observed six-state jobs, receipt hashing, pause/resume and retry/cancel guards. Real GPU paused at step 2 and recovered to 64 unique updates. SmolVLA uses the retained Flow Matching CLI adapter; REST text jobs reject VLA. |
| 04 | Three new 32-step training runs: broad LoRA, broad NF4 QLoRA, short-answer LoRA. Broad baseline F1 0.2476; candidates fail 0.55. Short-answer base/candidate F1 0.5605/0.5605; passes fixed gate without observed improvement. |
| 05 | Real vLLM trained-version API, deployment generations 1/2/3 and rollback; 384D CPU embedding; 50x7 frozen VLA action response. Go custom-policy protocol and Helm contracts tested. GPU Kubernetes/TEI/SGLang deployments not executed. |
| 06 | Official vLLM 0.10.2 benchmark: 40/40, 6.435 req/s, 183.712 output tokens/s, TTFT P95 34.763 ms. N=40 synthetic C4 workload; no production SLO claim. |
| 07 | Protected tenant metrics, existing OIDC/RBAC/Ed25519 production gates retained, actual SQLite backup/restore and identities verified. Kubernetes envtest passed. Real enterprise OIDC, PostgreSQL runtime, remote object-store restore and GPU cluster release remain unvalidated. |

## Real learning and deployment results
Broad Dolly LoRA and QLoRA are retained as rejected candidates. Their Token-F1 values are 0.254008 and 0.266793, versus 0.247649 for the base model. Neither passes the unchanged 0.55 threshold.

One additional pre-frozen short-answer task has base and trained candidate Token-F1 0.560539; both have exact match 10/24. This is a successful pipeline/release-gate validation with no measured quality gain. It is not evidence of general business-task quality.

An audited provenance repair corrected the adapter URI from the merged directory to the actual LoRA directory. Raw original registration is retained, and weights, digest, Run ID and evaluation results are unchanged.

The trained QA checkpoint was registered, independently evaluated by the saved heldout evaluator, accepted using separate development service principals, loaded into vLLM, invoked, promoted, and rolled back to the base identity. Development HMAC identities are not independent human production sign-off.

## Software and runtime verification
Python test counts by executed group: {"core": 104, "data-contract": 4, "training": 5, "evaluation": 12, "benchmark": 18, "ops": 25, "model-loader": 6, "dynamic-training": 6}. Two optional live-runtime tests were skipped in core pytest. Operator unit/envtest packages passed with an actual temporary API server; full Docker/kind suite failed before tests because Docker is unavailable. Console typecheck and production compilation passed; this does not validate enterprise OIDC browser sessions.

All GPU training uses the published frozen source with SHA 6d69cd48a9804d4de4d28615ad1fd9f3a9ce6b06e849a3b236e7813d4b281b38. The final worker only refactors GPU lease handling; the training function AST is identical, with a saved proof.

## Performance and cost
40 real synthetic streamed requests completed. Throughput: 6.435 req/s and 183.712 output tokens/s. TTFT P50/P95/P99: 32.404/34.763/36.676 ms. TPOT P50: 17.389 ms. Benchmark-observed whole-GPU peak: 10075 MiB. Whole sampling-window mean utilization: 6.90%, including client startup.

These figures describe this small 64-input/32-max-output, C4 workload. They do not establish a maximum capacity, a production SLO, or a hardware-matched acceleration claim. The invalid Completion-to-Chat attempt and its 300-second timeout are retained. Costs are measured boundaries, not rental invoices; idle/cloud provisioning expenses remain unmeasured.

## Evidence boundary and remaining production gates
1. Real authorized GPU Kubernetes nodes, device plugin and immutable serving/worker OCI images.
2. A real HTTPS OIDC issuer, PostgreSQL service, tenant provisioning and external credentials.
3. Private authenticated S3 checkpoint bundles and actual whole-platform restore; SQLite metadata restoration alone is not full disaster recovery.
4. Real TEI/SGLang GPU serving, Kubernetes model promotion/rollback, multi-node behavior and production workload SLOs.
5. VLA training and release checks retain their verified CLI protocol. The text evaluation API rejects robot policies; it does not pretend their metric is Token-F1.
6. VLM metadata is supported; native VLM serving is explicitly unsupported. Existing Console-native GPU job forms have not been validated.

## Reproduction
Use project-local environments. Run:
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e 'control-plane[dev,postgres,robotics]' pyyaml
.venv/bin/python -m ops.bootstrap_v1_assets --verify-only
.venv/bin/python -m ops.run_v1_training
.venv/bin/python -m ops.run_v1_training --dataset shortqa
.venv/bin/python -m ops.verify_v1
```
GPU entrypoints require the pinned .gpu-venv described in REPRODUCE.md, frozen datasets, and the private retained VLA assets for robotics. Existing complete training runs are rehashed and reused. Benchmark results are created by the real serving endpoint, never by CPU fixtures.

Code, aggregate metrics and manifests are published to GitHub; datasets, weights, optimizer state, raw observations and private VLA material remain in the owned cloud evidence directory. Upstream Transformers, PEFT, vLLM, LeRobot and LIBERO supply model algorithms; this sprint adds lifecycle integration, correctness guards, provenance and scoped operational proof.
