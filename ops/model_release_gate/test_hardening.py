import copy
from .hardening import validate_observed_trial,quality_decision
def trial():
    return {"config":{"model_sha":"frozen"},"requests":32,"errors":0,"status":"PASS","gpu_samples":10,"gpu":{"peak_used_mib":10},"latency":{"ttft_ms":{"p95":10}},"output_tokens_s":100,"expected_input_tokens":256,"expected_output_tokens":64}
def test_missing_telemetry_errors_version_and_regression_fail_closed():
    t=trial();assert validate_observed_trial(t,"frozen")["status"]=="PASS"
    for change in [{"gpu_samples":0},{"errors":1},{"config":{"model_sha":"wrong"}},{"output_tokens_s":float("nan")},{"latency":{"ttft_ms":{"p95":0}}}]:
        assert validate_observed_trial({**t,**change},"frozen")["status"]=="FAIL"
    assert validate_observed_trial({**t,"output_tokens_s":40},"frozen",t)["status"]=="FAIL"
def test_quality_gate_never_passes_missing_or_declining_quality():
    a={"spec":{"data_sha":"same"},"groups":{g:{"errors":0,"samples":128,"token_f1":.5,"exact_match":.3} for g in ["squad128","dolly24"]}}
    assert quality_decision(a,a)["status"]=="PASS"
    b=copy.deepcopy(a);b["groups"]["squad128"]["token_f1"]=.4
    assert quality_decision(a,b)["status"]=="FAIL"
    assert quality_decision(a,{})["status"]=="FAIL"
