"""The fixture is a real, disposable git repository with the named defects."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import fixture  # noqa: E402
import grade  # noqa: E402


class FixtureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="jarvis-bench-coding-test-"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _python(self, repo: Path, code: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-c", code], cwd=str(repo),
                              capture_output=True, text=True, timeout=60)

    def test_build_makes_a_git_repo_with_no_remote_and_one_commit(self):
        repo = fixture.build(self.tmp, name="bench-shop")
        self.assertTrue((repo / ".git").is_dir())
        self.assertTrue((repo / ".bench-coding-repo").is_file())
        remotes = grade.run(repo, ["git", "remote"])["out"].strip()
        self.assertEqual(remotes, "", "the disposable repo must have no remote")
        log = grade.run(repo, ["git", "log", "--oneline"])["out"].strip().splitlines()
        self.assertEqual(len(log), 1)
        status = grade.run(repo, ["git", "status", "--short"])["out"].strip()
        self.assertEqual(status, "", "the fixture must start clean")
        self.assertTrue((repo / "pyproject.toml").is_file())
        self.assertTrue((repo / "tests" / "conftest.py").is_file())

    def test_the_or_query_defect_is_real(self):
        repo = fixture.build(self.tmp, name="bench-shop")
        done = self._python(
            repo,
            "import sys; sys.path.insert(0, 'src');"
            "from shop.search import build_query;"
            "print(build_query('coffee tea', match='any'))")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "coffee AND tea")

    def test_the_missing_key_defect_is_real(self):
        repo = fixture.build(self.tmp, name="bench-shop")
        done = self._python(
            repo,
            "import sys; sys.path.insert(0, 'src');"
            "from shop.pricing import unit_price;"
            "unit_price('gift-card')")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("UnknownSku", done.stderr)

    def test_the_off_by_one_defect_is_real(self):
        repo = fixture.build(self.tmp, name="bench-shop")
        done = self._python(
            repo,
            "import sys; sys.path.insert(0, 'src');"
            "from shop.paginate import page_slice;"
            "print(page_slice(list(range(7)), 3, 1))")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "[]")

    def test_the_four_file_refactor_fails_the_specification(self):
        repo = fixture.build(self.tmp, name="bench-shop")
        done = self._python(
            repo,
            "import sys; sys.path.insert(0, 'src');"
            "from shop.cart import Cart;"
            "from shop.checkout import checkout_total_cents")
        self.assertNotEqual(done.returncode, 0)

    def test_the_discount_source_is_a_pure_function_with_a_docstring(self):
        repo = fixture.build(self.tmp, name="bench-shop")
        text = (repo / "src" / "shop" / "discount.py").read_text(encoding="utf-8")
        self.assertIn("def progressive_discount(cents: int, tier: int) -> int:", text)
        self.assertIn("capped at 2,000 cents", text)
        self.assertNotIn("import random", text)
        self.assertNotIn("datetime", text)

    def test_building_inside_the_harness_checkout_is_refused(self):
        with self.assertRaises(ValueError):
            fixture.build(HERE)

    def test_an_existing_repo_is_refused_instead_of_overwritten(self):
        fixture.build(self.tmp, name="bench-shop")
        with self.assertRaises(FileExistsError):
            fixture.build(self.tmp, name="bench-shop")

    def test_remove_refuses_a_folder_that_is_not_a_benchmark_repo(self):
        foreign = self.tmp / "not-a-repo"
        foreign.mkdir()
        with self.assertRaises(ValueError):
            fixture.remove(foreign)

    def test_remove_deletes_a_marker_repo(self):
        repo = fixture.build(self.tmp, name="bench-shop")
        fixture.remove(repo)
        self.assertFalse(repo.exists())


if __name__ == "__main__":
    unittest.main()
