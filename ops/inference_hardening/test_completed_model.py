from .completed import completed_model
from .contracts import digest
def test_verified_complete_model_reuses_without_server(tmp_path):
    raw=tmp_path/"outputs.jsonl";raw.write_text("{}\n")
    r={"status":"PASS","quality":{"status":"PASS","raw_sha":digest(raw)},"trials":[{"id":str(i),"status":"PASS"} for i in range(21)]}
    assert completed_model(r,raw,lambda r:True)
    raw.write_text("changed")
    assert not completed_model(r,raw,lambda r:True)
def test_partial_or_bad_trial_is_not_reused(tmp_path):
    raw=tmp_path/"outputs.jsonl";raw.write_text("{}\n")
    r={"status":"PASS","quality":{"status":"PASS","raw_sha":digest(raw)},"trials":[]}
    assert not completed_model(r,raw,lambda r:True)
