import importlib,pytest
def options():
    try:m=importlib.import_module("pipelines.training.options")
    except ModuleNotFoundError:m=None
    assert m is not None,"Recoverable configurable training options missing"
    return m

def test_preserves_legacy_defaults():
    m=options();assert m.training_options({})=={"gradient_accumulation_steps":1,"gradient_checkpointing":False}

def test_rejects_invalid_accumulation_or_checkpoint_flag():
    m=options()
    for c in [{"gradient_accumulation_steps":0},{"gradient_accumulation_steps":True},{"gradient_checkpointing":"yes"}]:
        with pytest.raises(ValueError):m.training_options(c)

def test_resume_hash_covers_semantic_parameters_but_not_output_path():
    m=options()
    base={"run_id":"a","output":"/one","method":"qlora","steps":64,"batch_size":2,"lr":1e-5,"dataset_sha256":"frozen","base_sha256":"weights"}
    assert m.semantic_sha(base)==m.semantic_sha({**base,"output":"/two"})
    assert m.semantic_sha(base)!=m.semantic_sha({**base,"lr":1e-4})

def test_loss_weights_follow_shifted_supervised_token_counts():
    m=options()
    assert m.microbatch_weights([[-100,7,8],[-100,9]])==[2/3,1/3]

def test_changed_configuration_rejected_on_resume():
    m=options()
    with pytest.raises(ValueError):m.verify_resume_identity({"config_sha":"old"},{"lr":1e-5})
