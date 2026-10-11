#!/usr/bin/env python3
"""Find a dictionary or a JSON object that writes the same key twice.

    python3 tools/check_literal_keys.py [-v]

Both languages keep the LAST duplicate and say nothing at all: CPython silently
rebinds the key, and `json.loads` does the same. So two entries that disagree
about one action do not collide, do not error, and do not warn - one of them
simply stops existing, and which one wins depends on which line was typed
later. Every reader after that sees a table that looks complete.

That is not hypothetical here. On 2026-10-05 the owner's own `jarvis_gate.py`
- the approval gate, which is not in this repository - was found to carry FOUR
duplicated `_RISK` keys: `append_logseq_journal`, `create_joplin_note`,
`send_email` and `draft_email`. The last is the one that decides whether an
email draft can be swipe-approved, and the second copy of it silently replaced
the first. Nothing in the project could have seen it: the file parses, the
suites pass, and the gate answers cards perfectly well - with a risk tier
nobody chose. It was found by hand, and this is the check that should have
found it instead.

WHAT IT READS. Every `*.py` and every `*.json` in this checkout that GIT would
carry, apart from the directories listed in SKIP (build output, virtualenvs,
caches, vendored packages). Two things are left out on purpose:

  * a path `git ls-files --others --ignored --exclude-standard` names as
    ignored. On 2026-10-04 that is `dshwork/`, the audit pass's own scratch,
    which holds four whole copies of `jarvis_gate.py` under
    `audit-01-evidence/` - exactly the four `_RISK` duplicates this script was
    written for, and exactly the files a fresh CI checkout does not have. That
    is the worst of both worlds and it was the actual state: red on the owner's
    PC for files nobody will ever commit, green on CI for a reason that proves
    nothing. A skipped path is not a clean path - it is not this repository's
    file. The real copy of `jarvis_gate.py` lives on the owner's PC and is
    fixed there.
  * the directories in SKIP.

A trackable file is NEVER skipped for being inconvenient: the whole point is
that this fires on a real `_RISK`-shaped duplicate the moment one lands in a
file git carries. If git cannot say what it ignores (no `.git`, no git, a
broken repository), nothing is skipped and the check runs over the whole tree
- loudly, and with the reason printed - because a scope this script cannot
work out is not a scope it may quietly invent.

A file that will not parse is a FAILURE, not a pass: its keys were not checked,
and saying nothing about it is exactly how a check ends up green having checked
nothing (the lesson check-tokens.py writes down about its own missing files).

Two implementations decide the JSON half on purpose. The keys are found with a
small scanner, because the `json` module reports a duplicate key without saying
where it was; the stdlib's own `object_pairs_hook` then confirms the scanner
found the same ones. If the two ever disagree, that is reported as a fault in
this script rather than quietly trusted.
"""
from __future__ import annotations

import ast
import bisect
import json
import re
import subprocess
import sys
import warnings
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Directories that hold no source of ours: build output, caches, virtualenvs
# and vendored packages. `dshwork/` is deliberately NOT here any more, though
# it is gitignored scratch holding whole copies of the backend: the scratch is
# worked out from git itself (gitignored_paths below), so the skip follows the
# repository's own rules instead of a second list that could drift from them.
SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "target",
        "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache"}


def gitignored_paths() -> tuple[set[str], str]:
    """(paths git ignores, why they could not be worked out).

    One git call, asked in git's own words: `--others` is "not tracked",
    `--ignored` is "matches a .gitignore rule", `--exclude-standard` is "the
    normal rules" (.gitignore, .git/info/exclude, core.excludesFile). So a
    path in the answer is one `git check-ignore` would name, and the answer
    cannot disagree with what a clone would carry - which is the property that
    matters here, because the bug this check was written for was found in a
    copy that no clone has. git always answers with `/` separators, whatever
    the platform, so the caller compares with `as_posix()`.

    git's stderr is captured rather than shown: a scratch tree full of dead
    symlinks (`dshwork/.../_fakeroot/Epic-Jarvis-main/`) makes it warn about
    directories it cannot open, and those warnings are not this check's news.

    On failure the answer is an empty set plus the reason, and the caller
    skips NOTHING: a check that cannot work out its scope must look at too
    much rather than at too little.
    """
    try:
        done = subprocess.run(
            ["git", "-C", str(REPO), "ls-files", "--others", "--ignored",
             "--exclude-standard"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120)
    except (OSError, subprocess.SubprocessError) as err:
        return set(), f"git could not be run ({err})"
    if done.returncode != 0:
        first = (done.stderr or "").strip().splitlines()
        return set(), (f"git exited {done.returncode}"
                       + (f": {first[0]}" if first else ""))
    return {line for line in done.stdout.splitlines() if line}, ""


def tracked_sources(ignored: set[str]) -> tuple[list[Path], list[str]]:
    """(the files git carries, the files skipped because git ignores them).

    One walk of the tree, not one per question. This checkout holds about
    thirty thousand gitignored files (the audit pass's scratch) and roughly
    three thousand of them are `.py`, so a second walk to work out what would
    have been read is not free - the first version of the scope fix walked the
    tree twice and took twice the twelve seconds the check already cost.

    The SKIP directories are dropped first and are never reported as skipped
    by git: `target/` and `__pycache__/` are ignored too, but they are ignored
    for every checkout alike and listing them would drown the one line that
    matters. A build directory named deep in the tree is dropped here as well
    (`jarvis-desktop/src-tauri/target/debug/...`), which is why the whole path
    is tested and not just its top: without that, the generated Tauri schemas
    under `jarvis-desktop/src-tauri/gen/` appear as a second skipped root and
    the one line stops telling the truth about what was left out.
    """
    kept: list[Path] = []
    skipped: list[str] = []
    for path in sorted(REPO.rglob("*")):
        if path.suffix not in (".py", ".json") or not path.is_file():
            continue
        # The directory parts only: a file's own name is never a skip reason
        # (`dist.py` is not build output).
        rel = path.relative_to(REPO)
        if any(part in SKIP for part in rel.parts[:-1]):
            continue
        name = rel.as_posix()
        if ignored and name in ignored:
            skipped.append(name)
        else:
            kept.append(path)
    return kept, skipped


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else path.as_posix()


# ---------------------------------------------------------------------------
#   Python
# ---------------------------------------------------------------------------

def python_duplicates(text: str):
    """(key, line, first line) for every key written twice in ONE dict.

    Each `ast.Dict` is judged on its own, so the same key in two different
    dictionaries is fine - and `{**other, "a": 1}` is fine too, because the
    unpacking is not a constant key at all and cannot be checked without
    running the file.

    The value itself is used as the key, which is what CPython does: `{1: "a",
    True: "b"}` is a duplicate, and this reports it as one.
    """
    out = []
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Dict):
            continue
        seen: dict[object, int] = {}
        for key in node.keys:
            if not isinstance(key, ast.Constant):
                continue
            value = key.value
            if isinstance(value, (str, int, float, complex, bytes, bool, type(None))):
                try:
                    first = seen.get(value)
                except TypeError:                     # unhashable: not a dict key
                    continue
                if first is not None:
                    out.append((repr(value), key.lineno, first))
                else:
                    seen[value] = key.lineno
    return out


# ---------------------------------------------------------------------------
#   JSON - found by hand, because the stdlib does not report where
# ---------------------------------------------------------------------------

def json_duplicates(text: str):
    """(key, line, first line) for every duplicate key in one JSON object.

    A small scanner rather than a parser: `json.loads` is happy to keep the
    last value, and the position it would report is the object's, not the
    key's. It tracks one thing only - whether the string it is looking at is a
    key or a value - by keeping a frame per open object or array.

    Line numbers come from a table of newline offsets built once, NOT from
    `text[:at].count("\\n")` at each key: that is a fresh scan of the whole file
    per key, which took 101 seconds on this repository's 2.9 MB golden fixture
    and is why the first version of this script appeared to hang.
    """
    out = []
    line_starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def line_at(at: int) -> int:
        return bisect.bisect_right(line_starts, at)

    stack: list[dict] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c == "{":
            stack.append({"kind": "obj", "keys": {}, "want_key": True})
            i += 1
            continue
        if c == "[":
            stack.append({"kind": "arr"})
            i += 1
            continue
        if c in "}]":
            if stack:
                stack.pop()
            i += 1
            continue
        if c == ",":
            if stack and stack[-1]["kind"] == "obj":
                stack[-1]["want_key"] = True
            i += 1
            continue
        if c == ":":
            i += 1
            continue
        if c == '"':
            start = i
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                i += 1
            raw = text[start:i]
            if stack and stack[-1]["kind"] == "obj" and stack[-1].get("want_key"):
                try:
                    name = json.loads(raw)
                except ValueError:
                    name = raw
                line = line_at(start)
                first = stack[-1]["keys"].get(name)
                if first is not None:
                    out.append((repr(name), line, first))
                else:
                    stack[-1]["keys"][name] = line
                stack[-1]["want_key"] = False
            continue
        # A number, true, false or null: a value, never a key.
        while i < n and text[i] not in ',}]\n':
            i += 1
    return out


def stdlib_duplicate_counts(text: str) -> Counter:
    """{key: how many times it was written twice}, from the `json` module's own
    view of the file - the second opinion the scanner above is checked against."""
    counts: Counter = Counter()

    def hook(pairs):
        seen = set()
        for key, _value in pairs:
            if key in seen:
                counts[key] += 1
            seen.add(key)
        return dict(pairs)

    json.loads(text, object_pairs_hook=hook)
    return counts


# ---------------------------------------------------------------------------
#   The run
# ---------------------------------------------------------------------------

def main() -> int:
    verbose = "-v" in sys.argv
    # A way to exercise the "git cannot say" path on purpose, in a tree where
    # git can: --no-git must skip exactly as little as a broken checkout does.
    ignored, why = (set(), "asked not to with --no-git") if "--no-git" in sys.argv \
        else gitignored_paths()

    if why:
        print(f"::warning::git could not list the paths it ignores ({why}), so "
              f"NOTHING is skipped and every file in this checkout was read - "
              f"including any scratch copy of a backend file, which no clone "
              f"carries. Fix the checkout rather than this check.")

    kept, skipped_names = tracked_sources(ignored)
    python_files = [p for p in kept if p.suffix == ".py"]
    json_files = [p for p in kept if p.suffix == ".json"]
    skipped_roots: dict[str, int] = {}
    for name in skipped_names:
        root = name.split("/", 1)[0]
        skipped_roots[root] = skipped_roots.get(root, 0) + 1

    if skipped_names:
        # One line, as asked for, and the reason leads: these are not checked
        # because they are not this repository's files, not because their
        # duplicates do not matter. The real jarvis_gate.py is the owner's own
        # copy on the PC, and the four `_RISK` duplicates are fixed there.
        print(f"skipped {len(skipped_names)} file(s) git ignores "
              f"({', '.join(f'{root}/' for root in sorted(skipped_roots))}) - "
              f"scratch from an earlier audit pass, not files this repository "
              f"carries; the duplicates there are reported to the owner "
              f"separately, and the fix belongs in his own jarvis_gate.py.")
        if verbose:
            for root in sorted(skipped_roots):
                print(f"  {root}/  {skipped_roots[root]} ignored file(s)")

    python_hits: list[tuple[str, str, int, int]] = []
    unreadable: list[tuple[str, str]] = []
    for path in python_files:
        # `utf-8-sig`, because a UTF-8 BOM is a byte-order mark to Python when
        # it runs a file and a syntax error to `ast.parse` - three of the
        # scratch files in this tree are written that way, and reporting them
        # as broken Python would be this check being wrong about them.
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as err:
            unreadable.append((rel(path), str(err)))
            continue
        try:
            # A file with `"\p"` in a regex raises a SyntaxWarning, which Python
            # prints while it parses - real, but not this check's news, and it
            # buries the list of keys that is.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                found = python_duplicates(text)
        except SyntaxError as err:
            unreadable.append((rel(path), f"line {err.lineno}: {err.msg}"))
            continue
        for key, line, first in found:
            python_hits.append((rel(path), key, line, first))

    json_hits: list[tuple[str, str, int, int]] = []
    json_faults: list[tuple[str, str]] = []
    for path in json_files:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as err:
            unreadable.append((rel(path), str(err)))
            continue
        try:
            found = json_duplicates(text)
            agree = stdlib_duplicate_counts(text)
        except ValueError as err:
            unreadable.append((rel(path), f"not readable as JSON: {err}"))
            continue
        except RecursionError:
            # A JSON file nested deeper than the interpreter's stack. `json`
            # raises RecursionError, not ValueError, so this used to end the
            # whole check with a traceback and no verdict at all (2026-10-08).
            # The file is reported like any other this check cannot read.
            unreadable.append((rel(path), "nested too deeply to check (RecursionError)"))
            continue
        # The scanner reports the key as `repr`; the stdlib hands back the value
        # itself. Read the repr back rather than trimming quotes off it, which
        # would turn `"don't"` into `dont` and quietly compare two wrong things.
        mine = Counter(ast.literal_eval(key) for key, _line, _first in found)
        if mine != agree:
            json_faults.append((rel(path),
                                f"this script found {dict(mine)}, the json module "
                                f"found {dict(agree)}"))
        for key, line, first in found:
            json_hits.append((rel(path), key, line, first))

    problems = bool(python_hits or json_hits or unreadable or json_faults)

    if python_hits:
        print("::error::a Python dict literal writes the same key twice - CPython "
              "keeps the LAST one and says nothing:")
        for name, key, line, first in sorted(python_hits, key=lambda h: (h[0], h[2])):
            print(f"  {name}:{line}  {key}   (written first at line {first})")
    if json_hits:
        print("::error::a JSON object writes the same key twice - every parser that "
              "accepts it keeps the LAST one, and some refuse the file instead:")
        for name, key, line, first in sorted(json_hits, key=lambda h: (h[0], h[2])):
            print(f"  {name}:{line}  {key}   (written first at line {first})")
    if json_faults:
        print("::error::the two JSON readers disagree - this is a fault in "
              "check_literal_keys.py, not in the file:")
        for name, why in json_faults:
            print(f"  {name}  {why}")
    if unreadable:
        print("::error::a file could not be read, so its keys were NOT checked - "
              "silence here would be this check passing having checked nothing:")
        for name, why in unreadable:
            print(f"  {name}  {why}")

    if problems:
        return 1

    print(f"{len(python_files)} Python file(s) and {len(json_files)} JSON file(s) "
          f"read; no dict or object literal writes the same key twice.")
    print("A duplicate key is silent in both languages - CPython and json.loads "
          "both keep the last one, which is why this is checked rather than "
          "noticed.")
    if skipped_names:
        print(f"{len(skipped_names)} file(s) were skipped for being gitignored, not "
              f"for being clean: they are scratch this repository does not carry, "
              f"and a duplicate inside a file git would CARRY is still a failure.")
    if verbose:
        print(f"  skipped directories: {', '.join(sorted(SKIP))}")
        if why:
            print(f"  gitignored paths: not available ({why})")
        else:
            print(f"  gitignored paths: {len(ignored)} path(s) in the answer from git")
    return 0


if __name__ == "__main__":
    sys.exit(main())
