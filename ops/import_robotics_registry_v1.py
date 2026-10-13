"""Import verified legacy VLA versions as immutable metadata; never copy weights or rerun training."""
from pathlib import Path
import json
from ops.dev_control import control_session
from pipelines.robotics.adapter import Registry
ROOT=Path(__file__).resolve().parents[1]
def main():
    registry=Registry(ROOT/"Evidence/v1/vla-registry")
    receipt={"scope":"legacy compatibility import; no new GPU experiment","versions":[]}
    with control_session(ROOT,"v1-robotics-metadata-importer") as client:
        existing=client.get("/api/v1/models").json()
        for path in sorted(registry.root.glob("m05-*.json")):
            record=registry.resolve(path.stem)
            base=record.get("model_kind")=="base"
            name="smolvla-frozen" if base else "smolvla-"+record["version"].replace("m05-","")
            found=[x for x in existing if x["name"]==name and x["version"]==1]
            if found:
                if found[0]["digest"]!=record["checkpoint_sha256"]:raise RuntimeError("Immutable metadata conflict")
                row=found[0]
            else:
                row=client.post("/api/v1/models",json={
                    "name":name,"version":1,"model_type":"vla","task_type":"action-prediction","framework":"lerobot",
                    "source":"lerobot/smolvla_libero","revision":record["version"],"digest":record["checkpoint_sha256"],
                    "base_model":"lerobot/smolvla_libero@"+record["base_sha256"],
                    "adapter_type":None if base else "lora","adapter_uri":None if base else Path(record["checkpoint"]).as_uri(),
                    "artifact_uri":Path(record["checkpoint"]).as_uri(),"training_run_id":record["run_id"]})
                row.raise_for_status();row=row.json()
            receipt["versions"].append({"artifact_id":row["id"],"version":record["version"],
                "training_run_id":record["run_id"],"checkpoint_sha256":record["checkpoint_sha256"],
                "processor_sha256":record["processor_sha256"],"normalizer_sha256":record.get("normalizer_sha256"),
                "legacy_registry_record":str(path),"metadata_status":row["deployment_status"],
                "deployed_by_this_sprint":base})
    receipt["status"]="PASS"
    (ROOT/"Evidence/v1/robotics-registry-import.json").write_text(json.dumps(receipt,indent=2))
    print("VERIFIED_ROBOTICS_METADATA_IMPORT",len(receipt["versions"]))
if __name__=="__main__":main()
