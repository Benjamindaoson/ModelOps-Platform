import importlib,json,pytest
from pathlib import Path
from ops.observability.stream_metrics import StreamMeter

def module():
    try: value=importlib.import_module("ops.inference_hardening.contracts")
    except ModuleNotFoundError:value=None
    assert value is not None,"Hardening protocol implementation absent"
    return value

def test_engine_arguments_freeze_cache_and_limits(tmp_path):
    m=module()
    config={"engine":"vllm","model":str(tmp_path),"name":"frozen","port":19801,"memory_fraction":.7,"max_context":4096,"max_sequences":64,"batch_tokens":2048,"prefix_cache":False}
    v=m.launch_args(config)
    assert "--no-enable-prefix-caching" in v
    assert v[v.index("--max-num-seqs")+1]=="64"
    s=m.launch_args({**config,"engine":"sglang"})
    assert "--disable-radix-cache" in s
    assert s[s.index("--dtype")+1]=="float16"

def test_unsupported_engine_and_invalid_budget_rejected(tmp_path):
    m=module()
    with pytest.raises(ValueError):m.launch_args({"engine":"fake","model":str(tmp_path)})
    with pytest.raises(ValueError):m.launch_args({"engine":"vllm","model":str(tmp_path),"memory_fraction":1.1})

def test_release_rejects_missing_gpu_or_wrong_output_lengths():
    m=module()
    row={"status":"PASS","requests":32,"errors":0,"output_tokens":2048,"expected_output_tokens":64,"gpu_samples":0}
    assert m.trial_valid(row) is False
    row["gpu_samples"]=5
    assert m.trial_valid(row) is True
    row["output_tokens"]=2047
    assert m.trial_valid(row) is False

def test_receipt_reuse_rehashes_raw_bytes(tmp_path):
    m=module();raw=tmp_path/"raw.jsonl";raw.write_text("real-test-record\n")
    receipt={"source_sha":"frozen","raw_sha":m.digest(raw),"protocol_sha":"fixed","status":"PASS"}
    assert m.resume_valid(receipt,raw,"frozen","fixed")
    raw.write_text("changed\n")
    assert not m.resume_valid(receipt,raw,"frozen","fixed")

def test_completions_meter_uses_actual_usage_and_chunk_times():
    meter=StreamMeter(10)
    meter.feed(b'data: {"choices":[{"text":"Paris"}]}\n\n',10.2)
    meter.feed(b'data: {"choices":[{"text":"."}],"usage":{"prompt_tokens":256,"completion_tokens":2}}\n\n',10.3)
    meter.feed(b'data: [DONE]\n\n',10.4)
    assert getattr(meter,"prompt_tokens",None)==256
    assert getattr(meter,"content_times",None)==[10.2,10.3]
    assert getattr(meter,"text",None)=="Paris."
    assert meter.output_tokens==2
