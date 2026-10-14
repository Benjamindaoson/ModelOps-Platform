from modelops.schemas import ArtifactIn
from .training_contracts import candidate_payload
def test_actual_derived_candidate_satisfies_registry_contract(tmp_path):
    result={"checkpoint_sha256":"a"*64,"checkpoint":str(tmp_path/"model.safetensors"),"adapter":str(tmp_path/"adapter")}
    body=candidate_payload("no-checkpoint",result,"run-id","base-id")
    actual=ArtifactIn.model_validate(body)
    assert actual.revision=="aa8e72537993ba99e69dfaafa59ed015b17504d1"
    assert actual.training_run_id=="run-id" and actual.digest=="a"*64
