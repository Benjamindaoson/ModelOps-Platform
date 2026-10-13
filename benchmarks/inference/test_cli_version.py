"""CLI compatibility contracts for the pinned GPU validation runtime."""
import unittest
from pathlib import Path
from run import parse_args,build_command
class VersionContracts(unittest.TestCase):
    def test_v010_uses_official_random_dataset_flags(self):
        a=parse_args(["--base-url","http://127.0.0.1:8000","--model","uuid",
             "--cli-profile","v0.10","--tokenizer","/private/base","--warmups","0"])
        cmd=build_command(a,Path("/evidence"))
        self.assertIn("--endpoint-type",cmd)
        self.assertEqual(cmd[cmd.index("--endpoint-type")+1],"openai-chat")
        self.assertIn("--random-input-len",cmd)
        self.assertIn("--random-output-len",cmd)
        self.assertNotIn("--input-len",cmd)
        self.assertNotIn("--num-warmups",cmd)
        self.assertEqual(cmd[cmd.index("--tokenizer")+1],"/private/base")
if __name__=="__main__":unittest.main()
