"""test_outbox.py - what Jarvis still owes you survives a restart, and is said once.

    py -3 -B backend/test_outbox.py

No pytest, no network, no real backend. Real SQLite in temp files, real JSON
files in temp folders, and one fake "restart" that is exactly the lifecycle hook
the queue already documents (`jarvis_jobs.shutdown()` then `_init()`, which is
what `test_jobs.py` uses to move the database between cases).

WHY THIS SUITE EXISTS. `docs/DEFECT-REGISTER.md` and the 2026-11-04 review name
the same defect: a backend restart LOSES a pending approval card. The job row
survives - `waiting_approval`, one pending grant - but the event that told the
apps about it was a moment, not a record, so nothing ever says it again, and the
job waits for ever. A completion notice has the same shape: a job that finished
while the process was going down was told to nobody and is not re-told.

The fix (pattern 5B, the owner-forwarded spec, Part II section 2.6B) is an
outbox: write down what you are about to say, with a deterministic `(kind, key)`,
BEFORE you say it; settle the entry only once it has been said; and on startup
re-announce whatever is still owed. What that buys, and what this file checks:

  1. **Nothing is lost.** Every entry is on disk before the send. The check that
     proves it reads the file from inside the sender, which is the only place
     that can see the ordering.
  2. **Nothing is said twice.** The `(kind, key)` pair plus the settle means a
     repeated park, a repeated finish and a repeated restart announce once. The
     crash window is stated honestly rather than hidden: a process that dies
     between the send and the settle repeats ONE notice on the next start, and
     that is at-least-once by design - the opposite mistake loses the card.
  3. **A card is not settled by being announced.** It is settled by being
     ANSWERED (`answer()`), refused (`_stop_denied`) or cancelled (`cancel()`),
     so an unanswered card is announced again by every restart.
  4. **Nothing here approves anything.** Rehydration re-announces; the grant is
     still decided by `decide_grant()` and by nothing else. Rule 4 untouched.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _where import require_shipped  # noqa: E402

require_shipped("jarvis_jobs.py", "jarvis_outbox.py")

_BASE = Path(tempfile.gettempdir()) / "jarvis-outbox-suite"
os.makedirs(_BASE, exist_ok=True)
_WORK = Path(tempfile.mkdtemp(dir=str(_BASE), prefix="run-"))

# Never the owner's real queue, real settings folder or real outbox.
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", str(_WORK / "cfg"))
os.environ.setdefault("JARVIS_CONFIG_DIR", str(_WORK / "cfg"))
os.environ["JARVIS_JOBS_DB"] = str(_WORK / "jobs.db")
os.environ["JARVIS_OUTBOX_PATH"] = str(_WORK / "outbox.json")
os.environ["JARVIS_RECEIPTS_DB"] = str(_WORK / "receipts.db")

for _c in (HERE / "jarvis-framework.toml", HERE / "rebuilt" / "jarvis-framework.toml"):
    if _c.is_file():
        os.environ["JARVIS_FRAMEWORK_TOML"] = str(_c)
        break

import jarvis_jobs as J     # noqa: E402
import jarvis_outbox as O   # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []

#: An action in no tier table anywhere, so `require()` asks (the shipped
#: `unknown_action_tier` is "ask"). A real action would make this suite depend
#: on the owner's policy for a result the test is not about.
PROBE = "outbox_probe_action"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" +
          (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def fresh_queue():
    """A queue and an outbox of their own, on a clean writer thread."""
    J.shutdown()
    d = Path(tempfile.mkdtemp(dir=str(_BASE), prefix="case-"))
    J.DB_PATH = d / "jobs.db"
    O.bind(d / "outbox.json")
    O._reset_for_tests()
    O.bind(d / "outbox.json")
    return d


def reading(path):
    """The outbox document as it is on disk RIGHT NOW, or {}."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def keys_in(doc, kind=None):
    return [f"{e['kind']}:{e['key']}" for e in (doc.get("entries") or [])
            if kind is None or e.get("kind") == kind]


# ==========================================================================
#   1. The store: write first, settle after, never two slots for one notice
# ==========================================================================

def t_write_before_send_and_settle_after():
    fresh_queue()
    seen = {}

    def send(entry):
        seen["on_disk"] = O.get(entry["kind"], entry["key"])
        seen["file"] = reading(O.path())
        return True

    got = O.deliver("job_done", "job:abc:done", {"row": {"id": "abc"}}, send)
    check("the first delivery says so", got == "sent", got)
    check("the entry was ALREADY on disk when the sender ran",
          seen["on_disk"] is not None and seen["file"].get("entries"),
          seen.get("file"))
    check("... and it was pending at that moment, not settled",
          (seen["on_disk"] or {}).get("state") == "pending", seen.get("on_disk"))
    check("afterwards it is settled", (O.get("job_done", "job:abc:done") or {})
          .get("state") == "done")
    check("the file is a real JSON document with a version",
          reading(O.path()).get("version") == 1)


def t_one_key_is_one_slot():
    fresh_queue()
    a = O.enqueue("job_card", "job:x:grant:probe", {"row": {"id": "x"}})
    b = O.enqueue("job_card", "job:x:grant:probe", {"row": {"id": "x"}})
    check("the first enqueue writes it", a["state"] == "pending", a)
    check("the second is a duplicate and writes nothing", b["state"] == "duplicate", b)
    check("... there is exactly ONE entry", len(O.pending()) == 1, O.pending())
    O.resolve("job_card", "job:x:grant:probe")
    c = O.enqueue("job_card", "job:x:grant:probe", {})
    check("a settled key is still a duplicate: a notice is delivered once",
          c["state"] == "duplicate" and c["entry"]["state"] == "done", c)
    check("resolve is idempotent", O.resolve("job_card", "job:x:grant:probe") is False)


def t_a_card_stays_owed_until_it_is_answered():
    fresh_queue()
    calls = []
    got = O.deliver("job_card", "job:y:grant:probe", {"row": {"id": "y"}},
                    lambda e: calls.append(e["key"]) or False)
    check("a sender returning False keeps the card owed", got == "owed"
          and [p["key"] for p in O.pending()] == ["job:y:grant:probe"], (got, O.pending()))
    got = O.deliver("job_card", "job:y:grant:probe", {"row": {"id": "y"}},
                    lambda e: calls.append(e["key"]) or False)
    check("a repeated park says NOTHING a second time",
          got == "owed" and calls == ["job:y:grant:probe"], (got, calls))
    check("until it is resolved by name", O.resolve("job_card", "job:y:grant:probe")
          and O.pending() == [])


def t_a_sender_that_raises_leaves_it_owed_and_is_named():
    fresh_queue()

    def boom(entry):
        raise RuntimeError("the event bus is gone")

    got = O.deliver("pr_ci_notice", "pr:1:abc:all_green", {"x": 1}, boom)
    check("a raising sender is 'failed', never a crash", got == "failed", got)
    check("... the entry stays pending", len(O.pending()) == 1, O.pending())
    check("... and the failure is visible in status()",
          "send failed" in (O.status().get("last_error") or ""), O.status())


def t_rehydrate_announces_what_a_crash_left_behind():
    fresh_queue()
    O.enqueue("job_done", "job:1:done", {"row": {"id": "1"}})
    O.enqueue("job_card", "job:2:grant:probe", {"row": {"id": "2"}})
    sent = []
    done = O.rehydrate(lambda e: sent.append(e["key"]) or
                       (False if e["kind"] == "job_card" else True))
    check("every pending entry was announced once",
          sorted(sent) == ["job:1:done", "job:2:grant:probe"], sent)
    check("the noticed one is settled, the card is not",
          "job_done:job:1:done" in done and [p["key"] for p in O.pending()]
          == ["job:2:grant:probe"], (done, O.pending()))
    sent.clear()
    O.rehydrate(lambda e: sent.append(e["key"]) or True)
    check("a second rehydrate only re-announces the card",
          sent == ["job:2:grant:probe"], sent)


def t_the_kinds_and_the_keys_are_checked():
    fresh_queue()
    for bad in ("", "job", "JOBCARD", None):
        try:
            O.enqueue(bad, "k")
            ok = False
        except ValueError:
            ok = True
        check(f"kind {bad!r} is refused - the key has to be composeable", ok)
    try:
        O.enqueue("job_card", "")
        ok = False
    except ValueError:
        ok = True
    check("an empty key is refused", ok)
    check("the shipped kinds are the three the spec names",
          tuple(O.KINDS) == ("job_card", "job_done", "pr_ci_notice"), O.KINDS)


def t_a_damaged_file_is_set_aside_and_costs_one_restart():
    d = fresh_queue()
    O.path().parent.mkdir(parents=True, exist_ok=True)
    O.path().write_text("{not json", encoding="utf-8")
    check("a damaged outbox reads as empty rather than raising",
          O.pending() == [] and O.status()["entries"] == 0, O.status())
    stray = list(O.path().parent.glob("outbox.json.corrupt-*"))
    check("... and the damaged file is PRESERVED, not overwritten", len(stray) == 1, stray)


def t_the_file_is_bounded_and_never_drops_something_owed():
    fresh_queue()
    for i in range(O.MAX_ENTRIES + 25):
        O.enqueue("job_done", f"job:{i}:done", {"row": {"id": str(i)}})
        O.resolve("job_done", f"job:{i}:done")
    O.enqueue("job_card", "job:owed:grant:probe", {"row": {"id": "owed"}})
    st = O.status()
    check("settled entries are pruned back to the cap",
          st["entries"] <= O.MAX_ENTRIES + 1, st["entries"])
    check("... and the one still owed is never pruned",
          [p["key"] for p in O.pending()] == ["job:owed:grant:probe"], O.pending())


def t_the_path_follows_the_queue_it_belongs_to():
    d = fresh_queue()
    check("bind() wins", str(O.path()) == str(d / "outbox.json"), O.path())
    saved = {k: os.environ.get(k)
             for k in ("JARVIS_OUTBOX_PATH", "JARVIS_JOBS_DB")}
    try:
        O.bind(None)
        os.environ.pop("JARVIS_OUTBOX_PATH", None)
        os.environ["JARVIS_JOBS_DB"] = str(d / "elsewhere" / "jobs.db")
        check("unbound, it sits beside JARVIS_JOBS_DB",
              O.path() == d / "elsewhere" / "outbox.json", O.path())
        os.environ.pop("JARVIS_JOBS_DB", None)
        check("with neither, it is outbox.json in the settings folder",
              O.path().name == "outbox.json" and "cfg" in str(O.path()), O.path())
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        O.bind(d / "outbox.json")


def t_the_atomic_writer_leaves_no_half_file():
    fresh_queue()
    O.enqueue("job_done", "job:z:done", {})
    left = [p.name for p in O.path().parent.iterdir() if p.name.endswith(".tmp")]
    check("no .tmp file is left behind", left == [], left)
    check("the document holds exactly what was written",
          keys_in(reading(O.path())) == ["job_done:job:z:done"], reading(O.path()))


# ==========================================================================
#   2. The queue: a parked card survives the process, exactly once
# ==========================================================================

def t_a_parked_card_is_written_before_it_is_announced():
    d = fresh_queue()
    announced = []
    real = J._emit

    def recorder(row, note="", force=True):
        # The order check: the outbox file ALREADY holds the card when the
        # event is published.
        announced.append((row.get("id"), note, reading(O.path())))
        return real(row, note=note, force=force)

    J.register("outbox_parker", lambda ctx, p: ctx.require(PROBE))
    J._emit = recorder
    try:
        jid = J.create("outbox_parker", {}, label="parker", caps=[])
        J.run_due()
    finally:
        J._emit = real
    row = J.get(jid)
    check("the job parked with one pending grant",
          row["state"] == "waiting_approval" and len(J.pending_grants(jid)) == 1, row)
    card = f"job_card:{J.card_key(jid, PROBE)}"
    check("the outbox holds the card, deterministically keyed", card in keys_in(reading(O.path())),
          keys_in(reading(O.path())))
    parked = [a for a in announced if a[2].get("entries")]
    check("the card was announced exactly once", len(parked) == 1, announced)
    check("... and the entry was on disk BEFORE the announcement",
          bool(parked) and card in keys_in(parked[0][2]), parked[:1])
    check("a card announced is not settled (nobody answered it)",
          (O.get("job_card", J.card_key(jid, PROBE)) or {}).get("state") == "pending")


def t_a_restart_re_announces_an_unanswered_card_once():
    fresh_queue()
    J.register("outbox_parker2", lambda ctx, p: ctx.require(PROBE))
    jid = J.create("outbox_parker2", {}, label="parker2", caps=[])
    J.run_due()
    check("parked", (J.get(jid) or {}).get("state") == "waiting_approval")

    announced = []
    real = J._emit
    J._emit = lambda row, note="", force=True: announced.append((row.get("id"), note))
    try:
        # THE RESTART: the documented lifecycle hook, not a trick.
        J.shutdown()
        J._init()
        mine = [a for a in announced if a[0] == jid]
        check("after a restart the card is announced again", len(mine) == 1, announced)
        check("... with its note, so the app can draw it",
              mine and "outbox_probe_action" in mine[0][1], mine)
        # A second init in the SAME process is not a second restart.
        J._init()
        mine = [a for a in announced if a[0] == jid]
        check("a second init in one process announces nothing again", len(mine) == 1,
              announced)
    finally:
        J._emit = real
    check("... and the card is STILL owed, because nobody answered it",
          [p["key"] for p in O.pending("job_card")] == [J.card_key(jid, PROBE)],
          O.pending())


def t_answering_the_card_settles_it_for_good():
    fresh_queue()
    J.register("outbox_parker3", lambda ctx, p: ctx.require(PROBE))
    jid = J.create("outbox_parker3", {}, label="parker3", caps=[])
    J.run_due()
    out = J.answer(jid, False, by="test")
    check("the owner's no is accepted once", out.get("ok") is True, out)
    check("... and the card is no longer owed",
          J.card_key(jid, PROBE) not in [p["key"] for p in O.pending()], O.pending())
    announced = []
    real = J._emit
    J._emit = lambda row, note="", force=True: announced.append(row.get("id"))
    try:
        J.shutdown()
        J._init()
    finally:
        J._emit = real
    check("a restart does not re-announce an answered card", jid not in announced, announced)
    check("... and it does not approve anything: the row is failed, not run",
          (J.get(jid) or {}).get("state") == "failed", J.get(jid))


def t_a_cancelled_job_owes_nobody_its_question():
    fresh_queue()
    J.register("outbox_parker4", lambda ctx, p: ctx.require(PROBE))
    jid = J.create("outbox_parker4", {}, label="parker4", caps=[])
    J.run_due()
    check("parked first", len(O.pending("job_card")) == 1, O.pending())
    check("cancel works", J.cancel(jid, by="test") is True)
    check("... and the card is settled by the cancel",
          O.pending("job_card") == [], O.pending("job_card"))


def t_a_completion_notice_is_written_first_and_said_once():
    fresh_queue()
    J.register("outbox_finisher", lambda ctx, p: {"did": "the work"})
    announced = []
    seen_before = []
    real = J._emit

    def recorder(row, note="", force=True):
        doc = reading(O.path())
        announced.append((row.get("id"), row.get("state")))
        seen_before.append(keys_in(doc, "job_done"))
        return real(row, note=note, force=force)

    J._emit = recorder
    try:
        jid = J.create("outbox_finisher", {}, label="finisher", caps=[])
        J.run_due()
    finally:
        J._emit = real
    check("the job finished", (J.get(jid) or {}).get("state") == "done")
    check("the completion notice was on disk before it was published",
          seen_before and any(k.endswith(f"job:{jid}:done") for k in seen_before[-1]),
          seen_before)
    check("... and it is settled once delivered",
          (O.get("job_done", J.done_key(jid, "done")) or {}).get("state") == "done")

    announced.clear()
    J._emit = lambda row, note="", force=True: announced.append(row.get("id"))
    try:
        J.shutdown()
        J._init()
    finally:
        J._emit = real
    check("a restart does not repeat a delivered completion notice",
          jid not in announced, announced)


def t_a_cancelled_job_gets_no_completion_notice():
    fresh_queue()
    J.register("outbox_slow", lambda ctx, p: time.sleep(0.01) or "done")
    started = []
    real = J._emit
    J._emit = lambda row, note="", force=True: started.append((row.get("id"), note))
    jid = ""
    try:
        jid = J.create("outbox_slow", {}, label="slow", caps=[])
    finally:
        J._emit = real
    # Cancel while queued: no run, no notice, and none owed.
    J.cancel(jid, by="test")
    check("a cancelled job owes no completion notice",
          O.get("job_done", J.done_key(jid, "cancelled")) is None
          and O.pending("job_done") == [], O.pending("job_done"))


def t_status_reports_what_is_owed_without_answering_it():
    fresh_queue()
    J.register("outbox_parker5", lambda ctx, p: ctx.require(PROBE))
    before = J.status()["outbox"]
    check("status has an outbox block", isinstance(before, dict) and before["available"], before)
    jid = J.create("outbox_parker5", {}, label="parker5", caps=[])
    J.run_due()
    after = J.status()["outbox"]
    check("a parked card shows as one owed job_card",
          after["pending"] == 1 and after["by_kind"]["job_card"] == 1, after)
    check("... and reading status did not settle it",
          len(O.pending("job_card")) == 1, O.pending("job_card"))
    check("... nor answer it: the grant is still pending",
          len(J.pending_grants(jid)) == 1)


# ==========================================================================

def main() -> int:
    tests = [(n, f) for n, f in list(globals().items())
             if n.startswith("t_") and callable(f)]
    for name, fn in tests:
        print(f"--- {name} ---")
        try:
            fn()
        except Exception as exc:                    # pragma: no cover
            traceback.print_exc()
            check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    print(f"      ({len(tests)} t_ function(s) were found by name and run)")
    if FAILED:
        print("failed: " + "; ".join(FAILED))
    J.shutdown()
    shutil.rmtree(_WORK, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
