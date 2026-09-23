"""Which tables in memory.db Epic-Jarvis actually made.

THE PROBLEM

Epic-Jarvis keeps its memory in `~/.openjarvis/memory.db` - the same folder
and the same file name OpenJarvis uses, because Jarvis was first built to sit
in front of OpenJarvis. OpenJarvis was never part of this setup, but the
owner did download a copy once. If that copy is ever run, its document
indexer creates a table called `documents` in that same file (OpenJarvis
`rust/crates/openjarvis-tools/src/storage/sqlite.rs:58-67`).

`jarvis_hud.py` reads a table with exactly that name into the brain map and
into the text that retrieval puts in front of the model
(`documents-honesty.patch`). So the moment another program made that table,
whatever it indexed would start reaching Jarvis's prompts, and nobody would
have decided that.

THE RULE

A table in that file is read only if Epic-Jarvis recorded creating it. The
record is one row in `epic_jarvis_created_tables`, written in the same
transaction as the CREATE TABLE, by `create_owned_table()` below. A table
with the right name and no record is someone else's, and is left alone -
never read, never changed, never deleted.

Today nothing in Epic-Jarvis creates a `documents` table, so today the answer
is always "not ours" and the documents are never read. That is the same as
before this module existed (the table never existed either); what changes is
that it stays that way if another program adds one.

`created_by_us()` opens the file read-only and never raises: anything it
cannot answer counts as "not ours", which is the safe side.
"""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

MARKER_TABLE = "epic_jarvis_created_tables"

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_DDL = re.compile(r'^\s*CREATE\s+TABLE\s+"?([A-Za-z_][A-Za-z0-9_]*)"?\s*\(', re.I)


class NotOurs(Exception):
    """The table already exists and Epic-Jarvis did not make it."""


def _ro(db_path) -> sqlite3.Connection:
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5.0)


def _has_table(con: sqlite3.Connection, name: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (name,)).fetchone() is not None


def created_by_us(db_path, name: str) -> bool:
    """True only if the table exists AND Epic-Jarvis recorded creating it."""
    if not isinstance(name, str) or not _NAME.match(name):
        return False
    try:
        if not Path(db_path).is_file():
            return False
        con = _ro(db_path)
    except (sqlite3.Error, OSError, ValueError):
        return False
    try:
        if not _has_table(con, name) or not _has_table(con, MARKER_TABLE):
            return False
        return con.execute(f"SELECT 1 FROM {MARKER_TABLE} WHERE name=?",
                           (name,)).fetchone() is not None
    except sqlite3.Error:
        return False
    finally:
        con.close()


def create_owned_table(con: sqlite3.Connection, name: str, ddl: str) -> None:
    """Create table `name` with `ddl` and record that Epic-Jarvis made it.

    The only way a future Epic-Jarvis feature should make a table that is
    read into prompts. Refuses, and changes nothing, when:

    - the table already exists - it was made by something else, or by an
      earlier run that should not be silently adopted (NotOurs);
    - the DDL does not start `CREATE TABLE <name> (` - in particular
      `CREATE TABLE IF NOT EXISTS`, which would quietly adopt a table another
      program made (ValueError).
    """
    if not isinstance(name, str) or not _NAME.match(name) or name == MARKER_TABLE:
        raise ValueError(f"not a table name this can own: {name!r}")
    m = _DDL.match(ddl or "")
    if not m or m.group(1) != name:
        raise ValueError("ddl must be exactly `CREATE TABLE <name> (...)`, "
                         "without IF NOT EXISTS")
    if con.in_transaction:
        raise ValueError("commit or roll back the open transaction first")
    # One explicit transaction: the table and its record land together or
    # not at all. Not `with con:` - Python's sqlite3 does not open a
    # transaction before a CREATE TABLE by itself, so the table could be
    # made and the record lost.
    prev = con.isolation_level
    con.isolation_level = None
    try:
        con.execute("BEGIN IMMEDIATE")
        try:
            if _has_table(con, name):
                raise NotOurs(f"a table called {name!r} is already there and "
                              "Epic-Jarvis did not make it; it is left alone")
            con.execute(f"CREATE TABLE IF NOT EXISTS {MARKER_TABLE} ("
                        "name TEXT PRIMARY KEY, created_at REAL NOT NULL)")
            con.execute(ddl)
            con.execute(f"INSERT INTO {MARKER_TABLE} (name, created_at) "
                        "VALUES (?, ?)", (name, time.time()))
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
    finally:
        con.isolation_level = prev
