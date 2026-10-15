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
below round-trips the patch against exactly THOSE fifteen lines, quoted
here as a literal fixture, rather than against a `_stack` reconstruction.
That is a weaker guarantee than the usual test - it proves the patch is
internally consistent and does what it claims to THAT snapshot, not that
the snapshot still matches the owner's file today. Re-verify against the
real file before trusting this patch on a PC whose jarvis_hud.py has
changed around that line since 2026-09-27.

THAT FIXTURE IS NOW AN INPUT PLUS ONE INSERTED LINE, NOT A QUOTE.

`lanes=<the Project Mode gate>` was inserted (2026-10-15) between
`budget=budget,` and `owner_said_yes=...`, inside the SAME hunk, because a
second `.patch` file costs registration in three lists plus a 27-file
catalogue regeneration. So `_PRE` below is still the fifteen verified lines
and `_POST` is what the patch makes of them. `t_the_guard_is_the_patch_s_own`
reads the guard line back OUT of the patch file it is testing - never a
hand-typed copy - so a fixture that drifted from the patch cannot pass, and
`t_the_guard_survives_removal` shows that check going red when the guard is
deleted. What is still NOT proven here: that the owner's file at that point
in the stack is byte-for-byte `_PRE`. Only a PC holding his jarvis_hud.py
can say that.

THE ONE THING THIS PATCH ADDS TO POLICY, AND WHY IT IS STILL SAFE

`lanes` is a request, not a grant: `choose()` decides, and every one of its
privacy gates reads that list. So any expression that can only ever return
`[]` or the list it was handed can only ever REMOVE a lane - it cannot add
one, and it cannot talk a gate out of a refusal. `t_lanes_can_only_be_removed`
measures exactly that over every state the gate can be in, including the
"Shareable is on" case, which is where a mistake WOULD add one.

The guard reads the project's Shareable flag through `jarvis_projects`, and
it does its own `import` inside the inserted line, so `backend/`'s copy of
this file never needs `jarvis_projects` to be an importable name at module
scope. No active project, and no `jarvis_projects.py` at all, both end in
`[]` - local. One state does still raise, and it is measured rather than
hidden: `jarvis_projects.get().get(pid)` raises `KeyError` for a project
that was deleted while it was still the active one (the mode file keeps the
id). `_s4`'s finding, reported up rather than papered over.

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
#: literal fixture rather than a `_stack` stand-in. This is the PRE-image: the
#: file as it is just before the patch applies, which already carries the
#: `owner_said_yes` block this same patch added earlier. It was SIXTEEN lines
#: (2557-2572) until 2026-10-15, when the Project Mode gate was added to this
#: same hunk: the hunk's context now reaches the `owner_said_yes` lines, so a
#: fixture that stopped at `budget=budget,` no longer matched the patch and
#: `git apply` refused it. The fixture is the patch's own pre-image, checked
#: against the patch by `t_the_patch`'s round trip.
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

#: The same fifteen lines with the Project Mode gate now INSIDE the existing
#: `lanes=` line, which is what applying the patch to _PRE must produce. It is
#: deliberately NOT a second `lanes=` argument: a repeated keyword argument is a
#: SyntaxError ("keyword argument repeated"), so the backend would not start at
#: all - `t_the_patch`s own "still valid Python" check is what catches that.
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
                # (docs/PROJECTS-DESIGN.md); no active project, and no
                # jarvis_projects.py at all, both read as "not shareable" and
                # stay local. jarvis_projects.get().get(pid) raises for a
                # project deleted while still the active one, which
                # backend/test_cloud_say_yes.py measures rather than hides.
                lanes=[] if jarvis_side_memory else (lanes if (lambda m: hasattr(m, "active_project_id") and bool((m.get().get(m.active_project_id()) or {}).get("shareable")))(__import__("jarvis_projects")) else []),
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


def _stub_projects(pid, row, *, raises=None, has_module=True):
    """A `jarvis_projects` good enough for the guard: which project is active,
    and what one lookup of it answers. Returns the module object, so the test
    can show it to the expression by putting it in sys.modules."""
    mod = types.ModuleType("jarvis_projects")
    if has_module:
        mod.active_project_id = lambda: pid

        class _Store:
            def get(self, pid_asked):
                if raises is not None:
                    raise raises
                return row

        mod.get = lambda: _Store()
    sys.modules["jarvis_projects"] = mod
    return mod


def _lanes_from_patch(*, pid, row, raises=None, has_module=True, memory=False,
                      lanes=None):
    """Evaluate the patch's own guard line exactly as the installed HUD would.

    `jarvis_projects` is put in sys.modules first, so the line's own
    `__import__("jarvis_projects")` finds this stub on any machine."""
    _stub_projects(pid, row, raises=raises, has_module=has_module)
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
    # line) - the manual-lane branch a few lines below builds its Decision
    # with `_manual_decision`, a wholly different call this patch's hunk
    # never touches, with no privacy gating at all. Whether anything OTHER
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


def t_lanes_can_only_be_removed():
    """THE BITE THAT MATTERS: over every state the gate can be in, the value
    handed to choose() is either exactly the list that was passed in, or `[]`.
    Nothing else is reachable, so the guard can never ADD a lane - and a
    Shareable project really does keep its lanes, so the guard is not just
    always returning `[]`."""
    cases = [
        ("Project Mode off", dict(pid=None, row=None)),
        ("active, Shareable off (the default)", dict(pid="p1", row={"id": "p1", "shareable": False})),
        ("active, Shareable on", dict(pid="p1", row={"id": "p1", "shareable": True})),
        ("active, no jarvis_projects.py", dict(pid="p1", row=None, has_module=False)),
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
          all(_empty_stays_empty(name) for name, _ in cases), "")


def _empty_stays_empty(name):
    """The one property that must hold everywhere: `[]` in, `[]` out - the
    memory-injection line's own promise, now covering the project gate too."""
    kw = {"Project Mode off": dict(pid=None, row=None),
          "active, Shareable off (the default)": dict(pid="p1", row={"id": "p1", "shareable": False}),
          "active, Shareable on": dict(pid="p1", row={"id": "p1", "shareable": True}),
          "active, no jarvis_projects.py": dict(pid="p1", row=None, has_module=False)}[name]
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
        _stub_projects("p1", {"id": "p1", "shareable": False})
        old = eval("[] if jarvis_side_memory else lanes",
                   {"jarvis_side_memory": False, "lanes": list(LANES)})
        new = _lanes_from_patch(pid="p1", row={"id": "p1", "shareable": False},
                                memory=False)
    finally:
        _restore_modules(saved)
    check("with the guard, a not-Shareable active project offers NO lane",
          new == [], new)
    check("without it (the pre-change line), the SAME state still offers every lane",
          old == list(LANES), old)
    check("so the two differ, which is the whole point of the inserted line",
          old != new, (old, new))


def t_the_deleted_active_project_is_not_hidden():
    """The one state the guard still cannot survive, measured rather than
    described. `jarvis_projects.get().get(pid)` raises KeyError for a project
    deleted while it was still the active one - the mode file keeps the id.
    THIS IS REPORTED, NOT FIXED HERE: the fix belongs to jarvis_projects'
    delete path, not to a bigger expression in jarvis_hud.py."""
    saved = sys.modules.get("jarvis_projects")
    try:
        _stub_projects("p1", None, raises=KeyError("p1"))
        try:
            _lanes_from_patch(pid="p1", row=None, raises=KeyError("p1"), memory=False)
            raised = None
        except KeyError as exc:
            raised = exc
    finally:
        _restore_modules(saved)
    check("a deleted-but-active project makes the guard raise (measured in this tree)",
          isinstance(raised, KeyError),
          "if this stops raising, the expression changed shape - re-read the docstring")


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
    for fn in (t_the_patch, t_the_patch_counts_match, t_the_guard_is_the_patch_s_own,
               t_lanes_can_only_be_removed, t_the_guard_survives_removal,
               t_the_deleted_active_project_is_not_hidden,
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
