from pathlib import Path
import pytest
import ops.dev_control as d

def paths(root,subdir=None):
    fn=getattr(d,"owned_evidence_root",None)
    assert fn is not None, "Isolated validation evidence root missing"
    return fn(root,subdir)

def test_default_v1_evidence_unchanged(tmp_path):
    assert paths(tmp_path)==tmp_path/"Evidence/v1"

def test_validation_metadata_is_isolated(tmp_path):
    assert paths(tmp_path,"Evidence/llm-production-validation")==tmp_path/"Evidence/llm-production-validation"

def test_metadata_cannot_escape_project(tmp_path):
    with pytest.raises(ValueError):paths(tmp_path,"../other-project")
