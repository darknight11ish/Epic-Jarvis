#!/usr/bin/env python3
"""Check the top-level `README.md` against the tree it describes.

WHY THIS EXISTS. `README.md` is the first page anyone reads, and it is the one
page no checker measured. On 2026-10-21 a review of it found three kinds of
false statement living on it at once:

  * it named a module, `jarvis_voice.py`, as the voice pipeline's home, after
    the shipped code had split into `jarvis_speech.py`, `jarvis_voice_flow.py`
    and `jarvis_voice_enroll.py` - so the page sent a reader to a file whose
    job no longer existed;
  * it linked documents and scripts that still have to exist for the link to
    mean anything, and nothing checked that they did;
  * it said **"The desktop installer is not published yet"** while the rolling
    `desktop-latest` release had been publishing a signed MSI and setup.exe
    for weeks, and it called two pull requests "in flight" that had merged.

That last one is the expensive kind: a beginner reads it first, and the page
that is supposed to teach them what Jarvis is tells them a download does not
exist while it does. Prose has no compiler, so this is the compiler for the
four things that can be checked mechanically.

WHAT IT CHECKS.

  1. **Every `jarvis_*.py` module the page names exists in what this
     repository ships.** The name may be bare (`jarvis_speech.py`) or carry a
     path (`backend/jarvis_speech.py`, `jarvis-backend/jarvis_speech.py`); a
     bare name is looked for in the folders that hold the shipped code -
     `backend/`, `backend/rebuilt/` and `jarvis-backend/` - and a named path
     must exist exactly.
  2. **Every `docs/*.md` and `scripts/*.ps1` path the page names exists.**
     Both `/` and `\\` separators are accepted, because the page's PowerShell
     lines write `scripts\\setup-jarvis.ps1` and its markdown links write
     `docs/INSTALL.md`.
  3. **No `#NNN` pull-request number, and none of the phrases that were stale
     on the page this one replaced** - "installer is not published", "not
     merged yet", "in flight". The project's rule is that the README talks
     about what the owner can do, not about pull requests; a number the page
     cannot keep true is a number that rots.
  4. **No Google-search rewrite links** - `https://www.google.com/search?q=`,
     the shape a chat or PDF pipeline writes when it turns a plain URL into a
     search for that URL. It happens in CONVERSION, not in the Markdown: the
     page was clean when a reader saw this, and the ruling that asked for the
     guard said so. The cheap rule is kept anyway, and it covers the page and
     every `docs/*.md`, because a corrupted copy of a document is just as
     misleading as a corrupted copy of the README.

WHAT IT DELIBERATELY DOES NOT CHECK. It does not check the page's wording,
order or claims that need judgement; it does not count documents (that is
`tools/check_docs_map.py`, whose count and size rules are left exactly as they
are); and apart from rule 4's one pattern it does not read `docs/` at all -
`docs/CLAIMS.tsv` and `docs/ABOUT-JARVIS.md` are other pages with their own
owners and their own checkers.

Run:  python -B tools/check_readme_truth.py
Exit: 0 when every reference is real and no stale phrase is on the page,
      1 otherwise, naming every bad reference and where it is.

`--readme` and `--root` point it at another copy, so a failure can be proved
without dirtying the real page (see the pull request's own bite test).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The folders that hold the code this repository ships whole. A bare
#: `jarvis_*.py` name on the page must be in one of them; anything else is a
#: module the page invented or one whose job moved (the `jarvis_voice.py` case).
SHIPPED_DIRS = ("backend", "backend/rebuilt", "jarvis-backend")

#: A module name, bare or with a path in front of it. The look-behind keeps a
#: name glued to a word or a hyphen (`ej-jarvis_foo.py`) from being read as a
#: shipped name, while a real relative path (`.\scripts\...`,
#: `backend/jarvis_speech.py`) still matches.
MODULE_RE = re.compile(r"(?<![\w-])(?:[A-Za-z0-9_.-]+[\\/])?jarvis_[A-Za-z0-9_]+\.py")

#: A document the page points at - `docs/INSTALL.md` in prose, or
#: `docs\INSTALL.md` inside a PowerShell line.
DOC_RE = re.compile(r"(?<![\w-])docs[\\/][A-Za-z0-9_.-]+\.md")

#: A PowerShell script the page points at, either separator, and whether the
#: page writes `scripts\setup-jarvis.ps1` or `.\scripts\setup-jarvis.ps1`.
SCRIPT_RE = re.compile(r"(?<![\w-])scripts[\\/][A-Za-z0-9_.-]+\.ps1")

#: A pull-request number: `#` immediately followed by two to four digits. A
#: heading (`## 4.`) has a space after the hashes and cannot match; an anchor
#: such as `#what-asks-first` has no digits and cannot match.
PR_RE = re.compile(r"(?<![\w#])#(\d{2,4})\b")

#: Phrases that were true once and are false now. The page is allowed to say
#: anything else; these three are the ones that had already rotted on it.
BANNED = (
    "installer is not published",
    "not merged yet",
    "in flight",
)

#: Rule 4: the shape a chat or PDF pipeline writes when it turns a plain URL
#: into a Google search for that URL. It is a CONVERSION artifact (the page is
#: clean, and the ruling that asked for this guard says so), kept as a cheap
#: guard because a corrupted copy of a document is as misleading as a
#: corrupted README.
GOOGLE_SEARCH_LINK = "https://www.google.com/search?q="


def check(name: str, cond: bool, detail: str = "") -> bool:
    print(f"{'ok   ' if cond else 'FAIL '} {name}")
    if detail and not cond:
        for line in detail.splitlines():
            print(f"        {line}")
    return cond


def module_exists(name: str, root: Path) -> bool:
    """Whether a `jarvis_*.py` name the page uses is real.

    A bare name is looked for in the folders that hold the shipped code (and
    the page is not required to say which one, because the same file is in
    several). A name that carries a path must exist at that path exactly - a
    wrong path is the same stale-reference failure as a wrong name.
    """
    if "/" in name or "\\" in name:
        return (root / name.replace("\\", "/")).is_file()
    return any((root / d / name).is_file() for d in SHIPPED_DIRS)


def path_exists(rel: str, root: Path) -> bool:
    return (root / rel.replace("\\", "/")).is_file()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Check README.md's file references, PR numbers and stale "
                    "phrases against the tree it describes."
    )
    parser.add_argument("--readme", default=str(ROOT / "README.md"),
                        help="the page to read (default: <root>/README.md)")
    parser.add_argument("--root", default=str(ROOT),
                        help="the tree its references are checked against")
    args = parser.parse_args(argv)

    readme = Path(args.readme)
    root = Path(args.root)
    if not readme.is_file():
        print(f"readme truth FAILED: {readme} is not a file")
        return 1
    if not root.is_dir():
        print(f"readme truth FAILED: {root} is not a directory")
        return 1

    text = readme.read_text(encoding="utf-8")
    ok = True

    # 1. Every module the page names is a module this repository ships.
    modules = sorted(set(MODULE_RE.findall(text)))
    bad_modules = [m for m in modules if not module_exists(m, root)]
    print(f"found  {len(modules)} module reference(s) in {readme.name}")
    ok &= check("every jarvis_*.py module named in the README exists",
                not bad_modules,
                "\n".join(f"{m} - not in {' or '.join(SHIPPED_DIRS)}" for m in bad_modules)
                or "")

    # 2a. Every document the page points at exists.
    docs = sorted(set(DOC_RE.findall(text)))
    bad_docs = [d for d in docs if not path_exists(d, root)]
    print(f"found  {len(docs)} document reference(s) in {readme.name}")
    ok &= check("every docs/*.md path named in the README exists",
                not bad_docs,
                "\n".join(f"{d} - there is no such file" for d in bad_docs) or "")

    # 2b. Every PowerShell script the page points at exists.
    scripts = sorted(set(SCRIPT_RE.findall(text)))
    bad_scripts = [s for s in scripts if not path_exists(s, root)]
    print(f"found  {len(scripts)} script reference(s) in {readme.name}")
    ok &= check("every scripts/*.ps1 path named in the README exists",
                not bad_scripts,
                "\n".join(f"{s} - there is no such file" for s in bad_scripts) or "")

    # 3a. No pull-request number: the page is about what Jarvis does, not
    #     about the pull requests that did it.
    prs = PR_RE.findall(text)
    ok &= check("the README names no pull-request number",
                not prs,
                ("found: " + ", ".join(f"#{n}" for n in prs)) if prs else "")

    # 3b. None of the phrases that were already stale on the page it replaced.
    lowered = text.lower()
    stale = [phrase for phrase in BANNED if phrase in lowered]
    ok &= check("the README carries none of the stale phrases it replaced",
                not stale,
                ("found: " + ", ".join(f'"{p}"' for p in stale)) if stale else "")

    # 4. No Google-search rewrite links in the page or in docs/*.md.
    scanned = 0
    offenders = []
    pages = [readme]
    docs_dir = root / "docs"
    if docs_dir.is_dir():
        pages += sorted(docs_dir.rglob("*.md"))
    for path in pages:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        scanned += 1
        for number, line in enumerate(lines, 1):
            if GOOGLE_SEARCH_LINK in line:
                try:
                    shown = path.relative_to(root)
                except ValueError:
                    shown = path.name
                offenders.append(f"{shown}:{number}")
    ok &= check(f"no Google-search rewrite links in the README or docs/ "
                f"({scanned} markdown file(s) scanned)",
                not offenders,
                "\n".join(offenders[:20]))

    if not ok:
        print("\nreadme truth FAILED. Fix the references or the stale words "
              "on the page; the check is mechanical and the page is what a "
              "new reader trusts first.")
        return 1

    print(f"\nreadme truth OK: {len(modules)} module reference(s), "
          f"{len(docs)} document reference(s), {len(scripts)} script "
          f"reference(s), no pull-request numbers, no stale phrases and no "
          f"Google-search rewrite links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
