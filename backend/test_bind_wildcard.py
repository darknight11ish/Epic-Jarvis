"""No spelling of "every interface" gets past the backend's bind.

The desktop refused only the exact text "0.0.0.0" (and "::") for the phone
address, and `loopback-too.patch` decided "is this a wildcard?" from a list of
strings. But the operating system's address parser is far looser: "0", "0x0",
"0.0" and "000.000.000.000" all bind every network interface - the home or
cafe Wi-Fi as well as the private mesh. `bind-wildcard.patch` adds
`_binds_every_interface` (asks the resolver `socket.bind` itself uses) and
`_refuse_every_interface`, which `main()` calls before anything listens.

The cases come from `jarvis-desktop/tests/bind-address-cases.json`, which the
desktop's own Rust validator is tested against too. This test binds a REAL
socket to every "every_interface" entry first, so the table is proven against
the operating system rather than against itself, and only then asks the
patched functions about it.

The functions are lifted from the installed jarvis_hud.py when it has them,
otherwise from a rehearsal: `_skeleton` rebuilds the lines token-file and
loopback-too wrote and `git apply` puts this patch on top.

    python3 test_bind_wildcard.py
"""
import ast
import contextlib
import io
import json
import socket
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, missing, explain  # noqa: E402
import _skeleton  # noqa: E402

SRC = BACKEND / "jarvis_hud.py"
PATCH = HERE / "bind-wildcard.patch"
CASES = HERE.parent / "jarvis-desktop" / "tests" / "bind-address-cases.json"
LIFTED = ("_binds_every_interface", "_refuse_every_interface", "_loopback_companion")

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


_SOURCE = None


def _source():
    global _SOURCE
    if _SOURCE is None:
        if not missing("jarvis_hud.py") and "_binds_every_interface" in SRC.read_text(encoding="utf-8"):
            _SOURCE = (SRC.read_text(encoding="utf-8"), f"the installed {SRC.name}")
        else:
            ok, out = _skeleton.rehearse(PATCH.name, "token-file.patch", "loopback-too.patch")
            if ok is None:
                raise AssertionError(out)
            if not ok:
                raise AssertionError(f"{PATCH.name} does not apply over loopback-too: {out}")
            _SOURCE = (out, f"{PATCH.name} applied over loopback-too")
    return _SOURCE


def _function_text(source, name):
    """One top-level function's text. Cut out by hand rather than by parsing
    the whole file, because a rehearsal file is fragments and filler, not a
    module Python can parse."""
    lines = source.splitlines()
    starts = [i for i, l in enumerate(lines) if l.startswith(f"def {name}(")]
    if len(starts) != 1:
        return None, len(starts)
    out = [lines[starts[0]]]
    for line in lines[starts[0] + 1:]:
        if line and not line[0].isspace():
            break
        out.append(line)
    return "\n".join(out) + "\n", 1


def _lifted():
    source, where = _source()
    body = []
    for name in LIFTED:
        text, count = _function_text(source, name)
        if text is None:
            raise AssertionError(f"expected one {name} in {where}, found {count}")
        body.extend(ast.parse(text).body)
    ns = {"ThreadingHTTPServer": ThreadingHTTPServer}
    exec(compile(ast.Module(body=body, type_ignores=[]), "<lifted>", "exec"), ns)
    return ns, where


def _cases():
    return json.loads(CASES.read_text(encoding="utf-8"))


def _os_binds_every_interface(spelling):
    """What the operating system does with it: bind a real socket and look.
    None when this machine cannot answer (no IPv6, say)."""
    family = socket.AF_INET6 if ":" in spelling else socket.AF_INET
    try:
        s = socket.socket(family, socket.SOCK_STREAM)
    except OSError:
        return None
    try:
        s.bind((spelling, 0))
        return s.getsockname()[0] in ("0.0.0.0", "::")
    except OSError:
        return None
    finally:
        s.close()


def _quiet(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = fn(*args)
    return result, out.getvalue()


class Echo(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass


def t_the_patch_applies_over_loopback_too():
    ok, out = _skeleton.rehearse(PATCH.name, "token-file.patch", "loopback-too.patch")
    if ok is None:
        return check("SKIP - " + out, True)
    check(f"{PATCH.name} applies (and reverses) over what loopback-too wrote", ok is True, out)
    if ok:
        # The rehearsal file repeats context lines across hunks, so read the
        # order from the call site onwards, not from the top.
        refuse = out.find("\n    _refuse_every_interface(bind)\n")
        call = out.find("_loopback_companion(bind, HUD_PORT, Handler)", max(refuse, 0))
        server = out.find("ThreadingHTTPServer((bind, HUD_PORT), Handler)", max(call, 0))
        check("main() refuses before the companion and before the main socket",
              -1 < refuse < call < server, f"refuse {refuse}, companion {call}, server {server}")
        check("the old string-list test is gone",
              '"localhost", "0.0.0.0", "::", ""' not in out)
    ps1 = (HERE.parent / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    check("apply-patches.ps1 applies it, after loopback-too.patch",
          PATCH.name in names and names.index(PATCH.name) > names.index("loopback-too.patch"))


def t_the_table_is_true_and_every_wildcard_is_refused():
    ns, where = _lifted()
    print(f"(testing the functions from {where})")
    wild, refuse = ns["_binds_every_interface"], ns["_refuse_every_interface"]
    asked = 0
    for spelling in _cases()["every_interface"]:
        real = _os_binds_every_interface(spelling)
        if real is None:
            check(f"SKIP - this machine cannot bind {spelling!r} to ask the OS", True)
        else:
            asked += 1
            check(f"the OS really binds every interface for {spelling!r}", real is True)
        check(f"_binds_every_interface({spelling!r}) is True", wild(spelling) is True)
        try:
            _, said = _quiet(refuse, spelling)
            check(f"the backend refuses to start on {spelling!r}", False, said)
        except SystemExit as exc:
            check(f"the backend refuses to start on {spelling!r}, exit code 2", exc.code == 2)
    check("the OS was asked about at least the IPv4 spellings", asked >= 8, f"asked {asked}")


def t_ordinary_addresses_still_start():
    # CONTROL: a refusal that fires on everything would stop every backend.
    ns, _ = _lifted()
    wild, refuse = ns["_binds_every_interface"], ns["_refuse_every_interface"]
    for spelling in ("127.0.0.1", "localhost", "::1", "100.64.12.3", "100.64.012.3", "0177.0.0.1",
                     "no-such-host.invalid"):
        check(f"{spelling!r} is not every interface", wild(spelling) is False)
        result, said = _quiet(refuse, spelling)
        check(f"and the backend does not refuse {spelling!r}", result is None, said)


def t_no_second_listener_for_any_wildcard_spelling():
    # The companion used to test the same string list; with "0" it would have
    # taken 127.0.0.1 first and then collided with the main 0.0.0.0 socket.
    ns, _ = _lifted()
    fn = ns["_loopback_companion"]
    for bind in _cases()["every_interface"] + ["", "127.0.0.1", "localhost"]:
        result, said = _quiet(fn, bind, 1, Echo)
        check(f"bind {bind!r} gets no second listener", result is None, said)


def t_the_real_file():
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    src = SRC.read_text(encoding="utf-8")
    if "_refuse_every_interface" not in src:
        return check("bind-wildcard.patch is applied to jarvis_hud.py", False,
                     "run scripts/apply-patches.ps1 first")
    mains = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "main"]
    check("found main()", len(mains) == 1, f"found {len(mains)}")
    if len(mains) == 1:
        body = ast.unparse(mains[0])
        refuse = body.find("_refuse_every_interface(bind)")
        server = body.find("ThreadingHTTPServer((bind, HUD_PORT), Handler)")
        check("main() refuses a wildcard before the main socket opens", -1 < refuse < server,
              f"refusal at {refuse}, server at {server}")


if __name__ == "__main__":
    for fn in (t_the_patch_applies_over_loopback_too,
               t_the_table_is_true_and_every_wildcard_is_refused,
               t_ordinary_addresses_still_start,
               t_no_second_listener_for_any_wildcard_spelling,
               t_the_real_file):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
