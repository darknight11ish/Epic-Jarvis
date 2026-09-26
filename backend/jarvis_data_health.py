"""jarvis_data_health.py - "Data health in the preflight" (feasibility idea
I97, docs/FEASIBILITY-AUDIT-2026-09-26.md §2: "Small, read-only." /
"WARN, never fix.").

NEW MODULE, shipped whole. data-health.patch adds GET /api/data-health to
jarvis_hud.py (no settings, so no approval card either way - the same shape
as jarvis_sayable.py and jarvis_reach.py). backend/selftest.py's
`--preflight` reads this route as its own check, "Is Jarvis's own data
healthy?", right beside the other live checks that make up its "N pass,
N fail, N warn" line.

WHAT THIS CHECKS, and why each one is read-only:

  * The chat history database (chat-history.db) and the memory database
    (memory.db) each open, read-only (`mode=ro` - this never creates either
    file), and pass SQLite's own `PRAGMA integrity_check`. A file that does
    not exist yet is not a problem: history may be off, or Jarvis may never
    have learned anything yet.
  * Free disk space where Jarvis writes its data (the same folder the two
    databases above live in). Both databases, every settings file and the
    locked backup file all live here; running out mid-write is worse than
    running out anywhere else on the machine.
  * Every `*.json` settings file directly in that folder parses as JSON.
    A damaged one is not fixed or deleted here - jarvis_framework.py and
    every module's own settings() already fall back to a safe default when
    its file will not parse, so nothing this check finds is, by itself, an
    outage. It is a WARN precisely because the owner would otherwise have
    no way to learn that a setting silently reverted to its default.

THE GUARDRAIL, twice over: every row this module can return is `OK` or
`WARN`. It never returns anything read as a failure, and it never writes to,
moves, deletes or repairs anything it finds wrong - it only says so. Fixing
a damaged file is the owner's call (docs/FEASIBILITY-AUDIT-2026-09-26.md's
guardrail for I97 is literally "WARN, never fix").

Everything below takes its inputs as parameters (`config_dir`, `disk_usage`)
with real defaults, so test_data_health.py can hand in a temporary folder
and a stand-in `disk_usage()` and never touch the owner's real files.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Optional

OK, WARN = "ok", "warn"

TITLE = "Data health"

#: How little free space where Jarvis writes its data counts as "critically
#: low" (bytes). 1 GiB: room enough that this warns before a write actually
#: fails, not after.
LOW_DISK_BYTES = 1 * 1024 ** 3

#: How many *.json files in the folder to actually try to parse. A folder
#: full of thousands of small files (never expected in practice) still
#: returns quickly rather than reading forever.
MAX_JSON_FILES = 200


def _config_dir() -> Path:
    """The same folder jarvis_chat_log._config_dir(), jarvis_memory._config_dir()
    and jarvis_framework.CONFIG_DIR resolve to: OPENJARVIS_CONFIG_DIR or
    JARVIS_CONFIG_DIR, else ~/.openjarvis. Not imported from any of them -
    jarvis_memory in particular loads the embedder on import, which this
    read-only check has no reason to pay for."""
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def _sqlite_problem(path: Path) -> Optional[str]:
    """None: the file does not exist, or opens and checks out. A sentence:
    something is wrong with it. Opens `mode=ro` - this never creates the
    file and never writes a byte to it, so a store that is simply off, or
    has never been written to, is never mistaken for a broken one."""
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5.0)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return f"{type(exc).__name__}: {exc}"
    if row and str(row[0]) != "ok":
        return str(row[0])[:300]
    return None


def _bad_json_files(dir_: Path, *, limit: int = MAX_JSON_FILES) -> list:
    """[(name, error)] for every *.json file directly in `dir_` (never a
    subfolder - voice/, voice-models/ and notes/ hold real data, not
    settings) that does not parse. Reads each file; changes none of them."""
    bad = []
    try:
        names = sorted(p.name for p in dir_.glob("*.json") if p.is_file())
    except OSError:
        return bad
    for name in names[:limit]:
        try:
            json.loads((dir_ / name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            bad.append((name, type(exc).__name__))
    return bad


def check(*, config_dir=None, disk_usage=None) -> list:
    """[(status, what, detail)], status one of OK or WARN - never anything
    read as a failure (see the module docstring's guardrail). Never raises,
    and never creates, writes to, moves or deletes anything."""
    d = Path(config_dir) if config_dir is not None else _config_dir()
    disk_usage = disk_usage or shutil.disk_usage
    rows = []

    # -- the two databases ----------------------------------------------------
    chat_db = d / "chat-history.db"
    if not chat_db.is_file():
        rows.append((OK, "chat history: no database file yet (off, or nothing "
                         "written yet)", ""))
    else:
        problem = _sqlite_problem(chat_db)
        if problem is None:
            rows.append((OK, "the chat history database opens and checks out", ""))
        else:
            rows.append((WARN, "the chat history database may be damaged", problem))

    mem_env = (os.environ.get("JARVIS_MEMORY_DB") or "").strip()
    mem_db = Path(os.path.expanduser(mem_env)) if mem_env else d / "memory.db"
    if not mem_db.is_file():
        rows.append((OK, "memory store: no database file yet (nothing learned "
                         "yet)", ""))
    else:
        problem = _sqlite_problem(mem_db)
        if problem is None:
            rows.append((OK, "the memory store database opens and checks out", ""))
        else:
            rows.append((WARN, "the memory store database may be damaged", problem))

    # -- disk space -------------------------------------------------------------
    probe = d if d.exists() else d.parent
    try:
        usage = disk_usage(str(probe))
        free_gb = int(usage.free) / (1024 ** 3)
        if int(usage.free) < LOW_DISK_BYTES:
            rows.append((WARN, f"only {free_gb:.1f} GB free where Jarvis writes "
                               f"its data ({probe})",
                         "Chat history, memory and the locked backup file all "
                         "live here. Free up space soon - nothing here does it "
                         "for you."))
        else:
            rows.append((OK, f"{free_gb:.1f} GB free where Jarvis writes its data", ""))
    except OSError as exc:
        rows.append((WARN, "could not read free disk space",
                     f"{type(exc).__name__}: {exc}"))

    # -- settings files -----------------------------------------------------------
    try:
        import jarvis_framework as fw
        st = fw.status()
    except Exception as exc:
        st = None
        rows.append((WARN, "jarvis_framework.py will not import",
                     f"{type(exc).__name__}: {exc}"))
    if st is not None:
        if not st.get("config_file"):
            rows.append((WARN, "no jarvis-framework.toml found",
                         "Every setting is running on its default."))
        elif not st.get("config_loaded") or not st.get("sections"):
            rows.append((WARN, f"{st.get('config_file')} is present but nothing "
                               f"parsed from it",
                         "It may be damaged. Every setting in it is running on "
                         "its default until it is fixed by hand."))
        else:
            rows.append((OK, f"{st.get('config_file')} parses "
                             f"({len(st.get('sections') or [])} section(s))", ""))

    bad = _bad_json_files(d)
    if bad:
        shown = ", ".join(n for n, _e in bad[:8])
        more = f" and {len(bad) - 8} more" if len(bad) > 8 else ""
        rows.append((WARN, f"{len(bad)} settings file(s) in {d} will not parse "
                           f"as JSON",
                     f"{shown}{more}. Whatever each one controls is running on "
                     f"its own default until it is fixed by hand or deleted (a "
                     f"missing settings file is always read as \"off\"/default, "
                     f"never as broken)."))
    else:
        rows.append((OK, f"every settings file in {d} parses", ""))

    return rows


def view() -> dict:
    """GET /api/data-health. Never raises."""
    rows = check()
    return {
        "available": True,
        "title": TITLE,
        "warn": sum(1 for s, _w, _d in rows if s == WARN),
        "checks": [{"status": s, "what": w, "detail": det} for s, w, det in rows],
        "written_by": "code",
    }


def handle_get() -> tuple:
    return 200, view()
