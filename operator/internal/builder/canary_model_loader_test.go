package builder

import (
 "testing"

 v1alpha1 "github.com/kube-llmops/operator/api/v1alpha1"
 metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
 "k8s.io/utils/ptr"
)

func TestCanaryPodLoadsVersionedCheckpointAndSharesPVC(t *testing.T) {
 md:=&v1alpha1.ModelDeployment{
  ObjectMeta:metav1.ObjectMeta{
   Name:"candidate",Namespace:"tenant-a",
   Annotations:map[string]string{
    "modelops.io/artifact-revision":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "modelops.io/artifact-sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
   },
  },
  Spec:v1alpha1.ModelDeploymentSpec{
   Source:"Qwen/Qwen2.5-0.5B-Instruct",
   Replicas:ptr.To(int32(1)),
  },
 }
 dep:=BuildCanaryDeployment(md,"vllm",nil,"stable","Qwen--Qwen2.5-0.5B-Instruct-canary")
 if len(dep.Spec.Template.Spec.InitContainers)!=1 {
  t.Fatalf("canary requires verified model-loader before serving: %+v",dep.Spec.Template.Spec.InitContainers)
 }
 init:=dep.Spec.Template.Spec.InitContainers[0]
 if init.Image!="ghcr.io/benjamindaoson/modelops-model-loader:v0.1.0"{
  t.Fatalf("canary must use verified model-loader image: %s",init.Image)
 }
 env:=map[string]string{}
 for _,v:=range init.Env {
  env[v.Name]=v.Value
 }
 if env["MODEL_REVISION"]!=md.Annotations["modelops.io/artifact-revision"] ||
    env["MODEL_ARTIFACT_SHA256"]!=md.Annotations["modelops.io/artifact-sha256"] ||
    env["MODEL_SLUG"]!="Qwen--Qwen2.5-0.5B-Instruct-canary"{
  t.Fatalf("canary provenance is missing: %v",env)
 }
 if dep.Spec.Template.Spec.SecurityContext==nil ||
    dep.Spec.Template.Spec.SecurityContext.FSGroup==nil ||
    *dep.Spec.Template.Spec.SecurityContext.FSGroup!=10001{
  t.Fatal("nonroot canary loader cannot write unowned model PVC")
 }
}
