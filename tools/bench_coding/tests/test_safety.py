"""The harness's own promises, asserted over its source.

These are not style checks. Each one names something this tool said it would
never do, and looks for the code that would do it.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import client  # noqa: E402
import fixture  # noqa: E402

SOURCES = ("run.py", "client.py", "fixture.py", "grade.py", "telemetry.py",
           "cases.py", "report.py")


def source(name: str) -> str:
    return (HERE / name).read_text(encoding="utf-8")


class NoApprovalRouteTest(unittest.TestCase):
    def test_there_is_no_approve_route_anywhere(self):
        for name in SOURCES:
            text = source(name)
            for needle in ("/api/approve", "/api/approve/challenge"):
                self.assertNotIn(needle, text, f"{name} names {needle}")

    def test_a_denial_is_the_only_card_decision_and_it_is_a_no(self):
        holders = [name for name in SOURCES if "/api/deny" in source(name)]
        self.assertEqual(holders, ["client.py"],
                         "only the client may decline, and only a NO")
        self.assertIn("baseline", source("client.py"),
                      "a card is declined only when it is new to this turn")
        self.assertIn("DECLINE_NOTE", source("client.py"))

    def test_no_code_approves_a_card(self):
        for name in SOURCES:
            self.assertNotRegex(source(name), r"\.approve\(")
            self.assertNotIn('"/api/approve"', source(name))


class NoTokenOutputTest(unittest.TestCase):
    def test_no_source_prints_or_logs_the_token(self):
        pattern = re.compile(r"print\([^)]*(token|secret)", re.I)
        for name in SOURCES:
            self.assertIsNone(pattern.search(source(name)), name)

    def test_the_client_scrubs_what_it_hands_back(self):
        self.assertEqual(client.scrub("a SECRET b", "SECRET"), "a <redacted> b")
        self.assertEqual(client.scrub("nothing", "SECRET"), "nothing")


class NoRepositoryEscapeTest(unittest.TestCase):
    def test_every_source_that_writes_uses_a_fixture_repo_path(self):
        # The only writes are grade.apply_changes (guarded by _inside) and the
        # report/json artefacts; neither is reached with the checkout as root.
        self.assertIn("relative_to(repo.resolve())", source("grade.py"))

    def test_the_fixture_refuses_to_build_inside_the_checkout(self):
        with self.assertRaises(ValueError):
            fixture.build(HERE)

    def test_no_source_git_pushes(self):
        for name in SOURCES:
            text = source(name)
            self.assertNotIn('"push"', text, name)
            self.assertNotIn("'push'", text, name)

    def test_no_source_checks_out_a_branch(self):
        for name in SOURCES:
            text = source(name)
            self.assertIsNone(
                re.search(r"git[^\n]{0,80}\bcheckout\b", text), name)


class NoProductWriteTest(unittest.TestCase):
    def test_the_harness_does_not_name_a_live_backend_file(self):
        for name in SOURCES:
            text = source(name)
            for needle in ("config.toml", "memory.db", "chat-history.db",
                           "approvals.db"):
                self.assertNotIn(needle, text, f"{name} names {needle}")

    def test_the_apply_preset_is_opt_in_and_get_only_by_default(self):
        text = source("run.py")
        self.assertIn('parser.add_argument("--apply-preset"', text)
        self.assertIn('if args.apply_preset:', text)


if __name__ == "__main__":
    unittest.main()
