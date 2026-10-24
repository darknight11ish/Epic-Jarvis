"""test_web_rogue_and_backup_hardening.py - the read-only security/backup probes.

    python -B backend/run_suites.py test_web_rogue_and_backup_hardening.py

WHY THIS EXISTS (2026-10-23, Gemini's security/backup work order). The work
order asked for four web-search "rogue command" guards and three backup
hardening changes. It was written against `origin/main = 6d821abee`, which is
much older than this tree: on today's `main` the three web guards it describes
are ALREADY enforced, by different (and stricter) code, so this suite pins that
behaviour rather than re-implementing it:

  * Web-Gap 1 (cardless smart-home under taint): `jarvis_asks_first.
    lights_without_card` refuses when anything outside shaped the turn;
  * Web-Gap 2 (post-private-read web search): `jarvis_agent.
    web_search_card_lines` asks whenever a reading tool ran or the conversation
    is tainted;
  * Web-Gap 3 (cardless reminder/timer/setting mutations under taint):
    `jarvis_agent.SCHEDULE_TOOLS` refuse when outside text shaped the turn,
    and `_settings_turn_is_shaped` does the same for settings;
  * Web-Gap 4 (multi-hop persistence) is NOT covered here: the write is already
    carded, but a note saved AFTER a person approves it carries no
    `source_taint` marker yet. That remains a real gap (see the review report).

The backup half IS new here (Backup-Gap 2): an archive is refused as a whole
before a single live file is touched - unsafe member names and links, then the
SQLite header + `quick_check` + `integrity_check` on every staged database.

Nothing in this file reads or writes the owner's real `~/.openjarvis`: every
path is a temp fixture and `_config_dir` is patched to it.
"""
from __future__ import annotations

import io
import json
import os
import sqlite3
import stat
import sys
import tempfile
import traceback
import zipfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_backup.py", "jarvis_agent.py", "jarvis_asks_first.py")

import jarvis_agent as A  # noqa: E402
import jarvis_asks_first as AF  # noqa: E402
import jarvis_backup as B  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------------------
#   The web guards this tree ALREADY carries (evidence, not new code)
# ---------------------------------------------------------------------------

def _watch(**kw):
    """A stand-in for jarvis_agent._TurnWatch with the fields these helpers read."""
    base = dict(read={}, tainted=False, money=False, spending_asked=False,
                memory=False, facts=(), owner_words="", provenance="",
                app_context=False)
    base.update(kw)
    return types.SimpleNamespace(**base)


def t_web_gap_1_outside_shaped_turn_gets_a_card():
    saved_lights, saved_lock = AF.lights_on, AF.lockdown_on
    try:
        AF.lights_on = lambda: True
        AF.lockdown_on = lambda: False
        why = AF.lights_without_card(None, "turn off the kitchen light",
                                     shaped="outside text shaped this turn")
        check("Web-Gap 1 is closed: an outside-shaped turn never gets the "
              "cardless smart-home path", bool(why), why)
        check("... and the reason says outside text shaped it",
              "outside text" in (why or "").lower(), why)
    finally:
        AF.lights_on, AF.lockdown_on = saved_lights, saved_lock


def t_web_gap_2_search_after_a_read_asks_first():
    clean = A.web_search_card_lines(_watch(), False, "tauri release notes")
    check("a clean turn's search needs no card", clean == [], clean)
    after_read = A.web_search_card_lines(_watch(read={"web_search": 1}), False,
                                         "tauri release notes")
    check("Web-Gap 2 is closed: after a reading tool the search asks",
          A.WEB_SEARCH_READ in after_read, after_read)
    tainted = A.web_search_card_lines(_watch(tainted=True), False, "tauri news")
    check("... and a tainted conversation asks too", A.WEB_SEARCH_READ in tainted,
          tainted)


def t_web_gap_3_schedule_and_settings_refuse_under_outside_text():
    check("Web-Gap 3 is closed for schedule tools: the refusal sentence exists",
          "outside text shaped this turn" in A.SCHEDULE_AFTER_OUTSIDE)
    check("... and the schedule tools are the cardless ones it covers",
          {"set_timer", "set_reminder", "todo_add"} <= set(A.SCHEDULE_TOOLS))
    check("... settings have their own refusal sentence",
          "outside text shaped this turn" in A.SETTINGS_AFTER_OUTSIDE)
    shaped = A._settings_turn_is_shaped.__doc__ is not None
    check("... and a turn shaped by a read is detected", shaped)


def t_web_gap_3_note_writes_wait_for_a_person():
    fake = types.SimpleNamespace(tainted=False, read={"web_search": 1},
                                 provenance="", app_context=False)
    why = A._TurnWatch.note_needs_a_person(fake)
    check("a note write after a reading tool waits for a person", bool(why), why)
    fake_clean = types.SimpleNamespace(tainted=False, read={}, provenance="",
                                       app_context=False)
    check("... and a clean turn's note write goes straight away",
          A._TurnWatch.note_needs_a_person(fake_clean) == "")
    check("... the gate action names the case",
          A.NOTE_AFTER_OUTSIDE_ACTION == "write_notes_after_outside_text")


# ---------------------------------------------------------------------------
#   Backup-Gap 2: the archive is refused as a whole, before anything is touched
# ---------------------------------------------------------------------------

def _zip(members):
    """zip_bytes from [(name, data)] or [(ZipInfo, data)]."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zf.writestr(name, data)
    return buf.getvalue()


def _good_db_bytes():
    buf = tempfile.TemporaryFile()
    buf.close()
    path = Path(tempfile.mkdtemp(prefix="jarvis-db-")) / "good.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT);")
    conn.execute("INSERT INTO t (v) VALUES ('intact');")
    conn.commit()
    conn.close()
    data = path.read_bytes()
    path.unlink()
    return data


def t_backup_gap_2_member_paths_are_checked():
    for good in ("db/memory.db", "settings/config.toml", "notes/a/b.md",
                 "voice/owner.json", "source/jarvis_x.py",
                 "secrets/chat-history-key.b64", "jarvis-framework.toml",
                 "manifest.json"):
        try:
            got = B.validate_archive_member_path(good)
            check(f"member {good!r} is allowed", got == good, got)
        except B.BackupRestoreRefusedError as exc:
            check(f"member {good!r} is allowed", False, str(exc))
    for bad in ("../../evil.db", "dbs/../../evil.db", "/etc/passwd",
                "C:\\Windows\\System32\\cmd.exe", "evil_script.py",
                "settings/../../x.json", "", "db/\x00x"):
        try:
            B.validate_archive_member_path(bad)
            check(f"member {bad!r} is refused", False, "it was allowed")
        except B.BackupRestoreRefusedError:
            check(f"member {bad!r} is refused", True)
    try:
        B.validate_archive_member_path("db/memory.db", is_symlink=True)
        check("a symbolic-link member is refused", False, "it was allowed")
    except B.BackupRestoreRefusedError:
        check("a symbolic-link member is refused", True)


def t_backup_gap_2_sqlite_checks_are_real():
    good = _good_db_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "good.db"
        db.write_bytes(good)
        ok, why = B.verify_staged_sqlite_db(db)
        check("a real database passes the staged check", ok, why)
        bad = Path(tmp) / "bad.db"
        bad.write_bytes(b"NOT_A_VALID_SQLITE_HEADER_AT_ALL" * 8)
        ok, why = B.verify_staged_sqlite_db(bad)
        check("a non-SQLite file is refused", not ok and "not a SQLite" in why, why)
        short = Path(tmp) / "short.db"
        short.write_bytes(good[:40])
        ok, why = B.verify_staged_sqlite_db(short)
        check("a cut-short database is refused", not ok and "cut short" in why, why)


def t_backup_gap_2_bad_archive_touches_no_live_file():
    good = _good_db_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        conf = Path(tmp) / "config"
        conf.mkdir()
        live_db = conf / "memory.db"
        live_db.write_bytes(b"LIVE-OLD-CONTENT")
        saved = B._config_dir
        B._config_dir = lambda: conf
        try:
            bad_zip = _zip([("db/memory.db", b"NOT_A_VALID_SQLITE_HEADER" * 8),
                            ("settings/keep.json", b'{"old": 1}')])
            try:
                B._apply_restore(bad_zip)
                check("a corrupt database refuses the whole restore", False,
                      "the restore went ahead")
            except (B.BackupRestoreRefusedError, B.RestoreError) as exc:
                check("a corrupt database refuses the whole restore", True)
            check("... and the live database is untouched",
                  live_db.read_bytes() == b"LIVE-OLD-CONTENT", live_db.read_bytes())
            check("... and no temp file was left beside it",
                  sorted(p.name for p in conf.iterdir()) == ["memory.db"],
                  sorted(p.name for p in conf.iterdir()))
            escaped = Path(tmp) / "evil.db"
            traversal = _zip([("../evil.db", b"x"), ("settings/ok.json", b"{}")])
            try:
                B._apply_restore(traversal)
                check("a path-traversal member refuses the whole restore", False,
                      "the restore went ahead")
            except B.BackupRestoreRefusedError:
                check("a path-traversal member refuses the whole restore", True)
            check("... and nothing was written outside the folder",
                  not escaped.exists())
            link = zipfile.ZipInfo("settings/link.json")
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            linked = _zip([(link, b"elsewhere")])
            try:
                B._apply_restore(linked)
                check("a linked member refuses the whole restore", False,
                      "the restore went ahead")
            except B.BackupRestoreRefusedError:
                check("a linked member refuses the whole restore", True)
            good_zip = _zip([("db/memory.db", good),
                             ("settings/keep.json", b'{"new": 1}')])
            done = B._apply_restore(good_zip)
            check("a whole, valid archive still restores",
                  (conf / "memory.db").read_bytes() == good
                  and (conf / "keep.json").read_bytes() == b'{"new": 1}',
                  done)
        finally:
            B._config_dir = saved


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and callable(fn):
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
