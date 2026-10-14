"""Additional fail-closed predicates for observed telemetry and immutable regression baselines."""
from .gate import finite

def validate_observed_trial(trial,model_sha,baseline=None,max_regression=.15):
    checks={"version":trial.get("config",{}).get("model_sha")==model_sha,
            "requests":trial.get("requests",0)>=32 and trial.get("errors") == 0 and trial.get("status")=="PASS",
            "telemetry":trial.get("gpu_samples",0)>0 and finite(trial.get("gpu",{}).get("peak_used_mib")),
            "latency":False,"throughput":False}
    try:
        ttft=trial["latency"]["ttft_ms"]["p95"];tps=trial["output_tokens_s"]
        checks["latency"]=finite(ttft) and ttft>0
        checks["throughput"]=finite(tps) and tps>0
        if baseline:
            same=(baseline["config"]["model_sha"]==model_sha and baseline["expected_input_tokens"]==trial["expected_input_tokens"] and baseline["expected_output_tokens"]==trial["expected_output_tokens"] and baseline["requests"]==trial["requests"])
            checks["baseline_identity"]=same
            checks["latency"] &= ttft <= baseline["latency"]["ttft_ms"]["p95"]*(1+max_regression)
            checks["throughput"] &= tps >= baseline["output_tokens_s"]/(1+max_regression)
    except (KeyError,TypeError,ZeroDivisionError):pass
    return {"status":"PASS" if all(checks.values()) else "FAIL","checks":checks,"scope":"Engineering regression predicate only; no business SLO certified"}

def quality_decision(base,candidate,min_delta=-.02):
    errors=[];checks={}
    for group in ["squad128","dolly24"]:
        try:
            a=base["groups"][group];b=candidate["groups"][group]
            checks[group]=a["errors"]==b["errors"]==0 and a["samples"]==b["samples"] and b["token_f1"]-a["token_f1"]>=min_delta and b["exact_match"]-a["exact_match"]>=min_delta
        except (KeyError,TypeError):checks[group]=False
    checks["frozen_data"]=base.get("spec",{}).get("data_sha")==candidate.get("spec",{}).get("data_sha") and bool(base.get("spec",{}).get("data_sha"))
    return {"status":"PASS" if all(checks.values()) else "FAIL","checks":checks,"threshold_delta":min_delta,"scope":"Bounded QA engineering admission; not broad model-quality proof"}
