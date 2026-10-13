"""Additional lifecycle contracts. CPU fixtures are not GPU evidence."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
from modelops.native_serving import NativeServing
from modelops.runtime import RuntimeNotFound
spec=importlib.util.spec_from_file_location("v1_contract_fixtures",Path(__file__).with_name("test_api.py"))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
api=module.api
headers=module.headers
register=module.register

def test_deleted_native_deployment_is_absent(tmp_path):
    serving=NativeServing(tmp_path,"python",tmp_path/"runtime")
    row=SimpleNamespace(tenant="alpha",id="d1")
    path=serving.directory(row);path.mkdir(parents=True)
    (path/"intent.json").write_text('{"metadata":{"generation":1}}')
    (path/"deleted.json").write_text('{"deleted":true}')
    with pytest.raises(RuntimeNotFound):
        serving.get(row)

def test_evaluation_only_dataset_cannot_train(api):
    client,_=api
    artifact,_=register(client)
    response=client.post("/api/v1/datasets",headers=headers(),json={
      "name":"holdout-only","version":1,"uri":"s3://private/holdout.jsonl",
      "digest":"b"*64,"train_count":0,"heldout_count":24})
    assert response.status_code==201,response.text
    job=client.post("/api/v1/train-jobs",headers=headers(),json={
      "name":"invalid-eval-training","artifact_id":artifact["id"],
      "dataset_id":response.json()["id"],"output_name":"no-checkpoint"})
    assert job.status_code==422
