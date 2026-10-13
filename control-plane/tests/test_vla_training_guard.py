"""Prevent text-SFT substitution for a continuous-action policy."""
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location("vla_guard_fixtures",Path(__file__).with_name("test_api.py"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
api=m.api;headers=m.headers;register=m.register;model_payload=m.model_payload

def test_vla_cannot_be_submitted_to_argo_text_training(api):
    client,runtime=api
    _,dataset=register(client)
    payload=model_payload();payload.update(name="smolvla-guard",family="vla")
    model=client.post("/api/v1/models",headers=headers(),json=payload).json()
    response=client.post("/api/v1/train-jobs",headers=headers(),json={
      "name":"invalid-vla-text-sft","artifact_id":model["id"],"dataset_id":dataset["id"],
      "framework":"llama_factory","output_name":"invalid-policy"})
    assert response.status_code==422,response.text
    assert runtime.training_create_calls==0
