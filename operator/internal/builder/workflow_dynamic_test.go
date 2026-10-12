package builder

import (
  "testing"

  model "github.com/kube-llmops/operator/api/v1alpha1"
  metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
  "k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
)

var requiredDynamicNames = []string{
  "base_model","base_revision","base_sha256","dataset_uri","dataset_sha256",
  "method","output_name","epochs","batch_size","learning_rate","lora_rank",
  "lora_alpha","gpu","gradient_accumulation_steps","min_token_f1",
}

func dynamicFixture() *model.FineTuneRun {
  return &model.FineTuneRun{
    ObjectMeta:metav1.ObjectMeta{Name:"train",Namespace:"tenant-a"},
    Spec:model.FineTuneRunSpec{
      BaseModel:"Qwen/Qwen2.5-0.5B-Instruct",
      BaseRevision:"c1234567890abcdef",
      BaseDigest:"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      DataSource:model.DataSourceSpec{
        Type:"minio",Path:"s3://datasets/run-a/",Digest:"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      },
      OutputName:"candidate",Method:"qlora",
      Training:model.TrainingSpec{
        Epochs:3,BatchSize:2,LearningRate:"0.0001",LoraRank:16,LoraAlpha:32,
        GradientAccumulationSteps:4,
      },
      Resources:model.ModelResources{GPU:1},
      Evaluation:model.EvaluationSpec{Enabled:true,MinTokenF1:"0.6"},
    },
  }
}

func TestDynamicFineTuneWorkflowMatchesArgoParameters(t *testing.T){
  ftr:=dynamicFixture()
  if !IsDynamicFineTuneRun(ftr) {t.Fatal("versioned workflow must select dynamic Argo path")}
  wf:=BuildArgoWorkflow(ftr,"kube-llmops")
  ref,found,err:=unstructured.NestedString(wf.Object,"spec","workflowTemplateRef","name")
  if err!=nil || !found || ref!="modelops-finetune-dynamic" {
    t.Fatalf("expected dynamic Argo ref, got %s (%v)",ref,err)
  }
  params,found,err:=unstructured.NestedSlice(wf.Object,"spec","arguments","parameters")
  if err!=nil || !found || len(params)!=len(requiredDynamicNames) {
    t.Fatalf("parameter count: %d; err %v",len(params),err)
  }
  actual:=map[string]string{}
  for _,p:=range params {
    obj:=p.(map[string]interface{})
    actual[obj["name"].(string)]=obj["value"].(string)
  }
  for _,key:=range requiredDynamicNames {
    if _,ok:=actual[key];!ok {t.Errorf("missing dynamic parameter %s",key)}
  }
  if actual["learning_rate"]!="0.0001" || actual["lora_rank"]!="16" ||
     actual["dataset_sha256"]!=ftr.Spec.DataSource.Digest {
    t.Fatalf("per-run values missing from actual Argo request: %+v",actual)
  }
}
