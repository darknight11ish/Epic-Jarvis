#!/usr/bin/env python3
"""`skill-scan-wiring.patch` is the route the wave-12 skill scan reaches a PC by.

WHY THIS SUITE EXISTS. Wave 12 (PR #1217: DEF-049's four extra scan checks and
Gemini's Q3 `skills.lock` row) landed in the PUBLISHED BASE files and in no
`.patch` at all. That is fine for a fresh install and useless for the owner's
PC, because `jarvis_skills.py` is one of the FIVE patched base files that
`tools/reconcile_live_backend.py` never copies - it carries them only through
`.patch` hunks. So the deploy would print "already present" for every patch,
copy the shipped `jarvis_skill_hub.py` (which does carry the four checks), and
leave the live `vet()` judging with `_RULES` alone: a Hermes skill using the
inline `` !`cmd` `` form installing as **clean**, and `GET /api/skills/hub/lock`
reading a file nothing wrote. Measured read-only on the owner's folder,
2026-11-09: `extra_findings` 0, `skills.lock` 0, `_lock_after_install` 0 in a
2026-11-06 `jarvis_skills.py` of 42,416 B.

`backend/skill-scan-wiring.patch` is the delivery route. This suite pins the
three things that make it one, and each of them can silently stop being true:

  * it is IN the stack, at the position that makes its context valid (after
    every other writer of `jarvis_skills.py`) and before `plugin-loader.patch`,
    which must stay last;
  * git can read it, and it touches ONE file - a patch that quietly names a
    second file would be carried by the deploy's stack walk into a file this
    route did not intend;
  * its `+` lines ARE the published base's own bytes for all five regions, and
    `tools/reconcile_live_backend.py` has a DELTA_TABLE entry that carries it as
    those hunks. A base edit that forgets the patch, or a patch edit that drifts
    from the base, fails here; so does a deploy entry whose probes stop matching
    the patch it describes.

    py -3 -B backend/test_skill_scan_wiring.py
"""
from __future__ import annotations

import re
import subprocess
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

PATCH = REPO / "backend" / "skill-scan-wiring.patch"
BASE = REPO / "jarvis-backend" / "jarvis_skills.py"
PS1 = REPO / "scripts" / "apply-patches.ps1"
RECONCILE = REPO / "tools" / "reconcile_live_backend.py"

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail="") -> None:
    if ok:
        PASSED.append(name)
        print(f"ok    {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}")
        if detail:
            print(f"        {detail}")


def listed_patches() -> list[str]:
    """The names in scripts/apply-patches.ps1's own $PATCHES array.

    ONLY WHOLE LINES COUNT, the same rule test_patch_wellformed.py uses: many
    entries carry a comment above them naming OTHER patches.
    """
    text = PS1.read_text(encoding="utf-8")
    start = text.index("$PATCHES = @(")
    end = text.index("\n)", start)
    entry = re.compile(r"^\s*'([^']+\.patch)',?\s*$")
    out = []
    for ln in text[start:end].splitlines()[1:]:
        m = entry.match(ln)
        if m:
            out.append(m.group(1))
    return out


def added_lines(patch_text: str) -> list[str]:
    """Every `+` line of the patch, without its leading marker."""
    return [ln[1:] for ln in patch_text.splitlines() if ln.startswith("+")
            and not ln.startswith("+++ ")]


def base_blocks() -> dict:
    """The five regions, sliced out of the published base BY CONTENT.

    Each is the exact byte run the patch must add, so this is checked against
    the file a reader can open rather than against a line number that moves.
    """
    text = BASE.read_text(encoding="utf-8")
    out = {}
    marks = (
        ("constants+helpers", "#: The instruction prose the four extra checks read",
         "    return out\n"),
        ("vet caller", "# The four shapes the hub knows and `_RULES` does not",
         "    findings += _extra_findings(skill)\n"),
        ("report field", "# 0 means the hub was not beside this module",
         '            "extra_checks": EXTRA_CHECKS_VERSION if _hub_present() else 0,\n'),
        ("lock helpers", "def _lock_after_install(skill, report) -> None:",
         "        return\n"),
    )
    for name, first, last in marks:
        i = text.index(first)
        j = text.index(last, i) + len(last)
        out[name] = text[i:j]
    return out


def call_lines() -> dict:
    """The two single added lines, taken from the base's own call sites."""
    text = BASE.read_text(encoding="utf-8")
    return {
        "install call": "    _lock_after_install(skill, report)",
        "uninstall call": "    _unlock_after_remove(name)",
    } if "    _lock_after_install(skill, report)" in text else {}


def t_the_base_still_carries_what_is_being_delivered() -> None:
    """If this fails, the patch is stale and the suite that owns it must speak."""
    text = BASE.read_text(encoding="utf-8")
    check("the published base still defines _extra_findings()",
          "def _extra_findings(skill) -> list:" in text)
    check("the published base's vet() still CALLS it",
          "    findings += _extra_findings(skill)" in text,
          "the caller is the whole of DEF-049 - without it the four checks are dead code")
    check("the published base still writes a skills.lock row",
          "    _lock_after_install(skill, report)" in text)
    check("the published base still forgets the row on uninstall",
          "    _unlock_after_remove(name)" in text and "def _unlock_after_remove(" in text)


def t_the_patch_is_in_the_stack_at_the_right_position() -> None:
    names = listed_patches()
    check("$PATCHES was found and is a real list", len(names) >= 170, len(names))
    check("skill-scan-wiring.patch is in $PATCHES",
          "skill-scan-wiring.patch" in names)
    if "skill-scan-wiring.patch" not in names:
        return
    earlier = ("skill-notes.patch", "skill-install-note.patch",
               "packs-tamper-on-load.patch")
    for name in earlier:
        check(f"{name} still comes earlier, before this patch's context is fixed",
              name in names and names.index(name) < names.index("skill-scan-wiring.patch"))
    check("it is the LAST writer of jarvis_skills.py - only other files follow it",
          names.index("skill-scan-wiring.patch") + 1 < len(names)
          and all(n in ("activity-turn-guard.patch", "plugin-loader.patch")
                  for n in names[names.index("skill-scan-wiring.patch") + 1:]),
          names[names.index("skill-scan-wiring.patch"):])
    check("activity-turn-guard.patch is STILL the last core patch before the loader",
          names[-2] == "activity-turn-guard.patch", names[-3:])
    check("plugin-loader.patch is still the last entry of all",
          names[-1] == "plugin-loader.patch", names[-3:])


def t_git_can_read_it_and_it_touches_one_file() -> None:
    if not PATCH.is_file():
        check("backend/skill-scan-wiring.patch exists", False, str(PATCH))
        return
    p = subprocess.run(["git", "apply", "--numstat", str(PATCH)],
                       cwd=str(REPO), capture_output=True, text=True)
    check("git can read it (git apply --numstat exits 0)", p.returncode == 0,
          (p.stderr or p.stdout).strip()[:300])
    raw = PATCH.read_bytes()
    check("it is stored with LF endings, the only kind that can match an LF file",
          b"\r\n" not in raw)
    targets = sorted(set(re.findall(r"^\+\+\+ b/(\S+)", raw.decode("utf-8", "replace"),
                                    re.M)))
    check("it changes exactly one file: jarvis_skills.py",
          targets == ["jarvis_skills.py"], targets)


def t_its_added_lines_are_the_published_bases_own_bytes() -> None:
    """The one thing that makes the delivered regions match the base exactly."""
    if not PATCH.is_file():
        return
    added = "\n".join(added_lines(PATCH.read_text(encoding="utf-8")))
    for name, block in base_blocks().items():
        check(f"its added lines carry the base's {name} block, byte for byte",
              block in added,
              "the base changed and the patch did not - regenerate the patch")
    for name, line in call_lines().items():
        check(f"its added lines carry the base's {name}", line in added, line)


def t_the_deploy_tool_has_a_rule_that_carries_it() -> None:
    """No entry here and reconcile REFUSES the file - so the entry is the route."""
    text = RECONCILE.read_text(encoding="utf-8")
    check("tools/reconcile_live_backend.py names the patch in its DELTA_TABLE",
          '"skill-scan-wiring.patch"' in text)
    check("the entry carries the patch's own hunks (four disjoint regions)",
          "SKILL_SCAN_WIRING_PROBES" in text)
    if not PATCH.is_file():
        return
    added = "\n".join(added_lines(PATCH.read_text(encoding="utf-8")))
    block = re.search(r"SKILL_SCAN_WIRING_PROBES = \((.*?)\n\)", text, re.S)
    check("the probe list is there to be read", bool(block))
    if not block:
        return
    probes = re.findall(r'^\s*"((?:[^"\\]|\\.)*)",\s*$', block.group(1), re.M)
    check("the entry has at least five probes, one from several regions",
          len(probes) >= 5, probes)
    missing = [p for p in probes if p not in added]
    check("every probe is a line the patch really adds", not missing,
          f"not in the patch's + side: {missing}")


def t_the_stack_walk_pins_what_it_measures() -> None:
    """_stack.RATCHET must equal the walk, or the walk's warning is decorative."""
    sys.path.insert(0, str(HERE))
    import _stack  # noqa: E402

    pin = _stack.RATCHET.get("jarvis_skills.py")
    check("_stack.RATCHET pins jarvis_skills.py at 11 hunks (6 before this patch + its 5)",
          pin == 11, pin)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_patch_original_text", REPO / "tools" / "check_patch_original_text.py")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    check("tools/check_patch_original_text.py pins the same patch, at 5 hunks / 33 lines",
          checker.PIN.get("skill-scan-wiring.patch") == (5, 33),
          checker.PIN.get("skill-scan-wiring.patch"))


def main() -> int:
    for fn in (t_the_base_still_carries_what_is_being_delivered,
               t_the_patch_is_in_the_stack_at_the_right_position,
               t_git_can_read_it_and_it_touches_one_file,
               t_its_added_lines_are_the_published_bases_own_bytes,
               t_the_deploy_tool_has_a_rule_that_carries_it,
               t_the_stack_walk_pins_what_it_measures):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            print(f"FAIL  {fn.__name__} raised")
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
