from pathlib import Path
import pytest
from . import runtime
def test_vllm_temp_path_respects_unix_socket_limit():
    f=getattr(runtime,"runtime_temp_dir",None);assert f is not None
    p=f(Path("/data/ModelOps-Platform/tmp/v1-production-readiness"))
    assert len(str(p).encode())+1+36<=107
    assert p==Path("/data/ModelOps-Platform/tmp/v1-production-readiness/.tmp")
def test_excessively_long_worktree_fails_explicitly():
    f=getattr(runtime,"runtime_temp_dir",None);assert f is not None
    with pytest.raises(ValueError):f(Path("/data/"+("x"*150)))
