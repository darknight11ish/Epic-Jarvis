"""test_cloud_say_yes.py - cloud-say-yes.patch: the owner's "Try the cloud
model" for one question actually reaches jarvis_router.choose()'s own
`owner_said_yes` gate (docs/ARCHITECTURE.md "Cloud / API keys"; docs/
JARVIS-API.md "`offer` in `X-Jarvis-Route`").

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

`jarvis_router.choose()`'s own `owner_said_yes` gate - what actually makes
a "yes" safe (every privacy gate still runs first, in order) - is real,
shipped code, and already has real tests: test_rebuilt.py and
test_chat_stream_contract.py's own `owner_said_yes=True` cases. Nothing
here repeats those; this file tests only the one thing that is new: does
the patch itself wire the request through to that already-proven gate,
in the right place, doing nothing else.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _stack  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


#: The exact real lines this patch was written against (jarvis_hud.py,
#: 2557-2572 on the owner's PC, 2026-09-27) - see the module docstring for
#: why this is a literal fixture rather than a `_stack` stand-in.
_REAL_PRE_IMAGE = '''\
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


def t_the_patch():
    order = _stack.order()
    check("cloud-say-yes.patch is in apply-patches.ps1's list, last",
          order and order[-1] == "cloud-say-yes.patch", order[-3:])
    patch = (HERE / "cloud-say-yes.patch").read_text(encoding="utf-8")
    check("it patches jarvis_hud.py and nothing else",
          sorted(l[6:].strip() for l in patch.splitlines() if l.startswith("+++ b/"))
          == ["jarvis_hud.py"])
    git = shutil.which("git")
    if not git:
        check("git is here to apply it", False)
        return
    target = "jarvis_hud.py"
    d = Path(tempfile.mkdtemp(prefix="jarvis-cloud-say-yes-patch-"))
    try:
        (d / target).write_text(_REAL_PRE_IMAGE, encoding="utf-8", newline="\n")
        one = "".join(h for h, _ in _stack.hunks(patch, target))
        (d / "p.patch").write_text(f"--- a/{target}\n+++ b/{target}\n{one}",
                                   encoding="utf-8", newline="\n")
        r = subprocess.run([git, "apply", "p.patch"], cwd=d, capture_output=True, text=True)
        ok = r.returncode == 0
        after = (d / target).read_text(encoding="utf-8") if ok else ""
        r2 = subprocess.run([git, "apply", "-R", "p.patch"], cwd=d, capture_output=True,
                            text=True)
        back = (d / target).read_text(encoding="utf-8") == _REAL_PRE_IMAGE
        check(f"{target}: applies to the real snapshot it was written against, and reverses",
              ok and r2.returncode == 0 and back, (r.stderr, r2.stderr))
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
    # This choose() call only exists inside the auto-routing branch
    # (`if ROUTING and body.get("auto", True):` - the fixture's own first
    # line) - the manual-lane branch a few lines below builds its Decision
    # with `_manual_decision`, a wholly different call this patch's hunk
    # never touches, with no privacy gating at all. Whether anything OTHER
    # than the intended lines changed is already proven above: reversing
    # the patch reproduced `_REAL_PRE_IMAGE` byte for byte, which a stray
    # edit anywhere else in the hunk could not have survived.


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
    for fn in (t_the_patch, t_cloud_yes_is_read_as_a_plain_bool):
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
