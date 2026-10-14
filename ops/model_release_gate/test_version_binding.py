from ops.model_release_gate import hardening
def test_online_checkpoint_and_registry_version_must_match():
    f=getattr(hardening,"version_decision",None)
    assert f is not None,"Registry/owned-online model binding absent"
    registry={"name":"qwen","version":3,"run_id":"run","checkpoint_sha":"sha"}
    live={"ready":True,"owned":True,"model_name":"qwen","version":3,"run_id":"run","checkpoint_sha":"sha"}
    assert f(registry,live)["status"]=="PASS"
    for key,value in [("version",4),("run_id","other"),("checkpoint_sha","bad"),("ready",False),("owned",False)]:
        assert f(registry,{**live,key:value})["status"]=="FAIL"
