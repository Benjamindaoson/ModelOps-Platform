package builder

import (
    "testing"

    v1alpha1 "github.com/kube-llmops/operator/api/v1alpha1"
    metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
    "k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
)

func TestBuildArgoWorkflowUsesRealHelmWorkflowTemplate(t *testing.T){
    ftr:=&v1alpha1.FineTuneRun{
        ObjectMeta:metav1.ObjectMeta{Name:"job",Namespace:"team"},
        Spec:v1alpha1.FineTuneRunSpec{
            BaseModel:"Qwen/Qwen2.5-0.5B-Instruct",
            OutputName:"qwen-finetuned-v1",
            Method:"lora",
        },
    }
    got:=BuildArgoWorkflow(ftr,"modelops")
    if got.GetKind()!="Workflow" || got.GetNamespace()!="team" { t.Fatal("invalid workflow identity") }
    if got.GetName()!="job-qwen-fin" { t.Fatalf("unexpected name: %s",got.GetName()) }
    ref,found,err:=unstructured.NestedString(got.Object,"spec","workflowTemplateRef","name")
    if err!=nil || !found || ref!="modelops-finetune" {t.Fatalf("must reference actual Helm WorkflowTemplate: %q, %v",ref,err)}
    if _,found,_:=unstructured.NestedSlice(got.Object,"spec","templates");found {
        t.Fatal("inline no-op task containers must never be generated")
    }
    if _,found,_:=unstructured.NestedString(got.Object,"spec","entrypoint");found {
        t.Fatal("entrypoint is the Helm template's responsibility")
    }
}
func TestBuildArgoWorkflowStableName(t *testing.T){
    ftr:=&v1alpha1.FineTuneRun{ObjectMeta:metav1.ObjectMeta{Name:"x",Namespace:"ns"},
        Spec:v1alpha1.FineTuneRunSpec{OutputName:"abc"}}
    if BuildArgoWorkflow(ftr,"test").GetName()!="x-abc" { t.Fatal("bad name") }
}
