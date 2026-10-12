package controller

import (
    "fmt"
    "regexp"
    "strconv"
    "strings"

    v1alpha1 "github.com/kube-llmops/operator/api/v1alpha1"
)

// VerifyFineTuneTemplateContract prevents a requested fine-tune from
// silently executing a *different* fixed Helm WorkflowTemplate.
// Per-run overrides must be implemented as Argo parameters, not ignored.
func VerifyFineTuneTemplateContract(ftr *v1alpha1.FineTuneRun, annotations map[string]string) error {
    expected:=map[string]string{
        "modelops.io/base-model":ftr.Spec.BaseModel,
        "modelops.io/output-name":ftr.Spec.OutputName,
        "modelops.io/method":ftr.Spec.Method,
        "modelops.io/data-source-type":ftr.Spec.DataSource.Type,
        "modelops.io/data-source-path":ftr.Spec.DataSource.Path,
    }
    if expected["modelops.io/method"]=="" { expected["modelops.io/method"]="lora" }
    if ftr.Spec.DataSource.Format!="" && ftr.Spec.DataSource.Format!=annotations["modelops.io/data-source-format"] {
        return fmt.Errorf("data source format differs from configured WorkflowTemplate")
    }
    for k,want:=range expected {
        if strings.TrimSpace(want)=="" || annotations[k]!=want {
            return fmt.Errorf("workflow template mismatch for %s: customize the Helm release or use its configured values",k)
        }
    }
    // Reject unsupported per-job overrides rather than quietly discarding them.
    tr:=ftr.Spec.Training
    if tr.Epochs!=0 || tr.BatchSize!=0 || tr.LearningRate!="" || tr.GradientAccumulationSteps!=0 ||
        tr.WarmupRatio!="" || tr.LoraRank!=0 || tr.LoraAlpha!=0 || tr.LoraTarget!="" {
        return fmt.Errorf("FineTuneRun per-job training overrides are not parameterized; configure the Helm release")
    }
    rs:=ftr.Spec.Resources
    if rs.GPU!=0 || rs.Memory!="" || rs.CPU!="" {
        return fmt.Errorf("FineTuneRun per-job resources are not parameterized; configure the Helm release")
    }
    if ftr.Spec.Evaluation.Dataset!="" || ftr.Spec.QualityGate.Thresholds.MinEvalLoss!="" ||
        ftr.Spec.QualityGate.Thresholds.MaxTrainLoss!="" {
        return fmt.Errorf("FineTuneRun per-job evaluation/quality overrides are not supported by the Helm WorkflowTemplate")
    }
    if ftr.Spec.Deploy.Enabled && annotations["modelops.io/deploy-auto"]!="true" {
        return fmt.Errorf("requested automatic promotion but Helm deploy.auto is disabled")
    }
    if ftr.Spec.Deploy.CanaryWeight!=0 {
        expectedWeight,err:=strconv.Atoi(annotations["modelops.io/canary-percent"])
        if err!=nil || int32(expectedWeight)!=ftr.Spec.Deploy.CanaryWeight{
            return fmt.Errorf("requested canary percentage differs from Helm WorkflowTemplate")
        }
    }
    return nil
}

// Dynamic Argo jobs must have independently versioned inputs and valid,
// actionable per-run settings. Never silently fall back to fixed Helm values.
func ValidateDynamicFineTuneRunSpec(f *v1alpha1.FineTuneRun) error {
	s := f.Spec
	hex := regexp.MustCompile("^[a-f0-9]{64}$")
	if s.BaseModel == "" || len(s.BaseRevision) < 7 || !hex.MatchString(s.BaseDigest) {
		return fmt.Errorf("dynamic fine-tuning requires pinned baseModel/baseRevision/baseDigest")
	}
	if !hex.MatchString(s.DataSource.Digest) {
		return fmt.Errorf("dynamic fine-tuning requires a dataset manifest SHA-256")
	}
	if !strings.HasPrefix(s.DataSource.Path,"s3://") && !strings.HasPrefix(s.DataSource.Path,"hf://") {
		return fmt.Errorf("dynamic dataset URI must use s3:// or hf://")
	}
	if s.OutputName == "" || (s.Method!="lora" && s.Method!="qlora" && s.Method!="full" && s.Method!="") {
		return fmt.Errorf("dynamic output name or fine-tuning method invalid")
	}
	t := s.Training
	if t.Epochs < 1 || t.Epochs > 30 || t.BatchSize < 1 || t.BatchSize > 256 ||
		t.GradientAccumulationSteps < 1 || t.GradientAccumulationSteps > 256 ||
		t.LoraRank < 1 || t.LoraRank > 256 || t.LoraAlpha < 1 || t.LoraAlpha > 512 {
		return fmt.Errorf("dynamic fine-tuning hyperparameters outside supported range")
	}
	learningRate,err:=strconv.ParseFloat(t.LearningRate,64)
	if err!=nil || learningRate<=0 || learningRate>0.01 { return fmt.Errorf("invalid learning rate") }
	f1,err:=strconv.ParseFloat(s.Evaluation.MinTokenF1,64)
	if err!=nil || f1<0 || f1>1 { return fmt.Errorf("minTokenF1 must be in [0,1]") }
	if s.Resources.GPU < 1 || s.Resources.GPU > 16 { return fmt.Errorf("dynamic GPU resources must be 1..16") }
	if s.Deploy.Enabled { return fmt.Errorf("dynamic workflows publish only; release requires separate approval") }
	return nil
}

// DynamicTemplateHasParameters verifies that Helm actually deployed all
// parameters the builder will submit, catching Go/Argo protocol drift.
func DynamicTemplateHasParameters(parameters []interface{}, required []map[string]string) error {
	available:=map[string]bool{}
	for _,entry:=range parameters {
		obj,ok:=entry.(map[string]interface{})
		if !ok { continue }
		name,ok:=obj["name"].(string)
		if ok { available[name]=true }
	}
	for _,item:=range required {
		if !available[item["name"]] { return fmt.Errorf("Argo WorkflowTemplate missing %s parameter",item["name"]) }
	}
	return nil
}

