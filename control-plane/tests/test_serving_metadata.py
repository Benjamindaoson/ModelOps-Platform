"""Unified Deployment configuration and bounded inference API contracts."""
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location("serving_fixtures",Path(__file__).with_name("test_api.py"))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
api=module.api;headers=module.headers;register=module.register

def test_deployment_config_is_persisted_and_rendered(api):
    client,runtime=api
    model,_=register(client)
    response=client.post("/api/v1/deployments",headers=headers(),json={
        "name":"quantized-serving","artifact_id":model["id"],"engine":"vllm","gpu":1,
        "quantization":"awq","cache":True})
    assert response.status_code==201,response.text
    row=response.json()
    assert row["quantization"]=="awq" and row["cache"] is True
    body=runtime.deployments[("alpha",row["name"])]
    assert body["spec"]["quantization"]=="awq"
    assert body["spec"]["cache"]["prefixCaching"] is True
    assert body["spec"]["model"]["id"]==model["id"]

def test_metrics_are_tenant_scoped_and_require_privilege(api):
    client,_=api
    register(client)
    assert client.get("/metrics").status_code==401
    response=client.get("/metrics",headers=headers())
    assert response.status_code==200,response.text
    assert "modelops_training_jobs_total" in response.text
    assert "modelops_deployment_status" in response.text
    assert "modelops_inference_latency" in response.text
    assert "modelops_gpu_usage" in response.text

def test_inference_is_owned_and_fails_closed_without_ready_backend(api):
    client,_=api
    model,_=register(client)
    d=client.post("/api/v1/deployments",headers=headers(),json={
      "name":"not-ready","artifact_id":model["id"],"engine":"vllm"}).json()
    url="/api/v1/deployments/"+d["id"]+"/infer"
    assert client.post(url,headers=headers("beta"),json={"input":"hello"}).status_code==404
    assert client.post(url,headers=headers(),json={"messages":[]}).status_code==503

def test_custom_policy_protocol_survives_api_serialization(api):
    client,runtime=api
    model,_=register(client)
    protocol={"image":"example.invalid/policy@sha256:"+"a"*64,
       "command":["python","-m","policy_server"],"args":["--port","8001"],"port":8001,"healthPath":"/health"}
    response=client.post("/api/v1/deployments",headers=headers(),json={
       "name":"custom-protocol-contract","artifact_id":model["id"],"engine":"custom","custom":protocol})
    assert response.status_code==201,response.text
    body=runtime.deployments[("alpha",response.json()["name"])]
    assert body["spec"]["custom"]==protocol
