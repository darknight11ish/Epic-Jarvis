"""The HUD's port is taken EXCLUSIVELY - tested on the patch's own code (N4).

    python3 backend/test_hud_server.py

WHY THIS SUITE EXISTS. SECPRIV audit 2026-10-18 (N4): the live
`jarvis_hud.py` constructs `ThreadingHTTPServer` with no `allow_reuse_address`
and no `SO_EXCLUSIVEADDRUSE`, and CPython's `http.server.HTTPServer` defaults
`allow_reuse_address = 1`. On Windows SO_REUSEADDR lets a second process bind
the same port and race/steal connections - the token a phone sends included.
`hud-exclusive-bind.patch` replaces that construction with a local
`_HudServer(ThreadingHTTPServer)` that sets `allow_reuse_address = False` (and
SO_EXCLUSIVEADDRUSE on Windows).

The class is lifted out of the patch's own added lines, so this runs on a clean
checkout with no owner PC and no live HUD. The duplicate-bind check uses a real
local socket on an ephemeral port. What this cannot prove: that the owner's
installed file has the patch applied - only apply-patches.ps1 there can do
that. The loopback companion is deliberately NOT changed by this patch (its
line belongs to `_loopback_companion`'s own patch context); the main :4719
listener is the one a second process must not share.
"""
from __future__ import annotations

import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATCH = HERE / "hud-exclusive-bind.patch"
PS1 = HERE.parent / "scripts" / "apply-patches.ps1"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (FAILED if not cond else PASSED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Quiet(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass


def _patch_text() -> str:
    return PATCH.read_text(encoding="utf-8") if PATCH.is_file() else ""


def _class_source() -> str:
    """The indented `class _HudServer(...)` block, dedented by four spaces."""
    out, inside = [], False
    for line in _patch_text().splitlines():
        if line.startswith("+    class _HudServer("):
            inside = True
            out.append(line[1:])
            continue
        if inside:
            # Class body lines are added with eight spaces; the `httpd = ...`
            # line that follows is four, and must not be exec'd as module code.
            if line.startswith("+        "):
                out.append(line[1:])
                continue
            if line == "+":
                out.append("")
                continue
            break
    if not out:
        return ""
    return "\n".join(line[4:] if line.startswith("    ") else line
                     for line in out) + "\n"


def _server_class():
    source = _class_source()
    assert source, "no _HudServer class in the N4 patch"
    import os
    import socket
    namespace = {"ThreadingHTTPServer": ThreadingHTTPServer, "os": os,
                 "socket": socket}
    exec(compile(source, "<patch>", "exec"), namespace)
    return namespace["_HudServer"]


def t_the_patch_takes_the_port_exclusively():
    text = _patch_text()
    check("the exclusive-bind patch ships", PATCH.is_file(), PATCH)
    check("... it refuses to share the port", "allow_reuse_address = False" in text)
    check("... and asks Windows for SO_EXCLUSIVEADDRUSE",
          "SO_EXCLUSIVEADDRUSE" in text)
    check("... the main listener uses the class",
          "_HudServer((bind, HUD_PORT), Handler)" in text
          and "-    httpd = ThreadingHTTPServer((bind, HUD_PORT), Handler)" in text)
    ps1 = PS1.read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    block = ps1[start:ps1.index(chr(10) + ")", start)]
    names = [line.strip().strip("'") for line in block.splitlines()
             if line.strip().startswith("'")]
    check("apply-patches.ps1 applies it before plugin-loader.patch",
          "hud-exclusive-bind.patch" in names
          and names.index("hud-exclusive-bind.patch") < names.index("plugin-loader.patch"))


def t_a_second_listener_cannot_take_the_same_port():
    server_class = _server_class()
    first = server_class(("127.0.0.1", 0), Quiet)
    port = first.server_address[1]
    second = None
    try:
        try:
            second = server_class(("127.0.0.1", port), Quiet)
        except OSError:
            refused = True
        else:
            refused = False
        check(f"a second listener on 127.0.0.1:{port} is REFUSED", refused)
    finally:
        first.server_close()
        if second is not None:
            second.server_close()
    third = None
    try:
        try:
            third = server_class(("127.0.0.1", port), Quiet)
        except OSError:
            taken = True
        else:
            taken = False
        check("... but after it closes, the port is free again", not taken)
    finally:
        if third is not None:
            third.server_close()


if __name__ == "__main__":
    for fn in (t_the_patch_takes_the_port_exclusively,
               t_a_second_listener_cannot_take_the_same_port):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, 0 skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
