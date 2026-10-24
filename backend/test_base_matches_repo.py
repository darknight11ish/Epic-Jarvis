"""Is the base backend published in this repository the base these patches describe?

    python3 test_base_matches_repo.py

WHY THIS EXISTS

`backend/` is the patch directory: the patches written against the owner's
live backend, plus the tests that prove they do what they say. On 2026-10-06
that base was published as plain source in `jarvis-backend/`, so that a
stranger can clone this repository and have a backend to run rather than a
folder of patches against a folder they do not have. See
`jarvis-backend/README.md` and `docs/BACKEND-PUBLISH-INVENTORY-2026-10-06.md`.

Publishing it created the problem this suite exists for. There are now TWO
copies of every module this repository ships whole - `backend/<name>.py`, the
one `apply-patches.ps1` copies onto a backend, and `jarvis-backend/<name>.py`,
the published base - and nothing kept them in step. Nothing does now, either:
this file is the check that notices. Without it they drift, and
`apply-patches.ps1` step 3 goes on copying the repository's copy over the
published one's, on the owner's machine, every run, silently.

WHAT IT CHECKS

  1. `jarvis-backend/` is there and is a backend: the entry point, and enough
     modules that it is not a stub.
  2. Every module this repository ships whole (`backend/_where.py`'s SHIPPED
     list, plus `backend/rebuilt/`) is in the base, and the base's copy is the
     same text. Line endings are ignored, the same rule `_where._same_text()`
     uses: `.gitattributes` is `eol=lf`, and a Windows clone may hold CRLF.
     `twin_pairs()` below is the same rule extended over the BESIDE-files
     `tools/gen_base_from_backend.py` re-takes from this repository, which are
     not modules and so are not in SHIPPED - `requirements.lock` is the one
     that got past everyone on 2026-10-13 (PR #390).
  3. The base is complete on its own: the import walk
     `scripts/check-backend.ps1` performs finds nothing missing, and nothing
     that only `apply-patches.ps1` could supply.
  4. The non-Python files the code reads are beside it - `jarvis_hud.html`,
     the page served at "/", among them.
  5. No private, generated or superseded file was swept in: no database, no
     token, no `__pycache__`, no patcher backup folder, no legacy guide, and
     `jarvis-framework.toml` is the repository's template rather than the
     owner's live settings file.
  6. `tools/check_stale_twins.py` - the fast local check a person or an agent
     runs before pushing, so drift is named in a second instead of a CI round
     trip later - names exactly the files this suite names. It is checked the
     only way that means anything: on a copy of the two folders holding a
     deliberately drifted twin, where the functions above are the judge. Since
     2026-10-13 the list it is judged against is `twin_pairs()`, which is the
     modules **and** the beside-files, so the fast check can no longer report
     green while the beside-file half of the rule is broken. Since 2026-10-23
     that list keeps a leaf named by two different sources as two pairs, so the
     fast check also covers `jarvis-desktop/src/jarvis_hud.html` - the third
     copy of the page, which the old one-pair-per-leaf dedupe dropped - and the
     agreement test below drifts that copy on its own to prove it bites.

WHAT IT DOES NOT CHECK, PLAINLY

  It cannot prove the base is the state the patch stack describes. Reversing
  the stack off the base stops at `approval-notice.patch`, because
  `backend/rebuilt/jarvis_events.py` already contains the code that patch adds
  (`docs/BACKEND-PUBLISH-INVENTORY-2026-10-06.md` section 1). So the base is
  checked against THIS REPOSITORY's copies, never against the patch stack.
  That is the whole of what "a checked copy" means here, and it is why the
  patches remain the description of the owner's own install.

Needs nothing from the owner's PC; runs anywhere, including CI.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _where  # noqa: E402

REPO = _where.REPO
BACKEND = REPO / "backend"
BASE = REPO / "jarvis-backend"
FAILED, PASSED = [], []

#: The non-Python files the base's own code reads, by the name it looks for.
BESIDE = (
    "jarvis_hud.html",          # jarvis_hud.py:2226, the page served at "/"
    "jarvis-framework.toml",    # the settings template, never the owner's live file
    "requirements.lock",        # jarvis_tool_updates.py, jarvis_backup.py, jarvis_pc_help.py
    "quiz_grader_cases.json",   # eval_quiz_grader.py
    "jarvis-visual-spec.json",  # /api/visual-spec
    "rust-crates.lock",         # jarvis_tool_updates.py
    # The browser's own files (2026-10-23, PWA Slice 3a): jarvis_hud.py's
    # STATIC_ASSETS whitelist reads each from beside itself, so the page loads
    # in a browser with its theme, fonts and modules instead of 404s.
    "theme.css", "fonts.css",                                   # /theme.css, /fonts/fonts.css
    "chakra-petch-400.woff2", "chakra-petch-500.woff2",          # /fonts/*
    "chakra-petch-600.woff2", "chakra-petch-700.woff2",
    "ibm-plex-mono-400.woff2", "ibm-plex-mono-500.woff2",
    "ibm-plex-sans-400.woff2",
    "lane-warning.js", "hud-actions.js", "hud-safety.js", "hud-edit.js",
    "hud-presets.js", "private-speech.js", "face-voice.js", "face-moments.js",
    "face-tuning.js", "animal-shared.js", "hud-layout.js",
    "hud-layout-store.js",                                      # /<module>.js
    # PWA Slice 2's browser bridge: the page loads it with a <script src>, so
    # the whitelist serves it like the modules above (delivery fix F1).
    "hud-web-bridge.js",                                        # /hud-web-bridge.js
    # PWA Slice 3b: the manifest, the service worker and the home-screen
    # icons the page/worker/manifest ask for; served from beside the server.
    "manifest.webmanifest",                                     # /manifest.webmanifest
    "sw.js",                                                    # /sw.js
    "jarvis-180.png", "jarvis-192.png", "jarvis-512.png",       # /icons/*
)

#: What must never be in the base: (pattern on the name, why).
FORBIDDEN = (
    (r"^__pycache__$|\.pyc$", "bytecode; it embeds absolute paths, and git ignores it"),
    (r"\.db$|\.sqlite$|\.db-wal$|\.db-shm$", "one of the owner's databases - memory, chats, approvals"),
    (r"^token$|cloud-keys", "a credential file"),
    (r"\.bak$|\.before-", "a stale second copy of a file"),
    (r"^_jarvis-backup-", "the patcher's before-images of security-relevant files"),
    (r"^_jarvis-logs$", "the patcher's transcripts; one names the owner's path 231 times"),
    (r"^\.env$|^\.env\.", "local secrets"),
    (r"^test_.*\.py$", "the tests are the repository's, and a base carries none"),
    (r"^patch_openjarvis\.py$|^spike_sandbox\.py$", "a tool for a different project, and an experiment"),
    (r"^shell\.html$|reactor-kit|^faces_(helpers|bodies)\.js$", "the superseded front-end; no module reads them"),
    (r"^(JARVIS-API|JARVIS-EXPLAINED|JARVIS-FRAMEWORK|DESKTOP-BUILD|DESKTOP-UPDATE-PROMPT|ANDROID-VOICE-PROMPT)\.md$",
     "a legacy guide, superseded by docs/"),
)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def same_text(a: Path, b: Path) -> bool:
    """`_where._same_text`'s rule: line endings do not count."""
    return (a.read_bytes().replace(b"\r\n", b"\n")
            == b.read_bytes().replace(b"\r\n", b"\n"))


def shipped_pairs() -> list:
    """(leaf name in the base, this repository's copy) for every module this
    repository ships whole, read from `_where.SHIPPED` rather than copied, so
    a module added to that list is checked here without an edit."""
    pairs = [(n.rsplit("/", 1)[-1], BACKEND / n) for n in _where.SHIPPED]
    pairs += [(p.name, p) for p in sorted((BACKEND / "rebuilt").glob("*.py"))]
    pairs.append(("jarvis-framework.toml", BACKEND / "rebuilt" / "jarvis-framework.toml"))
    seen, out = set(), []
    for leaf, ours in pairs:
        if leaf not in seen:
            seen.add(leaf)
            out.append((leaf, ours))
    return out


def _beside_twins_from_the_rule() -> tuple:
    """(leaf in the base, where this repository keeps its copy) for the
    BESIDE-files this repository owns.

    Read out of `tools/gen_base_from_backend.py`'s own `BESIDE` and
    `BESIDE_BINARY` tables - the tables the re-take rule is - rather than
    restated, so a file added there is checked here with no edit to this file.
    `BESIDE_BINARY` is the seven woff2 faces PWA Slice 3a serves: their base
    copies are byte-identical, and `same_text()` below still compares them
    correctly because both sides hold the same bytes (the line-ending
    normalisation cannot make two different binary files equal). Filtered to
    the entries whose source is this repository: `jarvis-visual-spec.json`
    comes from the owner's live backend folder (`{source}/`), which is not in
    this repository and is not in CI, so there is no copy here to compare it
    with.

    `_where.py` is deliberately NOT here. It lands under `DERIVED_FROM_REPO`,
    not `BESIDE`, and the base's copy is this repository's copy PLUS
    `BASE_WHERE_TRAILER` - so it is a different text by design, and
    `same_text()` would report the rule working as a difference.
    `backend/test_base_regeneration.py` compares it with its own rule.

    Paths are kept relative to the repository root, because `beside_pairs()`
    resolves them from `BACKEND` at call time. A `tools/gen_base_from_backend.py`
    that will not import is a hard failure on purpose: a check that cannot read
    its rule must say so, never quietly check less.
    """
    sys.path.insert(0, str(REPO / "tools"))
    try:
        import gen_base_from_backend as gen        # noqa: PLC0415
    finally:
        sys.path.remove(str(REPO / "tools"))
    out = []
    for name, where, _why in gen.BESIDE + gen.BESIDE_BINARY:
        if "{source}" in where:
            continue
        at = Path(where.format(repo=REPO.as_posix(), source=""))
        out.append((name, at.relative_to(REPO).as_posix()))
    return tuple(out)


#: The beside-files this repository owns: (leaf in the base, its path here).
BESIDE_TWINS = _beside_twins_from_the_rule()


def beside_pairs() -> list:
    """(leaf name in the base, this repository's copy) for BESIDE_TWINS.

    Resolved from `BACKEND.parent` rather than `REPO` so that `rule_finds()`
    below can point the whole rule - modules and beside-files together - at a
    copy of the two folders in a temp folder.
    """
    root = BACKEND.parent
    return [(leaf, root / rel) for leaf, rel in BESIDE_TWINS]


def twin_pairs() -> list:
    """Every file the base's copy must hold as this repository's copy: the
    modules shipped whole, and the beside-files this repository owns.

    This is the list `tools/check_stale_twins.py` checks, so the fast local
    check answers the question a person actually has before pushing - "is the
    base still this repository's copy?" - and not only the module half of it.
    On 2026-10-13 the module half was green and `requirements.lock` was stale;
    see `BESIDE_TWINS` for the two beside-files that are deliberately not here.

    The modules come first, and a pair seen twice is dropped. THE SAME LEAF FROM
    TWO DIFFERENT SOURCES IS NOT DROPPED (2026-10-23): a file named by both
    lists can have two copies in this repository, and dropping one left it
    unchecked. `jarvis-framework.toml` is the same path in both lists, so it
    contributes one pair either way. `jarvis_hud.html` is the one that differs:
    `_where.SHIPPED` lists it (the page served at "/", added 2026-10-07 because
    the patcher never copied it), which is why there is also a
    `backend/jarvis_hud.html` for `test_shipped_modules.py` to find, while
    `tools/gen_base_from_backend.py` re-takes that page from
    `jarvis-desktop/src/`. All three copies are the same text today; before
    2026-10-23 the dedupe kept only the SHIPPED pair, so a drifted desktop page
    went unnoticed by this rule and by `tools/check_stale_twins.py`, and only
    `t_the_files_beside_the_code_are_there` caught it in CI. Now the desktop
    page is a pair here too, and the fast check compares every pair against the
    base.
    """
    seen, out = set(), []
    for leaf, ours in shipped_pairs() + beside_pairs():
        if (leaf, ours) not in seen:
            seen.add((leaf, ours))
            out.append((leaf, ours))
    return out


def t_the_base_is_there_and_is_a_backend():
    check("jarvis-backend/ is in this repository", BASE.is_dir(), str(BASE))
    check("... and holds the entry point, jarvis_hud.py", (BASE / "jarvis_hud.py").is_file())
    n = len(list(BASE.glob("*.py")))
    check("... and is not a stub (150 or more top-level modules)",
          n >= 150, f"{n} top-level .py file(s)")


def t_every_shipped_module_is_in_the_base():
    pairs = shipped_pairs()
    absent = [leaf for leaf, _ours in pairs if not (BASE / leaf).is_file()]
    check(f"all {len(pairs)} modules this repository ships whole are in the base",
          not absent, "not in jarvis-backend/: " + ", ".join(sorted(absent)))


def t_the_base_copies_are_the_same_text():
    pairs = shipped_pairs()
    differ, uncomparable = [], []
    for leaf, ours in pairs:
        theirs = BASE / leaf
        if not theirs.is_file() or not ours.is_file():
            uncomparable.append(leaf)
            continue
        if not same_text(theirs, ours):
            differ.append(f"{leaf} (base {theirs.stat().st_size} B, repository {ours.stat().st_size} B)")
    check(f"the base's copy of each of those {len(pairs)} files is this repository's copy",
          not differ,
          "these differ: " + "; ".join(differ)
          + " - copy backend/<name> (or backend/rebuilt/<name>) over jarvis-backend/ after a change")
    check("... and every one of them could be compared (none missing on either side)",
          not uncomparable, "no copy on one side: " + ", ".join(sorted(uncomparable)))


# ---------------------------------------------------------------------------
#   tools/check_stale_twins.py - the fast local half of this same rule
# ---------------------------------------------------------------------------
#
# That tool exists because this suite reports in CI's `backend` job, after the
# `frontend` job has taken its time: on 2026-10-10 three pull requests (#167,
# #173, #175) each failed a full CI round trip over one or two omitted copies.
# It reuses this file's own `shipped_pairs()` and `same_text()` rather than
# restating them, and the checks below are what makes that claim mean
# something: on a copy of the two folders holding a deliberately drifted twin,
# THE FUNCTIONS ABOVE ARE THE JUDGE, and the tool must name exactly the files
# they name. A tool that disagrees with the rule is worse than no tool, so this
# is not a promise in a comment.

CHECKER = REPO / "tools" / "check_stale_twins.py"
DIFFER_PREFIX, MISSING_PREFIX = "stale twin: ", "missing twin: "


def run_checker(root: Path) -> tuple:
    """(exit code, everything the fast check printed) for one folder."""
    done = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def named_by_checker(out: str) -> set:
    """The files the fast check reported, read from the two lines it prints."""
    found = set()
    for line in out.splitlines():
        for prefix in (DIFFER_PREFIX, MISSING_PREFIX):
            if line.startswith(prefix):
                found.add(line[len(prefix):].split("  ")[0].strip())
    return found


def rule_finds(backend: Path, base: Path, shipped: tuple) -> tuple:
    """What THIS suite says about another pair of folders: (differ, missing).

    `twin_pairs()` reads the module globals BACKEND and `_where.SHIPPED` - and
    `beside_pairs()` reads BACKEND too, keeping its paths relative to the
    repository root - so all of them are swapped for the length of the call and
    the beside-files follow the copy. The rule's own code is not copied: that
    is what makes the comparison an agreement rather than two independent
    guesses that happen to match today.
    """
    global BACKEND, BASE
    saved = (BACKEND, BASE, _where.SHIPPED)
    try:
        BACKEND, BASE = backend, base
        _where.SHIPPED = shipped
        differ, missing = set(), set()
        for leaf, ours in twin_pairs():
            theirs = BASE / leaf
            if not theirs.is_file() or not ours.is_file():
                missing.add(leaf)
            elif not same_text(theirs, ours):
                differ.add(leaf)
        return differ, missing
    finally:
        BACKEND, BASE, _where.SHIPPED = saved


def twin_fixture(work: Path) -> tuple:
    """A copy of the two folders holding just two real shipped modules and the
    one file that is both a module and a beside-file.

    Built from `_where.SHIPPED` itself, so the names are ones the rule really
    lists and the fixture cannot rot as that list changes - one top-level
    module and one `rebuilt/` module, plus `jarvis-framework.toml`, which
    `shipped_pairs()` adds whether or not SHIPPED names it. On top of those it
    adds the overlap file (2026-10-23): the one leaf `shipped_pairs()` and
    `BESIDE_TWINS` both name, which today is `jarvis_hud.html`. That leaf gives
    the fixture all three real copies - `backend/`, `jarvis-backend/` and the
    BESIDE source under `jarvis-desktop/src/` - so the agreement test below can
    drift the desktop copy on its own and prove the fast check now sees it.

    The copy's own `_where.py` carries a trimmed SHIPPED, which is how the fast
    check is told which files this copy is about, and its own
    `test_base_matches_repo.py` is the rule the fast check loads.

    It carries `tools/gen_base_from_backend.py` too, because the rule now reads
    `BESIDE_TWINS` out of it, and every BESIDE-file that file names as this
    repository's - at the same path relative to the copy's root, which is where
    the copy's own rule looks for it. A fixture that skipped them would make
    the fast check report them missing and turn the agreement below into a red
    run about the fixture.
    """
    top = next(n for n in _where.SHIPPED if "/" not in n)
    rebuilt = next(n for n in _where.SHIPPED if n.startswith("rebuilt/"))
    beside_leaves = {leaf for leaf, _rel in BESIDE_TWINS}
    overlap_leaf = next((leaf for leaf, _ours in shipped_pairs()
                         if leaf in beside_leaves), None)
    overlap_rel = dict(BESIDE_TWINS).get(overlap_leaf) if overlap_leaf else None
    overlap_source = next((ours for leaf, ours in shipped_pairs()
                           if leaf == overlap_leaf), None)
    shipped = (rebuilt, top) + ((overlap_leaf,) if overlap_leaf else ())
    copy = work / "copy"
    (copy / "backend" / "rebuilt").mkdir(parents=True)
    (copy / "jarvis-backend").mkdir()
    (copy / "tools").mkdir()
    for name in ("_where.py", "test_base_matches_repo.py"):
        shutil.copyfile(BACKEND / name, copy / "backend" / name)
    shutil.copyfile(REPO / "tools" / "gen_base_from_backend.py",
                    copy / "tools" / "gen_base_from_backend.py")
    with (copy / "backend" / "_where.py").open("a", encoding="utf-8",
                                               newline="\n") as handle:
        handle.write("\n\n# the agreement test's own list\nSHIPPED = %r\n"
                     % (shipped,))
    sources = ["rebuilt/jarvis-framework.toml", rebuilt, top]
    if overlap_source is not None:
        sources.append(overlap_source.relative_to(BACKEND).as_posix())
    for name in sources:
        leaf = name.rsplit("/", 1)[-1]
        shutil.copyfile(BACKEND / name, copy / "backend" / name)
        shutil.copyfile(BACKEND / name, copy / "jarvis-backend" / leaf)
    for leaf, rel in BESIDE_TWINS:
        here = copy / rel
        here.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, here)
        shutil.copyfile(REPO / rel, copy / "jarvis-backend" / leaf)
    return (copy, shipped, top.rsplit("/", 1)[-1],
            rebuilt.rsplit("/", 1)[-1], overlap_leaf, overlap_rel)


def t_the_stale_twin_check_agrees_with_the_rule():
    check("tools/check_stale_twins.py, the fast local twin check, is here",
          CHECKER.is_file(), str(CHECKER))
    if not CHECKER.is_file():
        return
    work = Path(tempfile.mkdtemp(prefix="twin-guard-"))
    try:
        copy, shipped, top_leaf, rebuilt_leaf, overlap_leaf, overlap_rel = twin_fixture(work)
        backend, base = copy / "backend", copy / "jarvis-backend"

        code, out = run_checker(copy)
        differ, missing = rule_finds(backend, base, shipped)
        check("the copies agree on a matching pair of folders, so a red run "
              "below is the drift and not the fixture",
              code == 0 and not differ and not missing
              and not named_by_checker(out),
              f"the tool exited {code}: {out}")

        drifted = base / top_leaf
        drifted.write_bytes(drifted.read_bytes()
                            + b"# drifted by the agreement test\n")
        code, out = run_checker(copy)
        differ, missing = rule_finds(backend, base, shipped)
        check(f"a drifted twin is red, and the tool names the same file this "
              f"suite does ({top_leaf})",
              code == 1 and differ == {top_leaf}
              and named_by_checker(out) == differ | missing,
              f"the tool named {sorted(named_by_checker(out))} and exited "
              f"{code}; this suite says differ={sorted(differ)}, "
              f"missing={sorted(missing)}")

        shutil.copyfile(backend / top_leaf, drifted)
        code, out = run_checker(copy)
        check("... and green again once that file is copied back",
              code == 0 and not named_by_checker(out),
              f"the tool exited {code}: {out}")

        twin = base / rebuilt_leaf
        twin.write_bytes((backend / "rebuilt" / rebuilt_leaf).read_bytes()
                         .replace(b"\n", b"\r\n"))
        code, out = run_checker(copy)
        check("a twin that differs only in line endings is green, the rule "
              "_where._same_text() uses (a Windows clone holds CRLF)",
              code == 0 and not named_by_checker(out),
              f"the tool exited {code}: {out}")
        shutil.copyfile(backend / "rebuilt" / rebuilt_leaf, twin)

        (base / top_leaf).unlink()
        code, out = run_checker(copy)
        differ, missing = rule_finds(backend, base, shipped)
        check(f"a twin missing from the base is red too, and named "
              f"({top_leaf}) - the suite fails for that as well",
              code == 1 and missing == {top_leaf}
              and named_by_checker(out) == differ | missing,
              f"the tool named {sorted(named_by_checker(out))} and exited "
              f"{code}; this suite says differ={sorted(differ)}, "
              f"missing={sorted(missing)}")
        shutil.copyfile(backend / top_leaf, base / top_leaf)

        # The beside-file half of the rule, one file at a time, because that is
        # the half that was silently uncovered until 2026-10-13: PR #390 added
        # rapidocr to `backend/requirements.lock`, left
        # `jarvis-backend/requirements.lock` as it was, and the fast check
        # reported 191 of 191 modules matching while CI went red. Every entry
        # is proved, not only the one that bit, and the names come from the
        # rule's own table rather than from this test.
        for beside_leaf, _rel in BESIDE_TWINS:
            theirs = base / beside_leaf
            keep = theirs.read_bytes()
            theirs.write_bytes(keep + b"# drifted by the agreement test\n")
            code, out = run_checker(copy)
            differ, missing = rule_finds(backend, base, shipped)
            check(f"a drifted beside-file is red as well, and the tool names it "
                  f"({beside_leaf}) - this is the half of the rule that let "
                  f"requirements.lock through on 2026-10-13",
                  code == 1 and differ == {beside_leaf}
                  and named_by_checker(out) == differ | missing,
                  f"the tool named {sorted(named_by_checker(out))} and exited "
                  f"{code}; this suite says differ={sorted(differ)}, "
                  f"missing={sorted(missing)}")
            theirs.write_bytes(keep)
            code, out = run_checker(copy)
            check(f"... and green again once {beside_leaf} is put back",
                  code == 0 and not named_by_checker(out),
                  f"the tool exited {code}: {out}")

        # The overlap of the two lists, which is a third copy of the same file.
        # `jarvis_hud.html` is in `_where.SHIPPED` (so `backend/` holds a copy
        # for the module tests) and in the BESIDE table (so the base is re-taken
        # from `jarvis-desktop/src/`). Until 2026-10-23 `twin_pairs()` dropped a
        # leaf seen twice and kept the SHIPPED pair, so a desktop page that
        # drifted - while `backend/` and the base still agreed - was green in
        # the fast check and only red in this suite. This is that bite.
        check("the fixture holds the file that is both a SHIPPED module and a "
              "BESIDE file, so the three-copy case is exercised",
              overlap_leaf is not None and overlap_rel is not None
              and (copy / overlap_rel).is_file()
              and (backend / overlap_leaf).is_file(),
              f"overlap leaf={overlap_leaf!r}, beside path={overlap_rel!r}")
        if overlap_leaf is not None and overlap_rel is not None:
            desktop = copy / overlap_rel
            keep = desktop.read_bytes()
            desktop.write_bytes(keep + b"# desktop copy drifted by the agreement test\n")
            code, out = run_checker(copy)
            differ, missing = rule_finds(backend, base, shipped)
            check(f"a desktop-only drift is red, and the tool names the file "
                  f"({overlap_leaf}) - the copy the old dedupe dropped",
                  code == 1 and differ == {overlap_leaf}
                  and named_by_checker(out) == differ | missing,
                  f"the tool named {sorted(named_by_checker(out))} and exited "
                  f"{code}; this suite says differ={sorted(differ)}, "
                  f"missing={sorted(missing)}")
            desktop.write_bytes(keep)
            code, out = run_checker(copy)
            check("... and green again once the desktop copy is put back",
                  code == 0 and not named_by_checker(out),
                  f"the tool exited {code}: {out}")

        empty = work / "no-rule-here"
        empty.mkdir()
        code, out = run_checker(empty)
        check("a folder with no rule in it is a failure the tool reports, "
              "never a quiet pass",
              code == 1 and "could not be read" in out,
              f"the tool exited {code}: {out}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def t_the_base_is_complete_on_its_own():
    """`scripts/check-backend.ps1`'s walk, in Python and in the same shape:
    only the project's own `jarvis_*` names count, the name after `from` is
    the module, and the names after `import a, b as c` are all modules. Run
    here against the base, it must find nothing missing - a stranger has no
    apply-patches.ps1 run to make up the difference."""
    need = {}
    for f in sorted(BASE.glob("*.py")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            mods = []
            m = re.match(r"^\s*from\s+([A-Za-z_][A-Za-z0-9_\.]*)\s+import\s", line)
            if m:
                mods = [m.group(1)]
            else:
                m = re.match(r"^\s*import\s+(.+?)\s*(#.*)?$", line)
                if m:
                    for part in m.group(1).split(","):
                        name = part.split(" as ")[0].strip()
                        if name:
                            mods.append(name)
            for mod in mods:
                top = mod.split(".")[0]
                if not top.startswith("jarvis_"):
                    continue
                need.setdefault(top, set()).add(f.name)

    have = {n for n in need if (BASE / f"{n}.py").is_file()}
    shipped = {n.rsplit("/", 1)[-1][:-3] for n in _where.SHIPPED}
    coming = sorted(n for n in need if n not in have and n in shipped)
    missing = sorted(n for n in need if n not in have and n not in shipped)
    check(f"the base's own imports close ({len(need)} modules needed by the base)",
          len(need) > 100 and not missing,
          (f"{len(missing)} missing: "
           + ", ".join(f"{n} ({len(need[n])} file(s) import it)" for n in missing)) if missing
          else f"only {len(need)} modules found - the walk did not read the folder")
    check("... and none of the base's own imports is left for apply-patches.ps1 to copy in",
          not coming, "the base lacks: " + ", ".join(coming))


def t_the_files_beside_the_code_are_there():
    absent = [n for n in BESIDE if not (BASE / n).is_file() or (BASE / n).stat().st_size == 0]
    check(f"the {len(BESIDE)} non-Python files the base's code reads are in it",
          not absent, "missing or empty: " + ", ".join(absent))
    page, page_src = BASE / "jarvis_hud.html", REPO / "jarvis-desktop" / "src" / "jarvis_hud.html"
    check("... and jarvis_hud.html is beside jarvis_hud.py, and is the page this repository ships",
          page.is_file() and page_src.is_file() and same_text(page, page_src),
          "jarvis_hud.py:2226 serves HERE/jarvis_hud.html at \"/\"; without it that URL answers HTTP 500")


def t_no_private_or_generated_file_was_swept_in():
    bad = []
    for p in sorted(BASE.rglob("*")):
        name = p.name + ("/" if p.is_dir() else "")
        for pattern, why in FORBIDDEN:
            if re.search(pattern, p.name):
                bad.append(f"{p.relative_to(BASE).as_posix()}{'/' if p.is_dir() else ''} - {why}")
    check("no private, generated or superseded file is in the base",
          not bad, "; ".join(sorted(set(bad))))


def t_the_settings_file_is_the_template():
    theirs = BASE / "jarvis-framework.toml"
    ours = BACKEND / "rebuilt" / "jarvis-framework.toml"
    check("jarvis-framework.toml is the repository's template, not the owner's live settings",
          theirs.is_file() and ours.is_file() and same_text(theirs, ours),
          "the owner's live file is smaller and is missing 23 settings the template has, so a "
          "new user given it would run with features off (docs/BACKEND-PUBLISH-INVENTORY-2026-10-06.md section 3)")


def t_the_base_says_what_it_is():
    readme = BASE / "README.md"
    text = readme.read_text(encoding="utf-8", errors="replace") if readme.is_file() else ""
    check("jarvis-backend/README.md says what the folder is, where it came from and what it is not",
          bool(text)
          and "BACKEND-PUBLISH-INVENTORY-2026-10-06" in text
          and "patch" in text
          and "not" in text,
          f"{len(text)} characters read from {readme}")


if __name__ == "__main__":
    for fn in (t_the_base_is_there_and_is_a_backend,
               t_every_shipped_module_is_in_the_base,
               t_the_base_copies_are_the_same_text,
               t_the_stale_twin_check_agrees_with_the_rule,
               t_the_base_is_complete_on_its_own,
               t_the_files_beside_the_code_are_there,
               t_no_private_or_generated_file_was_swept_in,
               t_the_settings_file_is_the_template,
               t_the_base_says_what_it_is):
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
