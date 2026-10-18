"""test_gate_raise_rows.py - `gate-raise-rows.patch`, proved without the owner's PC.

    python3 backend/test_gate_raise_rows.py

WHY THIS EXISTS. `jarvis_limits.py` and `jarvis_arbiter.py` each name the gate
action a raise is asked under - `raise_a_limit` and `raise_attention_budget` -
and neither name was ever a row in `jarvis_gate.py`'s own two tables. The tier
was right (both have their own `[autonomy.tiers]` line, "ask"), and a tier line
is all `test_gate_names.py` asks for, so nothing failed. What the owner saw was
the consequence:

  * `risk_for()` fell back to `_UNKNOWN_RISK`, so the card said "not
    classified, so treated as irreversible and outbound" about two actions
    whose modules both set `leaves_this_pc: False` - and the phone showed a red
    UNCLASSIFIED pill with no swipe;
  * neither name is in `_NO_RULE_FROM_DENIAL`, so DENYING one proposed a
    standing memory rule ("I do not want Jarvis to raise a limit without asking
    me first") - the exact noise that set exists to prevent.

`chatbot-limits.patch` had already given the sibling pair (`raise_api_limit`,
`lower_api_limit`) both rows; this is the same shape for the two actions that
were left out.

WHAT THIS CHECKS, AND AGAINST WHAT. `jarvis_gate.py` is the owner's own file
and is not in this repository, so three things stand in for it, and the test
says which is which:

  1. the PATCH's own text - two hunks, both jars to `jarvis_gate.py`, additions
     only, and exactly the four rows (two per table);
  2. `jarvis-backend/jarvis_gate.py`, the published base, with `git apply`:
     the rows land, `risk_for()` classifies both, and `git apply --reverse`
     takes the file back to the byte. This is the check `_stack` cannot make;
  3. the whole-stack stand-in (`backend/_stack.py`), which proves no OTHER
     patch gives either action a row (a second row is dead code - a dict keeps
     the last one) and that this patch needed no context invented for it, and
     that it did not move any other patch's cost either. Both halves are real
     checks rather than formalities: placed after quiz-cloud.patch but before
     readpage.patch, this patch leaves `quiz_cloud_grade` twice in `_RISK`
     (`test_gate_risk_words.py` catches that); placed after readpage.patch but
     before the handoff pair, it knocks `handoff-mode.patch`'s own hunk on that
     same row out of reach and the two handoff actions end up in no set at all
     (`test_gate_denial_rule.py` catches that). See its entry in
     `scripts/apply-patches.ps1` for where it has to sit.

Runs anywhere git and Python are: no model, no network, no owner's PC.
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
from _where import REPO  # noqa: E402
import _stack  # noqa: E402

PATCH = HERE / "gate-raise-rows.patch"
BASE = REPO / "jarvis-backend" / "jarvis_gate.py"
PS1 = REPO / "scripts" / "apply-patches.ps1"

#: The two actions, with the module that names each one and the tier it acts
#: on. The name is read from the module (below), never typed twice.
ACTIONS = {
    "raise_a_limit": ("jarvis_limits.py", "limits-settings.patch"),
    "raise_attention_budget": ("jarvis_arbiter.py", "attention-settings.patch"),
}
#: The shape `raise_api_limit` already had, and the shape both of these must
#: match: a raise LOOSENS, so it cannot be undone ("no"), and nothing leaves
#: this PC ("local").
SHAPE = '("no", "local", "'

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    print(f"SKIP {name}\n        {why}")


def added_lines() -> list:
    """The patch's own added lines, without their `+`."""
    return [l[1:] for l in PATCH.read_text(encoding="utf-8").splitlines()
            if l.startswith("+") and not l.startswith("+++")]


# --------------------------------------------------------------------------
# 1. The patch's own text
# --------------------------------------------------------------------------


def t_the_patch_is_registered_and_only_adds_rows():
    check("the patch is a file beside its test", PATCH.is_file())
    ps1 = PS1.read_text(encoding="utf-8")
    listed = ps1[ps1.index("$PATCHES = @("):]
    check("apply-patches.ps1 applies it", "'gate-raise-rows.patch'" in listed)
    # WHERE it sits. Three constraints, every one of them measured rather than
    # reasoned about, because the first two placements tried were each wrong in
    # a different way (see the comments on `_NO_RULE_FROM_DENIAL`'s hunk and on
    # the patch's entry in apply-patches.ps1):
    #
    #   * AFTER quiz-cloud.patch - its `_RISK` hunk anchors on that patch's own
    #     `quiz_cloud_grade` row and the comment above it.
    #   * AFTER readpage.patch - its `_NO_RULE_FROM_DENIAL` hunk has
    #     `read_web_page` as TRAILING context, which readpage.patch writes.
    #     Before it, that hunk is materialised at the END of the file and
    #     `_RISK` holds `quiz_cloud_grade` twice (test_gate_risk_words.py).
    #   * AFTER handoff-front.patch - handoff-mode.patch's own
    #     `_NO_RULE_FROM_DENIAL` hunk anchors on that same `quiz_cloud_grade`
    #     row, so rows added before it are materialised past the set's closing
    #     brace and the two handoff actions end up in no set at all
    #     (test_gate_denial_rule.py).
    #   * AND BEFORE gate-touches.patch, which test_gate_touches.py requires to
    #     stay the last jarvis_gate.py patch in the list.
    def at(name):
        return listed.index(f"'{name}'")

    check("after quiz-cloud.patch, whose `quiz_cloud_grade` row is its anchor",
          at("gate-raise-rows.patch") > at("quiz-cloud.patch"))
    check("... after readpage.patch, which writes the `read_web_page` row its "
          "second hunk ends on",
          at("gate-raise-rows.patch") > at("readpage.patch"))
    check("... and after the handoff pair, whose own `_NO_RULE_FROM_DENIAL` "
          "hunk anchors on that same row",
          at("gate-raise-rows.patch") > at("handoff-mode.patch")
          and at("gate-raise-rows.patch") > at("handoff-front.patch"))
    check("... and before gate-touches.patch, which must stay the last "
          "jarvis_gate.py patch (test_gate_touches.py's own rule)",
          at("gate-raise-rows.patch") < at("gate-touches.patch"))
    check("it needs no new module copied in: nothing ships for it",
          not (HERE / "jarvis_gate_raise.py").exists())
    body = PATCH.read_text(encoding="utf-8")
    files = re.findall(r"^\+\+\+ b/(\S+)$", body, re.M)
    check("it touches jarvis_gate.py and nothing else", files == ["jarvis_gate.py"], files)


def t_the_two_hunks_are_well_formed():
    body = PATCH.read_text(encoding="utf-8")
    heads = re.findall(r"^@@ -(\d+),(\d+) \+(\d+),(\d+) @@", body, re.M)
    check("exactly two hunks, one per table", len(heads) == 2, heads)
    if len(heads) != 2:
        return
    lines = body.splitlines()
    hunks, cur = [], None
    for line in lines:
        if line.startswith("@@"):
            cur = [line]
            hunks.append(cur)
        elif cur is not None:
            cur.append(line)
    added_total = 0
    for i, (h, said) in enumerate(zip(hunks, heads), 1):
        counted_old = sum(1 for l in h[1:] if l[:1] in (" ", "-"))
        counted_new = sum(1 for l in h[1:] if l[:1] in (" ", "+"))
        check(f"hunk {i}: the header's counts match the hunk's own lines",
              (int(said[1]), int(said[3])) == (counted_old, counted_new),
              f"header {said[1]}/{said[3]}, lines {counted_old}/{counted_new}")
        check(f"hunk {i}: nothing is REMOVED - this patch only adds rows",
              not [l for l in h[1:] if l.startswith("-")],
              [l for l in h[1:] if l.startswith("-")])
        check(f"hunk {i}: there is context before AND after the added rows",
              h[1][:1] == " " and h[-1][:1] == " ",
              f"first {h[1][:20]!r}, last {h[-1][:20]!r}")
        added_total += counted_new - counted_old
    check("the two hunks add exactly the rows this patch is for",
          added_total == len(added_lines()) == 17,
          f"hunks add {added_total}, file carries {len(added_lines())}")


def t_each_action_gets_one_row_in_each_table():
    added = added_lines()
    block = "\n".join(added)
    for action, (module, patch) in ACTIONS.items():
        risk = [l for l in added if l.startswith(f'    "{action}": {SHAPE}')]
        check(f"{action}: exactly one _RISK row, in raise_api_limit's shape",
              len(risk) == 1, risk)
        rule = [l for l in added if l.startswith(f'    "{action}",  # ')]
        check(f"{action}: exactly one _NO_RULE_FROM_DENIAL entry", len(rule) == 1, rule)
        # The two tables carry their reasoning differently, the way
        # chatbot-limits.patch's rows do: the _RISK row's own sentence is what
        # the card shows, and the paragraph ABOVE it names the module and the
        # patch; the denial entry carries all of it on its own line.
        check(f"{action}: its _NO_RULE_FROM_DENIAL line names {module}",
              bool(rule) and module in rule[0], rule[0][:120] if rule else "")
        check(f"{action}: ... names {patch}", bool(rule) and patch in rule[0],
              rule[0][:140] if rule else "")
        check(f"{action}: the _RISK comment above its row names {module} and {patch}",
              f"{module}" in block and f"{module.split('.')[0]}.RAISE_ACTION" in block
              and patch in block)
    check("the _RISK block says which module names each action",
          all(f"{m.split('.')[0]}.RAISE_ACTION" in block for m, _p in ACTIONS.values()))
    check("... and that neither sends anything anywhere",
          "neither sends anything anywhere" in block)
    check("... and what a raise does to the owner, limit by limit",
          "Undo history" in block and "spoken interruptions" in block)
    check("... and that lowering either again is instant",
          block.count("lowering it again is instant") == 2)


def t_the_names_are_the_modules_own():
    """The names must be the ones the modules really put to the gate, or the
    rows are for actions nothing raises."""
    for action, (module, _patch) in ACTIONS.items():
        src = (HERE / module).read_text(encoding="utf-8")
        m = re.search(r'^RAISE_ACTION\s*=\s*"([\w_]+)"', src, re.M)
        check(f"{module} defines RAISE_ACTION", m is not None)
        check(f"... and it is {action}", m is not None and m.group(1) == action,
              m.group(1) if m else "")


# --------------------------------------------------------------------------
# 2. The published base, with git apply - the check the stand-in cannot make
# --------------------------------------------------------------------------


def pre_image(text: str, why: str = "") -> str:
    """`text` with this patch's added lines taken back out.

    WHICH DIRECTION THIS HAS TO RUN IN, and why it is the opposite of what the
    stranded tree wrote. That tree applied the patch to
    `jarvis-backend/jarvis_gate.py` and expected the rows to appear. On THIS
    repository's convention the base is not the file the owner's PC starts
    from - it IS the post-patch state (`backend/test_base_matches_repo.py`
    keeps `backend/<f>` and `jarvis-backend/<f>` equal, and
    `jarvis-backend/jarvis_gate.py` holds the two raise rows). So applying the
    patch there can only ever refuse, which is exactly what it did:

        error: jarvis_gate.py: patch does not apply

    The invariant that IS checkable here is the one that matters: the patch
    and the base agree. This removes the patch's own added lines from the base,
    and the caller then applies the patch and gets the base back - BYTE FOR
    BYTE, which is the strong form of `git apply --check` and catches a wrong
    hunk count as well as wrong context.

    WHERE the added lines are is found by the patch's own ADDED text, which is
    unique, and then checked against the patch's own context above and below -
    NOT by the hunk header's line number, and deliberately: the header counts
    lines of the OWNER's file, and the base is not that file. In `_RISK` the
    owner holds a six-line comment this repository does not have above
    `quiz_cloud_grade`, so everything below it sits six lines lower here than
    the header says. The added text and the surrounding context are the same in
    both files.

    It raises AssertionError with the reason rather than returning None,
    because every failure here is a fact about the patch or the base.
    """
    lines = text.splitlines(keepends=True)
    src = PATCH.read_text(encoding="utf-8").splitlines()
    hunks, cur = [], None
    for l in src:
        if l.startswith("@@"):
            cur = []
            hunks.append(cur)
        elif cur is not None:
            cur.append(l)
    out = list(lines)
    # LAST HUNK FIRST. The patch's hunks go down the file, so taking them off
    # bottom-up means an earlier removal can never shift a later one's position.
    # Doing it in the patch's own order and deleting from `out` while searching
    # `lines` is what made the first version of this helper cut the wrong two
    # lines out and leave the rows in place - the same bug this test exists to
    # catch, so it is written down rather than quietly fixed.
    for body in reversed(hunks):
        added = [l[1:] + "\n" for l in body if l.startswith("+")]
        first_add = body.index(next(x for x in body if x.startswith("+")))
        last_add = len(body) - 1 - body[::-1].index(
            next(x for x in reversed(body) if x.startswith("+")))
        before = [l[1:] + "\n" for l in body[:first_add] if l.startswith(" ")]
        after = [l[1:] + "\n" for l in body[last_add + 1:] if l.startswith(" ")]
        # WHERE the added lines are, and HOW THEY ARE FOUND, both matter here and
        # neither is the hunk header's line number. The header counts lines of
        # the OWNER's file, and the base is not that file: in `_RISK` the owner
        # holds a six-line comment this repository does not have above
        # `quiz_cloud_grade`, so every line below it sits lower here than the
        # header says. And the added text ALONE is not enough either - the
        # action names appear again in `_propose_constraint_from_denial`'s
        # docstring in this very file. So a candidate counts only if the patch's
        # own context is above AND below it; the first one that is, is the block.
        at = None
        for i in range(len(before), len(out) - len(added) - len(after) + 1):
            if (out[i:i + len(added)] == added
                    and out[i - len(before):i] == before
                    and out[i + len(added):i + len(added) + len(after)] == after):
                at = i
                break
        if at is None:
            raise AssertionError(
                f"{why}the base does not carry the {len(added)} line(s) this "
                f"patch adds, between the context it says they sit between - "
                f"looked for {added[0].strip()[:60]!r} with "
                f"{len(before)} line(s) above and {len(after)} below, as the "
                f"patch has them")
        del out[at:at + len(added)]
    stripped = "".join(out)
    if stripped == text:
        raise AssertionError(f"{why}nothing was removed - the patch adds no line here")
    return stripped


def risk_for_in(text: str, action: str):
    """The file's OWN `_RISK`, `_UNKNOWN_RISK` and `risk_for()`, run on a stub
    namespace - so this is the answer the card would really get."""
    ns: dict = {}
    pieces = [
        re.search(r"^_RISK: dict.*?^\}$", text, re.S | re.M),
        re.search(r"^_UNKNOWN_RISK = \(.*?^\s+\"[^\n]*\)$", text, re.S | re.M),
        re.search(r"^def risk_for\(.*?(?=^\S)", text, re.S | re.M),
    ]
    for m in pieces:
        if m is None:
            raise AssertionError(f"the patched file's table could not be cut out: {pieces}")
        exec(compile(m.group(0), "<patched jarvis_gate.py>", "exec"), ns)
    return ns["risk_for"](action)


def t_the_patch_applies_to_the_published_base():
    base = BASE.read_text(encoding="utf-8")
    git = shutil.which("git")
    if not git:
        return skip("git is not installed, so the patch cannot be driven here")
    try:
        stripped = pre_image(base, "jarvis-backend/jarvis_gate.py: ")
    except AssertionError as e:
        check("the base carries the patch's own added rows, where the patch "
              "says they are", False, str(e))
        return
    check("the base carries the patch's own added rows, where the patch says "
          "they are", True)
    d = Path(tempfile.mkdtemp(prefix="jarvis-gate-raise-rows-"))
    try:
        # core.autocrlf is true on a Windows checkout, and in such a repository
        # `git apply` rewrites the whole file with CRLF as it writes; the byte
        # comparison below would then measure git's line endings, not the patch.
        subprocess.run([git, "init", "-q"], cwd=d, capture_output=True)
        subprocess.run([git, "config", "core.autocrlf", "false"], cwd=d,
                       capture_output=True)
        subprocess.run([git, "config", "core.eol", "lf"], cwd=d, capture_output=True)
        (d / "jarvis_gate.py").write_text(stripped, encoding="utf-8", newline="")
        r = subprocess.run([git, "apply", "--check", str(PATCH)], cwd=d,
                           capture_output=True, text=True)
        check("with its own rows taken back out, the patch applies to that "
              "pre-image with git apply", r.returncode == 0,
              (r.stderr or r.stdout or "").strip())
        r = subprocess.run([git, "apply", str(PATCH)], cwd=d,
                           capture_output=True, text=True)
        check("... and applying it reproduces the base", r.returncode == 0,
              (r.stderr or r.stdout or "").strip())
        check("... BYTE FOR BYTE - so the base is exactly what this patch "
              "produces, hunk counts included",
              (d / "jarvis_gate.py").read_bytes() == base.encode("utf-8"))
        r = subprocess.run([git, "apply", "--reverse", str(PATCH)], cwd=d,
                           capture_output=True, text=True)
        check("... and --reverse takes it back to the pre-image again",
              r.returncode == 0, r.stderr.strip())
        check("... byte for byte",
              (d / "jarvis_gate.py").read_text(encoding="utf-8") == stripped)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for action in ACTIONS:
        check(f"{action}: the row is in the base",
              f'    "{action}": {SHAPE}' in base)
        r = risk_for_in(base, action)
        check(f"{action}: the base's own risk_for() classifies it",
              r["classified"] is True, r)
        check(f"{action}: ... and says it stays on this PC",
              r["reach"] == "local", r)
        check(f"{action}: ... and that it cannot be undone", r["reversible"] == "no", r)
        check(f"{action}: ... and no longer says 'not classified'",
              "not classified" not in r["why"], r["why"])
        check(f"{action}: it is in _NO_RULE_FROM_DENIAL, so a denial proposes nothing",
              f'\n    "{action}",  #' in base)
        check(f"{action}: ... and it is NOT in the pre-image, which is the "
              "defect this fixes", f'"{action}"' not in stripped)
    # The base is untouched by this test: only the temp copy was written to.
    check("the published base is read-only here (it is a repository file)",
          BASE.read_text(encoding="utf-8") == base)


# --------------------------------------------------------------------------
# 3. The whole-stack stand-in
# --------------------------------------------------------------------------


def t_no_other_patch_gives_either_action_a_row():
    text, log = _stack.stand_in("jarvis_gate.py")
    if text is None:
        check("the whole stack builds a stand-in jarvis_gate.py", False, log[:2])
        return
    check("the whole stack builds a stand-in jarvis_gate.py", True)
    for action in ACTIONS:
        check(f"{action}: named exactly twice - its two new rows - so no other "
              "patch gives it a row a dict would silently drop",
              text.count(f'"{action}"') == 2, text.count(f'"{action}"'))
        check(f"{action}: the stand-in's own risk table classifies it",
              f'    "{action}": {SHAPE}' in text)
    # WHAT THIS PATCH COSTS THE WALK: NOTHING, and that is worth checking
    # rather than assuming, because the first attempt at this rescue got it
    # wrong. Placed straight after quiz-cloud.patch the patch materialised two
    # hunks and left `quiz_cloud_grade` twice in `_RISK` - dead code, caught by
    # test_gate_risk_words.py. Its `_NO_RULE_FROM_DENIAL` hunk has
    # `read_web_page` as TRAILING context, and readpage.patch is what writes
    # that row, so the patch has to sit after readpage.patch. From there both
    # hunks match real context.
    by_patch = _stack.materialised("jarvis_gate.py")["by_patch"]
    check("this patch needed no context invented for it (see _stack.RATCHET)",
          "gate-raise-rows.patch" not in by_patch, by_patch)
    # ... and NOTHING ELSE moved either. Two earlier attempts at placing this
    # patch each cost the walk in a different way - one left `quiz_cloud_grade`
    # twice in `_RISK`, the other knocked handoff-mode.patch's own hunk on that
    # same row out of reach and put the two handoff actions in no set at all.
    # A pin that only ever moves up cannot tell those apart from honest drift,
    # so this names the patches that must stay materialised and the count.
    # 25 -> 28 on 2026-10-18: gate-touches.patch gained three hunks for
    # DEF-012 (the whole-arguments prompt) and I6 (the process-local latch),
    # and all three sit on the owner's ORIGINAL gate_tool/latch text that no
    # earlier patch writes. _stack.RATCHET records the same raise with the
    # reason; this check stays a real pin, not "any number".
    check("... and no other patch's cost changed either: the walk reads the "
          "RATCHET pin, and handoff-mode.patch is NOT among the patches invented",
          _stack.materialised("jarvis_gate.py")["materialised"]
          == _stack.RATCHET["jarvis_gate.py"]
          and "handoff-mode.patch" not in by_patch
          and "gate-raise-rows.patch" not in by_patch,
          f"measured {_stack.materialised('jarvis_gate.py')['materialised']}, "
          f"pinned {_stack.RATCHET['jarvis_gate.py']}, "
          f"by_patch {sorted(by_patch)}")
    check("the walk's pin for jarvis_gate.py is what it measures",
          _stack.materialised("jarvis_gate.py")["materialised"]
          == _stack.RATCHET["jarvis_gate.py"],
          f"measured {_stack.materialised('jarvis_gate.py')['materialised']}, "
          f"pinned {_stack.RATCHET['jarvis_gate.py']}")


def main() -> int:
    if not PATCH.is_file():
        print(f"the patch is not beside this test: {PATCH}")
        return 1
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
