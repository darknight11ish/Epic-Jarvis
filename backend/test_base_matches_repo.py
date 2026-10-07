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
  3. The base is complete on its own: the import walk
     `scripts/check-backend.ps1` performs finds nothing missing, and nothing
     that only `apply-patches.ps1` could supply.
  4. The non-Python files the code reads are beside it - `jarvis_hud.html`,
     the page served at "/", among them.
  5. No private, generated or superseded file was swept in: no database, no
     token, no `__pycache__`, no patcher backup folder, no legacy guide, and
     `jarvis-framework.toml` is the repository's template rather than the
     owner's live settings file.

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
import sys
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
