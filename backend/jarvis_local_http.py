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

import http.client
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


# --------------------------------------------------------------------------
# FETCHING AN ADDRESS THE OWNER TYPED, MEANT TO BE ON THE OPEN INTERNET
# (a news feed - jarvis_news.py; "tell me when this page changes" -
# jarvis_tellme.py's "page" source. Both 2026-09-27, CLAUDE.md: "News
# headlines and 'tell me when this page changes': yes, the safe version -
# one card per address the owner adds, read-only, never follows links
# elsewhere, never acts on what it reads".)
#
# `plain_http_problem` above answers "is this one of the owner's OWN
# networks?" for a password Jarvis sends TO a service the owner set up
# (Home Assistant, the calendar). This answers the opposite question, for
# an address the owner typed expecting it to be OUT on the internet: "does
# this address actually lead to this PC or the home network?" A feed or a
# page-to-watch is not a password, so plain http:// is not refused here -
# what is refused is the address turning out to be somewhere it should
# never have been able to reach at all.
#
# WHY THIS NEEDS A REAL DNS LOOKUP, NOT SPELLING
# `_own_network` above judges "is this the owner's own network" by
# spelling alone, on purpose (a password must never trigger a lookup that
# could itself leak it). Here it is the other way round: the owner typed a
# public-looking name, and what matters is what it REALLY resolves to right
# now - a name gives no protection at all against pointing at
# 127.0.0.1 or a 192.168.x.x address on the home network (a classic SSRF:
# "newsfeed.example.com" answering 10.0.0.5 today, or an attacker-controlled
# DNS record later). So `_resolved_addresses` below calls the real resolver.
#
# WHY THIS IS CALLED AGAIN ON EVERY FETCH, NOT ONLY WHEN THE ADDRESS IS ADDED
# DNS is not a fact fixed at setup time (DNS rebinding): the same name can
# answer with a public address when the owner's one approval card is shown,
# then with a home-network address by the time a later look actually
# fetches it. `jarvis_tellme.py` calls this again immediately before every
# GET, not only when the watch is created.
#
# That alone was NOT enough (security/privacy audit, 2026-09-27): urllib
# then looked the name up a second time to connect, so an answer that
# changed within that moment still got through. The fetch itself now goes
# through `public_urlopen` (below), whose connection checks the very
# addresses it connects to. This function stays as the early check that
# gives the plain sentence (before a card, and before each look).

#: Ranges refused for an address meant to be on the open internet - the
#: reverse of _OWN_NETS's job above: here _OWN_NETS's ranges (this PC, the
#: home network, Tailscale, NordVPN Meshnet) are exactly what must be
#: refused, plus link-local and "any address" ranges that _OWN_NETS leaves
#: out (on purpose, for the opposite reason: a home router never hands out
#: 169.254.x.x, so `plain_http_problem` need not treat it as "safely home").
#
# The last two groups were added 2026-10-08, reading OpenMuse's
# `apps/worker/src/network.ts` (docs/COMPETITORS-OPENMUSE-2026-10-08.md) and
# then checking this file: its own allowlist taught the check about the
# ranges the internet has set aside for things that are NOT a destination.
# None of these is "somewhere on the open internet" either, so a fetch to
# one is refused for exactly the reason 127.0.0.1 is - and two of them are
# reachable on purpose by ordinary software (198.18.0.0/15 is claimed by
# some VPN and proxy tools; 192.0.0.1/192.0.0.9 are DNS64 and PCP anycast),
# which is the reason to name them rather than assume nobody would try.
_PRIVATE_NETS = _OWN_NETS + (
    ipaddress.ip_network("169.254.0.0/16"), ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("0.0.0.0/8"), ipaddress.ip_network("::/128"),
    # RFC 5735/6890 "never a destination": protocol assignments, the three
    # TEST-NET blocks a documentation example uses, the benchmarking block.
    ipaddress.ip_network("192.0.0.0/24"), ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"), ipaddress.ip_network("203.0.113.0/24"),
    # Multicast and the reserved top of the space (255.255.255.255 in it),
    # and the IPv6 equivalents.
    ipaddress.ip_network("224.0.0.0/4"), ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("ff00::/8"), ipaddress.ip_network("2001:db8::/32"),
)

#: NAT64 (RFC 6052): what a DNS64 network answers for a name that only has
#: an IPv4 address. `127.0.0.1` inside it is spelled `64:ff9b::7f00:1`, and
#: `ipaddress` does NOT report that as `.ipv4_mapped`, so without the
#: unwrapping in `_address_carries` the private address behind it would be
#: invisible to the check. The range itself is deliberately NOT in
#: `_PRIVATE_NETS`: a NAT64 address carrying a genuinely public IPv4 is a
#: legitimate way for an IPv6-only machine to reach the open internet, and
#: refusing the whole range would break that for no security gain.
_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def _address_carries(ip):
    """The IPv4 address an IPv6 address CARRIES, or None.

    Two real forms, both of which the operating system will dial as the
    address they embed: IPv4-mapped (`::ffff:0:0/96`, which `ipaddress`
    reports as `.ipv4_mapped`) and NAT64 (`64:ff9b::/96`)."""
    if ip.version == 4:
        return None
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip in _NAT64:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def _resolved_addresses(host: str) -> list:
    """The real addresses `host` denotes RIGHT NOW: the literal address if
    `host` already is one, else every address a live DNS lookup returns.
    Never cached, and callers are expected to call this again before every
    fetch - see "WHY THIS IS CALLED AGAIN" above. Empty when the name will
    not resolve at all (the caller then has nothing to fetch either).

    An IPv4-mapped IPv6 answer (`::ffff:127.0.0.1`) is judged as the IPv4
    address it carries, exactly as `_as_address` already did for a literal
    one (security/privacy audit 2026-09-27: a DNS AAAA record of that shape
    passed, although the same address typed literally was refused)."""
    ip = _as_address(host)
    if ip is not None:
        return [ip]
    try:
        infos = socket.getaddrinfo(host, None)
    except (OSError, UnicodeError):
        return []
    out = []
    for info in infos:
        try:
            addr = info[4][0]
            ip = ipaddress.ip_address(addr.split("%", 1)[0])
        except (ValueError, IndexError, TypeError):
            continue
        if ip.version == 6 and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if ip not in out:
            out.append(ip)
    return out


def _is_private(ip) -> bool:
    """Is this an address Jarvis must not reach for a fetch meant to be on
    the open internet?

    Unwraps a carried IPv4 FIRST (see `_address_carries`): an IPv6 address
    that is a wrapped 127.0.0.1 or 10.0.0.5 is judged as the address it
    really is, never as a harmless-looking IPv6 one. Recursion ends at the
    IPv4 hop, and IPv4 addresses never carry anything."""
    inner = _address_carries(ip)
    if inner is not None:
        return _is_private(inner)
    return any(ip in net for net in _PRIVATE_NETS if net.version == ip.version)


def private_fetch_problem(url: str) -> str:
    """"" when Jarvis may fetch `url` - an address the OWNER TYPED, meant to
    be somewhere on the open internet - else the plain sentence why not.

    Refused when the host is a bare address in a private, loopback or
    link-local range, OR a name whose real DNS answer, looked up just now,
    resolves to one of those: a news feed or "tell me when this page
    changes" address must never become a way to make Jarvis's own PC, or
    anything on its home network, fetch itself. Every address is checked,
    never only the first. `http` and `https` only; anything else (a file
    path, `ftp://`, a bare host with no scheme) is refused too, since this
    is only ever called before a GET Jarvis itself makes.

    Call this again immediately before every fetch, not only when the
    address is first added - see the module docstring."""
    url = str(url or "").strip()
    try:
        parts = urllib.parse.urlsplit(url)
        scheme, host = parts.scheme.lower(), parts.hostname or ""
    except ValueError:
        return "That address could not be read."
    if scheme not in ("http", "https"):
        return "That address must start with http:// or https://."
    if not host:
        return "That address needs a host name."
    addrs = _resolved_addresses(host)
    if not addrs:
        return f"{host} could not be looked up - there may be no such address."
    for ip in addrs:
        if _is_private(ip):
            return _private_words(host, ip)
    return ""


def _private_words(host, ip) -> str:
    return (f"{host} leads to {ip}, which is this PC or a private network address, "
            f"not somewhere on the open internet. Refused, so a web address could "
            f"never be used to make Jarvis fetch something from its own network.")


# --------------------------------------------------------------------------
# THE CHECK AND THE CONNECTION MUST USE THE SAME LOOKUP (security/privacy
# audit, 2026-09-27)
#
# `private_fetch_problem` above looks the name up, and then urllib looks it
# up AGAIN, on its own, when it connects. A name whose DNS answer changes
# between those two lookups (a public address for the check, 127.0.0.1 or
# 192.168.x.x a moment later - "fast" DNS rebinding, with a zero-second
# DNS lifetime) passed the check and was then fetched from this PC or the
# home network. Re-checking before every fetch (above) only closes the
# SLOW version, where the answer changes between the card and a later look.
#
# `public_urlopen` closes the fast one: its connections resolve the name
# ONCE, refuse if ANY answer is private (the same rule, `_is_private`), and
# then connect to one of exactly those checked addresses - never to the
# name, so nothing can be looked up a second time. https still checks the
# certificate against the NAME (http.client wraps the socket with
# server_hostname=<the name>), so pinning the address costs no TLS safety.
# Every connection a redirect makes goes through the same code, so a
# redirect is checked here too, not only by the callers' redirect handlers.
# No proxy, ever: a proxy would do its own lookup, out of this check's reach.
# --------------------------------------------------------------------------

class PrivateAddressRefused(OSError):
    """A public fetch whose name, looked up at connect time, led somewhere
    private. An OSError, so urllib reports it as it would any failed
    connection (wrapped in URLError) and callers need nothing new."""


def _connect_public(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None,
                    *args, **kwargs):
    """Stands in for socket.create_connection on a public fetch's
    connection: ONE lookup, every answer checked, then a connection to a
    checked address itself (see the section above)."""
    host, port = address[0], address[1]
    addrs = _resolved_addresses(host)
    if not addrs:
        raise PrivateAddressRefused(f"{host} could not be looked up")
    for ip in addrs:
        if _is_private(ip):
            raise PrivateAddressRefused(_private_words(host, ip))
    last = None
    for ip in addrs:
        try:
            return socket.create_connection((str(ip), port), timeout, source_address)
        except OSError as exc:
            last = exc
    raise last  # type: ignore[misc]


class _PublicHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connect_public


class _PublicHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connect_public


class _PublicHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_PublicHTTPConnection, req)


class _PublicHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        kwargs = {"context": self._context}
        if hasattr(self, "_check_hostname"):      # Python 3.11 and older only
            kwargs["check_hostname"] = self._check_hostname
        return self.do_open(_PublicHTTPSConnection, req, **kwargs)


def public_opener(*handlers) -> urllib.request.OpenerDirector:
    """An opener for an address the owner typed, meant to be on the open
    internet (a news feed, a page to watch): never a proxy, and every
    connection it makes - redirects included - checked by `_connect_public`
    against the very address it then connects to. Plus any extra
    `handlers` (a module's own redirect rule)."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _PublicHTTPHandler(),
                                       _PublicHTTPSHandler(), *handlers)


def public_urlopen(req, timeout: float, *handlers):
    """`urllib.request.urlopen(req, timeout=timeout)` for a public address:
    no proxy, and the private-address check made on the connection itself."""
    return public_opener(*handlers).open(req, timeout=timeout)
