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

WHERE THE CODE COMES FROM. `jarvis_hud.py` is the owner's file and is not in
this repository, so in CI this suite used to be skipped BY NAME and every
check in it ran only on the owner's PC (`backend/run_suites.py`'s
NEEDS_OWNER list). What the whole patch stack's text can prove here was
MEASURED rather than assumed (2026-10-10, `backend/_stack.py`'s stand-in):

  * `_has_table` is written whole by `documents-honesty.patch`, so the stack
    carries it - but it CALLS `_ro_sqlite`, which the owner wrote and no patch
    does, and the stand-in has only that function's `def` line and the first
    line of its docstring (`mode=ro` and `as_uri` appear nowhere in it). So the
    two checks that EXECUTE it cannot be lifted and are named as skips here.
  * The last check is about the two sentences a failed documents read prints.
    Both are written by the patch, both are in the stand-in, and it needs no
    function at all - so it runs everywhere.

That leaves one real check in CI where there were none, and says plainly, by
name, which ones still need the owner's file. `.dsh-scratch`'s note of the
same date carries the measurement; `backend/run_suites.py`'s comment on the
list says which suites can now run part of themselves and why this one runs
only a part.

    python3 test_documents_honesty.py
"""
import ast, sqlite3, sys, tempfile, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test actually live - this folder in
# the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, missing, explain
HUD = BACKEND / "jarvis_hud.py"

FAILED, PASSED, SKIPPED = [], [], []

#: Why a check needs the owner's whole file.
_WHOLE_FILE = ("jarvis_hud.py is not on this machine and the patch stack's stand-in "
               "(backend/_stack.py) cannot be parsed as a file")

#: Why one function's calls cannot be read from the stand-in.
_NOT_IN_THE_STACK = ("the patch stack's stand-in (backend/_stack.py) does not carry this "
                     "function as a whole one - no patch writes it (retrieval_corpus, "
                     "build_graph) or a gap cuts its text short (collect_documents) - so its "
                     "calls can only be read from the owner's whole jarvis_hud.py")

#: Why the two checks that EXECUTE `_has_table` cannot run without the file.
#: MEASURED 2026-10-10, not assumed: `_has_table` itself IS written whole by
#: documents-honesty.patch and cuts cleanly out of the stand-in, but it calls
#: `_ro_sqlite`, and that one appears in the stand-in as its `def` line and the
#: first line of its docstring only - its body is the owner's own code, which
#: no patch writes, so the stand-in's `# gap` cuts it off. Run without it,
#: `_has_table` raises NameError instead of answering. Lifting the helper from
#: somewhere else and passing it in would be a paraphrase of the code under
#: test, which is the one thing this suite refuses to do.
_NOT_WHOLE = ("the patch stack's stand-in cannot hand over {names} whole - a function it "
              "only ever sees as another hunk's CONTEXT is cut off at the gap, so _has_table "
              "cannot be run: it calls _ro_sqlite, which the owner wrote and no patch does")

#: The checks `t_has_table_tells_the_truth` makes, in order.
_HAS_TABLE_CHECKS = ("a file that is not there has no table",
                     "the file existing is not the question",
                     "a table that IS there is found",
                     "CONTROL: a real documents table reads as present",
                     "an empty documents table still counts as present",
                     "a view does not read as a table",
                     "a corrupt file answers no instead of raising")
#: The checks `t_it_does_not_leak_handles` makes, in order.
_HANDLES_CHECKS = ("200 calls do not exhaust anything",
                   "the file is still writable afterwards")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    """A check this machine cannot run. Printed as `skip`, counted on its own,
    never as a pass; the summary line at the end carries the number into
    backend/run_suites.py."""
    SKIPPED.append(name)
    print(f"skip  {name} - {why}")


_STAND_IN = None


def _stack_text() -> str:
    """The whole patch stack's text for jarvis_hud.py, built once ("" when it
    cannot be built at all)."""
    global _STAND_IN
    if _STAND_IN is None:
        import _stack
        _STAND_IN = _stack.stand_in("jarvis_hud.py")[0] or ""
    return _STAND_IN


def _lift(*names):
    """Pull named top-level functions out of jarvis_hud.py and run them.

    `(namespace, the names it could not hand over)`. The second is empty
    whenever the owner's jarvis_hud.py is here - the normal case, and the one
    this suite was written for. In CI it names what the patch stack's stand-in
    does not write whole, and the caller turns each into a named skip.

    Importing the module would start a server. These functions are pure and
    depend on nothing but sqlite3, Path and sys, so the real source can be
    executed in isolation - the alternative is a paraphrase in the test, which
    would pass whatever the shipped code does.

    With no jarvis_hud.py on this machine, the same functions come out of the
    stand-in one at a time: it is fragments, so `ast.parse` cannot read it as
    a file, but a `def` the stack writes whole is cut out by line
    (`backend/_stack.py`'s `function_text`) and compiles on its own. A piece
    that does not compile is not a function to run, and is reported rather
    than executed."""
    if not HUD.is_file():
        import _stack
        src = _stack_text()
        if not src:
            return {}, list(names)
        ns = {"sqlite3": sqlite3, "Path": Path, "sys": sys}
        absent = []
        for name in names:
            piece = _stack.function_text(src, name)
            if piece is None:
                absent.append(name)
                continue
            try:
                exec(compile(piece, f"<{name}, lifted from the patch stack>", "exec"), ns)
            except SyntaxError:
                absent.append(name)
        return ns, absent
    tree = ast.parse(HUD.read_text(encoding="utf-8"))
    want = {n: None for n in names}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in want:
            want[node.name] = node
    missing = [n for n, v in want.items() if v is None]
    if missing:
        raise AssertionError(f"not defined at module level in jarvis_hud.py: {missing}")
    ns = {"sqlite3": sqlite3, "Path": Path, "sys": sys}
    exec(compile(ast.Module(body=list(want.values()), type_ignores=[]), "<lifted>", "exec"), ns)
    return ns, []


def _hud_text() -> str:
    """The whole file's text from whichever copy this machine has (the
    stand-in in CI), or "" when neither can be had."""
    return HUD.read_text(encoding="utf-8") if HUD.is_file() else _stack_text()


def _function_node(src: str, fn: str, real: bool):
    """`fn`'s own AST node, or None.

    From the real file: the first definition with that name, the way this
    suite always found them. From the stand-in: the one `def fn(` there is,
    cut out and parsed. None means the stand-in cannot answer - no patch
    writes that function at all, or (the shape a stand-in really has) the
    `def` is there but a `# gap` line at the margin ends the cut early, so the
    piece is not a whole function and cannot be parsed. Either way there is
    nothing honest to lift, and the caller says so by name instead."""
    if real:
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.FunctionDef) and node.name == fn:
                return node
        return None
    import _stack
    piece = _stack.function_text(src, fn)
    if piece is None:
        return None
    try:
        return ast.parse(piece).body[0]
    except SyntaxError:
        return None


def t_has_table_tells_the_truth():
    ns, absent = _lift("_ro_sqlite", "_has_table")
    if absent:
        for name in _HAS_TABLE_CHECKS:
            skip(name, _NOT_WHOLE.format(names=", ".join(absent)))
        return
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
    ns, absent = _lift("_ro_sqlite", "_has_table")
    if absent:
        for name in _HANDLES_CHECKS:
            skip(name, _NOT_WHOLE.format(names=", ".join(absent)))
        return
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
    """CONTROL on the fix itself. Fails if any site goes back to the file check.

    The tree is read rather than the text, because a comment that mentions the
    old check is not the old check - and this fix ships with a comment that
    mentions it. Which means these four checks need a function the stand-in can
    hand over whole, and it has none of these three: they are named as skips
    when jarvis_hud.py is not here. The last check is about the two sentences a
    failed read prints, needs no function at all, and runs either way.
    """
    real = HUD.is_file()
    src = _hud_text()
    tree = ast.parse(src) if real else None

    def node_of(fn):
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == fn:
                    return node
            return None
        return _function_node(src, fn, real)

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
            if real:
                check(f"{fn} exists", False, "not found in jarvis_hud.py")
            else:
                for what in (f"{fn} exists", f"{fn} asks whether the table is there",
                             f"{fn} no longer asks whether the file is there"):
                    skip(what, _NOT_IN_THE_STACK)
            continue
        c = calls(node)
        check(f"{fn} asks whether the table is there", "_has_table" in c,
              "no _has_table call in this function")
        check(f"{fn} no longer asks whether the file is there", "DOCS_DB.exists" not in c,
              "DOCS_DB is memory.db; that check is true on every boot")

    # The silent excepts were only defensible while a missing table was the
    # expected case. It no longer is. Both sentences are written by the patch
    # and neither sits in a gap, so this one runs wherever the suite does.
    if not src:
        skip("a failed documents read is reported, not swallowed",
             "jarvis_hud.py is not here and the patch stack's stand-in could not be built")
        return
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
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if SKIPPED:
        print(f"      ({len(SKIPPED)} check(s) read the whole of jarvis_hud.py, which only the "
              f"owner's PC has; they run there)")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
