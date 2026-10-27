"""test_cloud_say_yes.py - cloud-say-yes.patch: the owner's "Try the cloud
model" for one question actually reaches jarvis_router.choose()'s own
`owner_said_yes` gate, AND Project Mode's Shareable switch is read at that same
call as a second way to empty the lane list (docs/ARCHITECTURE.md "Cloud / API
keys"; docs/JARVIS-API.md "`offer` in `X-Jarvis-Route`";
docs/PROJECTS-DESIGN.md "a Shareable switch per project, off by default").

    python3 backend/test_cloud_say_yes.py

WHY THIS TEST FILE LOOKS DIFFERENT FROM THE OTHERS

Every other patch against jarvis_hud.py in this repository lands beside a
call an EARLIER patch already introduced, so `_stack.stand_in()` can
reconstruct real, patch-authored context for it and the usual round-trip
test (apply the new patch to that stand-in, reverse it, compare) proves
something real. `jarvis_router.choose()`'s call site is different: no
patch before this one had ever touched it, so `_stack.stand_in()` would
hand back a stand-in with a GAP exactly where this hunk needs to land -
applying the hunk to that gap would tell us nothing (see `_stack.py`'s own
docstring, "What it cannot say").

So this patch was written against the owner's real file, sent to this
session by hand (2026-09-27) as fifteen lines of real, verified context
around `jarvis_hud.py:2560` - not derived, not guessed. `t_the_patch`
below round-trips the patch against exactly that pre-image, quoted here as
a literal fixture, rather than against a `_stack` reconstruction. The
fixture's SIZE is load-bearing and is explained under "WHY THE PRE-IMAGE IS
SIXTEEN LINES AGAIN" below.
That is a weaker guarantee than the usual test - it proves the patch is
internally consistent and does what it claims to THAT snapshot, not that
the snapshot still matches the owner's file today. Re-verify against the
real file before trusting this patch on a PC whose jarvis_hud.py has
changed around that line since 2026-09-27.

THE PROJECT MODE GATE, AND THE 500 THIS FILE FIRST MISSED

`lanes=<the Project Mode gate>` was added (2026-10-15) ON the existing
`lanes=` line inside the SAME hunk, because a second `lanes=` argument is a
duplicate keyword argument - a SyntaxError, so the backend would not start -
and a second `.patch` file costs registration in three lists plus a
catalogue regeneration. `t_the_patch` re-applies it to the real pre-image and
reverses it; `t_the_patch_counts_match` keeps the `@@` header honest, which
is what `git apply` refuses the whole file over.

WHY THE PRE-IMAGE IS SIXTEEN LINES AGAIN (2026-10-16), AND THE STUCK PC

This patch has two lives. The 2026-09-27 original (recorded at
`backend/patch-history/cloud-say-yes/3583bf0.patch`) has the plain
`lanes=[] if jarvis_side_memory else lanes,` line and NO `owner_said_yes`
block, and it ADDS that block. The 2026-10-15 rewrite (21146d37, PR #468) put
the Project Mode gate into the same hunk, and its own context then REACHED the
`owner_said_yes` lines this repository had added the day before: its pre-image
became the state the original leaves - twenty-seven lines - and it added the
gate alone.

Two texts like that do not commute, and that is what stuck the owner's PC.
`apply-patches.ps1` finds an older text on a backend by reversing the patch
(`git apply --reverse`), and a backend updated before an edit still carries
the older text. On his, it found the 2026-09-27 text - rightly, that is what
he had - took it off, which REMOVED the `owner_said_yes` block, and then could
not put the current text on, because that text NEEDS the block as context.
Measured on a byte-verified copy of his backend: `2 patch(es) will not apply:
cloud-say-yes.patch, screen.patch`, and screen.patch only because it too
anchors on the block the strip took off.

So this patch is ONE hunk whose pre-image is the TRUE pre-patch text - the
plain `lanes=` line and no `owner_said_yes` block - and which adds BOTH the
Project Mode gate AND the `owner_said_yes` block. Strip the 2026-09-27 text,
land on that pre-image, apply this; and a backend that already carries this
text takes itself off with no history at all, because the text it reverses is
its own. Two checks keep it that way:

  * `t_the_patch_is_self_contained` - `owner_said_yes` must be a line this
    patch ADDS, never one it expects to find. That one rule is the whole fix.
  * `t_the_strip_and_reapply_round_trip` - the owner's exact sequence, run
    here with real `git apply`: old text on, old text OFF, this patch on. It
    also rebuilds the 2026-10-15 shape and shows the same sequence REFUSING
    for it, so the check has a bite rather than a story.

THE INSTRUMENT WAS BROKEN AND THIS FILE PASSED OVER A 500 ON THE COMMON
PATH. As first committed (9a596c4f), the guard called
`jarvis_projects.get().get(jarvis_projects.active_project_id())` with no test
on the id first. `Projects._project_row` raises `KeyError(pid)` for an id
that is not a string, and `active_project_id()` is `None` on EVERY turn with
no Project Mode active - so that line was a 500 on an ordinary chat turn, not
only on a deleted-project one. It survived this suite because `_stub_projects`
answered for ANY pid handed to it, `None` included: a stub that models nothing
cannot fail. Both halves are now fixed and both are pinned:

  * the id is tested before it is used - `isinstance(..., str) and bool(p)` -
    so None, "" and a non-string id all answer `[]` without reaching `get()`;
    `t_the_ordinary_turn_does_not_raise` asserts the store is never asked, and
    `t_the_old_expression_fails_this_suite` runs the OLD expression through the
    same stub and shows it raising `KeyError(None)`.
  * `_stub_projects` now raises exactly as `Projects._project_row` does, for a
    non-string pid and for an id with no row;
    `t_the_stub_the_old_suite_used_could_not_see_it` is what says so.

One state is still not survived, and is pinned rather than hidden: an
id-shaped pointer whose row is gone (a `projects.db` restored from an older
backup) still reaches `get()` and raises. A single expression cannot catch an
exception. The ORDINARY way that state was created - deleting the active
project - is closed by `fix/active-project-deleted` (29a9cf81, merged into
this branch): `Projects._delete` clears the mode file, measured end-to-end in
`t_the_deleted_active_project_clears_project_mode` against the real module.

The guard reads the project's Shareable flag through `jarvis_projects`, and
it does its own `import` inside the inserted line, so `backend/`'s copy of
this file never needs `jarvis_projects` to be an importable name at module
scope. No active project, an id that is not a string, and no
`jarvis_projects.py` at all all end in `[]` - local.

What is still NOT proven here: that the owner's file at that point in the
stack is byte-for-byte `_PRE`. Only a PC holding his jarvis_hud.py can say
that.

`jarvis_router.choose()`'s own `owner_said_yes` gate - what actually makes
a "yes" safe (every privacy gate still runs first, in order) - is real,
shipped code, and already has real tests: test_rebuilt.py and
test_chat_stream_contract.py's own `owner_said_yes=True` cases. Nothing
here repeats those; this file tests only the one thing that is new: does
the patch itself wire the request through to that already-proven gate,
in the right place, doing nothing else.
"""
from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _stack  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


#: The exact real lines this patch was written against (jarvis_hud.py,
#: around 2557 on the owner's PC) - see the module docstring for why this is a
#: literal fixture rather than a `_stack` stand-in.
#:
#: THIS IS THE TRUE PRE-IMAGE, and it is sixteen lines because the patch is
#: SELF-CONTAINED: the plain `lanes=` line, and no `owner_said_yes` block. It
#: was sixteen lines until 2026-10-15, when the Project Mode gate was added to
#: this same hunk and the context grew to twenty-seven lines (reaching the
#: `owner_said_yes` block), and it is sixteen again from 2026-10-16 - see the
#: module docstring's "WHY THE PRE-IMAGE IS SIXTEEN LINES AGAIN" for the stuck
#: PC that cost, and why the round trip below is the check that keeps it
#: honest. The fixture is the patch's own pre-image, checked against the patch
#: by `t_the_patch`'s round trip.
_PRE = '''\
        if ROUTING and body.get("auto", True):
            budget = jarvis_router.Budget.load()
            tainted = _history_tainted(messages, body)
            decision = jarvis_router.choose(
                query,
                local_model=local_model,
                # While Jarvis injects memory itself we cannot escalate safely:
                # it would attach your facts to a free-tier cloud request.
                lanes=[] if jarvis_side_memory else lanes,
                has_image=bool(body.get("has_image")),
                conversation_tainted=tainted,
                budget=budget,
            )
            if jarvis_side_memory and decision.gate == "unavailable":
                decision.reason = "escalation off while Jarvis injects memory itself"
                decision.gate = "privacy"
'''

#: The same real lines with the `owner_said_yes` block AND the Project Mode
#: gate now in them, which is what applying the patch to `_PRE` must produce.
#: The gate is deliberately NOT a second `lanes=` argument: a repeated keyword
#: argument is a SyntaxError ("keyword argument repeated"), so the backend
#: would not start at all - `t_the_patch`s own "still valid Python" check is
#: what catches that.
_POST = '''\
        if ROUTING and body.get("auto", True):
            budget = jarvis_router.Budget.load()
            tainted = _history_tainted(messages, body)
            decision = jarvis_router.choose(
                query,
                local_model=local_model,
                # While Jarvis injects memory itself we cannot escalate safely:
                # it would attach your facts to a free-tier cloud request.
                # cloud-say-yes.patch: Project Mode's gate, on the SAME line
                # and never as a second `lanes=` argument - a repeated keyword
                # argument is a SyntaxError ("keyword argument repeated"), so
                # the backend would not start at all. `[]` is the one value
                # that can only ever REMOVE a lane, so empty lanes stay empty
                # and the lanes that were passed are never added to. Nothing
                # leaves this PC from a project until the owner has turned
                # that project's Shareable switch on himself
                # (docs/PROJECTS-DESIGN.md).
                #
                # THE ID IS TESTED BEFORE IT IS USED, and that is not
                # tidiness: Projects.get() RAISES KeyError for an id that is
                # not a string (Projects._project_row: "if not isinstance(pid,
                # str) ... raise KeyError(pid)"), and active_project_id() is
                # None on EVERY ordinary turn. Handing that None to get() is
                # a KeyError out of the chat turn - measured against the real
                # module, not assumed. So no active project, an empty id and
                # a non-string id all answer "local" without ever reaching
                # get(). An id that IS a string but is not a row would still
                # raise; jarvis_projects' own delete path clears the mode file
                # when it deletes the active project, so no such id is left.
                lanes=[] if jarvis_side_memory else (lanes if (lambda m: hasattr(m, "active_project_id") and isinstance((p := m.active_project_id()), str) and bool(p) and bool((m.get().get(p) or {}).get("shareable")))(__import__("jarvis_projects")) else []),
                has_image=bool(body.get("has_image")),
                conversation_tainted=tainted,
                budget=budget,
                # cloud-say-yes.patch: the owner's yes for THIS ONE
                # question - the app's "Try the cloud model" button, shown
                # only after choose() itself already offered a lane with
                # gate "offer" (docs/JARVIS-API.md, "`offer` in
                # `X-Jarvis-Route`"). Absent or false reads exactly as
                # before this patch. Every gate above still runs first, in
                # the same order, so a yes can never pull a private,
                # tainted or picture turn out - it only ever turns gate 6
                # from "offer" into "escalate" for a question that had
                # already cleared every other gate on its own merits.
                owner_said_yes=bool(body.get("cloud_yes")),
            )
            if jarvis_side_memory and decision.gate == "unavailable":
                decision.reason = "escalation off while Jarvis injects memory itself"
                decision.gate = "privacy"
'''

#: The three lanes the owner's own ~/.openjarvis/litellm-proxy.yaml defines.
LANES = ["jarvis-escalate", "jarvis-critic", "jarvis-bulk"]


def _patch_text() -> str:
    return (HERE / "cloud-say-yes.patch").read_text(encoding="utf-8")


def _guard_line(patch_text: str = None) -> str:
    """The whole `lanes=` line the patch INSTALLS, read out of the patch file.

    Read from the patch rather than re-typed, so a drift between this suite's
    fixture and the patch it claims to test cannot pass quietly: every check
    below is about the line that would really be installed. The patch REPLACES
    the old line here rather than adding another, so this is the `+` half of a
    `-`/`+` pair."""
    text = _patch_text() if patch_text is None else patch_text
    added = [l[1:] for l in text.splitlines()
             if l.startswith("+") and l[1:].strip().startswith("lanes=")
             and "jarvis_projects" in l]
    return added[0].strip() if len(added) == 1 else ""


def _guard_expr(patch_text: str = None) -> str:
    """Just the expression, `lanes=` and the trailing comma taken off, so it
    can be evaluated on its own."""
    line = _guard_line(patch_text)
    return line[len("lanes="):].rstrip().rstrip(",").strip()


#: The id shape `jarvis_projects._ID` accepts. Copied from that module so the
#: stub below refuses exactly what `Projects._project_row` refuses.
_ID_LIKE = re.compile(r"^[0-9a-f]{32}$")


def _stub_projects(pid, row, *, has_module=True, rows=None, raise_on_get=None):
    """A `jarvis_projects` that behaves like the real one, not like a rubber
    stamp: which project is active, and what a lookup really answers.

    THE STUB IS AN INSTRUMENT AND WAS ONCE A BROKEN ONE. It used to return
    `row` for ANY pid handed to it, `None` included - so the no-active-project
    case, which is every ordinary turn, could never fail here while the REAL
    `Projects.get()` raised `KeyError(None)` out of `Projects._project_row`
    ("if not isinstance(pid, str) ... raise KeyError(pid)"). This suite passed
    over a 500 on the common path. It now raises the way the real store does:
    a pid that is not a string at all, or an id that is not a row, both raise
    `KeyError(pid)`. Nothing is returned for a pid the real store would refuse.
    """
    mod = types.ModuleType("jarvis_projects")
    if has_module:
        mod.active_project_id = lambda: pid
        known = dict(rows or {})

        class _Store:
            def get(self, pid_asked):
                if raise_on_get is not None:
                    raise (
                        KeyError(pid_asked) if raise_on_get is True else raise_on_get
                    )
                if not isinstance(pid_asked, str) or not _ID_LIKE.match(pid_asked):
                    # Projects._project_row, word for word.
                    raise KeyError(pid_asked)
                if pid_asked not in known:
                    # ... and its second raise, for an id with no row.
                    raise KeyError(pid_asked)
                return known[pid_asked]

        mod.get = lambda: _Store()
    sys.modules["jarvis_projects"] = mod
    return mod


def _lanes_from_patch(*, pid, row=None, rows=None, has_module=True, memory=False,
                      lanes=None, raise_on_get=None):
    """Evaluate the patch's own guard line exactly as the installed HUD would.

    `jarvis_projects` is put in sys.modules first, so the line's own
    `__import__("jarvis_projects")` finds this stub on any machine. `row` is
    shorthand for "this one id has this row"; `rows` is the whole table."""
    if rows is None:
        rows = {} if row is None else ({pid: row} if isinstance(pid, str) else {})
    _stub_projects(pid, row, has_module=has_module, rows=rows,
                   raise_on_get=raise_on_get)
    expr = _guard_expr()
    return eval(expr, {"jarvis_side_memory": memory,
                       "lanes": list(LANES if lanes is None else lanes)})


def _restore_modules(saved):
    if saved is None:
        sys.modules.pop("jarvis_projects", None)
    else:
        sys.modules["jarvis_projects"] = saved


#: The line number the patch's single `@@` header names. Only used to rebuild
#: the header text; `git apply` finds the hunk by context either way.
_HUNK_START = 2557


def _one_hunk(patch_text: str, target: str = "jarvis_hud.py") -> list:
    """The `@@` header plus every line of the patch's FIRST hunk for `target`,
    in the patch's own order, stopping as soon as that hunk is complete.

    `_stack.hunks()` is the repository's patch reader and this suite keeps
    using it for the fixture round trip - but it does not stop at a complete
    hunk's last line: the hunk it returns here ran on into the SECOND hunk and
    the file's trailing newline (measured 2026-10-15 in %TEMP%\\s4-wiring:
    25 context + 14 added against the file's own 16 + 14). That is invisible
    while every patch is one hunk - which is why nobody had hit it - and this
    suite rebuilds a `git apply`-able file, so it cannot afford the overshoot.
    """
    wanted = f"b/{target}"
    lines = patch_text.replace("\r\n", "\n").split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.startswith("+++ ") and line.split()[1] == wanted:
            start = i + 1
            break
    if start is None:
        return []
    at = next((i for i in range(start, len(lines)) if lines[i].startswith("@@")), None)
    if at is None:
        return []
    # NB: the hunk's own `@@` counts are deliberately NOT used to decide where
    # it ends. The whole point of this helper is to MEASURE those counts; a
    # stale header must not be able to hide lines from the measurement.
    out = [lines[at]]
    for line in lines[at + 1:]:
        if line == "":
            break                      # the newline that ends the patch
        if line.startswith(("@@", "diff ", "--- ", "+++ ", "index ")):
            break
        out.append(line)
    return out


def _apply_patch_text(patch_text: str, target: str = "jarvis_hud.py") -> str:
    """The patch, rebuilt with the `@@` counts taken from what its body really
    holds, ready for `git apply`.

    The counts are rewritten because a hunk that has been edited by hand is
    exactly where an `@@` header goes stale - and `git apply` refuses the whole
    file with "corrupt patch" when it does, which reads like the patch is
    broken rather than like the header is wrong."""
    lines = _one_hunk(patch_text, target)
    old = sum(1 for l in lines[1:] if l[:1] in (" ", "-"))
    new = sum(1 for l in lines[1:] if l[:1] in (" ", "+"))
    header = f"@@ -{_HUNK_START},{old} +{_HUNK_START},{new} @@"
    return f"--- a/{target}\n+++ b/{target}\n{header}\n" + "\n".join(lines[1:]) + "\n"


def t_the_patch_counts_match():
    """The `@@` header the patch file carries must be what its body really
    holds - a header that disagrees by one line is a patch `git apply` refuses,
    which is exactly what happened here when the guard was added."""
    lines = _one_hunk(_patch_text())
    old = sum(1 for l in lines[1:] if l[:1] in (" ", "-"))
    new = sum(1 for l in lines[1:] if l[:1] in (" ", "+"))
    declared = lines[0]
    check("the @@ header's old-line count matches the body",
          f"-{_HUNK_START},{old} " in declared,
          f"header={declared!r} body says {old} old line(s)")
    check("the @@ header's new-line count matches the body",
          f"+{_HUNK_START},{new} " in declared,
          f"header={declared!r} body says {new} new line(s)")
    check("the patch REPLACES the old lanes= line rather than adding a second",
          sum(1 for l in lines if l[:1] == "-" and "lanes=" in l) == 1
          and sum(1 for l in lines if l[:1] == "+" and l[1:].strip().startswith("lanes=")) == 1,
          "a second `lanes=` argument would be a SyntaxError in jarvis_hud.py")


def _context_owner_said_yes(patch_text: str) -> str:
    """The 2026-10-15 shape of this patch, rebuilt from the current one: the
    `owner_said_yes` block back as CONTEXT, which is the shape that could not
    follow its own strip. Used only by the bite check in
    `t_the_strip_and_reapply_round_trip`, so that check can fail if the fix is
    ever undone. `_apply_patch_text` recomputes the `@@` counts, so this copy
    cannot fail for the wrong reason (a stale header)."""
    lines = _one_hunk(patch_text)
    out, in_yes = [lines[0]], False
    for line in lines[1:]:
        if line[:1] == "+" and "the owner's yes for THIS ONE" in line:
            in_yes = True
        if in_yes and line[:1] == "+":
            line = " " + line[1:]
            if "owner_said_yes=bool" in line:
                in_yes = False
        out.append(line)
    return "\n".join(out) + "\n"


def t_the_patch_is_self_contained():
    """THE ONE RULE THAT KEEPS A BACKEND UNSTUCK: this patch must carry its own
    pre-image.

    `apply-patches.ps1` finds the text already on a backend by REVERSING the
    patch, and an older text it finds there is taken off before the current
    text goes on. So the current text must be applicable to whatever taking an
    older text off leaves behind. `owner_said_yes` is a line the 2026-09-27
    text ADDS; if this patch ever expects it as CONTEXT again - the shape the
    2026-10-15 rewrite had - then stripping that older text removes the block
    and this patch refuses a file it just created. That is the two-patch
    failure measured on the owner's backend on 2026-10-16; see the module
    docstring."""
    body = _one_hunk(_patch_text())[1:]
    ctx = [l for l in body if l[:1] == " " and "owner_said_yes" in l]
    added = [l for l in body if l[:1] == "+" and "owner_said_yes" in l]
    check("owner_said_yes is ADDED by this patch, never expected as context",
          not ctx and len(added) == 1, f"context={ctx} added={added}")
    check("... and the plain lanes= line is REMOVED, so the pre-image is the true one",
          len([l for l in body if l[:1] == "-" and "lanes=" in l]) == 1,
          [l for l in body if l[:1] == "-"])
    check("... and the fixture above really has no owner_said_yes in it",
          "owner_said_yes" not in _PRE, "the fixture still carries the block")


def t_the_strip_and_reapply_round_trip():
    """THE SEQUENCE THAT FAILED ON THE OWNER'S PC, run here with real git apply.

    His backend carried the 2026-09-27 text. The script took that off - which
    removed the `owner_said_yes` block - and then could not put the current
    text back on, because the current text needed that block as context. So:
    the older text on, the older text OFF, then THIS patch on, and the result
    must be `_POST`.

    BITE: the same three applies are run again with the 2026-10-15 shape of
    the patch (the block as context, rebuilt by `_context_owner_said_yes`) and
    must REFUSE. Without that half this would be a story about a bug rather
    than a check on the fix."""
    git = shutil.which("git")
    if not git:
        check("git is here to apply it", False)
        return
    hist = HERE / "patch-history" / "cloud-say-yes" / "3583bf0.patch"
    if not hist.is_file():
        check("the recorded 2026-09-27 text is in backend/patch-history", False,
              f"no {hist}")
        return
    patch = _patch_text()
    d = Path(tempfile.mkdtemp(prefix="jarvis-cloud-say-yes-roundtrip-"))
    try:
        (d / "old.patch").write_bytes(hist.read_bytes())
        (d / "p.patch").write_text(_apply_patch_text(patch), encoding="utf-8", newline="")
        (d / "broken.patch").write_text(
            _apply_patch_text(_context_owner_said_yes(patch)), encoding="utf-8", newline="")

        (d / "jarvis_hud.py").write_text(_PRE, encoding="utf-8", newline="\n")
        on = subprocess.run([git, "apply", "old.patch"], cwd=d, capture_output=True, text=True)
        check("the 2026-09-27 text goes on to the true pre-image (his state)",
              on.returncode == 0, on.stderr)
        off = subprocess.run([git, "apply", "-R", "old.patch"], cwd=d, capture_output=True, text=True)
        stripped = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        check("... taking it off lands back on the true pre-image, byte for byte",
              off.returncode == 0 and stripped == _PRE, (off.stderr, stripped[:200]))
        r = subprocess.run([git, "apply", "p.patch"], cwd=d, capture_output=True, text=True)
        after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        check("... and THIS patch then applies to what the strip left",
              r.returncode == 0, r.stderr)
        check("... producing exactly the post-image fixture", after == _POST,
              "the patch and _POST have drifted apart")

        (d / "jarvis_hud.py").write_text(_PRE, encoding="utf-8", newline="\n")
        subprocess.run([git, "apply", "old.patch"], cwd=d, capture_output=True, text=True)
        subprocess.run([git, "apply", "-R", "old.patch"], cwd=d, capture_output=True, text=True)
        rb = subprocess.run([git, "apply", "broken.patch"], cwd=d, capture_output=True, text=True)
        check("BITE: with the owner_said_yes block as CONTEXT the same sequence refuses",
              rb.returncode != 0,
              "the old shape applied, so this check could not have caught the bug")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_the_patch():
    order = _stack.order()
    check("cloud-say-yes.patch is in apply-patches.ps1's list",
          "cloud-say-yes.patch" in order, order[-4:])
    patch = _patch_text()
    check("it patches jarvis_hud.py and nothing else",
          sorted(l[6:].strip() for l in patch.splitlines() if l.startswith("+++ b/"))
          == ["jarvis_hud.py"])
    check("it is still ONE hunk", len(_stack.hunks(patch, "jarvis_hud.py")) == 1)
    git = shutil.which("git")
    if not git:
        check("git is here to apply it", False)
        return
    target = "jarvis_hud.py"
    d = Path(tempfile.mkdtemp(prefix="jarvis-cloud-say-yes-patch-"))
    try:
        (d / target).write_text(_PRE, encoding="utf-8", newline="\n")
        (d / "p.patch").write_text(_apply_patch_text(patch), encoding="utf-8", newline="")
        r = subprocess.run([git, "apply", "p.patch"], cwd=d, capture_output=True, text=True)
        ok = r.returncode == 0
        after = (d / target).read_text(encoding="utf-8") if ok else ""
        r2 = subprocess.run([git, "apply", "-R", "p.patch"], cwd=d, capture_output=True,
                            text=True)
        back = (d / target).read_text(encoding="utf-8") == _PRE
        check(f"{target}: applies to the real snapshot it was written against, and reverses",
              ok and r2.returncode == 0 and back, (r.stderr, r2.stderr))
        check("... and the result is exactly this file's own post-image fixture",
              after == _POST, "the patch and _POST have drifted apart")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    if not after:
        check("the new line is inside the auto-routing choose() call", False, "no post-image")
        return
    # The call's own closing paren is the FIRST one on its own line at the
    # call's indent (12 spaces) after `owner_said_yes` - not the first `)`
    # textually, which closes `body.get(...)` one token in.
    call_start = after.index("decision = jarvis_router.choose(")
    said_yes_at = after.index("owner_said_yes", call_start)
    call_end = after.index("\n            )", said_yes_at)
    call_body = after[call_start:call_end]
    check("owner_said_yes is a real argument to THIS choose() call, not floating loose",
          "owner_said_yes=bool(body.get(\"cloud_yes\"))" in call_body, call_body)
    check("the Project Mode gate is a real argument to the same call",
          _guard_line() in call_body, call_body)
    # The whole post-image must still be Python: an inserted line that will not
    # parse is a backend that will not start.
    try:
        ast.parse("if 1:\n" + "\n".join("    " + l for l in after.splitlines()) + "\n")
        parsed = True
    except SyntaxError as exc:
        parsed = False
        check("the inserted region is still valid Python", False, str(exc))
    if parsed:
        check("the inserted region is still valid Python", True)
    # This choose() call only exists inside the auto-routing branch
    # (`if ROUTING and body.get("auto", True):` - the fixture's own first
    # line) - the manual-lane branch a few lines below built its Decision
    # with `_manual_decision`, a wholly different call this patch's hunk
    # never touches. That manual path had NO privacy gating at all until
    # `f01-manual-lane-gate.patch` (F-01, 2026-10-27), which is a LATER patch
    # in the stack and not this one's business: this fixture is `_PRE`, so
    # nothing here can see it. Whether anything OTHER
    # than the intended lines changed is already proven above: reversing
    # the patch reproduced `_PRE` byte for byte, which a stray
    # edit anywhere else in the hunk could not have survived.


def t_the_guard_is_the_patch_s_own():
    """The guard line is real, unique, and the old memory-injection guard is
    still inside it - so the rule-1 switch this repository already tests in
    test_cloud_lane_precondition.py has not been replaced by the new one."""
    line = _guard_line()
    check("the patch inserts exactly one lanes= guard", bool(line), line)
    # The whole point of the file's other suite (test_cloud_lane_precondition.py
    # reads this substring out of the installed jarvis_hud.py): the memory
    # switch must still be the FIRST thing the guard tests, unchanged.
    check("... and it still begins with the memory-injection guard, unchanged",
          "lanes=[] if jarvis_side_memory else" in line, line)
    check("... and it reads the active project's Shareable switch",
          "jarvis_projects" in line and "shareable" in line, line)
    try:
        ast.parse(_guard_expr(), mode="eval")
        check("... and the guard is valid Python on its own", True)
    except SyntaxError as exc:
        check("... and the guard is valid Python on its own", False, str(exc))


_PID = "0123456789abcdef0123456789abcdef"
_SHARED = {"id": _PID, "shareable": True}
_UNSHARED = {"id": _PID, "shareable": False}
#: A second, different id, so "some other project is the active one" is a real
#: state and not the same string under another name.
_OTHER = "fedcba9876543210fedcba9876543210"


def t_lanes_can_only_be_removed():
    """THE BITE THAT MATTERS: over every state the gate can be in, the value
    handed to choose() is either exactly the list that was passed in, or `[]`.
    Nothing else is reachable, so the guard can never ADD a lane - and a
    Shareable project really does keep its lanes, so the guard is not just
    always returning `[]`.

    Every case below goes through the stub that RAISES the way the real store
    raises, and `rows` is filled in ONLY for ids that really have a row. Every
    state listed is one the guard can really meet: with
    `fix/active-project-deleted` merged, `Projects._delete` clears the mode
    file when it deletes the active project, so an id whose row is gone is not
    a state this line has to survive - see
    `t_an_id_shaped_pointer_with_no_row` for the one that is left."""
    cases = [
        ("Project Mode off (active is None)",
         dict(pid=None, rows={})),
        ("active is the empty string",
         dict(pid="", rows={})),
        ("active is not a string at all",
         dict(pid=17, rows={})),
        ("active, Shareable off (the default)",
         dict(pid=_PID, rows={_PID: _UNSHARED})),
        ("active, Shareable on",
         dict(pid=_PID, rows={_PID: _SHARED})),
        ("active, no jarvis_projects.py",
         dict(pid=_PID, rows={_PID: _SHARED}, has_module=False)),
    ]
    rows = []
    for name, kw in cases:
        for memory in (False, True):
            saved = sys.modules.get("jarvis_projects")
            try:
                got = _lanes_from_patch(memory=memory, **kw)
            except Exception as exc:            # noqa: BLE001 - reported, not swallowed
                check(f"{name} (memory={memory}): the guard does not raise", False,
                      f"{type(exc).__name__}: {exc}")
                continue
            finally:
                _restore_modules(saved)
            rows.append((name, memory, got))
            check(f"{name} (memory={memory}): only [] or the lanes that were passed",
                  got == [] or got == list(LANES), got)
    shared = [r for r in rows if r[0] == "active, Shareable on" and r[1] is False]
    check("a Shareable project keeps its cloud lanes (so the guard is not vacuous)",
          bool(shared) and shared[0][2] == list(LANES), shared)
    off = [r for r in rows if r[0].startswith("active, Shareable off") and r[1] is False]
    check("a project that is NOT Shareable loses every cloud lane",
          bool(off) and off[0][2] == [], off)
    check("... and an empty lane list stays empty in every state",
          all(_empty_stays_empty(name) for name in
              [n for n, _ in cases]), "")


def t_an_id_shaped_pointer_with_no_row():
    """WHAT IS STILL NOT SURVIVED, said plainly instead of left implicit.

    An id that is a real 32-hex id but has no row (a `projects.db` restored
    from an older backup, or a mode file edited by hand) still reaches
    `Projects.get()` and raises `KeyError(id)`. A single expression cannot
    catch an exception, and the ORDINARY way that state was created -
    deleting the active project - is closed by
    `fix/active-project-deleted` (29a9cf81): measured in
    `t_the_deleted_active_project_clears_project_mode`, `active_project_id()`
    answers None afterwards, which the guard's own test handles. This check
    pins the leftover behaviour so nobody has to guess at it later."""
    saved = sys.modules.get("jarvis_projects")
    try:
        _stub_projects(_OTHER, None, rows={_PID: _SHARED})
        try:
            got = eval(_guard_expr(), {"jarvis_side_memory": False,
                                       "lanes": list(LANES)})
            raised = None
        except Exception as exc:                # noqa: BLE001
            got, raised = None, exc
    finally:
        _restore_modules(saved)
    check("an id-shaped pointer with no row still raises (measured, not hidden)",
          isinstance(raised, KeyError), (raised, got))


def t_the_ordinary_turn_does_not_raise():
    """THE 500 THAT WAS SHIPPING IN THIS LINE, measured. `Projects.get()` raises
    `KeyError` for an id that is not a string, and `active_project_id()` is
    `None` on every turn with no Project Mode active - so a guard that hands
    that None straight to `get()` takes down the common path, not just the
    deleted-project one. The id must be tested BEFORE it is used.

    The check is written so it FAILS on the old shape of the line: it asserts
    both that nothing raises AND that the store was never asked at all."""
    line = _guard_line()
    check("the guard tests the id before it uses it",
          "isinstance(" in line and "active_project_id()" in line,
          "no isinstance guard: a None or non-string id would reach get()")
    for label, pid in (("no project active (None, every ordinary turn)", None),
                       ("the empty string", ""),
                       ("an int where an id belongs", 17)):
        saved = sys.modules.get("jarvis_projects")
        asked = []
        try:
            _stub_projects(pid, None, rows={})
            real_get = sys.modules["jarvis_projects"].get

            class _Recording:
                def get(self, pid_asked):
                    asked.append(pid_asked)
                    return real_get().get(pid_asked)

            sys.modules["jarvis_projects"].get = lambda: _Recording()
            try:
                got = eval(_guard_expr(), {"jarvis_side_memory": False,
                                           "lanes": list(LANES)})
                raised = None
            except Exception as exc:            # noqa: BLE001
                got, raised = None, exc
        finally:
            _restore_modules(saved)
        check(f"{label}: the guard does not raise", raised is None,
              f"{type(raised).__name__}: {raised}" if raised else "")
        check(f"{label}: and the store is never asked for that id", asked == [], asked)
        check(f"{label}: so the turn stays local", got == [], got)


def t_the_stub_the_old_suite_used_could_not_see_it():
    """BITE, and the reason this file went green while the line was broken: the
    stub must refuse what the real store refuses. If it ever answers for None
    or for an id with no row, `t_the_ordinary_turn_does_not_raise` can pass
    over a real 500 and this check is what says so."""
    saved = sys.modules.get("jarvis_projects")
    try:
        _stub_projects(None, None, rows={})
        store = sys.modules["jarvis_projects"].get()
        for label, pid_asked in (("None", None), ("an int", 17),
                                 ("a string that is not an id", "p1"),
                                 ("an id with no row", _OTHER)):
            try:
                store.get(pid_asked)
                check(f"the stub raises KeyError for {label}, like _project_row", False,
                      "it answered instead - this is the rubber stamp that hid the 500")
            except KeyError:
                check(f"the stub raises KeyError for {label}, like _project_row", True)
        check("... and it still answers for an id that really has a row", True)
        _stub_projects(_PID, None, rows={_PID: _UNSHARED})
        check("... and it really does return the row for a live id",
              sys.modules["jarvis_projects"].get().get(_PID) == _UNSHARED)
    finally:
        _restore_modules(saved)


def _empty_stays_empty(name):
    """The one property that must hold everywhere: `[]` in, `[]` out - the
    memory-injection line's own promise, now covering the project gate too."""
    kw = {
        "Project Mode off (active is None)": dict(pid=None, rows={}),
        "active is the empty string": dict(pid="", rows={}),
        "active is not a string at all": dict(pid=17, rows={}),
        "active, Shareable off (the default)": dict(pid=_PID, rows={_PID: _UNSHARED}),
        "active, Shareable on": dict(pid=_PID, rows={_PID: _SHARED}),
        "active, no jarvis_projects.py": dict(pid=_PID, rows={_PID: _SHARED},
                                              has_module=False),
    }[name]
    for memory in (False, True):
        saved = sys.modules.get("jarvis_projects")
        try:
            if _lanes_from_patch(memory=memory, lanes=[], **kw) != []:
                return False
        except Exception:                       # noqa: BLE001
            return False
        finally:
            _restore_modules(saved)
    return True


def t_the_guard_survives_removal():
    """BITE: delete the guard line from a copy of the patch and show that the
    checks above go red. Without this, `t_the_guard_is_the_patch_s_own` and
    `t_lanes_can_only_be_removed` could keep passing against a patch whose
    guard had been dropped or hollowed out."""
    patch = _patch_text()
    without = "\n".join(l for l in patch.splitlines()
                        if not (l.startswith("+") and "jarvis_projects" in l
                                and l[1:].strip().startswith("lanes=")))
    check("the guard line is gone from that copy", _guard_line(without) == "",
          _guard_line(without))
    check("... and the patch still has it", _guard_line(patch) != "", _guard_line(patch))
    # With the guard gone, the state that MUST stay local hands choose() the
    # cloud lanes - measured, not argued: run the OLD line, which is what the
    # patch would be left with.
    saved = sys.modules.get("jarvis_projects")
    try:
        _stub_projects(_PID, None, rows={_PID: _UNSHARED})
        old = eval("[] if jarvis_side_memory else lanes",
                   {"jarvis_side_memory": False, "lanes": list(LANES)})
        new = _lanes_from_patch(pid=_PID, rows={_PID: _UNSHARED}, memory=False)
    finally:
        _restore_modules(saved)
    check("with the guard, a not-Shareable active project offers NO lane",
          new == [], new)
    check("without it (the pre-change line), the SAME state still offers every lane",
          old == list(LANES), old)
    check("so the two differ, which is the whole point of the inserted line",
          old != new, (old, new))


def t_the_old_expression_fails_this_suite():
    """THE BITE FOR THE NO-PROJECT FIX, run against the expression this branch
    actually shipped in 9a596c4f.

    That line called `m.get().get(m.active_project_id())` with no test on the
    id first. With the stub now modelling the real store, it raises
    `KeyError(None)` on the ordinary no-Project-Mode turn - which is exactly
    what the real `Projects.get()` does, measured in this tree. The fixed line
    answers `[]`. If the old shape ever passes these checks again, the stub has
    gone back to being a rubber stamp."""
    old_expr = ('([] if jarvis_side_memory else (lanes if (lambda m: hasattr(m,'
                ' "active_project_id") and bool((m.get().get(m.active_project_id())'
                ' or {}).get("shareable")))(__import__("jarvis_projects")) else []))')
    saved = sys.modules.get("jarvis_projects")
    try:
        _stub_projects(None, None, rows={})
        try:
            eval(old_expr, {"jarvis_side_memory": False, "lanes": list(LANES)})
            old_raised = None
        except Exception as exc:                # noqa: BLE001
            old_raised = exc
    finally:
        _restore_modules(saved)
    saved = sys.modules.get("jarvis_projects")
    try:
        _stub_projects(None, None, rows={})
        try:
            fixed = eval(_guard_expr(), {"jarvis_side_memory": False,
                                         "lanes": list(LANES)})
            fixed_raised = None
        except Exception as exc:                # noqa: BLE001
            fixed_raised = exc
    finally:
        _restore_modules(saved)
    check("the OLD line raises KeyError(None) on the no-project turn (the 500)",
          isinstance(old_raised, KeyError), old_raised)
    check("the FIXED line answers [] on the same state",
          fixed_raised is None and fixed == [], (fixed_raised, fixed))
    check("so the fix is measurable on this stub, not just asserted",
          isinstance(old_raised, KeyError) and fixed == [], (old_raised, fixed))


def t_the_deleted_active_project_clears_project_mode():
    """The OTHER half of the reachable defect, and the reason it is folded in
    here: `fix/active-project-deleted` (29a9cf81, merged into this branch) makes
    `Projects._delete` clear the mode file when it deletes the ACTIVE project,
    so `active_project_id()` can never answer an id whose row is gone. The
    guard's own `isinstance` test covers None; the id that is a real-shaped
    string with no row is this commit's job.

    Measured against the REAL jarvis_projects from this tree, with its config
    and db redirected into a scratch folder."""
    real = Path(__file__).resolve().parent.parent / "jarvis-backend" / "jarvis_projects.py"
    if not real.is_file():
        print("skip  jarvis_projects.py is not in jarvis-backend/ here")
        return
    saved = sys.modules.pop("jarvis_projects", None)
    scratch = Path(tempfile.mkdtemp(prefix="jarvis-s4-mode-"))
    #: Project Mode now copies its pointer file through the guardian first;
    #: that copy must land in this scratch folder, never in the real store.
    saved_home = os.environ.get("OPENJARVIS_HOME")
    saved_receipts = os.environ.get("JARVIS_RECEIPTS_DB")
    os.environ["OPENJARVIS_HOME"] = str(scratch / "guardian-home")
    os.environ["JARVIS_RECEIPTS_DB"] = str(scratch / "receipts.db")
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("jarvis_projects_real", real)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod._config_dir = lambda: scratch
        mod.db_path = lambda: scratch / "projects.db"
        pid = mod.get().create({"name": "mode", "kind": "life"}, here=False)["id"]
        mod.set_active_project(pid)
        check("the real store has that project active",
              mod.active_project_id() == pid, mod.active_project_id())
        import jarvis_file_guardian as _guardian
        home = os.path.realpath(str(_guardian.home_dir()))
        check("the guardian store this Project Mode write used is under its own "
              "scratch folder", home.startswith(os.path.realpath(str(scratch))),
              (home, str(scratch)))
        mod.get().delete_full(pid)
        check("deleting the ACTIVE project leaves Project Mode (no dead id)",
              mod.active_project_id() is None, mod.active_project_id())
        # And now the guard's own read on that state answers local, no raise.
        check("... so the guard's read answers local on that state",
              _lanes_from_patch(pid=None, rows={}) == [], "guard did not answer []")
    finally:
        if saved_home is None:
            os.environ.pop("OPENJARVIS_HOME", None)
        else:
            os.environ["OPENJARVIS_HOME"] = saved_home
        if saved_receipts is None:
            os.environ.pop("JARVIS_RECEIPTS_DB", None)
        else:
            os.environ["JARVIS_RECEIPTS_DB"] = saved_receipts
        shutil.rmtree(scratch, ignore_errors=True)
        sys.modules.pop("jarvis_projects_real", None)
        if saved is not None:
            sys.modules["jarvis_projects"] = saved


def t_cloud_yes_is_read_as_a_plain_bool():
    # `body.get("cloud_yes")` on an older client that never sends the field,
    # or one that sends `false`, `None`, `""` or an unrelated type, must all
    # read as "no" - never a `TypeError`, never a truthy accident. This is
    # exactly the shape jarvis_router.choose()'s own docstring warns a
    # loosely-typed argument can hide a real bug behind (the `**_extra`
    # story it tells about `conversation_tainted`) - so it is checked here,
    # not assumed.
    for absent_or_falsy in (None, False, "", 0, []):
        body = {} if absent_or_falsy is None else {"cloud_yes": absent_or_falsy}
        check(f"body.get('cloud_yes') reads as False for {absent_or_falsy!r}",
              bool(body.get("cloud_yes")) is False, absent_or_falsy)
    check("body.get('cloud_yes') reads as True only when the field is really true",
          bool({"cloud_yes": True}.get("cloud_yes")) is True)


if __name__ == "__main__":
    for fn in (t_the_patch, t_the_patch_counts_match, t_the_patch_is_self_contained,
               t_the_strip_and_reapply_round_trip,
               t_the_guard_is_the_patch_s_own,
               t_lanes_can_only_be_removed, t_an_id_shaped_pointer_with_no_row,
               t_the_ordinary_turn_does_not_raise,
               t_the_stub_the_old_suite_used_could_not_see_it,
               t_the_guard_survives_removal, t_the_old_expression_fails_this_suite,
               t_the_deleted_active_project_clears_project_mode,
               t_cloud_yes_is_read_as_a_plain_bool):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            import traceback
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
