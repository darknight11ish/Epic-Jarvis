"""jarvis_local_http.py - HTTP to this PC's own services, never through a proxy.

WHAT WENT WRONG (bug audit 3, CONN-1)
Python's `urllib.request.urlopen`, and any opener made with `build_opener()`
and no ProxyHandler of its own, sends every request through whatever proxy
the machine is set up with: the `HTTP_PROXY` / `HTTPS_PROXY` variables, and
on Windows the system proxy in Internet Options (read from the registry).
Windows' "Bypass proxy server for local addresses" (`<local>`) covers bare
host names with no dot in them, NOT `127.0.0.1`, so it does not help.

So the "loopback only" calls were not: a request to Joplin on
`http://127.0.0.1:41184/...?token=<the Joplin token>` went, whole, to the
proxy. The audit proved it with a fake proxy, which received the token.
Rule 3 (CLAUDE.md) says a key is "sent only to the one service it
authenticates against"; a proxy is not that service. Rule 1 says anything
touching files or memory stays on this machine; a corporate or VPN proxy is
another machine.

THE FIX
Every call to a service on this PC (Ollama, the second card's Ollama,
Joplin, the Obsidian plugin) goes through `opener()` below, which is
`build_opener(ProxyHandler({}))`: an EMPTY proxy table, so urllib connects
straight to the address in the URL and never asks the environment or the
registry for a proxy. `jarvis_big_model.py` already did exactly this for
colibri (its `_OPENER`); this is the same thing, shared.

Callers that refuse redirects (jarvis_notes and jarvis_note_capture, whose
`_RefuseRedirect` stops a credential following a 30x to another host) pass
their handler in, and keep it: `opener(_RefuseRedirect)`.

Standard library only. Opens nothing on import.
"""
from __future__ import annotations

import urllib.request


def opener(*handlers) -> urllib.request.OpenerDirector:
    """An opener that never uses a proxy, plus any extra `handlers` (for
    example a module's own redirect refusal).

    Built per call on purpose: `build_opener` is cheap, and a fresh one means
    a test that swaps `urllib.request.build_opener` sees every call."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), *handlers)


def urlopen(req, timeout: float, *handlers):
    """`urllib.request.urlopen(req, timeout=timeout)`, minus the proxy."""
    return opener(*handlers).open(req, timeout=timeout)
