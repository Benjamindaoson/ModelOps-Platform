package controller

import (
    "fmt"
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
