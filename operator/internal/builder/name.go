package builder

import "fmt"

// Kubernetes stable Pod/Service/PVCs and Canary resources add '-canary-cache'
// to the original CRD name. Enforce the longest generated suffix at admission
// to avoid accepting models whose child resources can never be created.
const MaxModelDeploymentNameLength = 63 - len("-canary-cache")

func ValidateDeploymentName(name string) error {
 if len(name)==0 || len(name)>MaxModelDeploymentNameLength {
  return fmt.Errorf("model deployment name must be 1..%d ASCII characters",MaxModelDeploymentNameLength)
 }
 for i:=0;i<len(name);i++ {
  c:=name[i]
  valid:= (c>='a' && c<='z') || (c>='0' && c<='9')
  if c=='-' && i>0 && i<len(name)-1 {valid=true}
  if !valid {return fmt.Errorf("invalid DNS-safe ModelDeployment name")}
 }
 return nil
}
