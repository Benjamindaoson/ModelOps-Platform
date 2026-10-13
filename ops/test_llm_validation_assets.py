import hashlib, importlib
import pytest

def feature():
    try: m=importlib.import_module("ops.bootstrap_llm_validation_assets")
    except ModuleNotFoundError: m=None
    assert m is not None, "Pinned 3B asset verifier is not implemented"
    return m

def test_lfs_corruption_is_rejected(tmp_path):
    p=tmp_path/"model"; p.write_bytes(b"abc")
    f={"name":"model","lfs":{"sha256":hashlib.sha256(b"abc").hexdigest(),"size":3}}
    assert feature().validate_file(f,p)
    p.write_bytes(b"abd")
    assert not feature().validate_file(f,p)

def test_lfs_wrong_size_is_rejected(tmp_path):
    p=tmp_path/"model"; p.write_bytes(b"abc")
    f={"name":"model","lfs":{"sha256":hashlib.sha256(b"abc").hexdigest(),"size":4}}
    assert not feature().validate_file(f,p)

def test_git_blob_identity_is_verified(tmp_path):
    p=tmp_path/"config"; p.write_bytes(b"abc")
    blob=hashlib.sha1(b"blob 3\0abc").hexdigest()
    assert feature().validate_file({"name":"config","blob":blob},p)
    assert not feature().validate_file({"name":"config","blob":"0"*40},p)

def test_asset_path_cannot_escape(tmp_path):
    with pytest.raises(ValueError):
        feature().owned_destination(tmp_path, "../escape")
