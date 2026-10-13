import unittest,tempfile,os
from pathlib import Path
from unittest.mock import patch
from ops.gpu_lease import gpu_lease
class GPULeaseContracts(unittest.TestCase):
    def test_shared_lease_bytes_are_preserved_and_exclusion_is_real(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"lease";path.write_bytes(b"preserved-owner-marker")
            with patch.dict(os.environ,{"MODELOPS_GPU_LEASE":str(path)}):
                with gpu_lease(tmp):
                    with self.assertRaises(BlockingIOError):
                        with gpu_lease(tmp):pass
            self.assertEqual(path.read_bytes(),b"preserved-owner-marker")
    def test_explicit_missing_shared_lease_is_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ,{"MODELOPS_GPU_LEASE":str(Path(tmp)/"absent")}):
                with self.assertRaises(ValueError):
                    with gpu_lease(tmp):pass
if __name__=="__main__":unittest.main()
