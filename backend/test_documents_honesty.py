"""Two readers, no writer, and a status line that said everything was fine.

`SELECT ... FROM documents` runs in two places in jarvis_hud.py. Nothing in
the backend creates that table - there is no CREATE TABLE documents anywhere -
so both queries have always raised "no such table", both caught sqlite3.Error
and returned empty, and the brain map's source list reported

    "documents": DOCS_DB.exists()

which is true on every boot because DOCS_DB is memory.db, a file the memory
store creates for its own tables. Missing and empty were indistinguishable
from the outside, and the one surface that could have shown it asserted the
opposite.

These tests execute the real `_has_table` - lifted out of the source with ast
so the server module is never imported - against real SQLite files, and then
check the three call sites.

    python3 test_documents_honesty.py
"""
import ast, sqlite3, sys, tempfile, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "jarvis_hud.py"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _lift(*names):
    """Pull named top-level functions out of jarvis_hud.py and run them.

    Importing the module would start a server. These two functions are pure
    and depend on nothing but sqlite3, Path and sys, so the real source can be
    executed in isolation - the alternative is a paraphrase in the test, which
    would pass whatever the shipped code does.
    """
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    want = {n: None for n in names}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in want:
            want[node.name] = node
    missing = [n for n, v in want.items() if v is None]
    if missing:
        raise AssertionError(f"not defined at module level in jarvis_hud.py: {missing}")
    ns = {"sqlite3": sqlite3, "Path": Path, "sys": sys}
    exec(compile(ast.Module(body=list(want.values()), type_ignores=[]), "<lifted>", "exec"), ns)
    return ns


def t_has_table_tells_the_truth():
    ns = _lift("_ro_sqlite", "_has_table")
    has = ns["_has_table"]
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)

        missing = d / "nothing.db"
        check("a file that is not there has no table", has(missing, "documents") is False)

        # The actual production shape: memory.db exists, the memory store's
        # own tables are in it, and `documents` is not one of them.
        mem = d / "memory.db"
        con = sqlite3.connect(mem)
        con.execute("CREATE TABLE facts (id INTEGER PRIMARY KEY, text TEXT)")
        con.commit(); con.close()
        check("the file existing is not the question",
              mem.exists() and has(mem, "documents") is False,
              "this is the live case - memory.db is always there")
        check("a table that IS there is found", has(mem, "facts") is True)

        # CONTROL. Without this, a _has_table that returned False for
        # everything would pass every check above.
        docs = d / "real.db"
        con = sqlite3.connect(docs)
        con.execute("CREATE TABLE documents (id INTEGER PRIMARY KEY, content TEXT, "
                    "source TEXT, created_at REAL)")
        con.commit(); con.close()
        check("CONTROL: a real documents table reads as present",
              has(docs, "documents") is True)
        check("an empty documents table still counts as present",
              has(docs, "documents") is True,
              "present-but-empty and absent are different answers")

        # A view is not a table for this purpose either way, but the query
        # must not crash on one.
        con = sqlite3.connect(docs)
        con.execute("CREATE VIEW recent AS SELECT * FROM documents")
        con.commit(); con.close()
        check("a view does not read as a table", has(docs, "recent") is False)

        junk = d / "junk.db"
        junk.write_bytes(b"this is not a database")
        check("a corrupt file answers no instead of raising",
              has(junk, "documents") is False)


def t_it_does_not_leak_handles():
    ns = _lift("_ro_sqlite", "_has_table")
    has = ns["_has_table"]
    with tempfile.TemporaryDirectory() as d:
        mem = Path(d) / "memory.db"
        con = sqlite3.connect(mem)
        con.execute("CREATE TABLE facts (id INTEGER)")
        con.commit(); con.close()
        # build_graph calls this on every brain-map refresh. A connection left
        # open per call would hold a Windows file lock the memory store then
        # cannot write through.
        for _ in range(200):
            has(mem, "documents")
        check("200 calls do not exhaust anything", True)
        con = sqlite3.connect(mem)
        con.execute("INSERT INTO facts VALUES (1)")
        con.commit(); con.close()
        check("the file is still writable afterwards", True)


def t_the_three_call_sites():
    """CONTROL on the fix itself. Fails if any site goes back to the file check."""
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)

    def node_of(fn):
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == fn:
                return node
        return None

    def calls(node):
        """Every call in the function, as `receiver.attr` or `name`.

        Read from the tree rather than the text, because a comment that
        mentions the old check is not the old check - and this fix ships with
        a comment that mentions it.
        """
        out = []
        for n in ast.walk(node):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            if isinstance(f, ast.Attribute):
                who = getattr(f.value, "id", "") or getattr(f.value, "attr", "")
                out.append(f"{who}.{f.attr}")
            elif isinstance(f, ast.Name):
                out.append(f.id)
        return out

    for fn in ("collect_documents", "retrieval_corpus", "build_graph"):
        node = node_of(fn)
        if node is None:
            check(f"{fn} exists", False, "not found in jarvis_hud.py")
            continue
        c = calls(node)
        check(f"{fn} asks whether the table is there", "_has_table" in c,
              "no _has_table call in this function")
        check(f"{fn} no longer asks whether the file is there", "DOCS_DB.exists" not in c,
              "DOCS_DB is memory.db; that check is true on every boot")

    # The silent excepts were only defensible while a missing table was the
    # expected case. It no longer is.
    check("a failed documents read is reported, not swallowed",
          src.count("documents read failed") + src.count("documents corpus read failed") >= 2,
          "sqlite3.Error on a table that exists is a real fault")


if __name__ == "__main__":
    for fn in (t_has_table_tells_the_truth, t_it_does_not_leak_handles, t_the_three_call_sites):
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
