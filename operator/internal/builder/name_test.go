package builder

import (
 "strings"
 "testing"
)

func TestValidateDeploymentNameReservesCanaryPVCName(t *testing.T) {
 if MaxModelDeploymentNameLength+len("-canary-cache")!=63 {
  t.Fatalf("wrong generated suffix name bound: %d",MaxModelDeploymentNameLength)
 }
 for _,name:=range []string{"qwen",strings.Repeat("a",MaxModelDeploymentNameLength),"model-01"} {
  if err:=ValidateDeploymentName(name);err!=nil {t.Fatalf("valid %q: %v",name,err)}
 }
 for _,name:=range []string{"",strings.Repeat("a",MaxModelDeploymentNameLength+1),
  "-invalid","invalid-","Capitals","../kube-system","多模态","model_name"} {
  if err:=ValidateDeploymentName(name);err==nil {t.Errorf("accepted invalid %q",name)}
 }
}
