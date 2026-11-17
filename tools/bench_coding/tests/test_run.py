"""The command itself: --dry lists every row, and the live-folder finder."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import client  # noqa: E402


class DryRunTest(unittest.TestCase):
    def test_dry_lists_all_thirteen_and_the_t5_rows_and_sends_nothing(self):
        done = subprocess.run(
            [sys.executable, str(HERE / "run.py"), "--dry"],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        for case_id in ("T1.1", "T1.2", "T1.3", "T2.1", "T2.2", "T2.3",
                        "T3.1", "T3.2", "T3.3", "T3.4",
                        "T4.1", "T4.2", "T4.3", "T5.1", "T5.2", "T5.3"):
            self.assertIn(case_id, done.stdout)
        self.assertIn("Nothing was sent", done.stdout)
        self.assertIn("BLOCKED", done.stdout)


class LiveFolderTest(unittest.TestCase):
    def test_an_explicit_folder_with_the_token_store_is_found(self):
        tmp = Path(tempfile.mkdtemp(prefix="jarvis-bench-coding-test-"))
        try:
            (tmp / "jarvis_token_store.py").write_text("print('x')\n",
                                                       encoding="utf-8")
            self.assertEqual(client.find_live_backend(str(tmp)), tmp)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_folder_without_the_store_is_not_mistaken_for_the_live_one(self):
        tmp = Path(tempfile.mkdtemp(prefix="jarvis-bench-coding-test-"))
        try:
            try:
                found = client.find_live_backend(str(tmp))
            except client.Blocked:
                return  # no live folder on this machine: the honest answer
            self.assertNotEqual(found, tmp)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
