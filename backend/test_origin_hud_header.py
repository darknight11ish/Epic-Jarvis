"""test_origin_hud_header.py - with no Origin, only the HUD's own header gets in.

    python3 backend/test_origin_hud_header.py

CLAUDE.md's standing rule is *"Send `X-Jarvis-Client: hud` on every request."*
On the server that header is load-bearing in exactly one place: jarvis_hud.py's
`_origin_ok` accepts a request that carries no `Origin` **only** when it also
carries that header, because a custom header forces a CORS preflight and so
cannot be produced by a drive-by simple request from a page the owner merely
visited - which is what stops such a page approving Jarvis's own pending
commands.

The promises-vs-tests audit (2026-10-04, section 7 item 1 of
docs/HANDOFF-2026-10-04-test-suite-fixes.md) found this guarded by **nothing**:
every suite in this folder stubs `_origin_ok`, so replacing the last line of
the real function with `return True` broke no test anywhere. That is what this
suite is for, and why it lifts the REAL function out of the installed
jarvis_hud.py with ast instead of stubbing it - a stub here would prove
nothing at all.

What is proved, against the real `_origin_ok`:

  * an Origin this server actually answers on is allowed;
  * an Origin it does not answer on is refused (the Origin path is checked,
    not bypassed - DNS rebinding is the attack the docstring names);
  * a trailing slash on a served Origin still counts as served;
  * with NO Origin, the request is allowed only with `X-Jarvis-Client: hud`
    exactly - no header, an empty one, the wrong value, the right value with
    different case or stray space, are all refused.

WHICH jarvis_hud.py IS READ, AND WHY IT IS NEVER "NOTHING"

Three cases, in this order (backend/_base.py holds the rule in one place):

  1. `jarvis_hud.py` is in the folder this run reads - `JARVIS_BACKEND` when it
     is set (the owner's PC, or the throwaway folder the runner staged), and
     `backend/` otherwise (a dev container symlinks it there). That file is
     read, and this repository's copy of an older one is never substituted.
  2. No copy there, but the **published base** has one - which is CI and every
     clone. `jarvis-backend/jarvis_hud.py` is read: real code, derived from the
     owner's folder by `tools/gen_base_from_backend.py`, at the state the whole
     patch stack left when it was last re-taken. The suite prints which folder
     answered, so a green line never hides the difference.
  3. Neither file exists. The checks then SKIP, honestly, on their own SKIPPED
     list - and `run_suites.py`'s rule that a suite which passes nothing FAILS
     means even that run cannot read as a pass.

Until 2026-10-27 this suite had none of that: without the owner's file both
checks SKIPPED, and `skip()` appended them to PASSED - so it printed
`2 passed, 0 failed`, exit 0, in the required `backend` job, having read
nothing. The job's green said the HUD's Origin check had been re-proved when
`_origin_ok` had not been looked at. Both halves are fixed: `skip()` counts on
its own SKIPPED list (never a pass), and the base means a clone now runs all
14 checks for real instead of skipping 2:

    $ python3 backend/test_origin_hud_header.py
    14 passed, 0 skipped, 0 failed       (no owner install: the base was read)

WHAT THE BASE RUN DOES NOT PROVE, plainly: it proves `_origin_ok` in
`jarvis-backend/jarvis_hud.py` - the file this repository publishes and an
installer starts from - and NOT in a patch newer than the base's last re-take.
Run it on the owner's PC with `JARVIS_BACKEND` set for that half.
"""
from __future__ import annotations

import ast
import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, explain  # noqa: E402
import _base  # noqa: E402

#: WHICH jarvis_hud.py this run reads - see the docstring's three cases. The
#: published base is read only when there is no owner install and no copy in
#: `backend/`; `_base.folder` is the one place that rule lives.
BASE = _base.folder("jarvis_hud.py")
if BASE is not None:
    BACKEND = BASE
    _base.put_on_path(BASE)
    _base.say(BACKEND, "jarvis_hud.py")
HUD = BACKEND / "jarvis_hud.py"


def missing(*names):
    """Which of `names` are not in the folder this run really reads.

    `_where.missing` asks about `backend/`; after the fallback above the file
    may be in `jarvis-backend/` instead, and asking the wrong folder would
    report a file as absent while it is being read."""
    return _base.missing(BACKEND, *names)


def why_absent(name):
    """Why neither file exists, for the skip this suite can then honestly make."""
    return (f"{name} is in neither {HERE} nor {_base.BASE} "
            f"(JARVIS_BACKEND is {'set' if os.environ.get('JARVIS_BACKEND') else 'unset'}); "
            f"the published base is the fallback and it is not here either. {explain()}")

#: The one origin the fake configuration answers on. `_served_origins` is the
#: server's own answer to "what was I configured for"; it is replaced here with
#: a fixed set so the promise under test is `_origin_ok`'s decision, not the
#: config file's contents - the same reason the product's own docstring says
#: trust is derived from OUR configuration and never from a request header.
SERVED = "http://127.0.0.1:8765"
OTHER = "http://attacker.example"

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (FAILED if not cond else PASSED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    """A check this machine cannot make. NOT a pass: counted in its own list and
    printed on its own line, the shape backend/test_price_sources.py uses."""
    SKIPPED.append(name)
    print(f"SKIP  {name}  (not a pass)\n        {why}")


def real_origin_ok():
    """The REAL `_origin_ok` lifted out of the installed jarvis_hud.py.

    None when the file is not there or has no such function - the caller says
    so honestly rather than passing on an empty check."""
    if missing("jarvis_hud.py"):
        return None
    tree = ast.parse(HUD.read_text(encoding="utf-8"))
    body = [n for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "_origin_ok"]
    if not body:
        return None
    ns = {"os": os, "set": set, "_served_origins": lambda: {SERVED}}
    exec(compile(ast.Module(body=body, type_ignores=[]), "<_origin_ok>", "exec"), ns)
    return ns["_origin_ok"]


class _Handler:
    """As much of a BaseHTTPRequestHandler as `_origin_ok` touches."""

    def __init__(self, headers=None, peer="127.0.0.1"):
        self.headers = dict(headers or {})
        self.client_address = (peer, 54321)


def t_allowed_when_no_origin():
    fn = real_origin_ok()
    if fn is None:
        return skip("an Origin-less request is only allowed with the HUD header",
                    why_absent("jarvis_hud.py"))
    check("sanity: the real _origin_ok was lifted, not a stand-in",
          fn.__name__ == "_origin_ok" and fn.__code__.co_filename == "<_origin_ok>",
          fn)
    check("an Origin this server answers on is allowed",
          fn(_Handler({"Origin": SERVED})) is True)
    check("...and a trailing slash on it still counts",
          fn(_Handler({"Origin": SERVED + "/"})) is True)
    check("an Origin this server does NOT answer on is refused (rebinding)",
          fn(_Handler({"Origin": OTHER})) is False)
    check("no Origin, with X-Jarvis-Client: hud - the one accepted shape",
          fn(_Handler({"X-Jarvis-Client": "hud"})) is True)
    check("no Origin and no such header is refused",
          fn(_Handler({})) is False)
    check("no Origin and an empty header is refused",
          fn(_Handler({"X-Jarvis-Client": ""})) is False)
    check("no Origin and the wrong value is refused",
          fn(_Handler({"X-Jarvis-Client": "web"})) is False)
    check("...including a different case (the comparison must be exact)",
          fn(_Handler({"X-Jarvis-Client": "HUD"})) is False)
    check("...and a stray space around the value",
          fn(_Handler({"X-Jarvis-Client": " hud "})) is False)
    check("a served Origin is allowed even with a wrong client header",
          fn(_Handler({"Origin": SERVED, "X-Jarvis-Client": "web"})) is True)
    check("an unserved Origin is refused even WITH the hud header "
          "(the header never overrides a checked Origin)",
          fn(_Handler({"Origin": OTHER, "X-Jarvis-Client": "hud"})) is False)
    check("a peer address alone never buys anything",
          fn(_Handler({}, peer="127.0.0.1")) is False)


def t_the_fallback_is_not_a_blanket_yes():
    """The exact edit the audit says broke nothing: the last line replaced by
    `return True`. If `_origin_ok` ever becomes an unconditional yes, the
    third check of this suite is the one that goes red - it is kept separate so
    the reason is on the failing line."""
    fn = real_origin_ok()
    if fn is None:
        return skip("the Origin-less fallback is not an unconditional yes",
                    why_absent("jarvis_hud.py"))
    refused = [h for h in ({}, {"X-Jarvis-Client": ""}, {"X-Jarvis-Client": "web"},
                           {"X-Jarvis-Client": "HUD"})
               if fn(_Handler(h)) is not False]
    check("every Origin-less request without the exact header is refused",
          not refused, f"allowed anyway with {refused!r}")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if SKIPPED:
        print("skipped, and NOT passes: " + ", ".join(SKIPPED))
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
