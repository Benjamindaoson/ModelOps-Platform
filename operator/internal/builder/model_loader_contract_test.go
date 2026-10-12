package builder

import (
  "testing"

  model "github.com/kube-llmops/operator/api/v1alpha1"
  metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func TestModelLoaderDownloadsPinnedCheckpointWithoutInlineSecrets(t *testing.T) {
  md:=&model.ModelDeployment{
    ObjectMeta:metav1.ObjectMeta{Name:"pinned",Namespace:"tenant",
      Annotations:map[string]string{
        "modelops.io/artifact-revision":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "modelops.io/artifact-sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      }},
    Spec:model.ModelDeploymentSpec{Source:"Qwen/Qwen2.5-0.5B-Instruct"},
  }
  got:=buildInitContainers(md,nil,"Qwen--Qwen2.5-0.5B-Instruct")
  if len(got)!=1 {t.Fatal("real model-loader must be present without LLMPlatform")}
  c:=got[0]
  if c.Image!="ghcr.io/benjamindaoson/modelops-model-loader:v0.1.0" {
    t.Fatalf("wrong image: %s",c.Image)
  }
  m:=map[string]bool{}
  for _,env:=range c.Env {
    m[env.Name]=true
    if env.Name=="MODEL_REVISION" && env.Value!=md.Annotations["modelops.io/artifact-revision"] { t.Fatal("model revision not pinned") }
    if env.Name=="MODEL_ARTIFACT_SHA256" && env.Value!=md.Annotations["modelops.io/artifact-sha256"] {t.Fatal("sha not forwarded")}
    if env.Name=="HF_TOKEN" && (env.ValueFrom==nil || env.Value!="") {
      t.Fatal("HF token must be Kubernetes Secret-backed")
    }
  }
  if !m["MODEL_REVISION"] || !m["MODEL_ARTIFACT_SHA256"] {t.Fatal("missing provenance")}
}

func TestMinioLoaderCredentialsNeverAppearAsInlinePodValues(t *testing.T) {
  md:=&model.ModelDeployment{
    ObjectMeta:metav1.ObjectMeta{Name:"s3model",Namespace:"tenant"},
    Spec:model.ModelDeploymentSpec{Source:"s3://models/checkpoints/version-1/"},
  }
  containers:=buildInitContainers(md,nil,"s3-model")
  for _,env:=range containers[0].Env {
    if env.Name=="MODELOPS_S3_ACCESS_KEY" || env.Name=="MODELOPS_S3_SECRET_KEY" {
      if env.Value!="" || env.ValueFrom==nil || env.ValueFrom.SecretKeyRef==nil ||
         env.ValueFrom.SecretKeyRef.Name!="modelops-objectstore" {
        t.Errorf("%s should only come from tenant Kubernetes Secret",env.Name)
      }
    }
  }
}
