"""Deterministic offline contract tests; do not claim to have run model training."""
import json
import tempfile
import unittest
from pathlib import Path

from run import (EvaluationError, calculate, evaluate, prepare_heldout,
                 quality_gate, score, sha256_artifact)

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.train = self.root/"train.json"
        self.train.write_text(json.dumps([{"instruction":"train prompt", "output":"train answer"}]))
        self.heldout = self.root/"heldout.jsonl"
        with self.heldout.open("w") as f:
            for i in range(20):
                f.write(json.dumps({"id":str(i),"split":"heldout",
                    "prompt":f"Independent problem {i}",
                    "reference":"correct output"})+"\n")
        self.base = self.root/"base"
        self.candidate = self.root/"candidate"
        self.base.mkdir()
        self.candidate.mkdir()
        (self.candidate/"model.safetensors").write_bytes(b"fake-checkpoint-for-offline-contract-test")
        (self.base/"model.safetensors").write_bytes(b"fake-baseline")

    def fake_models(self,path,max_new_tokens):
        # Predictor injection is TEST-ONLY. Production CLI has no fake mode.
        return lambda prompt: "correct output" if path == self.candidate else "incorrect response"

    def run_report(self):
        dest = self.root/"report.json"
        evaluate(self.heldout,self.train,self.base,self.candidate,dest,20,32,self.fake_models)
        return dest

    def test_exact_and_f1(self):
        self.assertEqual(score("hello, World", "hello world"), (1.0,1.0))
        self.assertEqual(score("a b c", "a b"), (0.0,0.8))

    def test_independent_dataset(self):
        rows, meta=prepare_heldout(self.heldout,self.train,20)
        self.assertEqual(len(rows),20)
        self.assertEqual(len(meta["heldout_sha256"]),64)

    def test_forbid_training_overlap(self):
        with self.heldout.open("a") as f:
            f.write(json.dumps({"split":"heldout","prompt":"train prompt","reference":"train answer"})+"\n")
        with self.assertRaisesRegex(EvaluationError,"overlap"):
            prepare_heldout(self.heldout,self.train,20)

    def test_forbid_missing_split(self):
        self.heldout.write_text(json.dumps({"prompt":"problem","reference":"answer"})+"\n")
        with self.assertRaises(EvaluationError):
            prepare_heldout(self.heldout,self.train,1)

    def test_forbid_duplicate(self):
        with self.heldout.open("a") as f:
            f.write(json.dumps({"prompt":"Independent problem 1","reference":"x","split":"test"})+"\n")
        with self.assertRaisesRegex(EvaluationError,"duplicate"):
            prepare_heldout(self.heldout,self.train,20)

    def test_successful_gate_and_no_raw_data_leak(self):
        report=self.run_report()
        payload=json.loads(report.read_text())
        self.assertEqual(payload["proof_type"],"real_checkpoint_holdout")
        self.assertNotIn("Independent problem", report.read_text())
        self.assertEqual(payload["metrics"]["candidate_token_f1"],1)
        out=self.root/"approved.json"
        quality_gate(report,self.candidate,self.heldout,self.train,out,20,0.9,0)
        self.assertEqual(json.loads(out.read_text())["gate_schema"],"modelops.approval.v1")

    def test_fail_closed_on_artifact_mutation(self):
        report=self.run_report()
        (self.candidate/"model.safetensors").write_bytes(b"mutated")
        with self.assertRaisesRegex(EvaluationError,"artifact"):
            quality_gate(report,self.candidate,self.heldout,self.train,self.root/"approved.json",20,0.5,0)

    def test_fail_closed_on_bad_evaluation_report(self):
        report=self.run_report()
        payload=json.loads(report.read_text())
        payload["metrics"]["candidate_token_f1"]=100
        report.write_text(json.dumps(payload))
        with self.assertRaises(EvaluationError):
            quality_gate(report,self.candidate,self.heldout,self.train,self.root/"approved.json",20,0.5,0)

    def test_fail_closed_on_too_few_samples(self):
        report=self.run_report()
        with self.assertRaisesRegex(EvaluationError,"incomplete"):
            quality_gate(report,self.candidate,self.heldout,self.train,self.root/"approved.json",21,0.5,0)

    def test_fail_closed_on_regression(self):
        report=self.run_report()
        with self.assertRaisesRegex(EvaluationError,"below absolute"):
            quality_gate(report,self.candidate,self.heldout,self.train,self.root/"approved.json",20,1.01,0)

    def test_fail_closed_on_dataset_mutation(self):
        report=self.run_report()
        with self.heldout.open("a") as f:
            f.write(json.dumps({"id":"extra","prompt":"different","reference":"x","split":"test"})+"\n")
        with self.assertRaises(EvaluationError):
            quality_gate(report,self.candidate,self.heldout,self.train,self.root/"approved.json",20,0.5,0)

    def test_fail_closed_on_symlink_artifact(self):
        (self.candidate/"escape").symlink_to(self.train)
        with self.assertRaisesRegex(EvaluationError,"symlink"):
            sha256_artifact(self.candidate)

if __name__=="__main__":
    unittest.main()
