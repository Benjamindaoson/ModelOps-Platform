package controller

import (
  "testing"
  model "github.com/kube-llmops/operator/api/v1alpha1"
)

func dynamicRunForTest() *model.FineTuneRun {
 return &model.FineTuneRun{Spec:model.FineTuneRunSpec{
    BaseModel:"Qwen/Qwen2.5-0.5B-Instruct",
    BaseRevision:"c1234567890abcdef",
    BaseDigest:"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    DataSource:model.DataSourceSpec{Type:"minio",Path:"s3://datasets/run-a/",
      Digest:"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
    Method:"qlora",OutputName:"candidate",
    Training:model.TrainingSpec{Epochs:3,BatchSize:2,LearningRate:"0.0001",
      LoraRank:16,LoraAlpha:32,GradientAccumulationSteps:4},
    Resources:model.ModelResources{GPU:1},
    Evaluation:model.EvaluationSpec{Enabled:true,MinTokenF1:"0.6"},
 }}
}
func TestDynamicFineTunePositiveContract(t *testing.T){
 if err:=ValidateDynamicFineTuneRunSpec(dynamicRunForTest());err!=nil{t.Fatal(err)}
}
func TestDynamicFineTuneRejectMissingDigest(t *testing.T){
 f:=dynamicRunForTest();f.Spec.DataSource.Digest=""
 if ValidateDynamicFineTuneRunSpec(f)==nil {t.Fatal("dataset checksum mandatory")}
}
func TestDynamicFineTuneRejectUnsupportedAutodeploy(t *testing.T){
 f:=dynamicRunForTest();f.Spec.Deploy.Enabled=true
 if ValidateDynamicFineTuneRunSpec(f)==nil {t.Fatal("cannot auto-promote without independent approval")}
}
func TestDynamicFineTuneRejectOutOfRangeParams(t *testing.T){
 f:=dynamicRunForTest();f.Spec.Training.Epochs=0
 if ValidateDynamicFineTuneRunSpec(f)==nil {t.Fatal("incomplete hyperparameters must fail")}
}
func TestArgoParameterManifestParity(t *testing.T){
 params:=[]interface{}{map[string]interface{}{"name":"model"},map[string]interface{}{"name":"version"}}
 requested:=[]map[string]string{{"name":"model","value":"x"},{"name":"version","value":"y"}}
 if err:=DynamicTemplateHasParameters(params,requested);err!=nil{t.Fatal(err)}
 requested=append(requested,map[string]string{"name":"dataset_digest","value":"z"})
 if err:=DynamicTemplateHasParameters(params,requested);err==nil{t.Fatal("missing Argo parameter must be rejected")}
}
