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

PLAIN http:// TO ANOTHER MACHINE (security audit L7, 2026-09-25)
`plain_http_problem()` below is for the services that are NOT on this PC
and take a password or token: the calendar (jarvis_calendar) and Home
Assistant (jarvis_home). Over plain `http://` that password or token - and
everything read back - crosses the network unencrypted, where anything on
the same network can read it. So `http://` is refused for them unless the
address is this PC (loopback) or a Tailscale address (100.64.0.0/10,
fd7a:115c:a1e0::/48, or a `*.ts.net` name), whose traffic Tailscale
encrypts end to end. There is no switch to allow it anyway.

Standard library only. Opens nothing on import.
"""
from __future__ import annotations

import ipaddress
import urllib.parse
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


_TAILSCALE_NETS = (ipaddress.ip_network("100.64.0.0/10"),
                   ipaddress.ip_network("fd7a:115c:a1e0::/48"))


def _encrypted_route(host: str) -> bool:
    """Is `host` this PC, or a Tailscale address (encrypted by Tailscale)?"""
    host = (host or "").lower().rstrip(".")
    if host == "localhost" or host.endswith(".ts.net"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or any(ip in net for net in _TAILSCALE_NETS)


def plain_http_problem(url: str, env_name: str, secret: str) -> str:
    """"" when `url` may carry `secret` (e.g. "the calendar password"), else
    the plain sentence saying why not. Only plain http:// to another machine
    is refused - see "PLAIN http://" above."""
    try:
        parts = urllib.parse.urlsplit(str(url or "").strip())
        host = parts.hostname or ""
    except ValueError:
        return ""
    if parts.scheme.lower() != "http" or _encrypted_route(host):
        return ""
    return (f"{env_name} starts with http://, not https://, and {host} is another "
            f"machine, so {secret} and everything read back would cross the network "
            f"unencrypted, where anything on it could read them. Nothing was sent. Use "
            f"the https:// address instead, or the machine's Tailscale address")
