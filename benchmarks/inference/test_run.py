"""CPU-only contract tests; no network or GPU results are mocked as passing."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from run import build_command, parse_args, validate


class BenchContractTests(unittest.TestCase):
    def args(self, *extra):
        return parse_args([
            "--base-url", "http://127.0.0.1:8000",
            "--model", "Qwen/example", *extra
        ])

    def test_chat_command_preserves_workload(self):
        args = self.args("--prompts", "20", "--concurrency", "2", "--request-rate", "3", "--input-len", "1024")
        validate(args)
        cmd = build_command(args, Path("/tmp/bench"))
        self.assertEqual(cmd[:3], ["vllm", "bench", "serve"])
        self.assertEqual(cmd[cmd.index("--backend") + 1], "openai-chat")
        self.assertEqual(cmd[cmd.index("--endpoint") + 1], "/v1/chat/completions")
        self.assertEqual(cmd[cmd.index("--input-len") + 1], "1024")
        self.assertIn("--save-result", cmd)
        self.assertNotIn("--save-detailed", cmd)

    def test_embedding_backend(self):
        args = self.args("--backend", "openai-embeddings")
        validate(args)
        cmd = build_command(args, Path("results"))
        self.assertEqual(cmd[cmd.index("--endpoint") + 1], "/v1/embeddings")
        self.assertNotIn("--output-len", cmd)

    def test_rejects_credentials_in_url(self):
        with self.assertRaises(ValueError):
            validate(self.args("--base-url", "https://alice:secret@host.test"))

    def test_rejects_path_traversal_run_id(self):
        with self.assertRaises(ValueError):
            validate(self.args("--run-id", "../../bad"))

    def test_rejects_negative_concurrency(self):
        with self.assertRaises(ValueError):
            validate(self.args("--concurrency", "0"))

    def test_rejects_base_url_with_path(self):
        with self.assertRaises(ValueError):
            validate(self.args("--base-url", "http://127.0.0.1:8000/v1"))

    def test_cli_dry_run_needs_no_gpu_or_vllm(self):
        script = Path(__file__).with_name("run.py")
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [
                    sys.executable, str(script), "--base-url", "http://127.0.0.1:8000",
                    "--model", "test", "--dry-run", "--output-root", tmp,
                ],
                capture_output=True, text=True, check=True,
            )
            data = json.loads(completed.stdout)
            self.assertTrue(data["dry_run"])
            self.assertFalse(list(Path(tmp).iterdir()))


if __name__ == "__main__":
    unittest.main()
