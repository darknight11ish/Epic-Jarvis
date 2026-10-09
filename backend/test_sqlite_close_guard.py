"""Does any shipped module hand a `with ... as c:` block a connection that
commits but never closes?

    python3 test_sqlite_close_guard.py

WHY THIS SUITE EXISTS (2026-10-08: a bug class, after the third hand fix)

`sqlite3.Connection`'s own context manager COMMITS on the way out and never
closes the connection. So a module whose `_db()` helper hands back a bare
`sqlite3.connect(...)` leaks an OPEN HANDLE on its database file for every

    with self._lock, self._db() as c:

block, until CPython happens to collect the connection - immediate on a quiet
line of code, and NOT immediate when a caught exception's traceback, a
generator frame or a temp-folder object still holds a reference. On Windows an
open handle makes the file undeletable, so TemporaryDirectory's own cleanup
raised, twice, inside test_sayable.py's group (run 2026-10-07, PR #86):

    PermissionError: [WinError 32] The process cannot access the file
    because it is being used by another process:
    'C:\\Users\\RUNNER~1\\AppData\\Local\\Temp\\tmpqw88ug3r\\schedule.json'

That cost hours of misdiagnosis twice, in two different suites, because the
message names a temp folder and the suite it landed on kept changing.

The fix was then written BY HAND THREE TIMES: jarvis_schedule.py grew its own
private `_ClosingConnection` (PR #112), then jarvis_goals.py and
jarvis_projects.py grew a second and a third (PR #129). Three private copies is
how a fourth module reinvents the bug, or misses the fix - so the class now
lives once, in jarvis_sqlite.py, and this suite is the part that actually
closes the class.

WHAT IT READS, AND WHY IT IS SOURCE RATHER THAN A LIST OF NAMES

Every module this repository ships - `backend/_where.py`'s SHIPPED list, the
one apply-patches.ps1 copies by - parsed with `ast`. Each `with ... as c:`
block is followed back to the `sqlite3.connect(...)` behind it, through a
helper in that module or in a shipped module it calls (`self._db()`,
`_db(store)`, `jarvis_sqlite.connect(path)`). No file is named by the check
itself, so a module written tomorrow is covered the moment it is added to
SHIPPED - which test_shipped_modules.py refuses to leave undone.

A connection handed to a `with` block is reported unless it is one of:

  * wrapped in `contextlib.closing(...)` - that calls close() for you. The
    existing example is jarvis_topics.py's `closing(st._connect())`.
  * opened with `factory=` a `sqlite3.Connection` subclass whose `__exit__`
    closes the connection - jarvis_sqlite.py's `_ClosingConnection`, which
    jarvis_schedule.py, jarvis_goals.py and jarvis_projects.py now share. A
    factory whose `__exit__` does NOT close is reported, so `factory=` cannot
    be used to silence this check.

WHAT IT DELIBERATELY DOES NOT FLAG, AND WHY THAT IS NOT A HOLE

  * A raw connection whose caller closes it in a `finally`, never as a `with`
    item of its own - jarvis_tellme.py's `_db(sched)`, used by `_state`,
    `_save` and `_tidy`. There is no `with` block to leak the handle, so the
    shape this suite is about is not present.
  * A connection used as its own context manager through an object this check
    cannot resolve - `with s._connect() as c:` in test_memory_intake.py, and
    `with sched._db() as c:` in jarvis_tellme.py. `s` and `sched` are values,
    not module names; the class behind them could close (jarvis_memory.py's
    own store) or not, and guessing either way would be a false positive or a
    false negative. Reading only what the source proves is the point.
  * The suites' own scratch files: four of them open a temporary database with
    `with sqlite3.connect(...)` directly (test_focus.py, test_memory_safety.py,
    test_tasks.py, test_tellme.py). `test_*.py` is out of scope here - this is
    about the modules that reach the owner's PC.
  * `jarvis-backend/`, the published base: it is a copy, and
    test_base_matches_repo.py already fails if its copy is not this one's.

Needs nothing from the owner's PC; runs anywhere, including CI.
"""
from __future__ import annotations

import ast
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _where  # noqa: E402

FAILED, PASSED = [], []

#: Modules whose closing connection class this suite expects to find, and to
#: find exactly once. Named here on purpose: these three are the ones whose
#: private copies were removed, so a regression in any of them must be loud.
SHARED_BY = ("jarvis_schedule.py", "jarvis_goals.py", "jarvis_projects.py")

#: The one module allowed to define a `sqlite3.Connection` subclass.
CLOSING_MODULE = "jarvis_sqlite.py"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# ------------------------------------------------------------ reading the code --

class _Mod:
    """One module's source, parsed, with the four maps the walk needs."""

    def __init__(self, name: str, src: str):
        self.name = name
        self.src = src
        self.tree = ast.parse(src)
        self.funcs = {}          # top-level function name -> node
        self.classes = {}        # class name -> node
        self.methods = {}        # (class name, method name) -> node
        self.mods = {}           # local name -> module name (`import x as y`)
        self.froms = {}          # local name -> (module name, original name)
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.funcs[node.name] = node
            elif isinstance(node, ast.ClassDef):
                self.classes[node.name] = node
                for m in node.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.methods[(node.name, m.name)] = m
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    top = a.name.split(".")[0]
                    self.mods[a.asname or top] = top
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                for a in node.names:
                    self.froms[a.asname or a.name] = (top, a.name)


def analyse(sources: dict) -> list:
    """Every `with ... as <name>:` in `sources` that is handed a connection
    which commits but does not close.

    `sources` is {module name: source text}. Returns [(module, lineno, why)],
    in file order. This is the whole check, on plain text, so its own
    behaviour is testable - see `t_the_check_catches_the_old_shape` below.
    """
    mods = {}
    for name, src in sources.items():
        # A key may be a module name or a file name; the maps below are looked
        # up by module name, so "jarvis_sqlite.py" and "jarvis_sqlite" must not
        # be two different things.
        name = name[:-3] if name.endswith(".py") else name
        try:
            mods[name] = _Mod(name, src)
        except SyntaxError:
            continue

    def callable_of(mod, func, cls):
        """(module, function node) this call expression calls, or None."""
        if isinstance(func, ast.Name):
            if func.id in mod.funcs:
                return mod, mod.funcs[func.id]
            got = mod.froms.get(func.id)
            if got and got[0] in mods and got[1] in mods[got[0]].funcs:
                return mods[got[0]], mods[got[0]].funcs[got[1]]
            return None
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            base = func.value.id
            if base in ("self", "cls") and cls:
                node = mod.methods.get((cls, func.attr))
                return (mod, node) if node else None
            other = mod.mods.get(base)
            if other and other in mods and func.attr in mods[other].funcs:
                return mods[other], mods[other].funcs[func.attr]
        return None

    def returned_connect(mod, fn, seen):
        """The sqlite3.connect(...) this function hands back, or None."""
        assigned = {}
        for n in ast.walk(fn):
            if isinstance(n, (ast.Assign, ast.AnnAssign)) and isinstance(n.value, ast.Call):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                for t in targets:
                    if isinstance(t, ast.Name):
                        assigned[t.id] = n.value
        for n in ast.walk(fn):
            if not isinstance(n, ast.Return) or n.value is None:
                continue
            v = n.value
            if isinstance(v, ast.Name):
                v = assigned.get(v.id)
            if isinstance(v, ast.Call):
                got = connect_behind(mod, v, None, seen)
                if got:
                    return got
        return None

    def connect_behind(mod, call, cls, seen):
        """(module, the sqlite3.connect(...) call) behind `call`, or None."""
        if _is_sqlite_connect(call):
            return mod, call
        key = (mod.name, ast.unparse(call.func))
        if key in seen:
            return None
        seen = seen | {key}
        got = callable_of(mod, call.func, cls)
        if not got:
            return None
        return returned_connect(got[0], got[1], seen)

    def closing_wrapped(expr):
        """`closing(X)` / `contextlib.closing(X)`: close() is called for you."""
        for n in ast.walk(expr):
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Name) and f.id == "closing":
                    return True
                if isinstance(f, ast.Attribute) and f.attr == "closing":
                    return True
        return False

    def factory_of(call):
        for kw in call.keywords:
            if kw.arg == "factory":
                return kw.value
        return None

    def class_closes(mod, expr, seen=()):
        """True/False/None: does this `factory=` class close the connection?

        None means the class is not in the sources being read at all."""
        if isinstance(expr, ast.Name):
            node = mod.classes.get(expr.id)
            owner = mod
            if node is None:
                got = mod.froms.get(expr.id)
                if got and got[0] in mods and got[1] in mods[got[0]].classes:
                    owner, node = mods[got[0]], mods[got[0]].classes[got[1]]
        elif isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
            other = mod.mods.get(expr.value.id)
            node = mods[other].classes.get(expr.attr) if other in mods else None
            owner = mods.get(other)
        else:
            return None
        if node is None:
            return None
        if (owner.name, ast.unparse(expr)) in seen:
            return False
        seen = seen + ((owner.name, ast.unparse(expr)),)
        mine = owner.methods.get((node.name, "__exit__"))
        if mine is not None:
            return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                       and n.func.attr == "close" for n in ast.walk(mine))
        # No __exit__ of its own: it inherits one. Safe only if a base closes -
        # inheriting sqlite3.Connection's own is exactly the bug.
        for base in node.bases:
            got = class_closes(owner, base, seen)
            if got:
                return True
        return False

    def with_items(tree):
        """(class name, with node, item) for every `with` in the module."""
        out = []

        def walk(node, cls):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    walk(child, child.name)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    walk(child, cls)
                else:
                    if isinstance(child, ast.With):
                        for item in child.items:
                            out.append((cls, child, item))
                    walk(child, cls)

        walk(tree, None)
        return out

    found = []
    for name in sorted(mods):
        mod = mods[name]
        for cls, node, item in with_items(mod.tree):
            ctx = item.context_expr
            if not isinstance(ctx, ast.Call) or closing_wrapped(ctx):
                continue
            got = connect_behind(mod, ctx, cls, frozenset())
            if not got:
                continue
            owner, connect = got
            factory = factory_of(connect)
            said = f"{ast.unparse(ctx)}"
            if factory is None:
                found.append((name, node.lineno,
                              f"`with {said} as ...` is handed a raw sqlite3 connection "
                              f"(sqlite3.connect with no factory=): it commits and leaves "
                              f"the handle open"))
                continue
            if class_closes(owner, factory) is True:
                continue
            found.append((name, node.lineno,
                          f"`with {said} as ...` is handed a connection whose factory "
                          f"({ast.unparse(factory)}) has no __exit__ that closes it"))
    return found


def _is_sqlite_connect(call) -> bool:
    f = call.func
    return (isinstance(f, ast.Attribute) and f.attr == "connect"
            and isinstance(f.value, ast.Name) and f.value.id == "sqlite3")


# --------------------------------------------------------------- reading the folder --

def backend_sources() -> dict:
    """{module name: source} for every module this repository ships, read from
    the backend being checked: flat beside the other modules (the owner's PC,
    and run_suites.py's staged copy of SHIPPED), or under rebuilt/ when that is
    this repository's own backend/ folder.

    The list is `_where.SHIPPED` - the one apply-patches.ps1 copies by, and the
    one test_shipped_modules.py keeps equal to the script's - and not every
    `*.py` in the folder. Two reasons: a file that is not shipped never reaches
    the owner's PC, and reading his own unshipped modules (jarvis_hud.py and the
    rest, which this repository does not own) would make this suite go red about
    code it cannot fix. A module written tomorrow is covered the moment it is
    added to SHIPPED - which test_shipped_modules.py refuses to leave undone.
    """
    if "srcs" not in _CACHE:
        srcs, missing = {}, []
        for rel in _where.SHIPPED:
            leaf = rel.rsplit("/", 1)[-1]
            if not leaf.endswith(".py"):
                continue                      # jarvis_hud.html and its like
            for p in (_where.BACKEND / leaf, _where.BACKEND / rel):
                if p.is_file():
                    srcs[leaf[:-3]] = p.read_text(encoding="utf-8", errors="replace")
                    break
            else:
                missing.append(leaf)
        _CACHE["srcs"], _CACHE["missing"] = srcs, missing
    return _CACHE["srcs"]


def missing_shipped() -> list:
    """Shipped modules the backend being checked does not have."""
    backend_sources()
    return _CACHE["missing"]


_CACHE = {}


# ------------------------------------------------------------------------ tests --

def t_the_check_reads_the_backend_it_thinks_it_does():
    """A walk that read nothing would pass every other check here."""
    srcs = backend_sources()
    check(f"the check read the modules that ship ({len(srcs)} of them)",
          len(srcs) > 100, f"only {len(srcs)} source(s): {sorted(srcs)[:5]}")
    miss = missing_shipped()
    check("... and every module this repository ships was read", not miss,
          f"not in {_where.BACKEND}: {', '.join(miss)} - copy backend\\<name> into "
          f"the backend folder (apply-patches.ps1 does this for you)")
    check("... including the three modules whose private copies were removed",
          all(Path(n).stem in srcs for n in SHARED_BY),
          f"missing: {[n for n in SHARED_BY if Path(n).stem not in srcs]}")
    check("... and the shared helper they now use", Path(CLOSING_MODULE).stem in srcs)


def t_the_check_catches_the_old_shape():
    """The detector on made-up sources: the bug is caught, the three
    legitimate shapes are not, and a `factory=` that does not close is not a
    way out. Without this the suite could be green because it looks at
    nothing - the one shape a guard must never have."""
    raw = ("import sqlite3\n"
           "class Store:\n"
           "    def _db(self):\n"
           "        c = sqlite3.connect(self.path, timeout=30)\n"
           "        return c\n"
           "    def get(self, k):\n"
           "        with self._lock, self._db() as c:\n"          # line 7
           "            return c.execute('select 1').fetchone()\n")
    got = analyse({"m_raw.py": raw})
    check("the old shape - a raw _db() used as `with self._db() as c:` - is caught",
          len(got) == 1 and got[0][1] == 7 and "raw sqlite3 connection" in got[0][2],
          f"{got}")

    shared = ("import sqlite3\n"
              "import jarvis_sqlite\n"
              "class Store:\n"
              "    def _db(self):\n"
              "        return jarvis_sqlite.connect(self.path, timeout=30)\n"
              "    def get(self, k):\n"
              "        with self._lock, self._db() as c:\n"
              "            return c.execute('select 1').fetchone()\n")
    helper = ("import sqlite3\n"
              "class _ClosingConnection(sqlite3.Connection):\n"
              "    def __exit__(self, *exc):\n"
              "        try:\n"
              "            return super().__exit__(*exc)\n"
              "        finally:\n"
              "            self.close()\n"
              "def connect(path, timeout=30):\n"
              "    return sqlite3.connect(path, timeout=timeout, factory=_ClosingConnection)\n")
    check("... and a bare `with sqlite3.connect(...) as c:`, with no helper at all, is caught",
          len(analyse({"m_direct": "import sqlite3\n"
                                   "def count(path):\n"
                                   "    with sqlite3.connect(path) as c:\n"
                                   "        return c.execute('select 1').fetchone()\n"})) == 1)
    check("the fixed shape - `with self._db() as c:` through jarvis_sqlite.connect - is not",
          analyse({"m_fixed.py": shared, "jarvis_sqlite.py": helper}) == [])
    private = ("import sqlite3\n"
               "class _ClosingConnection(sqlite3.Connection):\n"
               "    def __exit__(self, *exc):\n"
               "        try:\n"
               "            return super().__exit__(*exc)\n"
               "        finally:\n"
               "            self.close()\n"
               "class Store:\n"
               "    def _db(self):\n"
               "        return sqlite3.connect(self.path, timeout=30, factory=_ClosingConnection)\n"
               "    def get(self, k):\n"
               "        with self._lock, self._db() as c:\n"
               "            return c.execute('select 1').fetchone()\n")
    check("a private copy of the class, in the module that uses it - the shape the three "
          "modules had before this change - is not a leak",
          analyse({"m_private.py": private}) == [],
          "it IS the other half of the class, and the check below is the one that "
          "objects to a second copy")

    leaks = helper.replace("self.close()", "pass")
    check("... but a `factory=` class whose __exit__ does NOT close is flagged",
          len(analyse({"m_fixed.py": shared, "jarvis_sqlite.py": leaks})) == 1,
          f"{analyse({'m_fixed.py': shared, 'jarvis_sqlite.py': leaks})}")

    closed = ("import sqlite3, contextlib\n"
              "class Store:\n"
              "    def _db(self):\n"
              "        return sqlite3.connect(self.path, timeout=30)\n"
              "    def a(self):\n"
              "        with contextlib.closing(self._db()) as c:\n"
              "            return c.execute('select 1').fetchone()\n"
              "    def b(self):\n"
              "        c = self._db()\n"
              "        try:\n"
              "            return c.execute('select 1').fetchone()\n"
              "        finally:\n"
              "            c.close()\n")
    check("contextlib.closing(...) and a helper closed in a `finally` are not flagged",
          analyse({"m_ok.py": closed}) == [], f"{analyse({'m_ok.py': closed})}")

    other = ("def get(store):\n"
             "    with store._connect() as c:\n"
             "        return c.execute('select 1').fetchone()\n")
    check("a connection reached through an object the check cannot type is left alone "
          "(jarvis_tellme.py's `with sched._db()`, test_memory_intake.py's `with s._connect()`)",
          analyse({"m_other.py": other}) == [])


def t_the_check_sees_the_three_modules_at_all():
    """The sensitivity proof, kept as a check: the same three modules' own
    source, with the shared helper swapped back for a bare `sqlite3.connect` -
    the shape they had before this fix - must be caught, with the line the
    `with` block is on. Without this, every other check here could be green
    because the walk stopped resolving `jarvis_sqlite.connect` and sees
    nothing - the one way a guard goes quietly blind."""
    srcs = backend_sources()
    for name in SHARED_BY:
        stem = Path(name).stem
        old = ("jarvis_sqlite.connect(self.path, timeout=30)",
               "sqlite3.connect(self.path, timeout=30)")
        raw = srcs[stem].replace(old[0], old[1])
        found = analyse({stem: raw})
        check(f"with its `_db()` put back to a raw sqlite3.connect, {name} is caught "
              f"({len(found)} place(s))", bool(found) and found[0][1] > 0,
              f"{found[:3]}")


def t_the_legitimate_shapes_in_this_repo_are_not_flagged():
    """The shapes the guard must leave alone, taken from this repository rather
    than invented: `closing(...)` in jarvis_topics.py and in rebuilt/
    jarvis_memory.py, and - in jarvis_tellme.py - a raw `_db(sched)` whose
    callers close it in a `finally`, plus a connection reached through another
    object (`with sched._db() as c:`, the Scheduler's own method). Checked on
    the real sources, so a change to the detector that starts flagging them is
    caught here rather than in the suite the owner is running."""
    srcs = backend_sources()
    for name, must_contain in (("jarvis_topics", "closing(st._connect())"),
                               ("jarvis_memory", "closing(self._connect())"),
                               ("jarvis_tellme", "finally:")):
        src = srcs.get(name)
        check(f"{name}.py is one of the files this check reads", bool(src), sorted(srcs)[:5])
        if not src:
            continue
        check(f"... and the shape it must not flag is really in it ({must_contain})",
              must_contain in src)
        got = analyse({name: src})
        check(f"... and {name}.py is not flagged", got == [], f"{got[:3]}")


def t_exactly_one_module_owns_the_closing_connection():
    """The other half of the bug class: a private copy per module is what let a
    fourth module miss the fix. One class, in one file. A second copy - in a
    new module, or grown back into one of these three - fails here."""
    srcs = backend_sources()
    owners, definitions = [], []
    for name, src in sorted(srcs.items()):
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(ast.unparse(b).split(".")[-1] == "Connection" for b in node.bases):
                continue
            owners.append(f"{name}.py")
            definitions.append((f"{name}.py", node))
    check("exactly one module defines a sqlite3.Connection subclass",
          len(owners) == 1 and owners[0] == CLOSING_MODULE,
          f"defined in: {owners} - the closing connection belongs in {CLOSING_MODULE} alone")
    for where, node in definitions:
        exits = [m for m in node.body if isinstance(m, ast.FunctionDef) and m.name == "__exit__"]
        closes = bool(exits) and any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                                     and n.func.attr == "close" for n in ast.walk(exits[0]))
        check(f"{where}'s {node.name}.__exit__ closes the connection", closes,
              "without `self.close()` in __exit__, `with ... as c:` commits and leaks the "
              "handle - the WinError 32 failure of 2026-10-07")


def t_the_three_modules_share_it():
    """The fix, positively: these three open their connections through the one
    helper rather than each keeping its own copy of the class."""
    srcs = backend_sources()
    for name in SHARED_BY:
        src = srcs.get(Path(name).stem)
        check(f"{name} opens its connections through jarvis_sqlite.connect",
              bool(src) and "jarvis_sqlite.connect(" in src,
              f"{name} does not call jarvis_sqlite.connect( - a raw sqlite3.connect "
              f"left the handle open on the Windows runner (2026-10-07/08)")


def t_no_shipped_module_hands_a_with_block_an_unclosed_connection():
    found = analyse(backend_sources())
    if found:
        detail = (f"{len(found)} place(s) - a leaked handle is what made schedule.json "
                  f"undeletable on the Windows runner (2026-10-07): "
                  + "; ".join(f"{n}.py:{line}: {why}" for n, line, why in found[:6]))
    else:
        detail = ""
    check("no module hands a `with ... as c:` block a connection that commits but "
          "never closes", not found, detail)


if __name__ == "__main__":
    for fn in (t_the_check_reads_the_backend_it_thinks_it_does,
               t_the_check_catches_the_old_shape,
               t_the_check_sees_the_three_modules_at_all,
               t_the_legitimate_shapes_in_this_repo_are_not_flagged,
               t_exactly_one_module_owns_the_closing_connection,
               t_the_three_modules_share_it,
               t_no_shipped_module_hands_a_with_block_an_unclosed_connection):
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
