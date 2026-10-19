"""A stand-in for one of the owner's files, as the WHOLE patch stack leaves it.

WHY

About twenty suites test "the installed file" - jarvis_hud.py, jarvis_gate.py
- when it is there, and something else (a patch's own `+` lines, a
_skeleton rehearsal) when it is not. In CI it is never there, so the
installed-file branch of those suites never ran anywhere but the owner's PC.
That is how test_loopback_too.py came to fail only on the owner's machine:
bind-wildcard.patch, later in the stack, made `_loopback_companion` call a
new function, and the suite lifted `_loopback_companion` alone.

_skeleton.build() lays each named patch's after-image side by side. This goes
further: it walks every patch scripts/apply-patches.ps1 applies, IN ITS
ORDER, and applies each hunk for the target file with `git apply`. When a
hunk's context is not in the stand-in yet - it is text of the owner's
original file, which this repository does not hold - that context (the
hunk's pre-image) is added first, after a "# gap" line, and the hunk is then
applied to it. So every patch's lines are in the result, and where a later
patch rewrote an earlier one's lines, the result has the rewrite.

What it cannot say: anything about the owner's own lines between the hunks.
A hunk whose pre-image had to be added is logged ("materialised"); a hunk
whose context an EARLIER patch was meant to write, but did not, would be
materialised too rather than fail - scripts/apply-patches.ps1, on a copy of
the real files, is the only proof of that.

THE RATCHET. A hunk whose context an EARLIER patch was meant to write, but did
not, is materialised rather than failing - so a patch whose context has drifted
still "applies", and every suite reading that stand-in proves nothing about the
real file. The number of hunks that had to invent a pre-image is therefore
recorded per target in RATCHET, and may only go DOWN: test_installed_stand_in.py
fails when one of them goes up. That failure is the moment to find out whether
the drift is real, or whether the new patch simply touches text only the
owner's PC holds - either way a person looks, then moves the pin by hand.

The numbers were measured on 2026-10-05 over all 119 patches the branch this
pass came from applies, by calling `stand_in(target, stats=...)`. RATCHET's own
comment says which pin that stack and this one each produce, and why one moved.

Not a test (no `test_` prefix). Standard library and git only.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _gitapply  # noqa: E402  (beside this file; see its docstring)

HERE = Path(__file__).resolve().parent
PS1 = HERE.parent / "scripts" / "apply-patches.ps1"
GAP = "# gap"

#: How many hunks of the whole stack had to have their pre-image - "what the
#: owner's file says here", which this repository does not hold - pasted in
#: before they would apply. Measured 2026-10-05 with `materialised()`: 45 for
#: `jarvis_hud.py` on THIS branch's 116-patch walk (`order()`).
#: A ratchet: it may go down, never up without a person looking. See the module
#: docstring. The pin lives here rather than in the suite so that the number
#: and the reason it matters are in the same place.
#:
#: `jarvis_hud.py` is pinned at 45 here, one more than the 44 this pass first
#: wrote down, and it is not drift: the two numbers were measured on two
#: different patch stacks. This branch is the audit pass cherry-picked onto
#: `main`, and its walk is 116 patches (`order()`); the branch the pass came
#: from, `fix/2026-10-04-audit-pass`, lists 121 entries - among the ones this
#: branch's 116 do not name are `gate-entries.patch`, `gate-action-name.patch`
#: and `tutorials.patch`. Which extra hunk of that stack accounts for the one
#: this branch adds is not measurable from here and so is not guessed at: what
#: is measured is that this stack reads 45. A different stack materialises a
#: different number of hunks, and not only upwards: `jarvis_gate.py` reads 20
#: here against its pin of 22, which drift alone cannot do.
#:
#: Nor is it anything this pass wrote: the walk rebuilt with `main`'s own
#: `gate-push.patch` - the one patch file the pass edits - gives the same 45
#: and the same per-patch list, and the count comes from the patch files and
#: their order alone, never from the tree it is run in.
#:
#: (Left as it is, so nobody re-derives it: `jarvis_gate.py` is 2 under its
#: pin. Tightening a pin is its own decision - test_installed_stand_in.py
#: prints the same note.)
#:
#: RAISED 2026-10-06, 22 -> 24, for `jarvis_gate.py`, and both extra hunks are
#: honest rather than drift - the two names are in `by_patch`:
#:
#:   * `chatbot-limits.patch` (this pass) +1. Its `_RISK` hunk sits directly
#:     after quiz-cloud.patch's own `quiz_cloud_grade` row, whose lines are
#:     themselves a materialised pre-image, so the context is text only the
#:     owner's PC holds. There is no earlier patch this could anchor to
#:     instead: `_RISK`'s last entry before quiz-cloud is 800 lines earlier.
#:     Its `_NO_RULE_FROM_DENIAL` hunk materialised nothing, so this patch
#:     costs the walk exactly one hunk.
#:   * `readpage.patch` +1, already on this branch before this pass. Its third
#:     hunk anchors to an `_TOOL_ACTIONS` line `inbox-tidy.patch` writes, and
#:     that patch is not in this branch's 116-entry walk - the same
#:     different-stacks gap described above, not a patch that drifted.
#:
#: Neither can be fixed by editing a patch: what is missing is the owner's own
#: lines. The pin may come back down when `inbox-tidy.patch` joins the walk.
RATCHET = {
    #: 46, LOWERED from 47 on 2026-10-06, when `ollama-direct.patch` stopped
    #: carrying the cloud lane's whole resolution in the HUD and left
    #: `body["model"]`, the key and the reason to `jarvis_chatbot_api.py`'s
    #: `lane_state()`. Measured, not argued: with the patch as it was, the walk
    #: materialised 47 hunks and THREE patches were in `by_patch` for this file
    #: - `ollama-direct.patch` 3, and then `cloud-one-turn.patch` 1 and
    #: `chat-stream.patch` 1, both of which had to invent context that
    #: ollama-direct was supposed to have written and did not. With the smaller
    #: patch the walk materialises 46 and only `ollama-direct.patch` is there,
    #: at 4: its one added hunk still needs the owner's own lines, and the other
    #: two no longer drift. 3 + 1 + 1 became 4 + 0 + 0, which is one hunk less
    #: and, more to the point, two patches that now anchor on real text. A
    #: ratchet: it may still only go down.
    #: Raised 2026-10-08, 46 -> 48, for `retrieve-count.patch`, and both extra
    #: hunks are honest rather than drift - the patch is in `by_patch`:
    #:
    #:   * The count-only retrieval trace (the owner's decision of 2026-10-08,
    #:     "Just the number"; docs/RETRIEVE-PORT-BRIEF.md, option B;
    #:     JARVIS-API section 119). Two hunks in `jarvis_hud.py`, both on text
    #:     only the owner's PC holds: `retrieve()`'s own closing
    #:     `return {"hits": pack(hits), ...}` line in the middle of the file,
    #:     and the `/api/retrieve` handler's `q = (parse_qs(...))[0]` near the
    #:     end. No earlier patch in this walk writes either, and nothing else
    #:     in `jarvis_hud.py` was ever patched around them - the nearest
    #:     patched region for the second is `brain-reads.patch`'s route table,
    #:     hundreds of lines away. Both hunks were verified to apply to
    #:     `jarvis-backend/jarvis_hud.py` (this repository's copy of the state
    #:     the whole stack leaves) with `git apply`, which is the check this
    #:     walk cannot make; `backend/test_retrieve_count.py` re-runs it. A
    #:     ratchet: it may still only go down.
    # prompt-coach.patch (2026-10-08) also contributed one, when it was raised to
# 47 on this branch alone: its POST hunk is anchored on task-control.patch's own
# `if route in ("/api/task/pause"` block, and the four lines of leading context
# above that line are the tail of a route which predates every patch - text only
# the owner's real file holds. The other hunk was re-anchored onto patch-written
# lines and no longer needs one. The number above is the walk's own MEASUREMENT
# with both features in it, not a sum worked out by hand: test_retrieve_count.py
# asserts the pin equals what it measures, so it must be the measured value.
    # attention-settings.patch (2026-10-08) adds one more, 48 -> 49: its single
    # hunk - the interruption budget's route, POST /api/attention/settings -
    # anchors on the blank line and the `if route == "/api/digest/seen":` that
    # follow the `/api/attention/unmute` block. That context is text only the
    # owner's PC holds: the walk's stand-in has a gap there, so the hunk
    # materialises its pre-image honestly rather than drifting, the same reason
    # `gate-risk-rows.patch`'s `_RISK` hunk does. Measured, not argued:
    # `_stack.materialised("jarvis_hud.py")` reads 48 without this patch and 49
    # with it, and `by_patch` names `retrieve-count.patch: 2` and
    # `attention-settings.patch: 1`, with `prompt-coach.patch` absent. A
    # ratchet: it may still only go down.
    # limits-read.patch (2026-10-08) adds two more, 49 -> 51: GET /api/limits.
    # Both of its hunks materialise a pre-image for the same honest reason -
    # they anchor on the HUD's read-only route set and its `/api/attention`
    # dispatch, and that whole block is text only the owner's PC holds, so the
    # walk cannot rebuild it. Measured, not argued:
    # `_stack.materialised("jarvis_hud.py")` reads 49 without this patch and 51
    # with it, and `by_patch` names `limits-read.patch: 2`. A ratchet: it may
    # still only go down.
    # LOWERED 2026-10-09, 51 -> 50, and this one IS a drift fixed rather than a
    # patch that stopped needing an honest pre-image. `tutorials.patch` was
    # anchored on quiz-cloud.patch's two print lines, with the banner comment
    # below them; `chatbot-limits-hud.patch` runs first and writes its own
    # `chatbot money NOT ON` block between those lines and that comment, so on
    # the owner's backend the hunk could not match and the walk invented a
    # pre-image for it - 51, with `by_patch` naming `tutorials.patch: 1`. The
    # patch now anchors on `chatbot-limits-hud.patch`'s own block instead: the
    # hunk applies to lines an earlier patch really writes, `tutorials.patch`
    # is out of `by_patch`, and the walk reads 50. Measured, not argued:
    # `_stack.materialised("jarvis_hud.py")` reads 51 with the old anchor and
    # 50 with this one. A ratchet: it may still only go down, and the pin has
    # to move with a LOWERING too - test_retrieve_count.py asserts this number
    # EQUALS what the walk measures.
    # 2026-10-11, and this pin did NOT move: `picture-card.patch`'s one hunk made
    # the walk read 51, and it was DRIFT rather than an honest pre-image, so the
    # patch was re-anchored instead. Its hunk sat between `progress.patch` and
    # `topics.patch`, on `progress.patch`'s block, with `topics.patch`'s own banner
    # as its trailing context - and `topics.patch` runs AFTER it in `order()`. The
    # finished file holds both blocks, so the hunk applied to the after-image; the
    # file as it stands at that patch's own turn does not, which is the state
    # `apply-patches.ps1` rebuilds by stripping its rehearsal copy and putting the
    # whole list back on in order. There it would have been one more "will not
    # apply", refusing the run with NOTHING HAS BEEN CHANGED. Measured, not argued:
    # `materialised("jarvis_hud.py")` reads 51 with the patch in its old place and
    # 50 with it moved to just BEFORE `plugin-loader.patch` - the one patch that
    # must stay last of all (see `backend/test_gate_touches.py`) - anchored on the
    # OWNER's own lines under `_loopback_companion`, which no patch writes, instead
    # of on an install block; `by_patch` names `picture-card.patch` in the first
    # case and not in the second, and `backend/test_picture_card.py` now checks
    # exactly that, so the drift cannot come back silently. The pin stays 50. A
    # ratchet: it may still only go down.
    # RAISED 2026-10-13, 50 -> 51, for `attention-settings.patch`'s SECOND hunk,
    # and it is honest rather than drift - the patch is in `by_patch` at 2:
    #
    #   * The interruption budget's route, POST /api/attention/settings, was in
    #     `_desktop_action` and in NO dispatch tuple, so both apps' requests fell
    #     through to 404 (the same half-wiring `limits-settings.patch` had, fixed
    #     2026-10-10). The new hunk writes the tuple's own entry, and the tuple -
    #     `/api/models/install` .. `/api/voice/wake` - is text only the owner's
    #     PC holds: no patch in this walk writes a line of it, and limits-read.patch
    #     reads it only through its own materialised pre-image. So the walk
    #     invents those seven lines, exactly as the patch's first hunk already
    #     did for the `_desktop_action` block.
    #   * The entry is written after the `/api/watch/remove` line and not beside
    #     `/api/attention/mute`, where it reads best, and that PLACE was measured
    #     rather than chosen: `limits-settings.patch` runs next and its own tuple
    #     hunk's context ends at `/api/watch/remove`, so an entry written before
    #     that line sits inside the remaining context and the limits hunk can no
    #     longer match - `apply-patches.ps1` then refuses the whole run with
    #     NOTHING HAS BEEN CHANGED. Measured: the entry after the
    #     `/api/attention/unmute` line gives materialised 51 with
    #     `limits-settings.patch: 1` in `by_patch` and the limits patch failing;
    #     after `/api/watch/remove` the limits patch applies to real context and
    #     leaves `by_patch` entirely.
    #   * Which is the one part of this that went DOWN: `limits-settings.patch`
    #     used to invent its tuple pre-image (1 hunk) and now anchors on the line
    #     THIS patch writes. Measured, not argued: 50 before this change
    #     (`attention-settings.patch` 1, `limits-settings.patch` 1) and 51 after
    #     (`attention-settings.patch` 2, `limits-settings.patch` absent) - the new
    #     hunk costs one and the limits patch gives one back. A ratchet: it may
    #     still only go down.
    # RAISED 2026-10-15, 51 -> 52, for `initiative-payload.patch`'s ONLY hunk, and
    # it is honest rather than drift - the patch is in `by_patch` at 1:
    #
    #   * The phone's "Findings" note reads a `checks` count out of the
    #     `/api/initiative` body, and the route never sent one. The patch's one
    #     hunk replaces that route's own return line -
    #     `return self._send(200, {"available": bool(_ENGINE), "items": items})` -
    #     with the same body plus `"checks": (len(_ENGINE.watchers) if _ENGINE
    #     else 0)`, and does nothing else in the file.
    #   * That return line, and the `pass` / `if card:` / `items.append(card)`
    #     block above it that the hunk carries as context, are the OWNER's text:
    #     no patch in this walk writes a line of that region. Every other match
    #     for `/api/initiative` in `backend/*.patch` is a CONTEXT line of the
    #     path-LIST line ~140 lines above - `memory-pane.patch` is the only one
    #     that REWRITES anything there, and it stops at the list's own
    #     continuation line. So the walk cannot rebuild this context and invents
    #     its pre-image, which is the honest case this pin exists to record
    #     rather than the drift it exists to catch.
    #   * There is no anchor to move to, which is why the patch is not
    #     re-anchored instead: the `/api/initiative` route block has no
    #     patch-written line in it at all, and the nearest patched region is
    #     `memory-pane.patch`'s path-list edit above it. Materialising is the
    #     same cost `retrieve-count.patch` and `limits-read.patch` already pay
    #     for the same reason.
    #   * What it costs, said plainly: the walk cannot verify this hunk against
    #     the owner's file. `jarvis-backend/jarvis_hud.py` - this repository's
    #     copy of the state the whole stack leaves - holds the very line the
    #     hunk anchors on, and `backend/test_jobs.py` rehearses the patch against
    #     it (apply, reverse, byte for byte), which is the check this walk
    #     cannot make - the same pairing `_stack.py`'s note above records for
    #     `retrieve-count.patch`.
    #   * Measured, not argued: `_stack.materialised("jarvis_hud.py")` reads 51
    #     with the patch off the list and 52 with it on, and `by_patch` names
    #     `initiative-payload.patch: 1`. A ratchet: it may still only go down,
    #     and the pin has to move with a RAISING too - test_picture_card.py and
    #     test_retrieve_count.py assert this number EQUALS what the walk measures.
    #: RAISED 2026-10-18, 55 -> 57, for `presets.patch`, measured after its
    #: call-site hunks were re-authored against the CURRENT stack (the first
    #: version was written against an older base, so the stand-in materialised
    #: them and read 59 - that was drift, not the patch). Now: active-lane
    #: helper (1), the two chat call sites (2) and the install block (1) invent
    #: a pre-image; the local-model URL detail applies exactly. Measured, not
    #: argued: test_installed_stand_in reads 57, and the picture-card/
    #: retrieve-count suites assert this number EQUALS the walk.
    "jarvis_hud.py": 57,
    #: 23, raised from 22 on 2026-10-06. PR #80's `gate-risk-rows.patch` is the
    #: one new patch this walk adds for this file, and its single hunk's context
    #: is text only the owner's PC holds: the short `"delete it and it is gone"`
    #: rows of `_RISK`, which no other patch in `order()` writes (checked by
    #: searching every patch for those sentences - `gate-risk-rows.patch` is the
    #: only match). So the hunk is MATERIALISED honestly, not drifted, and the
    #: pin moves with it. The note above already records that this stack reads
    #: 20 for this file against the old pin of 22 - the pin was loose either way.
    #: 23 is what the walk measures now. A ratchet: it may still only go down.
    #:
    #: Raised once more, to 25, when this branch and PR #80 met: the two patches
    #: are independent, so the walk now carries BOTH materialised `_RISK` hunks.
    #: This branch's own `chatbot-limits.patch` adds the two api-limit actions,
    #: each needing a `_RISK` row, and the nearest non-materialised `_RISK`
    #: anchor in this walk is ~800 lines away - the same honest reason as
    #: `gate-risk-rows.patch`'s, not a patch that drifted. The number below is
    #: what the walk measures with both patches in it; `test_installed_stand_in.py`
    #: is what says so, and it may still only go down. (SUPERSEDED below.)
    #:
    #: LOWERED 2026-10-06, 25 -> 23, when the walk was read again while this
    #: branch and PR #89's `main` were merged. The note above called
    #: `chatbot-limits.patch`'s two materialised hunks honest, and they were not:
    #: BOTH hunks were anchored on the entry each list held when that patch was
    #: written - `"youtube_captions_read"` in `_RISK`, `"quiz_cloud_grade"` in
    #: `_NO_RULE_FROM_DENIAL` - and neither was the last entry any more, because
    #: `quiz-cloud.patch` and `readpage.patch` add their own entries after them
    #: and both run earlier in this walk. A hunk that cannot match is
    #: materialised at the END of the file (see the module docstring), so the
    #: `_RISK` hunk re-emitted its context lines - `youtube_captions_read` among
    #: them - and `jarvis_gate.py`'s `_RISK` held that action TWICE. The last row
    #: wins, so the first was dead code; `test_gate_risk_words.py`'s duplicate
    #: check is what caught it. Both hunks now name `read_web_page`,
    #: `readpage.patch`'s own last entry in each of those two lists, so both
    #: apply to real context: neither is in `by_patch` and the walk reads 23.
    #: This was never a missing-line problem of the owner's PC's, which is what
    #: the note above assumed - it was a patch anchored one entry too early. A
    #: ratchet: it may still go down.
    #:
    #: RAISED 2026-10-10, 23 -> 25, for `gate-touches.patch`, and both extra
    #: hunks are honest rather than drift - the patch is in `by_patch` at 2:
    #:
    #:   * Both of its hunks anchor on text NO PATCH IN THIS WALK WRITES, and
    #:     that is a fact about the gate rather than about this patch. The first
    #:     sits directly under `_PROTECTED` and `_PROTECTED_RE` (the tuple of
    #:     nine file names the rule exists for); the second replaces
    #:     `check()`'s own `hit = _touches_protected(prompt, detail)` call.
    #:     Every `.patch` here was searched for `_PROTECTED`: the only matches
    #:     are `gate-outcome.patch`'s CONTEXT lines around that call (`hit =`
    #:     and the `_audit` line below it), `no-auto-approve.patch`'s REMOVED
    #:     `if _touches_protected(prompt):`, and this patch's own lines. The
    #:     tuple itself, the `_touches_protected` body and `check()` are the
    #:     owner's text in every version of his file, so the walk cannot
    #:     rebuild them and invents their pre-image - 8 lines for one hunk and
    #:     7 for the other.
    #:   * There is no anchor to move to. Every patch that runs earlier in this
    #:     walk and touches this region (`gate-outcome.patch`,
    #:     `no-auto-approve.patch`) is itself materialised here, so the nearest
    #:     text an earlier patch really writes is `gate-entries.patch`'s and
    #:     `gate-action-name.patch`'s additions to `_TOOL_ACTIONS`, hundreds of
    #:     lines away. A hunk is materialised when its CONTEXT cannot be found,
    #:     and no context in this region can be found - which is why
    #:     `gate-push.patch`, `gate-outcome.patch` and
    #:     `rebuilt-patches/approval-notice.patch` are already in `by_patch`
    #:     for this same file.
    #:   * What it costs, said plainly: the walk cannot verify these two hunks
    #:     against the owner's file. `backend/test_gate_touches.py` covers that
    #:     from the other side - it runs the repository's published copy of the
    #:     gate and checks the patch applies to it and reverses back out - and
    #:     `jarvis-backend/jarvis_gate.py` holds the very lines the hunks
    #:     anchor on, so a fresh copy of the owner's file does too.
    #:
    #: A ratchet: it may still only go down.
    #:
    #: NOT RAISED for the rescued `gate-raise-rows.patch` (2026-10-13): it
    #: materialises NOTHING and this file still reads 25, which is why the pin
    #: is unchanged. That was worth measuring rather than assuming - the first
    #: two attempts at placing that patch both cost the walk, in two different
    #: ways, and both were caught by other suites rather than by this one:
    #:
    #:   * Placed after quiz-cloud.patch but BEFORE readpage.patch, its
    #:     `_NO_RULE_FROM_DENIAL` hunk (trailing context `read_web_page`, which
    #:     readpage.patch writes) could not match: materialised at the END of
    #:     the file, leaving `quiz_cloud_grade` TWICE in `_RISK`. Dead code -
    #:     test_gate_risk_words.py caught it.
    #:   * Placed after readpage.patch but BEFORE the handoff pair, it pushes
    #:     handoff-mode.patch's own `_NO_RULE_FROM_DENIAL` hunk - which anchors
    #:     on that same `quiz_cloud_grade` row, the owner's text - out of reach,
    #:     so THAT hunk is materialised past the set's closing brace and the two
    #:     handoff actions end up in no set at all. test_gate_denial_rule.py
    #:     caught that one. The count would have gone 25 -> 26 and looked
    #:     "honest" here; it was not, and the ratchet alone would not have said
    #:     so. Worth remembering: this pin is one signal among several, not the
    #:     safety net.
    #:
    #: It now sits after the handoff pair and before gate-touches.patch (see its
    #: entry in apply-patches.ps1), where both of its hunks apply to real
    #: context and nothing else moves.
    #:
    #: RAISED 2026-10-18, 25 -> 28, for gate-touches.patch's three new hunks and
    #: all are honest rather than drift: (1) DEF-012, gate_tool's prompt now
    #: carries the whole arguments so the PROTECTED rule can read a target past
    #: character 1,500; (2) I6, latch_taint now keeps a process-local latch when
    #: its own database write raises; (3) the same latch change's clear_taint
    #: hunk. All three sit on lines of the owner's original `jarvis_gate.py` -
    #: no patch in this walk writes them - so the walk must invent their
    #: pre-image. Verified rather than assumed: the hunks were extracted and
    #: `git apply --check`ed against this branch's published gate
    #: (`jarvis-backend/jarvis_gate.py`, which holds those lines in the state
    #: gate-touches.patch expects), and backend/test_gate_touches.py reruns
    #: patch forward/reverse against it. A ratchet: it may still only go down.
    "jarvis_gate.py": 28,
    "jarvis_extract.py": 9,
    "jarvis_models.py": 5,
    "jarvis_skills.py": 2,
}


def materialised(target: str, patches=None) -> dict:
    """What building `target`'s stand-in had to invent.

    {'target', 'hunks', 'materialised', 'by_patch', 'by_patch_lines'} -
    'materialised' is the count the RATCHET pins, 'by_patch' names the patches
    that needed it and 'by_patch_lines' says how many LINES of the owner's
    original text each of them read, so a failure can say which patch drifted
    and by how much. The two units disagree in the case that matters:
    `tools/check_patch_original_text.py` measured the pre-#472
    `cloud-say-yes.patch` at 1 hunk / 27 lines against the fixed one's
    1 hunk / 16 lines, so a hunk-count ratchet cannot see that break at all.
    Empty counts when git is missing (the stand-in could not be built at all,
    which the caller reports as a skip)."""
    stats = {}
    stand_in(target, patches, stats=stats)
    return stats


def order() -> list:
    """The patches apply-patches.ps1 applies, in its order, as paths under
    backend/: a patch the rebuilt modules supersede is its rebuilt-patches/
    half when it has one, and left out when it has none (the script always
    applies the halves, because it always copies the rebuilt modules in)."""
    ps1 = PS1.read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    sup_start = ps1.index("$REBUILT_SUPERSEDES = @{")
    sup = set(re.findall(r"^\s*'([\w.-]+\.patch)'\s*=",
                         ps1[sup_start:ps1.index("\n}", sup_start)], re.M))
    out = []
    for n in names:
        if n in sup:
            if (HERE / "rebuilt-patches" / n).is_file():
                out.append("rebuilt-patches/" + n)
        else:
            out.append(n)
    return out


_AT = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


def hunks(patch_text: str, target: str) -> list:
    """[(hunk text with its @@ line, pre-image lines)] for `target` in a patch.

    A hunk ends when the line counts in its @@ header are used up, the way
    git reads it. It used to end only at the next header, so the empty line
    at the very end of a patch file was read as one more (blank) context
    line - and the last hunk of rebuilt-patches/memory-safety.patch, which
    ends the file, then asked for a blank line the file does not have, and
    no stand-in of jarvis_extract.py could be built (auto-learn.patch,
    2026-09-24)."""
    out, cur, on = [], None, False
    left = [0, 0]                      # old lines, new lines still to come
    for line in patch_text.replace("\r\n", "\n").split("\n"):
        if cur is not None and left[0] <= 0 and left[1] <= 0 and not line.startswith("\\"):
            cur = None
        if line.startswith("+++ ") and cur is None:
            on = line.split()[1] == "b/" + target
            continue
        if line.startswith(("--- ", "diff ", "index ")) and cur is None:
            continue
        if not on:
            continue
        m = _AT.match(line)
        if m and cur is None:
            cur = [[line], []]
            left = [int(m.group(1) or 1), int(m.group(2) or 1)]
            out.append(cur)
        elif cur is not None and line[:1] in (" ", "-", "+", "\\"):
            cur[0].append(line)
            if line[:1] in (" ", "-"):
                cur[1].append(line[1:])
                left[0] -= 1
            if line[:1] in (" ", "+"):
                left[1] -= 1
        elif cur is not None and line == "":
            # A blank context line some editors strip to nothing.
            cur[0].append(" ")
            cur[1].append("")
            left[0] -= 1
            left[1] -= 1
    return [("\n".join(h) + "\n", pre) for h, pre in out]


def _apply(git: str, d: Path, target: str, hunk: str, *extra: str, env: dict = None) -> bool:
    p = d / "one.patch"
    p.write_text(f"--- a/{target}\n+++ b/{target}\n{hunk}", encoding="utf-8")
    r = subprocess.run([git, "apply", *extra, "--include", target, str(p)], cwd=d,
                       capture_output=True, text=True, env=env)
    return r.returncode == 0


def stand_in(target: str, patches=None, *, replace: dict = None, stats: dict = None):
    """(text, log) - `target` after every patch in `patches` (default: the
    whole stack, order()). `replace` maps a patch name to other text to use
    for it (a rehearsal of an edited patch before it is committed). Returns
    (None, why) when git is missing or a hunk will not apply even to its own
    pre-image (a broken patch).

    `stats`, when given, is filled in with what the walk had to invent -
    {'target', 'hunks', 'materialised', 'by_patch'} - for the RATCHET above.
    Callers that do not ask for it are unaffected."""
    git = shutil.which("git")
    if not git:
        if stats is not None:
            stats.update(target=target, hunks=0, materialised=0, by_patch={},
                         by_patch_lines={})
        return None, ["git is not installed"]
    patches = order() if patches is None else list(patches)
    d = Path(tempfile.mkdtemp(prefix="jarvis-stack-"))
    # A scratch folder inside a git work tree makes every `git apply` below
    # resolve its paths against the repository root instead of `d` - and then a
    # bare `--include <name>` matches nothing while git still exits 0. See
    # _gitapply.py: this is what keeps a stand-in from coming back empty.
    env = _gitapply.env_for(git, d)
    log = []
    gaps = 0
    seen = 0
    by_patch = {}
    by_patch_lines = {}
    try:
        f = d / target
        f.write_text("", encoding="utf-8")
        for name in patches:
            text_of = (replace or {}).get(name)
            if text_of is None:
                text_of = (HERE / name).read_text(encoding="utf-8")
            for hunk, pre in hunks(text_of, target):
                seen += 1
                if _apply(git, d, target, hunk, env=env):
                    continue
                gaps += 1
                by_patch[name] = by_patch.get(name, 0) + 1
                by_patch_lines[name] = by_patch_lines.get(name, 0) + len(pre)
                text = f.read_text(encoding="utf-8")
                if text and not text.endswith("\n"):
                    text += "\n"
                f.write_text(text + f"{GAP} {gaps}\n" + "\n".join(pre) + "\n",
                             encoding="utf-8")
                if not _apply(git, d, target, hunk, env=env):
                    return None, log + [f"{name}: a hunk does not apply even to its own "
                                        f"pre-image:\n{hunk[:400]}"]
                log.append(f"{name}: materialised {len(pre)} line(s) of the original")
        text = f.read_text(encoding="utf-8")
        if seen and not text.strip():
            # The walk applied hunks and produced nothing: the stand-in is a
            # lie, and returning it would let a suite assert against "". Say so
            # instead - a review on 2026-10-08 lost an hour to exactly this.
            return None, log + [
                f"{target}: the walk applied {seen} hunk(s) and built an EMPTY file. "
                "`git apply` matched no path - usually a scratch folder inside a git "
                "work tree (see _gitapply.py)."]
        return text, log
    finally:
        if stats is not None:
            stats.update(target=target, hunks=seen, materialised=gaps,
                         by_patch=dict(by_patch),
                         by_patch_lines=dict(by_patch_lines))
        shutil.rmtree(d, ignore_errors=True)


def later_rewriting(name: str, needle: str, patches=None) -> list:
    """The patches after `name` in the stack whose added or removed lines
    mention `needle` - i.e. that rewrite `name`'s own lines. A new patch goes
    last, after every other; what matters for the one it follows is that it
    leaves that one's lines alone. [] when none does (or `name` is absent)."""
    patches = order() if patches is None else list(patches)
    if name not in patches:
        return []
    out = []
    for n in patches[patches.index(name) + 1:]:
        changed = "".join(l for l in (HERE / n).read_text(encoding="utf-8").splitlines(True)
                          if l.startswith(("-", "+")) and not l.startswith(("---", "+++")))
        if needle in changed:
            out.append(n)
    return out


def function_text(source: str, name: str):
    """One top-level `def name(` and its body, cut out by lines (a stand-in is
    fragments, not a module Python can parse). None unless there is exactly one."""
    lines = source.splitlines()
    starts = [i for i, l in enumerate(lines) if l.startswith(f"def {name}(")]
    if len(starts) != 1:
        return None
    out = [lines[starts[0]]]
    for line in lines[starts[0] + 1:]:
        if line and not line[0].isspace():
            break
        out.append(line)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out) + "\n"


def fragment_with(source: str, needle: str):
    """The lines between the two "# gap" markers around `needle` - one piece
    of the original file with every patch's edits in it."""
    lines = source.splitlines()
    at = [i for i, l in enumerate(lines) if needle in l]
    if len(at) != 1:
        return None
    a = at[0]
    while a > 0 and not lines[a - 1].startswith(GAP):
        a -= 1
    b = at[0]
    while b + 1 < len(lines) and not lines[b + 1].startswith(GAP):
        b += 1
    return lines[a:b + 1]
