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
import tempfile
from pathlib import Path

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
    #: 47, raised from 45 on 2026-10-06, when this branch and PR #80 met. Both
    #: sides add a hunk to jarvis_hud.py whose context is text only the owner's
    #: PC holds, so the walk materialises it rather than reading it as drift:
    #: PR #80's `gate-risk-rows.patch` install block, and this branch's
    #: `chatbot-limits.patch` install block. 45 was the measure before either
    #: existed, and neither side alone would have moved it by two. A ratchet: it
    #: may still only go down.
    "jarvis_hud.py": 47,
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
    #: is what says so, and it may still only go down.
    "jarvis_gate.py": 25,
    "jarvis_extract.py": 9,
    "jarvis_models.py": 5,
    "jarvis_skills.py": 2,
}


def materialised(target: str, patches=None) -> dict:
    """What building `target`'s stand-in had to invent.

    {'target', 'hunks', 'materialised', 'by_patch'} - 'materialised' is the
    count the RATCHET pins, 'by_patch' names the patches that needed it, so a
    failure can say which patch drifted. Empty counts when git is missing (the
    stand-in could not be built at all, which the caller reports as a skip)."""
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


def _apply(git: str, d: Path, target: str, hunk: str, *extra: str) -> bool:
    p = d / "one.patch"
    p.write_text(f"--- a/{target}\n+++ b/{target}\n{hunk}", encoding="utf-8")
    r = subprocess.run([git, "apply", *extra, "--include", target, str(p)], cwd=d,
                       capture_output=True, text=True)
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
            stats.update(target=target, hunks=0, materialised=0, by_patch={})
        return None, ["git is not installed"]
    patches = order() if patches is None else list(patches)
    d = Path(tempfile.mkdtemp(prefix="jarvis-stack-"))
    log = []
    gaps = 0
    seen = 0
    by_patch = {}
    try:
        f = d / target
        f.write_text("", encoding="utf-8")
        for name in patches:
            text_of = (replace or {}).get(name)
            if text_of is None:
                text_of = (HERE / name).read_text(encoding="utf-8")
            for hunk, pre in hunks(text_of, target):
                seen += 1
                if _apply(git, d, target, hunk):
                    continue
                gaps += 1
                by_patch[name] = by_patch.get(name, 0) + 1
                text = f.read_text(encoding="utf-8")
                if text and not text.endswith("\n"):
                    text += "\n"
                f.write_text(text + f"{GAP} {gaps}\n" + "\n".join(pre) + "\n",
                             encoding="utf-8")
                if not _apply(git, d, target, hunk):
                    return None, log + [f"{name}: a hunk does not apply even to its own "
                                        f"pre-image:\n{hunk[:400]}"]
                log.append(f"{name}: materialised {len(pre)} line(s) of the original")
        return f.read_text(encoding="utf-8"), log
    finally:
        if stats is not None:
            stats.update(target=target, hunks=seen, materialised=gaps,
                         by_patch=dict(by_patch))
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
