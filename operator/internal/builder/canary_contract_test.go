package builder

import (
  "testing"

  metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
  v1alpha1 "github.com/kube-llmops/operator/api/v1alpha1"
)

func TestServingServicePortsMatchRuntimeEngine(t *testing.T) {
  md := &v1alpha1.ModelDeployment{ObjectMeta: metav1.ObjectMeta{Name:"model",Namespace:"modelops"}}
  for _, tc := range []struct{engine string; port int32}{
    {"vllm",8000}, {"sglang",30000}, {"tei",8080}, {"llamacpp",8080},
  } {
    s := BuildService(md,tc.engine)
    if len(s.Spec.Ports)!=1 || s.Spec.Ports[0].Port!=tc.port {
      t.Errorf("engine %s expected %d, got %+v",tc.engine,tc.port,s.Spec.Ports)
    }
    canary := BuildCanaryService(md,tc.engine,md.Name)
    if len(canary.Spec.Ports)!=1 || canary.Spec.Ports[0].Port!=tc.port {
      t.Errorf("canary engine %s expected %d, got %+v",tc.engine,tc.port,canary.Spec.Ports)
    }
  }
}

func TestCanaryPVCUsesStorageResourceRequirements(t *testing.T) {
  md := &v1alpha1.ModelDeployment{ObjectMeta: metav1.ObjectMeta{Name:"demo",Namespace:"modelops"}}
  pvc := BuildCanaryPVC(md,"demo-canary")
  if pvc.Spec.Resources.Requests.Storage().IsZero() {
    t.Fatal("Canary PVC storage request is required")
  }
}
