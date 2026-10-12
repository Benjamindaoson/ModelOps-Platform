package controller

import(
 "testing"

 v1alpha1 "github.com/kube-llmops/operator/api/v1alpha1"
 metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func TestCanaryUsesSamePublicGroupForWeightedTraffic(t *testing.T){
 md:=&v1alpha1.ModelDeployment{
  ObjectMeta:metav1.ObjectMeta{Name:"qwen",Namespace:"tenant-a"},
  Status:v1alpha1.ModelDeploymentStatus{Endpoint:"http://stable:8000"},
 }
 routes,err:=desiredGatewayRoutes(md)
 if err!=nil || len(routes)!=1 {t.Fatalf("expected stable-only route: %+v %v",routes,err)}
 if routes[0].ModelName!="tenant-a--qwen" || *routes[0].LiteLLMParams.Weight!=100 {
  t.Fatalf("public model group is not tenant-safe: %+v",routes)
 }
 md.Spec.Canary=&v1alpha1.CanaryConfig{Source:"Qwen/new-version",Weight:20}
 md.Status.Canary=&v1alpha1.CanaryStatus{Phase:"Pending",Endpoint:"http://canary:8000"}
 routes,err=desiredGatewayRoutes(md)
 if err!=nil || len(routes)!=1 {t.Fatal("pending candidate must receive no production traffic")}
 md.Status.Canary.Phase="Ready"
 routes,err=desiredGatewayRoutes(md)
 if err!=nil || len(routes)!=2 {t.Fatalf("expected two weighted routes: %+v %v",routes,err)}
 if routes[0].ModelName!=routes[1].ModelName || routes[0].ModelName!="tenant-a--qwen"{
  t.Fatal("stable and canary public names differ")
 }
 if *routes[0].LiteLLMParams.Weight!=80 || *routes[1].LiteLLMParams.Weight!=20{
  t.Fatalf("weighted split incorrect: %+v",routes)
 }
 if routes[1].LiteLLMParams.Model!="openai/qwen-canary" ||
  routes[1].LiteLLMParams.APIBase!="http://canary:8000/v1"{
  t.Fatal("candidate must use own serving alias and OpenAI v1 endpoint")
 }
 md.Spec.Canary.Weight=0
 routes,err=desiredGatewayRoutes(md)
 if err!=nil || len(routes)!=1 || *routes[0].LiteLLMParams.Weight!=100 {t.Fatal("0% must be all stable")}
 md.Spec.Canary.Weight=100
 routes,err=desiredGatewayRoutes(md)
 if err!=nil || len(routes)!=1 || routes[0].ModelInfo.Metadata["slot"]!="canary" ||
  *routes[0].LiteLLMParams.Weight!=100 {t.Fatal("100% must contain only candidate")}
}
