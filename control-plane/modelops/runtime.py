"""Real Kubernetes CustomObjects runtime. There is deliberately NO production fake fallback."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

GROUP = "llmops.kubellmops.io"
VERSION = "v1alpha1"


class RuntimeUnavailable(RuntimeError):
    pass


class RuntimeFailure(RuntimeError):
    pass


class RuntimeNotFound(RuntimeFailure):
    """A specifically missing Kubernetes object, not a generic outage."""
    pass


def namespace_for(tenant: str) -> str:
    return "modelops-" + tenant


def deployment_body(dep, artifact) -> dict:
    # Runtime identity is a tenant-scoped K8s namespace, never a user-supplied
    # arbitrary namespace. The namespace must already exist.
    # A pinned revision is consumed by the model-loader init container.
    # Backend CLIs receive only a verified local model path; --revision is
    # not universally supported for local model files.
    args = {}
    return {
        "apiVersion": GROUP + "/" + VERSION, "kind": "ModelDeployment",
        "metadata": {
            "name": dep.name, "namespace": namespace_for(dep.tenant),
            "labels": {"app.kubernetes.io/part-of": "modelops"},
            "annotations": {
                "modelops.io/artifact-id": artifact.id,
                "modelops.io/artifact-sha256": artifact.digest,
                "modelops.io/artifact-revision": artifact.revision,
                "modelops.io/tenant": dep.tenant,
            },
        },
        "spec": {
            "source": artifact.source, "engine": dep.engine,
            "replicas": dep.replicas, "resources": {
                "gpu": dep.gpu, "cpu": "4", "memory": "16Gi",
            }, "engineArgs": args,
        },
    }


def fine_tune_workflow_body(job, artifact, dataset, parameters: dict) -> dict:
    """Argo dynamic template with explicit immutable inputs, not fixed Helm values."""
    vals = {
        "base_model": artifact.source,
        "base_revision": artifact.revision,
        "base_sha256": artifact.digest,
        "dataset_uri": dataset.uri,
        "dataset_sha256": dataset.digest,
        "method": job.method,
        "output_name": parameters["output_name"],
        "epochs": str(parameters["epochs"]),
        "batch_size": str(parameters["batch_size"]),
        "learning_rate": str(parameters["lr"]),
        "lora_rank": str(parameters["lora_rank"]),
        "lora_alpha": str(parameters["lora_alpha"]),
        "gpu": str(parameters["gpu"]),
        "gradient_accumulation_steps": str(parameters["gradient_accumulation_steps"]),
        "min_token_f1": str(parameters["min_token_f1"]),
    }
    return {
        "apiVersion": "argoproj.io/v1alpha1", "kind": "Workflow",
        "metadata": {"name": job.workflow_name, "namespace": namespace_for(job.tenant),
                     "labels": {"modelops.io/tenant": job.tenant, "modelops.io/job-id": job.id}},
        "spec": {
            "workflowTemplateRef": {"name": "modelops-finetune-dynamic"},
            "arguments": {"parameters": [{"name": k, "value": str(v)} for k, v in vals.items()]},
        },
    }


class DisabledRuntime:
    connected = False
    def _deny(self, *args, **kwargs):
        raise RuntimeUnavailable("Kubernetes runtime is disconnected; no fake deployment was created")
    create_deployment = _deny
    patch_deployment = _deny
    patch_canary = _deny
    get_deployment = _deny
    delete_deployment = _deny
    submit_finetune = _deny
    get_finetune = _deny
    cancel_finetune = _deny


class KubernetesRuntime:
    connected = True

    def __init__(self, context: str = "") -> None:
        try:
            from kubernetes import client, config
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config(context=context or None)
            self.objects = client.CustomObjectsApi()
        except Exception as exc:
            raise RuntimeUnavailable("Kubernetes config unavailable; refusing simulated success") from exc

    @staticmethod
    def _run(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if getattr(exc, "status", None) == 404:
                raise RuntimeNotFound("Requested Kubernetes object is absent") from exc
            raise RuntimeFailure("Kubernetes API request failed; inspect cluster events") from exc

    def create_deployment(self, dep, artifact):
        return self._run(self.objects.create_namespaced_custom_object, GROUP, VERSION,
                         namespace_for(dep.tenant), "modeldeployments", deployment_body(dep, artifact))

    def patch_deployment(self, dep, artifact):
        # Merge-patch only approved fields. Runtime observed state comes from K8s.
        return self._run(self.objects.patch_namespaced_custom_object, GROUP, VERSION,
                         namespace_for(dep.tenant), "modeldeployments", dep.name,
                         {"metadata": {"annotations": {
                             "modelops.io/artifact-id": artifact.id,
                             "modelops.io/artifact-sha256": artifact.digest,
                             "modelops.io/artifact-revision": artifact.revision,
                         }},
                          "spec": {"source": artifact.source, "replicas": dep.replicas,
                                   "engineArgs": None,
                                   **({"canary": None} if dep.canary_artifact_id is None else {})}})

    def patch_canary(self, dep, candidate, weight: int):
        if not 0 <= weight <= 100:
            raise ValueError("Canary weight must be in 0..100")
        spec = {"canary": None if candidate is None else {
            "source": candidate.source,
            "revision": candidate.revision,
            "digest": candidate.digest,
            "weight": weight,
            "resources": {"gpu": dep.gpu, "cpu": "4", "memory": "16Gi"},
        }}
        return self._run(self.objects.patch_namespaced_custom_object,
                         GROUP, VERSION, namespace_for(dep.tenant),
                         "modeldeployments", dep.name, {"spec": spec})

    def get_deployment(self, dep):
        return self._run(self.objects.get_namespaced_custom_object, GROUP, VERSION,
                         namespace_for(dep.tenant), "modeldeployments", dep.name)

    def delete_deployment(self, dep):
        return self._run(self.objects.delete_namespaced_custom_object, GROUP, VERSION,
                         namespace_for(dep.tenant), "modeldeployments", dep.name)

    def submit_finetune(self, job, artifact, dataset, parameters):
        return self._run(self.objects.create_namespaced_custom_object,
                         "argoproj.io", "v1alpha1", namespace_for(job.tenant),
                         "workflows", fine_tune_workflow_body(job, artifact, dataset, parameters))

    def get_finetune(self, job):
        return self._run(self.objects.get_namespaced_custom_object,
                         "argoproj.io", "v1alpha1", namespace_for(job.tenant),
                         "workflows", job.workflow_name)

    def cancel_finetune(self, job, resource_version: str):
        if not resource_version:
            raise RuntimeFailure("Argo resourceVersion is mandatory before terminating a Workflow")
        # Argo shutdown=Terminate is a REQUEST. The observed phase is polled
        # independently; a successful PATCH is not "training stopped".
        return self._run(self.objects.patch_namespaced_custom_object,
                         "argoproj.io", "v1alpha1", namespace_for(job.tenant),
                         "workflows", job.workflow_name, {
                             "metadata": {"resourceVersion": resource_version},
                             "spec": {"shutdown": "Terminate"},
                         })
