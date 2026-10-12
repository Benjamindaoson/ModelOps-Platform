package gateway

import (
 "bytes"
 "context"
 "encoding/json"
 "fmt"
 "io"
 "net/http"
 "strings"
)

// RouteManager converges the public LiteLLM model group without duplicate
// /model/new calls. Production must support this interface; silently falling
// back to separate candidate names cannot provide weighted traffic.
type RouteManager interface {
 ReconcileModelGroup(context.Context,string,[]GatewayModel) error
 DeleteModelGroup(context.Context,string) error
}

type modelRecord struct {
 ModelName string `json:"model_name"`
 LiteLLMParams LiteLLMParams `json:"litellm_params"`
 ModelInfo ModelInfo `json:"model_info"`
}
type modelListing struct {
 Data []json.RawMessage `json:"data"`
}

func (c *HTTPClient) adminRequest(ctx context.Context,method,route string,payload any,out any) error {
 var reader io.Reader
 if payload!=nil {
  data,err:=json.Marshal(payload);if err!=nil{return fmt.Errorf("marshal LiteLLM request: %w",err)}
  reader=bytes.NewReader(data)
 }
 if c.masterKey=="" {return fmt.Errorf("LiteLLM admin key missing")}
 req,err:=http.NewRequestWithContext(ctx,method,strings.TrimRight(c.baseURL,"/")+route,reader)
 if err!=nil {return fmt.Errorf("build LiteLLM request: %w",err)}
 req.Header.Set("Authorization","Bearer "+c.masterKey)
 if payload!=nil {req.Header.Set("Content-Type","application/json")}
 resp,err:=c.httpClient.Do(req)
 if err!=nil{return fmt.Errorf("LiteLLM %s transport error: %w",route,err)}
 defer resp.Body.Close()
 if resp.StatusCode<200 || resp.StatusCode>=300 {
  // Do not propagate remote body; it might contain credentials.
  return fmt.Errorf("LiteLLM %s HTTP %d",route,resp.StatusCode)
 }
 if out!=nil {
  if err:=json.NewDecoder(io.LimitReader(resp.Body,16<<20)).Decode(out);err!=nil {
   return fmt.Errorf("LiteLLM %s returned invalid JSON: %w",route,err)
  }
 }
 return nil
}

func (c *HTTPClient) listGroup(ctx context.Context,group string)([]modelRecord,error) {
 var response modelListing
 if err:=c.adminRequest(ctx,http.MethodGet,"/model/info",nil,&response);err!=nil{return nil,err}
 var found []modelRecord
 for _,raw:=range response.Data {
  var name struct{ModelName string `json:"model_name"`}
  if err:=json.Unmarshal(raw,&name);err!=nil{return nil,fmt.Errorf("invalid LiteLLM model row: %w",err)}
  if name.ModelName!=group {continue}
  var item modelRecord
  if err:=json.Unmarshal(raw,&item);err!=nil{return nil,fmt.Errorf("cannot validate LiteLLM model ownership: %w",err)}
  found=append(found,item)
 }
 return found,nil
}

func routeSlot(model GatewayModel)(string,error) {
 if model.ModelInfo==nil || model.ModelInfo.Metadata["owner"]!="modelops" {
  return "",fmt.Errorf("route must contain ModelOps ownership marker")
 }
 meta:=model.ModelInfo.Metadata
 if meta["namespace"]=="" || meta["resource"]=="" {return "",fmt.Errorf("route tenant/resource required")}
 slot:=meta["slot"]
 if slot!="stable" && slot!="canary" {return "",fmt.Errorf("invalid route slot")}
 return slot,nil
}

// ReconcileModelGroup converges 0, 1 or 2 role-tagged deployments; both
// Stable and Canary MUST use the same public model_name. Deployments in a
// same-name group that are not ours are a hard failure, never mutated.
// No success is emitted if LiteLLM cannot return real deployment IDs.
func(c *HTTPClient) ReconcileModelGroup(ctx context.Context,group string,desired []GatewayModel) error {
 if strings.TrimSpace(group)=="" || len(desired)>2 {return fmt.Errorf("invalid public group or route count")}
 wanted:=map[string]GatewayModel{}
 identity:=""
 total:=0
 for _,route:=range desired {
  slot,err:=routeSlot(route);if err!=nil{return err}
  if _,exists:=wanted[slot];exists {return fmt.Errorf("duplicate route slot")}
  if route.ModelName!=group || route.LiteLLMParams.APIBase=="" || route.LiteLLMParams.Model=="" {
   return fmt.Errorf("route has inconsistent model group, endpoint or backend")
  }
  if route.LiteLLMParams.Weight==nil || *route.LiteLLMParams.Weight<1 || *route.LiteLLMParams.Weight>100 {
   return fmt.Errorf("positive route weight required")
  }
  key:=route.ModelInfo.Metadata["namespace"]+"/"+route.ModelInfo.Metadata["resource"]
  if route.ModelInfo.Metadata["namespace"]+"--"+route.ModelInfo.Metadata["resource"]!=group {
   return fmt.Errorf("model alias does not match tenant/resource identity")
  }
  if identity!="" && identity!=key {return fmt.Errorf("mixed owner identities in same group")}
  identity=key
  total+=*route.LiteLLMParams.Weight
  wanted[slot]=route
 }
 if len(desired)>0 && total!=100 {return fmt.Errorf("weighted group total must be 100")}
 records,err:=c.listGroup(ctx,group);if err!=nil{return err}
 current:=map[string]modelRecord{}
 for _,record:=range records {
  meta:=record.ModelInfo.Metadata
  if meta==nil || meta["owner"]!="modelops" {
   return fmt.Errorf("refusing to change unmanaged LiteLLM group %s",group)
  }
  key:=meta["namespace"]+"/"+meta["resource"]
  // A ModelOps-looking owner marker is insufficient for deletion. The
  // namespace/resource must match the public alias even when desired=[].
  // Otherwise a forged/foreign same-name route could be deleted at finalizer.
  if meta["namespace"]+"--"+meta["resource"]!=group {
   return fmt.Errorf("gateway route provenance does not match public model alias")
  }
  if identity!="" && key!=identity {return fmt.Errorf("gateway owner mismatch")}
  slot:=meta["slot"]
  if slot!="stable" && slot!="canary" {return fmt.Errorf("unexpected managed role")}
  if record.ModelInfo.ID=="" {return fmt.Errorf("managed deployment missing LiteLLM DB ID")}
  if _,duplicate:=current[slot];duplicate{return fmt.Errorf("duplicate managed backend; requires manual cleanup")}
  current[slot]=record
 }
 for _,slot:=range []string{"stable","canary"} {
  route,needed:=wanted[slot];if !needed{continue}
  old,exists:=current[slot]
  if exists && old.ModelName==route.ModelName &&
   old.LiteLLMParams.Model==route.LiteLLMParams.Model &&
   old.LiteLLMParams.APIBase==route.LiteLLMParams.APIBase &&
   old.LiteLLMParams.Weight!=nil &&
   *old.LiteLLMParams.Weight==*route.LiteLLMParams.Weight {continue}
  if !exists {
   if err:=c.adminRequest(ctx,http.MethodPost,"/model/new",route,nil);err!=nil {
    return fmt.Errorf("create %s route: %w",slot,err)
   }
  }else{
   payload:=map[string]interface{}{
    "model_name":route.ModelName,
    "model_info":map[string]interface{}{"id":old.ModelInfo.ID,"metadata":route.ModelInfo.Metadata},
    "litellm_params":route.LiteLLMParams,
   }
   if err:=c.adminRequest(ctx,http.MethodPost,"/model/update",payload,nil);err!=nil {
    return fmt.Errorf("update %s route: %w",slot,err)
   }
  }
 }
 for _,slot:=range []string{"canary","stable"} {
  if _,needed:=wanted[slot];needed {continue}
  old,exists:=current[slot];if !exists{continue}
  if err:=c.adminRequest(ctx,http.MethodPost,"/model/delete",
   map[string]string{"id":old.ModelInfo.ID},nil);err!=nil{
    return fmt.Errorf("delete stale %s deployment: %w",slot,err)
  }
 }
 return nil
}
func(c *HTTPClient) DeleteModelGroup(ctx context.Context,group string)error{
 return c.ReconcileModelGroup(ctx,group,nil)
}
func(n *NoopClient) ReconcileModelGroup(ctx context.Context,group string,desired []GatewayModel)error{return nil}
func(n *NoopClient) DeleteModelGroup(ctx context.Context,group string)error{return nil}

func BuildOwnedRoute(group,namespace,resource,slot,backend,endpoint string,weight int) GatewayModel {
 return GatewayModel{ModelName:group,
  LiteLLMParams:LiteLLMParams{Model:backend,APIBase:endpoint,Weight:&weight},
  ModelInfo:&ModelInfo{Metadata:map[string]string{
   "owner":"modelops","namespace":namespace,"resource":resource,"slot":slot,
  }},
 }
}
