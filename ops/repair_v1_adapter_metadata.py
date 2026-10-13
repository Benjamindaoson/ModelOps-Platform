"""Audited repair of one non-identity provenance pointer; never alters model bytes or history."""
from pathlib import Path
import json,sys,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"control-plane"))
from modelops.db import make_session_factory,ModelArtifact,AuditEvent
def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1048576),b""):h.update(block)
    return h.hexdigest()
def main():
    e=ROOT/"Evidence/v1";history=json.loads((e/"llm-lifecycle.json").read_text())
    result=json.loads((e/"runtime/lab"/history["training_run_id"]/"artifacts/result.json").read_text())
    adapter=Path(result["adapter"])/"adapter_model.safetensors"
    if sha(adapter)!=result["adapter_sha256"]:raise RuntimeError("Adapter receipt does not verify")
    correct=Path(result["adapter"]).as_uri()
    _,sessions=make_session_factory("sqlite:///"+str(e/"modelops.sqlite"))
    with sessions() as db:
        row=db.get(ModelArtifact,history["candidate"]["id"])
        if row.tenant!="lab" or row.training_run_id!=history["training_run_id"] or row.digest!=history["candidate"]["digest"]:
            raise RuntimeError("Artifact identity conflict")
        before=row.adapter_uri
        details={"field":"adapter_uri","before":before,"after":correct,"checkpoint_sha256":row.digest,
            "adapter_sha256":result["adapter_sha256"],"training_run_id":row.training_run_id,
            "identity_and_bytes_unchanged":True,"reason":"Original registration linked merged directory as adapter; correction preserves raw registration receipt."}
        if before!=correct:
            row.adapter_uri=correct
            event=AuditEvent(tenant=row.tenant,actor="v1-provenance-auditor",action="artifact.metadata.correct",
                object_kind="model",object_id=row.id,detail=json.dumps(details,sort_keys=True))
            db.add(event);db.commit();details["audit_event_id"]=event.id
        else:details["already_correct"]=True
    (e/"adapter-metadata-repair.json").write_text(json.dumps({"status":"PASS",**details},indent=2))
    print("ADAPTER_METADATA_VERIFIED",result["adapter_sha256"])
if __name__=="__main__":main()
