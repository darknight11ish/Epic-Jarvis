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

    python3 test_loopback_too.py
"""
import ast
import contextlib
import io
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


def _companion_fn():
    source, where = _source()
    found = [n for n in ast.walk(ast.parse(source))
             if isinstance(n, ast.FunctionDef) and n.name == "_loopback_companion"]
    if len(found) != 1:
        raise AssertionError(f"expected one _loopback_companion in {where}, found {len(found)}")
    ns = {"ThreadingHTTPServer": ThreadingHTTPServer}
    exec(compile(ast.Module(body=[found[0]], type_ignores=[]), "<lifted>", "exec"), ns)
    return ns["_loopback_companion"], where


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
    for bind in ("127.0.0.1", "::1", "localhost", "0.0.0.0", "::", ""):
        result, said = _quiet(fn, bind, 1, Echo)
        check(f"bind {bind!r} gets no second listener", result is None, said)


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
    call = body.find("_loopback_companion(bind, HUD_PORT, Handler)")
    server = body.find("ThreadingHTTPServer((bind, HUD_PORT), Handler)")
    check("main() calls _loopback_companion with the real bind, port and Handler", call != -1)
    check("before the main socket is opened", -1 < call < server, f"call at {call}, server at {server}")


if __name__ == "__main__":
    for fn in (t_nothing_is_added_when_loopback_is_already_covered,
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
