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
  5. **The HUD layout count the page states equals the desktop's own
     `contract/hud-presets.json`** (coherence audit F13, 2026-10-22; Gemini
     ruling Q6). The page had said "three flagship layouts ... plus seven
     built-in HUD layout presets", but the seven presets INCLUDE those three,
     so the page counted ten where the tree has seven; and it said the seven
     were "chosen with the pill in its header", while the header pill could
     only switch the old three-way look (the seven are chosen in Settings or
     edited in the window). The count is read from the contract, so this rule
     cannot go stale when a preset is added. The rule also refuses the
     double-count shape and any claim that a header pill chooses the presets.
     It is the one FEATURE claim the checker can count, and it is here because
     the word "seven" on the first page was wrong while every reference rule
     above it was green.

WHAT IT DELIBERATELY DOES NOT CHECK. It does not check the page's wording,
order or claims that need judgement - only the one countable feature claim in
rule 5. It does not count documents (that is `tools/check_docs_map.py`, whose
count and size rules are left exactly as they are); and apart from rule 4's one
pattern and rule 5's contract read it does not read `docs/` at all -
`docs/CLAIMS.tsv` and `docs/ABOUT-JARVIS.md` are other pages with their own
owners and their own checkers.

Run:  python -B tools/check_readme_truth.py
      python -B tools/check_readme_truth.py --bite   (proves rule 5 can fail)
Exit: 0 when every reference is real, no stale phrase is on the page, and the
      HUD layout count matches the contract; 1 otherwise, naming every bad
      reference and where it is.

`--readme` and `--root` point it at another copy, so a failure can be proved
without dirtying the real page (see the pull request's own bite test).
`--bite` writes mutated README copies to a temporary directory and proves the
five rule-5 shapes pass/fail as intended; it is kept in the tool, rather than
in a source pin, so the proof travels with the check.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
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

#: Rule 5: the desktop HUD's own contract. The README states how many built-in
#: HUD layouts the big window has; that number must equal the number of
#: presets this file really holds. The contract is the desktop's mirror of
#: `jarvis-desktop/src/hud-layout.js` (its own tests fail if the two drift), so
#: reading it here cannot disagree with the app.
HUD_PRESETS_JSON = "contract/hud-presets.json"

#: Number words the page may use. The count is 7 today; the rule is written for
#: any count so it does not need editing when a preset is added.
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20,
}
WORDS_BY_NUMBER = {value: word for word, value in NUMBER_WORDS.items()}

#: "seven built-in HUD layouts" / "seven HUD layouts" - the count this page
#: states. The optional `built-in` lets either wording pass.
HUD_LAYOUT_COUNT_RE = re.compile(
    r"(?i)\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"\d{1,2})\s+(?:built-in\s+)?HUD\s+layouts?\b")

#: "seven built-in HUD layout presets" - the same claim with the word
#: `presets` after it. Kept separate so either sentence shape is counted; both
#: resolve to the same number.
HUD_PRESET_COUNT_RE = re.compile(
    r"(?i)\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"\d{1,2})\s+(?:built-in\s+)?HUD\s+layout\s+presets?\b")

#: The double-count shape that was on the page: "three flagship layouts ...
#: plus seven built-in HUD layout presets". The seven INCLUDE the three, so
#: the sentence counts ten things where the tree has seven.
HUD_DOUBLE_COUNT_RE = re.compile(
    r"(?i)\b(?:three|3)\b[^.\n]{0,80}\blayouts?\b[^.\n]{0,120}\bplus\b")

#: The header-pill claim that was on the page: the pill could only switch the
#: old three-way look, never one of the seven presets. Any of these shapes is
#: the claim coming back - a plain "layout pill", or "pill" in the same
#: sentence as the presets / the number.
HUD_PILL_CLAIM_RES = (
    re.compile(r"(?i)\blayout\s+pill\b"),
    re.compile(r"(?i)\bpill\b[^.\n]{0,120}\b(?:seven|presets?)\b"),
    re.compile(r"(?i)\b(?:seven|presets?)\b[^.\n]{0,120}\bpill\b"),
)


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


# --------------------------------------------------------------------------
# Rule 5: the one feature claim the page makes that can be counted.
# --------------------------------------------------------------------------

def hud_preset_count(root: Path) -> tuple[int | None, str]:
    """How many built-in HUD layouts the desktop contract really holds.

    Reads `contract/hud-presets.json` (the desktop's own mirror of
    `jarvis-desktop/src/hud-layout.js`) and returns `(count, why_not)`. A
    missing or unreadable contract is reported as such rather than passing:
    the page's count claim cannot be checked against nothing.
    """
    path = root / HUD_PRESETS_JSON
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, f"{HUD_PRESETS_JSON} cannot be read ({exc})"
    except ValueError as exc:
        return None, f"{HUD_PRESETS_JSON} is not valid JSON ({exc})"
    presets = data.get("presets") if isinstance(data, dict) else None
    if not isinstance(presets, list) or not presets:
        return None, f"{HUD_PRESETS_JSON} has no non-empty `presets` list"
    return len(presets), ""


def hud_count_claims(text: str) -> list[tuple[int, int, str, int]]:
    """Every HUD layout count the page states, as `(start, end, phrase, n)`.

    Both sentence shapes are read ("seven built-in HUD layouts" and "seven
    built-in HUD layout presets"); when they overlap at the same start the
    longer phrase is kept so the failure names the whole phrase.
    """
    claims: list[tuple[int, int, str, int]] = []
    for pattern in (HUD_LAYOUT_COUNT_RE, HUD_PRESET_COUNT_RE):
        for match in pattern.finditer(text):
            raw = match.group(1).lower()
            value = int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw)
            if value is None:
                continue
            claims.append((match.start(), match.end(), match.group(0).strip(), value))
    claims.sort(key=lambda c: (c[0], -c[1]))
    deduped: list[tuple[int, int, str, int]] = []
    for claim in claims:
        if deduped and claim[0] == deduped[-1][0]:
            if claim[1] > deduped[-1][1]:
                deduped[-1] = claim
        else:
            deduped.append(claim)
    return deduped


def rule5_problems(text: str, root: Path) -> tuple[int | None, list[str]]:
    """The problems rule 5 finds in `text`, and the contract's count.

    Four checks, all mechanical:
      * the contract gives a count at all;
      * the page states the count (a page that drops it cannot be checked);
      * every count it states equals the contract;
      * none of the two wrong shapes is back (the "three ... plus ..." double
        count, and a header pill choosing the presets).
    """
    expected, why = hud_preset_count(root)
    problems: list[str] = []
    if expected is None:
        return None, [why]
    claims = hud_count_claims(text)
    if not claims:
        problems.append(
            "the README states no HUD layout count; it must name how many "
            f"built-in HUD layouts the window has ({expected})")
    for _start, _end, phrase, value in claims:
        if value != expected:
            problems.append(
                f'"{phrase}" says {value}, but {HUD_PRESETS_JSON} holds {expected}')
    for match in HUD_DOUBLE_COUNT_RE.finditer(text):
        problems.append(
            'double-counted HUD layouts: '
            f'"{match.group(0).strip()}" - the seven presets INCLUDE the three '
            f'flagship looks, so the page must not add them ({expected} total)')
    for pattern in HUD_PILL_CLAIM_RES:
        for match in pattern.finditer(text):
            problems.append(
                'a header pill is claimed to choose the HUD layouts: '
                f'"{match.group(0).strip()}" - the seven are chosen in Settings '
                "or edited in the window")
    return expected, problems


def _synthetic_page(word: str, shape: str) -> str:
    """One bite-test page, written in the shape being tested."""
    if shape == "good":
        return f"The big window has {word} built-in HUD layouts, including the three flagship looks."
    if shape == "double":
        return ("Three flagship layouts - Command Cockpit, Studio Split-Workspace "
                f"and Ambient Voice Core - plus {word} built-in HUD layout presets.")
    if shape == "pill":
        return f"The layout pill in its header chooses among the {word} presets."
    if shape == "wrong":
        return f"The big window has {word} built-in HUD layouts."
    raise ValueError(shape)


def run_bite(root: Path) -> bool:
    """Prove rule 5 can pass and fail, without touching the real README.

    Writes mutated copies of a tiny page into a temporary directory and runs
    rule 5 against each, with the real tree's contract. No source pin: the
    count comes from the contract, so this proof does not need editing when a
    preset is added. Run with `--bite`.
    """
    expected, why = hud_preset_count(root)
    if expected is None:
        print(f"readme truth bite FAILED: {why}")
        return False
    word = WORDS_BY_NUMBER.get(expected, str(expected))
    wrong = WORDS_BY_NUMBER.get(expected + 1, str(expected + 1))
    cases = (
        ("a page that states the real count passes", _synthetic_page(word, "good"), True),
        ("the old double-count shape fails", _synthetic_page(word, "double"), False),
        ("a header-pill claim fails", _synthetic_page(word, "pill"), False),
        ("a wrong count fails", _synthetic_page(wrong, "wrong"), False),
    )
    ok = True
    with tempfile.TemporaryDirectory(prefix="readme-truth-bite-") as tmp:
        tmp_page = Path(tmp) / "README.md"
        for name, page, should_pass in cases:
            tmp_page.write_text(page, encoding="utf-8")
            got_expected, problems = rule5_problems(page, root)
            passed = got_expected == expected and not problems
            good = passed == should_pass
            print(f"{'ok  ' if good else 'FAIL'} bite: {name}")
            if not good:
                ok = False
                if should_pass:
                    for problem in problems:
                        print(f"        unexpected: {problem}")
                else:
                    print("        the mutation was NOT caught")
        tmp_page.unlink()
    print(f"\nreadme truth bite OK: 4 shapes against {expected} contract preset(s)"
          if ok else "\nreadme truth bite FAILED: rule 5 did not behave as intended")
    return ok


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Check README.md's file references, PR numbers, stale "
                    "phrases and HUD layout count against the tree it describes."
    )
    parser.add_argument("--readme", default=str(ROOT / "README.md"),
                        help="the page to read (default: <root>/README.md)")
    parser.add_argument("--root", default=str(ROOT),
                        help="the tree its references are checked against")
    parser.add_argument("--bite", action="store_true",
                        help="prove rule 5 can pass and fail, using mutated "
                             "copies of a tiny page in a temporary directory")
    args = parser.parse_args(argv)

    readme = Path(args.readme)
    root = Path(args.root)
    if not root.is_dir():
        print(f"readme truth FAILED: {root} is not a directory")
        return 1
    if args.bite:
        return 0 if run_bite(root) else 1
    if not readme.is_file():
        print(f"readme truth FAILED: {readme} is not a file")
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

    # 5. The one countable feature claim: the HUD layout count, against the
    #    desktop's own contract. See the docstring for why this is a rule.
    expected, problems = rule5_problems(text, root)
    if expected is not None:
        claims = hud_count_claims(text)
        print(f"found  {len(claims)} HUD layout count claim(s) in {readme.name}; "
              f"{HUD_PRESETS_JSON} holds {expected}")
    ok &= check("the README's HUD layout count matches the desktop's contract",
                not problems,
                "\n".join(problems))

    if not ok:
        print("\nreadme truth FAILED. Fix the references, the stale words or "
              "the layout count on the page; the check is mechanical and the "
              "page is what a new reader trusts first.")
        return 1

    print(f"\nreadme truth OK: {len(modules)} module reference(s), "
          f"{len(docs)} document reference(s), {len(scripts)} script "
          f"reference(s), {len(hud_count_claims(text))} HUD layout count "
          f"claim(s) matching {HUD_PRESETS_JSON}, no pull-request numbers, no "
          f"stale phrases and no Google-search rewrite links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
