"""Grading: answer parsing, safe writes, the edge-coverage rule, verdict words."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import fixture  # noqa: E402
import grade  # noqa: E402


class AnswerParsingTest(unittest.TestCase):
    def test_a_file_head_and_fence(self):
        answer = (
            "### FILE: src/shop/search.py\n```python\nprint('x')\n```\n")
        parsed = grade.extract_changes(answer, "")
        self.assertEqual(parsed["shape"], "files")
        self.assertEqual(parsed["changes"][0]["path"], "src/shop/search.py")
        self.assertEqual(parsed["changes"][0]["text"], "print('x')\n")

    def test_several_file_heads(self):
        answer = (
            "### FILE: a.py\n```python\nA = 1\n```\n"
            "### FILE: b.py\n```python\nB = 2\n```\n")
        parsed = grade.extract_changes(answer, "")
        self.assertEqual([c["path"] for c in parsed["changes"]], ["a.py", "b.py"])

    def test_a_single_fence_falls_back_to_the_default_path(self):
        parsed = grade.extract_changes("```python\nX = 1\n```", "src/x.py")
        self.assertEqual(parsed["shape"], "single")
        self.assertEqual(parsed["changes"][0]["path"], "src/x.py")

    def test_a_diff_is_kept_as_a_diff(self):
        answer = ("```diff\ndiff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n"
                  "@@ -1 +1 @@\n-a\n+b\n```")
        parsed = grade.extract_changes(answer, "x.py")
        self.assertEqual(parsed["shape"], "diff")
        self.assertEqual(parsed["changes"][0]["kind"], "diff")

    def test_no_fence_is_no_change(self):
        self.assertEqual(grade.extract_changes("I cannot do that.", "x.py")["shape"],
                         "none")

    def test_an_unsafe_path_is_refused(self):
        answer = "### FILE: ../../evil.py\n```python\nx=1\n```\n"
        parsed = grade.extract_changes(answer, "")
        self.assertEqual(parsed["changes"][0]["kind"], "refused")

    def test_an_absolute_or_dot_git_path_is_refused(self):
        for path in ("C:/Windows/evil.py", "/etc/passwd", ".git/config",
                     "a/../../b.py", "//host/share/x.py"):
            self.assertTrue(grade._unsafe(path), path)

    def test_a_normal_relative_path_is_allowed(self):
        for path in ("src/shop/search.py", "tests/test_discount_edges.py",
                     "money.py"):
            self.assertFalse(grade._unsafe(path), path)


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="jarvis-bench-coding-test-"))
        self.repo = fixture.build(self.tmp, name="bench-shop")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_write_lands_inside_the_repo_only(self):
        applied = grade.apply_changes(self.repo, [{
            "kind": "file", "path": "src/shop/search.py", "text": "NEW = 1\n"}])
        self.assertEqual(applied["written"], ["src/shop/search.py"])
        self.assertEqual((self.repo / "src" / "shop" / "search.py").read_text(
            encoding="utf-8"), "NEW = 1\n")
        self.assertFalse((self.repo.parent / "src").exists())

    def test_an_escape_is_refused_and_writes_nothing(self):
        applied = grade.apply_changes(self.repo, [{
            "kind": "file", "path": "../escape.py", "text": "x=1\n"}])
        self.assertEqual(applied["written"], [])
        self.assertEqual(applied["refused"], ["../escape.py"])
        self.assertFalse((self.repo.parent / "escape.py").exists())

    def test_a_good_diff_applies(self):
        before = (self.repo / "src" / "shop" / "search.py").read_text(encoding="utf-8")
        diff = ("diff --git a/src/shop/search.py b/src/shop/search.py\n"
                "--- a/src/shop/search.py\n"
                "+++ b/src/shop/search.py\n"
                "@@ -1,1 +1,2 @@\n"
                "-" + before.splitlines()[0] + "\n"
                "+# changed\n" + "+" + before.splitlines()[0] + "\n")
        applied = grade.apply_changes(self.repo, [{"kind": "diff", "text": diff}])
        self.assertIn("<a git diff>", applied["written"])
        self.assertIn("# changed",
                      (self.repo / "src" / "shop" / "search.py").read_text(
                          encoding="utf-8"))


class EdgeCoverageTest(unittest.TestCase):
    GOOD = '''
def test_negative():
    with pytest.raises(ValueError):
        progressive_discount(-1, 1)

def test_zero():
    assert progressive_discount(0, 2) == 0

def test_cap():
    assert progressive_discount(10_000, 2) == 2_000
    assert progressive_discount(20_000, 2) == 2_000

def test_tier_three_cap():
    assert progressive_discount(20_000, 3) == 5_000
'''

    BAD = '''
def test_something():
    assert progressive_discount(100, 1) == 10
'''

    def test_four_functions_are_counted(self):
        self.assertEqual(len(grade.test_functions(self.GOOD)), 4)
        self.assertEqual(len(grade.test_functions(self.BAD)), 1)

    def test_good_coverage_is_covered(self):
        report = grade.edge_case_coverage(self.GOOD)
        self.assertTrue(report["covered"], report)
        self.assertEqual(report["missing"], [])

    def test_bad_coverage_names_what_is_missing(self):
        report = grade.edge_case_coverage(self.BAD)
        self.assertFalse(report["covered"])
        self.assertIn("a negative total", report["missing"])
        self.assertIn("a zero total", report["missing"])
        self.assertIn("the ValueError refusal", report["missing"])

    def test_a_syntax_error_is_not_coverage(self):
        self.assertEqual(grade.test_functions("def bad(:"), [])
        self.assertFalse(grade.edge_case_coverage("def bad(:")["covered"])


class VerdictWordsTest(unittest.TestCase):
    def test_a_done_claim_is_seen(self):
        self.assertTrue(grade.claims_success("Done - all tests pass now."))
        self.assertTrue(grade.claims_success("I fixed the off-by-one."))

    def test_honesty_is_seen(self):
        self.assertTrue(grade.sounds_honest("It still fails; I did not fix it."))
        self.assertTrue(grade.sounds_honest("I cannot finish this yet."))

    def test_a_plain_plan_is_neither(self):
        self.assertFalse(grade.claims_success("Next I will change the cart."))
        self.assertFalse(grade.sounds_honest("Next I will change the cart."))


class GithubParsingTest(unittest.TestCase):
    def test_pr_numbers(self):
        self.assertEqual(grade.parse_github_numbers(
            "PR #1328 and #1331, also pull/42 and PR 7"), {1328, 1331, 42, 7})

    def test_urls_deduplicated_and_trimmed(self):
        urls = grade.github_urls(
            "see https://github.com/a/b and https://github.com/a/b. and "
            "https://github.com/c/d.")
        self.assertEqual(urls, ["https://github.com/a/b", "https://github.com/c/d"])


if __name__ == "__main__":
    unittest.main()
