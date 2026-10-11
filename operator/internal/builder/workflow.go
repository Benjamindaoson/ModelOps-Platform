package builder

import (
    "fmt"
    "strings"

    v1alpha1 "github.com/kube-llmops/operator/api/v1alpha1"
    "k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
)

// BuildArgoWorkflow references the *real* Helm-managed WorkflowTemplate.
// The previous builder authored six empty Docker containers. Those were
// no-op tasks which could report Succeeded without any model training.
// Identity and override validation happen in the reconciler before creation.
func BuildArgoWorkflow(ftr *v1alpha1.FineTuneRun, releaseName string) *unstructured.Unstructured {
    outputTrunc := ftr.Spec.OutputName
    if len(outputTrunc)>8 { outputTrunc = outputTrunc[:8] }
    name:=strings.TrimRight(fmt.Sprintf("%s-%s",ftr.Name,outputTrunc),"-")
    return &unstructured.Unstructured{
        Object:map[string]interface{}{
            "apiVersion":"argoproj.io/v1alpha1",
            "kind":"Workflow",
            "metadata":map[string]interface{}{
                "name":name,
                "namespace":ftr.Namespace,
                "labels":map[string]interface{}{
                    "app.kubernetes.io/name":"finetune",
                    "app.kubernetes.io/part-of":"modelops-platform",
                    "modelops.io/finetunerun":ftr.Name,
                },
            },
            "spec":map[string]interface{}{
                "workflowTemplateRef":map[string]interface{}{
                    "name":releaseName+"-finetune",
                },
            },
        },
    }
}
