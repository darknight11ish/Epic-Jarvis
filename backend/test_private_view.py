"""jarvis_private_view.py - the Q1 read-only lock-state hook, and the three private views.

    python3 backend/test_private_view.py

The 2026-10-20 ruling (Q1) approved ONE read-only live-state hook and made the
rule explicit: a request's `app_locked` / `hide_memory_lists` may only ADD
withholding, never remove it; an absent hook means unlocked in-process; and the
desktop apps' own hiding stays as belt-and-braces. This suite proves:

1. The helper's semantics: absent is unlocked; each "yes" spelling locks; every
   other spelling does not; the trusted state can be set and cleared only by
   note_state(); a caller's False cannot clear it.
2. The wording is the one private view the backend already uses
   (jarvis_people_crm's WITHHELD_LOCKED / WITHHELD_HIDDEN, byte-identical).
3. Every route answer withholds: the guardian journal page and diff, the person
   dossier, and the receipts list. A locked answer carries the honest marker
   and NO row/path/diff/summary, and the store read is never made (a fake
   reader that raises is never called). Absent/false flags leave the normal
   answer, unchanged.
4. Direct HTTP, through each module's own install() wrapper: GET with the lock
   flags answers withheld; `force_unlock=1` and `app_locked=0` do not unlock.
5. The module is shipped (backend/_where.py + jarvis-backend twin) so every one
   of those routes can import it on the owner's PC.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_brain_reads as B  # noqa: E402
import jarvis_people_crm as people  # noqa: E402
import jarvis_private_view as PV  # noqa: E402
import jarvis_receipts as R  # noqa: E402

FAILED, PASSED = [], []

SECRET_NAME = "Priya Secretperson"
SECRET_PATH = r"C:\Users\pcadmin\Documents\private\salary-2026.docx"
SECRET_DIFF = "- old salary\n+ new salary"
SECRET_SUMMARY = "changed the salary note"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    print(f"skip  {why}")


class Reader:
    """A store reader that records the call; `boom` proves it was NOT read."""

    def __init__(self, rows=None):
        self.calls = 0
        self.rows = rows if rows is not None else []
        self.boom = False

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.boom:
            raise AssertionError("a locked view read its store")
        return self.rows


def _reset():
    PV._reset_for_tests()


# ---------------------------------------------------------------- 1. the hook

def t_absent_hook_is_unlocked_and_a_flag_can_only_lock():
    _reset()
    check("no hook called yet: the state is unlocked", PV.state() == {
        "app_locked": False, "hide_memory_lists": False}, PV.state())
    check("nothing withheld: no sentence and locked False",
          PV.effective() == {"app_locked": False, "hide_memory_lists": False,
                             "locked": False, "why": ""}, PV.effective())
    locked = PV.effective(app_locked=1)
    check("app_locked=1 withholds with the App-lock sentence",
          locked["locked"] is True and locked["why"] == PV.WITHHELD_LOCKED, locked)
    hidden = PV.effective(hide_memory_lists="Yes")
    check("hide_memory_lists=Yes withholds with the hidden-lists sentence",
          hidden["locked"] is True and hidden["why"] == PV.WITHHELD_HIDDEN, hidden)
    both = PV.effective(app_locked="true", hide_memory_lists="on")
    check("both on: the App-lock sentence wins (the order the apps use)",
          both["locked"] and both["why"] == PV.WITHHELD_LOCKED, both)
    for spelling in ("1", "true", "TRUE", " Yes ", "on"):
        check(f"a yes spelling locks: {spelling!r}", PV.flag(spelling) is True)
    for spelling in ("0", "false", "no", "off", "", None, 0, []):
        check(f"anything else does not lock: {spelling!r}", PV.flag(spelling) is False)
    check("a flag that cannot be stringified is False, never a raise",
          PV.flag(object()) is False)


def t_a_caller_cannot_unlock_the_trusted_state():
    _reset()
    PV.note_state(app_locked=True)
    try:
        check("trusted locked: state says so", PV.state()["app_locked"] is True)
        for call in (dict(app_locked=False), dict(app_locked="0"),
                     dict(app_locked=0, hide_memory_lists=False),
                     dict(lock_state={"app_locked": False})):
            got = PV.effective(**call)
            check(f"a caller's false cannot clear it: {call}", got["locked"] is True, got)
        PV.note_state(hide_memory_lists=True)
        check("the hidden half can be raised while the lock is on",
              PV.state()["hide_memory_lists"] is True)
        PV.note_state(app_locked=False, hide_memory_lists=False)
        check("note_state() is the one place that can clear it",
              PV.effective()["locked"] is False, PV.effective())
    finally:
        _reset()
    check("lock_state as a truthy non-mapping locks (fail-safe)",
          PV.effective(lock_state=True)["locked"] is True)
    check("after the reset, nothing can be unlocked from a request",
          PV.effective(app_locked=False)["locked"] is False)


def t_the_wording_is_the_private_views_one():
    check("App-lock sentence matches jarvis_people_crm's",
          PV.WITHHELD_LOCKED == people.WITHHELD_LOCKED,
          (PV.WITHHELD_LOCKED, people.WITHHELD_LOCKED))
    check("hidden-lists sentence matches jarvis_people_crm's",
          PV.WITHHELD_HIDDEN == people.WITHHELD_HIDDEN,
          (PV.WITHHELD_HIDDEN, people.WITHHELD_HIDDEN))
    check("withhold() is a pure lookup, not a decision",
          PV.withhold("app_locked") == PV.WITHHELD_LOCKED
          and PV.withhold("hidden") == PV.WITHHELD_HIDDEN
          and PV.withhold(None) == PV.WITHHELD_HIDDEN)
    check("withheld_words() follows effective()",
          PV.withheld_words(hide_memory_lists=1) == PV.WITHHELD_HIDDEN
          and PV.withheld_words() == "")


def t_the_builder_merges_the_hook_and_the_flags():
    _reset()
    locked = people.build_person_dossier(SECRET_NAME, app_locked=True)
    check("the dossier builder withholds on app_locked=True",
          locked.get("withheld") is True and locked.get("why") == PV.WITHHELD_LOCKED,
          locked)
    check("... carrying the caller's own name and none of the private keys",
          locked.get("name") == SECRET_NAME and "active_facts" not in locked
          and "recent_chat" not in locked, locked)
    hidden = people.build_person_dossier(SECRET_NAME, hide_memory_lists=True)
    check("... and on hide_memory_lists=True", hidden.get("withheld") is True
          and hidden.get("why") == PV.WITHHELD_HIDDEN, hidden)
    PV.note_state(app_locked=True)
    try:
        still = people.build_person_dossier(SECRET_NAME, app_locked=False)
    finally:
        _reset()
    check("a caller's False cannot unlock the builder",
          still.get("withheld") is True, still)


# ------------------------------------------------------------ 2. guardian views

def t_guardian_snapshots_and_diff_withhold_without_reading():
    rows = [{"path": SECRET_PATH, "before_sha256": "a" * 64, "timestamp": 1.0,
             "reason": "changed " + SECRET_SUMMARY, "size": 10}]
    reader = Reader(rows)
    _reset()
    try:
        code, plain = B._snapshot_page("", reader, lambda: {})
        check("unlocked: the journal comes back",
              code == 200 and plain["snapshots"]
              and plain["snapshots"][0].get("path") == SECRET_PATH, (code, plain))
        reader.boom = reader.calls = 0
        reader.boom = True
        code_l, locked = B._snapshot_page("app_locked=1", reader, lambda: {})
        code_h, hidden = B._snapshot_page("hide_memory_lists=1", reader, lambda: {})
        check("locked snapshots: withheld, empty page, honest sentence",
              code_l == 200 and locked.get("withheld") is True
              and locked.get("snapshots") == [] and locked.get("why") == PV.WITHHELD_LOCKED,
              (code_l, locked))
        check("... no path, reason or receipt id is in it",
              SECRET_PATH not in json.dumps(locked)
              and SECRET_SUMMARY not in json.dumps(locked), locked)
        check("... hidden lists answers the other sentence",
              code_h == 200 and hidden.get("withheld") is True
              and hidden.get("why") == PV.WITHHELD_HIDDEN, (code_h, hidden))
        check("... and a locked view never called the row reader",
              reader.calls == 0, reader.calls)
        reader.boom = False
        code_z, zero = B._snapshot_page(
            "app_locked=0&hide_memory_lists=false&force_unlock=1", reader, lambda: {})
        check("a false or force-unlock flag is not a bypass",
              code_z == 200 and zero.get("withheld") is not True and reader.calls == 1,
              (code_z, zero, reader.calls))

        diff_reader = Reader({"path": SECRET_PATH, "diff": SECRET_DIFF,
                              "ok": True, "same": False})
        code_d, plain_diff = B._diff_answer(
            "path=" + SECRET_PATH + "&sha_before=" + "a" * 64, diff_reader)
        check("unlocked: the module's own diff is passed through",
              code_d == 200 and plain_diff.get("diff") == SECRET_DIFF, plain_diff)
        diff_boom = Reader({"path": SECRET_PATH, "diff": SECRET_DIFF, "ok": True})
        diff_boom.boom = True
        code_dl, locked_diff = B._diff_answer(
            "path=" + SECRET_PATH + "&sha_before=" + "a" * 64 + "&app_locked=true",
            diff_boom)
        check("locked diff: withheld, empty, and no path echoed",
              code_dl == 200 and locked_diff.get("withheld") is True
              and locked_diff.get("diff") == "" and locked_diff.get("path") == ""
              and SECRET_PATH not in json.dumps(locked_diff), (code_dl, locked_diff))
        check("... and the differ was never called", diff_boom.calls == 0)

        PV.note_state(app_locked=True)
        try:
            code_t, trusted = B._snapshot_page(
                "app_locked=0&force_unlock=1", reader, lambda: {})
            code_td, trusted_diff = B._diff_answer(
                "path=" + SECRET_PATH + "&sha_before=" + "a" * 64 + "&app_locked=0",
                diff_boom)
        finally:
            _reset()
        check("the trusted lock survives a caller's false (snapshots)",
              code_t == 200 and trusted.get("withheld") is True, trusted)
        check("... and the same for the diff",
              code_td == 200 and trusted_diff.get("withheld") is True
              and diff_boom.calls == 0, trusted_diff)
    finally:
        _reset()


# ------------------------------------------------------------- 3. receipts

def t_receipts_list_withholds_without_reading_rows():
    _reset()
    saved_recent, saved_undoable = R.recent, R.is_undoable
    R.is_undoable = lambda row: True
    try:
        R.recent = Reader([{"receipt_id": "abc123", "summary": SECRET_SUMMARY,
                            "path": SECRET_PATH}])
        plain = R.list_view(10)
        check("unlocked: the list comes back with its rows",
              plain.get("withheld") is not True and plain["count"] == 1
              and SECRET_SUMMARY in json.dumps(plain), plain)
        reader = Reader([])
        reader.boom = True
        R.recent = reader
        locked = R.list_view(10, app_locked="1")
        hidden = R.list_view(10, hide_memory_lists="yes")
        code, out = R.handle_get("/api/receipts", "app_locked=1&force_unlock=1")
        check("locked: withheld, no rows, the App-lock sentence",
              locked.get("withheld") is True and locked.get("receipts") == []
              and locked.get("why") == PV.WITHHELD_LOCKED, locked)
        check("... hidden lists answers the other sentence",
              hidden.get("withheld") is True
              and hidden.get("why") == PV.WITHHELD_HIDDEN, hidden)
        check("... and recent() was never called", reader.calls == 0, reader.calls)
        check("... the GET route withholds too, force_unlock and all",
              code == 200 and out.get("withheld") is True
              and out.get("receipts") == [], (code, out))
        check("... no summary or path is in the withheld JSON",
              SECRET_SUMMARY not in json.dumps(locked)
              and SECRET_PATH not in json.dumps(locked), locked)
        R.recent = Reader([{"receipt_id": "abc123", "summary": SECRET_SUMMARY}])
        zero = R.list_view(10, app_locked="0", hide_memory_lists="false")
        check("a false flag leaves the normal list",
              zero.get("withheld") is not True and zero["count"] == 1, zero)
        PV.note_state(hide_memory_lists=True)
        try:
            still = R.handle_get("/api/receipts", "app_locked=0")
        finally:
            _reset()
        check("a caller's false cannot clear the trusted hidden state",
              still[0] == 200 and still[1].get("withheld") is True, still)
    finally:
        R.recent, R.is_undoable = saved_recent, saved_undoable
        _reset()


# --------------------------------------------------- 4. direct HTTP wrappers

class FakeGet:
    """The barest handler install() can wrap: records what `_send` was given."""

    def __init__(self, path):
        self.path = path
        self.sent = None
        self.client_address = ("127.0.0.1", 50000)
        self.connection = types.SimpleNamespace(getsockname=lambda: ("127.0.0.1", 8765))

    def do_GET(self):
        raise AssertionError("the original handler must not run")

    def do_POST(self):
        raise AssertionError("the original POST handler must not run")

    def _send(self, code, body):
        self.sent = (code, body)


def t_direct_http_routes_honour_the_lock_flags():
    _reset()
    # Receipts: its own install() wrapper, no other setup.
    R.install(FakeGet, origin_ok=lambda self: True,
              token_ok=lambda self: True, read_body=lambda self: b"{}")
    h = FakeGet("/api/receipts?app_locked=1")
    h.do_GET()
    check("HTTP GET /api/receipts?app_locked=1 answers withheld",
          h.sent and h.sent[0] == 200 and h.sent[1].get("withheld") is True,
          h.sent)

    # The Brain door: guardian page and dossier, install()ed on a bare handler.
    B.install(FakeGet, origin_ok=lambda self: True,
              token_ok=lambda self: True, read_body=lambda self: b"{}")
    saved_from, saved_rows = B._from_this_pc, None
    B._from_this_pc = lambda peer, local: True
    import jarvis_file_guardian as G
    saved_rows = G.rows
    G.rows = lambda: (_ for _ in ()).throw(
        AssertionError("a locked guardian route read the journal"))
    try:
        hg = FakeGet("/api/guardian/snapshots?app_locked=1")
        hg.do_GET()
        hd = FakeGet("/api/people/dossier?name=" + SECRET_NAME + "&app_locked=1")
        hd.do_GET()
    finally:
        B._from_this_pc = saved_from
        G.rows = saved_rows
        _reset()
    check("HTTP GET guardian snapshots with the lock flag answers withheld",
          hg.sent and hg.sent[0] == 200 and hg.sent[1].get("withheld") is True
          and hg.sent[1].get("snapshots") == [], hg.sent)
    check("HTTP GET the dossier with the lock flag answers withheld, no facts",
          hd.sent and hd.sent[0] == 200 and hd.sent[1].get("withheld") is True
          and "active_facts" not in hd.sent[1], hd.sent)


# --------------------------------------------------- 5. shipped and twin files

def t_the_hook_is_shipped_and_its_twin_matches():
    from _where import SHIPPED
    check("jarvis_private_view.py is in _where.SHIPPED",
          "jarvis_private_view.py" in SHIPPED)
    base = HERE.parent / "jarvis-backend"
    for name in ("jarvis_private_view.py", "jarvis_brain_reads.py",
                 "jarvis_people_crm.py", "jarvis_file_guardian.py",
                 "jarvis_receipts.py"):
        ours = (HERE / name).read_bytes().replace(b"\r\n", b"\n")
        theirs = (base / name).read_bytes().replace(b"\r\n", b"\n")
        check(f"the base twin of {name} matches", ours == theirs)
    check("the base's _where.py carries the new entry too",
          "jarvis_private_view.py" in (base / "_where.py").read_text(encoding="utf-8"))


def main():
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                import traceback
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, 0 skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
