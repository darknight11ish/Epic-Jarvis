#!/usr/bin/env python3
"""Name every .py in the published base that the installer will never deliver.

    python3 tools/check_unmanaged_files.py

WHY THIS EXISTS. On 2026-10-14 a work order said to add a feature to
`jarvis-backend/jarvis_style.py`. Before briefing anyone, the question asked was
"if this file is edited, does the installer put the edit on the owner's PC?"
The installer was run against a copy of the backend standing in for his folder,
with two files deleted from it first. Measured:

    jarvis_style.py        STILL MISSING - not shipped
    jarvis_accounts.py     RESTORED by the installer

`jarvis_accounts.py` is in the script's `$SHIPPED` block; `jarvis_style.py` is
not, and no patch writes it either. So code written there is dead on arrival -
and it passes every check this repository has, because the twin checks compare
`backend/<f>` with `jarvis-backend/<f>` and there is no
`backend/jarvis_style.py` to compare.

THE CLASS WAS ALREADY WRITTEN DOWN, AND NOTHING DETECTED A NEW ONE. The
installer's own record of the owner's folder, measured 2026-10-11, sits in
`scripts/apply-patches.ps1` above its no-source branch: of his 201 `.py` files,
7 are named by a patch header, 180 are shipped by this repository, and 17 have
no version anywhere in this repository at all - `jarvis_preview.py`,
`jarvis_style.py`, `jarvis_undo.py`, `patch_openjarvis.py`, `spike_sandbox.py`
and twelve `test_*.py`. `backend/test_shipped_modules.py` says the same of
`jarvis_style` by name ("not in backend/, so never shipped", its OWNER_ONLY
entry). The knowledge existed. What did not exist was anything that would say
so about the NEXT one. This does.

WHAT IT CLASSIFIES. Every `.py` file in the published base - the folder a clone
runs its backend from - by the one mechanism that carries an edit to the
owner's PC:

  * patched  - a patch `scripts/apply-patches.ps1` APPLIES writes it. The target
               comes from the patch's own `+++ b/` header lines, never from a
               guess at its content;
  * shipped  - its name is in the script's `$SHIPPED` block, copied whole over
               the owner's copy on every run;
  * both     - both of the above (empty today, and
               `backend/test_shipped_modules.py`'s
               `t_no_patch_edits_a_shipped_file` is the assertion that this
               stays true);
  * NEITHER  - delivered by nothing. This is the set that matters: the file is
               in the published base and an edit to it reaches the owner's PC by
               no mechanism at all.

WHICH PATCHES COUNT, AND WHY THE APPLIED ONES. The applied list, not the pile
of `backend/*.patch` on disk. Six patches are superseded by the rebuilt modules
(`$REBUILT_SUPERSEDES`): the installer applies their `backend/rebuilt-patches/`
half where one exists, and leaves the whole patch out where one does not (four
halves, two left out whole, measured 2026-10-14). Counting every patch header
would call a file "patched" when the only patch naming it is one the installer
skips - a way for exactly the file this tool exists to find to hide in the
wrong bucket. Both readings are printed: the two files they disagree about are
`jarvis_events.py` and `jarvis_memory.py`, which are delivered by `$SHIPPED` as
their rebuilt copies rather than by the superseded patches that name them. A
file named ONLY by a patch the installer leaves out, and delivered by nothing
else, is a failure in its own right (below) - so the looser reading can never
hide one.

THE RECORD, AND WHY IT IS A DICT AND NOT A HABIT. `UNMANAGED` below names every
NEITHER file, with the reason it is one. A new file in the base that nothing
delivers is a FAILURE - which is the point: "somebody will notice" is how this
class reached two audits before anyone could say whether a new one had arrived.
A recorded name that has BECOME delivered is a failure too, so the record
cannot rot into a list of things that are no longer true.

WHAT IT DELIBERATELY DOES NOT DO. It does not promote anything into `$SHIPPED`
and does not touch `scripts/apply-patches.ps1`. Promoting a file means the
installer starts OVERWRITING the owner's own copy of it on every run, and that
is his decision, not this tool's. Recording the set is the job; changing what
is shipped is a different one.

WHAT IT CANNOT SEE. The owner's folder. Five names in the 2026-10-11
measurement live only there - `patch_openjarvis.py`, `spike_sandbox.py` and the
twelve `test_*.py` beside his backend - so they can never appear here. The
three that are both on his PC and in the published base (`jarvis_preview.py`,
`jarvis_style.py`, `jarvis_undo.py`) are recorded below, and `_where.py` is a
fourth for a different reason of its own.

Exit code: 0 when every .py in the base is delivered by something or recorded
here, 1 otherwise.
"""
from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

#: The published base: the folder a clone's backend runs from, and the state
#: `scripts/apply-patches.ps1` copies and patches on the owner's PC.
BASE = REPO / "jarvis-backend"

#: The installer itself - the only place `$SHIPPED` and `$PATCHES` are written.
PS1 = REPO / "scripts" / "apply-patches.ps1"

#: The patches, and the split halves of the six superseded ones.
PATCH_DIR = REPO / "backend"
HALF_DIR = PATCH_DIR / "rebuilt-patches"

#: The file this tool was built for. Its verdict is printed on every run,
#: whatever that verdict is, so nobody has to infer it from a count.
FOUNDING_CASE = "jarvis_style.py"

#: Every `.py` in the published base that NOTHING delivers: no patch the
#: installer applies writes it, and `$SHIPPED` does not carry it. Each entry is
#: the reason, and each is checked below - a name here that is not a file in
#: the base, or that has become delivered, is a failure, so the record cannot
#: rot. A name in the base that is missing from here is the failure this tool
#: exists for.
UNMANAGED = {
    "jarvis_style.py":
        "THE CASE THIS TOOL WAS BUILT FOR. In the published base and on the owner's PC, "
        "and delivered by nothing: no patch writes it and $SHIPPED does not carry it. It "
        "is read by the running backend all the same - rebuilt/jarvis_events.py:802 "
        "probes it by name for the \"persona\" capability (`has(\"jarvis_style\")`, an "
        "actual __import__, which answers false when it is absent) - and it is named in "
        "selftest.py's EXPECTED list of the modules jarvis_hud and its siblings import "
        "(selftest.py:99). A work order of 2026-10-14 sent a feature here; the installer "
        "run against a copy of the backend left this file missing while restoring "
        "jarvis_accounts.py from $SHIPPED. An edit in either copy of it reaches the "
        "owner's PC by nothing.",
    "jarvis_preview.py":
        "One of the base's ten orphan modules (jarvis-backend/README.md, \"The ten "
        "orphan modules\"): jarvis_hud.py:793 imports it inside the /api/holds/cancel "
        "handler, so a request for that route raises where it is absent. The base holds "
        "the only copy this repository has - no patch writes it and $SHIPPED does not "
        "copy it - so an edit here is delivered by nothing.",
    "jarvis_undo.py":
        "The same shape: jarvis_hud.py:774 (the /api/undo/revert handler) and "
        "jarvis_hud.py:2402 (the /api/undo status route) both import it, the base holds "
        "the only copy this repository has, and no patch writes it and $SHIPPED does not "
        "carry it.",
    "_where.py":
        "This repository's own test plumbing, DERIVED into the base rather than copied "
        "from the owner's PC: tools/gen_base_from_backend.py writes it as "
        "backend/_where.py plus BASE_WHERE_TRAILER, and backend/test_base_regeneration.py "
        "fails if the two differ by anything else. It is in the base at all because "
        "import_history.py, which the base carries and which must run from a cloned "
        "folder with no repository around it, reads BACKEND and explain from it. There is "
        "no _where.py on the owner's PC for an installer to refresh, and its content is "
        "edited in backend/_where.py and re-derived - so promoting this name into "
        "$SHIPPED would be wrong twice over.",
}

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name
          + (("\n      " + str(detail)) if (detail and not cond) else ""))


class Unreadable(Exception):
    """The rule could not be read, so nothing was classified.

    A check that cannot read the list it judges by says so and exits 1. It
    never passes on the strength of a guess - that silence is the whole reason
    this tool exists one level up.
    """


def rel(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:                                  # pragma: no cover
        return path.as_posix()


def wrapped(text: str, indent: str = "      ") -> str:
    return textwrap.fill(text, width=98, initial_indent=indent,
                         subsequent_indent=indent)


# ------------------------------------------------------- reading the script --

def ps1_list(name: str) -> list:
    """The quoted entries of `$name = @( ... )` in apply-patches.ps1, in order.

    The same parser as `backend/test_shipped_modules.py`'s own `ps1_list`,
    deliberately: comments (`#`) are dropped first, so a name mentioned in a
    comment is not an entry, and the closing `)` is what ends the list.
    `backend/test_unmanaged_files.py` compares this tool's answer with that
    suite's, so the two parsers cannot drift apart unnoticed.
    """
    text = PS1.read_text(encoding="utf-8")
    try:
        start = text.index(f"${name} = @(")
    except ValueError:
        raise Unreadable(f"${name} is not defined in {rel(PS1)} any more. This "
                         f"check reads the real block there and will not guess "
                         f"at one.") from None
    out = []
    for line in text[start:].splitlines()[1:]:
        code = line.split("#", 1)[0].strip()
        if code == ")":
            return out
        out += re.findall(r"'([^']+)'", code)
    raise Unreadable(f"${name} in {rel(PS1)} has no closing ')'")


def ps1_superseded() -> set:
    """The six patch names in `$REBUILT_SUPERSEDES`, read from the table."""
    text = PS1.read_text(encoding="utf-8")
    try:
        start = text.index("$REBUILT_SUPERSEDES = @{")
        end = text.index("}", start)
    except ValueError:
        raise Unreadable(f"$REBUILT_SUPERSEDES is not in {rel(PS1)} any more, so "
                         f"which patches the installer applies cannot be read. "
                         f"Four of the six are applied as a split half in "
                         f"{rel(HALF_DIR)}/ and two are left out whole; without "
                         f"the table this check cannot tell an applied patch "
                         f"from a skipped one.") from None
    return set(re.findall(r"^\s*'([^']+\.patch)'\s*=", text[start:end], re.M))


def installed_patches(names: list, superseded: set) -> tuple:
    """(the patch files the installer applies, the names it leaves out whole).

    `$PATCHES` with the six superseded patches replaced by their half in
    `backend/rebuilt-patches/` where one exists, and dropped where one does not
    - which is what `scripts/apply-patches.ps1` does to the list at its own
    line 2295 ("Applying: ALWAYS the split halves"). A patch named in
    `$PATCHES` whose file is not on disk raises rather than being skipped: a
    classification built on a patch that was never read would be a guess.
    """
    applied, left_out = [], []
    for name in names:
        if name not in superseded:
            path = PATCH_DIR / name
            if not path.is_file():
                raise Unreadable(f"$PATCHES names {name}, and {rel(path)} is not "
                                 f"there to read. Nothing was classified.")
            applied.append(path)
            continue
        half = HALF_DIR / name
        if half.is_file():
            applied.append(half)
        else:
            left_out.append(name)
    return applied, left_out


def patch_targets(path: Path) -> set:
    """The files one patch writes, from its own `+++ b/` header lines.

    The header is the patch's own statement of what it edits. A deletion says
    `+++ /dev/null` and matches nothing here, which is right: a deleted file is
    not delivered. The leaf is taken because a `rebuilt/x.py` entry lands beside
    jarvis_hud.py under its bare name - the same rule `$SHIPPED` follows
    (`backend/test_shipped_modules.py`'s LEAVES).
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    return {m.split("\t")[0].strip().rsplit("/", 1)[-1]
            for m in re.findall(r"^\+\+\+ b/(.+)$", text, re.M)}


# ------------------------------------------------------------------- main ---

def main() -> int:
    if not BASE.is_dir():
        print(f"FAIL  {rel(BASE)}/ is not here. This check classifies the "
              f"published base's own .py files, and a check with nothing to "
              f"look at says so rather than passing.")
        return 1
    try:
        shipped = ps1_list("SHIPPED")
        patch_names = ps1_list("PATCHES")
        superseded = ps1_superseded()
        applied, left_out = installed_patches(patch_names, superseded)
    except Unreadable as err:
        print(f"FAIL  {err}")
        print("\nNothing was classified. A check that cannot read its rule says "
              "so, and never passes.")
        return 1
    except OSError as err:                              # pragma: no cover
        print(f"FAIL  {rel(PS1)} could not be read ({err}). Nothing was "
              f"classified.")
        return 1

    # What each mechanism carries, read from the files themselves.
    shipped_leaves = {p.rsplit("/", 1)[-1] for p in shipped}
    shipped_py = {n for n in shipped_leaves if n.endswith(".py")}
    patched_by_applied = set()
    for path in applied:
        patched_by_applied |= patch_targets(path)
    patched_by_any = set()
    for path in sorted(PATCH_DIR.glob("*.patch")) + sorted(HALF_DIR.glob("*.patch")):
        patched_by_any |= patch_targets(path)

    base_pys = sorted(p.name for p in BASE.glob("*.py") if p.is_file())
    buckets = {"patched": [], "shipped": [], "both": [], "neither": []}
    for name in base_pys:
        written = name in patched_by_applied
        carried = name in shipped_leaves
        buckets["both" if written and carried
                else "patched" if written
                else "shipped" if carried
                else "neither"].append(name)

    # ------------------------------------------------- what was looked at ----
    print(f"The published base: {rel(BASE)}/ - {len(base_pys)} .py file(s), "
          f"classified one by one.")
    print(f"The rule, read from {rel(PS1)}: {len(shipped)} $SHIPPED entry(ies), "
          f"{len(patch_names)} $PATCHES entry(ies), {len(superseded)} of them "
          f"superseded -> {len(applied)} patch(es) applied, {len(left_out)} left "
          f"out whole ({', '.join(left_out) if left_out else 'none'}).")
    print(f"  patched  {len(buckets['patched']):3d}  " + ", ".join(buckets["patched"]))
    print(f"  shipped  {len(buckets['shipped']):3d}  every .py named by $SHIPPED"
          + (f" ({', '.join(buckets['shipped'][:5])}, ...)"
             if len(buckets["shipped"]) > 5 else ""))
    print(f"  both     {len(buckets['both']):3d}  "
          + (", ".join(buckets["both"]) if buckets["both"] else
             "(none - backend/test_shipped_modules.py asserts no applied patch "
             "edits a shipped file)"))
    print(f"  NEITHER  {len(buckets['neither']):3d}  " + ", ".join(buckets["neither"]))
    named_by_superseded = sorted(set(base_pys) & (patched_by_any - patched_by_applied))
    print("A second reading, for the reader: counting EVERY backend/*.patch "
          "header, these would be called 'both' rather than 'shipped', because a "
          "superseded patch names them and the installer skips it: "
          + (", ".join(named_by_superseded) if named_by_superseded else "none")
          + ". They are delivered by $SHIPPED, as the rebuilt copies. The NEITHER "
            "set is the same either way.")
    print("Non-.py files are not classified here. The one $SHIPPED entry that is "
          "not a module is jarvis_hud.html.")

    # ------------------------------------------------------------ checks ----
    print()
    check(f"$SHIPPED in {rel(PS1)} was read, and is a list of files",
          len(shipped) > 10, f"{len(shipped)} entries")
    check("$SHIPPED is defined once, so this read the only one there is",
          PS1.read_text(encoding="utf-8").count("$SHIPPED = @(") == 1)
    check(f"{rel(BASE)}/ holds .py files to classify", len(base_pys) > 100,
          f"{len(base_pys)} .py file(s) under {rel(BASE)}/")
    check("every .py entry in $SHIPPED is a file in the base",
          not (shipped_py - set(base_pys)),
          f"named by $SHIPPED and not in {rel(BASE)}/: "
          f"{sorted(shipped_py - set(base_pys))}")
    check("every .py in the base landed in exactly one bucket",
          sum(len(v) for v in buckets.values()) == len(base_pys),
          f"{sum(len(v) for v in buckets.values())} classified, "
          f"{len(base_pys)} in the base")
    check("the split halves of the superseded patches were read off the disk, so the "
          "applied list is not every patch by accident",
          any(p.parent == HALF_DIR for p in applied),
          f"no patch under {rel(HALF_DIR)}/ was read, so the {len(left_out)} "
          f"superseded patch(es) above were treated as left out whole for the wrong "
          f"reason - the classification would be built on a list of patches the "
          f"installer does not use.")
    named_only_by_skipped = [n for n in base_pys
                             if n in patched_by_any
                             and n not in patched_by_applied
                             and n not in shipped_leaves]
    check("no .py in the base is named only by a patch the installer leaves out "
          "whole and delivered by nothing else",
          not named_only_by_skipped,
          f"{named_only_by_skipped} - the patch naming it is one the installer "
          f"skips, so the installer never delivers it. Record it in UNMANAGED "
          f"here with the reason, or ship it - which is the owner's decision.")

    for name in buckets["neither"]:
        check(f"{name} is delivered by nothing and is recorded here with its reason",
              bool(UNMANAGED.get(name, "").strip()),
              f"{rel(BASE)}/{name} is written by no patch the installer applies "
              f"and is not in $SHIPPED, and UNMANAGED in this file does not name "
              f"it. Record it there with the reason an edit to it reaches the "
              f"owner's PC by nothing - or, if it should be delivered, promoting "
              f"it into $SHIPPED is the owner's decision, because the installer "
              f"would then overwrite his own copy of it on every run.")

    for name in sorted(UNMANAGED):
        reason = UNMANAGED[name]
        if name not in base_pys:
            check(f"the record for {name} still points at a file in the base",
                  False, f"{name} is not in {rel(BASE)}/ any more - drop it from "
                         f"UNMANAGED here")
        elif name not in buckets["neither"]:
            check(f"the record for {name} is still true (nothing delivers it)",
                  False, f"{name} is delivered now, so the record is stale - drop "
                         f"it from UNMANAGED. Promoting a file is the owner's "
                         f"decision and not this tool's; the record only follows "
                         f"it.")
        else:
            check(f"the record for {name} is still true (nothing delivers it), and "
                  f"says why in its own words", len(reason.strip()) > 80,
                  f"the reason recorded for {name} is too short to be one: "
                  f"{reason!r}")

    # ------------------------------------------- the case this was built for --
    verdict = "not in the published base"
    for label, key in (("patched", "patched"), ("shipped", "shipped"),
                       ("both", "both"), ("NEITHER", "neither")):
        if FOUNDING_CASE in buckets[key]:
            verdict = label
            break
    print(f"\nThe case this tool was built for: {FOUNDING_CASE} -> {verdict}"
          + (" (no patch the installer applies writes it, and $SHIPPED does not "
             "carry it)" if verdict == "NEITHER" else "") + ".")
    if FOUNDING_CASE in UNMANAGED:
        print(wrapped(f"Recorded in UNMANAGED: {UNMANAGED[FOUNDING_CASE]}"))
    else:
        print(wrapped(f"{FOUNDING_CASE} is not recorded in UNMANAGED, so "
                      f"something delivers it now, or it is no longer in the "
                      f"base."))

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
