# ModelOps Platform

An enterprise-focused model hosting, inference optimization, and fine-tuning platform.

## Foundation

The first development milestone imports a pinned snapshot of [GaeaRuiW/kube-llmops](https://github.com/GaeaRuiW/kube-llmops) (Apache-2.0) into a reviewable `bootstrap/kube-llmops-import` branch. Until that import is merged, `main` is an initialization-only branch.

We will distinguish inherited upstream capabilities from features that are independently implemented and benchmarked in this repository. Real GPU performance, fine-tuning, and availability claims require evidence and must not be inferred from Helm-template CI alone.

## Project goals

- Multi-engine inference service (vLLM, SGLang, embeddings, ASR/TTS adapters) with model registry, routing, lifecycle, and permission controls.
- Reproducible latency/throughput/VRAM/availability optimization on actual hardware.
- Dataset-to-LoRA/QLoRA training, versioned artifacts, evaluation gates, and deployment promotion/rollback.
- Kubernetes-based orchestration, observability, security, and automated recovery.
- Transparent upstream provenance and separate validation of original contributions.

See the upstream import branch and its `docs/UPSTREAM_PROVENANCE.md` for source details.