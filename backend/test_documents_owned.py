"""A documents table another program made is never read into Jarvis's prompts.

    python3 test_documents_owned.py

Epic-Jarvis keeps memory.db in ~/.openjarvis - OpenJarvis's folder, with
OpenJarvis's file name. If the OpenJarvis copy the owner downloaded is ever
run, its indexer creates a `documents` table in that file, and jarvis_hud.py
reads a table with exactly that name into the brain map and into the text
retrieval hands the model. documents-owned.patch makes both readers, and the
status line, ask one more question first: did Epic-Jarvis record creating
it? jarvis_owned_tables.py keeps that record.

No pytest, no network. Real SQLite files in a temp folder.

Three parts:
  1. jarvis_owned_tables.py itself - runs anywhere.
  2. The patch's context against what the earlier patches wrote - needs git.
  3. The patched jarvis_hud.py itself - only where it exists (the owner's PC,
     via JARVIS_BACKEND). Skipped, and said so, everywhere else.
"""
import ast
import sqlite3
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, missing, explain  # noqa: E402

# jarvis_owned_tables.py is OURS - it ships in this repository. Put this
# folder first for it, so a stale copy in the backend folder cannot shadow
# the one being edited (the same reason test_research.py does this).
sys.path.insert(0, str(HERE))
import jarvis_owned_tables as O  # noqa: E402
import _skeleton  # noqa: E402

SRC = BACKEND / "jarvis_hud.py"
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


DDL = "CREATE TABLE documents (id INTEGER PRIMARY KEY, content TEXT, source TEXT)"


def _openjarvis_made_it(db: Path) -> None:
    """What OpenJarvis's indexer does: a documents table, no record."""
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, "
                "content TEXT NOT NULL, source TEXT, metadata TEXT)")
    con.execute("INSERT INTO documents (content, source) VALUES ('private', 'x')")
    con.commit()
    con.close()


def t_the_module():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        mem = d / "memory.db"
        con = sqlite3.connect(mem)
        con.execute("CREATE TABLE facts (id INTEGER PRIMARY KEY, text TEXT)")
        con.commit(); con.close()

        check("no file: not ours", O.created_by_us(d / "absent.db", "documents") is False)
        check("no documents table: not ours", O.created_by_us(mem, "documents") is False)

        _openjarvis_made_it(mem)
        check("THE CASE: a documents table another program made is not ours",
              O.created_by_us(mem, "documents") is False)

        con = sqlite3.connect(mem)
        try:
            O.create_owned_table(con, "documents", DDL)
            refused = False
        except O.NotOurs:
            refused = True
        check("and Epic-Jarvis will not adopt it by creating over it", refused)
        check("and refusing left the record untouched",
              O.created_by_us(mem, "documents") is False)
        n = con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        con.close()
        check("and its rows are all still there - nothing is deleted", n == 1, f"rows={n}")

        # CONTROL: the path a future Epic-Jarvis feature would take.
        ours = d / "ours.db"
        con = sqlite3.connect(ours)
        O.create_owned_table(con, "documents", DDL)
        con.close()
        check("CONTROL: a table Epic-Jarvis created is ours",
              O.created_by_us(ours, "documents") is True)
        check("and the record is about that name only",
              O.created_by_us(ours, "facts") is False)

        con = sqlite3.connect(d / "x.db")
        for bad in ("CREATE TABLE IF NOT EXISTS documents (id INTEGER)",
                    "CREATE TABLE other (id INTEGER)",
                    "DROP TABLE documents"):
            try:
                O.create_owned_table(con, "documents", bad)
                ok = False
            except ValueError:
                ok = True
            check(f"refuses ddl {bad[:40]!r}", ok)
        try:
            O.create_owned_table(con, O.MARKER_TABLE, f"CREATE TABLE {O.MARKER_TABLE} (x)")
            ok = False
        except ValueError:
            ok = True
        check("refuses to 'own' its own record table", ok)
        con.close()
        check("a refused ddl created nothing",
              O.created_by_us(d / "x.db", "documents") is False)

        # Atomic: a DDL that fails leaves no record behind.
        con = sqlite3.connect(d / "y.db")
        try:
            O.create_owned_table(con, "documents", "CREATE TABLE documents (")
        except (sqlite3.Error, ValueError):
            pass
        con.close()
        c2 = sqlite3.connect(d / "y.db")
        has_marker = c2.execute("SELECT 1 FROM sqlite_master WHERE name=?",
                                (O.MARKER_TABLE,)).fetchone() is not None
        c2.close()
        check("a failed create leaves no record behind", not has_marker)

        junk = d / "junk.db"
        junk.write_bytes(b"not a database")
        check("a corrupt file answers no instead of raising",
              O.created_by_us(junk, "documents") is False)
        check("an odd name answers no instead of raising",
              O.created_by_us(mem, "documents; DROP TABLE facts") is False)

        # created_by_us opens read-only: it must never create the file.
        ghost = d / "ghost.db"
        O.created_by_us(ghost, "documents")
        check("asking never creates the file", not ghost.exists())


def t_the_patch_context():
    ok, out = _skeleton.rehearse("documents-owned.patch", "documents-honesty.patch")
    if ok is None:
        return check("SKIP - " + out, True)
    check("documents-owned.patch applies to what documents-honesty.patch wrote",
          ok is True, out)
    if ok:
        check("all three readers now ask whose table it is",
              out.count("_documents_are_ours(DOCS_DB)") == 4,
              f"found {out.count('_documents_are_ours(DOCS_DB)')}")


def _lift(src, *names):
    tree = ast.parse(src)
    want = {n: None for n in names}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in want:
            want[node.name] = node
    gone = [n for n, v in want.items() if v is None]
    if gone:
        raise AssertionError(f"not defined at module level in jarvis_hud.py: {gone}")
    ns = {"sqlite3": sqlite3, "Path": Path, "sys": sys}
    exec(compile(ast.Module(body=list(want.values()), type_ignores=[]), "<lifted>", "exec"), ns)
    return ns


def t_the_real_file():
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    src = SRC.read_text(encoding="utf-8")
    if "_documents_are_ours" not in src:
        return check("documents-owned.patch is applied to jarvis_hud.py", False,
                     "run scripts/apply-patches.ps1 first")
    ns = _lift(src, "_ro_sqlite", "_has_table", "_documents_are_ours")
    ours = ns["_documents_are_ours"]
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        theirs = d / "memory.db"
        _openjarvis_made_it(theirs)
        check("the real function says an OpenJarvis-made table is not ours",
              ours(theirs) is False)
        mine = d / "mine.db"
        con = sqlite3.connect(mine)
        O.create_owned_table(con, "documents", DDL)
        con.close()
        check("CONTROL: and one Epic-Jarvis made is", ours(mine) is True)

    tree = ast.parse(src)
    for fn in ("collect_documents", "retrieval_corpus", "build_graph"):
        node = next((n for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef) and n.name == fn), None)
        if node is None:
            check(f"{fn} exists", False)
            continue
        names = {n.func.id for n in ast.walk(node)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        check(f"{fn} asks whose table it is", "_documents_are_ours" in names)


if __name__ == "__main__":
    for fn in (t_the_module, t_the_patch_context, t_the_real_file):
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
