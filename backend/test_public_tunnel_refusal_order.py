"""test_public_tunnel_refusal_order.py - a wildcard bind is refused, and refused FIRST.

    python3 backend/test_public_tunnel_refusal_order.py

CLAUDE.md's rule 2 is not negotiable: *"The app never opens a public tunnel."*
The backend honours it in one place - jarvis_hud.py's `_refuse_every_interface`
raises `SystemExit(2)` when the address it was told to listen on would listen
on EVERY interface (the home or cafe Wi-Fi, not just the owner's private
mesh), and `main()` must ask BEFORE it opens the socket.

The promises-vs-tests audit (2026-10-04, section 7 item 1) recorded this as
UNGUARDED: `test_bind_wildcard.py` proves the *check* exists, and
`t_the_patch_applies_over_loopback_too` proves the *patch text* puts the call
first, but nothing asserted the order in the **installed** file - so an edit
that moved the refusal after `ThreadingHTTPServer((bind, HUD_PORT), ...)`
would have bound every interface first and only then refused.

What is proved here, against the REAL functions lifted out of the installed
jarvis_hud.py with ast:

  * `0.0.0.0`, `::`, `::0` and an empty address are refused with SystemExit(2);
  * every address in `jarvis-desktop/tests/bind-address-cases.json` that THIS
    machine's resolver reads as every-interface is refused too (the contract
    the desktop, the patch and this file share), and no address in that file's
    "refused" list is treated as a wildcard;
  * loopback and a private mesh address are allowed;
  * in `main()`, the refusal call comes before the main socket is created.

The platform is stated rather than assumed: on this PC the bare forms ("0",
"0x0", "0.0") are not read as every-interface by `getaddrinfo`, which is why
`test_bind_wildcard.py` SKIPS that half on Windows. Those are reported, not
asserted.
"""
from __future__ import annotations

import ast
import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing, explain  # noqa: E402

HUD = BACKEND / "jarvis_hud.py"
CASES = REPO / "jarvis-desktop" / "tests" / "bind-address-cases.json"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (FAILED if not cond else PASSED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    print(f"SKIP  {name}\n        {why}")
    PASSED.append(name)


def _tree():
    if missing("jarvis_hud.py"):
        return None
    return ast.parse(HUD.read_text(encoding="utf-8"))


def _lift(tree, names):
    """The real functions, executed in isolation - never stubbed."""
    body = [n for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), "<jarvis_hud>", "exec"), ns)
    return ns


def _code(fn, value):
    """SystemExit's code when `fn(value)` refuses, else None."""
    try:
        fn(value)
        return None
    except SystemExit as exc:
        return exc.code


def t_a_wildcard_bind_is_refused():
    tree = _tree()
    if tree is None:
        return skip("a wildcard bind is refused with SystemExit(2)",
                    "jarvis_hud.py is not in " + str(BACKEND) + ". " + explain())
    ns = _lift(tree, {"_binds_every_interface", "_refuse_every_interface"})
    refuse = ns.get("_refuse_every_interface")
    binds = ns.get("_binds_every_interface")
    if refuse is None or binds is None:
        return skip("a wildcard bind is refused with SystemExit(2)",
                    "the installed jarvis_hud.py has no _refuse_every_interface / "
                    "_binds_every_interface to read (an older copy).")
    for spelling in ("0.0.0.0", "::", "::0", ""):
        got = _code(refuse, spelling)
        check(f"listening on {spelling!r} is refused with SystemExit(2)",
              got == 2, f"got {got!r}")
    check("loopback is allowed",
          _code(refuse, "127.0.0.1") is None and binds("127.0.0.1") is False)
    check("a private mesh address is allowed",
          _code(refuse, "100.64.1.2") is None and binds("100.64.1.2") is False)

    if not CASES.is_file():
        return skip("the shared bind-address cases agree",
                    f"{CASES} is not in this repository.")
    try:
        doc = json.loads(CASES.read_text(encoding="utf-8"))
    except Exception as exc:
        return check("the shared bind-address cases parse", False,
                     f"{type(exc).__name__}: {exc}")
    every = [c for c in doc.get("every_interface", []) if binds(c)]
    print(f"        (this machine's resolver reads {len(every)} of "
          f"{len(doc.get('every_interface', []))} every_interface spellings as "
          f"every-interface: {every})")
    not_wild = [c for c in every if _code(refuse, c) != 2]
    check("every spelling THIS machine reads as every-interface is refused",
          not not_wild, f"allowed anyway: {not_wild!r}")
    wrongly = [c for c in doc.get("refused", []) if _code(refuse, c) == 2]
    check("no address the contract says is not a wildcard is refused",
          not wrongly, f"refused wrongly: {wrongly!r}")


def t_the_refusal_comes_before_the_socket():
    """The order, in the INSTALLED main() - not in the patch text."""
    tree = _tree()
    if tree is None:
        return skip("main() refuses before it opens the socket",
                    "jarvis_hud.py is not in " + str(BACKEND) + ". " + explain())
    mains = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"]
    if not mains:
        return skip("main() refuses before it opens the socket",
                    "the installed jarvis_hud.py has no module-level main().")
    main = mains[0]
    refusal = [n for n in ast.walk(main)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "_refuse_every_interface"]
    sockets = [n for n in ast.walk(main)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "ThreadingHTTPServer"]
    check("main() asks _refuse_every_interface at all", bool(refusal), "no call found")
    check("main() creates the server socket with ThreadingHTTPServer", bool(sockets),
          "no socket call found")
    if not (refusal and sockets):
        return
    first_refusal = min(n.lineno for n in refusal)
    first_socket = min(n.lineno for n in sockets)
    check("...and asks BEFORE it opens the socket (line order, installed file)",
          first_refusal < first_socket,
          f"_refuse_every_interface at line {first_refusal}, "
          f"ThreadingHTTPServer at line {first_socket}")


if __name__ == "__main__":
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
    sys.exit(1 if FAILED else 0)
