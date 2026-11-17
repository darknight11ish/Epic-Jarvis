"""Telemetry from the real files: speed.jsonl, api-money.json, git snapshots."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import telemetry  # noqa: E402


class SpeedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="jarvis-bench-coding-test-"))
        self.speed = self.tmp / "speed.jsonl"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rows):
        self.speed.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    def test_the_real_schema_has_no_completion_tokens(self):
        self.assertIn("tokens", telemetry.SPEED_FIELDS)
        self.assertNotIn("completion_tokens", telemetry.SPEED_FIELDS)

    def test_a_delta_keeps_the_fields_the_spec_names(self):
        self._write([
            {"at": 1, "model": "a", "tokens": 1},
            {"at": 2, "model": "b", "prompt_tokens": 100, "cached_tokens": 40,
             "tokens": 20, "tokens_per_s": 12.5, "total_ms": 1600},
        ])
        before = telemetry.speed_count(self.speed)
        self._write([
            {"at": 1, "model": "a", "tokens": 1},
            {"at": 2, "model": "b", "prompt_tokens": 100, "cached_tokens": 40,
             "tokens": 20, "tokens_per_s": 12.5, "total_ms": 1600},
            {"at": 3, "model": "b", "prompt_tokens": 50, "cached_tokens": 0,
             "tokens": 5, "tokens_per_s": 9.0},
        ])
        rows = telemetry.speed_delta(before, telemetry.speed_count(self.speed),
                                     self.speed)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["prompt_tokens"], 50)
        self.assertEqual(rows[0]["cached_tokens"], 0)
        self.assertEqual(rows[0]["tokens"], 5)
        self.assertEqual(rows[0]["tokens_per_s"], 9.0)

    def test_attribution_prefers_the_routes_lane_inside_the_window(self):
        rows = [
            {"at": 100.0, "model": "other", "tokens": 1},
            {"at": 101.0, "model": "coder", "tokens": 2},
        ]
        found = telemetry.attribute_turn(rows, 99.0, 105.0, "coder")
        self.assertTrue(found["matched"])
        self.assertEqual(found["chosen"]["model"], "coder")
        self.assertTrue(found["ambiguous"])

    def test_attribution_outside_the_window_is_not_a_match(self):
        rows = [{"at": 50.0, "model": "coder", "tokens": 2}]
        found = telemetry.attribute_turn(rows, 100.0, 110.0, "coder")
        self.assertFalse(found["matched"])
        self.assertIn("why", found)

    def test_the_schema_reader_names_the_missing_documented_fields(self):
        self._write([{"at": 1}])
        schema = telemetry.speed_schema(self.speed)
        self.assertTrue(schema["exists"])
        self.assertIn("tokens", schema["missing_from_first_row"])


class MoneyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="jarvis-bench-coding-test-"))
        self.money = self.tmp / "api-money.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_total_adds_every_month_and_service(self):
        self.money.write_text(json.dumps({"months": {
            "2026-10": {"deepseek_api": {"dollars": 0.25, "requests": 2}},
            "2026-11": {"deepseek_api": {"dollars": 0.5, "requests": 3},
                        "openai_api": {"dollars": 0.75, "requests": 1}},
        }}), encoding="utf-8")
        total = telemetry.money_total(self.money)
        self.assertAlmostEqual(total["total_dollars"], 1.5)
        self.assertEqual(total["requests"]["deepseek_api"], 5)
        self.assertEqual(total["months"], ["2026-10", "2026-11"])

    def test_the_daily_budget_note_is_honest_when_the_file_is_absent(self):
        total = telemetry.money_total(self.money)
        self.assertEqual(total["daily_budget_file"]["exists"],
                         telemetry.daily_budget_path().is_file())
        self.assertIn("daily cap", total["daily_budget_file"]["note"])

    def test_a_delta_is_the_difference(self):
        before = {"total_dollars": 1.0, "per_service": {"deepseek_api": 1.0}}
        after = {"total_dollars": 1.25, "per_service": {"deepseek_api": 1.25}}
        delta = telemetry.money_delta(before, after)
        self.assertAlmostEqual(delta["dollars"], 0.25)
        self.assertAlmostEqual(delta["per_service"]["deepseek_api"], 0.25)

    def test_a_missing_or_broken_file_is_zero_not_a_crash(self):
        self.money.write_text("{not json", encoding="utf-8")
        total = telemetry.money_total(self.money)
        self.assertEqual(total["total_dollars"], 0.0)


class GitTest(unittest.TestCase):
    def setUp(self):
        import subprocess
        self.tmp = Path(tempfile.mkdtemp(prefix="jarvis-bench-coding-test-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True)
        (self.repo / "a.txt").write_text("one\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t",
                        "-c", "user.email=t@t", "commit", "-q", "-m", "x"],
                       check=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_named_file_appears_in_the_snapshot(self):
        (self.repo / "a.txt").write_text("two\n", encoding="utf-8")
        snapshot = telemetry.git_snapshot(self.repo)
        self.assertIn("a.txt", snapshot["changed_paths"])
        self.assertFalse(snapshot["clean"])
        self.assertIn("a.txt", snapshot["diff_stat"])

    def test_a_clean_repo_is_clean(self):
        snapshot = telemetry.git_snapshot(self.repo)
        self.assertTrue(snapshot["clean"])
        self.assertEqual(snapshot["changed_paths"], [])


if __name__ == "__main__":
    unittest.main()
