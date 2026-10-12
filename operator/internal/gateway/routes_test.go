package gateway

import (
 "context"
 "encoding/json"
 "fmt"
 "net/http"
 "net/http/httptest"
 "sync"
 "testing"
)

type fakeLiteLLM struct {
 mu sync.Mutex
 routes map[string]modelRecord
 next int
 creates,updates,deletes int
 failCreate bool
 foreign bool
 omitID bool
}
func newFakeLiteLLM()*fakeLiteLLM {return &fakeLiteLLM{routes:map[string]modelRecord{}}}
func (f *fakeLiteLLM) handler(w http.ResponseWriter,r *http.Request){
 f.mu.Lock();defer f.mu.Unlock()
 w.Header().Set("Content-Type","application/json")
 if r.Header.Get("Authorization")!="Bearer modelops-test-key" {
  w.WriteHeader(401);return
 }
 switch r.URL.Path {
 case "/model/info":
  data:=make([]modelRecord,0,len(f.routes))
  for _,v:=range f.routes{data=append(data,v)}
  if f.foreign {data=append(data,modelRecord{
   ModelName:"tenant--qwen",LiteLLMParams:LiteLLMParams{Model:"openai/foreign",APIBase:"http://foreign"},
   ModelInfo:ModelInfo{ID:"foreign-model"},
  })}
  if f.omitID {
   for i:=range data {data[i].ModelInfo.ID=""}
  }
  _=json.NewEncoder(w).Encode(map[string]any{"data":data})
 case "/model/new":
  if f.failCreate {w.WriteHeader(503);return}
  var route modelRecord
  if err:=json.NewDecoder(r.Body).Decode(&route);err!=nil{w.WriteHeader(400);return}
  f.next++;id:=fmt.Sprintf("lite-id-%d",f.next)
  route.ModelInfo.ID=id
  f.routes[id]=route
  f.creates++
  _=json.NewEncoder(w).Encode(map[string]string{"id":id})
 case "/model/update":
  var route modelRecord
  if err:=json.NewDecoder(r.Body).Decode(&route);err!=nil{w.WriteHeader(400);return}
  if _,ok:=f.routes[route.ModelInfo.ID];!ok {w.WriteHeader(404);return}
  f.routes[route.ModelInfo.ID]=route
  f.updates++
  _=json.NewEncoder(w).Encode(map[string]string{"status":"updated"})
 case "/model/delete":
  var payload struct{ID string `json:"id"`}
  if err:=json.NewDecoder(r.Body).Decode(&payload);err!=nil{w.WriteHeader(400);return}
  if _,ok:=f.routes[payload.ID];!ok {w.WriteHeader(404);return}
  delete(f.routes,payload.ID)
  f.deletes++
  _=json.NewEncoder(w).Encode(map[string]string{"status":"deleted"})
 default:
  w.WriteHeader(404)
 }
}

func (f *fakeLiteLLM) roles(t *testing.T)map[string]modelRecord{
 t.Helper()
 f.mu.Lock();defer f.mu.Unlock()
 out:=map[string]modelRecord{}
 for _,v:=range f.routes {
  out[v.ModelInfo.Metadata["slot"]]=v
 }
 return out
}

func TestManagedCanaryGroupConvergesWithoutDuplicates(t *testing.T){
 store:=newFakeLiteLLM()
 server:=httptest.NewServer(http.HandlerFunc(store.handler))
 defer server.Close()
 client:=NewHTTPClient(server.URL,"modelops-test-key")
 stable:=BuildOwnedRoute("tenant--qwen","tenant","qwen","stable","openai/qwen","http://stable:8000/v1",100)
 if err:=client.ReconcileModelGroup(context.Background(),"tenant--qwen",[]GatewayModel{stable});err!=nil{t.Fatal(err)}
 if err:=client.ReconcileModelGroup(context.Background(),"tenant--qwen",[]GatewayModel{stable});err!=nil{t.Fatal(err)}
 if store.creates!=1 || store.updates!=0 {t.Fatalf("reconcile duplicated stable model: creates %d updates %d",store.creates,store.updates)}
 stable.LiteLLMParams.Weight=ptrWeight(80)
 canary:=BuildOwnedRoute("tenant--qwen","tenant","qwen","canary","openai/qwen-canary","http://canary:8000/v1",20)
 if err:=client.ReconcileModelGroup(context.Background(),"tenant--qwen",[]GatewayModel{stable,canary});err!=nil{t.Fatal(err)}
 slots:=store.roles(t)
 if store.creates!=2 || store.updates!=1 || len(slots)!=2 {
  t.Fatalf("failed weighted group: creates %d updates %d roles %v",store.creates,store.updates,slots)
 }
 if slots["stable"].ModelName != slots["canary"].ModelName ||
  *slots["stable"].LiteLLMParams.Weight!=80 || *slots["canary"].LiteLLMParams.Weight!=20 {
   t.Fatalf("same public group with 80/20 weights required: %+v",slots)
 }
 if err:=client.ReconcileModelGroup(context.Background(),"tenant--qwen",[]GatewayModel{stable,canary});err!=nil{t.Fatal(err)}
 if store.creates!=2 || store.updates!=1 {
  t.Fatalf("repeated reconciliation wrote again: creates %d updates %d",store.creates,store.updates)
 }
 stable.LiteLLMParams.Weight=ptrWeight(100)
 if err:=client.ReconcileModelGroup(context.Background(),"tenant--qwen",[]GatewayModel{stable});err!=nil{t.Fatal(err)}
 if store.deletes!=1 || len(store.roles(t))!=1 ||
  *store.roles(t)["stable"].LiteLLMParams.Weight!=100 {
  t.Fatalf("canary rollback did not restore stable route: %+v",store.roles(t))
 }
 if err:=client.DeleteModelGroup(context.Background(),"tenant--qwen");err!=nil{t.Fatal(err)}
 if store.deletes!=2 || len(store.roles(t))!=0 {t.Fatal("finalizer should delete by LiteLLM deployment IDs")}
}
func ptrWeight(n int)*int {return &n}

func TestGroupCannotHijackAnotherModel(t *testing.T){
 store:=newFakeLiteLLM();store.foreign=true
 server:=httptest.NewServer(http.HandlerFunc(store.handler));defer server.Close()
 c:=NewHTTPClient(server.URL,"modelops-test-key")
 desired:=BuildOwnedRoute("tenant--qwen","tenant","qwen","stable","openai/qwen","http://stable",100)
 if err:=c.ReconcileModelGroup(context.Background(),"tenant--qwen",[]GatewayModel{desired});err==nil {
  t.Fatal("unmanaged same-name group must be rejected")
 }
 if store.creates!=0 || store.updates!=0 || store.deletes!=0 {t.Fatal("foreign group was modified")}
}
func TestGatewayRejectsBadWeightOrDuplicatedSlots(t *testing.T){
 c:=NewHTTPClient("http://127.0.0.1:1","modelops-test-key")
 stable:=BuildOwnedRoute("grp","ns","model","stable","openai/model","http://model",80)
 if err:=c.ReconcileModelGroup(context.Background(),"grp",[]GatewayModel{stable});err==nil {
  t.Fatal("group must total 100 percent")
 }
 stable.LiteLLMParams.Weight=ptrWeight(50)
 if err:=c.ReconcileModelGroup(context.Background(),"grp",[]GatewayModel{stable,stable});err==nil {
  t.Fatal("duplicate slot not allowed")
 }
}
func TestGatewayAdminFailureDoesNotClaimSuccess(t *testing.T){
 store:=newFakeLiteLLM();store.failCreate=true
 server:=httptest.NewServer(http.HandlerFunc(store.handler));defer server.Close()
 c:=NewHTTPClient(server.URL,"modelops-test-key")
 stable:=BuildOwnedRoute("tenant--qwen","tenant","qwen","stable","openai/qwen","http://stable",100)
 if err:=c.ReconcileModelGroup(context.Background(),"tenant--qwen",[]GatewayModel{stable});err==nil {
  t.Fatal("HTTP 503 must fail closed")
 }
}
func TestMissingDeploymentIDFailsClosed(t *testing.T){
 store:=newFakeLiteLLM()
 server:=httptest.NewServer(http.HandlerFunc(store.handler));defer server.Close()
 c:=NewHTTPClient(server.URL,"modelops-test-key")
 stable:=BuildOwnedRoute("tenant--qwen","tenant","qwen","stable","openai/qwen","http://stable",100)
 if err:=c.ReconcileModelGroup(context.Background(),"tenant--qwen",[]GatewayModel{stable});err!=nil{t.Fatal(err)}
 store.omitID=true
 if err:=c.DeleteModelGroup(context.Background(),"tenant--qwen");err==nil {
  t.Fatal("gateway must not guess delete ID from public name")
 }
}
