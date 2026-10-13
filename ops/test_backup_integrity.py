import json
import sys
import tempfile
import unittest
from pathlib import Path

from ops.backup_integrity import BackupIntegrityError, generate, verify


class BackupIntegrityTests(unittest.TestCase):
    def make_directory(self, root: Path) -> Path:
        (root / "postgresql").mkdir()
        (root / "kubernetes").mkdir()
        (root / "objects").mkdir()
        (root / "postgresql/modelops.dump").write_bytes(b"PGDMP" + b"x"*70)
        (root / "kubernetes/modeldeployments.json").write_text('{"items":[]}')
        (root / "objects/.objects-marker").write_text("source=s3://models-prod")
        (root / "objects/checkpoint.safetensors").write_bytes(b"real backup test bytes")
        return root

    def test_seal_and_verify_complete_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_directory(Path(tmp))
            sealed = generate(root, "modelops-alpha", "models-prod")
            self.assertEqual(sealed["schema"], "modelops.backup.v1")
            self.assertEqual(verify(root)["namespace"], "modelops-alpha")

    def test_corrupted_model_artifact_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_directory(Path(tmp))
            generate(root, "modelops-alpha", "models-prod")
            (root/"objects/checkpoint.safetensors").write_bytes(b"tampered")
            with self.assertRaises(BackupIntegrityError):
                verify(root)

    def test_empty_or_missing_database_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_directory(Path(tmp))
            (root/"postgresql/modelops.dump").write_bytes(b"")
            with self.assertRaises(BackupIntegrityError):
                generate(root, "modelops-alpha", "models-prod")

    def test_unexpected_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_directory(Path(tmp))
            generate(root, "modelops-alpha", "models-prod")
            (root/"objects/extra.bin").write_bytes(b"unexpected")
            with self.assertRaises(BackupIntegrityError):
                verify(root)

    def test_missing_object_store_payload_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_directory(Path(tmp))
            (root/"objects/checkpoint.safetensors").unlink()
            with self.assertRaises(BackupIntegrityError):
                generate(root, "modelops-alpha", "models-prod")

    def test_symlink_denied_even_if_not_regular_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_directory(Path(tmp))
            (root/"objects/link").symlink_to(root/"missing")
            with self.assertRaises(BackupIntegrityError):
                generate(root, "modelops-alpha", "models-prod")


if __name__ == "__main__":
    unittest.main()
