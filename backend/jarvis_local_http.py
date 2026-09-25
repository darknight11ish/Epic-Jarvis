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

PLAIN http:// OUTSIDE THE OWNER'S OWN NETWORKS (security audit L7, 2026-09-25)
`plain_http_problem()` below is for the services that are NOT on this PC
and take a password or token: the calendar (jarvis_calendar) and Home
Assistant (jarvis_home). Over plain `http://` that password or token - and
everything read back - crosses the network unencrypted. On the open
internet anything along the way can read it, so `http://` there is refused.

The first version refused plain `http://` to anything but this PC and
Tailscale, which also refused Home Assistant's own default address
(`http://homeassistant.local:8123`). The owner decided on 2026-09-25 that
plain `http://` is allowed inside their own networks, and refused only to
the open internet. "Own networks" is, exactly:

  - this PC: `localhost`, 127.0.0.0/8, ::1;
  - the home network: the private IPv4 ranges 10.0.0.0/8, 172.16.0.0/12
    and 192.168.0.0/16, IPv6 unique-local addresses (fc00::/7), a name
    ending in `.local`, `.lan` or `.home.arpa`, and a single-word name with
    no dot in it (`homeassistant`, `nas`), which is a home-network name
    (the home router answers those, not the internet);
  - Tailscale: 100.64.0.0/10, fd7a:115c:a1e0::/48, a `*.ts.net` name;
  - NordVPN Meshnet: the same 100.64.0.0/10 block, and a `*.nord` name
    (the Nord Name; the phone's network_security_config.xml allows the
    same two suffixes).

Nothing is looked up to decide: no DNS, no network call at all. A name is
judged by its spelling. Link-local addresses (169.254.x.x, fe80::) are
NOT on the list - they are not what a home router hands out, and the
first version did not allow them either. A number written oddly
(`3232235777`, `0xc0a80101`), which the operating system would still dial
as an address, is judged as that address, so it cannot pass as a
single-word name. Everything else - a public address, a name with any
other ending (`ha.example.com`, `mydomain.duckdns.org`) - is refused.
There is no switch to allow it anyway.

Standard library only. Opens nothing on import.
"""
from __future__ import annotations

import ipaddress
import re
import socket
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


#: This PC, the home network, and the mesh networks - see "PLAIN http://"
#: above. Link-local (169.254.0.0/16, fe80::/10) is deliberately absent.
_OWN_NETS = (
    ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("::1/128"),   # this PC
    ipaddress.ip_network("10.0.0.0/8"),                                      # home network
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),                                        # IPv6 unique-local
    ipaddress.ip_network("100.64.0.0/10"),              # Tailscale and NordVPN Meshnet
    ipaddress.ip_network("fd7a:115c:a1e0::/48"),        # Tailscale IPv6 (inside fc00::/7 too)
)

#: Name endings that only the owner's own networks answer.
_OWN_SUFFIXES = (".local", ".lan", ".home.arpa",     # home network
                 ".ts.net",                            # Tailscale MagicDNS
                 ".nord")                              # NordVPN Meshnet Nord Name


#: A plain host name: words of letters, digits, "-" or "_", joined by dots.
_NAME_RE = re.compile(r"^[\w-]+(\.[\w-]+)*$")


def _dialled_host(url: str) -> str:
    """The host urllib will actually connect to for `url`.

    `urlsplit` and urllib's own connection code read a malformed address
    differently: for `http://fe80::1:8123/`, urlsplit's hostname is `fe80`
    (a single word, which would pass as a home-network name) while urllib
    dials fe80::1. So the check judges both, and both must pass. This
    mirrors urllib.request.Request's host and http.client's port split;
    it parses only, and looks nothing up."""
    try:
        host = urllib.request.Request(url).host or ""
    except ValueError:
        return ""
    colon, bracket = host.rfind(":"), host.rfind("]")
    if colon > bracket:
        host = host[:colon]
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host


def opener_for(url: str, *handlers) -> urllib.request.OpenerDirector:
    """The opener for a request to `url` that carries a password or token.

    Plain http:// never goes through a proxy: `plain_http_problem` allowed it
    because it stays inside the owner's own networks, and a proxy is another
    machine that would read the password as plain text (the same reasoning
    as CONN-1 above). https:// keeps urllib's usual behaviour, where a proxy
    only ever sees scrambled traffic."""
    if str(url or "").strip().lower().startswith("http://"):
        return opener(*handlers)
    return urllib.request.build_opener(*handlers)


def _as_address(host: str):
    """The address `host` denotes, or None when it is a name.

    Beyond the usual spellings, this catches the old numeric forms the
    operating system still dials as an address (`3232235777`, `0xc0a80101`,
    `10.1`): judged as a name they would have no dot and pass as a
    single-word home name. socket.inet_aton only parses; it looks nothing
    up."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            ip = ipaddress.IPv4Address(socket.inet_aton(host))
        except (OSError, ValueError):
            return None
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip


def _own_network(host: str) -> bool:
    """Is `host` this PC or on one of the owner's own networks (home
    network, Tailscale, NordVPN Meshnet)? Judged by spelling alone."""
    host = (host or "").strip().lower().rstrip(".")
    if not host:
        return False
    ip = _as_address(host)
    if ip is not None:
        return any(ip in net for net in _OWN_NETS if net.version == ip.version)
    if not _NAME_RE.match(host):
        return False      # not a plain host name (an odd IPv6 form, an "@", a space...)
    if host == "localhost" or "." not in host:
        return True       # this PC, or a single-word name on the home network
    return host.endswith(_OWN_SUFFIXES)


def plain_http_problem(url: str, env_name: str, secret: str) -> str:
    """"" when `url` may carry `secret` (e.g. "the calendar password"), else
    the plain sentence saying why not. Only plain http:// outside the
    owner's own networks is refused - see "PLAIN http://" above."""
    url = str(url or "").strip()
    try:
        parts = urllib.parse.urlsplit(url)
        scheme, host = parts.scheme.lower(), parts.hostname or ""
    except ValueError:
        # An address urlsplit cannot read (a stray "[", say). It used to be
        # let through; a plain http:// one is now refused, since nothing
        # here can tell where it would go.
        scheme, host = url[:7].lower().rstrip(":/"), ""
    if scheme != "http":
        return ""
    dialled = _dialled_host(url)
    if _own_network(host) and _own_network(dialled):
        return ""
    # Name the address urllib would have dialled, when that is the one that
    # failed - but only a clean host or address, never text that could hold
    # a user name or password written into the URL ("http://me:pw@...").
    if (dialled and not _own_network(dialled)
            and (_as_address(dialled) is not None or _NAME_RE.match(dialled))):
        host = dialled
    return (f"{env_name} starts with http://, not https://, and {host or 'that address'} "
            f"is not this PC or one of your own networks, so {secret} and everything "
            f"read back would cross the internet unencrypted, where anyone along the way "
            f"could read them. Nothing was sent. Plain http:// is allowed only to this PC, "
            f"your home network (an address like 192.168.x.x or 10.x.x.x, or a name "
            f"ending in .local), Tailscale or NordVPN Meshnet. Use the https:// address "
            f"instead, or the machine's home-network, Tailscale or Meshnet address")
