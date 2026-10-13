"""A signed text score cannot qualify a continuous-action robot policy."""
import importlib.util,json,hmac,hashlib,os
from pathlib import Path
from modelops.evidence import digest_report
spec=importlib.util.spec_from_file_location("metric_fixtures",Path(__file__).with_name("test_api.py"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
api=m.api;headers=m.headers;register=m.register;model_payload=m.model_payload

def test_text_token_f1_cannot_approve_vla(api):
    client,_=api;_,dataset=register(client)
    payload=model_payload();payload.update(name="robot-metric-boundary",family="vla")
    model=client.post("/api/v1/models",headers=headers(),json=payload).json()
    report={"schema":"modelops.heldout.v1","proof_type":"real_checkpoint_holdout","num_samples":24,
      "artifact_sha256":model["digest"],"heldout_sha256":dataset["digest"],"generation_success_rate":1.,
      "train_overlap_count":0,"metrics":{"base_token_f1":.7,"candidate_token_f1":.8,"delta_token_f1":.1}}
    signature=hmac.new(os.environ["MODELOPS_ATTESTATION_KEY"].encode(),digest_report(report).encode(),hashlib.sha256).hexdigest()
    response=client.post("/api/v1/evaluations/attest",headers={**headers(),"X-ModelOps-Attestation":signature},
      json={"artifact_id":model["id"],"dataset_id":dataset["id"],"report":report})
    assert response.status_code==422,response.text
    assert "robot" in response.text.lower() or "text" in response.text.lower()
