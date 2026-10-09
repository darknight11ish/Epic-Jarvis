"""test_gate_risk_rows.py - `gate-risk-rows.patch`, checked without applying it.

WHY THIS TEST LOOKS LIKE THIS

`jarvis_gate.py` is not in this repository, and proving a patch really applies
means making `git apply` write a file. Two things about THIS repository make
that impossible to do here, both measured on 2026-10-06:

  * the audit stand-in cannot be built at all in a sandbox that refuses Python
    writes inside a `tempfile.mkdtemp` folder (mode 0700) - `_stack.stand_in`
    cannot even write its empty starting file;
  * where it can be built, `git apply` returns exit code 0 **without writing
    the file** (measured: a one-line patch to a file called `a.txt` applied,
    rc=0, contents unchanged). So a stand-in built in that environment is
    EMPTY while every count reads as success - the most dangerous shape a
    check can have.

So this test proves what can be proved from a checkout alone, and says plainly
what it cannot: that the owner's own `jarvis_gate.py` holds the removed lines
byte for byte. Only `scripts/apply-patches.ps1`'s dry run on a copy proves
that, exactly as the README says for every patch here.
"""
from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATCH = HERE / "gate-risk-rows.patch"
PS1 = HERE.parent / "scripts" / "apply-patches.ps1"

#: The stale row this patch removes, and the row that already says the same
#: thing better. Python keeps the LAST of two equal dict keys, so the
#: patch-added `outbound` row wins today - by luck of ordering.
STALE = '    "draft_email":         ("yes", "local", "a draft is not a sent message"),'
KEPT = ('"draft_email": ("yes", "outbound", "saves the draft shown on the card to your '
        'own Drafts folder')
#: The SECOND stale row this patch removes (2026-10-06), and why it counts.
#: `create_joplin_note` is held twice as well: this placeholder, which
#: `create_logseq_page` carries verbatim right beside it, and
#: note-capture.patch's informative row. Both copies rate the write
#: ("yes", "local"), so no safety decision turns on which one survives - unlike
#: draft_email - but they are NOT identical values, the placeholder is the dead
#: copy (Python keeps the last key), and a cleanup that kept it would leave the
#: uninformative sentence on the card. test_gate_risk_words.py's duplicate scan
#: is what caught it.
STALE_JOPLIN = '    "create_joplin_note":     ("yes", "local", "delete it and it is gone"),'

checks: list = []


def check(name: str, cond, extra="") -> None:
    checks.append(bool(cond))
    print(("ok    " if cond else "FAIL  ") + name + ("" if not extra else f"   [{extra}]"))


def _patch_names() -> list:
    """The `$PATCHES` list out of apply-patches.ps1, in order - the same slice
    `_stack.order()` reads."""
    text = PS1.read_text(encoding="utf-8")
    start = text.index("$PATCHES = @(")
    end = text.index("\n)", start)
    return [l.strip().strip("'") for l in text[start:end].splitlines()
            if l.strip().startswith("'")]


def t_the_patch_is_registered_last():
    names = _patch_names()
    check("the patch file is in $PATCHES", "gate-risk-rows.patch" in names)
    # "Last" means last but for the patches written after it - the same rule
    # test_referee.py and test_devices.py use. Every new patch is appended, so
    # the next one pushes this one up the list, and that is not a defect in
    # either of them.
    # screen-attach.patch (2026-10-07) comes after it: one hunk in jarvis_hud.py's
    # tutorials install block, touching jarvis_gate.py not at all, so it cannot
    # rewrite the rows this patch fixes.
    # tasks.patch (2026-10-08) comes after it too: two hunks in jarvis_hud.py -
    # one GET route, one POST block - and jarvis_gate.py not at all, so it
    # cannot rewrite the stale rows this patch removes either.
    later = {"screen-attach.patch", "tasks.patch"}
    check("it is LAST, like every new patch here, bar the ones written after it",
          [n for n in names if n not in later][-1] == "gate-risk-rows.patch",
          names[-3:] if names else names)
    check("and every name in the list has a file",
          all((HERE / n).is_file() for n in names),
          [n for n in names if not (HERE / n).is_file()][:3])


def t_the_hunk_is_well_formed():
    body = PATCH.read_text(encoding="utf-8")
    heads = re.findall(r"^@@ -(\d+),(\d+) \+(\d+),(\d+) @@", body, re.M)
    check("exactly one hunk", len(heads) == 1, heads)
    if len(heads) != 1:
        return
    old, new = int(heads[0][1]), int(heads[0][3])
    lines = body.splitlines()
    at = next(i for i, l in enumerate(lines) if l.startswith("@@"))
    hunk = lines[at + 1:]
    counted_old = sum(1 for l in hunk if l[:1] in (" ", "-"))
    counted_new = sum(1 for l in hunk if l[:1] in (" ", "+"))
    check("the header's counts match the hunk's own lines",
          (old, new) == (counted_old, counted_new),
          f"header {old}/{new}, lines {counted_old}/{counted_new}")
    check("it removes two lines and adds none", counted_old - counted_new == 2)
    check("the removed lines are the two stale rows and nothing else",
          sorted(l for l in hunk if l.startswith("-"))
          == sorted(["-" + STALE, "-" + STALE_JOPLIN]),
          [l for l in hunk if l.startswith("-")])
    check("nothing is added to _RISK by this patch",
          not [l for l in hunk if l.startswith("+")])


def t_no_other_patch_touches_that_line():
    """The rows must be the owner's own, untouched by the stack: if another
    patch added or removed one, this patch would be racing that one."""
    others = []
    for p in sorted(HERE.glob("*.patch")):
        if p.name == PATCH.name:
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if line[:1] in ("+", "-") and ("a draft is not a sent message" in line
                                           or "delete it and it is gone" in line):
                others.append(f"{p.name}: {line[:60]}")
    check("no other patch adds or removes those rows", not others, others)


def t_the_kept_row_is_the_better_one():
    """Why removing the STALE one is right, not the other way round."""
    body = PATCH.read_text(encoding="utf-8")
    check("the row kept is the one that calls a draft outbound", "outbound" in KEPT)
    src = ""
    for p in sorted(HERE.glob("*.patch")):
        t = p.read_text(encoding="utf-8", errors="replace")
        if KEPT in t:
            src = p.name
            break
    check("...and it comes from draft-email.patch, which is not this patch",
          src == "draft-email.patch", src)


def t_the_pristine_copy_holds_the_removed_line():
    """When the verified copy of the owner's own file is present, prove the
    line and every context line are there verbatim. Absent (CI): say so."""
    pristine = (HERE.parent / "dshwork" / "audit-2026-10-04" / "audit-01-evidence"
                / "_stage" / "pristine" / "jarvis_gate.py")
    if not pristine.is_file():
        print("skip  the verified copy of the owner's jarvis_gate.py is not in this checkout, "
              "so the bytes that patch targets cannot be checked here - apply-patches.ps1's "
              "dry run is what proves it")
        return
    text = pristine.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    lines = PATCH.read_text(encoding="utf-8").splitlines()
    at = next(i for i, l in enumerate(lines) if l.startswith("@@"))
    wanted = [l[1:] for l in lines[at + 1:] if l[:1] in (" ", "-")]
    missing = [w for w in wanted if f"\n{w}\n" not in "\n" + text + "\n"]
    check("every line this hunk needs is in the owner's own file", not missing, missing)
    check("the stale row appears exactly once there", text.count(STALE) == 1,
          text.count(STALE))


def main() -> int:
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception as exc:
                checks.append(False)
                print(f"FAIL  {name} raised {type(exc).__name__}: {exc}")
    n = sum(1 for c in checks if c)
    print(f"\n{n} passed, {len(checks) - n} failed")
    return 0 if n == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
