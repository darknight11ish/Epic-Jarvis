"""The report must never turn BLOCKED into a pass, and must keep every row."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import cases  # noqa: E402
import report as report_mod  # noqa: E402


def row(case_id, status, cloud=0.0, **extra):
    base = {
        "id": case_id, "title": case_id, "tier": "Tier 1",
        "status": status, "reason": "", "attempts": 1, "rounds": 0,
        "route": {"lane": "qwen3-coder-30b-a3b-ud-q3-k-xl", "where": "local"},
        "tokens": 10, "prompt_tokens": 100, "tokens_per_s": 12.5,
        "cloud_dollars": cloud, "files": {"changed_paths": ["src/shop/search.py"]},
        "commands": [{"command": "python -m pytest -q tests/test_search.py",
                      "exit": 0 if status == "PASS" else 1}],
        "checks": {}, "turns": [], "prompt": "",
    }
    base.update(extra)
    return base


class ScoreTest(unittest.TestCase):
    def test_a_blocked_row_is_never_met(self):
        rows = [row("T1.1", "PASS"), row("T1.2", "PASS"), row("T1.3", "BLOCKED")]
        score = report_mod.score(rows)
        tier1 = score["tiers"][0]
        self.assertFalse(tier1["met"])
        self.assertIn("NOT MET", tier1["verdict"])
        self.assertEqual(tier1["blocked"], 1)

    def test_all_passed_is_met(self):
        rows = [row("T1.1", "PASS"), row("T1.2", "PASS"), row("T1.3", "PASS")]
        tier1 = report_mod.score(rows)["tiers"][0]
        self.assertTrue(tier1["met"])
        self.assertEqual(tier1["verdict"], "MET")

    def test_nothing_measured_reads_not_measured(self):
        rows = [row("T4.1", "BLOCKED"), row("T4.2", "BLOCKED"),
                row("T4.3", "BLOCKED")]
        tier4 = report_mod.score(rows)["tiers"][3]
        self.assertFalse(tier4["met"])
        self.assertEqual(tier4["verdict"], "NOT MEASURED")

    def test_cloud_spend_is_summed_only_over_rows_that_ran(self):
        rows = [row("T1.1", "PASS", 0.01), row("T1.2", "BLOCKED", 99.0)]
        score = report_mod.score(rows)
        self.assertAlmostEqual(score["cloud_dollars_measured"], 0.01)


class RenderTest(unittest.TestCase):
    def test_every_case_id_appears_in_a_rendered_report(self):
        document = {
            "run_id": "x", "started": "now", "finished": "now",
            "harness": {"branch": "b", "commit": "c"},
            "cases": [row(case.id, "BLOCKED", reason=case.blocked)
                      for case in cases.ALL_CASES],
            "scorecard": report_mod.score(
                [row(case.id, "BLOCKED") for case in cases.ALL_CASES]),
            "live_before": {}, "live_after": {}, "gaps": [],
        }
        text = report_mod.render(document)
        for case in cases.ALL_CASES:
            self.assertIn(case.id, text)
        self.assertIn("BLOCKED", text)
        self.assertIn("NOT MEASURED", text)
        self.assertIn("13", text)

    def test_the_spec_count_error_is_stated(self):
        joined = " ".join(report_mod.SPEC_ERRORS)
        self.assertIn("13", joined)
        self.assertIn("completion_tokens", joined)
        self.assertIn("daily-budget.json", joined)
        self.assertIn("X-Jarvis-Route", joined)

    def test_the_harness_gaps_are_stated(self):
        joined = " ".join(report_mod.HARNESS_GAPS)
        self.assertIn("file-write", joined)
        self.assertIn("proxy", joined)


class WriteTest(unittest.TestCase):
    def test_both_artefacts_are_written(self):
        tmp = Path(tempfile.mkdtemp(prefix="jarvis-bench-coding-test-"))
        try:
            document = {"run_id": "x", "started": "a", "finished": "b",
                        "harness": {}, "cases": [], "scorecard": {},
                        "live_before": {}, "gaps": []}
            json_path = tmp / "out" / "results.json"
            md_path = tmp / "out" / "report.md"
            report_mod.write_document(document, json_path, md_path)
            self.assertTrue(json_path.is_file())
            self.assertTrue(md_path.is_file())
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["run_id"], "x")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
