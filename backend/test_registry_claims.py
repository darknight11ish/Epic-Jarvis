#!/usr/bin/env python3
"""The registry's own sentences about its modules must agree with the source.

    python3 test_registry_claims.py

WHY THIS EXISTS. This project keeps two lists of the modules it ships whole -
the `SHIPPED` tuple in `backend/_where.py` and the `$SHIPPED` block in
`scripts/apply-patches.ps1` - and every entry carries a comment saying what the
module is and who uses it. Those comments are read as fact by anyone deciding
whether a module is wired in. Read on `main` at `e286fe26`, two of them were
not:

  * `jarvis_tool_schema.py` was described as one "jarvis_skill_hub.py calls".
    Nothing calls it: `jarvis_skill_hub.py` does not name it anywhere, and
    outside its own suite it has no importer at all. `docs/JARVIS-API.md`
    already said so in words - "It has no caller yet" - so the registry
    contradicted both the code and this project's own documentation.
  * `jarvis_task_lease.py` was described as a module "nothing imports ...
    yet", while `jarvis_browser_control.py` imports it inside its one
    integration point and `run_steps()` gates every step on it.

A third was the same defect in prose rather than in a list: the
`cloud-say-yes.patch` row of `backend/README.md` said the Shareable-lane work
sat on a branch "not merged into `main` yet", and the hunks were on `main` -
the branch's copy of that patch and `main`'s were the same blob.

WHAT IS CHECKED, AND HOW. Not English. Each sentence is reduced to one of four
shapes a machine can settle, and only those shapes are read at all:

  * `X.py calls it` / `imports it` / `uses it` - X must be in this tree and must
    really import the module the entry is about;
  * `nothing imports it` / `has no caller` - no file in this tree outside the
    module itself and the `test_*.py` suites may import it. A suite is not a
    caller, and a suite that imports the module under test is the point of a
    suite; a comment that meant to include tests would say so;
  * `X.py proves it` - X must be in this tree and must name the module;
  * `merged as ... \\`<sha>\\`` - that commit must be in this tree's history.

Everything but the last is a plain read of the working tree: no network, no
model, no file from the owner's PC. The `merged as` check is the one that needs
git, and where git or the commit is not available - a shallow clone, a
downloaded ZIP, CI's shallow `audit` job - it prints `skip` and is counted as a
skip, never as a pass. The `backend` job that runs this suite sets
`fetch-depth: 0`, so there it is judged for real.

WHAT IT DELIBERATELY DOES NOT DO. It does not judge prose. An entry whose
comment makes no claim in one of those four shapes is not read, and a claim
this cannot settle is reported as a skip rather than guessed at.
"""
import ast
import os
import re
import subprocess
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _where  # noqa: E402

REPO = _where.REPO
API_DOC = REPO / "docs" / "JARVIS-API.md"
SHIPPED_LISTS = (("backend/_where.py", REPO / "backend" / "_where.py"),
                 ("jarvis-backend/_where.py", REPO / "jarvis-backend" / "_where.py"),
                 ("scripts/apply-patches.ps1", REPO / "scripts" / "apply-patches.ps1"))
README = REPO / "backend" / "README.md"

PASSED, FAILED, SKIPPED = [], [], []

#: Directories never walked. `.dsh-scratch` is the important one: this project
#: is worked in dozens of parallel `git worktree` checkouts kept there, so a
#: walk that descended into it would find an import in a *copy* of the file
#: being asked about - the wrong answer, and the same instrument reading
#: confidently about the wrong tree (CLAUDE.md, "Do not claim more than the
#: evidence supports").
SKIP_DIRS = {".git", ".dsh-scratch", "node_modules", "__pycache__", ".venv",
             "venv", "brag-output"}

#: The four shapes, deliberately narrow. A sentence that makes no claim in one
#: of these is not read at all - which is what keeps this from being an English
#: parser, and what keeps a new sentence from failing here for its grammar.
_CALLS_IT = re.compile(r"([A-Za-z_]\w*\.py)`?\s+(calls|imports|uses)\s+it\b")
_NOTHING_IMPORTS = re.compile(r"\bnothing imports it\b")
_NO_CALLER = re.compile(r"\b(?:has|have)\s+no\s+caller\b|\bno caller yet\b", re.I)
_PROVES_IT = re.compile(r"([A-Za-z_]\w*\.py)`?\s+proves it\b")
#: `merged as PR #468, `21146d37`` and `merged as PR #392, `a284f0d0`` - the
#: project's own idiom, and the sha is always backticked. The window stops a
#: backticked word from a later clause being read as the commit.
_MERGED_AS = re.compile(r"merged as[^`\n]{0,60}`([0-9a-f]{7,40})`")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))
    return bool(cond)


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   Reading the two lists
# --------------------------------------------------------------------------

def where_entries(text):
    """[(name, comment, line)] for the `SHIPPED` tuple of a `_where.py`.

    More than one name may sit on one line (`"jarvis_intake.py",
    "jarvis_feedback.py", ...`), and each carries the comment block written
    above it - so the block is accumulated and attached to every name on the
    next line that holds one.
    """
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("SHIPPED = (")), None)
    if start is None:
        return []
    end = next((i for i, l in enumerate(lines[start:], start) if l.strip() == ")"), None)
    if end is None:
        return []
    out, block = [], []
    for i in range(start + 1, end):
        stripped = lines[i].strip()
        if stripped.startswith("#"):
            block.append(stripped.lstrip("#").strip())
            continue
        names = re.findall(r'"([^"]+)"', stripped)
        if names:
            out += [(n, " ".join(block), i + 1) for n in names]
            block = []
    return out


def ps1_entries(text):
    """[(name, comment, line)] for the installer's `$SHIPPED` block.

    Here the description is an inline `#` comment on the entry's own line, not
    a block above it - the block above an entry in this file is a section
    marker (`# --- The blind credential vault (2026-10-14) ---`).
    """
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines)
                  if re.match(r"^\$SHIPPED\s*=\s*@\(", l)), None)
    if start is None:
        return []
    end = next((i for i, l in enumerate(lines[start:], start) if l.strip() == ")"), None)
    if end is None:
        return []
    out = []
    for i in range(start + 1, end):
        m = re.match(r"^\s*'([^']+)'\s*(?:#\s*(.*))?$", lines[i])
        if m:
            out.append((m.group(1), (m.group(2) or "").strip(), i + 1))
    return out


_ENTRIES_CACHE = {}


def entries_of(name, path):
    """The entries of one registry list, read from disk once, or [] if
    unreadable."""
    if name in _ENTRIES_CACHE:
        return _ENTRIES_CACHE[name]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        rows = []
    else:
        rows = ps1_entries(text) if path.suffix == ".ps1" else where_entries(text)
    _ENTRIES_CACHE[name] = rows
    return rows


def _first_difference(a, b):
    """Where two lists of names stop agreeing, in words."""
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return f"entry {i + 1}: {x!r} against {y!r}"
    if len(a) != len(b):
        longer, shorter = (a, b) if len(a) > len(b) else (b, a)
        return (f"{len(a)} entries against {len(b)}; the first extra is "
                f"{longer[len(shorter)]!r}")
    return ""


# --------------------------------------------------------------------------
#   Reading the source the sentences are about
# --------------------------------------------------------------------------

def _imported(tree):
    """Every top-level module name one parsed file imports."""
    got = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            got.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            got.add(node.module.split(".")[0])
    return got


class Scan:
    """This tree's Python source, read once: what each file imports, which
    local name each module was bound to, what is called on it, and what file
    names exist anywhere in the tree."""

    def __init__(self, repo):
        self.repo = repo
        self.imports = {}      # relpath -> {module names imported}
        self.aliases = {}      # relpath -> {local name: module it came from}
        self.calls = {}        # relpath -> [(local name, attribute, line)]
        self.names = set()     # every file name in the tree
        self.unreadable = []   # (relpath, why) - a file this could not parse
        for dirpath, dirnames, filenames in os.walk(repo):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                rel = (Path(dirpath) / fn).relative_to(repo)
                self.names.add(rel.name)
                if rel.suffix != ".py":
                    continue
                key = rel.as_posix()
                try:
                    tree = ast.parse((Path(dirpath) / fn).read_text(
                        encoding="utf-8", errors="replace"))
                except SyntaxError as exc:
                    self.unreadable.append((key, str(exc)))
                    continue
                self.imports[key] = _imported(tree)
                alias, calls = {}, []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for a in node.names:
                            alias[a.asname or a.name.split(".")[0]] = a.name.split(".")[0]
                    elif isinstance(node, ast.ImportFrom):
                        if node.level == 0 and node.module:
                            alias[node.module.split(".")[0]] = node.module.split(".")[0]
                    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                        if isinstance(node.func.value, ast.Name):
                            calls.append((node.func.value.id, node.func.attr, node.lineno))
                self.aliases[key], self.calls[key] = alias, calls

    def has(self, name):
        """Is a file with this name anywhere in the tree?"""
        return name in self.names

    def named(self, name):
        """Every relpath whose file name is exactly `name`."""
        return sorted(r for r in self.imports if r.rsplit("/", 1)[-1] == name)

    def importers(self, stem, count_tests=False):
        """Every file that imports `stem`, leaving out the module itself and -
        unless `count_tests` - the `test_*.py` suites.

        The test files are left out because of what the claim means: a suite
        that imports the module it tests is not a caller of it in the running
        program, and `nothing imports it` is a statement about the program.
        `count_tests=True` is what the failure detail prints, so the reader
        sees the suites too and can judge for themselves.
        """
        out = []
        for rel, mods in self.imports.items():
            name = rel.rsplit("/", 1)[-1]
            if name == stem + ".py" or (not count_tests and name.startswith("test_")):
                continue
            if stem in mods:
                out.append(rel)
        return sorted(out)

    def callers_of(self, stem, func):
        """[(relpath, line)] where `<alias>.<func>(...)` is called and `alias`
        was bound to `stem` by an import in that same file."""
        hits = []
        for rel, calls in self.calls.items():
            bound = {a for a, m in self.aliases.get(rel, {}).items() if m == stem}
            if not bound:
                continue
            hits += [(rel, line) for a, attr, line in calls
                     if attr == func and a in bound]
        return sorted(hits)


# --------------------------------------------------------------------------
#   Settling one entry's comment
# --------------------------------------------------------------------------

def claims_in(comment):
    """How many claims of the four shapes a comment makes."""
    return (len(_CALLS_IT.findall(comment))
            + len(_PROVES_IT.findall(comment))
            + (1 if _NOTHING_IMPORTS.search(comment) else 0)
            + (1 if _NO_CALLER.search(comment) else 0))


def problems_with(name, comment, scan):
    """[(shape, message)] for every claim in one entry's comment that `scan`
    contradicts. The shape is "caller", "uncalled" or "proof", so each check
    below can report only its own kind.

    Pure but for `scan`, so the two sentences that were wrong on `main` can be
    handed to it as planted input - see
    `t_the_checker_refuses_the_sentences_that_were_shipped`.
    """
    stem = name.rsplit("/", 1)[-1]
    stem = stem[:-3] if stem.endswith(".py") else stem
    out = []
    for who, verb in _CALLS_IT.findall(comment):
        where = scan.named(who)
        if not where:
            out.append(("caller", f"says {who} {verb} it, and there is no {who} "
                                  f"in this tree"))
        elif not any(stem in scan.imports.get(r, ()) for r in where):
            out.append(("caller", f"says {who} {verb} it, and {who} never imports {stem}"))
    if _NOTHING_IMPORTS.search(comment) or _NO_CALLER.search(comment):
        found = scan.importers(stem)
        if found:
            out.append(("uncalled", f"says nothing imports it, and {' and '.join(found)} do "
                                    f"(all importers: {scan.importers(stem, count_tests=True)})"))
    for who in _PROVES_IT.findall(comment):
        where = scan.named(who)
        if not where:
            out.append(("proof", f"says {who} proves it, and there is no {who} in this tree"))
        elif not any(stem in scan.imports.get(r, ()) for r in where):
            out.append(("proof", f"says {who} proves it, and {who} never names {stem}"))
    return out


def _of_shape(shape):
    """`(how many claims of this shape were read, [(where, message)])` across
    both registry lists."""
    found, problems = 0, []
    for label, path in SHIPPED_LISTS:
        for name, comment, line in entries_of(label, path):
            found += _claims_of_shape(comment, shape)
            problems += [f"{label}:{line} ({name}) - {p}"
                         for s, p in problems_with(name, comment, SCAN) if s == shape]
    return found, problems


def _claims_of_shape(comment, shape):
    """How many claims of one shape a comment makes, whether or not they hold."""
    if shape == "caller":
        return len(_CALLS_IT.findall(comment))
    if shape == "proof":
        return len(_PROVES_IT.findall(comment))
    return ((1 if _NOTHING_IMPORTS.search(comment) else 0)
            + (1 if _NO_CALLER.search(comment) else 0))


def _merge_claims():
    """[(where, line, sha)] for every `merged as <sha>` claim in this project's
    prose. Split from the git call so the reading can be tested on made-up
    input."""
    out = []
    files = [README] + [p for _, p in SHIPPED_LISTS]
    docs = REPO / "docs"
    if docs.is_dir():
        files += sorted(p for p in docs.rglob("*")
                        if p.is_file() and p.suffix in (".md", ".tsv"))
    for path in files:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for num, line in enumerate(text.splitlines(), 1):
            for m in _MERGED_AS.finditer(line):
                out.append((path.relative_to(REPO).as_posix(), num, m.group(1)))
    return out


def _merge_problems(claims, probe):
    """[(where, line, sha, why)] for every claim `probe` contradicts.

    `probe(sha)` answers "in-history", "absent" (this checkout does not have
    the commit, so the claim cannot be judged here) or "not-in-history". The
    two are told apart on purpose: a shallow clone must produce a SKIP, never a
    failure and never a pass.
    """
    out = []
    for where, num, sha in claims:
        verdict = probe(sha)
        if verdict == "absent":
            out.append((where, num, sha, "this checkout does not have that commit"))
        elif verdict == "not-in-history":
            out.append((where, num, sha, "NOT in this tree's history"))
    return out


def _git(*args):
    """(exit code, output) for a git command in this repository, or
    (None, why) when git itself cannot be run here."""
    try:
        r = subprocess.run(["git", *args], cwd=str(REPO), capture_output=True,
                           text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


# --------------------------------------------------------------------------
#   The lists themselves
# --------------------------------------------------------------------------

def t_the_three_lists_are_one_list_in_one_order():
    """The same modules, in the same order, in all three places.

    `$SHIPPED` in the installer and `SHIPPED` in `backend/_where.py` are the
    two authorities on what is shipped, and `jarvis-backend/_where.py` is the
    published base's copy of the second. A module added to one and not the
    others, or moved, is the class `test_shipped_modules.py` exists for - and
    the order matters here because the registry's comments are written in it.
    """
    lists = {label: entries_of(label, path) for label, path in SHIPPED_LISTS}
    for label, rows in lists.items():
        check(f"{label}: the list was found, and is not empty "
              f"(a parser that found nothing must not pass)",
              len(rows) > 50, f"{len(rows)} entries")
    where = [n for n, _, _ in lists["backend/_where.py"]]
    base = [n for n, _, _ in lists["jarvis-backend/_where.py"]]
    ps1 = [n for n, _, _ in lists["scripts/apply-patches.ps1"]]
    check("backend/_where.py and scripts/apply-patches.ps1 list the same modules, "
          "in the same order", where == ps1,
          _first_difference(where, ps1))
    check("jarvis-backend/_where.py carries the same list, in the same order",
          base == where, _first_difference(where, base))


# --------------------------------------------------------------------------
#   Every claim a registry comment makes
# --------------------------------------------------------------------------

def t_a_comment_that_names_a_caller_names_a_real_one():
    """`X.py calls it` must be true of X, wherever the sentence is written."""
    found, problems = _of_shape("caller")
    check("the sweep read at least one 'X calls/imports/uses it' claim "
          "(a checker that settles nothing must not pass)", found > 0,
          f"{found} found")
    check(f"every one of the {found} claims about who calls a module is true",
          not problems, "\n        ".join(problems))


def t_a_comment_that_says_nothing_imports_it_is_right():
    """`nothing imports it` / `has no caller` must match the source.

    This is the sentence that was wrong about `jarvis_task_lease.py`. The
    measure is production importers, and a failure prints the suites too, so
    the reader sees everything that imports it rather than the verdict alone.
    """
    found, problems = _of_shape("uncalled")
    check("the sweep read at least one 'nothing imports it' claim", found > 0,
          f"{found} found")
    check(f"every one of the {found} 'nothing imports it' claims is true",
          not problems, "\n        ".join(problems))


def t_a_comment_that_names_a_proof_names_a_real_one():
    """`X.py proves it` must name a file that exists and names the module."""
    found, problems = _of_shape("proof")
    check(f"every one of the {found} 'X proves it' claims names a real suite "
          "that names the module", not problems, "\n        ".join(problems))


def t_a_comment_that_names_a_file_names_one_that_exists():
    """Every `X.py` a registry comment names is a file in this tree.

    Measured on the tree of `e286fe26`: all 197 entries of each list, every
    `.py` name in every comment, and not one of them is missing. So a name
    added later that does not exist fails here rather than being read as fact.
    """
    scan = SCAN
    found, problems = 0, []
    for label, path in SHIPPED_LISTS:
        for name, comment, line in entries_of(label, path):
            for who in sorted(set(re.findall(r"[A-Za-z_]\w*\.py", comment))):
                found += 1
                if not scan.has(who):
                    problems.append(f"{label}:{line} ({name}) names {who}, "
                                    f"and no file of that name is in this tree")
    check("the sweep read at least one file name out of the comments", found > 0,
          f"{found} found")
    check(f"every one of the {found} file names a comment mentions is in this tree",
          not problems, "\n        ".join(problems))


# --------------------------------------------------------------------------
#   The two entries this suite was written for
# --------------------------------------------------------------------------

def t_jarvis_tool_schema_still_has_no_caller():
    """The corrected claim, pinned by measurement - and by the doc it cites.

    `jarvis_tool_schema.py`'s own docstring records why wiring it into the tool
    loop would be wrong: on the live Ollama, a tool's schema in `format` on a
    call that also offers `tools` corrupted the arguments. So a *new* caller
    appearing is a real event worth failing on, and the registry comment and
    `docs/JARVIS-API.md` must move together with it.
    """
    scan = SCAN
    importers = scan.importers("jarvis_tool_schema")
    check("jarvis_tool_schema.py still has no caller outside its own suite",
          not importers,
          f"importers now: {scan.importers('jarvis_tool_schema', count_tests=True)}")
    for label, path in SHIPPED_LISTS:
        rows = [c for n, c, _ in entries_of(label, path)
                if n == "jarvis_tool_schema.py"]
        check(f"{label}'s entry for jarvis_tool_schema.py says it has no caller",
              rows and _NO_CALLER.search(rows[0]),
              f"comment: {rows[0][-260:] if rows else 'NO ENTRY'}")
        check(f"{label}'s entry points at the doc that says the same",
              rows and "JARVIS-API.md" in rows[0],
              f"comment: {rows[0][-260:] if rows else 'NO ENTRY'}")
    if not API_DOC.is_file():
        skip(f"{API_DOC.relative_to(REPO).as_posix()} is not here, so the sentence "
             f"the registry points at was NOT checked")
        return
    text = API_DOC.read_text(encoding="utf-8", errors="replace")
    # The PARAGRAPH, not a window of characters: this page is hard-wrapped, and
    # it says "It has no\ncaller yet" - so a search for the words "no caller"
    # misses a sentence that is there. Measured, not guessed: that is exactly
    # how the first version of this check failed.
    said = [p for p in re.split(r"\n\s*\n", text) if "jarvis_tool_schema.py" in p]
    check("docs/JARVIS-API.md still says it has no caller - the sentence the "
          "registry comment points at",
          any("no caller" in re.sub(r"\s+", " ", p) for p in said),
          f"{len(said)} paragraph(s) name the module; flat text of the first: "
          f"{re.sub(r'\\s+', ' ', said[0])[:300]!r}" if said else "no paragraph names it")


def t_jarvis_task_lease_is_wired_on_the_consumer_side_only():
    """The corrected claim, pinned: wired where it is consumed, unopened in
    production.

    Two facts, and both are needed. The consumer-side wiring is
    `jarvis_browser_control.py`'s single `_lease_check()` - if that import goes,
    the registry comment saying it is wired becomes false. And no production
    caller opens a lease: `create()` is called only from the module's own
    suite. `create()` being called *nowhere* must fail too, or the second check
    would pass on a tree where the harness was deleted.
    """
    scan = SCAN
    importers = scan.importers("jarvis_task_lease")
    check("jarvis_browser_control.py still imports jarvis_task_lease, which is "
          "what the corrected comment now claims",
          any(r.endswith("jarvis_browser_control.py") for r in importers),
          f"importers: {importers}")
    for label, path in SHIPPED_LISTS:
        rows = [c for n, c, _ in entries_of(label, path)
                if n == "jarvis_task_lease.py"]
        check(f"{label}'s entry says it IS wired on the consumer side",
              rows and "jarvis_browser_control.py" in rows[0],
              f"comment: {rows[0][-320:] if rows else 'NO ENTRY'}")
        check(f"{label}'s entry no longer claims nothing imports it",
              rows and not (_NOTHING_IMPORTS.search(rows[0])
                            or _NO_CALLER.search(rows[0])),
              f"comment still says it: {rows[0][-320:] if rows else 'NO ENTRY'}")
    callers = scan.callers_of("jarvis_task_lease", "create")
    check("a lease IS opened somewhere, so the next check is not vacuous",
          bool(callers), "create() is called from nowhere at all")
    check("no production caller opens a lease yet - create() is called only "
          "from the module's own suite",
          callers and all(r.rsplit("/", 1)[-1].startswith("test_") for r, _ in callers),
          f"create() called from: {callers}")


# --------------------------------------------------------------------------
#   A claim about a merge, in prose
# --------------------------------------------------------------------------

def t_a_claim_that_work_is_merged_is_really_merged():
    """`merged as <sha>` must name a commit in this tree's history.

    The third sentence of the same class: the `cloud-say-yes.patch` row of
    `backend/README.md` said the Shareable-lane hunks sat on a branch "not
    merged into `main` yet", while `main` and that branch held the same blob.
    The reading is a plain source scan; only the ancestry needs git, and a
    checkout without the commit SKIPS rather than passing quietly.
    """
    claims = _merge_claims()
    check("the sweep read at least one 'merged as <sha>' claim "
          "(a checker that settles nothing must not pass)", bool(claims),
          f"{len(claims)} found")

    rows = [l for l in README.read_text(encoding="utf-8", errors="replace").splitlines()
            if "cloud-say-yes.patch" in l] if README.is_file() else []
    check("backend/README.md names cloud-say-yes.patch in at least one line",
          bool(rows), "the patch is not named in that file at all")
    if rows:
        # Its own table row, and the row of a later patch that names it as
        # context. EITHER saying it is unmerged would be the same false claim,
        # so no line that names the patch may say that.
        bad = [l for l in rows if "not merged into `main`" in l]
        shown = bad[0][max(0, bad[0].find("not merged") - 80):][:200] if bad else ""
        check("... and no line naming that patch says the work is not merged "
              "into main", not bad,
              f"the false sentence is back: {shown}")
        check("... and a line naming it says which commit the work was merged as",
              any(_MERGED_AS.search(l) for l in rows),
              "no `merged as <sha>` in any line naming it, so this claim is unchecked")

    code, why = _git("rev-parse", "--git-dir")
    if code != 0:
        skip(f"git could not be run here ({why or 'no exit 0'}), so the "
             f"{len(claims)} 'merged as <sha>' claim(s) were NOT checked")

        def probe(_sha):
            return "absent"
    else:
        def probe(sha):
            rc, _ = _git("cat-file", "-e", sha + "^{commit}")
            if rc != 0:
                return "absent"
            rc, _ = _git("merge-base", "--is-ancestor", sha, "HEAD")
            return "in-history" if rc == 0 else "not-in-history"

    problems = _merge_problems(claims, probe)
    judged = len(claims) - len([p for p in problems if p[3].startswith("this checkout")])
    absent = [f"{w}:{n} {s}" for w, n, s, why_ in problems if why_.startswith("this checkout")]
    if absent:
        skip(f"{len(absent)} 'merged as <sha>' claim(s) name a commit this checkout "
             f"does not have, so they were NOT checked: {'; '.join(absent)}")
    check(f"every 'merged as <sha>' claim that could be judged ({judged} of "
          f"{len(claims)}) names a commit in this tree's history",
          not [p for p in problems if p[3].startswith("NOT")],
          "\n        ".join(f"{w}:{n} {s} - {why_}" for w, n, s, why_ in problems
                            if why_.startswith("NOT")))


# --------------------------------------------------------------------------
#   The control: this checker must be able to fail
# --------------------------------------------------------------------------

def t_the_checker_refuses_the_sentences_that_were_shipped():
    """THE CONTROL, and the reason this suite is worth having.

    A checker that reported nothing would pass every check above. These hand it
    the exact sentences that were wrong on `main`, against the real tree, and
    demand a problem back - so the guard is proved inside the suite on every
    run, not only on the day it was written.
    """
    scan = SCAN
    planted = "Standard library only, and no patch - jarvis_skill_hub.py calls it."
    check("it REFUSES 'jarvis_skill_hub.py calls it' for jarvis_tool_schema.py - "
          "the sentence that was shipped",
          problems_with("jarvis_tool_schema.py", planted, scan),
          "the checker reported no problem with a false sentence")
    planted = ("Leases live in memory and die with the process: no route, no patch, "
               "no file, no database, and nothing imports it yet.")
    check("it REFUSES 'nothing imports it yet' for jarvis_task_lease.py - the "
          "sentence that was shipped",
          problems_with("jarvis_task_lease.py", planted, scan),
          "the checker reported no problem with a false sentence")
    # THE OTHER DIRECTION. A refuser that refused everything would pass both
    # checks above and be useless, so a true claim must come back clean.
    true_claim = "Standard library only, and no patch - jarvis_agent.py calls it."
    check("... and it does NOT report a claim that is true (jarvis_agent.py does "
          "call jarvis_claims.py)",
          problems_with("jarvis_claims.py", true_claim, scan) == [],
          f"reported: {problems_with('jarvis_claims.py', true_claim, scan)}")
    # The merge reader, on made-up input: one commit in history, one not.
    fake = [("docs/x.md", 1, "aaaaaaa"), ("docs/x.md", 2, "bbbbbbb")]
    verdicts = {"aaaaaaa": "in-history", "bbbbbbb": "not-in-history"}
    got = _merge_problems(fake, lambda s: verdicts[s])
    check("the merged-as reader reports the claim that is out of history and "
          "leaves the one that is in it",
          [g[2] for g in got] == ["bbbbbbb"], f"reported: {got}")
    check("... and it calls a commit this checkout does not have 'cannot be "
          "judged here', never 'not merged'",
          [g[3] for g in _merge_problems([("docs/x.md", 1, "ccccccc")],
                                         lambda s: "absent")][0].startswith("this checkout"),
          "an absent commit would be reported as a failure")


# --------------------------------------------------------------------------
#   It reads this tree and nothing else
# --------------------------------------------------------------------------

def t_it_reads_this_tree_and_reaches_nothing():
    """No socket, no subprocess but git, and the two lists are the repo's own."""
    check("every path this suite reads is inside this repository",
          all(str(p).startswith(str(REPO)) for _, p in SHIPPED_LISTS),
          f"REPO is {REPO}")
    check("the source scan read the tree, not nothing", len(SCAN.imports) > 100,
          f"{len(SCAN.imports)} .py files")
    check("every .py file in the tree parsed (a file skipped silently would be "
          "a claim never checked)", not SCAN.unreadable,
          f"unreadable: {SCAN.unreadable[:5]}")


SCAN = Scan(REPO)


if __name__ == "__main__":
    for fn in (t_the_three_lists_are_one_list_in_one_order,
               t_a_comment_that_names_a_caller_names_a_real_one,
               t_a_comment_that_says_nothing_imports_it_is_right,
               t_a_comment_that_names_a_proof_names_a_real_one,
               t_a_comment_that_names_a_file_names_one_that_exists,
               t_jarvis_tool_schema_still_has_no_caller,
               t_jarvis_task_lease_is_wired_on_the_consumer_side_only,
               t_a_claim_that_work_is_merged_is_really_merged,
               t_the_checker_refuses_the_sentences_that_were_shipped,
               t_it_reads_this_tree_and_reaches_nothing):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
