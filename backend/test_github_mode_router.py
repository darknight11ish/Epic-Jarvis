#!/usr/bin/env python3
"""test_github_mode_router.py - full GitHub mode's second standing yes, read at
gate 6 and nowhere else, for a GitHub-shaped turn and nothing else.

    py -3 -B backend/test_github_mode_router.py

THE OWNER'S ASK, verbatim (2026-11-25): full GitHub mode "can be enabled in chat
or settings and forwards anything necessary to the cloud api"; "activating
github mode needs a card"; "in github mode i still want the local ai model to do
as much work as possible though".

WHAT THIS SUITE PINS, each one a separate way it can regress:

  1. THE READER IS THE FILE AND ONLY THE FILE: `github-mode.json` on this PC.
     A request body, an extra keyword or a client flag cannot set it.
  2. IT IS CONSULTED AT GATE 6 AND NOWHERE ELSE: with the mode ON, a short
     GitHub question still answers local at the complexity gate, a GitHub
     question whose budget is spent still answers local at the budget gate, and
     the reason on an escalated turn names GitHub mode.
  3. IT IS GITHUB-SHAPED ONLY: a hard question that is not about GitHub keeps
     the ordinary offer, even with the mode on.
  4. EVERY PRIVACY GATE STILL WINS: Lockdown, a tainted chat, a picture, an
     attached file, the screen's words, a private topic and a pasted secret each
     answer local BEFORE gate 6, with the mode on.
  5. IT DOES NOT TURN ON THE CLOUD SWITCH: the two standing yeses are separate
     files, and this one changes nothing about `escalate-cloud.json`.
  6. THE LOCAL MODEL STILL DOES THE WORK: the mode changes no gate above gate 6 -
     a GitHub-shaped question under the threshold, and a coding turn with fewer
     than two local failures, both stay local.

No network and no model: `jarvis_router.choose()` is the real shipped module,
and the settings folder is a temporary one. The budget is the one thing stood
in, because a spent day's ledger would otherwise have to be written.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-ghmode-router-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP)
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")
os.environ["JARVIS_SUITE_RUNNING"] = "1"
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""
os.environ["JARVIS_FRAMEWORK_TOML"] = str(_TMP / "jarvis-framework.toml")
(_TMP / "jarvis-framework.toml").write_bytes(
    (HERE / "rebuilt" / "jarvis-framework.toml").read_bytes())

sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_router.py", "jarvis_presets.py", "jarvis_asks_first.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_presets as P  # noqa: E402
import jarvis_router as RT  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


LOCAL = "qwen3.5:9b"
LANES = ["jarvis-escalate"]
#: Long and clause-heavy, so only gate 6 can stop it.
HARD = ("Explain in detail how the three-body problem differs from the two-body "
        "problem, and why the difference matters for predicting orbits.")
#: The same length, about GitHub work.
GH = ("Explain in detail, step by step, why the merge of pull request 44 in "
      "owner/repo failed the CI checks and what the trade-offs are in rebasing it.")
#: Short: the complexity gate answers before gate 6 can be reached.
SHORT_GH = "merge pr 44"


def choose(query, **kw):
    return RT.choose(query, local_model=LOCAL, lanes=list(LANES), **kw)


class SpentBudget:
    def allows_cloud(self):
        return False

    def day_exceeded(self):
        return True


def fresh():
    for p in (P._github_mode_path(), P._escalate_path()):
        try:
            p.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------
#   1. The reader is the file, and only the file
# --------------------------------------------------------------------------

def t_the_reader_is_the_file_and_only_the_file():
    fresh()
    check("absent file: off", RT.github_mode_escalation() is False)
    P._github_mode_path().write_text("not json", encoding="utf-8")
    check("unreadable file: off", RT.github_mode_escalation() is False)
    P._github_mode_path().write_text('{"on": 1}', encoding="utf-8")
    check("anything but the boolean true: off",
          RT.github_mode_escalation() is False)
    P._github_mode_path().write_text('{"on": true}', encoding="utf-8")
    check("the boolean true, and only that, is on",
          RT.github_mode_escalation() is True)
    # A stale body or an extra keyword cannot turn it on or off.
    fresh()
    d = choose(GH, github_mode=True, github_mode_file=True, requested_cloud=True)
    check("a request body/keyword cannot turn it on: the ordinary offer stands",
          d.gate == "offer" and d.auto is False, (d.gate, d.auto))
    P.write_github_mode(True)
    d = choose(GH, github_mode=False, cloud_mode_off=True)
    check("... and cannot turn it off either: the file still decides",
          d.gate == "escalate" and d.auto is True, (d.gate, d.auto))
    fresh()


# --------------------------------------------------------------------------
#   2. Gate 6, and nowhere else
# --------------------------------------------------------------------------

def t_it_moves_gate_six_and_only_gate_six():
    fresh()
    d = choose(GH)
    check("mode off: a GitHub question gets the ordinary offer",
          d.gate == "offer" and d.auto is False, (d.gate, d.auto))
    P.write_github_mode(True)
    d = choose(GH)
    check("mode on: the SAME question escalates, and says why",
          d.gate == "escalate" and d.auto is True
          and "GitHub mode is on" in d.reason, (d.gate, d.auto, d.reason))
    check("... and it names the one lane", d.lane == "jarvis-escalate", d.lane)
    d = choose(SHORT_GH)
    check("a SHORT GitHub question still answers local at the complexity gate",
          d.gate == "complexity" and d.auto is False, (d.gate, d.reason))
    d = choose(GH, budget=SpentBudget())
    check("a spent budget still answers local before gate 6",
          d.gate == "budget" and d.auto is False, (d.gate, d.reason))
    d = choose(HARD)
    check("a hard question that is NOT about GitHub keeps the ordinary offer",
          d.gate == "offer" and d.auto is False, (d.gate, d.auto))
    fresh()


# --------------------------------------------------------------------------
#   3. GitHub-shaped only
# --------------------------------------------------------------------------

SHAPED = (
    "why did the merge of pull request 44 fail",
    "rebasing this branch onto main, what are the trade-offs",
    "explain the CI checks on owner/repo in detail",
    "which workflow runs failed on that repository",
    "review the diff in this pull request",
    "what does the issue say",
    "push the commits to that branch",
    "why is github slow today",
)
NOT_SHAPED = (
    "what is the weather like in Paris today",
    "explain in detail how compound interest works",
    "book me a flight to Rome",
    "what is the capital of Australia",
    "",
)


def t_github_shaped_is_narrow():
    for text in SHAPED:
        check(f"GitHub-shaped: {text[:38]!r}", RT.github_shaped_turn(text) is True)
    for text in NOT_SHAPED:
        check(f"not GitHub-shaped: {text[:38]!r}",
              RT.github_shaped_turn(text) is False)


# --------------------------------------------------------------------------
#   4. Every privacy gate still wins, with the mode on
# --------------------------------------------------------------------------

def t_every_privacy_gate_still_answers_local_with_the_mode_on():
    fresh()
    P.write_github_mode(True)
    try:
        real_lockdown = RT.lockdown_on
        RT.lockdown_on = lambda: True
        try:
            d = choose(GH)
            check("Lockdown: local, unconditionally", d.gate == "lockdown", d.gate)
        finally:
            RT.lockdown_on = real_lockdown
        cases = (
            ("taint", dict(conversation_tainted=True)),
            ("image", dict(has_image=True)),
            ("file", dict(has_file=True)),
            ("screen", dict(has_screen=True)),
        )
        for gate, kw in cases:
            d = choose(GH, **kw)
            check(f"{gate}: local, before gate 6", d.gate == gate, d.gate)
        d = choose("What is my bank password? " + GH)
        check("private topic: local", d.gate == "private", d.gate)
        d = choose("merge PR 44 with sk-live-0123456789abcdef0123456789abcdef")
        check("a pasted secret: local", d.gate == "secret", d.gate)
        d = choose("merge the pull request in my own repository")
        check("a question about this PC's own repository: local at self_repo",
              d.gate == "self_repo", d.gate)
    finally:
        fresh()


# --------------------------------------------------------------------------
#   5. The two standing yeses are separate
# --------------------------------------------------------------------------

def t_it_does_not_turn_on_the_cloud_switch():
    fresh()
    P.write_github_mode(True)
    check("GitHub mode on does NOT turn on the Presets cloud switch",
          P.escalate_on() is False and RT.standing_escalation() is False)
    check("... and the two files are different files",
          P._github_mode_path() != P._escalate_path())
    check("... the cloud switch alone does not make a non-GitHub question escape "
          "either", choose(HARD).gate == "offer")
    P.write_github_mode(False)
    P._write_cloud_escalate(True)
    try:
        d = choose(HARD)
        check("the cloud switch, by contrast, covers every hard question",
              d.gate == "escalate" and "cloud escalation is on" in d.reason,
              (d.gate, d.reason))
        d = choose(SHORT_GH)
        check("... and still only at gate 6", d.gate == "complexity", d.gate)
    finally:
        fresh()


# --------------------------------------------------------------------------
#   6. The local model still does the work
# --------------------------------------------------------------------------

def t_the_local_model_still_does_as_much_as_it_can():
    fresh()
    P.write_github_mode(True)
    try:
        threshold = float(RT._cfg("routing", "complexity_threshold", 0.40) or 0.40)
        check("CONTROL: the threshold was not lowered by the mode",
              threshold == 0.40, threshold)
        d = choose("merge this pull request", coding=True)
        check("a coding GitHub turn with no local failures stays local",
              d.gate == "complexity", (d.gate, d.reason))
        RT.note_local_failure("gh-chat")
        d = choose("merge this pull request", coding=True, conversation="gh-chat")
        check("... with ONE local failure it still stays local",
              d.gate == "complexity", (d.gate, d.reason))
        RT.note_local_failure("gh-chat")
        d = choose("merge this pull request", coding=True, conversation="gh-chat")
        check("... and only with TWO does the existing fallback pass it on",
              d.gate == "escalate" and "failed on this PC 2 times" in d.reason,
              (d.gate, d.reason))
        check("... the fallback's own reason is still on the decision, and it is "
              "marked automatic (the mode's yes and the fallback can both apply)",
              d.auto is True and "failed on this PC 2 times" in d.reason, d.reason)
    finally:
        fresh()


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("t_") and callable(v)]
    for t in tests:
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as exc:                            # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ran to the end", False, repr(exc))
    fresh()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed checks:")
        for name in FAILED:
            print(f"  {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
