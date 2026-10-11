package controller

import (
    "testing"

    v1alpha1 "github.com/kube-llmops/operator/api/v1alpha1"
)

func validTemplate() (*v1alpha1.FineTuneRun,map[string]string) {
    ftr:=&v1alpha1.FineTuneRun{Spec:v1alpha1.FineTuneRunSpec{
        BaseModel:"Qwen/Qwen2.5-0.5B-Instruct",OutputName:"qwen-ft",Method:"lora",
        DataSource:v1alpha1.DataSourceSpec{Type:"minio",Path:"s3://datasets/train/",Format:"alpaca"},
    }}
    a:=map[string]string{
        "modelops.io/base-model":"Qwen/Qwen2.5-0.5B-Instruct",
        "modelops.io/output-name":"qwen-ft",
        "modelops.io/method":"lora",
        "modelops.io/data-source-type":"minio",
        "modelops.io/data-source-path":"s3://datasets/train/",
        "modelops.io/data-source-format":"alpaca",
        "modelops.io/deploy-auto":"false",
        "modelops.io/canary-percent":"20",
    }
    return ftr,a
}
func TestFineTuneTemplateIdentityValid(t *testing.T){
    f,a:=validTemplate()
    if err:=VerifyFineTuneTemplateContract(f,a);err!=nil {t.Fatal(err)}
}
func TestFineTuneTemplateRejectsMismatchedModel(t *testing.T){
    f,a:=validTemplate()
    f.Spec.BaseModel="other/base"
    if VerifyFineTuneTemplateContract(f,a)==nil {t.Fatal("mismatched model must fail")}
}
func TestFineTuneTemplateRejectsMismatchedData(t *testing.T){
    f,a:=validTemplate()
    f.Spec.DataSource.Path="other/path"
    if VerifyFineTuneTemplateContract(f,a)==nil {t.Fatal("mismatched dataset must fail")}
}
func TestFineTuneTemplateRejectsSilentlyIgnoredOverrides(t *testing.T){
    f,a:=validTemplate()
    f.Spec.Training.LoraRank=128
    if VerifyFineTuneTemplateContract(f,a)==nil {t.Fatal("silently ignored training params") }
}
func TestFineTuneTemplateRejectsUnexpectedGPU(t *testing.T){
    f,a:=validTemplate()
    f.Spec.Resources.GPU=2
    if VerifyFineTuneTemplateContract(f,a)==nil {t.Fatal("silently ignored GPU resources") }
}
func TestFineTuneTemplateRejectsUnsupportedAutoDeploy(t *testing.T){
    f,a:=validTemplate()
    f.Spec.Deploy.Enabled=true
    if VerifyFineTuneTemplateContract(f,a)==nil {t.Fatal("silent auto promotion") }
}
