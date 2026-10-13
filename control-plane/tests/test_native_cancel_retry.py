"""CPU transport fixtures validate lifecycle invariants, not GPU experiments."""
import importlib.util,json,sys
from pathlib import Path
from types import SimpleNamespace
from modelops.linux_runtime import LinuxRuntime
spec=importlib.util.spec_from_file_location("retry_fixtures",Path(__file__).with_name("test_api.py"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
api=m.api;headers=m.headers;register=m.register

def test_native_uppercase_failure_can_retry_with_native_identity(api):
    client,runtime=api;runtime.kind="linux"
    model,dataset=register(client)
    job=client.post("/api/v1/train-jobs",headers=headers(),json={
      "name":"failed-linux-case","artifact_id":model["id"],"dataset_id":dataset["id"],
      "framework":"transformers","output_name":"failed-linux-output"}).json()
    runtime.jobs[job["workflow_name"]]["status"]["phase"]="FAILED"
    response=client.post("/api/v1/train-jobs/"+job["id"]+"/retry",headers=headers())
    assert response.status_code==201,response.text
    row=response.json()
    assert row["worker"]=="linux" and row["runtime_run_id"]==row["id"]

def test_paused_native_job_can_cancel_without_signalling_any_process(tmp_path):
    runtime=LinuxRuntime(tmp_path,sys.executable,tmp_path/"runtime")
    row=SimpleNamespace(tenant="alpha",id="job-1")
    directory=runtime.directory(row);directory.mkdir(parents=True)
    (directory/"intent.json").write_text('{"metadata":{}}')
    (directory/"process.json").write_text(json.dumps({"pid":99999999,"create_time":0,"started":0}))
    (directory/"artifacts").mkdir()
    (directory/"artifacts/result.json").write_text('{"status":"PAUSED"}')
    runtime.cancel_finetune(row,"0")
    assert runtime.get_finetune(row)["status"]["phase"]=="CANCELLED"
