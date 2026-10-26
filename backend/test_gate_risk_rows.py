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
    # prompt-coach.patch (2026-10-08) also comes after it: two hunks in
    # jarvis_hud.py and jarvis_gate.py not at all, so it cannot rewrite the
    # stale rows this patch removes.
    # tasks.patch (2026-10-08) comes after it too: two hunks in jarvis_hud.py -
    # one GET route, one POST block - and jarvis_gate.py not at all, so it
    # cannot rewrite the stale rows this patch removes either.
    # retrieve-count.patch (2026-10-08) comes after it too: two hunks in
    # jarvis_hud.py - `_retrieve_counts()` beside retrieve() and the handler's
    # own `count=1` branch - and jarvis_gate.py not at all, so it cannot
    # rewrite the stale rows this patch removes either.
    later = {"screen-attach.patch", "prompt-coach.patch",
             # secret-handoff.patch (2026-10-26): ONE added install block in
             # jarvis_hud.py, on setup.patch own last printed lines, and no
             # hunk in jarvis_gate.py - so it rewrites none of the stale rows
             # this patch removes.
             "secret-handoff.patch",
             "tasks.patch", "retrieve-count.patch",
             # attention-settings.patch (2026-10-08) comes after it as well: ONE
             # route in jarvis_hud.py (POST /api/attention/settings), anchored on
             # the attention routes already there, and jarvis_gate.py not at all -
             # so it cannot rewrite the stale rows this patch removes. It goes
             # before screen-attach.patch, the patch every new one is written
             # before.
             "attention-settings.patch",
             # handoff-mode.patch (2026-10-08) also comes after it: its two hunks
             # join the "acts only on tier ask" list and the _RISK table at the
             # END of each, so it cannot rewrite the two rows this patch removes
             # either.
             "handoff-mode.patch",
             # limits-settings.patch (2026-10-08) comes after it too: ONE route in
             # jarvis_hud.py (POST /api/limits/settings) right after the budget's
             # own, and jarvis_gate.py not at all - so it cannot rewrite the stale
             # rows either.
             "limits-settings.patch",
             # limits-read.patch (2026-10-08) comes after it as well: GET
             # /api/limits joins the HUD's read-only route set and jarvis_gate.py
             # is not touched at all - so it cannot rewrite the stale rows either.
             "limits-read.patch",
             # handoff-front.patch (2026-10-09) is the same shape as
             # handoff-mode.patch: its two hunks join the "acts only on tier ask"
             # list and the _RISK table at the END of each, so it cannot rewrite
             # the two rows this patch removes either.
             "handoff-front.patch",
             # gate-raise-rows.patch (2026-10-09; rescued onto main 2026-10-13)
             # comes after this one too: two hunks in jarvis_gate.py, one row
             # added to each of `_NO_RULE_FROM_DENIAL` and `_RISK` for
             # `raise_a_limit` and `raise_attention_budget`. It only ADDS, and it
             # anchors on quiz-cloud.patch's own `quiz_cloud_grade` rows -
             # hundreds of lines from the two stale rows this patch removes - and
             # it names neither of them. The checks above are what keep that
             # true: this patch adds nothing to `_RISK` itself, and
             # t_no_other_patch_touches_that_line refuses any patch that touches
             # the removed rows.
             "gate-raise-rows.patch",
             # docker.patch (2026-10-09) is the route half of the first Docker
             # integration: ONE install block in jarvis_hud.py, between
             # chatbot-limits-hud.patch's block and tutorials.patch's, and it
             # touches jarvis_gate.py not at all - no gate list entry, no risk
             # row, no _TOOL_ACTIONS line - so it cannot rewrite the stale rows
             # this patch removes either. Its own two actions,
             # docker_service_start and docker_service_stop, get their rows from
             # a later slice of docs/DOCKER-INTEGRATION-DESIGN.md (section 9.2);
             # until they land both take unknown_action_tier, which is "ask" in
             # the shipped config, so neither direction fails open.
             "docker.patch",
             # plugin-loader.patch (2026-10-10, this branch) is appended last
             # and has exactly ONE hunk, in jarvis_hud.py: fifteen ADDED lines
             # at the end of the install chain. It removes no line and does not
             # touch jarvis_gate.py at all, so it rewrites nothing this patch
             # wrote.
             "plugin-loader.patch",
             # app-control.patch (2026-10-19, the owner's phone
             # accessibility option) is appended after this patch and
             # touches jarvis_gate.py not at all: TWO ADDED route
             # blocks in jarvis_hud.py, on big-coder.patch's own last
             # lines and the /api/memory/decide route, so it rewrites
             # nothing this patch wrote.
             "app-control.patch",
             # setup.patch (2026-10-20, the owner's setup questionnaire) is
             # appended after app-control.patch and before plugin-loader.patch:
             # ONE ADDED install block in jarvis_hud.py, on presets.patch's
             # last printed lines. No gate list entry, no tier row, no _RISK
             # row, no _TOOL_ACTIONS line, and no line this patch wrote.
             "setup.patch",
             # card-prefs.patch (2026-10-10, "cards read short") sits after
             # gate-touches.patch and before picture-card.patch (so, before
             # plugin-loader.patch too) and has exactly ONE hunk, in
             # jarvis_hud.py: fifteen ADDED lines, an install block straight
             # after animal.patch's own. It removes no line and
             # does not touch jarvis_gate.py at all - no gate list entry, no
             # risk row, no _TOOL_ACTIONS line - so it rewrites nothing the
             # two stale rows this patch removes ever sat near.
             "card-prefs.patch",
             # gate-touches.patch (2026-10-10) is the one name here that DOES
             # touch jarvis_gate.py: two hunks, its own PROTECTED block (what an
             # action TOUCHES, rather than the words printed on its card) and
             # the comment above `check()`'s protected-file call. Neither goes
             # near `_RISK`: its own suite, test_gate_touches.py, checks that no
             # line it adds or removes mentions `_PROTECTED` or the refusal
             # sentence - so it cannot rewrite the two stale rows this patch
             # removes.
             "gate-touches.patch",
             # picture-card.patch (2026-10-11) goes immediately before
             # plugin-loader.patch and has exactly ONE hunk, in jarvis_hud.py: an
             # install block on the OWNER's own lines just before the main socket
             # is built. It removes no line and touches jarvis_gate.py not at all -
             # no gate list entry, no risk row, no _TOOL_ACTIONS line - so it
             # cannot rewrite the stale rows this patch removes. (It was
             # re-anchored there on 2026-10-11: its trailing context used to be
             # topics.patch's own banner, and topics.patch runs after it. See
             # _stack.py's RATCHET note.)
             # uncensored-optins.patch (2026-10-11) is appended in front of
             # plugin-loader.patch: TWO hunks in jarvis_gate.py, both ADDED lines at
             # the END of the "acts only on tier ask" set and the _RISK table, plus ONE
             # install block at the end of jarvis_hud.py's chain. It removes no line,
             # adds no _TOOL_ACTIONS line and does not touch register_approval_key, so
             # it cannot rewrite a line this patch wrote.
             "uncensored-optins.patch",
             # work.patch (2026-10-10) comes after it too: exactly TWO hunks, both
             # in jarvis_hud.py - one GET route in the read-only set and one POST
             # block, each anchored on a route that predates it. It removes no line
             # and touches jarvis_gate.py not at all - no gate list entry, no risk
             # row, no _TOOL_ACTIONS line - so it cannot rewrite the stale rows
             # this patch removes.
             "work.patch",
             "picture-card.patch",
             # pictures.patch (2026-10-11) is appended last and has exactly ONE
             # hunk, in jarvis_hud.py: an install block at the end of the
             # install chain. It removes no line and does not touch
             # jarvis_gate.py at all - no gate list entry, no risk row, no
             # _TOOL_ACTIONS line - so it rewrites nothing the two stale rows
             # this patch removes.
             "pictures.patch",
             # big-coder.patch (2026-10-11) is appended after it, before
             # plugin-loader.patch: two ADDED route blocks in jarvis_hud.py, no
             # gate list, no tier row and no _RISK row.
             "big-coder.patch",
             # model-lanes.patch (2026-10-13, "Start the local model") is appended
             # after that, still before plugin-loader.patch: ONE ADDED install
             # block at the end of the install chain in jarvis_hud.py, and no gate
             # list, no tier row and no _RISK row - it adds no action to the gate
             # at all - so it rewrites nothing the two stale rows this patch
             # removes.
             "model-lanes.patch",
             # initiative-payload.patch (2026-10-15) is appended after it, before
             # plugin-loader.patch: ONE hunk in jarvis_hud.py, on the
             # /api/initiative route's own return line, adding the `checks` count
             # the phone's "Findings" note reads. It removes and adds that one
             # line, touches jarvis_gate.py not at all - no gate list entry, no
             # risk row, no _TOOL_ACTIONS line - so it cannot rewrite the two
             # stale rows this patch removes.
               "initiative-payload.patch",
               # hud-origin-module.patch + hud-exclusive-bind.patch (SECPRIV audit
               # 2026-10-18) are appended immediately before plugin-loader.patch and
               # touch ONLY jarvis_hud.py: the two request-edge decisions delegate to
               # the tracked jarvis_owner_check module, and the main listener takes the
               # port exclusively. No gate list entry, no tier row, no _RISK row, no
               # _TOOL_ACTIONS line, and no line this patch writes - so neither can
               # rewrite my lines. Ordering is safe: they are the last two before the
               # loader and change nothing another patch's hunks anchor on.
             "hud-origin-module.patch",
             "hud-exclusive-bind.patch",
               # hud-request-gate.patch (SECPRIV audit 2026-10-18 N3) is appended
               # after hud-exclusive-bind.patch, immediately before plugin-loader.patch,
               # and touches ONLY jarvis_hud.py at the server seam: header/request
               # deadlines, 32 bounded request slots, and the token rate bucket. No gate
               # list entry, no tier row, no _RISK row, no _TOOL_ACTIONS line, and no
               # line this patch writes - ordering safe, it rewrites nothing.
"hud-request-gate.patch",
             # presets.patch (2026-10-18) is appended after it and before
             # plugin-loader.patch: the active-lane helper, the four chat call sites
             # and the install block that wires POST /api/work/apply. No gate list,
             # no tier row, no _RISK row, no line this patch writes.
             "presets.patch",
             # private-chat.patch (2026-10-25) is appended after it, immediately before plugin-loader.patch
             # and immediately before plugin-loader.patch: 13 hunks in
             # jarvis_hud.py (the private flag read, the held sighting, the
             # tool-list switch, the header, the deny-all gate and the write
             # guards). No gate list entry, no tier row, no _RISK row, and
             # no line this patch writes - ordering safe.
             "private-chat.patch"}
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
