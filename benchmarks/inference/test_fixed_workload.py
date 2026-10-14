import unittest
from pathlib import Path
from benchmarks.inference.run import parse_args,build_command

class FixedWorkloadTests(unittest.TestCase):
    def test_fixed_outputs_and_details_are_explicit(self):
        a=parse_args(["--base-url","http://127.0.0.1:8000","--model","frozen","--cli-profile","v0.10","--warmups","0","--fixed-lengths","--ignore-eos","--save-detailed"])
        cmd=build_command(a,Path("owned"))
        self.assertIn("--ignore-eos",cmd)
        self.assertIn("--save-detailed",cmd)
        self.assertEqual(cmd[cmd.index("--random-range-ratio")+1],"0.0")
    def test_old_recipe_preserved(self):
        a=parse_args(["--base-url","http://127.0.0.1:8000","--model","frozen","--cli-profile","v0.10","--warmups","0"])
        cmd=build_command(a,Path("owned"))
        self.assertNotIn("--ignore-eos",cmd)
        self.assertNotIn("--save-detailed",cmd)
if __name__=="__main__":unittest.main()
