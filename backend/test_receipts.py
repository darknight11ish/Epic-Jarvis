"""test_receipts.py - action receipts, and the one button that puts a change back
(jarvis_receipts.py, plugins/ready/receipts/, and the goals tick that is wired to it).

    python3 backend/test_receipts.py

What it proves, with a stub gate, a real Goals store and a real SQLite file in a
scratch folder (nothing here needs the owner's PC):

  - a receipt is WRITTEN before a change and read back with what was recorded,
    newest first, and an id that was never written reads as None;
  - the goals tick is wired to it: the result carries the `receipt_id`, and
    Undo puts THE WHOLE PLAN back exactly as it was - the same `done_at`, the
    same lock on the step that waited on it - not a fresh timestamp;
  - a second Undo is REFUSED in plain words and applies NOTHING: the counting
    callable runs once, and a step ticked again by hand afterwards is not
    clobbered by the old receipt;
  - an id that was never written is refused (a plain 404 from the route, and a
    plain sentence from undo()), and no card is raised for it;
  - a receipt that CANNOT be written does not fail the action it was recording:
    the tick still lands, and no receipt id comes back;
  - a snapshot never holds a secret - the project's own scrubber is what hid it,
    checked against the bytes of the database file itself;
  - when the in-memory callable is gone (a new process) the change is put back
    from the before snapshot, and the answer says which path it took; when
    neither is available it refuses, in plain words, and marks nothing;
  - the Undo card is raised ONCE for `undo_action`, and a DENIED card changes
    nothing at all; `allowed=True` at tier ask with no approval behind it does
    not reverse anything either (allowed is not "a human decided"), while a
    tier the GATE answers for is obeyed, because the shipped settings file is
    the one policy and this module reads no tier table of its own;
  - the shipped `jarvis-framework.toml` gives `undo_action` no line, so it
    takes `unknown_action_tier` - which that file says is "ask" - read out of
    the file itself rather than asserted about a stub;
  - install() wraps the core's Handler: GET /api/receipts answers, the POST is
    behind the origin and token checks, every other path reaches the core
    untouched, and a second install() does not double-wrap.

Every check fails on the code before this feature: jarvis_receipts.py did not
exist, and a goals tick left no record of what it changed.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_receipts.py", "jarvis_goals.py", "jarvis_scrub.py")

# A scratch folder INSIDE the checkout, and the settings folder pointed at it:
# this suite writes real SQLite files and real audit lines, and the owner's own
# state must not be touched (jarvis_goals' own tests write to %TEMP%, which
# this PC refuses).
SCRATCH = HERE / "_receipts_test_tmp"
shutil.rmtree(SCRATCH, ignore_errors=True)
SCRATCH.mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_RECEIPTS_DB"] = str(SCRATCH / "receipts.db")
os.environ["JARVIS_GOALS_DB"] = str(SCRATCH / "goals.db")

import jarvis_goals as G            # noqa: E402
import jarvis_receipts as R         # noqa: E402
import jarvis_scrub as SC           # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   Scaffolding: a clock, a verdict, a stub gate, a real Goals store
# --------------------------------------------------------------------------

class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class Verdict:
    """What jarvis_gate.check() hands back: allowed, tier, outcome."""

    def __init__(self, allowed, tier, outcome, reason=""):
        self.allowed, self.tier, self.outcome, self.reason = allowed, tier, outcome, reason


class Cards:
    """A stub for the ONE approval card. Records every card raised; answers
    with whatever this test set."""

    def __init__(self, answer="approved", tier="ask"):
        self.answer, self.tier, self.cards = answer, tier, []

    def gate(self, action, detail, prompt):
        self.cards.append({"action": action, "detail": detail, "prompt": prompt})
        if self.answer == "approved":
            return Verdict(True, "ask", "approved")
        return Verdict(False, "ask", self.answer)

    def tier_of(self, action):
        return self.tier


class Sched:
    """A stand-in for jarvis_schedule, the shape jarvis_goals' own docstring
    says a test should use ("no test needs a real scheduler or a real model").
    accept() only needs add_repeat to hand back a job id; a real Scheduler
    starts a background thread that runs every other feature's after_start
    hooks, which is a model download in a suite about receipts."""

    def __init__(self):
        self.jobs = []
        self.acted = []

    def add_repeat(self, kind, rule, **kw):
        job = {"id": f"job-{len(self.jobs) + 1}", "kind": kind, "rule": dict(rule)}
        self.jobs.append(job)
        return job

    def act(self, job_id, what):
        self.acted.append((job_id, what))
        return True


class World:
    """A real Goals store at the module's own db_path() - which is what
    restore_row() writes to, so the snapshot path is exercised against the
    store the receipt came from - and a stub scheduler."""

    def __init__(self, t=1_000_000.0, answer="approved", tier="ask"):
        self.clock = Clock(t)
        self.cards = Cards(answer=answer, tier=tier)
        self.sched = Sched()
        self.g = G.Goals(G.db_path(), clock=self.clock, scheduler=self.sched)

    def goal(self, text="Get married"):
        made = self.g.create(text, [
            {"id": "s1", "step": "Book the hall", "by": "", "needs": [], "measure": None,
             "done": False, "done_at": None},
            {"id": "s2", "step": "Send the invites", "by": "", "needs": ["s1"],
             "measure": None, "done": False, "done_at": None},
        ])
        return self.g.accept(made["id"])

    def plan(self, gid):
        return self.g.get(gid)["plan"]


class Stand:
    """A stand-in for the core's Handler and its three callbacks - the same
    shape jarvis_plugins.py calls install() with."""

    def __init__(self, origin=True, token=True):
        self.calls, self.sent = [], []
        self.origin, self.token = origin, token
        core = self

        class Handler:
            def __init__(self, path="/", body=b"{}"):
                self.path, self.body = path, body

            def do_GET(self):
                core.calls.append(("GET", self.path))

            def do_POST(self):
                core.calls.append(("POST", self.path))

            def _send(self, code, payload):
                core.sent.append((code, payload))
                return payload

        self.Handler = Handler

    def origin_ok(self, req):
        return self.origin

    def token_ok(self, req):
        return self.token

    def read_body(self, req):
        return req.body

    def get(self, path):
        self.Handler(path).do_GET()
        return self.sent[-1] if self.sent else (None, None)

    def post(self, path, body=b"{}"):
        self.Handler(path, body).do_POST()
        return self.sent[-1] if self.sent else (None, None)


FAKE_GITHUB = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
FAKE_AWS = "AKIA" + "IOSFODNN7EXAMPLE"


def db_bytes() -> bytes:
    """Everything the receipts database holds, -wal included: a WAL database
    keeps a just-written row in the side file, and a check that read only the
    main file would pass while the secret sat beside it."""
    out = b""
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(R.db_path()) + suffix)
        if path.is_file():
            out += path.read_bytes()
    return out


# --------------------------------------------------------------------------
#   The store
# --------------------------------------------------------------------------

def t_a_receipt_is_written_and_read_back():
    R._reset_for_tests()
    rid = R.record("goals.mark_step", "Ticked a step", before={"plan": "A"}, after={"plan": "B"})
    check("record() returns a receipt id", isinstance(rid, str) and rid.startswith("rc")
          and len(rid) > 6, rid)
    row = R.get(rid)
    check("... and the row reads back with what was recorded",
          isinstance(row, dict) and row["tool_name"] == "goals.mark_step"
          and row["summary"] == "Ticked a step"
          and row["before"] == {"plan": "A"} and row["after"] == {"plan": "B"},
          str(row))
    check("... it is not marked undone", row["undone"] is False and row["undone_at"] is None)
    check("... and the recent list carries it",
          rid in [r["receipt_id"] for r in R.recent()], str(R.recent()))
    check("... newest first", R.recent()[0]["receipt_id"] == rid)
    check("an id that was never written reads as None", R.get("rc" + "0" * 10) is None)
    check("a receipt with no text in it is still a receipt",
          isinstance(R.record("notes.write", ""), str))
    check("record() refuses a tool_name that is not text rather than guessing",
          R.record(None, "x") == "" and R.record("", "x") == "")
    check("get() and recent() never raise on rubbish input",
          R.get(None) is None and R.get(17) is None and isinstance(R.recent("nonsense"), list))


def t_undo_puts_a_real_goal_tick_back_exactly():
    R._reset_for_tests()
    w = World()
    goal = w.goal()
    gid = goal["id"]
    before = w.plan(gid)
    check("CONTROL: the second step waits on the first",
          before[1]["state"] == "locked" and before[1]["waiting_on"] == ["s1"], str(before[1]))

    out = w.g.mark_step(gid, 0, True)
    check("the tick changed the plan", out["plan"][0]["done"] is True
          and out["plan"][0]["done_at"] is not None)
    check("... and unlocked the step that waited on it", out["plan"][1]["state"] == "open")
    rid = out.get("receipt_id")
    check("the result carries the receipt id, so a caller can offer Undo",
          isinstance(rid, str) and rid.startswith("rc"), str(out.get("receipt_id")))
    receipt = R.get(rid)
    check("the receipt says what changed, in the owner's own words",
          "Book the hall" in receipt["summary"] and "Get married" in receipt["summary"],
          receipt["summary"])
    check("... and carries a before snapshot with the plan in it",
          receipt["has_before"] is True
          and receipt["before"]["id"] == gid
          and isinstance(receipt["before"]["plan"], str), str(receipt.get("before")))

    got = R.undo(rid)
    check("undo() really put it back", got["ok"] is True, str(got))
    check("... through the callable the process still held", got["path"] == "callable", str(got))
    check("... and said so in plain words", "Put back" in got.get("words", ""), str(got))
    after = w.plan(gid)
    check("the step is really not done again",
          after[0]["done"] is False and after[0]["done_at"] is None, str(after[0]))
    check("... the step that waited on it is locked again",
          after[1]["state"] == "locked" and after[1]["waiting_on"] == ["s1"], str(after[1]))
    check("... and the WHOLE plan is exactly what it was before the tick",
          after == before, f"{after}\n        {before}")
    check("... and the receipt records when it was put back",
          R.get(rid)["undone"] is True and R.get(rid)["undone_at"] is not None)


def t_a_second_undo_is_refused_and_applies_nothing():
    R._reset_for_tests()
    calls = {"n": 0}

    def reversal():
        calls["n"] += 1

    rid = R.record("goals.mark_step", "one change", before={"plan": "A"}, undo=reversal)
    first = R.undo(rid)
    second = R.undo(rid)
    check("the first undo ran the reversal", first["ok"] is True and calls["n"] == 1, str(first))
    check("a second undo is REFUSED, in plain words",
          second["ok"] is False and second.get("already_undone") is True
          and "already undone" in second.get("error", ""), str(second))
    check("... and it did NOT apply the reversal a second time", calls["n"] == 1, str(calls))
    check("... and it is a refusal, not an exception", isinstance(second, dict))

    # The real-world double tap: the owner ticks the step again by hand after
    # the Undo, then a retry of the OLD receipt arrives. It must not clobber
    # the new tick.
    w = World()
    gid = w.goal()["id"]
    ticked = w.g.mark_step(gid, 0, True)
    old = ticked["receipt_id"]
    check("CONTROL: the first undo of a goal tick succeeds", R.undo(old)["ok"] is True)
    w.g.mark_step(gid, 0, True)                       # a NEW change, by hand
    again = R.undo(old)
    check("a retry of an old receipt is refused, not applied again",
          again["ok"] is False and "already undone" in again.get("error", ""), str(again))
    check("... and the owner's own new tick is left exactly as it is",
          w.plan(gid)[0]["done"] is True, str(w.plan(gid)[0]))


def t_an_unknown_id_is_refused_and_raises_no_card():
    R._reset_for_tests()
    cards = Cards()
    out = R.undo("rc" + "9" * 10)
    check("undo() of an id that was never written is refused",
          out["ok"] is False and "no receipt" in out.get("error", ""), str(out))
    check("... and it is not recorded as an undo of anything",
          R.get("rc" + "9" * 10) is None)
    code, body = R.request_undo("rc" + "9" * 10, gate=cards.gate,
                                spawn=lambda fn: fn())
    check("the route answers 404 for it", code == 404, f"{code} {body}")
    check("... in plain words", "no receipt" in str(body.get("error")), str(body))
    check("... and NO card was raised for something that cannot happen",
          cards.cards == [], str(cards.cards))
    code, body = R.request_undo("no", gate=cards.gate,
                                spawn=lambda fn: fn())
    check("an id of the wrong shape is a 400, not a lookup", code == 400, f"{code} {body}")
    check("... and still no card", cards.cards == [])


def t_a_receipt_that_cannot_be_written_does_not_break_the_action():
    R._reset_for_tests()
    w = World()
    gid = w.goal()["id"]
    real = os.environ["JARVIS_RECEIPTS_DB"]
    # A folder where the database file should be: SQLite cannot open it.
    blocked = SCRATCH / "cannot-be-a-database"
    blocked.mkdir(exist_ok=True)
    os.environ["JARVIS_RECEIPTS_DB"] = str(blocked)
    try:
        check("record() answers \"\" rather than raising when it cannot write",
              R.record("goals.mark_step", "x", before={"a": 1}) == "")
        out = w.g.mark_step(gid, 0, True)
        check("the action it was recording still happened", out["plan"][0]["done"] is True,
              str(out.get("plan")))
        check("... and it carries no receipt id to offer", out.get("receipt_id") is None,
              str(out.get("receipt_id")))
        check("... and undo() of nothing is still a plain refusal, not a crash",
              R.undo("rc" + "1" * 10)["ok"] is False)
        check("... and the list route answers an empty list, not an error",
              R.recent() == [])
    finally:
        os.environ["JARVIS_RECEIPTS_DB"] = real
    check("CONTROL: with the database back, a receipt is written again",
          isinstance(R.record("goals.mark_step", "back", before={"a": 1}), str))


def t_a_snapshot_never_holds_a_secret():
    R._reset_for_tests()
    rid = R.record("notes.write", f"wrote the token {FAKE_GITHUB} into the note",
                   before={"note": f"key {FAKE_GITHUB}", "aws": FAKE_AWS,
                           "contact": "owner@example.org"},
                   after={"note": f"key {FAKE_GITHUB}"})
    row = R.get(rid)
    text = json.dumps(row)
    check("the GitHub token is not in the receipt at all", FAKE_GITHUB not in text, text)
    check("the AWS key is not in the receipt either", FAKE_AWS not in text, text)
    check("... and the row says it was redacted rather than dropping it silently",
          "[redacted" in text, text)
    check("CONTROL: the words that are not secrets are still there",
          "into the note" in row["summary"] and "aws" in row["before"], text)
    check("the project's own scrubber is what hid it",
          FAKE_GITHUB not in SC.scrub_text(FAKE_GITHUB)
          and "[redacted" in SC.scrub_text(FAKE_GITHUB))
    raw = db_bytes()
    check("... and the bytes of the database file do not hold the token either",
          FAKE_GITHUB.encode() not in raw, f"{len(raw)} bytes read")
    check("... nor the AWS key", FAKE_AWS.encode() not in raw)

    # Nothing recorded at all is the answer when the scrubber is not there -
    # the same rule chat history follows with no key. Fail closed, never guess.
    real_scrubber = R._scrubber
    R._scrubber = lambda: None
    try:
        check("no scrubber: nothing is recorded, rather than unscrubbed words",
              R.record("notes.write", f"key {FAKE_GITHUB}", before={"n": FAKE_GITHUB}) == "")
        rid2 = R.record("notes.write", "key " + FAKE_GITHUB, before={"n": 1})
        check("... and record() still does not raise", rid2 == "", rid2)
    finally:
        R._scrubber = real_scrubber


def t_the_snapshot_path_puts_it_back_when_the_callable_is_gone():
    R._reset_for_tests()
    w = World()
    gid = w.goal()["id"]
    before = w.plan(gid)
    out = w.g.mark_step(gid, None, True, step_id="s1")
    rid = out["receipt_id"]
    check("the tick landed", out["plan"][0]["done"] is True)
    check("... and the receipt names the code that can put it back",
          R.get(rid)["undo_callable"] == "jarvis_goals.restore_row",
          R.get(rid)["undo_callable"])

    # A NEW PROCESS: no in-memory callable. What is left is the row and the
    # module that knows how to apply the snapshot.
    R._reset_for_tests()
    got = R.undo(rid)
    check("undo() falls back to the before snapshot", got["ok"] is True, str(got))
    check("... and says plainly which path it took", got["path"] == "snapshot", str(got))
    check("... in words that name the snapshot",
          "before snapshot" in got.get("words", ""), str(got))
    check("... and the plan is really back", w.plan(gid) == before,
          f"{w.plan(gid)}\n        {before}")
    check("... and a second call is still refused",
          R.undo(rid).get("already_undone") is True)

    # The row on its own, with NOTHING registered in this process either: the
    # store has only the `undo_callable` name it wrote into the row, and must
    # find the code by that name.
    R._reset_for_tests()
    out1 = w.g.mark_step(gid, 0, True)
    rid1 = out1["receipt_id"]
    R._reset_for_tests()
    R._RESTORERS.clear()
    got1 = R.undo(rid1)
    check("with the registry empty too, the row's own name finds the code",
          got1["ok"] is True and got1["path"] == "snapshot", str(got1))
    check("... and the plan is really back again", w.plan(gid) == before, str(w.plan(gid)[0]))

    # The other half: a receipt with nothing left that can apply it. It must
    # refuse in plain words and mark NOTHING undone.
    R._reset_for_tests()
    lonely = R.record("some.other_tool", "changed something", before={"a": 1})
    out2 = R.undo(lonely)
    check("with no callable and no restorer it refuses", out2["ok"] is False, str(out2))
    check("... saying plainly that the snapshot is not enough on its own",
          "not enough" in out2.get("error", ""), str(out2))
    check("... and it is NOT marked undone, so it can be tried again",
          R.get(lonely)["undone"] is False)

    # A snapshot too big to keep is not half-kept: Undo refuses rather than
    # putting back part of a row.
    R._reset_for_tests()
    huge = R.record("some.tool", "a very large change", before={"blob": "x" * (R.MAX_SNAPSHOT + 100)})
    check("a snapshot too large to keep is replaced by a note, not truncated",
          R.get(huge)["has_before"] is False
          and R.get(huge)["before"].get("_receipts_snapshot") == "too large to keep",
          str(R.get(huge)["before"])[:200])
    check("... and Undo then refuses instead of restoring half a row",
          R.undo(huge)["ok"] is False and R.get(huge)["undone"] is False)


# --------------------------------------------------------------------------
#   The card: one, at tier ask, and nothing without a person's yes
# --------------------------------------------------------------------------

def t_the_undo_card_is_raised_once_and_a_denied_card_changes_nothing():
    R._reset_for_tests()
    w = World(answer="denied")
    gid = w.goal()["id"]
    out = w.g.mark_step(gid, 0, True)
    rid = out["receipt_id"]
    code, body = R.request_undo(rid, gate=w.cards.gate,
                                spawn=lambda fn: fn())
    check("the route answers 202: the card waits, the call does not",
          code == 202 and body.get("waiting") is True, f"{code} {body}")
    check("... and says nothing has happened yet", "Nothing has changed" in body.get("message", ""),
          str(body))
    check("ONE card was raised", len(w.cards.cards) == 1, str(w.cards.cards))
    card = w.cards.cards[0]
    check("... for the undo action", card["action"] == "undo_action", card["action"])
    check("... showing what will be put back, in the receipt's own words",
          "Book the hall" in card["prompt"], card["prompt"])
    check("... and what refusing costs",
          "nothing changes" in card["prompt"], card["prompt"])
    check("... with the receipt id and tool name in the detail, and no snapshot payload",
          card["detail"] == {"receipt_id": rid, "tool_name": "goals.mark_step"},
          str(card["detail"]))
    check("a DENIED card changed nothing: the tick is still there",
          w.plan(gid)[0]["done"] is True, str(w.plan(gid)[0]))
    check("... and the receipt is not marked undone", R.get(rid)["undone"] is False)
    last = R.status()["last"]
    check("... and the outcome is readable in plain words",
          last and last["outcome"] == "denied" and "turned down" in last["message"], str(last))
    check("... and the list route says nothing is waiting",
          R.list_view()["waiting"] is False)
    check("... and it still offers Undo, because the change is still there",
          [r["undoable"] for r in R.list_view()["receipts"] if r["receipt_id"] == rid]
          == [True], str([(r["receipt_id"], r["undoable"]) for r in R.list_view()["receipts"]]))

    # The same receipt, answered by a person
    R._reset_for_tests()
    w2 = World(answer="approved")
    gid2 = w2.goal()["id"]
    rid2 = w2.g.mark_step(gid2, 0, True)["receipt_id"]
    code, body = R.request_undo(rid2, gate=w2.cards.gate,
                                spawn=lambda fn: fn())
    check("an approved card puts it back", code == 202 and R.get(rid2)["undone"] is True,
          f"{code} {R.get(rid2)}")
    check("... and the step is really undone again", w2.plan(gid2)[0]["done"] is False)
    check("... and the outcome says so", "Put back" in R.status()["last"]["message"],
          str(R.status()["last"]))

    # A card for a receipt already undone is refused BEFORE it is raised.
    R._reset_for_tests()
    code, body = R.request_undo(rid2, gate=w2.cards.gate,
                                spawn=lambda fn: fn())
    check("a receipt already undone is refused before any card is raised",
          code == 409 and body.get("already_undone") is True, f"{code} {body}")
    check("... and no card was raised", len(w2.cards.cards) == 1, str(len(w2.cards.cards)))


def t_the_shipped_settings_ask_for_one_card_per_undo():
    """One card per undo, read out of the SHIPPED settings file rather than
    asserted about a stub: `undo_action` has no line in `[autonomy.tiers]`, so
    it takes `[autonomy] unknown_action_tier`, which the same file says is
    "ask". The MODULE must not force that tier (jarvis_gate.py's
    `_NO_RULE_FROM_DENIAL` rule, and this file's own docstring says why), so
    the shipped behaviour is pinned here instead."""
    import tomllib
    cfg = tomllib.loads((HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8"))
    auto = cfg.get("autonomy", {})
    tiers = auto.get("tiers", {})
    check("undo_action is deliberately absent from [autonomy.tiers] in the shipped file",
          "undo_action" not in tiers)
    check("... so it takes unknown_action_tier, and the shipped file says that is 'ask'",
          str(auto.get("unknown_action_tier", "")).strip().lower() == "ask",
          f"unknown_action_tier = {auto.get('unknown_action_tier')!r}")
    check("... and the module does NOT read that table itself, so a changed setting is "
          "the owner's own policy rather than a second opinion here",
          "tier_of(" not in (HERE / "jarvis_receipts.py").read_text(encoding="utf-8"))


def t_allowed_is_not_a_person_saying_yes():
    """ARCHITECTURE section 3's own trap: `check()` returns `allowed=True` at
    tier "notify" and at tier "auto" with nobody in the loop, so a boolean is
    not an answer. At tier "ask" only an outcome of "approved" is a yes."""
    R._reset_for_tests()
    w = World()
    gid = w.goal()["id"]
    rid = w.g.mark_step(gid, 0, True)["receipt_id"]

    class AllowedButNotApproved(Cards):
        def gate(self, action, detail, prompt):
            self.cards.append({"action": action, "detail": detail, "prompt": prompt})
            return Verdict(True, "ask", "denied")      # allowed, but nobody said yes

    gate = AllowedButNotApproved()
    code, body = R.request_undo(rid, gate=gate.gate, spawn=lambda fn: fn())
    check("allowed=True at tier ask with no approval does NOT reverse anything",
          R.get(rid)["undone"] is False and w.plan(gid)[0]["done"] is True,
          f"{code} {body}")
    check("... and it is recorded as the denial it was",
          R.status()["last"]["outcome"] == "denied", str(R.status()["last"]))

    # And the tier itself is the GATE's to decide, not this module's: a gate
    # that answers `allowed` for a tier of its own is obeyed, because there is
    # one policy reader and it is the gate. The shipped configuration has no
    # line for undo_action at all, which is "ask" (the check above), so this is
    # about what happens if the owner ever writes one.
    R._reset_for_tests()
    w2 = World()
    gid2 = w2.goal()["id"]
    rid2 = w2.g.mark_step(gid2, 0, True)["receipt_id"]

    class NotifyGate(Cards):
        def gate(self, action, detail, prompt):
            self.cards.append({"action": action, "detail": detail, "prompt": prompt})
            return Verdict(True, "notify", "notify")

    notify = NotifyGate()
    code, body = R.request_undo(rid2, gate=notify.gate, spawn=lambda fn: fn())
    check("a tier the GATE answers for itself is obeyed, rather than this module "
          "second-guessing the owner's own settings file",
          R.get(rid2)["undone"] is True and w2.plan(gid2)[0]["done"] is False,
          f"{code} {body} {R.status()['last']}")
    check("... and the card it raised was still the one card, for undo_action",
          [c["action"] for c in notify.cards] == ["undo_action"], str(notify.cards))


def t_one_card_at_a_time():
    R._reset_for_tests()
    w = World(answer="denied")
    gid = w.goal()["id"]
    rid = w.g.mark_step(gid, 0, True)["receipt_id"]
    # A spawn that does nothing: the card is left waiting, exactly as a real
    # 15-minute card leaves it.
    code, body = R.request_undo(rid, gate=w.cards.gate,
                                spawn=lambda fn: None)
    check("the first request waits", code == 202 and R.status()["pending"] is not None,
          f"{code} {R.status()}")
    code2, body2 = R.request_undo(rid, gate=w.cards.gate,
                                  spawn=lambda fn: None)
    check("a second request says a card is already waiting, in plain words",
          code2 == 202 and body2.get("waiting") is True
          and "already waiting" in body2.get("message", ""), f"{code2} {body2}")
    check("... and it raised no card of its own: it never reached the gate",
          w.cards.cards == [], str(w.cards.cards))
    check("... and nothing was reversed while the card waits",
          R.get(rid)["undone"] is False and w.plan(gid)[0]["done"] is True)
    # The marker is cleared by the decision itself, so the next request works.
    R._reset_for_tests()
    check("... and clearing it leaves nothing waiting", R.status()["pending"] is None)
    code3, body3 = R.request_undo(rid, gate=w.cards.gate,
                                  spawn=lambda fn: fn())
    check("... so the receipt can be asked about again", code3 == 202
          and len(w.cards.cards) == 1, f"{code3} {body3}")
    check("... and that card, denied, still changed nothing",
          R.get(rid)["undone"] is False and w.plan(gid)[0]["done"] is True)


# --------------------------------------------------------------------------
#   The routes, through the core's own Handler
# --------------------------------------------------------------------------

def t_install_turns_the_folder_into_two_live_routes():
    R._reset_for_tests()
    stand = Stand()
    line = R.install(stand.Handler, origin_ok=stand.origin_ok, token_ok=stand.token_ok,
                     read_body=stand.read_body)
    check("install() returns a banner line naming the feature",
          isinstance(line, str) and "receipts" in line, line)
    check("... and a second install() says it is already on, without double-wrapping",
          "already on" in R.install(stand.Handler, origin_ok=stand.origin_ok,
                                    token_ok=stand.token_ok, read_body=stand.read_body))

    rid = R.record("goals.mark_step", "Ticked a step", before={"plan": "A"})
    code, body = stand.get("/api/receipts")
    check("GET /api/receipts answers the list, behind the token",
          code == 200 and body["ok"] is True
          and rid in [r["receipt_id"] for r in body["receipts"]], f"{code} {str(body)[:200]}")
    check("... with the tier the undo needs, so an app knows it asks",
          body["undo_tier"] == "ask" and body["undo_action"] == "undo_action", str(body.keys()))
    code, body = stand.get("/api/receipts?limit=1")
    check("... and honours ?limit=", code == 200 and len(body["receipts"]) == 1, f"{code} {body}")
    code, body = stand.get("/api/receipts?limit=lots")
    check("... and refuses a limit that is not a number",
          code == 400 and "whole number" in str(body.get("error")), f"{code} {body}")

    before_calls = len(stand.calls)
    code, body = stand.get("/api/other")
    check("every other path reaches the core, untouched",
          len(stand.calls) == before_calls + 1 and stand.calls[-1] == ("GET", "/api/other"),
          str(stand.calls[-1]))
    code, body = stand.post("/api/other", b"{}")
    check("... on POST too", stand.calls[-1] == ("POST", "/api/other"), str(stand.calls[-1]))
    # The route's own door: a stub card that is turned down and a spawn that
    # runs it here, so this proves the route's shape and never opens a real
    # 15-minute card.
    denied = Cards(answer="denied")
    real_gate, real_spawn = R._gate, R._spawn
    R._gate, R._spawn = denied.gate, (lambda fn: fn())
    try:
        code, body = stand.post(f"/api/receipts/{rid}/undo", b"{}")
        check("the POST is answered here (202, waiting) rather than by the core",
              code == 202 and body.get("waiting") is True, f"{code} {body}")
        check("... it raised ONE card for that one receipt",
              len(denied.cards) == 1
              and denied.cards[0]["detail"]["receipt_id"] == rid, str(denied.cards))
        check("... and the core never saw it", stand.calls[-1] == ("POST", "/api/other"))
        check("CONTROL: the denied card changed nothing", R.get(rid)["undone"] is False)
    finally:
        R._gate, R._spawn = real_gate, real_spawn

    wrong = Stand(token=False)
    R.install(wrong.Handler, origin_ok=wrong.origin_ok, token_ok=wrong.token_ok,
              read_body=wrong.read_body)
    code, body = wrong.get("/api/receipts")
    check("a bad or missing token is a 401, and the list is not served",
          code == 401 and "Token" in str(body.get("error")), f"{code} {body}")
    code, body = wrong.post(f"/api/receipts/{rid}/undo", b"{}")
    check("... on the POST too, so nothing is reversed for a caller without the token",
          code == 401 and R.get(rid)["undone"] is False, f"{code} {body}")

    cross = Stand(origin=False)
    R.install(cross.Handler, origin_ok=cross.origin_ok, token_ok=cross.token_ok,
              read_body=cross.read_body)
    code, body = cross.get("/api/receipts")
    check("a cross-origin request is a 403", code == 403, f"{code} {body}")
    code, body = cross.post(f"/api/receipts/{rid}/undo", b"{}")
    check("... on the POST too", code == 403 and R.get(rid)["undone"] is False, f"{code} {body}")


def t_the_goals_route_hands_back_the_receipt_id():
    """The wiring end to end, through jarvis_goals' own route. `G.get` is
    pointed at this test's own store, the way jarvis_goals' own suite does it:
    the module's singleton would start the REAL scheduler, whose start-up runs
    every other feature's after_start hook - a model download, in a suite
    about receipts."""
    R._reset_for_tests()
    w = World()
    gid = w.goal()["id"]
    real_get = G.get
    G.get = lambda: w.g
    try:
        code, body = G.handle_post(f"{G.PATH}/{gid}/step", {"index": 0, "done": True})
    finally:
        G.get = real_get
    check("POST /api/goals/<id>/step still answers 200 with the goal",
          code == 200 and body.get("ok") is True and body["goal"]["plan"][0]["done"] is True,
          f"{code} {str(body)[:200]}")
    rid = body["goal"].get("receipt_id")
    check("... and the goal it hands back carries the receipt id",
          isinstance(rid, str) and rid.startswith("rc"), str(body["goal"].get("receipt_id")))
    check("... which is a real receipt for that tick",
          R.get(rid)["tool_name"] == "goals.mark_step", str(R.get(rid)))
    check("undo() of it puts the route's own change back",
          R.undo(rid)["ok"] is True and w.g.get(gid)["plan"][0]["done"] is False)


def t_the_tick_still_works_with_no_receipts_module_at_all():
    """jarvis_receipts.py is optional. Read from the parse tree of the module
    that calls it: every import of it must be inside a try, so a backend
    folder without the file still ticks steps."""
    src = (HERE / "jarvis_goals.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports, inside = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name == "jarvis_receipts" for a in node.names):
            imports.append(node)
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for child in ast.walk(node):
                if isinstance(child, ast.Import) and any(
                        a.name == "jarvis_receipts" for a in child.names):
                    inside.add(id(child))
    loose = [n.lineno for n in imports if id(n) not in inside]
    check("every import of jarvis_receipts.py in jarvis_goals.py is inside a try",
          imports and not loose, f"{len(imports)} import(s), loose at lines {loose}")
    check("... and none of them is at the top level of the file",
          "\nimport jarvis_receipts" not in src)
    check("... and the call that records is wrapped too, so it can only ever "
          "return \"\"",
          "def _record_step_receipt" in src
          and '    except Exception:\n        return ""' in src)


def t_the_plugin_folder_and_the_module_agree():
    repo = HERE.parent
    manifest = repo / "plugins" / "ready" / "receipts" / "plugin.json"
    check("the drop-in folder is there", manifest.is_file())
    if not manifest.is_file():
        return
    data = json.loads(manifest.read_text(encoding="utf-8"))
    check("it names this module, to be called with the core's Handler",
          data.get("module") == "jarvis_receipts" and data.get("install") == "handler",
          str(data))
    check("it has a name, a summary and a loader position",
          data.get("name") == "receipts" and bool(data.get("summary"))
          and isinstance(data.get("stack_order"), int), str(data))
    check("... and it replaces no patch, which is the whole point of the folder",
          "replaces_patch" not in data, str(sorted(data)))
    check("the module it names really has install()",
          callable(getattr(R, "install", None)))
    # THE FOLDERS THAT REPLACE A PATCH are "every folder the old patch stack
    # had", and `pictures` at 141 is the highest of them. A folder that replaces
    # NO patch is deliberately added later, and sorts later on purpose - this
    # feature's own README: "the order they were added rather than in the middle
    # of somebody else's". So the claim is the one the README makes, "after every
    # folder the old patch stack had" - and NOT "the highest number in the
    # folder", which the old reading of this check asserted and which broke the
    # moment a later no-patch folder existed. `plugins/ready/auto-router` (144)
    # is that folder (2026-10-14), and Stream 4's was next.
    registry = json.loads((repo / "plugins" / "registry.json").read_text(encoding="utf-8"))
    catalogued = {e.get("name") for e in registry.get("entries", [])
                  if e.get("bucket") == "plug-in"}
    orders = []
    for name in catalogued:
        other = repo / "plugins" / "ready" / name / "plugin.json"
        if other.is_file():
            orders.append((json.loads(other.read_text(encoding="utf-8")).get("stack_order"), name))
    # REWRITTEN 2026-10-14, by the branch that added `plugins/ready/vault`
    # (feat/blind-credential-vault, PR #433). This used to read
    # `max(orders)[1] == "receipts"` - "receipts is the LAST folder" - which is
    # a claim about every feature added after it as much as about this one, so
    # the next patch-free folder broke it while nothing about receipts had
    # changed. What the claim was for, and what it says now: receipts sits
    # AFTER every folder the old patch stack wrote. 141 is `pictures`, the
    # highest position in `plugins/registry.json`; everything at or below it
    # came from a patch, and receipts is above all of them. A future folder
    # lands after receipts and this stays true.
    from_patches = [(o, n) for o, n in orders if isinstance(o, int) and o <= 141]
    check("... and its loader position is after every folder the old patch stack had",
          bool(from_patches) and max(from_patches)[0] < data.get("stack_order", 0),
          f"receipts at {data.get('stack_order')}, the highest from the stack is "
          f"{max(from_patches) if from_patches else None}")


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and callable(fn):
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
