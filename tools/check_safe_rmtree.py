#!/usr/bin/env python3
"""Refuse a `shutil.rmtree(...)` that is not provably inside the temp folder.

    py -3 tools/check_safe_rmtree.py            # the repository
    py -3 tools/check_safe_rmtree.py --root DIR # a tree to check (the tests)
    py -3 tools/check_safe_rmtree.py -v         # also print the sites it proved

WHY THIS EXISTS, AND WHY IT IS AN AST CHECK AND NOT A GREP.

On 2026-11-27 a lane wiped this entire checkout: it built a cleanup path out of
`Path("")`, and `Path("")` is `Path(".")` - the working directory - so
`shutil.rmtree(Path(""))` deleted the repository it was running in. The same
class of accident is one typo away in a hundred places here, because most of
these suites create their own scratch folders and then delete them.

A text search cannot see this class. It cannot tell a call from a comment, it
cannot tell which `root` a line means, and it cannot follow `P = Path("")` two
lines up. So this reads each file's syntax tree and answers one question about
every `shutil.rmtree(...)` argument: is this expression PROVABLY a path inside
`tempfile.gettempdir()`?

WHAT IT REFUSES (the shapes the incident and this project's own suites make
possible):

  * `rmtree("")` - an empty string, which every path library treats as `.`.
  * `rmtree(".")`, `rmtree("..")`, `rmtree("build")` - a relative path resolves
    against the working directory, which is the checkout when a suite is run
    from here.
  * `rmtree(<the repo root>)` - a literal, or anything derived from `__file__`
    (the checkout) or `Path.cwd()` / `os.getcwd()`.
  * `rmtree(<the home directory>)` - `Path.home()`, `os.path.expanduser("~")`,
    `$HOME` / `%USERPROFILE%`.
  * `rmtree(<an absolute path outside the temp folder>)`.
  * `rmtree(<a bare variable or call>)` that is not traceable to
    `tempfile.mkdtemp()` / `gettempdir()` / `TemporaryDirectory` - "unguarded".
  * a path that CLIMBS: `rmtree(TMP / "..")`, `rmtree(TMP.parent)`.

WHAT IT ACCEPTS, because it is provable: `tempfile.mkdtemp(...)` (with no `dir=`,
or a `dir=` that is itself confined), `tempfile.gettempdir()`, a
`tempfile.TemporaryDirectory()` used with `as`, `str()` / `Path()` of a confined
value, `os.path.join(...)` / `/` / `.joinpath(...)` with a confined first part
and safe relative segments, and a LOCAL HELPER whose every `return` is one of
those (`def tmpdir(): return Path(tempfile.mkdtemp())`). It knows the two import
spellings (`import shutil as sh`, `from shutil import rmtree as rm`) and it also
checks `addCleanup(shutil.rmtree, path)` - the same deletion handed to unittest
instead of called.

THE ALLOWLIST IS EXPLICIT AND NEVER SILENT. Some calls cannot be proved by this
analysis (a path handed in from a harness module, a fixture that created its own
folder elsewhere) and are not dangerous either: the argument is a unique
`mkdtemp()` child even if the call that produced it is out of reach. Those are
listed entry by entry below with ONE reason each, keyed by
`(file, enclosing function, argument text)`. An entry that no longer matches a
flagged site is an ERROR, not a leftover: the allowlist cannot rot into a blanket
excuse. `backend/test_check_safe_rmtree.py` proves every refusal above, the
`Path("")` case specifically, that a confined site passes, that a comment
mentioning `rmtree` is not a call, and that this tree is clean.

WHAT IT DOES NOT CLAIM. An alias assigned somewhere else
(`rm = shutil.rmtree; rm(p)`) and a wrapper defined in another module are out of
reach; the scan is `tools/**/*.py` plus `backend/test_*.py`, which is where the
project's own scratch cleanup lives. A file that will not parse is a FAILURE: a
path nobody looked at is not a pass. That is the same rule as
`tools/check_vacuous_checks.py`.
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
import tempfile
from pathlib import Path

#: The repository this checker lives in. Only used to name "the repo root" in a
#: reason and to decide whether the allowlist below applies (`--root` tests run
#: against throwaway trees, where it must not).
REPO = Path(__file__).resolve().parent.parent

#: The temp folder every accepted path must be inside, resolved once.
TEMP = Path(tempfile.gettempdir()).resolve()

#: What is scanned: every `.py` under `tools/`, plus `backend/test_*.py`.
TOOLS_DIR = "tools"
TEST_GLOB = "test_*.py"
BACKEND_DIR = "backend"

#: The allowlist. `(path relative to the scanned root, enclosing function or
#: "<module>", the argument's source text)` -> ONE line saying why this call is
#: safe even though the checker cannot prove it. Every entry must still match a
#: flagged site, and every flagged site must either be fixed, be provably
#: confined, or be listed here; `backend/test_check_safe_rmtree.py` asserts that
#: every entry has a reason.
ALLOWLIST: dict[tuple, str] = {}

CONFINED, DANGER, UNKNOWN = "confined", "danger", "unknown"


def _verdict(kind: str, reason: str = "") -> tuple:
    return (kind, reason)


def _qname(node: ast.AST) -> str:
    """The dotted source name of a Name/Attribute expression, or ""."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _qname(node.value)
        return f"{base}.{node.attr}" if base else ""
    return ""


def _imports(tree: ast.Module) -> dict:
    """local name -> the fully qualified name it stands for.

    Handles `import shutil as sh` (sh -> shutil), `import pathlib` (pathlib),
    `from tempfile import mkdtemp as mk` (mk -> tempfile.mkdtemp) and the plain
    forms. Attributes are then resolved through this map by `_full`.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
                else:
                    root = alias.name.split(".")[0]
                    aliases[root] = root
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _full(node: ast.AST, aliases: dict) -> str:
    """`_qname`, with the leading import alias replaced by its full name."""
    name = _qname(node)
    if not name:
        return ""
    head, dot, rest = name.partition(".")
    resolved = aliases.get(head, head)
    return f"{resolved}.{rest}" if dot else resolved


# ---------------------------------------------------------------------------
# Dangerous anchors: expressions that are outside temp no matter what follows.
# ---------------------------------------------------------------------------

HOME_VARS = ("HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH")


def _is_literal(node: ast.AST, value=None) -> bool:
    return (isinstance(node, ast.Constant)
            and (value is None or node.value == value))


def _anchor(node: ast.AST, aliases: dict) -> str:
    """Why this expression is outside the temp folder by construction, or "".

    Checked over the WHOLE expression: `Path(__file__).parent / "x"` and
    `str(Path.home())` are dangerous for what they contain, not only for their
    outermost call.
    """
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id == "__file__":
            return ("derived from __file__ - a path inside the checkout, not the "
                    "temp folder")
        if isinstance(sub, ast.Call):
            name = _full(sub.func, aliases)
            if name in ("os.getcwd", "pathlib.Path.cwd", "pathlib.Path.home",
                        "pathlib.PurePath.cwd", "pathlib.PurePath.home"):
                return ("the working directory" if name.endswith(".cwd")
                        else "the home directory")
            if name == "os.path.expanduser" and sub.args and _is_literal(sub.args[0]):
                text = str(sub.args[0].value)
                if text == "~" or text.startswith(("~/", "~\\")):
                    return "the home directory"
            if name == "os.environ.get" and sub.args and _is_literal(sub.args[0]):
                if str(sub.args[0].value).upper() in HOME_VARS:
                    return "the home directory"
        if isinstance(sub, ast.Subscript):
            if _full(sub.value, aliases) == "os.environ":
                key = sub.slice
                if (isinstance(key, ast.Constant)
                        and str(key.value).upper() in HOME_VARS):
                    return "the home directory"
    return ""


def _absolute_reason(path: Path) -> str:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    if resolved == REPO:
        return "this repository's root"
    try:
        if resolved == Path.home().resolve():
            return "the home directory"
    except RuntimeError:  # a home directory that cannot be resolved
        pass
    try:
        if resolved == TEMP or resolved.is_relative_to(TEMP):
            return ""
    except (OSError, ValueError):
        pass
    return f"the absolute path {str(path)!r}, outside the temp folder"


def _literal_reason(text: str) -> str:
    """Why a bare string constant is outside temp, or "" when it is inside."""
    if text == "":
        return "an empty string, which is '.' - the working directory"
    normalized = os.path.normpath(text)
    if normalized == os.curdir:
        return "'.' - the working directory"
    if normalized == os.pardir:
        return "'..' - the parent of the working directory"
    if normalized.startswith(os.pardir + os.sep) or normalized.startswith("../"):
        return "a path that climbs out of the working directory"
    candidate = Path(text)
    if candidate.is_absolute():
        return _absolute_reason(candidate)
    # A bare relative path is resolved against the working directory, which is
    # the checkout whenever a person or a job runs a suite from here.
    return (f"the relative path {text!r}, which resolves against the working "
            f"directory (the checkout)")


#: Calls whose result is a token with no path separator in it, so it is a safe
#: RELATIVE segment inside a path join (`TMP / f"run-{os.getpid()}"`). They are
#: here by name, not as a general "any call is fine": a general rule would let
#: `TMP / user_name` through, and `user_name` can be `..`.
SAFE_TOKEN_CALLS = ("os.getpid", "time.time_ns", "secrets.token_hex",
                    "secrets.token_urlsafe", "uuid.uuid4")


def _safe_segment(node: ast.AST, aliases: dict) -> bool | None:
    """True when this is a safe RELATIVE path segment for a join, None when the
    checker cannot tell. `""` is harmless in `Path(a) / ""`; `".."`, an absolute
    segment and a segment that climbs are not."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        text = node.value
        if text.startswith(("/", "\\")) or Path(text).is_absolute():
            return False
        parts = [p for p in text.replace("\\", "/").split("/")
                 if p not in ("", ".")]
        if any(p == ".." for p in parts):
            return False
        return True
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        left = _safe_segment(node.left, aliases)
        right = _safe_segment(node.right, aliases)
        if left is False or right is False:
            return False
        return True if left is True and right is True else None
    if isinstance(node, ast.JoinedStr):
        answer = True
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                piece = _safe_segment(value, aliases)
            elif isinstance(value, ast.FormattedValue):
                piece = _safe_segment(value.value, aliases)
            else:
                piece = None
            if piece is False:
                return False
            if piece is None:
                answer = None
        return answer
    if isinstance(node, ast.Call):
        name = _full(node.func, aliases)
        if name in SAFE_TOKEN_CALLS:
            return True
        if name == "str" and len(node.args) == 1:
            return _safe_segment(node.args[0], aliases)
    return None


# ---------------------------------------------------------------------------
# The per-file analysis
# ---------------------------------------------------------------------------

class FileAnalysis:
    """Everything one file's tree can tell this checker, in one place."""

    def __init__(self, tree: ast.Module):
        self.aliases = _imports(tree)
        #: fact key -> list of (value expression, scope it was read in, class)
        self.assignments: dict[tuple, list] = {}
        #: scope -> (list of return expressions, class or "")
        self.returns: dict[str, tuple] = {}
        #: keys the syntax itself proves confined (`with TemporaryDirectory() as d`)
        self.direct: dict[tuple, tuple] = {}
        #: keys a loop draws from a confined folder (`for child in TMP.iterdir()`)
        self.contained: dict[tuple, tuple] = {}
        #: (node, argument expression, scope, cls, how)
        self.sites: list[tuple] = []
        self._walk_body(tree.body, scope="", cls="")

    # -- collection ---------------------------------------------------------

    def _record(self, target: ast.AST, value: ast.AST, scope: str, cls: str):
        for key, sc, cl in self._targets(target, scope, cls):
            self.assignments.setdefault(key, []).append((value, sc, cl))

    def _targets(self, target: ast.AST, scope: str, cls: str) -> list[tuple]:
        """The fact key(s) a plain assignment target writes."""
        keys = []
        if isinstance(target, ast.Name):
            if scope:
                keys.append((("local", scope, target.id), scope, cls))
            else:
                keys.append((("module", target.id), scope, cls))
        elif (isinstance(target, ast.Attribute) and cls
              and isinstance(target.value, ast.Name)
              and target.value.id == "self"):
            keys.append((("attr", cls, target.attr), scope, cls))
        return keys

    def _walk_body(self, body, scope: str, cls: str):
        for node in body:
            if isinstance(node, ast.ClassDef):
                inner = f"{scope}.{node.name}" if scope else node.name
                self._walk_body(node.body, scope=inner, cls=node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = f"{scope}.{node.name}" if scope else node.name
                self.returns[inner] = (self._returns(node), cls)
                self._walk_body(node.body, scope=inner, cls=cls)
                # Decorators and defaults are evaluated in the OUTER scope.
                for extra in list(node.decorator_list) + list(node.args.defaults):
                    self._walk_expr(extra, scope, cls)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if (isinstance(target, (ast.Tuple, ast.List))
                            and isinstance(node.value, ast.Call)):
                        self._unpack(target, node.value, scope, cls)
                    else:
                        self._record(target, node.value, scope, cls)
                self._walk_expr(node.value, scope, cls)
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                self._record(node.target, node.value, scope, cls)
                self._walk_expr(node.value, scope, cls)
            elif isinstance(node, ast.For):
                self._walk_expr(node.iter, scope, cls)
                base = self._contained_base(node.iter)
                if base is not None:
                    for key, sc, cl in self._targets(node.target, scope, cls):
                        self.contained[key] = (base, sc, cl)
                self._walk_body(node.body, scope, cls)
                self._walk_body(node.orelse, scope, cls)
            elif isinstance(node, ast.With):
                for item in node.items:
                    self._walk_expr(item.context_expr, scope, cls)
                    if item.optional_vars is None:
                        continue
                    context = item.context_expr
                    if (isinstance(context, ast.Call)
                            and _full(context.func, self.aliases)
                            == "tempfile.TemporaryDirectory"
                            and isinstance(item.optional_vars, ast.Name)):
                        self.direct[("local", scope, item.optional_vars.id)] = (
                            _verdict(CONFINED))
                    else:
                        self._record(item.optional_vars, context, scope, cls)
                self._walk_body(node.body, scope, cls)
            elif isinstance(node, ast.stmt):
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, ast.stmt):
                        self._walk_body([child], scope, cls)
                    elif isinstance(child, ast.expr):
                        self._walk_expr(child, scope, cls)

    def _unpack(self, target: ast.AST, value: ast.Call, scope: str, cls: str):
        """`a, b = helper()` where helper's one return is a tuple: place each
        element by position, in the helper's own scope. A helper that returns
        `(s, Path(tempfile.mkdtemp()))` proves `b` and says nothing about `a`."""
        helper = self._helper(_full(value.func, self.aliases), scope)
        if helper is None:
            return
        returns, helper_cls = self.returns[helper]
        if len(returns) != 1 or not isinstance(returns[0], (ast.Tuple, ast.List)):
            return
        elements = returns[0].elts
        if len(elements) != len(target.elts):
            return
        for sub_target, expr in zip(target.elts, elements):
            for key, _sc, _cl in self._targets(sub_target, scope, cls):
                self.assignments.setdefault(key, []).append(
                    (expr, helper, helper_cls))

    def _contained_base(self, expr: ast.AST):
        """The confined folder a loop's items come from, or None.

        `for child in VAULT.iterdir()` and `.glob(...)` yield paths directly
        inside VAULT, so if VAULT is inside temp every child is too. `list()`,
        `sorted()` and `tuple()` around it change nothing. `os.listdir` is NOT
        here: it yields names, not paths.
        """
        if not isinstance(expr, ast.Call):
            return None
        name = _full(expr.func, self.aliases)
        if name in ("list", "sorted", "tuple") and expr.args:
            return self._contained_base(expr.args[0])
        if (isinstance(expr.func, ast.Attribute)
                and expr.func.attr in ("iterdir", "glob", "rglob")):
            return expr.func.value
        return None

    def _returns(self, function: ast.AST) -> list:
        """The function's own `return` expressions, not a nested def's."""
        found = []

        def walk(node):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                      ast.ClassDef, ast.Lambda)):
                    continue
                if isinstance(child, ast.Return) and child.value is not None:
                    found.append(child.value)
                walk(child)

        walk(function)
        return found

    def _walk_expr(self, node: ast.AST, scope: str, cls: str):
        if isinstance(node, ast.Call) and _is_rmtree(node, self.aliases):
            argument = node.args[0] if node.args else None
            self.sites.append((node, argument, scope, cls, "rmtree"))
            if node.args:
                self._walk_expr(node.args[0], scope, cls)
            for keyword in node.keywords:
                self._walk_expr(keyword.value, scope, cls)
            return
        # The unittest shape: addCleanup(shutil.rmtree, path).
        if (isinstance(node, ast.Call)
                and _full(node.func, self.aliases).endswith(".addCleanup")
                and len(node.args) >= 2
                and _is_rmtree_ref(node.args[0], self.aliases)):
            self.sites.append((node, node.args[1], scope, cls, "addCleanup"))
        if isinstance(node, (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            return
        for child in ast.iter_child_nodes(node):
            self._walk_expr(child, scope, cls)

    # -- proof --------------------------------------------------------------

    def verdict(self, expr: ast.AST | None, scope: str, cls: str,
                facts: dict, seen: tuple = ()) -> tuple:
        if expr is None:
            return _verdict(UNKNOWN, "a call with no path argument")
        anchor = _anchor(expr, self.aliases)
        if anchor:
            return _verdict(DANGER, anchor)
        if isinstance(expr, ast.Constant):
            if isinstance(expr.value, str):
                reason = _literal_reason(expr.value)
                if reason:
                    return _verdict(DANGER, reason)
                return _verdict(CONFINED)
            return _verdict(UNKNOWN, "not a path")
        if isinstance(expr, ast.Name):
            found = self._lookup(expr.id, scope, facts)
            if found is not None:
                return found
            return _verdict(UNKNOWN,
                            f"the variable {expr.id!r}, which the checker cannot "
                            f"trace to the temp folder")
        if isinstance(expr, ast.Attribute):
            if (expr.attr == "name"
                    and isinstance(expr.value, ast.Call)
                    and _full(expr.value.func, self.aliases)
                    == "tempfile.TemporaryDirectory"):
                return _verdict(CONFINED)
            if expr.attr == "parent":
                return _verdict(UNKNOWN,
                                "a parent directory, so it may be the temp folder "
                                "itself or above it")
            if expr.attr in ("resolve", "absolute", "expanduser"):
                return self.verdict(expr.value, scope, cls, facts, seen)
            if (isinstance(expr.value, ast.Name) and expr.value.id == "self"
                    and cls):
                found = facts.get(("attr", cls, expr.attr))
                if found is not None:
                    return found
                return _verdict(UNKNOWN,
                                f"the attribute self.{expr.attr}, which the checker "
                                f"cannot trace to the temp folder")
            return _verdict(UNKNOWN,
                            f"the attribute {_qname(expr)}, which the checker "
                            f"cannot trace to the temp folder")
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
            return self._join([expr.left, expr.right], scope, cls, facts, seen)
        if isinstance(expr, ast.Call):
            return self._call(expr, scope, cls, facts, seen)
        if isinstance(expr, ast.IfExp):
            left = self.verdict(expr.body, scope, cls, facts, seen)
            right = self.verdict(expr.orelse, scope, cls, facts, seen)
            if left[0] == DANGER:
                return left
            if right[0] == DANGER:
                return right
            if left[0] == CONFINED and right[0] == CONFINED:
                return _verdict(CONFINED)
            return _verdict(UNKNOWN, "a conditional path")
        if isinstance(expr, ast.JoinedStr):
            parts: list[ast.AST] = []
            for value in expr.values:
                if isinstance(value, ast.Constant):
                    parts.append(value)
                elif isinstance(value, ast.FormattedValue):
                    parts.append(value.value)
            if parts:
                return self._join(parts, scope, cls, facts, seen)
        if isinstance(expr, ast.Subscript):
            return _verdict(UNKNOWN, "a value read out of a mapping")
        return _verdict(UNKNOWN,
                        f"the expression {ast.unparse(expr)[:80]!r}, which the "
                        f"checker cannot trace")

    def _lookup(self, name: str, scope: str, facts: dict):
        parts = scope.split(".") if scope else []
        for cut in range(len(parts), -1, -1):
            key = ("local", ".".join(parts[:cut]), name)
            if key in facts:
                return facts[key]
        return facts.get(("module", name))

    def _expand(self, parts) -> list:
        """Flatten an f-string into the path pieces it is built from, so a
        literal PREFIX of an f-string is a segment of the join rather than a
        standalone relative path."""
        out: list = []
        for part in parts:
            if isinstance(part, ast.JoinedStr):
                for value in part.values:
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        out.append(value)
                    elif isinstance(value, ast.FormattedValue):
                        out.append(value.value)
            else:
                out.append(part)
        return out

    def _join(self, parts, scope, cls, facts, seen) -> tuple:
        parts = self._expand(parts)
        first = self.verdict(parts[0], scope, cls, facts, seen)
        if first[0] != CONFINED:
            if first[0] == DANGER:
                return first
            return _verdict(UNKNOWN,
                            "a path whose first part is not provably in the temp "
                            "folder")
        for part in parts[1:]:
            safe = _safe_segment(part, self.aliases)
            if safe is True:
                continue
            if safe is False:
                return _verdict(DANGER,
                                "joined with a segment that leaves the temp folder")
            verdict = self.verdict(part, scope, cls, facts, seen)
            if verdict[0] == CONFINED:
                continue
            if verdict[0] == DANGER:
                return verdict
            return _verdict(UNKNOWN,
                            "a path joined with a part the checker cannot prove "
                            "is a relative name")
        return _verdict(CONFINED)

    def _call(self, node: ast.Call, scope: str, cls: str, facts, seen) -> tuple:
        name = _full(node.func, self.aliases)
        if name in ("tempfile.mkdtemp", "tempfile.mktemp"):
            for keyword in node.keywords:
                if keyword.arg == "dir":
                    inner = self.verdict(keyword.value, scope, cls, facts, seen)
                    if inner[0] != CONFINED:
                        if inner[0] == DANGER:
                            return inner
                        return _verdict(
                            UNKNOWN,
                            "mkdtemp(dir=...) in a folder the checker cannot "
                            "prove is the temp folder")
            return _verdict(CONFINED)
        if name == "tempfile.gettempdir":
            return _verdict(CONFINED)
        if name in ("str", "os.fspath", "pathlib.Path", "pathlib.PurePath",
                    "pathlib.PosixPath", "pathlib.WindowsPath"):
            if not node.args:
                return _verdict(DANGER, "Path() with no argument, which is '.'")
            return self._join(list(node.args), scope, cls, facts, seen)
        if name == "os.path.join":
            if not node.args:
                return _verdict(UNKNOWN, "os.path.join() with no argument")
            return self._join(list(node.args), scope, cls, facts, seen)
        helper = self._helper(name, scope)
        if helper is not None and helper not in seen:
            returns, helper_cls = self.returns[helper]
            if not returns:
                return _verdict(UNKNOWN, f"{helper}() never returns a path")
            answers = [self.verdict(expr, helper, helper_cls, facts,
                                    seen + (helper,)) for expr in returns]
            if any(kind == DANGER for kind, _ in answers):
                return next(answer for answer in answers if answer[0] == DANGER)
            if all(kind == CONFINED for kind, _ in answers):
                return _verdict(CONFINED)
            return _verdict(UNKNOWN, f"the value {helper}() returns")
        return _verdict(UNKNOWN,
                        f"the value {ast.unparse(node)[:80]!r}, which the checker "
                        f"cannot trace to the temp folder")

    def _helper(self, name: str, scope: str):
        """A local function whose every return this file can see, or None."""
        parts = scope.split(".") if scope else []
        for cut in range(len(parts), -1, -1):
            candidate = ".".join(parts[:cut] + [name]) if parts[:cut] else name
            if candidate in self.returns:
                return candidate
        return None

    # -- the fixpoint over names and attributes -----------------------------

    def facts(self) -> dict:
        facts = dict(self.direct)
        for _ in range(12):
            changed = False
            for key, values in self.assignments.items():
                answers = [self.verdict(expr, scope, cls, facts)
                           for expr, scope, cls in values]
                if any(kind == DANGER for kind, _ in answers):
                    answer = next(a for a in answers if a[0] == DANGER)
                elif all(kind == CONFINED for kind, _ in answers):
                    answer = _verdict(CONFINED)
                else:
                    continue
                if facts.get(key) != answer:
                    facts[key] = answer
                    changed = True
            for key, (base, scope, cls) in self.contained.items():
                verdict = self.verdict(base, scope, cls, facts)
                if verdict[0] == CONFINED and facts.get(key) != _verdict(CONFINED):
                    facts[key] = _verdict(CONFINED)
                    changed = True
            if not changed:
                break
        return facts


def _is_rmtree(node: ast.Call, aliases: dict) -> bool:
    """`shutil.rmtree(...)`, however it was imported or reached."""
    return _full(node.func, aliases).endswith("shutil.rmtree")


def _is_rmtree_ref(node: ast.AST, aliases: dict) -> bool:
    """The bare `shutil.rmtree` handed to something else (addCleanup)."""
    return _full(node, aliases).endswith("shutil.rmtree")


# ---------------------------------------------------------------------------
# Running the check
# ---------------------------------------------------------------------------

def targets(root: Path) -> list[Path]:
    found = sorted(path for path in (root / TOOLS_DIR).rglob("*.py"))
    found += sorted(path for path in (root / BACKEND_DIR).glob(TEST_GLOB))
    return found


def scan(root: Path, verbose: bool = False) -> tuple[list, list, list, int, int]:
    """(flagged, allowlisted, confined, site_count, file_count)."""
    flagged, allowed, confined = [], [], []
    seen_sites = 0
    files = targets(root)
    use_allowlist = root.resolve() == REPO
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            flagged.append((rel, 0, "<file>", rel, rel,
                            f"will not parse, so its call sites were never "
                            f"checked: {type(exc).__name__}: {exc}"))
            continue
        analysis = FileAnalysis(tree)
        if not analysis.sites:
            continue
        facts = analysis.facts()
        for node, argument, scope, cls, how in analysis.sites:
            seen_sites += 1
            text = ast.unparse(argument) if argument is not None else "<no argument>"
            call = ast.unparse(node)[:100]
            row = (rel, node.lineno, scope or "<module>", text, call)
            verdict = analysis.verdict(argument, scope, cls, facts)
            if verdict[0] == CONFINED:
                if verbose:
                    confined.append(row + (how,))
                continue
            reason = verdict[1] if verdict[0] == DANGER else (
                "not provably inside tempfile.gettempdir(): " + verdict[1])
            key = (rel, scope or "<module>", text)
            if use_allowlist and key in ALLOWLIST:
                allowed.append(row + (ALLOWLIST[key],))
            else:
                flagged.append(row + (reason,))
    if use_allowlist:
        matched = {(row[0], row[2], row[3]) for row in allowed}
        for key in ALLOWLIST:
            if key not in matched:
                flagged.append((key[0], 0, key[1], key[2], key[2],
                                "STALE allowlist entry: no flagged call matches "
                                "this (file, function, argument) any more - fix it "
                                "or remove the entry"))
    return flagged, allowed, confined, seen_sites, len(files)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Refuse a shutil.rmtree that is not provably inside "
                    "tempfile.gettempdir().")
    parser.add_argument("--root", default=str(REPO),
                        help="the tree to scan (default: this repository)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="also print each call site this checker proved")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if not (root / TOOLS_DIR).is_dir():
        print(f"FAIL  {root} has no {TOOLS_DIR}/ folder - nothing was scanned, "
              f"which is not a pass", file=sys.stderr)
        return 1
    flagged, allowed, confined, sites, files = scan(root, args.verbose)
    for rel, line, scope, text, call, reason in flagged:
        print(f"FAIL  {rel}:{line}  in {scope}(): {call}")
        print(f"        argument {text}")
        print(f"        {reason}")
    for rel, line, scope, text, call, reason in allowed:
        print(f"allow {rel}:{line}  in {scope}(): {call}")
        print(f"        allowlisted: {reason}")
    if args.verbose:
        for rel, line, scope, text, call, how in confined:
            print(f"ok    {rel}:{line}  {how}  {text}")
    print(f"\n{files} file(s) scanned, {sites} rmtree call site(s): "
          f"{sites - len(flagged) - len(allowed)} provably inside the temp "
          f"folder, {len(allowed)} allowlisted with a reason, "
          f"{len(flagged)} flagged.")
    if flagged:
        print("FAIL - every rmtree must be provably inside "
              "tempfile.gettempdir(), or fixed, or allowlisted with a reason.",
              file=sys.stderr)
        return 1
    print("PASS - no rmtree outside the temp folder.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
