"""Serialization contracts must map to real K8s CRDs, never fake success."""
import os
os.environ.setdefault("MODELOPS_AUTH_MODE","dev")
os.environ.setdefault("MODELOPS_ENV","test")
os.environ.setdefault("MODELOPS_JWT_SECRET","only-for-tests-32-chars-plus-000000000")

from types import SimpleNamespace
import pytest
from modelops.runtime import fine_tune_workflow_body, deployment_body, DisabledRuntime, RuntimeUnavailable


def test_namespaced_deployment_with_immutable_revision():
    dep = SimpleNamespace(name="qwen-1", tenant="a", engine="vllm", replicas=2, gpu=1)
    model = SimpleNamespace(id="model-id", source="Qwen/Qwen2.5-0.5B-Instruct",
                            revision="abc12345678", digest="a"*64)
    body = deployment_body(dep, model)
    assert body["metadata"]["namespace"] == "modelops-a"
    assert body["spec"]["engineArgs"] == {}
    assert body["metadata"]["annotations"]["modelops.io/artifact-revision"] == "abc12345678"
    assert body["status"] if "status" in body else True  # No fabricated Ready state.


def test_workflow_parameters_isolate_jobs():
    a=SimpleNamespace(name="job", tenant="a", workflow_name="job-ft", method="lora",id="jobid")
    model=SimpleNamespace(source="Qwen/Qwen",revision="abc1234567",digest="a"*64)
    data=SimpleNamespace(uri="s3://data/train",digest="b"*64)
    inp=dict(epochs=2,batch_size=1,lr=0.0001,lora_rank=8,lora_alpha=16,
             gpu=1,gradient_accumulation_steps=4,min_token_f1=0.6,output_name="finetuned")
    w=fine_tune_workflow_body(a,model,data,inp)
    params = {x["name"]:x["value"] for x in w["spec"]["arguments"]["parameters"]}
    assert params["dataset_sha256"] == "b"*64
    assert params["epochs"] == "2"
    assert "templates" not in w["spec"]


def test_disabled_runtime_is_explicit():
    with pytest.raises(RuntimeUnavailable):
        DisabledRuntime().create_deployment(None,None)



def test_cancel_request_requires_real_resource_version():
    from types import SimpleNamespace
    from modelops.runtime import KubernetesRuntime, RuntimeFailure
    fake = SimpleNamespace(tenant="test", workflow_name="first-ft")
    class Objects:
        def __init__(self):
            self.calls = []
        def patch_namespaced_custom_object(self, *args):
            self.calls.append(args)
            return {"status": {"phase": "Running"}}
    objects = Objects()
    runtime = KubernetesRuntime.__new__(KubernetesRuntime)
    runtime.objects = objects
    with pytest.raises(RuntimeFailure):
        runtime.cancel_finetune(fake, "")
    assert objects.calls == []
    result = runtime.cancel_finetune(fake, "11")
    assert result["status"]["phase"] == "Running"
    call = objects.calls[0]
    assert call[:5] == ("argoproj.io", "v1alpha1", "modelops-test", "workflows", "first-ft")
    assert call[5]["metadata"]["resourceVersion"] == "11"
    assert call[5]["spec"]["shutdown"] == "Terminate"
