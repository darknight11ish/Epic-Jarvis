"""The second time axis: valid time and transaction time, kept apart.

    python3 test_bitemporal.py

No pytest, no network, no model. Real sqlite stores in a temp dir, plus a
source read for the two call sites that make the column visible.

The case every assertion here exists for: "I moved in January, I am telling
you in March." With one axis that is unstorable - you either record the move
in March, which is wrong about the world, or in January, which is wrong about
what Jarvis knew in February. Both matter: the first is what a person asks
about, the second is what explains an answer Jarvis gave at the time.
"""
import os, sys, tempfile, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test actually live - this folder
# in the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, missing, explain

import jarvis_memory as M

HUD = BACKEND / "jarvis_hud.py"
BRAIN_JS = REPO / "jarvis-desktop" / "src" / "brain.js"
BRAIN_RS = REPO / "jarvis-desktop" / "src-tauri" / "src" / "brain.rs"
BUILD_RS = REPO / "jarvis-desktop" / "src-tauri" / "build.rs"
SURFACES = (REPO / "jarvis-desktop" / "src-tauri" / "permissions"
            / "surfaces.toml")

FAILED, PASSED = [], []
DAY = 86400.0


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def fresh():
    d = Path(tempfile.mkdtemp(prefix="jarvis-bitemp-"))
    s = M.MemoryStore(path=d / "memory.db")
    M._store = s
    return s, d


def cols(store):
    c = store._connect()
    try:
        return {r["name"] for r in c.execute("PRAGMA table_info(facts)")}
    finally:
        c.close()


def t_the_column_exists():
    s, _ = fresh()
    have = cols(s)
    check("the facts table has retired_at", "retired_at" in have,
          f"columns are {sorted(have)}")


def t_moved_in_january_told_in_march():
    """The whole reason for the second axis."""
    s, _ = fresh()
    now = time.time()
    january = now - 60 * DAY
    old = s.add_fact("Mario lives in Lisbon")
    # March: he tells Jarvis, and says when it happened.
    s.retire(old, valid_to=january)
    new = s.add_fact("Mario lives in Berlin", valid_from=january)

    row = s.get(old)
    check("valid_to is January, not today",
          abs(row["valid_to"] - january) < 1,
          f"valid_to={row['valid_to']} january={january}")
    check("retired_at is today, not January",
          abs(row["retired_at"] - now) < 60,
          f"retired_at={row['retired_at']} now={now}")
    check("the two are genuinely different numbers",
          abs(row["retired_at"] - row["valid_to"]) > 50 * DAY)
    check("the new fact starts in January",
          abs(s.get(new)["valid_from"] - january) < 1)


def t_what_did_you_believe_then():
    """Transaction time: a fact that was believed, then was not."""
    s, _ = fresh()
    now = time.time()
    keep = s.add_fact("Mario prefers tabs")
    gone = s.add_fact("Mario drives a Volvo")
    s.retire(gone)

    # A moment before either was written: the store knew nothing.
    before = [f["id"] for f in s.known_at(now - 10 * DAY)]
    check("before anything was written, nothing was believed", before == [],
          f"got {before}")

    # Right now, after the retirement.
    ids_now = {f["id"] for f in s.known_at(time.time() + 1)}
    check("the retired fact is not in today's belief", gone not in ids_now,
          f"got {ids_now}")
    check("the kept fact is in today's belief", keep in ids_now)


def t_a_fact_believed_then_but_not_now():
    """The case a single axis cannot answer at all."""
    s, _ = fresh()
    fid = s.add_fact("Mario works at Acme")
    # Rewrite history so the row was created a week ago and retired yesterday.
    week = time.time() - 7 * DAY
    yesterday = time.time() - 1 * DAY
    c = s._connect()
    try:
        c.execute("UPDATE facts SET created=?, valid_from=?, valid_to=?, retired_at=?"
                  " WHERE id=?", (week, week, yesterday, yesterday, fid))
    finally:
        c.close()

    three_days_ago = time.time() - 3 * DAY
    then = [f["id"] for f in s.known_at(three_days_ago)]
    check("three days ago Jarvis believed it", fid in then, f"got {then}")
    now_ids = [f["id"] for f in s.known_at(time.time())]
    check("today it does not", fid not in now_ids, f"got {now_ids}")


def t_a_future_valid_to_is_not_retired_yet():
    """A lease that ends in December is true today.

    CONTROL. Three places computed "current", and one of them said
    `valid_to is None` while its own neighbouring line said
    `valid_to is None or valid_to > at`. Unreachable while retire() could only
    stamp now; reachable the moment it takes a date.
    """
    s, _ = fresh()
    december = time.time() + 90 * DAY
    fid = s.add_fact("Mario's lease runs to December")
    s.retire(fid, valid_to=december)

    ids = [f["id"] for f in s.current_facts()]
    check("a future valid_to is still current", fid in ids, f"got {ids}")
    st = s.status()
    check("and status counts it as current", st["current"] == 1,
          f"status={st}")
    hits = s.search("lease", k=5)
    if hits:
        check("and search flags it current, not retired",
              hits[0].get("current") is True, f"got {hits[0]}")
    else:
        check("and search flags it current, not retired", False,
              "search returned nothing at all")


def t_retire_is_still_one_way():
    """The second axis must not have opened a door to un-retiring."""
    s, _ = fresh()
    fid = s.add_fact("Mario's main editor is Vim")
    check("the first retire works", s.retire(fid) is True)
    check("the second does nothing", s.retire(fid) is False,
          "retiring twice must not move valid_to a second time")
    check("nothing was deleted", s.get(fid) is not None)


def t_an_old_store_is_migrated_not_broken():
    """An existing memory.db has no retired_at. Opening it must not fail."""
    d = Path(tempfile.mkdtemp(prefix="jarvis-bitemp-old-"))
    db = d / "memory.db"
    import sqlite3, json
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE facts (
            id INTEGER PRIMARY KEY, text TEXT NOT NULL, source TEXT,
            created REAL NOT NULL, valid_from REAL NOT NULL, valid_to REAL,
            retired_by INTEGER, embedded INTEGER NOT NULL DEFAULT 0, meta TEXT);
        CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);""")
    then = time.time() - 30 * DAY
    c.execute("INSERT INTO facts (text, source, created, valid_from, valid_to, meta)"
              " VALUES ('an old retired fact','user',?,?,?,'{}')",
              (then, then, then + DAY))
    c.execute("INSERT INTO facts (text, source, created, valid_from, meta)"
              " VALUES ('an old live fact','user',?,?,'{}')", (then, then))
    c.commit(); c.close()

    s = M.MemoryStore(path=db)
    check("an old store still opens", "retired_at" in cols(s))
    c = s._connect()
    try:
        rows = {r["text"]: dict(r) for r in c.execute("SELECT * FROM facts")}
    finally:
        c.close()
    check("a historically retired row gets retired_at backfilled",
          rows["an old retired fact"]["retired_at"] is not None)
    check("and it is backfilled from valid_to, the only thing known",
          rows["an old retired fact"]["retired_at"]
          == rows["an old retired fact"]["valid_to"])
    check("a live row is left alone",
          rows["an old live fact"]["retired_at"] is None)


def t_reopening_does_not_re_migrate():
    """ALTER TABLE twice is an error, so the guard has to be a real check."""
    d = Path(tempfile.mkdtemp(prefix="jarvis-bitemp-re-"))
    M.MemoryStore(path=d / "memory.db")
    try:
        s = M.MemoryStore(path=d / "memory.db")
        ok = "retired_at" in cols(s)
    except Exception as exc:
        ok = False
        print(f"        {type(exc).__name__}: {exc}")
    check("opening the same store twice is fine", ok)


def t_it_is_reachable():
    """A column nobody reads is not a feature. Check every hop."""
    if not HUD.is_file():
        check("the route exposes known_at", False, f"no {HUD}")
        return
    src = HUD.read_text(encoding="utf-8")
    check("the facts route accepts ?known_at",
          'known = _qs_float(self, "known_at")' in src)
    check("and answers it from the store, not from a filter over today's rows",
          "st.known_at(known" in src)
    check("a bad timestamp is None rather than 1970",
          "def _qs_float" in src and "1.0e9 < v" in src)
    check("the as-of answer says it is read-only",
          "you cannot" in src and "edit the past" in src)


def t_the_desktop_can_ask():
    """Four files must agree or the command is callable from nowhere."""
    for path, needle, label in (
        (BRAIN_RS, "pub async fn brain_memory_as_of", "the command exists"),
        (BUILD_RS, '"brain_memory_as_of"', "build.rs declares it (the ACL)"),
        (SURFACES, "allow-brain-memory-as-of", "a surface grants it"),
        (BRAIN_JS, 'invoke("brain_memory_as_of"', "the pane calls it"),
    ):
        if not path.is_file():
            check(label, False, f"no {path}")
            continue
        check(label, needle in path.read_text(encoding="utf-8"))
    if BRAIN_RS.is_file():
        rs = BRAIN_RS.read_text(encoding="utf-8")
        check("a non-finite timestamp is refused before it is formatted",
              "is_finite()" in rs)
    if BRAIN_JS.is_file():
        js = BRAIN_JS.read_text(encoding="utf-8")
        check("the pane cannot write while showing the past",
              "memoryAsOf !== null" in js and "Return to now" in js)
        check("and the gap between the axes is rendered",
              "function whenNoticed" in js)


def main():
    for fn in (t_the_column_exists, t_moved_in_january_told_in_march,
               t_what_did_you_believe_then, t_a_fact_believed_then_but_not_now,
               t_a_future_valid_to_is_not_retired_yet, t_retire_is_still_one_way,
               t_an_old_store_is_migrated_not_broken,
               t_reopening_does_not_re_migrate,
               t_it_is_reachable, t_the_desktop_can_ask):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
