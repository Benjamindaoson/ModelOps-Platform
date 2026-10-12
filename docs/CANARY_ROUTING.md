# Canary traffic control and evidence

LiteLLM *weighted routing* uses the **same public `model_name`** for multiple backend deployments. ModelOps now uses `<namespace>--<modeldeployment>` as the public group to prevent name collisions across tenant namespaces.

The Go Operator's `RouteManager` reads real `GET /model/info` deployment IDs, updates changed routes with `POST /model/update`, adds only missing routes with `POST /model/new`, and deletes obsolete owned IDs with `POST /model/delete`. Foreign and duplicate records are rejected rather than silently mutated. Stable-only routing remains in effect while the Canary's real Pod is not Ready.

New Canary CRDs require `spec.canary.source`, `revision` and `digest`; the candidate has the same verified model-loader Init Container as stable models. When Canary is removed, the Operator deletes its owned Deployment, Service, PDB and cache PVC.

To validate a **live LiteLLM proxy**, connect two distinguishable, CPU-backed OpenAI mock services or genuine models, then run:

```bash
export MODEL_OPS_API_KEY="<key stored in your secrets manager>"
python ops/verify_canary_routing.py --base-url http://127.0.0.1:4000 \
  --model modelops-alpha--qwen \
  --canary-weight 20 --requests 500 \
  --output evidence/canary-live-http.json
```

The verifier counts `x-litellm-model-id` response headers, not the model name returned in completion JSON. Any failed request or missing header blocks verification. It saves counts, rate and duration, not prompts, outputs or tokens. At boundary weights 0% and 100%, **any** wrong deployment is considered failure; at intermediate weights it checks against a sampling tolerance.

**Acceptance status:** Go API mock contract tests, local builder/controller checks and K8s CPU resource creation tests prove software wiring; they cannot prove LiteLLM's true statistical routing, model quality, GPU throughput or high availability. A successful run of the script against an actual LiteLLM proxy is a separate measurable release gate. Old legacy `model-canary` LiteLLM routes require an admin migration; the reconciler will never delete an unverified foreign group.

Reference: https://docs.litellm.ai/docs/routing
