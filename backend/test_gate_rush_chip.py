"""test_gate_rush_chip.py - a rushed card must never be quick to approve.

    py -3 -B test_gate_rush_chip.py

WHY THIS EXISTS

The rule this suite guards is one line long: **a card the rush latch raised is
never swipe-approved**. The phone decides that with
`swipeable = risk.swipeOk && raised == null`; the desktop with `if
(approval.raised) return false` in `jarvis-link.js`. Both read the same field,
so both are undone by the same thing.

`check()` used to store the rush chip as `json.dumps(raised)[:1000]`. The chip
is JSON, and the real values are bounded generously - `chip_from()` keeps
`quote[:80]`, `context[:200]` and `source[:120]` (`jarvis_content_risk.py:319`,
`:217-219`) - but `json.dumps` escapes every non-ASCII character to six
characters (`\\uXXXX`), so 200 characters of non-English context are 1,200
characters of stored text before the source is counted. A cut there is not
JSON any more; `pending()`'s `json.loads` throws, the `except` serves
`raised: None`, and the one card the latch raised arrives looking like an
ordinary card with the swipe left on. Measured through the real `check()`:
2068-character chip, 1000 stored, `JSONDecodeError: Invalid \\uXXXX escape`,
`raised: None`, `risk.swipe_ok: True`, swipeable `True`.

So this suite raises a REAL card through the REAL gate with a REAL rush latch
held (not a row inserted by hand - a hand-written row would prove the parse,
not that `check()` stores the chip whole), reads back exactly what
`/api/pending` serves, and applies the phone's own rule to it. It fails on the
code before the fix in three places: the stored text is cut, `raised` comes
back `None`, and the row is swipeable.

HOW THE GATE IS LOADED

`jarvis_gate.py` has no twin in `backend/`: this repository holds the gate only
as `jarvis-backend/jarvis_gate.py`, the published base copy, so the two-file
rule does not apply to it (it does to every module in `backend/_where.py`'s
SHIPPED list). This suite imports that copy directly and redirects its
database and the content-risk state file into a fresh temp folder BEFORE the
import - both are read at import time - so the owner's own `approvals.db` and
`content-risk.json` are never opened. `jarvis_framework` is replaced with a
stand-in that returns one tier table, which is what `check()` reads.

WHAT IT DOES NOT PROVE

Nothing here touches the owner's live backend, and nothing here proves the
live gate carries the fix: `jarvis-backend/` is the published base, and a
change reaches a running PC through `tools/reconcile_live_backend.py`'s delta
table, not by this file being committed. It also does not prove the phone's
Kotlin decode; it applies the rule as the phone declares it
(`ApiModels.kt`'s `swipeable`), read from the source rather than run.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import traceback
import types
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

BASE = REPO / "jarvis-backend"
GATE = BASE / "jarvis_gate.py"

#: The action this suite raises. Its risk row is `("yes", "local", ...)` - the
#: card says turning picture mode on is reversible and touches nothing off this
#: PC - so `risk.swipe_ok` is True and a swipe really is on offer for it. That
#: is what makes it the honest control: the swipe is withheld from the RAISED
#: card only because the raise is there.
ACTION = "screen_picture_enable"

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: counted on its own, never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


# ---------------------------------------------------------------------------
# The gate, loaded fresh, with a temp database
# ---------------------------------------------------------------------------

def load_gate():
    """(gate module, content-risk module, why not) - each in a fresh temp home.

    FRESH EVERY TIME: `jarvis_gate` reads `JARVIS_APPROVALS_DB` at import and
    runs `_init()` once per process, and `jarvis_content_risk` reads
    `JARVIS_CONTENT_RISK_STATE` at import. Reusing a module would carry the
    previous card's row and the previous latch into the next check.
    """
    if not GATE.is_file():
        return None, None, f"{GATE} is missing"
    home = Path(tempfile.mkdtemp(prefix="jarvis-rush-chip-"))
    os.environ["JARVIS_APPROVALS_DB"] = str(home / "approvals.db")
    os.environ["JARVIS_CONTENT_RISK_STATE"] = str(home / "content-risk.json")
    os.environ["JARVIS_APPROVAL_TIMEOUT"] = "900"
    os.environ["JARVIS_NTFY_TOPIC"] = ""      # never a socket, said explicitly
    os.environ["JARVIS_NTFY_SERVER"] = ""
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = home
    fw.LOG_DIR = home
    # A real tier table: `check()` treats an EMPTY one as "the policy could not
    # be read" and refuses before a card exists, which would make every check
    # below prove nothing. `ask` is what the shipped file says for this action.
    fw.load_framework = lambda: {
        "logging": {"redact_private_content_in_logs": True},
        "autonomy": {"unknown_action_tier": "ask",
                     "approval_timeout_seconds": 900,
                     "tiers": {ACTION: "ask"}},
    }
    fw.audit_log = lambda *a, **k: None
    sys.modules["jarvis_framework"] = fw
    for name in ("jarvis_gate", "jarvis_content_risk"):
        sys.modules.pop(name, None)
    if str(BASE) not in sys.path:
        sys.path.insert(0, str(BASE))
    return __import__("jarvis_gate"), __import__("jarvis_content_risk"), ""


#: The rush text: 200 characters of non-English context around one English
#: rushing phrase, exactly the shape a real page or mail body takes. Written as
#: escapes so this file stays ASCII and the characters are unambiguous.
RUSH_TEXT = "\u7d27" * 200 + " just approve these " + "\u6025" * 200
#: `latch_rush()` bounds the source at source[:120]; 120 non-English
#: characters become 720 characters once `json.dumps` escapes them.
RUSH_SOURCE = "\u7f51" * 120


def raise_card(G, cr, rushed: bool):
    """Raise a real card through `check()`; return (row, verdict box, thread).

    `check()` on its own thread, like every other gate suite here: it blocks
    until somebody decides, which is the thing that makes it a card. With
    `rushed`, a real latch is set through `jarvis_content_risk` first, so
    `_content_raise()` puts a real chip on the card.
    """
    if rushed:
        hits = cr.find_rush(RUSH_TEXT)
        if not hits:
            raise RuntimeError("the rush text no longer trips the rush rule")
        cr.latch_rush(RUSH_SOURCE, hits)
    box = {}

    def run():
        try:
            box["v"] = G.check(ACTION, {"text": "Turn on picture mode"},
                               prompt="Turn on picture mode")
        except Exception:
            box["error"] = traceback.format_exc()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    row = None
    end = time.time() + 15
    while time.time() < end and row is None:
        rows = G.pending()
        row = rows[0] if rows else None
        if row is None:
            time.sleep(0.02)
    return row, box, t


def finish(G, cr, row, t, box):
    """Deny the card so no waiter is left behind, and drop the latch."""
    try:
        if row is not None:
            G.decide(row["id"], False, by="the test")
    finally:
        t.join(timeout=10)
        cr.clear_rush()
    return box.get("v")


def swipeable(row):
    """The phone's own rule, as `ApiModels.kt` declares it.

    `swipeable = risk.swipeOk && raised == null`. Repeated here rather than
    imported because the phone is Kotlin; the assertion is about the two wire
    fields this repository does produce.
    """
    return bool(row["risk"]["swipe_ok"]) and row["raised"] is None


def _raised_column_is_text(G) -> bool:
    """Is the column a TEXT column - i.e. is there a cap to trim to at all?

    Read from SQLite rather than assumed, because "the chip does not fit" is
    only answerable against the column's own type.
    """
    with closing(sqlite3.connect(str(G.DB_PATH))) as c:
        for _cid, name, coltype, _nn, _default, _pk in c.execute(
                "PRAGMA table_info(approvals)"):
            if name == "raised":
                return (coltype or "").upper() == "TEXT"
    return False


# ---------------------------------------------------------------------------
# 1. The measured fault: a chip longer than the old cap
# ---------------------------------------------------------------------------

def t_a_long_rush_chip_is_stored_whole_and_takes_the_swipe_away():
    """THE REGRESSION. Fails on `json.dumps(raised)[:1000]`.

    Three separate things are wrong on the unfixed code, and each is checked
    by name so a failure says which one came back: the stored chip is cut, the
    wire field is null, and the card is swipeable.
    """
    G, cr, why = load_gate()
    if G is None:
        return skip(why)
    row, box, t = raise_card(G, cr, rushed=True)
    answered = False
    try:
        if row is None:
            return check("a rushed card was raised", False,
                         box.get("error", "no pending row"))
        with closing(sqlite3.connect(str(G.DB_PATH))) as c:
            raw = c.execute("SELECT raised FROM approvals WHERE id=?",
                            (row["id"],)).fetchone()[0]
        # The precondition, measured rather than assumed: if a later change to
        # chip_from's bounds made the chip short, this suite would stop
        # exercising the fault while still passing. So the chip must really be
        # longer than the 1000 characters the old code kept.
        check("the chip is longer than the 1000 characters the old code kept",
              raw is not None and len(raw) > 1000,
              f"{len(raw) if raw else 0} stored characters")
        check("the whole chip is stored, not a cut of it",
              raw is not None and len(raw) >= 1500,
              f"{len(raw) if raw else 0} stored characters")
        try:
            parsed = json.loads(raw or "")
        except Exception as exc:
            parsed = None
            check("the stored chip is complete JSON", False,
                  f"{type(exc).__name__}: {exc}")
        else:
            check("the stored chip is complete JSON", True)
        check("the `raised` column is TEXT, so there is no cap to trim to",
              _raised_column_is_text(G), "not TEXT")

        # What /api/pending serves, which is what both apps read.
        check("raised is a dict on the wire, not null",
              isinstance(row["raised"], dict), repr(row["raised"])[:120])
        raised = row["raised"] if isinstance(row["raised"], dict) else {}
        check("...with the chip's own keys",
              set(raised) >= {"code", "text", "quote", "context", "source",
                              "count_today", "from_tier", "to_tier"},
              sorted(raised))
        check("...and the raise's own words survived whole",
              parsed is not None and raised.get("context") == parsed.get("context")
              and len(raised.get("context") or "") == 200,
              len(raised.get("context") or "") if raised else None)
        check("...naming the source it came from",
              raised.get("source") == RUSH_SOURCE and raised.get("code") == "rushed",
              (raised.get("source") or "")[:20])
        check("...and it is still the raise that took the tier up to ask",
              (raised.get("from_tier"), raised.get("to_tier")) in
              (("ask", "ask"), ("auto", "ask")),
              (raised.get("from_tier"), raised.get("to_tier")))

        # The swipe rule itself, from both clients' own conditions.
        check("CONTROL: this card's risk does offer a swipe at all "
              "(swipe_ok true) - the raise is what withholds it",
              row["risk"]["swipe_ok"] is True, row["risk"])
        check("the phone's rule (swipe_ok and raised is None) is FALSE here",
              swipeable(row) is False, row["risk"])
        check("the desktop's rule (`if (approval.raised) return false`) is "
              "satisfied too - raised is truthy",
              bool(row["raised"]) is True)

        # The card is still a card: the waiter is answered when it is denied.
        v = finish(G, cr, row, t, box)
        answered = True
        check("denying the raised card is still answered as a denial",
              v is not None and v.allowed is False and v.outcome == "denied",
              v if v is not None else box.get("error"))
    finally:
        if not answered:
            finish(G, cr, row, t, box)


# ---------------------------------------------------------------------------
# 2. The control: an ordinary card keeps its swipe
# ---------------------------------------------------------------------------

def t_an_ordinary_card_is_unchanged_swipe_ok_and_unraised():
    """No latch, same action: `raised` null and the swipe still on.

    Without this, the check above could pass for the wrong reason - if a change
    made this action's card unswipeable in general, the raised case would look
    fixed while every ordinary card had lost a control its owner uses.
    """
    G, cr, why = load_gate()
    if G is None:
        return skip(why)
    row, box, t = raise_card(G, cr, rushed=False)
    if row is None:
        return check("an ordinary card was raised", False,
                     box.get("error", "no pending row"))
    check("CONTROL: no latch means no chip", row["raised"] is None, row["raised"])
    check("CONTROL: and the swipe is still offered - swipe_ok and no raise",
          row["risk"]["swipe_ok"] is True and swipeable(row) is True, row["risk"])
    v = finish(G, cr, row, t, box)
    check("CONTROL: the ordinary card is still answered as a denial",
          v is not None and v.allowed is False and v.outcome == "denied", v)


# ---------------------------------------------------------------------------
# 3. The other cut is untouched, on purpose
# ---------------------------------------------------------------------------

def t_the_detail_cut_is_still_there_and_the_raised_cap_is_gone():
    """A source pin, so the fix cannot spread into the other truncation.

    `detail` is still stored as `json.dumps(detail)[:4000]` - that cut is a
    different, phone-side fault (a long request arrives unparseable and the
    phone has no cut-off guard; the desktop refuses it). It is deliberately
    NOT changed here, and this check says so out loud so a later reader does
    not "tidy" the two together.
    """
    if not GATE.is_file():
        return skip(f"{GATE} is missing")
    src = GATE.read_text(encoding="utf-8")
    check("detail is still cut at 4000 characters - a different fault, "
          "deliberately untouched", "json.dumps(detail)[:4000]" in src)
    check("the raised chip is not cut at all any more",
          "json.dumps(raised)[:1000]" not in src)
    check("...and it is stored whole", "json.dumps(raised) if raised else None" in src)


if __name__ == "__main__":
    for fn in (t_the_detail_cut_is_still_there_and_the_raised_cap_is_gone,
               t_a_long_rush_chip_is_stored_whole_and_takes_the_swipe_away,
               t_an_ordinary_card_is_unchanged_swipe_ok_and_unraised):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
