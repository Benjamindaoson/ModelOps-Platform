import tempfile
import unittest
from pathlib import Path
from pipelines.training.merge import MergeError, merge_checkpoint, verify_checkpoint

class MergeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.base=self.root/"base"
        self.trained=self.root/"trained"
        self.output=self.root/"merged"
        for d in (self.base,self.trained):
            d.mkdir()
        for d in (self.base,self.trained):
            (d/"config.json").write_text("{}")
            (d/"model.safetensors").write_bytes(b"weights")
    def test_full_checkpoint_is_real_copy(self):
        receipt=merge_checkpoint(self.base,self.trained,self.output,"full")
        self.assertTrue(receipt["completed"])
        self.assertTrue((self.output/"model.safetensors").exists())
    def test_never_overwrites(self):
        merge_checkpoint(self.base,self.trained,self.output,"full")
        with self.assertRaises(MergeError):
            merge_checkpoint(self.base,self.trained,self.output,"full")
    def test_no_silent_missing_adapter(self):
        with self.assertRaises(MergeError):
            merge_checkpoint(self.base,self.trained,self.output,"qlora")
    def test_missing_model_rejected(self):
        (self.trained/"config.json").unlink()
        with self.assertRaises(MergeError):
            verify_checkpoint(self.trained)
    def test_source_output_same_rejected(self):
        with self.assertRaises(MergeError):
            merge_checkpoint(self.base,self.trained,self.trained,"full")

if __name__=="__main__":
    unittest.main()
