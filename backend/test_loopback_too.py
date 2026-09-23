"""Binding for the phone must not unplug the desktop.

`JARVIS_HUD_BIND` moved the server's one socket off loopback instead of adding
one. The desktop's HUD window may only talk to 127.0.0.1/localhost (its page
CSP), so pairing the phone disconnected the desktop - found on the owner's
machine, where the phone answered over Meshnet while a browser on the same PC
was refused at localhost:4719. `loopback-too.patch` adds `_loopback_companion`,
which also serves 127.0.0.1 whenever the main bind is somewhere else.

This runs the real function against real sockets. It is lifted from the
installed jarvis_hud.py when there is one, and otherwise from the patch's own
`+` lines, so the logic is proven even where the backend is not installed.
127.0.0.2 stands in for the mesh address: it is loopback, but it is not
127.0.0.1, which is the only property the function looks at.

It also proves the wildcard check (`_binds_every_interface`, and the startup
refusal built on it) against the operating system: every spelling in the
desktop's `tests/bind-address-cases.json` "every_interface" list is bound on a
REAL socket here first, to show the OS really reads it as every interface -
"0", "0x0", "0.0" and "000.000.000.000" all do - and only then is the patch's
function asked about it. The desktop's own validator reads the same table.

    python3 test_loopback_too.py
"""
import ast
import contextlib
import io
import json
import socket
import sys
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, missing, explain
SRC = BACKEND / "jarvis_hud.py"
PATCH = HERE / "loopback-too.patch"
CASES = HERE.parent / "jarvis-desktop" / "tests" / "bind-address-cases.json"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _source():
    if not missing("jarvis_hud.py"):
        return SRC.read_text(encoding="utf-8"), f"the installed {SRC.name}"
    added = [line[1:] for line in PATCH.read_text(encoding="utf-8").splitlines()
             if line.startswith("+") and not line.startswith("+++")]
    return "\n".join(added), PATCH.name


LIFTED = ("_binds_every_interface", "_refuse_every_interface", "_loopback_companion")


def _lifted():
    source, where = _source()
    tree = ast.parse(source)
    body = []
    for name in LIFTED:
        found = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
        if len(found) != 1:
            raise AssertionError(f"expected one {name} in {where}, found {len(found)}")
        body.append(found[0])
    ns = {"ThreadingHTTPServer": ThreadingHTTPServer}
    exec(compile(ast.Module(body=body, type_ignores=[]), "<lifted>", "exec"), ns)
    return ns, where


def _companion_fn():
    ns, where = _lifted()
    return ns["_loopback_companion"], where


def _cases():
    return json.loads(CASES.read_text(encoding="utf-8"))


def _os_binds_every_interface(spelling):
    """What the operating system does with it: bind a real socket and look."""
    family = socket.AF_INET6 if ":" in spelling else socket.AF_INET
    try:
        s = socket.socket(family, socket.SOCK_STREAM)
    except OSError:
        return None  # no IPv6 on this machine; cannot ask
    try:
        s.bind((spelling, 0))
        return s.getsockname()[0] in ("0.0.0.0", "::")
    except OSError:
        return None
    finally:
        s.close()


class Echo(BaseHTTPRequestHandler):
    def do_GET(self):
        body = f"served on {self.server.server_address[0]}".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _get(host, port):
    with urllib.request.urlopen(f"http://{host}:{port}/", timeout=5) as r:
        return r.read().decode()


def _quiet(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = fn(*args)
    return result, out.getvalue()


def t_nothing_is_added_when_loopback_is_already_covered():
    fn, where = _companion_fn()
    print(f"(testing the function from {where})")
    for bind in ("127.0.0.1", "::1", "localhost", "0.0.0.0", "::", "", "0", "0x0", "000.000.000.000"):
        result, said = _quiet(fn, bind, 1, Echo)
        check(f"bind {bind!r} gets no second listener", result is None, said)


def t_every_wildcard_spelling_in_the_shared_table_is_caught():
    ns, where = _lifted()
    wild = ns["_binds_every_interface"]
    refuse = ns["_refuse_every_interface"]
    table = _cases()
    asked = 0
    for spelling in table["every_interface"]:
        real = _os_binds_every_interface(spelling)
        if real is None:
            check(f"SKIP - this machine cannot bind {spelling!r} to ask the OS", True)
            check(f"{where} still says {spelling!r} binds every interface", wild(spelling) is True)
            continue
        asked += 1
        # The table is only worth sharing if it is true: the OS decides.
        check(f"the OS really binds every interface for {spelling!r}", real is True)
        check(f"{where} says {spelling!r} binds every interface", wild(spelling) is True)
        try:
            _, said = _quiet(refuse, spelling)
            check(f"the backend refuses to start on {spelling!r}", False, said)
        except SystemExit as exc:
            check(f"the backend refuses to start on {spelling!r}, exit code 2", exc.code == 2)
    check("the OS was asked about the short spellings at all", asked >= 5, f"asked {asked}")
    # CONTROL: a refusal that fires on everything would stop every backend.
    for spelling in ("127.0.0.1", "localhost", "100.64.12.3", "100.64.012.3", "0177.0.0.1"):
        check(f"{spelling!r} is not every interface", wild(spelling) is False)
        result, said = _quiet(refuse, spelling)
        check(f"and the backend does not refuse {spelling!r}", result is None, said)


def t_a_mesh_bind_also_answers_on_loopback():
    fn, _ = _companion_fn()
    try:
        main = ThreadingHTTPServer(("127.0.0.2", 0), Echo)
    except OSError as exc:
        return check(f"SKIP - this machine cannot bind 127.0.0.2 ({exc})", True)
    port = main.server_address[1]
    import threading
    threading.Thread(target=main.serve_forever, daemon=True).start()
    companion, said = _quiet(fn, "127.0.0.2", port, Echo)
    try:
        check("a companion server was started", companion is not None, said)
        check("it is on 127.0.0.1, the same port as the main listener",
              companion is not None and companion.server_address == ("127.0.0.1", port),
              companion and companion.server_address)
        check("the main (mesh) address still answers", _get("127.0.0.2", port) == "served on 127.0.0.2")
        check("loopback now answers too, through the same handler",
              _get("127.0.0.1", port) == "served on 127.0.0.1")
        check("the banner says loopback is served", "127.0.0.1" in said and "as well" in said, said)
    finally:
        main.shutdown()
        if companion is not None:
            companion.shutdown()


def t_a_taken_loopback_port_warns_instead_of_crashing_the_boot():
    fn, _ = _companion_fn()
    squatter = socket.socket()
    squatter.bind(("127.0.0.1", 0))
    squatter.listen()
    port = squatter.getsockname()[1]
    try:
        result, said = _quiet(fn, "127.0.0.2", port, Echo)
        check("no exception, and no server, when 127.0.0.1 is taken", result is None, said)
        check("and it says the phone still works", "phone still works" in said, said)
    finally:
        squatter.close()


def t_main_calls_it_before_opening_the_main_socket():
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    mains = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main"]
    check("found main()", len(mains) == 1, f"found {len(mains)}")
    if len(mains) != 1:
        return
    body = ast.unparse(mains[0])
    refuse = body.find("_refuse_every_interface(bind)")
    call = body.find("_loopback_companion(bind, HUD_PORT, Handler)")
    server = body.find("ThreadingHTTPServer((bind, HUD_PORT), Handler)")
    check("main() calls _loopback_companion with the real bind, port and Handler", call != -1)
    check("before the main socket is opened", -1 < call < server, f"call at {call}, server at {server}")
    check("main() refuses a wildcard bind before anything listens",
          -1 < refuse < call, f"refusal at {refuse}, companion at {call}")


def t_the_patch_puts_the_refusal_before_anything_listens():
    # Proven from the patch text itself, so it holds where jarvis_hud.py is
    # not installed too: the main() hunk adds the refusal above the companion.
    text = PATCH.read_text(encoding="utf-8")
    main_hunk = text[text.rindex("@@ -"):]
    refuse = main_hunk.find("+    _refuse_every_interface(bind)")
    call = main_hunk.find("+    _loopback_companion(bind, HUD_PORT, Handler)")
    check("the main() hunk adds the refusal before the companion", -1 < refuse < call,
          f"refusal at {refuse}, companion at {call}")


if __name__ == "__main__":
    for fn in (t_nothing_is_added_when_loopback_is_already_covered,
               t_every_wildcard_spelling_in_the_shared_table_is_caught,
               t_the_patch_puts_the_refusal_before_anything_listens,
               t_a_mesh_bind_also_answers_on_loopback,
               t_a_taken_loopback_port_warns_instead_of_crashing_the_boot,
               t_main_calls_it_before_opening_the_main_socket):
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
