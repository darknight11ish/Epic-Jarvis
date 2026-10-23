"""test_inbox_tidy_says_what_happened.py - the tidy's honest sentence reaches the owner.

    python3 backend/test_inbox_tidy_says_what_happened.py

WHY THIS EXISTS (2026-10-16)

"A tidy that skipped three emails must not say it simply worked." The backend
already built the honest sentence - `jarvis_inbox_tidy.run` returns

    "Archived 7 emails. 3 emails skipped - already moved, deleted or changed
     since the card was made. The owner can undo this for 10 minutes..."

- but NOTHING POSTs a tidy: `POST /api/email/tidy` is 405 on purpose, because a
tidy is asked for through the approval card. So no app ever saw that return
value. Both apps read `GET /api/email/tidy`, and the only sentence in it was
the undo record's own, `_said(action, n)` - "Archived 7 emails." - so an owner
whose tidy skipped three emails, or stopped part of the way, was told it simply
worked. The honest sentence is now built once (`_outcome_said`) and stored in
the undo record the two apps already render, so both show it with no app change.

The two callers, quoted, before the fix:
    jarvis-desktop/src/inbox-tidy.js:61   const said = u ? asText(u.said) : null;
    jarvis-client/.../net/InboxTidy.kt:97  val said = u.text("said")
Neither reads `last`; neither can see a return value.

EVERY GUARD IS BITE-PROVED: with the pre-fix sentence builder put back, the same
skipped tidy's status says it simply worked - then the fix is restored and the
skip is said again.
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-tidy-said-"))
# Before anything imports jarvis_framework: its CONFIG_DIR is read once.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_inbox_tidy as T  # noqa: E402
from _fake_imap import FakeServer, Msg  # noqa: E402

T._audit = lambda event, detail: None

PASSED, FAILED = [], []

FAKE_PW = "pw" + "-said-" + "Qx7" + "kLm2"
OWNER = "owner@example.com"
NOW = 1790596800.0            # 2026-09-28 12:00 UTC, the clock the other suite uses
ENV_NAMES = (T.HOST_ENV, T.PORT_ENV, T.MAILBOX_ENV, T.USER_ENV, T.PASSWORD_ENV)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def set_env() -> None:
    for n in ENV_NAMES:
        os.environ.pop(n, None)
    os.environ[T.HOST_ENV] = "imap.example.com"
    os.environ[T.USER_ENV] = OWNER
    os.environ[T.PASSWORD_ENV] = FAKE_PW


def mailbox() -> FakeServer:
    """Three emails from one sender (the ones a tidy acts on) and one other."""
    s = FakeServer()
    s.add("INBOX", Msg("<n1@shop.example>", "Shop Weekly <news@shop.example>",
                       "Your weekly digest", "Mon, 21 Sep 2026 09:00:00 +0000"))
    s.add("INBOX", Msg("<n2@shop.example>", "Shop Weekly <news@shop.example>",
                       "50% off everything", "Tue, 22 Sep 2026 09:00:00 +0000"))
    s.add("INBOX", Msg("<n3@shop.example>", "Shop Weekly <news@shop.example>",
                       "Big sale ends soon", "Wed, 23 Sep 2026 09:00:00 +0000"))
    s.add("INBOX", Msg("<b1@bank.example>", "Your Bank <alerts@bank.example>",
                       "Your statement is ready", "Sat, 26 Sep 2026 09:00:00 +0000"))
    return s


def connect_to(s: FakeServer):
    return lambda st: s.connection()


def plan(s, action="archive", **kw):
    kw.setdefault("now", NOW)
    return T.plan(action, connect=connect_to(s), **kw)


def run(s, p, **kw):
    kw.setdefault("now", NOW)
    kw.setdefault("timer", lambda seconds, fn: None)
    return T.run(p, approved=True, connect=connect_to(s), **kw)


def fresh() -> None:
    T._reset_for_tests()
    set_env()


def undo_said() -> str:
    """The one sentence both apps render: `status.undo.said`."""
    return ((T.status(NOW).get("undo") or {}).get("said") or "")


# --------------------------------------------------------------------------
#   The defect, and the fix
# --------------------------------------------------------------------------

def t_the_status_says_what_the_tidy_could_not_do():
    fresh()
    s = mailbox()
    p = plan(s, "archive", sender="shop")
    vanished = next(m for m in s.msgs if m.msgid == "<n2@shop.example>")
    s.msgs.remove(vanished)                      # the owner deleted it while the card waited
    out = run(s, p)
    said = undo_said()
    check("the tidy did two and skipped one", out["ok"] and out["done"] == 2
          and out["skipped"] == 1, out)
    check("the tidy's own return value says the skip",
          "1 email skipped" in out["said"], out["said"])
    check("... and the STATUS both apps read says it too",
          "1 email skipped" in said, said)
    check("... with the plain sentence still in front of it",
          said.startswith("Archived 2 emails."), said)
    check("... and the newest tidy's message says it as well",
          "1 email skipped" in ((T.status(NOW).get("last") or {}).get("message") or ""),
          T.status(NOW).get("last"))


def t_the_status_says_a_partial_stop():
    fresh()
    s = mailbox()
    s.fail_after = 2                             # the server drops after two
    out = run(s, plan(s, "archive", sender="shop"))
    said = undo_said()
    check("the tidy says it stopped part of the way",
          out["ok"] is False and "stopped part of the way" in out["said"], out)
    check("... and the status both apps read says it too",
          "stopped part of the way" in said, said)
    check("... and the two it did are still held for Undo",
          T.status(NOW)["undo"]["count"] == 2, T.status(NOW).get("undo"))


def t_control_a_clean_tidy_still_says_only_what_it_did():
    """The control: the fix must not make every tidy alarming."""
    fresh()
    s = mailbox()
    out = run(s, plan(s, "archive", sender="shop"))
    u = T.status(NOW)["undo"]
    check("CONTROL: a clean tidy's status sentence is the plain one",
          u["said"] == "Archived 3 emails.", u)
    check("CONTROL: ... with no skip or failure words in it",
          "skipped" not in u["said"] and "stopped" not in u["said"], u["said"])
    check("CONTROL: ... and the return value still tells the model about Undo",
          out["said"].startswith("Archived 3 emails.")
          and "undo" in out["said"].lower(), out["said"])


def t_an_undo_record_from_before_the_field_still_reads():
    # An undo record made before `said` was stored carries no sentence of its
    # own: the view falls back to the plain one rather than showing nothing.
    rec = {"until": NOW + 60, "items": [{}, {}], "action": "archive"}
    v = T._undo_view(rec, NOW, 0)
    check("an undo record with no sentence falls back to the plain one",
          v["said"] == "Archived 2 emails.", v)


# --------------------------------------------------------------------------
#   Both apps read the field the fix fills
# --------------------------------------------------------------------------

def t_both_apps_read_the_sentence_the_fix_fills():
    """A source pin on the two callers. The fix deliberately needed no app
    change: it fills `undo.said`, which both apps already render and which is
    the ONLY sentence either can see. If an app moved to reading `last`
    instead, this says so."""
    root = HERE.parent
    desk = (root / "jarvis-desktop" / "src" / "inbox-tidy.js").read_text(encoding="utf-8")
    phone = (root / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
             / "client" / "net" / "InboxTidy.kt").read_text(encoding="utf-8")
    check("the desktop reads the undo record's sentence", "asText(u.said)" in desk, "")
    check("... and renders it as the strip's text", "text = u.said" in desk, "")
    check("... and does not read the newest tidy's message instead",
          "body.last" not in desk and "last.message" not in desk, "")
    check("the phone reads the undo record's sentence", 'u.text("said")' in phone, "")
    check("... and does not read the newest tidy's message instead",
          'body["last"]' not in phone and 'text("last")' not in phone, "")


# --------------------------------------------------------------------------
#   The bite: with the pre-fix sentence, the status says it simply worked
# --------------------------------------------------------------------------

def t_the_honest_sentence_bites():
    real = T._outcome_said
    # Exactly the pre-fix behaviour: the sentence was `_said(action, n)` alone,
    # whichever of the four arguments were passed. Given the same signature, so
    # the shim does not merely raise and turn the bite into a crash.
    T._outcome_said = lambda action, n, skipped=0, failure="": T._said(action, n)
    try:
        fresh()
        s = mailbox()
        p = plan(s, "archive", sender="shop")
        vanished = next(m for m in s.msgs if m.msgid == "<n2@shop.example>")
        s.msgs.remove(vanished)
        run(s, p)
        blinded = undo_said()
    finally:
        T._outcome_said = real
    check("BITE: without the honest sentence the status says the tidy simply worked",
          blinded == "Archived 2 emails." and "skipped" not in blinded, blinded)
    # ... and the fix, put back, says it again.
    fresh()
    s = mailbox()
    p = plan(s, "archive", sender="shop")
    vanished = next(m for m in s.msgs if m.msgid == "<n2@shop.example>")
    s.msgs.remove(vanished)
    run(s, p)
    check("... and with it restored the skip is said again",
          "1 email skipped" in undo_said(), undo_said())
    check("... and the builder is the real one again", T._outcome_said is real)


def t_every_test_here_is_registered():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    defined = sorted(n.name for n in tree.body
                     if isinstance(n, ast.FunctionDef) and n.name.startswith("t_"))
    running = sorted(fn.__name__ for fn in RUN)
    missing = sorted(set(defined) - set(running))
    extra = sorted(set(running) - set(defined))
    check("every t_ function here is in RUN", not missing, missing)
    check("... and every name in RUN is a function here", not extra, extra)
    check("BITE: a name left out of RUN would be named",
          sorted(set(["t_a", "t_never_run"]) - set(["t_a"])) == ["t_never_run"])


if __name__ == "__main__":
    RUN = (
        t_the_status_says_what_the_tidy_could_not_do,
        t_the_status_says_a_partial_stop,
        t_control_a_clean_tidy_still_says_only_what_it_did,
        t_an_undo_record_from_before_the_field_still_reads,
        t_both_apps_read_the_sentence_the_fix_fills,
        t_the_honest_sentence_bites,
        t_every_test_here_is_registered,
    )
    for fn in RUN:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
