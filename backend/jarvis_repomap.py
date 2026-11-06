"""jarvis_repomap.py - a READ-ONLY repository map: the files and symbols of one
project folder, ranked for a question and packed into a bounded block of text.

NEW MODULE, shipped whole. It is the first piece of "Jarvis as a project
worker" (the owner's approved design: a read-only repo map FIRST, before
project-scoped chat and staged diffs; the 2026-11-05 project-management audit,
section 5 item 2, and the decision `decisions.d/2026-11-05-project-repomap-
first.md`). It is MODEL-FREE: the ranking is deterministic arithmetic, so the
same tree and the same question give the same map, every time, with no model
call and no network.

WHAT A MAP IS, IN PLAIN WORDS
  Every project the owner registers can hold one folder. This module walks
  that folder, reads the NAMES of what is in it - classes, functions, methods,
  and the imports that tie files together - and writes a short list of the
  ones most likely to matter for the question being asked. It never shows a
  function's body. It is a table of contents, not a book.

WHERE IT MAY LOOK - the SAME boundary the files tool uses, not a copy of it
  * The folder must be on "Folders Jarvis may look in" (jarvis_documents.py),
    or inside one of those folders. That check is `jarvis_documents.
    allowed_path()` - THE one boundary the `my_files` tool already uses, so
    hidden folders, "never looks in" places, "Protected from Jarvis" items,
    reserved Windows names and links that lead outside are all refused by the
    existing code rather than by a second list here.
  * The project's own folder is checked the way `jarvis_projects.check_folder`
    checks it (a project's folder must already be on that list), and then
    EVERY file the walk would show is passed through `allowed_path()` again,
    with the project's folder as its root. A file that fails that check is
    never parsed and never appears.
  * An unlisted folder is REFUSED in one plain sentence, never guessed at,
    never walked and then filtered: see REFUSED below.
  * Symlinks are not followed (`os.walk(followlinks=False)` and a real-path
    test on every directory), hidden names (a leading ".") are skipped, and a
    small set of dependency/build folders (node_modules, target, dist, build,
    __pycache__, .venv, ...) is skipped even when a .gitignore forgets them -
    they are never source, and walking them is how a map becomes a crash.
  * `.gitignore` is honoured, per directory, the way git reads it: comments,
    blank lines, `!` negation (last match wins), a trailing "/" for a folder
    only, a leading "/" anchored to that folder, and a pattern with no "/" at
    all matching the name at any depth.

WHAT IT CAN DO, AND WHAT IT CANNOT
  * It WRITES NOTHING. There is no index file, no cache, no temp file: the
    walk is read-only and the answer is built in memory. (The files tool keeps
    a search index; this one deliberately keeps nothing.)
  * It runs no program, starts no child process, opens no socket and calls no
    model. Standard library only: ast, os, re, fnmatch, math, json, urllib.parse.
  * It raises no approval card of its own and adds no gate action. Reading is
    decided under `read_files_readonly`, the same line `file_read` and the
    `my_files` tool already use, and the `map` action rides on `my_files`.
  * Its result is OUTSIDE TEXT, labelled by jarvis_documents.mark_outside on
    the model's path, exactly like a file read.

THE RANKING FORMULA (this is the whole of it - nothing hidden, no model)
  Question words: the question is lower-cased, split on anything that is not a
  letter, digit or underscore, and every word of two or more letters that is
  not in STOP is kept (STOP is the little list of English filler words below).

  For one file, with M = the question words:
    symbol_match  = the number of DISTINCT question words that appear in the
                    name of a class, function or method this file declares
                    (case-insensitive, as part of the name: "route" matches
                    "parse_route" and "route_for_turn")
    path_match    = the number of DISTINCT question words that appear in the
                    file's own name or in a folder name above it
    import_match  = the number of DISTINCT question words that appear in the
                    import targets this file names
    meat          = log2(1 + the number of symbols this file declares)

  A file is MATCHED when symbol_match or path_match is above zero. Then:
    score = 12 * symbol_match
          +  6 * path_match
          +  2 * import_match
          +  4 * (1 if a MATCHED file imports this one)      # its dependency
          +  1 * (1 if this file imports a MATCHED file)      # a caller
          +  0.5 * meat

  So a file whose function names hold the question's words wins; a file whose
  name or folder holds them is next; a file the matched files depend on gets a
  real boost (that is the "import edges from matched files" the brief asks
  for); and a bigger file gets a small tie-break rather than winning outright.
  Import edges are matched on NAMES, not by resolving paths: an import is a
  string ("from x.y import z", `import "./util"`, `use crate::db`, `import
  a.b.C`), and the last identifier in it is looked up against the file stems
  in the same tree. That is conservative on purpose - a wrong edge costs one
  line of the map, a resolved-path guess could invent one.

  Ties are broken by the file's relative path (A to Z), so the order never
  depends on the walk's order or on the file system.

THE BUDGET
  A map is packed to at most `budget` tokens, and `budget` is clamped to
  TOKENS_MAX (2,000). Tokens are counted the way this project counts them
  everywhere - CHARS_PER_TOKEN = 3, `jarvis_agent.estimate_tokens`' pessimistic
  count, the same 3 characters a token `jarvis_documents.PART_TOKENS` uses - so
  the figure is comparable with every other budget in the backend. The default
  is TOKENS_DEFAULT (1,500), inside the 1,000-2,000 the design asks for.
  Packing is greedy: files are taken in rank order until the next one would
  overflow; a file that does not fit whole has its symbol lines trimmed to the
  ones that do; a single line too long to fit is clipped. Nothing is ever
  refused for being big - a huge file is either not parsed (over MAX_FILE_BYTES)
  or trimmed.

THE ROUTE (added to the project store's own table, not a second router)
  GET /api/projects/<id>/map?q=<the question>&tokens=<budget>
  `id` is a registered project (projects.db, jarvis_projects.py) and the
  folder mapped is that project's own folder. The answer is JSON:
    {"ok": true, "available": true, "project": {"id", "name"},
     "folder": {"path", "name"}, "question": str,
     "map": "<the packed text>", "tokens": int, "budget": int,
     "files": int, "files_seen": int, "symbols": int, "truncated": bool,
     "ranked": [{"path", "score", "symbols"}],   # the top few, explainable
     "outside_text": true}
  A project with no folder, an unknown project, or a folder that is no longer
  listed each answer with their own plain sentence and `ok: false`.

THE TOOL
  The `my_files` action `map` (jarvis_documents.run_tool hands it here):
  {"action": "map", "project": "<id>"} or {"action": "map", "path": "<a folder
  on the list>"}, with "words" as the question. It returns the same map as
  `map`, marked as outside text, plus the counts.

WHY IT IS NOT IN EITHER APP YET
  It is a PC read, reached through chat (the local model calls `my_files`) and
  through the JSON route an app will one day call. No screen is added in this
  slice: a repository map is read by the MODEL, not by the owner, and drawing
  one for a person is a different job (a tree view, not a token budget). That
  is written down in docs/ARCHITECTURE.md section 8 and classified in
  tools/check_parity.py, so the gap is a decision rather than an oversight.

THE HONEST LIMITS, said plainly
  * Python is parsed exactly (ast). JS/TS/Kotlin/Rust are read by a
    CONSERVATIVE line scan for signatures and imports: it finds the usual
    declarations and misses anything clever (a function made by a factory, a
    macro-generated impl). A miss costs a line of the map, never a wrong
    claim: everything printed is a line that was really there, at the line
    number given.
  * A file that is not valid UTF-8 is decoded with replacement characters; its
    signatures still show, its odd bytes read as U+FFFD and nothing else
    happens.
  * The ranking is a heuristic and is not measured against a model's idea of
    relevant: it is explainable, deterministic and cheap, which is the point.
"""
from __future__ import annotations

import ast
import fnmatch
import json
import math
import os
import re
from bisect import bisect_right
from urllib.parse import parse_qs

#: The `my_files` action this module answers (jarvis_documents.run_tool).
#:
#: Deliberately NOT spelled `..._ACTION`. `backend/test_card_words.py`,
#: `backend/test_card_short_words.py` and `backend/test_gate_names.py` each
#: scan every `backend/jarvis_*.py` for a module-level constant whose NAME
#: contains ACTION, and each then demands that the name resolve against the
#: LIVE gate (a plain phrase in `jarvis_card_words.TITLES`, a line in the live
#: `[autonomy.tiers]`, and so on) - because every such constant is a GATE
#: action. This one is not: no card is ever raised under `map`. Reading a map
#: asks the gate under `read_files_readonly`, exactly like `my_files`'s other
#: actions (`jarvis_documents.GATE_ACTION`), and `map` only reaches this module
#: THROUGH that tool. Calling it `ACTION` would claim a gate action that does
#: not exist and fail three suites for a reason that is not about this module.
#: Same shape, same reason, as `jarvis_task_lease.LEASE_GATE_NAME`.
MY_FILES_OP = "map"

#: The route, built on the project store's own table: /api/projects/<id>/map
#: (jarvis_projects.parse_route returns ("map", pid) for it).
PATH = "/api/projects"
ROUTE_SUFFIX = "/map"

#: Tokens are 3 characters here, the same pessimistic count jarvis_agent uses
#: (`estimate_tokens`) and the same one jarvis_documents.PART_TOKENS is built
#: from. It is deliberately not a real tokeniser: this is a budget, not a bill.
CHARS_PER_TOKEN = 3

#: The bound on one map, and the default it is packed to. The design asks for
#: a concise 1,000-2,000 token map; TOKENS_MAX is a hard ceiling, and a caller
#: asking for more than it gets it clipped back to it.
TOKENS_MAX = 2000
TOKENS_DEFAULT = 1500
TOKENS_MIN = 200

#: The walk's own bounds, so a pathological tree cannot hang a turn.
MAX_FILES_SEEN = 4000
MAX_SECONDS = 6.0
MAX_FILE_BYTES = 512 * 1024
MAX_SYMBOLS_PER_FILE = 40
MAX_SYMBOL_LINE = 116
#: Characters held back while packing so the "... N more files did not fit"
#: line always has room (about 45 tokens).
TAIL_RESERVE = 140

#: Folders that are never source, skipped even when no .gitignore says so:
#: walking them is how a map becomes a crash, and none of them holds a class
#: or a function the owner wrote.
SKIP_DIRS = frozenset({
    "node_modules", "target", "dist", "build", "out", "obj", "bin", "vendor",
    "__pycache__", ".venv", "venv", "env", ".git", ".hg", ".svn", ".idea",
    ".vs", ".next", ".nuxt", ".gradle", ".cache", "coverage", "htmlcov",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".dart_tool",
})

#: Filler words that carry no location signal in a question.
STOP = frozenset("""
a an and are as at be been by can could do does did for from get gets give has
have how i if in into is it its just like make me my of on or our please should
so some that the their them then there these they this to us use used using was
we were what when where which who why will with would you your
""".split())

#: The languages whose SIGNATURES this module reads. Python is parsed with ast;
#: the rest are a conservative line scan (see the module docstring's limits).
PY_SUFFIXES = (".py", ".pyw")
SCAN_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
                 ".kt", ".kts", ".rs", ".java")
#: Any other text file can still appear when its PATH matches the question; it
#: is listed with no symbols and is never read.
TEXT_SUFFIXES = (".md", ".txt", ".toml", ".cfg", ".ini", ".json", ".yml", ".yaml",
                 ".html", ".css", ".sql", ".sh", ".ps1", ".gradle", ".kts")

#: One plain sentence for a folder that is not on the owner's list. It is the
#: WHOLE refusal: the walk starts only after the boundary check passes.
REFUSED = ("That folder is not on \"Folders Jarvis may look in\", so Jarvis does not map it - "
           "the folder is added on the PC first, in Settings, Folders Jarvis may look in.")

#: A project's id is uuid4().hex in projects.db: 32 hex characters, no folder
#: separator, and never the name of a folder that exists - which is how the
#: tool tells "a project" and "a folder" apart in its ONE path argument.
_PROJECT_ID = re.compile(r"^[0-9a-fA-F]{16,64}$")

#: What the model is told a map is, for `describe` (the card's words, if the
#: owner ever sets reading files to ask).
WHAT = ("read the names of the files, classes and functions in {where}, to see which ones "
        "matter for a question. It lists names and signatures only, never what a function "
        "does, and nothing is changed or sent anywhere.")

# --------------------------------------------------------------------------
#   The words both halves use
# --------------------------------------------------------------------------


def _sentence(exc) -> str:
    s = str(exc).strip() or type(exc).__name__
    return s[:1].upper() + s[1:]


def estimate_tokens(text) -> int:
    """The project's own pessimistic token count, counted the way
    `jarvis_agent.estimate_tokens` counts a string: 3 characters a token, with
    the JSON framing it puts round one (the two quote characters, and one extra
    character for every line break, which JSON writes as a backslash and an n).

    Doing it exactly matters: the budget exists to bound what reaches the
    model, and the model's own count is that one - a map packed to 2,000 by a
    plainer count would arrive as rather more than 2,000.
    """
    if not isinstance(text, str) or not text:
        return 0
    return len(json.dumps(text, ensure_ascii=False)) // CHARS_PER_TOKEN


def budget_of(value) -> int:
    """A caller's token budget, clamped into [TOKENS_MIN, TOKENS_MAX]."""
    try:
        n = int(str(value).strip()) if not isinstance(value, bool) else 0
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        return TOKENS_DEFAULT
    return max(TOKENS_MIN, min(TOKENS_MAX, n))


def words_of(text) -> list:
    """The question's words: lower case, 2+ letters, filler dropped, in order,
    with duplicates removed so a repeated word cannot double a score."""
    out = []
    for w in re.split(r"[^0-9A-Za-z_]+", str(text or "").casefold()):
        if len(w) < 2 or w in STOP or w in out:
            continue
        out.append(w)
    return out


# --------------------------------------------------------------------------
#   The boundary - the SAME function the files tool uses
# --------------------------------------------------------------------------


def _documents():
    """jarvis_documents, or None when this backend does not ship it.

    A missing copy means there is no "Folders Jarvis may look in" list at all,
    so there is nothing this module may read: the caller refuses in words.
    """
    try:
        import jarvis_documents
        return jarvis_documents
    except Exception:                                       # noqa: BLE001
        return None


def _projects():
    try:
        import jarvis_projects
        return jarvis_projects
    except Exception:                                       # noqa: BLE001
        return None


# --------------------------------------------------------------------------
#   .gitignore - read the way git reads it, per directory
# --------------------------------------------------------------------------

_COMMENT = re.compile(r"(?<!\\)#.*$")


class _Rules:
    """The .gitignore rules that apply under one folder, and whether a name is
    ignored. Rules are (base, pattern, negate, dir_only); the LAST matching
    rule wins, which is git's own rule for a single directory's file."""

    __slots__ = ("rules",)

    def __init__(self, rules=None):
        self.rules = list(rules or ())

    def add(self, base: str, text: str) -> "_Rules":
        for raw in str(text or "").splitlines():
            line = raw.rstrip()
            if not line or line.startswith("#"):
                continue
            line = _COMMENT.sub("", line).strip()
            if not line:
                continue
            negate = line.startswith("!")
            if negate:
                line = line[1:]
            dir_only = line.endswith("/")
            if dir_only:
                line = line[:-1]
            if not line:
                continue
            self.rules.append((base, line, negate, dir_only))
        return self

    def ignored(self, full: str, is_dir: bool) -> bool:
        name = os.path.basename(full)
        out = False
        for base, pat, negate, dir_only in self.rules:
            if dir_only and not is_dir:
                # A folder-only rule also covers everything IN that folder;
                # the walk prunes the folder itself, which is what git does.
                continue
            rel = _rel(base, full)
            if rel is None:
                continue
            if "/" in pat:
                hit = fnmatch.fnmatchcase(rel, pat) or rel.startswith(pat + "/")
            else:
                hit = fnmatch.fnmatchcase(name, pat)
            if hit:
                out = not negate
        return out


def _rel(base: str, full: str):
    """`full` relative to `base`, forward slashes, or None when it is not
    under it (it then cannot be covered by that folder's rules)."""
    try:
        rel = os.path.relpath(full, base)
    except ValueError:      # different drives on Windows
        return None
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return None
    return rel.replace(os.sep, "/")


# --------------------------------------------------------------------------
#   Reading one file's NAMES - never its body
# --------------------------------------------------------------------------


def _py_sig(node) -> str:
    """(a, b=1, *args, **kw) from a def's arguments - names only, no defaults,
    so the line stays short and no value from the file is copied out."""
    try:
        a = node.args
        parts = [x.arg for x in getattr(a, "posonlyargs", [])]
        if getattr(a, "posonlyargs", []):
            parts.append("/")
        parts += [x.arg for x in a.args]
        if a.vararg:
            parts.append("*" + a.vararg.arg)
        elif a.kwonlyargs:
            parts.append("*")
        parts += [x.arg for x in a.kwonlyargs]
        if a.kwarg:
            parts.append("**" + a.kwarg.arg)
        return "(" + ", ".join(parts) + ")"
    except Exception:                                       # noqa: BLE001
        return "(...)"


def _py_facts(text: str) -> dict:
    """classes, functions, methods and imports of Python source, in line order.

    ast only parses: NOTHING in the file is run, imported or evaluated.
    """
    out = {"symbols": [], "imports": [], "exact": True}
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        out["exact"] = False
        out["symbols"], out["imports"] = _py_scan(text)
        return out
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = []
            for b in node.bases:
                if isinstance(b, ast.Name):
                    bases.append(b.id)
                elif isinstance(b, ast.Attribute):
                    bases.append(b.attr)
            out["symbols"].append(("class", node.name, node.lineno,
                                   "(" + ", ".join(bases) + ")" if bases else ""))
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out["symbols"].append(("def", sub.name, sub.lineno, _py_sig(sub)))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out["symbols"].append(("def", node.name, node.lineno, _py_sig(node)))
        elif isinstance(node, ast.Import):
            for a in node.names:
                out["imports"].append(a.name or "")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out["imports"].append(node.module)
                # `from app import router` imports the FILE `router`, which is
                # the edge that matters; the module alone ("app") is a folder.
                for a in node.names:
                    if a.name and a.name != "*":
                        out["imports"].append(f"{node.module}.{a.name}")
    return out


_PY_DEF = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+([A-Za-z_]\w*)[ \t]*\(([^)]*)\)",
                     re.MULTILINE)
_PY_CLASS = re.compile(r"^[ \t]*class[ \t]+([A-Za-z_]\w*)", re.MULTILINE)
_PY_IMP = re.compile(r"^[ \t]*(?:from[ \t]+([\w.]+)[ \t]+import|import[ \t]+([\w.]+))",
                     re.MULTILINE)


def _py_scan(text: str):
    """The fallback for Python that does not parse: declarations only, found by
    a line scan. Never guesses - a name printed is a name in the file."""
    starts = _line_starts(text)
    symbols = [("def", m.group(1), _line_of(starts, m.start()),
                "(" + m.group(2).strip() + ")" if m.group(2).strip() else "()")
               for m in _PY_DEF.finditer(text)]
    symbols += [("class", m.group(1), _line_of(starts, m.start()), "")
                for m in _PY_CLASS.finditer(text)]
    symbols.sort(key=lambda s: (s[2], s[1]))
    imports = [m.group(1) or m.group(2) for m in _PY_IMP.finditer(text)]
    return symbols, [i for i in imports if i]


def _line_starts(text: str) -> list:
    starts = [0]
    i = text.find("\n")
    while i != -1:
        starts.append(i + 1)
        i = text.find("\n", i + 1)
    return starts


def _line_of(starts: list, pos: int) -> int:
    return bisect_right(starts, pos)


#: (kind, pattern, group 1 is the name, group 2 is an optional argument list)
_JS = (
    ("class", re.compile(r"^[ \t]*(?:export[ \t]+(?:default[ \t]+)?)?(?:abstract[ \t]+)?"
                         r"class[ \t]+([A-Za-z_$][\w$]*)", re.MULTILINE), False),
    ("function", re.compile(r"^[ \t]*(?:export[ \t]+(?:default[ \t]+)?)?(?:async[ \t]+)?"
                            r"function[ \t]*\*?[ \t]*([A-Za-z_$][\w$]*)[ \t]*\(([^)]*)\)",
                            re.MULTILINE), True),
    ("const", re.compile(r"^[ \t]*(?:export[ \t]+)?const[ \t]+([A-Za-z_$][\w$]*)[ \t]*="
                         r"[ \t]*(?:async[ \t]*)?(?:function[ \t]*)?\(([^)]*)\)[ \t]*=>",
                         re.MULTILINE), True),
    ("interface", re.compile(r"^[ \t]*(?:export[ \t]+)?interface[ \t]+([A-Za-z_$][\w$]*)",
                             re.MULTILINE), False),
    ("type", re.compile(r"^[ \t]*(?:export[ \t]+)?type[ \t]+([A-Za-z_$][\w$]*)[ \t]*=",
                        re.MULTILINE), False),
)
_JS_IMPORT = re.compile(r"""(?:^|[;\s])(?:import[^;\n]*?from[ \t]*|require[ \t]*\([ \t]*)"""
                        r"""["']([^"']+)["']""", re.MULTILINE)

_KT = (
    ("class", re.compile(r"^[ \t]*(?:public[ \t]+|internal[ \t]+|private[ \t]+|protected[ \t]+)?"
                         r"(?:data[ \t]+|sealed[ \t]+|abstract[ \t]+|open[ \t]+|inner[ \t]+|"
                         r"enum[ \t]+|annotation[ \t]+)*class[ \t]+([A-Za-z_]\w*)",
                         re.MULTILINE), False),
    ("object", re.compile(r"^[ \t]*(?:public[ \t]+|internal[ \t]+|private[ \t]+)?"
                          r"(?:companion[ \t]+)?object[ \t]+([A-Za-z_]\w*)", re.MULTILINE), False),
    ("interface", re.compile(r"^[ \t]*(?:public[ \t]+|internal[ \t]+)?"
                             r"(?:fun[ \t]+)?interface[ \t]+([A-Za-z_]\w*)",
                             re.MULTILINE), False),
    ("fun", re.compile(r"^[ \t]*(?:public[ \t]+|internal[ \t]+|private[ \t]+|protected[ \t]+|"
                       r"suspend[ \t]+|inline[ \t]+|override[ \t]+|operator[ \t]+|"
                       r"open[ \t]+|tailrec[ \t]+)*fun[ \t]+(?:<[^>]*>[ \t]*)?"
                       r"(?:[A-Za-z_][\w.]*\.)?([A-Za-z_]\w*)[ \t]*\(([^)]*)\)",
                       re.MULTILINE), True),
)
_KT_IMPORT = re.compile(r"^[ \t]*import[ \t]+([\w.]+)", re.MULTILINE)

_RS = (
    ("fn", re.compile(r"^[ \t]*(?:pub(?:\([^)]*\))?[ \t]+)?(?:const[ \t]+)?(?:async[ \t]+)?"
                      r"(?:unsafe[ \t]+)?(?:extern[ \t]+\"[^\"]*\"[ \t]+)?fn[ \t]+"
                      r"([A-Za-z_]\w*)[ \t]*\(([^)]*)\)", re.MULTILINE), True),
    ("struct", re.compile(r"^[ \t]*(?:pub(?:\([^)]*\))?[ \t]+)?struct[ \t]+([A-Za-z_]\w*)",
                          re.MULTILINE), False),
    ("enum", re.compile(r"^[ \t]*(?:pub(?:\([^)]*\))?[ \t]+)?enum[ \t]+([A-Za-z_]\w*)",
                        re.MULTILINE), False),
    ("trait", re.compile(r"^[ \t]*(?:pub(?:\([^)]*\))?[ \t]+)?(?:unsafe[ \t]+)?trait[ \t]+"
                         r"([A-Za-z_]\w*)", re.MULTILINE), False),
    ("impl", re.compile(r"^[ \t]*impl(?:<[^>]*>)?[ \t]+(?:[\w:<>, &']+[ \t]+for[ \t]+)?"
                        r"([A-Za-z_]\w*)", re.MULTILINE), False),
)
_RS_IMPORT = re.compile(r"^[ \t]*(?:pub[ \t]+)?(?:use[ \t]+([\w:]+)|mod[ \t]+([A-Za-z_]\w*)[ \t]*;)",
                        re.MULTILINE)

#: java is scanned with the JavaScript patterns plus its own import line: it is
#: close enough in shape (class, interface, and `import a.b.C;`) that a second
#: table would be a copy for no gain.
_JAVA_IMPORT = re.compile(r"^[ \t]*import[ \t]+(?:static[ \t]+)?([\w.]+)", re.MULTILINE)


def _scan_facts(text: str, ext: str) -> dict:
    """Signatures and imports of JS/TS/Kotlin/Rust/Java, by a conservative line
    scan. No parsing, no execution: a name printed here was really declared."""
    out = {"symbols": [], "imports": [], "exact": False}
    table = _JS
    imps = _JS_IMPORT
    if ext in (".kt", ".kts"):
        table, imps = _KT, _KT_IMPORT
    elif ext == ".rs":
        table, imps = _RS, _RS_IMPORT
    elif ext == ".java":
        table, imps = _JS, _JAVA_IMPORT
    starts = _line_starts(text)
    seen = set()
    for kind, pat, takes_args in table:
        for m in pat.finditer(text):
            name = m.group(1)
            key = (kind, name, m.start())
            if key in seen:
                continue
            seen.add(key)
            args = ""
            if takes_args and m.lastindex and m.lastindex >= 2:
                raw = (m.group(2) or "").strip()
                if raw:
                    args = "(" + raw + ")"
                else:
                    args = "()"
            out["symbols"].append((kind, name, _line_of(starts, m.start()), args))
    out["symbols"].sort(key=lambda s: (s[2], s[1]))
    imports = [m.group(1) or (m.group(2) if (m.lastindex or 0) >= 2 else "")
               for m in imps.finditer(text)]
    out["imports"] = [i for i in imports if i]
    return out


# --------------------------------------------------------------------------
#   The walk - bounded, .gitignore-aware, and behind the boundary
# --------------------------------------------------------------------------


def _walk(root: str, *, clock) -> tuple:
    """Every file under `root` this module may show: ([(full, rel)], why).

    `why` is "" or the bound that stopped the walk early, in words. Every file
    returned has passed `jarvis_documents.allowed_path(full, [root])` - the
    files tool's own boundary - a moment before it was added.
    """
    docs = _documents()
    started = clock()
    found = []
    seen = 0
    stopped = ""

    def visit(folder: str, rel_dir: str, rules: _Rules) -> bool:
        """False stops the whole walk."""
        nonlocal seen, stopped
        if clock() - started > MAX_SECONDS:
            stopped = f"the walk reached its {MAX_SECONDS:g} second limit"
            return False
        here = os.path.join(folder, ".gitignore")
        if os.path.isfile(here):
            try:
                with open(here, "rb") as fh:
                    rules = rules.add(os.path.dirname(here),
                                      fh.read(MAX_FILE_BYTES).decode("utf-8", "replace"))
            except OSError:
                pass
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            return True
        for name in names:
            full = os.path.join(folder, name)
            shown = f"{rel_dir}/{name}" if rel_dir else name
            try:
                is_dir = os.path.isdir(full)
            except OSError:
                continue
            if is_dir:
                if name.startswith(".") or name.casefold() in SKIP_DIRS:
                    continue
                if rules.ignored(full, True):
                    continue
                # A link or junction that leads out of the folder is not
                # entered: the boundary below would refuse its files one by
                # one, and not walking it at all is the same answer, cheaper.
                real = os.path.realpath(full)
                if docs is not None and not docs._inside(os.path.realpath(root), real):
                    continue
                if docs is not None and docs.protected(full):
                    continue
                if not visit(full, shown, rules):
                    return False
                continue
            if name.startswith("."):
                continue
            if rules.ignored(full, False):
                continue
            seen += 1
            if seen > MAX_FILES_SEEN:
                stopped = f"it looked at {MAX_FILES_SEEN:,} files"
                return False
            if docs is None:
                stopped = "the folders module is not installed on this backend"
                return False
            if docs.allowed_path(full, [root]) is None:
                # THE BOUNDARY, per file: not inside the folder once links are
                # followed, or a hidden / protected / reserved place.
                continue
            found.append((full, shown))
        return True

    visit(root, "", _Rules())
    return found, stopped


# --------------------------------------------------------------------------
#   Ranking - the formula in the module docstring, and nothing else
# --------------------------------------------------------------------------


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0].casefold()


def _import_words(target: str) -> list:
    """The identifiers an import target names, last part first: "a.b.C" gives
    ["c", "b", "a"]; "./util/x.js" gives ["x", "js", "util"]."""
    return [w for w in re.split(r"[^0-9A-Za-z_$]+", str(target or "").casefold()) if w]


def _score(files: list, question_words: list) -> None:
    """Set `score` on every file row, in place. See the module docstring."""
    want = set(question_words)
    stems = {}
    for row in files:
        stems.setdefault(_stem(row["path"]), []).append(row)
    for row in files:
        sym_hits = set()
        for kind, name, _line, _sig in row["symbols"]:
            low = name.casefold()
            for w in want:
                if w in low:
                    sym_hits.add(w)
        path_hits = set()
        low_path = row["path"].casefold().replace("\\", "/")
        for w in want:
            if w in low_path:
                path_hits.add(w)
        imp_hits = set()
        for target in row["imports"]:
            for w in want:
                if w in str(target).casefold():
                    imp_hits.add(w)
        row["symbol_match"] = len(sym_hits)
        row["path_match"] = len(path_hits)
        row["import_match"] = len(imp_hits)
        row["matched"] = bool(sym_hits or path_hits)
        row["edges_out"] = []
        for target in row["imports"]:
            names = _import_words(target)
            hit = None
            for n in names:
                if n in stems:
                    hit = n
                    break
            if hit is not None:
                for other in stems[hit]:
                    if other is not row:
                        row["edges_out"].append(other)
    for row in files:
        for other in row["edges_out"]:
            other.setdefault("edges_in", []).append(row)
    for row in files:
        edge_in = 1 if any(a["matched"] for a in row.get("edges_in") or ()) else 0
        edge_out = 1 if any(b["matched"] for b in row.get("edges_out") or ()) else 0
        row["score"] = round(
            12 * row["symbol_match"]
            + 6 * row["path_match"]
            + 2 * row["import_match"]
            + 4 * edge_in
            + 1 * edge_out
            + 0.5 * math.log2(1 + len(row["symbols"])), 2)


def _facts(full: str, ext: str) -> dict:
    """The names one file declares. Reads at most MAX_FILE_BYTES; a file over
    that is listed by its path alone and never read (never crashed on)."""
    try:
        size = os.path.getsize(full)
    except OSError:
        return {"symbols": [], "imports": [], "exact": True, "note": "unreadable"}
    if size > MAX_FILE_BYTES:
        return {"symbols": [], "imports": [], "exact": True, "note": "large file, not read"}
    try:
        with open(full, "rb") as fh:
            raw = fh.read(MAX_FILE_BYTES)
    except OSError:
        return {"symbols": [], "imports": [], "exact": True, "note": "unreadable"}
    text = raw.decode("utf-8", "replace")
    if ext in PY_SUFFIXES:
        return _py_facts(text)
    if ext in SCAN_SUFFIXES:
        return _scan_facts(text, ext)
    return {"symbols": [], "imports": [], "exact": True, "note": ""}


# --------------------------------------------------------------------------
#   Packing - greedy, trimmed, never over the budget
# --------------------------------------------------------------------------

_KIND_WORD = {"class": "class", "def": "def", "function": "function", "const": "const",
              "interface": "interface", "type": "type", "object": "object", "fun": "fun",
              "fn": "fn", "struct": "struct", "enum": "enum", "trait": "trait",
              "impl": "impl"}


def _symbol_line(sym) -> str:
    kind, name, line, sig = sym
    line = f"   L{line} {_KIND_WORD.get(kind, kind)} {name}{sig or ''}"
    if len(line) > MAX_SYMBOL_LINE:
        line = line[:MAX_SYMBOL_LINE - 3].rstrip() + "..."
    return line


def _ranked_symbols(row, question_words: list) -> list:
    """This file's symbols, the ones whose names hold the question's words
    first, then by line - so a trimmed file keeps its relevant lines."""
    want = [w for w in question_words]

    def key(sym):
        low = sym[1].casefold()
        hits = sum(1 for w in want if w in low)
        return (-hits, sym[2], sym[1])

    return sorted(row["symbols"], key=key)[:MAX_SYMBOLS_PER_FILE]


def _pack(name: str, question: str, files: list, question_words: list, *,
          budget: int, stopped: str) -> dict:
    """The map text, and what was left out of it. Deterministic by construction:
    `files` is already in rank order and every list here is sorted.

    TAIL_RESERVE characters are held back while the files are packed, so the
    "... N more files did not fit" line always fits at the end rather than
    being squeezed out by the very files it is reporting on.
    """
    tail_room = TAIL_RESERVE // CHARS_PER_TOKEN + 1
    ranked = sorted(files, key=lambda r: (-r["score"], r["path"]))
    head = [f"Repository map of {name} - {len(ranked)} files with names to show, "
            f"{sum(len(r['symbols']) for r in ranked)} symbols declared."]
    if question_words:
        head.append("Question: " + " ".join(question_words))
    if stopped:
        head.append(f"(Not the whole folder: {stopped}.)")
    lines = list(head)
    shown = 0
    symbols_shown = 0
    for row in ranked:
        block = [f"{shown + 1}. {row['path'].replace(os.sep, '/')}  score={row['score']:g}"]
        for sym in _ranked_symbols(row, question_words):
            block.append(_symbol_line(sym))
        # An import line is shown only where it MEANS something: the file's
        # imports answer part of the question, or they point at another file
        # this map kept (the edge the ranking used). Every file's imports
        # would double the size of a map for no extra signal.
        if row["imports"] and (row["import_match"] or row["edges_out"]):
            wanted = []
            for target in row["imports"]:
                target = str(target).replace("\n", " ").strip()
                if target and target not in wanted:
                    wanted.append(target)
            if wanted:
                line = "   imports: " + ", ".join(wanted[:6])
                if len(line) > MAX_SYMBOL_LINE:
                    line = line[:MAX_SYMBOL_LINE - 3].rstrip() + "..."
                block.append(line)
        if row.get("note"):
            block.append(f"   ({row['note']})")
        # Trim this block until it fits beside the header and the tail's room.
        while len(block) > 1 and estimate_tokens("\n".join(lines + block)) + tail_room > budget:
            block.pop()
        if estimate_tokens("\n".join(lines + block)) + tail_room > budget:
            break
        lines += block
        shown += 1
        symbols_shown += len(block) - 1 - (1 if row.get("note") else 0) \
            - (1 if block[-1].startswith("   imports: ") else 0)
    leftover = len(ranked) - shown
    if leftover > 0:
        lines.append(f"... {leftover} more file{'s' if leftover != 1 else ''} did not fit "
                     f"in {budget:,} tokens. Ask about a narrower area, or raise the budget.")
    text = "\n".join(lines)
    if estimate_tokens(text) > budget and leftover:
        lines.pop()                          # last resort: the tail line itself
        text = "\n".join(lines)
    while estimate_tokens(text) > budget and len(lines) > len(head):
        lines.pop()
        text = "\n".join(lines)
    return {"map": text, "tokens": estimate_tokens(text), "files": shown,
            "symbols": symbols_shown, "truncated": leftover > 0,
            "ranked": [{"path": r["path"].replace(os.sep, "/"),
                        "score": r["score"], "symbols": len(r["symbols"])}
                       for r in ranked[:10]]}


# --------------------------------------------------------------------------
#   The two ways in: a folder, or a registered project
# --------------------------------------------------------------------------


def map_folder(folder, question: str = "", *, roots=None,
               budget=TOKENS_DEFAULT, clock=None) -> dict:
    """The map of ONE folder on "Folders Jarvis may look in".

    `ok: False` and one plain sentence when the folder is not on that list -
    the walk does not start, and nothing is guessed.
    """
    import time as _time
    clock = clock or _time.monotonic
    docs = _documents()
    if docs is None:
        return {"ok": False, "available": False,
                "error": "Looking in folders is not installed on this backend, so there is "
                         "nothing to map."}
    listed = docs.folders() if roots is None else list(roots)
    got = docs.allowed_path(folder, listed)
    if got is None:
        return {"ok": False, "available": True, "error": REFUSED}
    root = got[0]
    if not os.path.isdir(root):
        return {"ok": False, "available": True,
                "error": "That folder is not on this PC any more, so there is nothing to map."}
    budget = budget_of(budget)
    found, stopped = _walk(root, clock=clock)
    rows = []
    for full, rel in found:
        ext = os.path.splitext(full)[1].lower()
        if ext not in PY_SUFFIXES and ext not in SCAN_SUFFIXES and ext not in TEXT_SUFFIXES:
            continue
        facts = _facts(full, ext) if (ext in PY_SUFFIXES or ext in SCAN_SUFFIXES) \
            else {"symbols": [], "imports": [], "exact": True, "note": ""}
        rows.append({"path": rel, "symbols": facts["symbols"], "imports": facts["imports"],
                     "note": facts.get("note") or "", "exact": facts.get("exact", True)})
    question_words = words_of(question)
    _score(rows, question_words)
    # A file with no match at all still belongs in a map of a SMALL folder (the
    # owner asked to see the folder), but in a big one it is noise: keep the
    # matched files, then the rest only while they are few.
    matched = [r for r in rows if r["matched"]]
    rest = [r for r in rows if not r["matched"]]
    if len(rows) <= 40:
        keep = rows
    else:
        keep = matched + sorted(rest, key=lambda r: r["path"])[:20]
    name = os.path.basename(root.rstrip("\\/")) or root
    out = _pack(name, question, keep, question_words, budget=budget, stopped=stopped)
    out.update({"ok": True, "available": True, "folder": {"path": root, "name": name},
                "question": str(question or ""), "budget": budget,
                "files_seen": len(found), "outside_text": True})
    return out


def map_project(pid, question: str = "", *, store=None, budget=TOKENS_DEFAULT,
                clock=None) -> dict:
    """The map of a registered project's own folder (projects.db)."""
    if store is None:
        projects = _projects()
        if projects is None:
            return {"ok": False, "available": False,
                    "error": "Projects are not installed on this backend, so there is no "
                             "project folder to map."}
        store = projects.get()
    try:
        project = store.get(pid)
    except KeyError:
        return {"ok": False, "available": True, "error": "There is no project with that id."}
    folder = ((project.get("folder") or {}).get("path") or "").strip()
    if not folder:
        return {"ok": False, "available": True,
                "error": "That project has no folder, so there is nothing to map. A coding "
                         "project's folder is chosen on the PC."}
    out = map_folder(folder, question, budget=budget, clock=clock)
    out["project"] = {"id": project.get("id"), "name": project.get("name")}
    return out


def handle_get(pid: str, query: str = "", *, store=None) -> tuple:
    """GET /api/projects/<id>/map -> (status, body). The documented shape is in
    the module docstring; a refusal is 400 and one plain sentence."""
    q = parse_qs(str(query or ""))
    question = (q.get("q") or [""])[0]
    budget = budget_of((q.get("tokens") or [TOKENS_DEFAULT])[0])
    try:
        out = map_project(pid, question, store=store, budget=budget)
    except Exception as exc:                                # noqa: BLE001
        if isinstance(exc, ValueError):
            return 400, {"ok": False, "error": _sentence(exc)}
        return 503, {"ok": False, "error": type(exc).__name__}
    return (200 if out.get("ok") else 400), out


def describe(args: dict) -> str:
    """What a card would say, if the owner set reading files to ask."""
    where = str(args.get("path") or "").strip()
    pid = str(args.get("project") or "").strip()
    if not where and pid:
        where = f"project {pid}"
    return ("Jarvis would like to " + WHAT.format(where=where or "one of your folders")
            + " Nothing is changed, nothing is written, and nothing is sent anywhere.")


def run_tool(args: dict, *, roots=None) -> dict:
    """The `my_files` action `map` (jarvis_documents.run_tool hands it here).

    `path` takes EITHER a folder on the owner's list or a project's id, so the
    tool's schema needs no second field: a project id is 32 hex characters and
    is never a folder that exists, which is exactly how the two are told apart.
    """
    if not isinstance(args, dict):
        return {"ok": False, "error": "say which project, or which folder on your list, to map"}
    pid = str(args.get("project") or "").strip()
    folder = str(args.get("path") or "").strip()
    question = str(args.get("words") or "")
    budget = budget_of(args.get("tokens"))
    if not pid and folder and not os.path.isdir(folder) and _PROJECT_ID.match(folder):
        pid = folder
    if pid:
        out = map_project(pid, question, budget=budget)
    elif folder:
        out = map_folder(folder, question, roots=roots, budget=budget)
    else:
        return {"ok": False, "error": "say which project, or which folder on your list, to map"}
    if not out.get("ok"):
        return out
    docs = _documents()
    if docs is not None:
        # The store's own boundary (security audit C6): the names in a map are
        # the owner's file names, so they are marked exactly like a file read.
        out["map"] = docs.mark_outside(out["map"])
        out["outside_text"] = True
    out["what"] = ("the names of files, classes and functions in one folder, ranked for the "
                   "question - names and signatures only, never a function's body")
    return out


def _reset_for_tests() -> None:
    """Nothing is cached, so there is nothing to reset - kept so a suite that
    resets its siblings can call it without a special case."""
    return None


if __name__ == "__main__":                                  # pragma: no cover
    import sys
    q = " ".join(a for a in sys.argv[2:] if not a.startswith("-"))
    res = map_project(sys.argv[1], q) if len(sys.argv) > 1 else {"ok": False}
    print(json.dumps({k: v for k, v in res.items() if k != "ranked"}, indent=2))
