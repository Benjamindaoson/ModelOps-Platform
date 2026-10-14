import pytest
from ops.platform_serving import comparison_args

def test_comparison_disables_prefix_reuse_for_both_model_conditions():
    args=comparison_args({"MODEL_PATH":"/frozen-model","SERVED_MODEL_NAME":"base","SERVING_HOST":"127.0.0.1"})
    assert "--no-enable-prefix-caching" in args
    assert args[args.index("--dtype")+1]=="half"

def test_comparison_cannot_bind_an_external_interface():
    with pytest.raises(ValueError):
        comparison_args({"SERVING_HOST":"0.0.0.0"})
