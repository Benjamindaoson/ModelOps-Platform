"""Build a derived candidate with the same immutable Registry contract as earlier validated jobs."""
from pathlib import Path
def candidate_payload(label,result,run_id,base_id):
    return {"name":"hardening-qwen3b-"+label,"version":1,"model_type":"llm","framework":"transformers",
        "source":"Qwen/Qwen2.5-3B-Instruct","revision":"aa8e72537993ba99e69dfaafa59ed015b17504d1","digest":result["checkpoint_sha256"],"artifact_uri":Path(result["checkpoint"]).as_uri(),
        "base_model":base_id,"adapter_type":"qlora","adapter_uri":Path(result["adapter"]).as_uri(),"training_run_id":run_id,"task_type":"bounded-shortqa"}
