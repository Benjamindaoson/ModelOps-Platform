# Execution ledger

| 01 | Integrated main and published M06/SmolVLA ancestry; local merge 4a1df727. No force push. GitHub publication is recorded separately. |
| 02 | Unified four model types and ten requested metadata fields; reversible Alembic 0004/0005/0006; legacy VLA versions imported by verified references. Deployment status derives from actual owned backend readiness. |
| 03 | Observed six-state jobs, receipt hashing, pause/resume and retry/cancel guards. Real GPU paused at step 2 and recovered to 64 unique updates. SmolVLA uses the retained Flow Matching CLI adapter; REST text jobs reject VLA. |
| 04 | Three new 32-step training runs: broad LoRA, broad NF4 QLoRA, short-answer LoRA. Broad baseline F1 0.2476; candidates fail 0.55. Short-answer base/candidate F1 0.5605/0.5605; passes fixed gate without observed improvement. |
| 05 | Real vLLM trained-version API, deployment generations 1/2/3 and rollback; 384D CPU embedding; 50x7 frozen VLA action response. Go custom-policy protocol and Helm contracts tested. GPU Kubernetes/TEI/SGLang deployments not executed. |
| 06 | Official vLLM 0.10.2 benchmark: 40/40, 6.435 req/s, 183.712 output tokens/s, TTFT P95 34.763 ms. N=40 synthetic C4 workload; no production SLO claim. |
| 07 | Protected tenant metrics, existing OIDC/RBAC/Ed25519 production gates retained, actual SQLite backup/restore and identities verified. Kubernetes envtest passed. Real enterprise OIDC, PostgreSQL runtime, remote object-store restore and GPU cluster release remain unvalidated. |

All outcomes are backed by saved actual receipts. Rejected models and failed attempts remain available.
