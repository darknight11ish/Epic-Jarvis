#!/usr/bin/env python3
"""A per-patch ratchet on how much of the owner's ORIGINAL text each patch reads.

    py -3 tools/check_patch_original_text.py
    py -3 tools/check_patch_original_text.py --root <a checkout>
    py -3 tools/check_patch_original_text.py --list
    py -3 tools/check_patch_original_text.py --rehearse cloud-say-yes.patch=<file>

WHAT IT DECIDES, in one sentence: for every patch `scripts/apply-patches.ps1`
applies, how many hunks had to have their pre-image invented for them by the
stand-in walk (`backend/_stack.py`), and how many LINES of that pre-image.

A hunk whose context is not in the stand-in yet is context this repository
cannot account for: it is text of the owner's own file, which this repository
does not hold. That is what the phrase "reads the owner's original text" means
here, and it is pinned per patch. The pin may only go DOWN.

WHY IT EXISTS - the bug class, and what it cost (2026-10-16)

`backend/cloud-say-yes.patch` could not be applied at all, and it blocked the
owner's backend for two days. The cause was exactly this property. Its one hunk
carried 11 lines of the owner's `owner_said_yes` call as CONTEXT, and a newer
strip of the stack removed that block, so the re-apply had no context to match.
One patch that will not apply refuses the WHOLE run:

    1 patch(es) will not apply. NOTHING HAS BEEN CHANGED

Every other update on his PC stopped dead on it. The repair (PR #472, e250f323)
made the patch self-contained: those 11 lines became ADDED lines, and the hunk
header went `@@ -2557,27 +2557,48 @@` -> `@@ -2557,16 +2557,48 @@`.

THE UNIT IS LINES, AND THAT WAS MEASURED RATHER THAN CHOSEN

Rehearsing the same walk with the recorded pre-fix text
(`backend/patch-history/cloud-say-yes/21146d3.patch`) against the fixed one, on
`origin/main` 2f85d772:

    fixed  cloud-say-yes.patch   1 hunk   16 lines invented
    broken cloud-say-yes.patch   1 hunk   27 lines invented

The hunk count is IDENTICAL, so a ratchet pinning hunks alone cannot see this
break at all - and the per-target ratchet in `_stack.py` pins hunks. The line
count moves 16 -> 27 and does see it. Both are pinned here; the lines are the
half that bites.

WHAT THE BASE IS, AND WHAT IT IS NOT

A patch is applied to the file the strip left behind: the owner's base plus
every earlier patch. This repository holds neither the owner's base nor a
pre-image of it - `jarvis-backend/` is a POST-patch snapshot, not a pre-image
(`backend/README.md` says so where it describes the base), so reading hunks
against it would compare a patch to a file that already has the patch in it and
would report failures that are not real. This check therefore does not guess the
owner's file and does not read `jarvis-backend/` as a pre-image. Its base is the
stand-in walk's own: an empty file plus the pre-images that walk had to invent,
which is exactly the question "does this patch read text that no earlier patch
in the stack writes?".

So a green run means: no patch reads text the stack cannot account for. It does
NOT mean every patch will apply on the owner's PC. Only `apply-patches.ps1`, on
a copy of his real files, proves that - `_stack.py`'s own docstring says the
same thing, and this tool does not narrow it.

WHAT IT DELIBERATELY DOES NOT DO

It does not enforce the literal rule the audit proposed on 2026-09-30
(`docs/audit-reports-2026-09-29-30/50-audit-a6c4aa03.md`, item 1): "Patches
numbered above 29 must be 0, except a named allow-list (cloud-say-yes: 1)".
Measured on 2f85d772, TWELVE patches after position 29 invent context, and only
one of them is `cloud-say-yes.patch`:

    position  30  voice-enroll.patch
    position  83  cloud-say-yes.patch
    position 118  gate-action-name.patch
    position 123  gate-risk-rows.patch
    position 125  attention-settings.patch
    position 127  limits-read.patch
    position 131  retrieve-count.patch
    position 137  gate-touches.patch
    position 143  initiative-payload.patch
    position 144  hud-origin-module.patch   (SECPRIV audit 2026-10-18: owner-only _token_ok/_origin_ok bodies)
    position 145  hud-exclusive-bind.patch  (SECPRIV audit 2026-10-18 N4: owner-only main() setup tail)
    position 146  presets.patch             (2026-10-18 preset model selector: the owner's original HUD text)

A checker enforcing "0 except cloud-say-yes" would therefore be RED on a clean
`main` with eight findings - the false positives the audit's own next sentence
warns about. Those eight are honest rather than drift: each anchors on lines
only the owner's PC holds, and the ones with a written reason have it in
`_stack.py`'s RATCHET comments, which name most of them. The pin below records
all twelve, with their positions, instead of pretending they are not there. The
position-29 rule is kept as a REPORTED fact, not a gate.

THE PIN

Every number below was measured by this tool against the tree it is committed
with. Raising one is a deliberate act: find out whether the text the patch
newly reads is text an earlier patch SHOULD have written (real drift - fix the
patch, which needs `tools/build_patch_history.py`) or text only the owner's PC
holds (honest - raise the pin here and say which in the commit message). The
same rule as `_stack.py`'s per-target RATCHET, one level finer: that one is an
aggregate over a whole target, so one patch drifting up while another comes down
leaves it unchanged and silent. This one names the patch.

Standard library and git only. No network.
"""
import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

#: patch -> (hunks, lines) the stand-in walk had to invent for it, measured on
#: `origin/main` 2f85d772 (2026-10-16). A patch that invents nothing is absent
#: and pinned at zero - which is the state the audit asked every late patch to
#: be in. Entries at positions 0..26 are the stack's own early core, written
#: against the owner's file before the stand-in existed; the nine later ones are
#: the exceptions, each named with its position in the report below.
PIN = {
    "rebuilt-patches/memory-safety.patch":     (6, 67),    # position 0
    "events-pump.patch":                       (3, 19),    # position 1
    "appearance.patch":                        (6, 37),    # position 2
    "gate-push.patch":                         (3, 26),    # position 3
    "skill-notes.patch":                       (2, 13),    # position 4
    "documents-honesty.patch":                 (6, 42),    # position 5
    "memory-prefix.patch":                     (3, 24),    # position 6
    "rebuilt-patches/extraction-wiring.patch": (3, 18),    # position 7
    "voice-503.patch":                         (5, 41),    # position 8
    "degrade-filter.patch":                    (1, 6),     # position 9
    "vram-estimate.patch":                     (4, 37),    # position 10
    "memory-pane.patch":                       (4, 25),    # position 11
    "token-file.patch":                        (2, 16),    # position 12
    "gpu-offload.patch":                       (2, 16),    # position 14
    "gate-outcome.patch":                      (11, 87),   # position 15
    "no-auto-approve.patch":                   (1, 41),    # position 16
    "memory-noise.patch":                      (4, 31),    # position 17
    "decide-once.patch":                       (1, 31),    # position 18
    "rebuilt-patches/approval-notice.patch":   (3, 19),    # position 19
    "ui-control-wiring.patch":                 (2, 12),    # position 20
    "gate-entries.patch":                      (1, 9),     # position 21
    "ollama-direct.patch":                     (4, 31),    # position 22
    "tool-calling-wiring.patch":               (2, 48),    # position 23
    "memory-intake.patch":                     (1, 3),     # position 26
    # The nine after the audit's position 29, each honest and each checked:
    "voice-enroll.patch":                      (1, 6),     # position 30 - named in the audit itself ("runs one line past an earlier patch's fragment into original text")
    "cloud-say-yes.patch":                     (1, 16),    # position 83 - the audit's own allow-list entry; 16 lines today, 27 when it was broken
    "gate-action-name.patch":                  (1, 8),     # position 118
    "gate-risk-rows.patch":                    (1, 7),     # position 123
    "attention-settings.patch":                (2, 13),    # position 125 - _stack.py: the new hunk invents the dispatch tuple's own lines
    "limits-read.patch":                       (2, 13),    # position 127 - _stack.py: names limits-read.patch: 2
    "retrieve-count.patch":                    (2, 17),    # position 131 - _stack.py: names retrieve-count.patch: 2
    # position 137 - 2 hunks / 15 lines were the PROTECTED-rule change. RAISED
    # 2026-10-18 to 5/59 for the DEF-012 and I6 hunks: gate_tool's whole-args
    # prompt, latch_taint's process-local fallback, and clear_taint's reset are
    # the owner's ORIGINAL gate text - no patch in this walk writes those
    # lines - so the patch necessarily carries 44 more lines of it. Honest
    # rather than drift, and checked: the three hunks were `git apply --check`ed
    # against the published gate and test_gate_touches.py applies them forwards
    # and reverses them out of it byte-for-byte.
    # RAISED AGAIN 2026-10-20 to 8/93 for the blind-approval guards (review
    # ruling 8.2): pending-card deduplication in check()'s ask branch, its two
    # helpers, and the `replaces` flag pending() carries to both apps. The three
    # new hunks read 34 lines of the owner's ORIGINAL gate - the `import` block,
    # the code above `def check(`, and check()'s own INSERT into the queue,
    # which the owner's file already had - and no patch in this walk writes any
    # of them, so they are honest rather than drift. Checked the same way: the
    # whole patch is `git apply`ed forwards and reversed out of the published
    # gate byte-for-byte by backend/test_gate_touches.py, and
    # backend/test_approval_guards.py proves the behaviour against that copy.
    # 2026-10-21 (F-680-2, long-detail dedupe): the target_digest column adds
    # one hunk in `_init`'s migration block and six lines of the owner's own
    # `check()` around the INSERT; raised here with the reason, the one case
    # the rule above allows.
    "gate-touches.patch":                      (9, 99),   # position 137
    "presets.patch":                           (4, 27),   # position 146 - presets.patch
    # (2026-10-18, the preset model selector): the active-lane helper and the
    # four chat call sites are the owner's original HUD text. Measured, not
    # argued: 4 of its 5 hunks read 27 lines of original text; the helper hunk
    # rewrites nothing (it is pure addition) and the install-block hunk applies
    # exactly. Pinned so a future edit that grows this is caught.
    "initiative-payload.patch":                (1, 7),     # position 143
    # SECPRIV audit 2026-10-18 (N1/origin/N4): text only the owner's PC holds.
    # hud-origin-module.patch replaces the old _token_ok/_origin_ok bodies
    # (owner-only text) with delegations to the tracked jarvis_owner_check
    # module; hud-exclusive-bind.patch replaces the main listener
    # construction, whose trailing context is setup only the installed file
    # has. Both were checked with `git apply --check` against a READ-ONLY COPY
    # of the live jarvis_hud.py.
    "hud-origin-module.patch":                 (2, 73),    # position 144
    "hud-exclusive-bind.patch":                (1, 7),     # position 145
    # 2026-10-23, rescue #4 narrowed by the owner's ruling Q1: only pairing a
    # device, an approval key and a restore may have no deadline. ALL EIGHT of
    # its hunks read text only the owner's PC holds - the module docstring, the
    # APPROVAL_TIMEOUT block, `_init()`'s stale-row sweep (touched by no patch
    # at all), `check()`'s deadline and wait loop, `pending()`'s expires_in
    # block, and `withdraw()`'s insertion point before `history()`. Honest
    # rather than drift, and checked the other way by
    # backend/test_gate_no_expiry.py, which applies the patch to the published
    # base with `git apply` (no fuzz), compiles the result and drives it. Its
    # three jarvis_owner_check.py/devices.py halves are shipped modules, not
    # patches, so they do not cost this walk anything.
    "no-expiry-cards.patch":                   (8, 62),     # position 36
}

#: The audit's position, kept because the rule it states is the shape of this
#: pin: a patch that is not in PIN and sits after this position is a new patch
#: reading text the stack cannot account for, and it must be looked at. It is
#: NOT a gate - see "WHAT IT DELIBERATELY DOES NOT DO" above.
BASELINE = 29

_TARGET = re.compile(r"^\+\+\+ b/(\S+)", re.M)


def load_stack(root):
    """The walk's own code, from the checkout being checked - never a copy."""
    backend = root / "backend"
    if not (backend / "_stack.py").is_file():
        raise SystemExit("cannot find backend/_stack.py under %s" % root)
    sys.path.insert(0, str(backend))
    import _stack
    return _stack


def targets_of(stack):
    """Every file the stack patches, in the order the patches first name it."""
    out = []
    for name in stack.order():
        path = Path(stack.HERE) / name
        if not path.is_file():
            raise SystemExit("the stack names %s, which is not there" % path)
        for m in _TARGET.finditer(path.read_text(encoding="utf-8", errors="replace")):
            if m.group(1) not in out:
                out.append(m.group(1))
    return out


def measure(stack, targets, replace=None, patches=None):
    """{patch: {'hunks', 'lines', 'targets'}} for one walk of `targets`.

    The targets are independent of one another - each walk gets its own scratch
    folder from `_stack.stand_in`, and `_gitapply` holds no state - so they are
    walked TOGETHER rather than one after another. Measured on the five targets
    of 2f85d772: 26s in series, 8s together, and identical counts either way.
    The aggregation below still runs in `targets` order, so the report reads the
    same however the threads interleave.
    """
    def walk(target):
        stats = {}
        text, log = stack.stand_in(target, replace=replace, stats=stats,
                                   patches=patches)
        return target, stats, text, log

    if len(targets) > 1:
        with ThreadPoolExecutor(max_workers=len(targets)) as pool:
            results = list(pool.map(walk, targets))
    else:
        results = [walk(t) for t in targets]

    totals = {}

    def slot(name):
        return totals.setdefault(name, {"hunks": 0, "lines": 0, "targets": []})

    for target, stats, text, log in results:
        if text is None:
            return None, "%s: the stand-in could not be built: %s" % (target, log[-1])
        for name, n in stats["by_patch"].items():
            slot(name)["hunks"] += n
            slot(name)["targets"].append(target)
        for name, n in stats["by_patch_lines"].items():
            slot(name)["lines"] += n
    return totals, None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]),
                    help="the checkout to check (default: the one this tool is in)")
    ap.add_argument("--list", action="store_true",
                    help="print every patch, not only the ones that read original text")
    ap.add_argument("--rehearse", metavar="PATCH=FILE", default=None,
                    help="walk with this patch text instead of the committed one")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    stack = load_stack(root)
    order = stack.order()

    replace, instead = None, None
    if args.rehearse:
        if "=" not in args.rehearse:
            raise SystemExit("--rehearse wants PATCH=FILE, not %r" % args.rehearse)
        name, path = args.rehearse.split("=", 1)
        if name not in order:
            raise SystemExit("%s is not in this stack; the stack has %d entries and "
                             "does not name it" % (name, len(order)))
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        replace = {name: text}
        instead = name

    targets = targets_of(stack)
    missing = sorted(set(stack.RATCHET) - set(targets))
    if missing:
        raise SystemExit("_stack.RATCHET pins %s, which the stack no longer patches - "
                         "this tool would have skipped it" % missing)

    patches = None
    if instead:
        # A rehearsal only has to walk the file(s) the rehearsed patch touches:
        # the patches for any other file cannot change its pre-image.
        touched = _names_in(Path(stack.HERE) / instead)
        targets = [t for t in targets if t in touched] or targets
        # ... and it can stop AT the rehearsed patch. Its pre-image is built by
        # the patches before it and by nothing after them, so stopping there
        # gives the same count for it - and skips every later hunk.
        patches = order[:order.index(instead) + 1]

    totals, why = measure(stack, targets, replace=replace, patches=patches)
    if totals is None:
        print("CANNOT RUN: %s" % why)
        return 2

    print("stack: %d entries, %d target(s) walked: %s"
          % (len(order), len(targets), ", ".join(targets)))
    if instead:
        print("rehearsing %s in place of the committed text\n" % instead)

    over, unlisted, late = [], [], []
    for position, name in enumerate(order):
        got = totals.get(name)
        pinned = PIN.get(name, (0, 0))
        if args.list or got:
            print("  %-46s pos %-4d hunks %d/%-3d lines %d/%-3d%s"
                  % (name, position, (got or {}).get("hunks", 0), pinned[0],
                     (got or {}).get("lines", 0), pinned[1],
                     "  <-- NOT PINNED" if (got and name not in PIN) else ""))
        if not got:
            continue
        if name not in PIN:
            unlisted.append((position, name, got))
        elif got["hunks"] > pinned[0] or got["lines"] > pinned[1]:
            over.append((position, name, got, pinned))
        if position > BASELINE:
            late.append((position, name, got))

    total_h = sum(v["hunks"] for v in totals.values())
    total_l = sum(v["lines"] for v in totals.values())
    print("\n%d patch(es) read original text; %d hunks and %d lines invented in all."
          % (len(totals), total_h, total_l))
    print("after the audit's position %d: %d patch(es) invent context, all of them pinned "
          "here (none is a new patch)" % (BASELINE, len(late)) if late
          else "after the audit's position %d: no patch invents context" % BASELINE)

    if instead:
        got = totals.get(instead) or {"hunks": 0, "lines": 0}
        pinned = PIN.get(instead, (0, 0))
        print("\nREHEARSAL of %s: %d hunk(s), %d line(s); pinned at %d hunk(s), %d line(s)"
              % (instead, got["hunks"], got["lines"], pinned[0], pinned[1]))
        if got["hunks"] <= pinned[0] and got["lines"] <= pinned[1]:
            print("ok - at or under the pin")
            return 0
        print("FAIL - %s reads more original text than the pin allows. If this is the "
              "patch you are about to commit, its context is text the strip may not "
              "leave behind: make the patch self-contained (PR #472 is the worked "
              "example), or raise the pin at the top of this tool with the reason in "
              "the commit message." % instead)
        return 1

    if over or unlisted:
        for position, name, got, pinned in over:
            print("\nFAIL  %s (position %d) reads %d hunk(s)/%d line(s) of the owner's "
                  "original text; pinned at %d/%d - it went UP by %d hunk(s), %d line(s)."
                  % (name, position, got["hunks"], got["lines"], pinned[0], pinned[1],
                     got["hunks"] - pinned[0], got["lines"] - pinned[1]))
            print("      read on: %s" % ", ".join(got["targets"]))
        for position, name, got in unlisted:
            print("\nFAIL  %s (position %d) now reads %d hunk(s)/%d line(s) of the owner's "
                  "original text and is NOT in the pin."
                  % (name, position, got["hunks"], got["lines"]))
        print("\nDecide which it is, then say so in the commit message: text an earlier "
              "patch SHOULD have written (real drift - the patch needs fixing, and that "
              "needs tools/build_patch_history.py), or text only the owner's PC holds "
              "(honest - raise the pin at the top of this file).")
        return 1

    print("\nok - no patch reads more original text than it is pinned at.")
    return 0


def _names_in(patch_path):
    """The targets a patch names - a helper for the rehearsal's shorter walk."""
    return set(_TARGET.findall(patch_path.read_text(encoding="utf-8", errors="replace")))


if __name__ == "__main__":
    sys.exit(main())
