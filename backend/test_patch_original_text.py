"""test_patch_original_text.py - tools/check_patch_original_text.py's own guard.

    python3 backend/test_patch_original_text.py

WHAT THIS IS FOR. `tools/check_patch_original_text.py` is a ratchet: it pins,
per patch, how many hunks and how many LINES of the owner's original file that
patch's context reads (the stand-in walk in `backend/_stack.py` had to invent
them), and fails when one goes up. A ratchet nobody proves is a tool that can
stop biting and still print `ok` - so this suite proves it on the real tree and
on the real breakage:

  * the committed tree is green today, and the happy line says how much was
    looked at (145 stack entries, 5 targets, 33 patches reading original text),
    so "nothing is wrong" cannot be confused with "nothing was looked at";
  * every patch the walk found is IN the pin, so a green run cannot be a pin
    that names nothing;
  * THE BITE PROOF, on the actual incident: the pre-#472 `cloud-say-yes.patch`
    is recorded in `backend/patch-history/cloud-say-yes/21146d3.patch`, its
    context carrying 11 lines the strip no longer leaves behind. Rehearsing the
    walk with that text must FAIL, and must name the patch;
  * the CONTROL for that proof: the same rehearsal with the committed (fixed)
    text must PASS, so a checker that simply failed every rehearsal could not
    pass the check above;
  * and the reason the pin carries LINES as well as hunks: the broken text and
    the fixed text are 1 hunk each, so a hunk-only ratchet cannot tell them
    apart. That is asserted here rather than left in a comment.

Needs nothing from the owner's PC, no network and no third-party package: the
checker is standard library and git only, and so is this.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CHECKER = REPO / "tools" / "check_patch_original_text.py"
BROKEN = REPO / "backend" / "patch-history" / "cloud-say-yes" / "21146d3.patch"

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def run(*args, timeout=900):
    """(exit code, output) for one run of the checker, from the repo root."""
    done = subprocess.run(
        [sys.executable, str(CHECKER), *args], cwd=str(REPO),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


_RUNS = {}


def once(*args):
    """One run per argument tuple, so the suite walks the stack once."""
    if args not in _RUNS:
        _RUNS[args] = run(*args)
    return _RUNS[args]


PATCH_LINE = re.compile(r"^\s+(\S+)\s+pos (\d+)\s+hunks (\d+)/(\d+)\s+lines (\d+)/(\d+)\s*$",
                        re.M)
REHEARSAL = re.compile(r"REHEARSAL of (\S+): (\d+) hunk\(s\), (\d+) line\(s\); "
                       r"pinned at (\d+) hunk\(s\), (\d+) line\(s\)")


def pinned_from_source():
    """The PIN dict as the tool itself holds it - read, never re-typed here."""
    tree = ast.parse(CHECKER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "PIN":
            return ast.literal_eval(node.value)
    return None


def t_the_checker_exists():
    check("tools/check_patch_original_text.py exists", CHECKER.is_file(), str(CHECKER))


def t_the_committed_tree_is_green():
    code, out = once()
    check("the checker exits 0 on the committed tree", code == 0,
          f"exit {code}\n{out[-1200:]}")


def t_the_happy_run_says_how_much_it_looked_at():
    code, out = once()
    m = re.search(r"stack: (\d+) entries, (\d+) target\(s\) walked: (.+)", out)
    check("the run says how many stack entries and targets it walked", bool(m),
          "no 'stack: ...' line in the output")
    if m:
        check("it walked the whole stack, not a corner of it", int(m.group(1)) > 100,
              f"only {m.group(1)} stack entries")
        check("it walked every target the stack patches", int(m.group(2)) >= 5,
              f"only {m.group(2)} target(s): {m.group(3)}")
    found = PATCH_LINE.findall(out)
    check("it names every patch that reads original text", len(found) >= 30,
          f"only {len(found)} patch line(s) in the output")
    check("... and says the totals", bool(re.search(
        r"\d+ patch\(es\) read original text; \d+ hunks and \d+ lines invented", out)),
        "no totals line in the output")


def t_every_patch_the_walk_found_is_pinned():
    code, out = once()
    pin = pinned_from_source()
    check("the tool's own PIN dict can be read", isinstance(pin, dict) and pin,
          f"read {pin!r}")
    if not isinstance(pin, dict):
        return
    found = {name for name, _pos, _h, _ph, _l, _pl in PATCH_LINE.findall(out)}
    unpinned = sorted(n for n in found if n not in pin)
    check("no patch the walk found is missing from the pin", not unpinned,
          f"not pinned: {unpinned} - a green run over an incomplete pin proves less "
          f"than it says")


def t_the_late_patches_are_pinned_and_not_new():
    """The audit's rule, reported rather than gated: patches after position 29
    must not read original text unless the pin names them with a reason."""
    code, out = once()
    pin = pinned_from_source() or {}
    late = [(name, int(pos)) for name, pos, *_ in PATCH_LINE.findall(out) if int(pos) > 29]
    unpinned = sorted((n, p) for n, p in late if n not in pin)
    check("every patch after the audit's position 29 that reads original text is "
          "pinned, so none of them is a new patch arriving unnoticed", not unpinned,
          f"unpinned late patch(es): {unpinned}")
    check("the eleven exceptions the tool's docstring names are the eleven the walk "
          "finds", len(late) == 11, f"the walk found {len(late)}: {late}")


def t_the_broken_patch_is_caught():
    if not BROKEN.is_file():
        check("the recorded pre-#472 cloud-say-yes.patch is still in the tree",
              False, f"{BROKEN} is missing - the bite proof has no material")
        return
    code, out = once("--rehearse", f"cloud-say-yes.patch={BROKEN}")
    check("rehearsing the BROKEN cloud-say-yes.patch fails", code == 1,
          f"exit {code}, expected 1\n{out[-1200:]}")
    m = REHEARSAL.search(out)
    check("the failure names the patch and both numbers", bool(m) and m.group(1) ==
          "cloud-say-yes.patch", "no REHEARSAL line naming cloud-say-yes.patch")
    if m:
        check("the broken text reads MORE lines than the pin allows",
              int(m.group(3)) > int(m.group(5)),
              f"{m.group(3)} lines measured, pinned at {m.group(5)}")
        check("... and the run says FAIL", "FAIL" in out, out[-400:])


def t_the_rehearsal_path_can_pass():
    """The control. Without it, a checker that failed every rehearsal - or a
    rehearsal that never substituted the text at all - would pass the proof
    above while proving nothing.

    It rehearses the COMMITTED text of a cheap patch rather than of the one the
    proof uses: the rehearsal path is the same code for every patch, and this
    walks `jarvis_skills.py` (2 hunks) instead of `jarvis_hud.py` (254), which
    is about twelve seconds of the suite for no extra proof. The committed
    cloud-say-yes text is measured at its pin by the clean run above, which only
    exits 0 when every patch is at or under its pin."""
    code, out = once("--rehearse", "skill-notes.patch=backend/skill-notes.patch")
    check("rehearsing a patch's own committed text passes", code == 0,
          f"exit {code}, expected 0\n{out[-1200:]}")
    m = REHEARSAL.search(out)
    check("... and it is measured at its pin", bool(m) and
          m.group(1) == "skill-notes.patch" and m.group(3) == m.group(5),
          f"REHEARSAL line: {m.group(0) if m else 'absent'}")


def t_the_two_forms_agree_on_hunks_and_differ_on_lines():
    """Why the pin carries LINES: the broken form is one hunk, like the fixed
    one, so a hunk-only ratchet is blind to this break. The fixed form's numbers
    come from the clean run, which applies exactly that text."""
    _, clean_out = once()
    _, broken_out = once("--rehearse", f"cloud-say-yes.patch={BROKEN}")
    b = REHEARSAL.search(broken_out)
    f = next((row for row in PATCH_LINE.findall(clean_out)
              if row[0] == "cloud-say-yes.patch"), None)
    if not b or not f:
        check("both forms were measured", False,
              "the broken rehearsal or the clean run printed no measurement")
        return
    check("both forms are the same number of hunks (so hunks alone cannot tell them "
          "apart)", b.group(2) == f[2], f"broken {b.group(2)}, fixed {f[2]}")
    check("... and the line counts differ, which is what the pin catches",
          b.group(3) != f[4], f"broken {b.group(3)}, fixed {f[4]}")


def t_a_rehearsal_of_a_patch_not_in_the_stack_is_refused():
    code, out = once("--rehearse", "not-a-patch.patch=backend/cloud-say-yes.patch")
    check("rehearsing a patch the stack does not name is refused, not ignored",
          code != 0, f"exit {code} - a rehearsal that substitutes nothing would "
                     f"report the committed text as if it were the candidate")
    check("... and the message says so", "is not in this stack" in out, out[-400:])


if __name__ == "__main__":
    for fn in (t_the_checker_exists,
               t_the_committed_tree_is_green,
               t_the_happy_run_says_how_much_it_looked_at,
               t_every_patch_the_walk_found_is_pinned,
               t_the_late_patches_are_pinned_and_not_new,
               t_the_broken_patch_is_caught,
               t_the_rehearsal_path_can_pass,
               t_the_two_forms_agree_on_hunks_and_differ_on_lines,
               t_a_rehearsal_of_a_patch_not_in_the_stack_is_refused):
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
