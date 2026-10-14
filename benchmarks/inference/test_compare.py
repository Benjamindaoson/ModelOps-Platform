"""Synthetic fixtures test the comparator; no fake GPU benchmark is published."""
import json
import tempfile
import unittest
from pathlib import Path
from benchmarks.inference.compare import ComparisonError, compare, load_run, render_markdown

class ComparisonContractTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        self.l=self.root/"baseline"
        self.r=self.root/"candidate"
        for p,metric in ((self.l,100),(self.r,120)):
            p.mkdir()
            (p/"manifest.json").write_text(json.dumps({
                "model":"Qwen/test","backend":"openai-chat",
                "dataset":"random_synthetic_smoke_not_business_distribution",
                "prompts":10,"concurrency":2,"request_rate_per_sec":3,
                "input_len_tokens":64,"output_len_tokens":32,"seed":42,
                "gpu_snapshot":"NVIDIA RTX 3090, 24576 MiB, driver 560",
                "git_sha":"same",
            }))
            (p/"status.json").write_text(json.dumps({
                "status":"PASS", "measurements_valid":True,
                "tool_exit_code":0, "benchmark_timed_out":False,
                "raw_results_exist":True, "successful_requests":10,
                "failed_requests":0, "observed_success_rate":1.0,
            }))
            (p/"raw-benchmark.json").write_text(json.dumps({
                "duration":20,"completed":10,"failed":0,
                "request_throughput":5,"output_throughput":metric,
                "p50_ttft_ms":100,"p95_ttft_ms":150,"p99_ttft_ms":200,
                "p50_tpot_ms":10,"p95_tpot_ms":15,"p99_tpot_ms":20,
                "p50_e2el_ms":300,"p95_e2el_ms":400,"p99_e2el_ms":500,
            }))
    def test_fair_comparison(self):
        r=compare(self.l,self.r)
        self.assertAlmostEqual(r["metrics"]["output_throughput"]["improvement_pct"],20)
        self.assertIn("| Metric |",render_markdown(r))
    def test_mismatched_hardware_rejected(self):
        f=self.r/"manifest.json";d=json.loads(f.read_text());d["gpu_snapshot"]="different";f.write_text(json.dumps(d))
        with self.assertRaisesRegex(ComparisonError,"GPU"):
            compare(self.l,self.r)
    def test_mismatched_workload_rejected(self):
        f=self.r/"manifest.json";d=json.loads(f.read_text());d["input_len_tokens"]=512;f.write_text(json.dumps(d))
        with self.assertRaisesRegex(ComparisonError,"workload parity"):
            compare(self.l,self.r)
    def test_failed_requests_rejected(self):
        f=self.r/"raw-benchmark.json";d=json.loads(f.read_text());d["failed"]=3;f.write_text(json.dumps(d))
        with self.assertRaisesRegex(ComparisonError,"failed requests"):
            compare(self.l,self.r)
    def test_claimed_pass_without_measured_requests_is_rejected(self):
        f=self.r/"status.json";d=json.loads(f.read_text())
        d["successful_requests"]=9;f.write_text(json.dumps(d))
        with self.assertRaisesRegex(ComparisonError,"status and raw"):
            compare(self.l,self.r)

    def test_fake_pass_status_rejected(self):
        f=self.r/"status.json";f.write_text(json.dumps({"status":"FAIL_SLO"}))
        with self.assertRaisesRegex(ComparisonError,"SLO"):
            compare(self.l,self.r)
    def test_missing_metric_rejected(self):
        f=self.r/"raw-benchmark.json";d=json.loads(f.read_text());del d["p95_ttft_ms"];f.write_text(json.dumps(d))
        with self.assertRaisesRegex(ComparisonError,"p95_ttft_ms"):
            compare(self.l,self.r)
    def test_nan_rejected(self):
        f=self.r/"raw-benchmark.json";d=json.loads(f.read_text());d["output_throughput"]=float('nan');f.write_text(json.dumps(d))
        with self.assertRaises(ComparisonError):
            compare(self.l,self.r)

if __name__=="__main__":
    unittest.main()
