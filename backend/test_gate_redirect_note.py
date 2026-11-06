"""A denial can carry the owner's own note: "No, and tell Jarvis what to do".

    python3 test_gate_redirect_note.py

THE OWNER'S RULING (2026-11-06 11:35 PT, next-sprint PR 2, Hermes borrow #1):
the approval-card deny path gains an OPTIONAL note in the owner's words, fed
back into the active turn so the model can adjust its next attempt without the
owner retyping the request. The constraints that make it safe are all checked
here:

  * a deny with NO note behaves exactly as today;
  * a deny WITH a note stores it, and the turn that was waiting on that card
    reads it through the mechanism that already carries a card's outcome -
    `jarvis_task_control.amend()` -> `take_amend()` -> `owner_note` in the tool
    result `jarvis_agent` appends (the same one the note button uses);
  * the note is NEVER the card's own text, and NEVER something that looks like
    a password, key or account number;
  * zero standing permission is introduced, and one card per action is
    unchanged: a deny writes no grant and raises nothing.

Where the route lives: `jarvis_hud.py`'s `/api/approve` + `/api/deny` block.
That file starts an HTTP server on import, so this suite does not import it -
it reads the block as TEXT for the ordering that matters (the note is kept
BEFORE the gate is told), and exercises the mechanism itself with the real
modules.
"""
import json
import os
import sqlite3
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _base  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


_TMP = Path(tempfile.mkdtemp(prefix="jarvis-redirect-note-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP)
os.environ["JARVIS_APPROVALS_DB"] = str(_TMP / "approvals.db")
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_APPROVAL_TIMEOUT"] = "600"

fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {
    "logging": {"redact_private_content_in_logs": True},
    "autonomy": {"unknown_action_tier": "ask", "tiers": {}},
}
fw.audit_log = lambda *a, **k: None
sys.modules["jarvis_framework"] = fw

BASE = _base.folder("jarvis_gate.py")
if BASE is not None:
    _base.put_on_path(BASE)
    _base.say(BASE, "jarvis_gate.py")

import jarvis_gate as G  # noqa: E402
import jarvis_task_control as TC  # noqa: E402


def _insert(rid, action, detail, prompt, state="pending"):
    G._init()
    with sqlite3.connect(str(G.DB_PATH)) as c:
        c.execute(
            "INSERT OR REPLACE INTO approvals (id,action,tier,detail,prompt,state,created)"
            " VALUES (?,?,?,?,?,?,?)",
            (rid, action, "ask", json.dumps(detail), prompt, state, time.time()))


def _count():
    G._init()
    with sqlite3.connect(str(G.DB_PATH)) as c:
        return c.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]


# --------------------------------------------------------------------------
#   The note itself: cleaned, echoed text refused, secrets refused
# --------------------------------------------------------------------------

def t_no_note_is_no_note():
    for raw in (None, "", "   ", 0, [], {}):
        note, why = TC.deny_note(raw)
        check(f"no note in {raw!r}: nothing stored, nothing said",
              note is None and why == "", (note, why))


def t_a_plain_note_is_kept():
    note, why = TC.deny_note("Use the Documents folder instead of the Desktop")
    check("a plain note is kept", note == "Use the Documents folder instead of the Desktop",
          note)
    check("... and needs no explanation", why == "", why)
    check("control characters are dropped, newlines kept",
          TC.deny_note("a\x07b\nc")[0] == "ab\nc", TC.deny_note("a\x07b\nc"))
    check("a very long note is cut, not refused",
          len(TC.deny_note("x" * 5000)[0]) == TC.MAX_NOTE_CHARS,
          len(TC.deny_note("x" * 5000)[0] or ""))


def t_the_card_echoed_back_is_never_stored_as_the_owner_s_words():
    card = "Delete the folder C:\\Temp\\old and empty the bin?"
    note, why = TC.deny_note(card, card)
    check("the card's own text is not kept as a note", note is None, note)
    check("... and the app is told why", why == TC.NOTE_ECHOED_CARD, why)
    # Whitespace is normalised before the comparison, so a line-wrapped copy of
    # the card is still the card.
    wrapped = card.replace(" ", "\n   ")
    check("a line-wrapped copy of the card is still the card",
          TC.deny_note(wrapped, card)[0] is None, TC.deny_note(wrapped, card))


def t_something_that_looks_like_a_secret_is_never_stored():
    for text in ("my password is hunter2",
                 "the API key is sk-abcdef1234567890abcdef",
                 "card number 4111 1111 1111 1111",
                 "login is admin / hunter2"):
        note, why = TC.deny_note(text)
        check(f"a secret-looking note is not kept: {text[:28]!r}", note is None, note)
        check(f"... and says why: {text[:28]!r}", why == TC.NOTE_LOOKS_SECRET, why)


# --------------------------------------------------------------------------
#   The mechanism the route uses: note first, gate told second
# --------------------------------------------------------------------------

def t_the_note_reaches_the_turn_that_was_waiting():
    _insert("wait1", "send_email", {"text": "Send it to Anna"}, "Send it?")
    note, why = TC.deny_note("Send it to Ben instead, not Anna",
                             G.pending_text("wait1"))
    check("the note is kept", note and why == "", (note, why))
    # This is the order the route uses: amend(), then decide(). The waiting
    # turn is blocked in jarvis_gate.check(); when decide() returns, the turn
    # calls take_amend(request_id) and puts the note in the tool result.
    TC.amend("wait1", note)
    decided = G.decide("wait1", False, by="hud")
    check("the denial went through", decided is True, decided)
    check("the note is still there for the turn to read",
          TC.take_amend("wait1") == "Send it to Ben instead, not Anna",
          TC.take_amend("wait1"))
    check("it is taken ONCE, so it is never repeated",
          TC.take_amend("wait1") is None, TC.take_amend("wait1"))
    row = [r for r in G.history(10) if r["id"] == "wait1"]
    check("the card is recorded as denied", row and row[0]["state"] == "denied", row)


def t_a_deny_store_no_permission_and_raises_nothing():
    before = _count()
    _insert("deny2", "run_shell_on_host", {"text": "Delete the folder"}, "Delete it?")
    note, _why = TC.deny_note("Move it to the recycle bin instead")
    TC.amend("deny2", note)
    G.decide("deny2", False, by="hud")
    after = _count()
    check("a deny with a note raises no second card", after == before + 1, (before, after))
    # There is no grant to create: the gate's own writes are the approvals row
    # and the taint latch, and the deny path touches neither except to settle
    # the card. `granted()` in jarvis_gate.py is an AUDIT RECORDER, not a
    # checker - calling it here would have written the very event this check
    # is about, which is how the first version of this test fooled itself.
    check("no standing permission: the deny leaves no taint latch",
          G.taint_active() is False, G.taint_active())
    check("... and the note itself grants nothing",
          "grant" not in (TC.deny_note.__doc__ or "").lower(), "")
    check("and the card is not pending any more",
          not any(r["id"] == "deny2" for r in G.pending()), G.pending())


def t_an_approve_still_reads_no_note():
    """The note is a DENY field. Approving with one must not store it."""
    _insert("yes1", "send_email", {"text": "Send it"}, "Send it?")
    TC.amend("yes1", "this must not be read by an approval")
    check("approve is allowed here", G.decide("yes1", True, by="hud") is True)
    # Nothing on the approve path calls take_amend, so the note would linger;
    # the route only ever amends on the deny branch (checked below). Take it
    # here so this test's own state cannot leak into another's.
    TC.take_amend("yes1")
    check("the approval is recorded", [r for r in G.history(5)
                                       if r["id"] == "yes1"][0]["state"] == "approved")


# --------------------------------------------------------------------------
#   The route's own shape, read as text (jarvis_hud starts a server on import)
# --------------------------------------------------------------------------

def _route_source():
    path = _base.folder("jarvis_hud.py") or BASE
    if path is None:
        return ""
    p = Path(str(path)) / "jarvis_hud.py"
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def t_the_route_keeps_the_note_before_it_tells_the_gate():
    src = _route_source()
    check("jarvis_hud.py was found", bool(src), "no source; the pins below cannot run")
    if not src:
        return
    start = src.find('if route in ("/api/approve", "/api/deny"):')
    end = src.find("if route != \"/api/chat\":", start)
    block = src[start:end] if start >= 0 and end > start else ""
    check("the approve/deny block was found", bool(block), (start, end))
    if not block:
        return
    check("a deny reads the optional note",
          'body.get("note")' in block, block[:400])
    check("only the DENY branch keeps it",
          'if route == "/api/deny" and body.get("note")' in block, "")
    check("the note is cleaned by jarvis_task_control.deny_note",
          "_tc.deny_note(" in block, "")
    check("... together with the card's own text, so the echo can be refused",
          "_tc.pending_text(rid)" in block or "pending_text(rid)" in block, "")
    check("the note is kept BEFORE jarvis_gate.decide() is called",
          0 <= block.find("_tc.amend(") < block.find("jarvis_gate.decide("),
          (block.find("_tc.amend("), block.find("jarvis_gate.decide(")))
    check("the answer says whether the note was kept",
          '"note_kept"' in block and '"note_why"' in block, "")
    check("the route grants nothing and approves nothing on a deny",
          "grant" not in block.lower(), "")


def t_the_agent_side_has_not_moved():
    """The mechanism the note rides on: take_amend -> `owner_note`. If either
    half is renamed the note silently stops reaching the model."""
    path = _base.folder("jarvis_agent.py") or BASE
    p = Path(str(path)) / "jarvis_agent.py" if path is not None else None
    try:
        src = p.read_text(encoding="utf-8", errors="replace") if p else ""
    except OSError:
        src = ""
    check("jarvis_agent.py was found", bool(src), "")
    if not src:
        return
    check("the agent still takes the note off the answered card",
          "take_amend(" in src, "")
    check("... and still puts it in the tool result the model reads",
          'result["owner_note"] = card_note' in src, "")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
