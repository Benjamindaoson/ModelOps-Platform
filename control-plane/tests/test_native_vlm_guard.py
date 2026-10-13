from types import SimpleNamespace
import pytest
from modelops.native_serving import NativeServing
from modelops.runtime import RuntimeFailure

def test_unvalidated_vlm_does_not_fall_through_to_robotics(tmp_path):
    s=NativeServing(tmp_path,"python",tmp_path/"runtime")
    with pytest.raises(RuntimeFailure,match="model type"):
        s.validate_model_engine(SimpleNamespace(engine="custom"),SimpleNamespace(model_type="vlm"))
