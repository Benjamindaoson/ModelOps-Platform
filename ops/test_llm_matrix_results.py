import json
from pathlib import Path
import pytest

def load(path):
    import ops.benchmark_llm_validation as m
    fn=getattr(m,"read_trial",None)
    assert fn is not None, "Official status/raw result boundary not implemented"
    return fn(path)

def fixture(path,status="PASS"):
    (path/"status.json").write_text(json.dumps({"status":status}))
    (path/"manifest.json").write_text(json.dumps({"prompts":2,"output_len_tokens":3}))
    (path/"raw-benchmark.json").write_text(json.dumps({"completed":2,"duration":1,"total_output_tokens":6,
        "output_lens":[3,3],"request_throughput":2,"output_throughput":6,"p50_ttft_ms":1}))
    (path/"gpu-telemetry.csv").write_text("utilization_percent,memory_used_mib,power_watts\n10,20,30\n")

def test_actual_status_and_raw_are_sufficient(tmp_path):
    fixture(tmp_path);r=load(tmp_path)
    assert r["status"]=="PASS" and r["completed_requests"]==2
    assert r["output_tokens"]==6

def test_failed_cli_never_becomes_passing(tmp_path):
    fixture(tmp_path,"FAIL_BENCHMARK")
    with pytest.raises(ValueError):load(tmp_path)

def test_short_outputs_reject_fixed_protocol(tmp_path):
    fixture(tmp_path);r=json.loads((tmp_path/"raw-benchmark.json").read_text());r["output_lens"]=[2,3]
    (tmp_path/"raw-benchmark.json").write_text(json.dumps(r))
    with pytest.raises(ValueError):load(tmp_path)
