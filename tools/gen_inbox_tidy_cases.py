#!/usr/bin/env python3
"""Writes the inbox-tidy contract file for both apps, and checks it.

    python3 tools/gen_inbox_tidy_cases.py            # write both copies
    python3 tools/gen_inbox_tidy_cases.py --check    # compare only

What `GET /api/email/tidy` and `POST /api/email/tidy/undo` REALLY answer
(backend/jarvis_inbox_tidy.py, inbox-tidy.patch; docs/JARVIS-API.md section
92), in named situations, made by the real code against a stand-in mail
server (backend/_fake_imap.py) and a fixed clock - nothing is written by
hand:

    jarvis-desktop/tests/fixtures/inbox-tidy-cases.json
    jarvis-client/app/src/test/resources/contract/inbox-tidy-cases.json

(byte-identical). Both apps build against it: the desktop's Rust and
JavaScript tests, and the phone's InboxTidyTest.

It also holds `strip`: what the small "Undo" strip under the chat says for a
status, in the app's own situations (an ordinary one, App lock locked, the
link stale). The rule is written here ONCE, in `strip_rule`, and both apps
must give the same answer for every row - the apps' tests read them.

Nothing private is in the file: a status carries counts and words of the
PC's own, never a sender or a subject, and the fake account's password is
built by concatenation and must not appear (checked).
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
os.environ["OPENJARVIS_CONFIG_DIR"] = tempfile.mkdtemp(prefix="jarvis-tidy-cases-")
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_inbox_tidy as T  # noqa: E402
from _fake_imap import FakeServer, Msg  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "inbox-tidy-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "inbox-tidy-cases.json")
COPIES = (DESKTOP, PHONE)

_FAKE = "pw" + "-cases-" + "0123456789"
_NOW = 1790596800.0            # 2026-09-28 12:00 UTC
_NAMES = (T.HOST_ENV, T.PORT_ENV, T.MAILBOX_ENV, T.USER_ENV, T.PASSWORD_ENV)


def _env(**kw):
    for n in _NAMES:
        os.environ.pop(n, None)
    for k, v in kw.items():
        os.environ[k] = v


def _mailbox() -> FakeServer:
    s = FakeServer()
    for n, (frm, subj, day) in enumerate((
            ("Shop Weekly <news@shop.example>", "Your weekly digest", 21),
            ("Shop Weekly <news@shop.example>", "50% off everything", 22),
            ("Shop Weekly <news@shop.example>", "Big sale ends soon", 23),
            ("Sam Smith <sam@example.org>", "Lunch on Friday?", 24)), 1):
        s.add("INBOX", Msg(f"<c{n}@x.example>", frm, subj,
                           f"Mon, {day} Sep 2026 09:00:00 +0000", unsub=n <= 3))
    return s


def strip_rule(body: dict, locked: bool, stale: bool):
    """What the Undo strip says - the rule both apps follow. None when there
    is nothing to undo. While App lock is locked (or the lists are hidden) it
    says only that the inbox was tidied - no count, no action - and Undo
    waits for the unlock; on a stale link Undo is held (rule 4)."""
    u = body.get("undo")
    if not u:
        return None
    words = T.WORDS
    if locked:
        text = words["hidden"]
    else:
        text = u["said"]
        if u.get("more"):
            n = u["more"]
            text += f" ({n} earlier tid{'y' if n == 1 else 'ies'} can be undone after)"
    note = words["locked"] if locked else words["stale"] if stale else ""
    return {"text": text, "left": words["undo_left"].format(minutes=u["minutes_left"]),
            "can_undo": not locked and not stale, "note": note}


def cases() -> dict:
    timer = lambda seconds, fn: None            # noqa: E731
    _env(**{T.HOST_ENV: "imap.example.com", T.USER_ENV: "owner@example.com",
            T.PASSWORD_ENV: _FAKE})
    T._reset_for_tests()
    T._audit = lambda event, detail: None
    s = _mailbox()
    conn = lambda st: s.connection()            # noqa: E731
    out = {}
    out["status_idle"] = {"status": 200, "body": T.status(_NOW)}

    p = T.plan("archive", sender="shop", connect=conn, now=_NOW)
    T.run(p, approved=True, connect=conn, now=_NOW, timer=timer)
    out["status_undo"] = {"status": 200, "body": T.status(_NOW + 30)}
    out["status_undo_last_minute"] = {"status": 200, "body": T.status(_NOW + 560)}

    q = T.plan("mark_read", sender="sam", connect=conn, now=_NOW + 60)
    T.run(q, approved=True, connect=conn, now=_NOW + 60, timer=timer)
    out["status_undo_two"] = {"status": 200, "body": T.status(_NOW + 90)}

    code, body = T.undo(connect=conn, now=_NOW + 100)
    out["undo_done"] = {"status": code, "body": body}
    out["status_after_undo"] = {"status": 200, "body": T.status(_NOW + 101)}

    # The owner deleted one meanwhile.
    s.msgs.remove(next(m for m in s.msgs if m.msgid == "<c2@x.example>"))
    code, body = T.undo(connect=conn, now=_NOW + 110)
    out["undo_some_lost"] = {"status": code, "body": body}
    code, body = T.undo(connect=conn, now=_NOW + 120)
    out["undo_nothing"] = {"status": code, "body": body}

    # The server cannot be reached at Undo.
    s2 = _mailbox()
    T.run(T.plan("trash", sender="sam", connect=lambda st: s2.connection(), now=_NOW),
          approved=True, connect=lambda st: s2.connection(), now=_NOW, timer=timer)

    def down(st):
        raise OSError("unreachable")
    code, body = T.undo(connect=down, now=_NOW + 5)
    out["undo_unreachable"] = {"status": code, "body": body}
    T._reset_for_tests()

    strips = []
    for name in ("status_idle", "status_undo", "status_undo_last_minute", "status_undo_two",
                 "status_after_undo"):
        for locked in (False, True):
            for stale in (False, True):
                strips.append({"case": name, "locked": locked, "stale": stale,
                               "expect": strip_rule(out[name]["body"], locked, stale)})
    _env()
    return {
        "words": T.WORDS,
        "routes": {"status": T.ROUTE, "undo": T.UNDO},
        "undo_minutes": T.UNDO_MINUTES,
        "cases": out,
        "strip": strips,
        # A backend without jarvis_inbox_tidy.py (the routes' 404, or a 503).
        "missing": {"status": 404, "body": {"error": "not found"}},
    }


def render() -> str:
    text = json.dumps(cases(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    assert _FAKE not in text, "the password reached the contract file"
    assert "owner@example.com" not in text and "shop.example" not in text, \
        "an address reached the contract file"
    return text


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        stale = []
        for path in COPIES:
            have = path.read_text(encoding="utf-8") if path.is_file() else ""
            if have.replace("\r\n", "\n") != text:
                stale.append(path)
        for path in stale:
            print(f"{path.relative_to(ROOT)} is out of date: run "
                  f"python3 tools/gen_inbox_tidy_cases.py")
        if stale:
            return 1
        print("inbox-tidy-cases.json matches the producer (desktop and phone copies).")
        return 0
    for path in COPIES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
