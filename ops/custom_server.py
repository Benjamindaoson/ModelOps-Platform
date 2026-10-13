"""Real CPU embeddings; not TEI or language generation."""
import argparse
import torch
from transformers import AutoTokenizer,AutoModel
from fastapi import FastAPI,HTTPException
from pydantic import BaseModel
import uvicorn
p=argparse.ArgumentParser();p.add_argument("--model-root",required=True)
p.add_argument("--model-id",required=True);p.add_argument("--host",default="127.0.0.1")
p.add_argument("--port",type=int,required=True);a=p.parse_args()
if a.host!="127.0.0.1":raise SystemExit("Loopback only")
tokenizer=AutoTokenizer.from_pretrained(a.model_root,local_files_only=True,trust_remote_code=False)
model=AutoModel.from_pretrained(a.model_root,local_files_only=True,trust_remote_code=False).eval()
app=FastAPI()
class Request(BaseModel):
    input:str|list[str]
    model:str
@app.get("/health")
def health():return {"ready":True,"model":a.model_id,"backend":"transformers-cpu"}
@app.post("/v1/embeddings")
def embeddings(req:Request):
    if req.model!=a.model_id:raise HTTPException(409,"Model version mismatch")
    texts=[req.input] if isinstance(req.input,str) else req.input
    if not 1<=len(texts)<=16 or any(len(x)>4096 for x in texts):raise HTTPException(422,"Input budget")
    tokens=tokenizer(texts,padding=True,truncation=True,max_length=256,return_tensors="pt")
    with torch.inference_mode():
        hidden=model(**tokens).last_hidden_state;mask=tokens["attention_mask"].unsqueeze(-1)
        vectors=torch.nn.functional.normalize((hidden*mask).sum(1)/mask.sum(1).clamp(min=1),dim=1).tolist()
    return {"object":"list","model":a.model_id,"data":[{"object":"embedding","index":i,"embedding":v} for i,v in enumerate(vectors)],
            "usage":{"prompt_tokens":int(tokens["attention_mask"].sum()),"total_tokens":int(tokens["attention_mask"].sum())}}
uvicorn.run(app,host=a.host,port=a.port,log_level="warning",access_log=False)
