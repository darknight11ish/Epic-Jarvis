"""jarvis_owner_check.py - the PC's own "is it really you?" check for approvals.

WHAT THIS IS FOR (docs/APPROVAL-GAP-DESIGN.md, step 1; the owner's decisions
of 2026-09-25 in CLAUDE.md)

Until now the Windows Hello check before a risky approval ran inside the
desktop app. The backend's POST /api/approve asked only for the pairing
token, and any program running as the owner can read that token. And the
approval gate (jarvis_gate.check) waited only for its row in approvals.db
to say "approved" - a file any program running as the owner can write. So a
program already on the PC could approve a card in two cheap ways, without
meeting Windows Hello at all.

This module closes those two cheap ways:

1. **The backend asks Windows Hello itself** before it accepts a RISKY
   approval that comes FROM THIS PC. The prompt shows the card's own title
   and why it matters, so a prompt nobody asked for names a card nobody
   pressed Approve on. A PC with no Windows Hello set up refuses risky
   approvals, with a sentence saying how to set it up (the owner's "no lock,
   no risky approval").
2. **Every real approval is stamped** by this running process, with a secret
   made fresh at every start and kept only in this process's memory. The
   gate (owner-check.patch) accepts "approved" only with a valid stamp, so
   "approved" written straight into approvals.db is refused.

WHAT IT DOES NOT STOP (said plainly, as the design does)

- A program written specifically to attack Jarvis, running as the owner,
  can still edit Jarvis's own files or take over its running process.
  Windows does not protect one of the owner's programs from another.
- A card that is NOT risky (it stays on this PC, can be undone, and nothing
  tried to rush it) can still be approved by a program that holds the token.
  "Risky only" is the phone's rule, and the desktop's default.
- An approval that arrives from ANOTHER device (the phone, over Tailscale or
  Meshnet) is not checked here: the phone checks its own fingerprint. A
  stolen token used from another device on the owner's private network is
  therefore still let through, until step 2 (a phone key per approval,
  with "more devices").

THE PIECES

- `is_risky(row)`       the phone's and the desktop's rule, on a pending row.
                        The shared cases are tools/gen_risky_approval_cases.py.
- `from_this_pc(...)`   is a request from this PC, or from another device?
- `approve_check(...)`  what POST /api/approve must do before the owner's
                        own handler records the answer.
- `stamp` / `take_stamp` the in-memory stamp the gate asks for.
- `install(Handler)`    wraps the web server's POST handler (owner-check.patch
                        calls it at start-up, in jarvis_hud.py).
- `verify(message)`     Windows Hello, in a child process; a stand-in can be
                        set for tests (`set_verifier`). Anything but Windows
                        is "unavailable", so a risky approval from the PC is
                        refused there - it fails closed.

Deny never comes here: POST /api/deny is passed straight to the owner's
handler, never held up by a prompt, and never needs a stamp.

Standard library only. The Windows Hello call is made with ctypes (built
into Python) rather than the `winrt` packages: those (3.2.1, checked in the
wheel's own type stubs) offer only the plain RequestVerificationAsync, and
Microsoft's documentation says a desktop program should use the "for a
window" form, which only the Windows API itself offers.
"""
from __future__ import annotations

import atexit
import hashlib
import hmac
import io
import ipaddress
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

# ---------------------------------------------------------------------------
# The words. The desktop says the same (lock/rules.rs), and the phone says
# the same about its screen lock (data/Security.kt).
# ---------------------------------------------------------------------------

#: A PC with no Windows Hello: the owner's "no lock, no risky approval".
#: The desktop's pages add " - nothing was decided. Try again." after it.
NOT_SET_UP = ("Windows Hello is not set up on this PC, so Jarvis cannot check it is "
              "you, and risky approvals are refused until it is. Set up Windows Hello "
              "in Windows Settings (Accounts, Sign-in options) to approve risky "
              "actions - a PIN is enough")
CANCELLED = "Windows Hello did not confirm it was you, so nothing was approved"
FAILED = ("The Windows Hello check could not be shown just now, so nothing was "
          "approved. Wait a moment")
#: The card stopped waiting while the prompt was open: it ran out of time, or
#: it was denied meanwhile. A 409, which both apps read as "no longer waiting".
GONE = ("This request stopped waiting while Windows Hello was open (it ran out of "
        "time or was answered), so it was not approved")
QUEUE_UNREADABLE = ("The approval queue could not be read, so Jarvis cannot tell "
                    "whether this approval needs Windows Hello. Nothing was approved")
#: The action has no written words of its own, so a prompt could only quote a
#: name nobody described: refused before any prompt appears (2026-10-26).
UNLABELLED = ("Jarvis has no written words for this action yet, so it will not ask "
              "you to confirm it. Nothing was approved")

#: Cards that are approved on THIS PC only, and always with Windows Hello,
#: whatever their risk says: loosening "What asks first" (jarvis_asks_first.
#: py, the owner's decision of 2026-09-26 - "on the PC only ... one card plus
#: Windows Hello per change"), offering a reading tool to the AI model at
#: all (jarvis_asks_first.py, the owner's answer of 2026-09-27 - "each with a
#: card plus Windows Hello"), and restoring from a locked backup file
#: (jarvis_backup.py, the owner's answer of 2026-09-27 - "restore is a card +
#: Windows Hello": it replaces memory, chat history, settings and notes with
#: what was saved then, so it always gets both, whatever the gate's risk
#: table says). An approval of one from another device - the phone, or
#: anything on the owner's network pretending to be it - is refused (403),
#: so a stolen token used elsewhere cannot loosen, enable or restore
#: anything. Also connecting a new device and bringing the old shared key
#: back for other devices (jarvis_devices.py, docs/PAIRING-DESIGN.md 6.3 and
#: 6.4, 2026-09-28): a stolen key used elsewhere cannot approve a new device
#: of its own, and on a PC without Windows Hello pairing waits until it is
#: set up (the owner's "no lock, no risky approval"). And letting a paired
#: phone approve risky cards with its own fingerprint or PIN
#: (register_approval_key, docs/PAIRING-DESIGN.md section 11): a stolen key
#: used elsewhere must not be able to register a signing key of its own.
#:
#: And RAISING a chatbot service's monthly money limit (jarvis_chatbot_limits.py;
#: the owner's approval of 2026-10-06, docs/ACCOUNT-KEYS-DESIGN.md decisions 1
#: and 3): raising it lets Jarvis spend more of the owner's money on that
#: service's account, so it is a loosening - it stays on this PC and always
#: asks Windows Hello. The LOWERING has its own action name,
#: "lower_api_limit", and is deliberately NOT on this list: it only ever
#: spends less, so it needs no card and no check. Two names rather than one
#: direction-blind name is the whole point - this list is read by ACTION, so
#: one name covering both directions would ask Hello for a lowering too.
#: And KEEPING the captcha hand-off on offer for the full 15 minutes instead of
#: stopping early (jarvis_handoff_mode.py; the owner's decision of 2026-10-08,
#: "make this a setting for both options with 1 as the default"): a live picture
#: of one of the owner's own browser windows - which may hold their account
#: details - stays on offer fifteen times longer, so choosing it is a loosening
#: that stays on this PC and always asks Windows Hello. Going back to "Stop
#: early" is the other direction and needs neither: it applies at once, from
#: either app (the OFF path in jarvis_handoff_mode.request never reaches here).
#: `raise_api_limit` USED to be in this set, and the owner took it out on
#: 2026-10-11: "Let the phone raise it too, with its own fingerprint." A raise
#: is still a RISKY card (`jarvis_asks_first`: tier ask, "lets Jarvis spend more
#: of your money"), so the two halves of the rule both stay:
#:   * on the PC it still asks Windows Hello - `is_risky` sends it there, which
#:     is why removing it from this set does not weaken the desktop's own path;
#:   * on the phone it needs that phone's signed approval, a fresh fingerprint
#:     or PIN over a one-use challenge, and a phone with no approval key is
#:     refused with "no_approval_key" so it can offer to turn signing on.
#: What the owner changed is only WHERE the raise may be confirmed, never
#: whether a person has to confirm it.
PC_ONLY_ACTIONS = frozenset({"loosen_what_asks_first", "enable_reading_tool", "restore_backup",
                             "pair_device", "unretire_shared_key", "register_approval_key",
                             "handoff_keep_offering",
                             "handoff_bring_to_front"})
PC_ONLY = ("This card can only be approved on the PC, with Windows Hello, so nothing was "
           "approved")

#: The shipped approval_timeout_seconds, used when a row carries no
#: `expires_in` (a backend without approval-expiry.patch).
DEFAULT_TIME_LEFT = 900.0

#: The longest a Windows Hello prompt may stay up, however much time its card
#: has left (2026-10-26). The prompt's only cancellation is its own deadline -
#: the visible dialog belongs to Windows, and killing the process that asked
#: for it does not close it (measured: .dsh-scratch/WINDOWS-HELLO-2026-10-26/
#: FINDINGS.md section 3) - so the number given here IS its lifetime. Three
#: minutes is long enough to reach the PC and confirm, and short enough that a
#: prompt queued behind another one cannot sit on screen for a quarter of an
#: hour because its card happened to have that long. The card is not used up
#: by a prompt that closes: it keeps waiting, and Approve can be pressed
#: again.
_PROMPT_MAX = 180.0

#: The ceiling on how long a request waits for the one-prompt-at-a-time lock
#: before it is refused (2026-10-26 review). The prompt in front of it can last
#: `_PROMPT_MAX` (180 s); its child then gets ten seconds to answer after its
#: own deadline (`_verify_windows`'s `proc.wait`), the cancel that follows gets
#: two more, and `stop()`'s two-second join runs while the lock is still held -
#: so the worst legitimate hold is about 194 s, and 210 is the ceiling that
#: covers it. (The thirty seconds is slack over the PROMPT, not over that hold:
#: 210 - 180.) `_PROMPT.acquire(-1)` waited for ever: one child that never
#: answered held every later approval until the backend was restarted. A card
#: that has not had its turn is refused with the same 409 as one that ran out.
_PROMPT_WAIT_MAX = _PROMPT_MAX + 30.0

#: How often the card is asked whether it is still waiting while its prompt is
#: open (2026-10-26 review; .dsh-scratch/WINDOWS-HELLO-2026-10-26/FINDINGS.md
#: section 5 B asks for 0.25 s). A quarter of a second is fast enough that the
#: dialog is gone a moment after its card is, and cheap enough that the poll
#: costs nothing: one queue read four times a second, only while a prompt is up.
_WATCH_INTERVAL = 0.25


def _wait_for_prompt(left: Optional[float]) -> float:
    """How long a request may wait for the one-prompt-at-a-time lock.

    A card with no deadline waits the whole `_PROMPT_WAIT_MAX`; a card with one
    waits its own time left, because it can never be prompted after that - and
    never more than `_PROMPT_WAIT_MAX`, the ceiling that covers the worst
    legitimate hold of the prompt in front: about 194 s, being 180 s of prompt,
    ten seconds for the child's answer, two for the cancel and two for
    `stop()`'s join (2026-10-26 review: the cap used to be `_PROMPT_MAX`,
    180 s, up to about 14 s short of that hold, so a card could be refused just
    as its turn arrived).
    """
    return _PROMPT_WAIT_MAX if left is None else min(left, _PROMPT_WAIT_MAX)


# ---------------------------------------------------------------------------
# Which approvals are risky - ONE rule, three places
# ---------------------------------------------------------------------------


def _raised(row: dict) -> bool:
    """The rush latch, read the way the desktop's `is_risky` reads it: only a
    missing value, JSON null or false is "not raised". Anything else - an
    object, true, the JSON text of an object, even text this code does not
    understand - is raised: an unreadable latch fails toward caution."""
    if "raised" not in row:
        return False
    value = row["raised"]
    return not (value is None or value is False)


def is_risky(row: Optional[dict]) -> bool:
    """True when approving `row` (a /api/pending row) needs the owner's check.

    The phone's rule (SecurityRules.riskyByToday) and the desktop's
    (lock/rules.rs `is_risky`): anything the gate has not classified,
    anything that leaves this PC, anything that cannot be undone, and
    anything outside text tried to rush. A missing `reach` is "outbound", a
    missing `reversible` is "no", a missing `risk` is unclassified - so a row
    this code cannot read is risky. tools/gen_risky_approval_cases.py writes
    the cases all three apps are tested against.
    """
    if not isinstance(row, dict):
        return True
    risk = row.get("risk")
    if not isinstance(risk, dict) or risk.get("classified") is not True:
        return True
    reach = risk.get("reach")
    if not isinstance(reach, str) or reach == "outbound":
        return True
    reversible = risk.get("reversible")
    if not isinstance(reversible, str) or reversible == "no":
        return True
    return _raised(row)


def approval_message(row: Optional[dict]) -> str:
    """What the Windows Hello prompt says: the gate's own title (built from
    the action name and the risk table, never the payload) and why it
    matters - the desktop's `approval_message`, word for word."""
    row = row if isinstance(row, dict) else {}
    notice = row.get("notice") if isinstance(row.get("notice"), dict) else {}
    title = str(notice.get("title") or "").strip()
    if not title:
        action = row.get("action")
        title = f"Approve: {action}" if isinstance(action, str) else "Approve a Jarvis action"
    risk = row.get("risk") if isinstance(row.get("risk"), dict) else {}
    why = str(risk.get("why") or "").strip() or "Check the card before you confirm."
    return f"{title}\n{why}"[:300]


def has_written_title(action) -> bool:
    """True when jarvis_card_words has words somebody WROTE for `action`.

    `approval_message` can always build a readable line, because the card's
    own title is there - but for an action with no phrase in the card words,
    that title is a name Jarvis quotes back (`title_for`'s fallback), not a
    description of anything. A prompt showing only that asks the owner to
    confirm a blank, so `approve_check` refuses before the prompt appears
    (2026-10-26).

    A missing words module answers False, and that is on purpose: if this
    process cannot read the written words, it cannot prove a card has any.
    """
    try:
        import jarvis_card_words
        return bool(jarvis_card_words.has_written_title(action))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# From this PC, or from another device?
# ---------------------------------------------------------------------------

_OWN_CACHE: dict = {"at": 0.0, "set": frozenset()}
_OWN_TTL = 60.0


def _ip(text) -> Optional[ipaddress._BaseAddress]:
    try:
        ip = ipaddress.ip_address(str(text or "").split("%", 1)[0].strip("[] "))
    except ValueError:
        return None
    mapped = getattr(ip, "ipv4_mapped", None)
    return mapped or ip


def own_addresses() -> frozenset:
    """This PC's own addresses, as Windows answers for its own name (every
    adapter's, Tailscale's and Meshnet's included). Cached for a minute; an
    error is an empty set - the connection's own address still counts."""
    now = time.monotonic()
    if now - _OWN_CACHE["at"] < _OWN_TTL:
        return _OWN_CACHE["set"]
    found = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = _ip(info[4][0])
            if ip is not None:
                found.add(ip)
    except (OSError, UnicodeError, ValueError):
        pass
    _OWN_CACHE.update(at=now, set=frozenset(found))
    return _OWN_CACHE["set"]


def from_this_pc(peer, local=None, own=None) -> bool:
    """True when a connection from `peer` (arriving at `local`) comes from
    this PC.

    Loopback (127.0.0.1, ::1) is this PC. So is a connection from one of
    this PC's own addresses: a program on the PC that calls the PC's own
    Tailscale address arrives FROM that same address - which is also the
    address the connection arrived AT, so `peer == local` catches it even
    when the name lookup misses an adapter.

    FAIL CLOSED when a NETWORK peer cannot be placed (2026-10-18, SECPRIV
    audit N8): an unparsable peer string (including "") or the unspecified
    address is NOT taken as proof of being on the PC. It used to return True
    for those, so a wrapper that handed a malformed peer through would
    silently turn a remote request into a local one for every PC-only route.

    `peer is None` is different, and is NOT "an unparsable peer": it is the
    project's documented in-process convention - a direct call with no network
    request behind it (jarvis_brain_reads.handle_get's own docstring, and the
    suites that call a handler in-process). A remote caller can never make
    client_address None, so None cannot be attacker-controlled; it means "no
    request to place", and keeps answering as this PC the way it always has.
    A program on the PC cannot make its request come from the phone's address;
    it would need another device.
    """
    if peer is None:
        return True                       # no request to place: in-process
    p = _ip(peer)
    if p is None or p.is_unspecified:
        return False
    if p.is_loopback:
        return True
    lo = _ip(local)
    if lo is not None and p == lo:
        return True
    return p in (own_addresses() if own is None else frozenset(_ip(a) for a in own))


# ---------------------------------------------------------------------------
# The HUD's two request-edge checks, extracted so CI can test the real code
# ---------------------------------------------------------------------------
#
# These used to live only inside jarvis_hud.py, which is on the owner's PC and
# not in this repository - so the only tests of them SKIPPED on a clean
# checkout, and CI never ran them. The DECISIONS are pure; only reading the
# request and the configuration stays in the HUD:
#
#   * `origin_ok(handler, served)` gets a duck-typed handler and the set of
#     origins this server was configured to answer on. `_served_origins()`
#     itself stays in the HUD - it reads the bind address and HUD_PORT, which
#     only the running server knows.
#   * `token_ok(handler, token, cookie, query)` gets the token (HUD_TOKEN, or
#     "" when none is configured) and the two HUD-specific extractors. A
#     `token` of "" means "not configured", and then only a loopback caller is
#     believed.
#
# `jarvis_hud.py` calls these through `hud-origin-module.patch`; the test suite
# `backend/test_origin.py` imports them and runs with zero skips on a clean
# checkout, instead of lifting the function out of the installed HUD.

#: The three places a request may present the token: a header, the cookie the
#: HUD sets after the first load, and the one-time ?token= bootstrap.
_HUD_TOKEN_HEADER = "X-Jarvis-Token"
_HUD_CLIENT_HEADER = "X-Jarvis-Client"
_HUD_TOKEN_COOKIE = "jarvis_token"

#: Peers believed when NO token is configured: this PC only.
_HUD_LOOPBACK_PEERS = frozenset({"127.0.0.1", "::1", "::ffff:127.0.0.1"})

#: The two private mesh ranges a browser or a phone reaches Jarvis on:
#: Tailscale and NordVPN Meshnet both hand out 100.64.0.0/10, and the IPv6
#: range is Tailscale's own. A public address is deliberately NOT here - the
#: app never opens a public tunnel (CLAUDE.md rule 2).
_MESH_NETWORKS = (ipaddress.ip_network("100.64.0.0/10"),
                  ipaddress.ip_network("fd7a:115c:a1e0::/48"))

#: The port a HUD answers on unless the owner configured another. The caller's
#: `served_origins` are read for any other configured port.
_HUD_DEFAULT_PORT = 4719

#: A mesh hostname: at least one label, then NordVPN Meshnet's `.nord` or
#: Tailscale MagicDNS's `.ts.net`. DNS labels (letters, digits, hyphens, no
#: leading or trailing hyphen), lower case because `urlsplit` lowercases the
#: hostname. `nord` alone does not match, and neither does a lookalike such as
#: `nord.evil.example`.
_MESH_HOST = re.compile(
    r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:nord|ts\.net)")


def _peer(handler):
    """The socket peer's IP address, or None when it cannot be read."""
    try:
        peer = (handler.client_address or ("",))[0]
    except Exception:
        return None
    return _ip(peer)


def _peer_on_mesh(handler, address=None) -> bool:
    """Is this request from this PC (loopback) or from another of the owner's
    devices on Tailscale/Meshnet?

    Fails closed: a peer that is absent or cannot be parsed is NOT on the
    mesh, whatever the request claims (the same rule as `from_this_pc`).
    """
    p = _peer(handler) if address is None else address
    if p is None or p.is_unspecified:
        return False
    if p.is_loopback:
        return True
    return any(p.version == n.version and p in n for n in _MESH_NETWORKS)


def _served_ports(served_origins) -> frozenset:
    """Every port this server was configured to answer on, plus the HUD's own
    default. A mesh Origin may name one of these; any other port is a
    different page on that machine, so it is refused."""
    ports = {_HUD_DEFAULT_PORT}
    for origin in served_origins or ():
        try:
            port = urlsplit(str(origin)).port
        except (TypeError, ValueError):
            continue
        if port is not None:
            ports.add(port)
    return frozenset(ports)


def _mesh_origin_ok(origin: str, handler, served_origins) -> bool:
    """A browser on this PC or on the owner's private mesh, talking to
    Jarvis by the machine's mesh name, sends an Origin the server's own
    configuration cannot list in advance: `_served_origins()` is built from
    the bind address and the port, not from a `.nord` / `.ts.net` DNS name.
    Without this the page loaded, then every POST that carried `Origin:
    http://mariorelan11-alps.nord:4719` was refused 403.

    Accepted host: loopback (`localhost`, `127.0.0.1`, `::1`), an IP literal
    in 100.64.0.0/10 (the range both mesh products use), or a hostname ending
    `.nord` / `.ts.net`. Accepted port: none (a browser omits the scheme's
    default) or one this server serves - 4719 unless configured otherwise.
    http or https only; `Origin: null`, a userinfo part and every other page
    are refused. And only from a peer on this PC or the private mesh: a
    public address gets nothing new from this, whatever Origin it sends.
    """
    if not _peer_on_mesh(handler):
        return False
    try:
        parts = urlsplit(str(origin or ""))
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    if parts.username or parts.password:
        return False
    try:
        port = parts.port
    except ValueError:
        return False
    if port is not None and port not in _served_ports(served_origins):
        return False
    host = (parts.hostname or "").lower()
    if not host:
        return False
    ip = _ip(host)
    if ip is not None:
        return ip.is_loopback or any(
            ip.version == n.version and ip in n for n in _MESH_NETWORKS)
    if host == "localhost":
        return True
    return bool(_MESH_HOST.fullmatch(host))


def _sse_same_origin_ok(handler) -> bool:
    """A browser's EventSource cannot set a request header, and a same-origin
    subscription is sent with no Origin at all. The HUD's own copy of this
    narrow exemption (`_same_origin_stream`) only believes a loopback peer,
    so a browser on the owner's iPad or second PC was refused 403 on
    /api/events and the HUD stayed "stale" - Approve blocked for ever.

    Accept the event stream itself, with no Origin, from a peer on this PC or
    on the mesh, and only when the request asked for an event stream
    (`Accept: text/event-stream`, which EventSource always sends and a
    cross-origin page cannot set without a preflight that carries an Origin).
    Every other route keeps the real Origin check, and the stream still needs
    the token.
    """
    if not _peer_on_mesh(handler):
        return False
    path = str(getattr(handler, "path", "") or "").split("?", 1)[0].rstrip("/")
    if path != "/api/events":
        return False
    try:
        accept = (handler.headers.get("Accept") or "").lower()
    except Exception:
        return False
    return "text/event-stream" in accept


def origin_ok(handler, served_origins) -> bool:
    """Is this request from a page we serve, or from a non-browser client?

    The first version accepted any Origin that matched the Host header. Both
    are supplied by the caller. In a DNS-rebinding attack a page on
    attacker.example rebinds that name to 127.0.0.1, sends
    Origin: http://attacker.example and Host: attacker.example, they match,
    and a page you merely visited was inside the CSRF defence - approving
    Jarvis's own pending shell commands. The Host header is not an identity.
    Trust is derived from what THIS server was configured to answer on, which
    is exactly the `served_origins` set the caller supplies.

    Two additions, both additive (2026-10-23, the PWA slice; the routes are
    documented in docs/JARVIS-API.md section 90):
      * a mesh Origin (`.nord`, `.ts.net`, a CGNAT IP literal or a loopback
        host) is accepted from a peer on this PC or the private mesh, even
        though the server's configuration never lists that DNS name - see
        `_mesh_origin_ok`;
      * a no-Origin `/api/events` request from such a peer is accepted when
        it asked for an event stream, because a browser's EventSource cannot
        set a header - see `_sse_same_origin_ok`.

    No Origin at all elsewhere: the request must carry `X-Jarvis-Client:
    hud`, which forces a CORS preflight and so cannot be produced by a
    drive-by simple request.
    """
    try:
        origin = (handler.headers.get("Origin") or "").rstrip("/")
        client = handler.headers.get(_HUD_CLIENT_HEADER)
    except Exception:                    # no headers object: refuse, never guess
        return False
    if origin:
        if origin in (served_origins or ()):
            return True
        return _mesh_origin_ok(origin, handler, served_origins)
    if client == "hud":
        return True
    return _sse_same_origin_ok(handler)


def token_ok(handler, token, cookie, query) -> bool:
    """Is the shared secret presented correctly, or is this the untokened
    loopback case?

    `token` is the configured HUD_TOKEN ("" = none configured). `cookie` and
    `query` are the HUD's own extractors: `(handler) -> str`. Three ways are
    accepted because a header alone locks out the HUD page itself (it has no
    token field): X-Jarvis-Token, the `jarvis_token` cookie (SameSite=Strict,
    so a cross-site request does not carry it), and the one-time ?token=
    bootstrap that plants that cookie.

    With no token configured, only a loopback peer is believed. Comparands are
    encoded to UTF-8 and compared as BYTES: `hmac.compare_digest` raises
    TypeError on non-ASCII str, and headers arrive latin-1 decoded, so an
    attacker-chosen byte used to crash the handler and print a traceback with
    local paths. Any failure to compare is a refusal.
    """
    try:
        peer = (handler.client_address or ("",))[0]
    except Exception:
        return False
    if not token:
        return peer in _HUD_LOOPBACK_PEERS
    want = str(token).encode("utf-8", "replace")
    try:
        candidates = (
            handler.headers.get(_HUD_TOKEN_HEADER) or "",
            cookie(handler) if callable(cookie) else "",
            query(handler) if callable(query) else "",
        )
    except Exception:
        return False
    for cand in candidates:
        if not cand:
            continue
        try:
            if hmac.compare_digest(str(cand).encode("utf-8", "replace"), want):
                return True
        except Exception:
            continue
    return False


#: The token-failure rate bucket (SECPRIV audit 2026-10-18, N3). The HUD calls
#: it from `_token_ok` through hud-request-gate.patch: count only requests that
#: actually PRESENTED a token and were refused, so ordinary unauthenticated
#: status/pre-flight polls are not penalised. Over the limit (the 11th failure) the HUD's
#: `_request_gate` turns the route's 401 into a 429 with Retry-After: 60.
class TokenFailureLimiter:
    """Pure, clock-injectable: MAX failures in WINDOW seconds blocks a peer.

    `clock` defaults to `time.monotonic`; a test passes a fake clock. One
    peer's history is pruned on every read/write, so memory is bounded by the
    peers that are actually failing. A valid token resets that peer at once.
    """

    def __init__(self, max_failures: int = 10, window_s: float = 60.0,
                 clock=None):
        self.max_failures = max(1, int(max_failures))
        self.window_s = max(1.0, float(window_s))
        self._clock = clock or time.monotonic
        self._failures = {}          # peer -> [monotonic seconds]
        self._lock = threading.Lock()

    def _recent(self, peer: str, now: float):
        stamps = [t for t in self._failures.get(peer, ())
                  if now - t < self.window_s]
        if stamps:
            self._failures[peer] = stamps
        else:
            self._failures.pop(peer, None)
        return stamps

    def blocked(self, peer: str) -> bool:
        with self._lock:
            return len(self._recent(peer, self._clock())) > self.max_failures

    def failed(self, peer: str) -> int:
        """Record one refused request that presented a token; returns the count
        inside the window (so callers can log the transition)."""
        with self._lock:
            now = self._clock()
            stamps = self._recent(peer, now)
            stamps.append(now)
            self._failures[peer] = stamps
            return len(stamps)

    def succeeded(self, peer: str) -> None:
        with self._lock:
            self._failures.pop(peer, None)


#: The one bucket the HUD uses when it is installed.
TOKEN_FAILURES = TokenFailureLimiter()


def request_carries_token(handler) -> bool:
    """Did this request PRESENT a token (any of the three ways)? Used to decide
    whether a refusal counts against the peer's rate bucket. A request with no
    token at all is a normal unauthenticated poll and is not counted.

    The query is read the way the HUD's own extractor reads it - through
    `urllib.parse` (2026-10-18 follow-up audit, MEDIUM): the first version
    matched the raw string "token=" in the path, so `?tok%65n=<guess>` (a
    percent-encoded `e`) reached the HUD's `_query_token` as `token` and got a
    401 while this helper said "no token presented", and the failure never
    filled the rate bucket. Decode the query names with `parse_qs`; do not
    import HUD code. The cookie is matched by NAME (a value containing
    "jarvis_token=" is not a presentation), and the header exactly as the HUD
    extracts it.
    """
    try:
        if (handler.headers.get(_HUD_TOKEN_HEADER) or "").strip():
            return True
        for part in (handler.headers.get("Cookie") or "").split(";"):
            name, _, _value = part.strip().partition("=")
            if name.strip() == _HUD_TOKEN_COOKIE:
                return True
        from urllib.parse import parse_qs, urlsplit
        query = parse_qs(urlsplit(getattr(handler, "path", "") or "").query)
        return "token" in query
    except Exception:
        return False


# ---------------------------------------------------------------------------
# The stamp
# ---------------------------------------------------------------------------

# Made fresh at every start and never written anywhere. A card still waiting
# when the backend restarts is refused anyway (its wait died with the old
# process), so a new secret loses nothing.
_SECRET = secrets.token_bytes(32)
_STAMPS: dict = {}
_STAMPS_LOCK = threading.Lock()
_MAX_STAMPS = 256
#: How long a stamp is honoured. 20 minutes is a deliberate margin over the
#: 15-minute default for an ordinary card (900 s shipped since 2026-10-13, and
#: changeable from Settings): if the two were equal, a stamp made at the start
#: of a card would expire exactly as the card did, and a late approval could
#: be refused for a Hello it had already given. backend/test_limits.py holds
#: that relationship for ordinary cards.
#:
#: A never-expiring card (jarvis_gate.APPROVAL_NEVER_EXPIRES - pairing, an
#: approval key, a restore) has no finite window for a stamp to outlive, so
#: this number no longer bounds "longer than any card waits". It bounds how
#: long a stamp can be replayed instead, and the stamp is read by the waiting
#: thread within one 0.25 s poll, so the margin is enormous for its real job.
_STAMP_TTL = 20 * 60.0


def _mac(request_id, action) -> bytes:
    msg = f"{request_id}\x00{action}".encode("utf-8", "replace")
    return hmac.new(_SECRET, msg, hashlib.sha256).digest()


def stamp(request_id, action) -> None:
    """Record that THIS process accepted an approval of `request_id` for
    `action`, after every check it needed. Called only by `approve_check`
    (and by the owner-PC tests, which approve through the gate directly)."""
    now = time.monotonic()
    with _STAMPS_LOCK:
        for k in [k for k, (_, at) in _STAMPS.items() if now - at > _STAMP_TTL]:
            del _STAMPS[k]
        while len(_STAMPS) >= _MAX_STAMPS:
            del _STAMPS[next(iter(_STAMPS))]
        _STAMPS[str(request_id)] = (_mac(request_id, action), now)


def take_stamp(request_id, action) -> bool:
    """True, once, when `request_id` was stamped for `action` by this process.
    What jarvis_gate asks before it believes an "approved" row."""
    with _STAMPS_LOCK:
        got = _STAMPS.pop(str(request_id), None)
    if got is None:
        return False
    mac, at = got
    if time.monotonic() - at > _STAMP_TTL:
        return False
    return hmac.compare_digest(mac, _mac(request_id, action))


# ---------------------------------------------------------------------------
# Windows Hello
# ---------------------------------------------------------------------------

#: How one check ended - the desktop's four outcomes (lock/rules.rs Outcome).
CONFIRMED, CANCELLED_, UNAVAILABLE, FAILED_ = "confirmed", "cancelled", "unavailable", "failed"
OUTCOMES = frozenset({CONFIRMED, CANCELLED_, UNAVAILABLE, FAILED_})

_VERIFIER: Optional[Callable[[str, float], str]] = None
_PROMPT = threading.Lock()


class _LivePrompt:
    """One Windows Hello child process that is still waiting for an answer.

    The child watches its own stdin (`_watch_for_stop`): a "cancel" line, or
    the pipe closing, makes it cancel the Windows prompt instead of waiting
    out its deadline. Keeping this end of the pipe open is therefore what
    ties the prompt to the backend - when the backend goes away, the pipe
    closes, and the child asks Windows to close the dialog.
    """

    def __init__(self, proc, token=None):
        self.proc = proc
        #: Which approval raised this prompt. `None` when the prompt was not
        #: raised by `approve_check` (a hand-run, or a test's stand-in). The
        #: watcher matches on this so it can only ever cancel its OWN prompt
        #: (2026-10-26 review).
        self.token = token
        self.stop = threading.Event()

    def say(self, ask: dict) -> bool:
        """Send the one JSON line the child reads first. False if it cannot."""
        try:
            self.proc.stdin.write(json.dumps(ask) + "\n")
            self.proc.stdin.flush()
            return True
        except (OSError, ValueError, AttributeError):
            return False

    def cancel(self) -> None:
        """Ask the child to close the prompt, then close its pipe.

        Closing is the same request as the line (the child treats the end of
        the pipe as "the backend is going away"), so a lost line still stops
        it. Never raises.
        """
        self.stop.set()
        stdin = getattr(self.proc, "stdin", None)
        if stdin is None:
            return
        try:
            if not stdin.closed:
                stdin.write("cancel\n")
                stdin.flush()
        except Exception:
            pass
        try:
            stdin.close()
        except Exception:
            pass

    def close(self) -> None:
        """Close this end of the pipe once the prompt is over."""
        stdin = getattr(self.proc, "stdin", None)
        try:
            if stdin is not None and not stdin.closed:
                stdin.close()
        except Exception:
            pass


_LIVE_PROMPTS: set = set()
_LIVE_LOCK = threading.Lock()


def _cancel_live_prompts() -> int:
    """Ask every prompt still open to close. Returns how many were asked.

    Registered with `atexit` at import, which is this project's pattern for
    work that must happen on the way out (`jarvis_hud._release_gpu`, and
    several other modules). It covers a clean backend shutdown:
    /api/shutdown, Ctrl-C, a normal exit. It cannot cover a hard kill of the
    process - the desktop's job object, Task Manager - because no Python runs
    then, so a prompt in that case still ends only at its own deadline. That
    limit is real and is written down in the PR, not hidden here.
    """
    with _LIVE_LOCK:
        live = list(_LIVE_PROMPTS)
    for prompt in live:
        prompt.cancel()
    return len(live)


#: Thread-local token for the approval that is raising a prompt right now.
#: `approve_check` sets it around its `verify` call; `_verify_windows` reads it
#: and tags the live prompt with it. A thread-local, not a module global,
#: because the token belongs to one request (2026-10-26 review).
_CURRENT_PROMPT = threading.local()


def _prompt_token() -> Optional[object]:
    """The token of the prompt this thread is raising, or None."""
    return getattr(_CURRENT_PROMPT, "token", None)


def _cancel_prompts_for(token) -> int:
    """Ask only the prompts raised for ONE approval to close. Returns how many.

    `_cancel_live_prompts` is for shutdown: everything closes. This is for the
    card watcher, whose queue read can outlive `_PromptWatch.stop()`'s
    two-second join - so by the time it reports "gone", the prompt lock may have
    been released and the NEXT card's prompt may be the one on screen.
    Cancelling by token means a stale watcher can only close the prompt it was
    made for (2026-10-26 review). A token of None cancels nothing: an untagged
    prompt was not raised by `approve_check`, so no watcher owns it.
    """
    if token is None:
        return 0
    with _LIVE_LOCK:
        live = [p for p in _LIVE_PROMPTS if getattr(p, "token", None) is token]
    for prompt in live:
        prompt.cancel()
    return len(live)


#: The atexit hook itself, kept in a name so a test can check that importing
#: this module really registers it.
_SHUTDOWN_HOOK = atexit.register(_cancel_live_prompts)


def set_verifier(fn: Optional[Callable[[str, float], str]]) -> None:
    """Replace the Windows Hello call (tests). None puts the real one back."""
    global _VERIFIER
    _VERIFIER = fn


def verify(message: str, timeout: float) -> str:
    """Ask the owner to confirm with Windows Hello. One of OUTCOMES. Never
    raises. Off Windows there is no Windows Hello: "unavailable"."""
    fn = _VERIFIER
    if fn is None:
        fn = _verify_windows if sys.platform == "win32" else (lambda _m, _t: UNAVAILABLE)
    try:
        out = fn(message, timeout)
    except Exception:
        return FAILED_
    return out if out in OUTCOMES else FAILED_


def _child_env() -> dict:
    try:
        import jarvis_child_env
        return dict(jarvis_child_env.inherited())
    except Exception:
        keep = ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "USERPROFILE",
                "LOCALAPPDATA", "APPDATA")
        return {k: v for k, v in os.environ.items() if k.upper() in keep}


#: How the Windows Hello child process is started. A name of its own so a test
#: can stand a FAKE child in its place: the real one raises a real prompt, and
#: no test may do that.
_SPAWN = subprocess.Popen


def _verify_windows(message: str, timeout: float) -> str:
    """Runs the check in a child process (this file, `--hello`). A mistake in
    the Windows calls can then end only the child - read as "failed", so the
    approval is refused - never the backend. The message goes in on stdin,
    never on a command line other programs can list.

    The child's stdin STAYS OPEN while it works: the JSON line tells it what
    to ask, and a later "cancel" line - or this end of the pipe closing - tells
    it to close the prompt. That is the cancellation the backend controls; the
    child's death is not one (the 2026-10-26 measurement found the Windows
    dialog survives the process that asked for it). A timeout asks the child
    to cancel, gives it a moment, and only then kills it.

    The prompt is tagged with the token of the approval raising it
    (`_prompt_token`), so its watcher can cancel this prompt and no other.
    """
    # THE PROMPT'S LIFETIME IS CAPPED HERE TOO (2026-10-26 review). The caller
    # already passes at most `_PROMPT_MAX` and the child clamps what it is
    # given; this is the third place, so no future caller can hand Windows a
    # longer dialog than the documented bound.
    try:
        seconds = min(max(1.0, float(timeout)), _PROMPT_MAX)
    except (TypeError, ValueError, OverflowError):
        seconds = _PROMPT_MAX
    try:
        proc = _SPAWN(
            [sys.executable, "-I", str(Path(__file__).resolve()), "--hello"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, env=_child_env(),
            # CREATE_NO_WINDOW: no console flashes up. The check's own small
            # window, and Windows Hello's prompt, are not affected.
            creationflags=0x08000000,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return FAILED_
    live = _LivePrompt(proc, token=_prompt_token())
    with _LIVE_LOCK:
        _LIVE_PROMPTS.add(live)
    try:
        if not live.say({"message": message, "timeout": seconds}):
            return FAILED_
        try:
            proc.wait(timeout=seconds + 10.0)
        except subprocess.TimeoutExpired:
            live.cancel()               # a kill cannot close the prompt
            try:
                proc.wait(timeout=2.0)
            except (subprocess.TimeoutExpired, OSError, ValueError):
                try:
                    proc.kill()
                except OSError:
                    pass
            return FAILED_
        except (OSError, ValueError):
            return FAILED_
        try:
            out = proc.stdout.read() if proc.stdout is not None else ""
        except (OSError, ValueError):
            out = ""
        return parse_child_answer(proc.returncode, out)
    finally:
        with _LIVE_LOCK:
            _LIVE_PROMPTS.discard(live)
        live.close()


def parse_child_answer(returncode: int, stdout: str) -> str:
    """The child's last line, {"outcome": ...}. Anything else is "failed"."""
    if returncode != 0:
        return FAILED_
    for line in reversed((stdout or "").strip().splitlines()):
        try:
            got = json.loads(line).get("outcome")
        except (ValueError, AttributeError):
            continue
        return got if got in OUTCOMES else FAILED_
    return FAILED_


# The meanings of Windows' own numbers - lock/rules.rs before_prompt and
# after_prompt, the same table. "again" means try once more.


def before_prompt(availability: int) -> Optional[str]:
    """UserConsentVerifierAvailability. None: show the prompt."""
    if availability == 0:
        return None
    if availability in (1, 2, 3):   # DeviceNotPresent, NotConfiguredForUser, DisabledByPolicy
        return UNAVAILABLE
    return "again"                   # DeviceBusy, or unknown


def after_prompt(result: int) -> str:
    """UserConsentVerificationResult."""
    if result == 0:
        return CONFIRMED
    if result in (1, 2, 3):
        return UNAVAILABLE
    if result in (5, 6):             # RetriesExhausted, Canceled
        return CANCELLED_
    return "again"                   # DeviceBusy, or unknown


def winrt_iid(signature: str) -> uuid.UUID:
    """The interface id Windows gives a generic interface such as
    IAsyncOperation<UserConsentVerificationResult>: a version-5 UUID from a
    SHA-1 over a fixed prefix and the type's signature - `GUID::from_signature`
    in the Rust `windows-core` crate, ported line for line."""
    prefix = bytes([0x11, 0xf4, 0x7a, 0xd5, 0x7b, 0x73, 0x42, 0xc0,
                    0xab, 0xae, 0x87, 0x8b, 0x1e, 0x16, 0xad, 0xee])
    b = bytearray(hashlib.sha1(prefix + signature.encode("utf-8")).digest()[:16])
    b[6] = (b[6] & 0x0F) | 0x50
    b[8] = (b[8] & 0x3F) | 0x80
    return uuid.UUID(bytes=bytes(b))


_ASYNC_OP = "{9fc2b0bb-e446-44e2-aa61-9cab8f636af2}"
IID_ASYNC_RESULT = winrt_iid(
    f"pinterface({_ASYNC_OP};enum(Windows.Security.Credentials.UI.UserConsentVerificationResult;i4))")
IID_STATICS = uuid.UUID("af4f3f91-564c-4ddc-b8b5-973447627c65")   # IUserConsentVerifierStatics
IID_INTEROP = uuid.UUID("39e050c3-4e74-441a-8dc0-b81104df949c")   # IUserConsentVerifierInterop
IID_ASYNC_INFO = uuid.UUID("00000036-0000-0000-c000-000000000046")  # IAsyncInfo
CLASS_NAME = "Windows.Security.Credentials.UI.UserConsentVerifier"


class _Stopped(Exception):
    """The backend is going away, so the prompt was told to cancel: unwind."""


def _watch_for_stop(stream, stop: threading.Event) -> None:
    """Set `stop` when the parent writes "cancel" or closes its end of the pipe.

    Run in a thread in the child. The pipe is the only honest lifetime tie the
    prompt has: when the backend exits, cleanly or by its handles being
    closed, the pipe ends and this notices. A "cancel" line says the same
    thing while the backend is still alive.
    """
    try:
        for line in stream:
            if str(line).strip().lower() == "cancel":
                break
    except Exception:
        pass
    stop.set()


#: What `_wait_async` returns when the stop flag cancelled the wait.
_STOPPED = object()


def _wait_async(status_of, cancel, value_of, stop, deadline, *,
                clock=time.monotonic, tick=None):
    """Wait for one Windows async operation to finish, or cancel it.

    `status_of()` is the operation's own status: 0 started, 1 completed,
    2 cancelled, 3 error, None when it cannot be read. `cancel()` asks
    Windows to close the prompt. `value_of()` reads the finished result.
    Returns the result, None when the wait ended without one, or `_STOPPED`
    when `stop` was set - the caller turns that into "cancelled".

    Split out of `_hello_child` so the rule can be tested with no Windows and
    no prompt at all: the loop body is the part that decides, and a fake
    operation can show that `cancel` is called exactly when the flag is set
    or the deadline has passed. `tick()` runs once per pass; the real one
    dispatches Windows messages and sleeps a moment, and a test passes its own
    so it never waits.
    """
    while True:
        status = status_of()
        if status is None:
            return None
        if status != 0:                       # 0 Started
            break
        if stop is not None and stop.is_set():
            cancel()
            return _STOPPED
        if clock() > deadline:
            cancel()
            return None
        if tick is not None:
            tick()
    if status != 1:                           # 1 Completed; 2 Canceled, 3 Error
        return None
    return value_of()


def _hello_ask(line: str) -> tuple:
    """The one line the `--hello` child reads first, as (message, seconds).

    Split out of the `__main__` block so the rule can be tested with no
    process and no prompt. An EMPTY line is not `{}`: the old code read it as
    a request with no timeout, and the 900 s default then let a child that had
    been asked nothing raise a quarter-hour dialog - the one path with no card
    at all, and exactly the lifetime this module exists to bound (2026-10-26
    review). It raises instead, and the caller answers "failed" before it ever
    gets near Windows.

    The seconds are clamped to `_PROMPT_MAX` HERE, in the child, because the
    dialog's lifetime is decided here: the child must not depend on the parent
    having done its arithmetic.
    """
    text = str(line or "").strip()
    if not text:
        raise ValueError("--hello: no question on stdin")
    ask = json.loads(text)
    if not isinstance(ask, dict):
        raise ValueError("--hello: the question is not an object")
    try:
        asked = float(ask.get("timeout") or DEFAULT_TIME_LEFT)
    except (TypeError, ValueError, OverflowError):
        asked = DEFAULT_TIME_LEFT
    seconds = min(max(1.0, asked), _PROMPT_MAX)
    return str(ask.get("message") or "Approve a Jarvis action"), seconds


def _hello_child(message: str, timeout: float,
                 should_stop: Optional[threading.Event] = None) -> str:  # pragma: no cover - Windows only
    """The check itself, in the child process. Windows only.

    The desktop's lock.rs `hello::verify`, in Python: availability first,
    then the prompt over a small window of this process's own (a desktop
    program "should" pass one - the backend has none, so it makes one),
    falling back to the plain prompt if Windows refuses that form. At most
    two tries, and only for temporary failures: a dismissed prompt is an
    answer and is never asked again.

    `should_stop` is the backend's cancellation: when it is set the prompt is
    cancelled and the answer is "cancelled", rather than waiting out the
    deadline. `_watch_for_stop` is what sets it.
    """
    import ctypes
    from ctypes import wintypes

    combase = ctypes.WinDLL("combase")
    user32 = ctypes.WinDLL("user32")
    kernel32 = ctypes.WinDLL("kernel32")
    vp = ctypes.c_void_p

    class GUID(ctypes.Structure):
        _fields_ = [("d1", ctypes.c_uint32), ("d2", ctypes.c_uint16),
                    ("d3", ctypes.c_uint16), ("d4", ctypes.c_ubyte * 8)]

    def guid(u: uuid.UUID) -> GUID:
        return GUID.from_buffer_copy(u.bytes_le)

    combase.RoInitialize.argtypes = [ctypes.c_int]
    combase.RoInitialize.restype = ctypes.c_long
    combase.WindowsCreateString.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.POINTER(vp)]
    combase.WindowsCreateString.restype = ctypes.c_long
    combase.WindowsDeleteString.argtypes = [vp]
    combase.WindowsDeleteString.restype = ctypes.c_long
    combase.RoGetActivationFactory.argtypes = [vp, ctypes.POINTER(GUID), ctypes.POINTER(vp)]
    combase.RoGetActivationFactory.restype = ctypes.c_long
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, vp, vp, vp, vp]
    user32.CreateWindowExW.restype = vp
    user32.DestroyWindow.argtypes = [vp]
    user32.SetForegroundWindow.argtypes = [vp]
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), vp, ctypes.c_uint,
                                    ctypes.c_uint, ctypes.c_uint]
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = vp

    def method(ptr: vp, index: int, *argtypes):
        table = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(vp))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, vp, *argtypes)(table[index])

    def release(ptr: vp) -> None:
        if ptr:
            method(ptr, 2)(ptr)

    def hstring(text: str) -> vp:
        h = vp()
        units = len(text.encode("utf-16-le")) // 2
        if combase.WindowsCreateString(text, units, ctypes.byref(h)) < 0:
            raise OSError("WindowsCreateString failed")
        return h

    def pump() -> None:
        msg = wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):  # PM_REMOVE
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def wait(op: vp, deadline: float) -> Optional[int]:
        """The result of an IAsyncOperation of a 4-byte enum, or None."""
        info = vp()
        iid = guid(IID_ASYNC_INFO)
        if method(op, 0, ctypes.POINTER(GUID), ctypes.POINTER(vp))(op, ctypes.byref(iid), ctypes.byref(info)) < 0:
            return None
        status = ctypes.c_int(0)

        def status_of() -> Optional[int]:
            if method(info, 7, ctypes.POINTER(ctypes.c_int))(info, ctypes.byref(status)) < 0:
                return None
            return status.value

        def cancel() -> None:
            method(info, 9)(info)            # Cancel: the prompt closes

        def value_of() -> Optional[int]:
            value = ctypes.c_int32(0)
            if method(op, 8, ctypes.POINTER(ctypes.c_int32))(op, ctypes.byref(value)) < 0:
                return None
            return value.value

        def tick() -> None:
            pump()
            time.sleep(0.05)

        try:
            got = _wait_async(status_of, cancel, value_of, should_stop, deadline, tick=tick)
            if got is _STOPPED:
                raise _Stopped()
            return got
        finally:
            release(info)

    deadline = time.monotonic() + max(1.0, float(timeout))
    combase.RoInitialize(1)                        # RO_INIT_MULTITHREADED; "already" is fine
    cls = hstring(CLASS_NAME)
    text = hstring(message)
    statics, interop, hwnd = vp(), vp(), None
    try:
        iid = guid(IID_STATICS)
        if combase.RoGetActivationFactory(cls, ctypes.byref(iid), ctypes.byref(statics)) < 0:
            return FAILED_
        iid_i = guid(IID_INTEROP)
        if combase.RoGetActivationFactory(cls, ctypes.byref(iid_i), ctypes.byref(interop)) < 0:
            interop = vp()
        # A 1x1 window at the middle of the main screen, on top, not on the
        # taskbar: something for the prompt to belong to, so it comes up in
        # front rather than behind. The desktop app lets it come to the front
        # (AllowSetForegroundWindow) just before it sends the approval.
        x = user32.GetSystemMetrics(0) // 2
        y = user32.GetSystemMetrics(1) // 2
        hwnd = user32.CreateWindowExW(0x00000080 | 0x00000008,       # TOOLWINDOW | TOPMOST
                                      "STATIC", "Jarvis - approval check",
                                      0x80000000 | 0x10000000,        # POPUP | VISIBLE
                                      x, y, 1, 1, None, None,
                                      kernel32.GetModuleHandleW(None), None)
        if hwnd:
            user32.SetForegroundWindow(hwnd)

        for attempt in range(2):
            if attempt:
                time.sleep(0.6)
            op = vp()
            if method(statics, 6, ctypes.POINTER(vp))(statics, ctypes.byref(op)) < 0:
                continue
            try:
                avail = wait(op, deadline)
            finally:
                release(op)
            said = "again" if avail is None else before_prompt(avail)
            if said is None:
                op = vp()
                asked = -1
                if interop and hwnd:
                    riid = guid(IID_ASYNC_RESULT)
                    asked = method(interop, 6, vp, vp, ctypes.POINTER(GUID), ctypes.POINTER(vp))(
                        interop, hwnd, text, ctypes.byref(riid), ctypes.byref(op))
                if asked < 0:
                    op = vp()
                    asked = method(statics, 7, vp, ctypes.POINTER(vp))(statics, text, ctypes.byref(op))
                if asked < 0:
                    said = "again"
                else:
                    try:
                        result = wait(op, deadline)
                    finally:
                        release(op)
                    said = "again" if result is None else after_prompt(result)
            if said != "again":
                return said
            if time.monotonic() > deadline:
                break
        return FAILED_
    except _Stopped:
        return CANCELLED_
    finally:
        if hwnd:
            user32.DestroyWindow(hwnd)
        release(interop)
        release(statics)
        combase.WindowsDeleteString(text)
        combase.WindowsDeleteString(cls)


# ---------------------------------------------------------------------------
# POST /api/approve
# ---------------------------------------------------------------------------


def _no_deadline(row: dict) -> bool:
    """True only when the GATE says this action's card has no deadline.

    Asked of jarvis_gate rather than read off the row, because an absent
    `expires_in` means two different things: a gate too old to send the field
    (those cards DO expire, and DEFAULT_TIME_LEFT is the honest answer) and a
    deliberate card the gate left the field off on purpose
    (jarvis_gate.APPROVAL_NEVER_EXPIRES). Only the module that made the
    decision can tell them apart. A backend without `timeout_for` - one older
    than this change - gets False and exactly today's behaviour.
    """
    try:
        import jarvis_gate
        ask = getattr(jarvis_gate, "timeout_for", None)
        if callable(ask):
            return ask(row.get("action")) is None
    except Exception:
        pass
    return False


def _time_left(row: dict) -> Optional[float]:
    """Seconds the card still has, or None when it has no deadline at all.

    None is not a very large number. The gate leaves `expires_in` off a
    deliberate card on purpose (jarvis_gate.APPROVAL_NEVER_EXPIRES): pairing a
    phone, registering its approval key and restoring a backup wait for the
    owner rather than lapsing. A caller that treated None as "0 seconds left"
    would refuse exactly those cards, and one that treated it as a number of
    seconds would invent a deadline the gate does not have - so both branches
    below test it explicitly.
    """
    # THE ROW'S OWN NUMBER WINS when it has one: if the gate sent
    # `expires_in`, that is this card's deadline, and 0 or a negative number
    # means it has run out - even for an action on the exempt list, so an old
    # or foreign row cannot outlive the window it carries. Only when the field
    # is ABSENT (or an explicit null) does the action itself decide, and that
    # question goes to the gate, because absence means two things: a gate too
    # old to send the field (those cards DO expire) and a deliberate card the
    # gate left it off on purpose.
    if "expires_in" in row and row.get("expires_in") is not None:
        try:
            left = float(row.get("expires_in"))
        except (TypeError, ValueError):
            return DEFAULT_TIME_LEFT
        return left if left == left else DEFAULT_TIME_LEFT   # NaN
    return None if _no_deadline(row) else DEFAULT_TIME_LEFT


def _find(rows, request_id) -> Optional[dict]:
    want = str(request_id).strip()
    for r in rows or ():
        if isinstance(r, dict) and str(r.get("id")).strip() == want:
            return r
    return None


def _pending_rows() -> list:
    import jarvis_gate
    return list(jarvis_gate.pending())


class _PromptWatch:
    """Watches one card while its prompt is open, and closes the prompt when
    the card stops waiting (2026-10-26 review).

    Before this, the dialog's only bound was the number of seconds chosen
    before it opened: let the card be denied, withdrawn or expire while the
    prompt was up, and the dialog stayed for the rest of that number - up to
    three minutes. The prompt is the child process's, and
    `_cancel_prompts_for` is what asks THIS one to close, so the watcher is a
    poll of the card plus that same cancel.

    Run in a thread from `approve_check`, which holds `_PROMPT` for as long as
    its prompt is up. Asking every live prompt to close would be safe while
    that lock is held - but `stop()` joins for only two seconds, and a queue
    read can outlive it. The lock is then released and the NEXT card's prompt
    can be live when the stale watcher's read finally returns, so the watcher
    is given its own approval's cancel (`cancel`, token-matched) and can never
    close another card's prompt (2026-10-26 review). A prompt that is already
    over when the watcher looks is harmless: the token matches nothing left in
    `_LIVE_PROMPTS`.

    It cancels on what the QUEUE says, never on a read that failed: a locked
    database must not close a prompt the owner is looking at, and a watcher
    bug must not close every prompt. Either way nothing can be approved
    without the read that follows the prompt (`approve_check` answers 503 or
    409 on it), so a queue this module cannot read still fails closed.
    """

    def __init__(self, pending, request_id, interval: float = _WATCH_INTERVAL,
                 cancel: Optional[Callable[[], int]] = None):
        self.pending = pending
        self.request_id = request_id
        self.interval = interval
        #: What closes the prompt this watcher owns. Default is the
        #: shutdown-wide cancel; `approve_check` passes the token-scoped one.
        self.cancel = cancel or _cancel_live_prompts
        self.done = threading.Event()      # the prompt is over
        self.gone = threading.Event()      # the card stopped waiting
        self.reads = 0
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="jarvis-prompt-watch")

    def start(self) -> "_PromptWatch":
        self._thread.start()
        return self

    def stop(self) -> None:
        """The prompt is over. Never leaves a thread behind that matters: the
        poll is a daemon, and a queue read that hangs is why the join is
        bounded. A thread that never started is not joined (that would raise),
        which keeps the call safe from any `start()` failure."""
        self.done.set()
        if self._thread.ident is not None:
            self._thread.join(timeout=2.0)

    def _still_waiting(self) -> bool:
        """True unless the card has definitely stopped waiting.

        A queue that cannot be read is NOT "gone": the prompt then ends at its
        own deadline, as it did before this watcher existed, and the read after
        it answers 503 - so nothing is approved either way.
        """
        try:
            row = _find(self.pending(), self.request_id)
        except Exception:
            return True
        left = _time_left(row) if row is not None else None
        return row is not None and (left is None or left > 0)

    def _run(self) -> None:
        while not self.done.wait(self.interval):
            self.reads += 1
            if not self._still_waiting():
                self.gone.set()
            if self.gone.is_set():
                # Every pass, not once: the first look can beat the child
                # process into _LIVE_PROMPTS, and the next still finds it.
                self.cancel()


def _signed_check(body, row, device) -> Optional[tuple]:
    """Phase 2 (docs/PAIRING-DESIGN.md 11.4): a RISKY card approved from
    another device with a DEVICE key must carry a valid signature from that
    device's approval key. `device` is who the request's own key said it
    was: "pc", "shared" (the old shared key - allowed as today, until it is
    retired), a device id, or None (jarvis_devices is not running - nothing
    to check, today's behaviour)."""
    if not isinstance(device, str) or device in ("", "pc", "shared"):
        return None
    try:
        import jarvis_devices
        return jarvis_devices.check_signed_approval(body, row, device)
    except Exception:
        return 503, {"ok": False, "owner_check": "cannot_check",
                     "error": ("This PC could not check the fingerprint or PIN signature "
                               "just now, so nothing was approved.")}


def approve_check(body, *, peer, local=None, pending: Callable[[], list] = None,
                  own=None, device=None) -> Optional[tuple]:
    """What must happen before the owner's own /api/approve handler records
    an approval. None: go ahead (the approval is stamped). Otherwise
    (http_status, body) to answer instead, and nothing is approved.

    - A card this backend cannot find is passed on unstamped: the owner's
      handler answers it (409, "no longer waiting"), and the gate is not
      waiting for it.
    - A risky card from THIS PC waits for Windows Hello, one prompt at a
      time. No Windows Hello: refused (NOT_SET_UP). Afterwards the queue is
      read again, and a card that stopped waiting meanwhile - it ran out of
      time, or was denied - is refused (409).
    - Anything else (not risky, or from another device, which checks its
      own) is stamped straight away.
    - Except a card in PC_ONLY_ACTIONS (loosening "What asks first",
      2026-09-26): refused from another device, and always Windows Hello
      from this PC, risky or not.
    - A risky card from another device, made with a DEVICE key (`device`,
      set by jarvis_devices' key check): needs that device's signature
      (`_signed_check`). A phone with no approval key yet is refused with
      "no_approval_key", so it can offer to turn signed approvals on.
    """
    pending = pending or _pending_rows
    request_id = body.get("id") if isinstance(body, dict) else None
    if request_id is None or str(request_id).strip() == "":
        return None
    try:
        row = _find(pending(), request_id)
    except Exception:
        return 503, {"ok": False, "error": QUEUE_UNREADABLE, "owner_check": "unreadable"}
    if row is None:
        return None
    action = row.get("action")
    here = from_this_pc(peer, local, own)
    if action in PC_ONLY_ACTIONS and not here:
        # Approved on the PC only, with Windows Hello (PC_ONLY_ACTIONS).
        return 403, {"ok": False, "error": PC_ONLY, "owner_check": "pc_only"}
    if not here and is_risky(row):
        refused = _signed_check(body, row, device)
        if refused is not None:
            return refused
    if (is_risky(row) or action in PC_ONLY_ACTIONS) and here:
        # A prompt may only ask about something Jarvis can NAME. An action with
        # no written words gets a title made up from its own name
        # (`jarvis_card_words.FALLBACK`), which reads fine but describes
        # nothing - so the owner would be asked to confirm a blank. Refused
        # here, before any prompt is shown (2026-10-26). Fail closed: if the
        # words module cannot be read, no card can prove it has written words.
        if not has_written_title(action):
            return 403, {"ok": False, "error": UNLABELLED, "owner_check": "unlabelled"}
        left = _time_left(row)
        # `left` is None for a card with no deadline at all (jarvis_gate.
        # APPROVAL_NEVER_EXPIRES). Such a card has no moment to be late for,
        # so the check below does not apply to it; what still applies is the
        # re-read after Windows Hello, further down, because that is the one
        # that says this is still the live card.
        if left is not None and left <= 0:
            return 409, {"ok": False, "error": GONE, "owner_check": "gone"}
        # THE WAIT FOR THE PROMPT IS BOUNDED (2026-10-26 review). It used to be
        # `acquire(-1)` - for ever - so one child that never answered held every
        # later approval until the backend was restarted. A card WITH a deadline
        # can never be prompted after it, so its own number is the whole useful
        # wait; a card with no deadline waits the worst legitimate hold of the
        # prompt in front, `_PROMPT_WAIT_MAX` (`_wait_for_prompt`). The cap is
        # `_PROMPT_WAIT_MAX`, NOT `_PROMPT_MAX`: the prompt in front can spend
        # its 180 s and then hold this lock for about 14 more (ten for its
        # child's answer, two for the cancel, two for the watcher's `stop()`),
        # so a wait capped at `_PROMPT_MAX` was up to about 14 s short and
        # refused a card just as its turn arrived (2026-10-26 review).
        if not _PROMPT.acquire(timeout=_wait_for_prompt(left)):
            return 409, {"ok": False, "error": GONE, "owner_check": "gone"}
        try:
            # THE WAIT FOR THE PROMPT CAN BE LONGER THAN THE CARD HAS LEFT.
            # `left` above was read before that wait, and another prompt may
            # have held this one for minutes. So the card is read AGAIN now
            # that the prompt is ours, and the number that counts is the one
            # from this second read: a prompt that opens as its card expires,
            # or after it has, is the measured defect this closes (2026-10-26,
            # .dsh-scratch/WINDOWS-HELLO-2026-10-26/FINDINGS.md section 3).
            try:
                live = _find(pending(), request_id)
            except Exception:
                return 503, {"ok": False, "error": QUEUE_UNREADABLE,
                             "owner_check": "unreadable"}
            left = _time_left(live) if live is not None else None
            if live is None or (left is not None and left <= 0):
                return 409, {"ok": False, "error": GONE, "owner_check": "gone"}
            # The label was checked before the wait, on the row as it was then.
            # A same-id action can change while the prompt queues (the gate
            # raises a fresh card under the same id for some actions), and
            # this is the row whose title the prompt would name - so it is
            # this row's action that must have written words (2026-10-26
            # review).
            if not has_written_title(live.get("action")):
                return 403, {"ok": False, "error": UNLABELLED, "owner_check": "unlabelled"}
            # ...and it is this row's action the approval is stamped for: the
            # gate asks for the stamp of the card that is on screen, not of
            # the one read before the wait.
            action = live.get("action")
            # The prompt gets a concrete number of seconds either way, and it
            # is never more than the card has left or _PROMPT_MAX. That number
            # is what Windows is told, so it is the dialog's lifetime - the
            # hard-kill bound as well as the ordinary one; what the watcher
            # below adds is that a card which stops waiting closes the dialog
            # within a quarter of a second instead of being waited out. Three
            # minutes is long enough to reach the PC and confirm. A card with
            # no deadline still waits afterwards - the owner can press Approve
            # again - so this bounds the dialog, not the decision.
            left = min(left, _PROMPT_MAX) if left is not None else _PROMPT_MAX
            # THE WATCHER MAY ONLY CLOSE ITS OWN PROMPT (2026-10-26 review):
            # `stop()` joins for two seconds, and a queue read slower than that
            # outlives it - the lock is then released and the next card's
            # prompt can be the one on screen. `token` tags the live prompt
            # this call raises (`_prompt_token` is read by `_verify_windows`),
            # and `_cancel_prompts_for` matches only that token.
            token = object()
            watch = _PromptWatch(pending, request_id,
                                 cancel=lambda: _cancel_prompts_for(token))
            _CURRENT_PROMPT.token = token
            try:
                watch.start()
                outcome = verify(approval_message(live), max(1.0, left))
            finally:
                _CURRENT_PROMPT.token = None
                watch.stop()
        finally:
            _PROMPT.release()
        # The prompt was closed by the watcher, not answered by the owner: the
        # card stopped waiting under it. Answer the 409 both apps read as "no
        # longer waiting", not "the owner dismissed the prompt", which would be
        # false (2026-10-26 review).
        if watch.gone.is_set():
            return 409, {"ok": False, "error": GONE, "owner_check": "gone"}
        if outcome == UNAVAILABLE:
            return 403, {"ok": False, "error": NOT_SET_UP, "owner_check": "not_set_up"}
        if outcome == CANCELLED_:
            return 403, {"ok": False, "error": CANCELLED, "owner_check": "cancelled"}
        if outcome != CONFIRMED:
            return 403, {"ok": False, "error": FAILED, "owner_check": "failed"}
        # The prompt can stay up for a while. A card that stopped waiting
        # meanwhile is not approved - the backend's own stale-link rule.
        try:
            again = _find(pending(), request_id)
        except Exception:
            return 503, {"ok": False, "error": QUEUE_UNREADABLE, "owner_check": "unreadable"}
        # For a card with NO deadline, `expires_in <= 0` cannot happen: the
        # gate never sends the field, so there is no moment it could have
        # passed. What still holds here, and must, is the re-read itself - the
        # card has to still be THE live card. Answered elsewhere, withdrawn, or
        # replaced by a newer card of the same kind (a second /api/pair/start
        # cancels the first card): each of those takes the row out of pending
        # while the Hello prompt was up, and this is what catches it.
        left_again = _time_left(again) if again is not None else None
        if again is None or (left_again is not None and left_again <= 0):
            return 409, {"ok": False, "error": GONE, "owner_check": "gone"}
    stamp(request_id, action)
    return None


# ---------------------------------------------------------------------------
# Wiring into jarvis_hud.py's server (owner-check.patch)
# ---------------------------------------------------------------------------

_ARMED = False


def armed() -> bool:
    """True once `install` has wrapped the server. /api/version reports it
    as `capabilities.owner_check` ("backend"), so the desktop stops asking
    Windows Hello itself - the owner is asked once."""
    return _ARMED


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_POST` so POST /api/approve goes through
    `approve_check` first. Every other request, POST /api/deny included,
    goes straight to the original. Returns the banner line."""
    global _ARMED
    original = handler_cls.do_POST
    if getattr(original, "_jarvis_owner_check", False):
        _ARMED = True
        return "  approvals  risky ones from this PC ask Windows Hello (already on)"

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != "/api/approve":
            return original(self)
        # Who is asking first: a request the owner's handler would refuse
        # anyway must not raise a Windows Hello prompt.
        try:
            if not origin_ok(self) or not token_ok(self):
                return original(self)
        except Exception:
            return original(self)
        try:
            raw = read_body(self) or b""
        except Exception:
            return original(self)
        kept = self.rfile
        self.rfile = io.BytesIO(raw)       # the owner's handler reads it again
        try:
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = None
            peer = (getattr(self, "client_address", None) or ("",))[0]
            try:
                local = self.connection.getsockname()[0]
            except Exception:
                local = None
            refused = approve_check(body, peer=peer, local=local,
                                    device=getattr(self, "_jarvis_device", None))
            if refused is not None:
                code, out = refused
                return self._send(code, out)
            return original(self)
        finally:
            self.rfile = kept

    do_POST._jarvis_owner_check = True
    handler_cls.do_POST = do_POST
    _ARMED = True
    return "  approvals  risky ones from this PC ask Windows Hello; each approval is stamped"


if __name__ == "__main__":
    if "--hello" in sys.argv:
        try:
            # ONE line, not read-to-EOF: the pipe stays open after it, and a
            # later "cancel" line (or the pipe closing) is how the backend
            # says "close the prompt" - see _watch_for_stop.
            # `_hello_ask` is what that line may say: an empty one is refused
            # rather than read as "{}", and the seconds are clamped to
            # _PROMPT_MAX in the child itself (2026-10-26 review).
            message, seconds = _hello_ask(sys.stdin.readline())
            stop = threading.Event()
            threading.Thread(target=_watch_for_stop, args=(sys.stdin, stop),
                             daemon=True).start()
            said = _hello_child(message, seconds, should_stop=stop)
        except Exception:
            said = FAILED_
        print(json.dumps({"outcome": said if said in OUTCOMES else FAILED_}))
        sys.exit(0)
    print(f"  armed      {armed()}")
    print(f"  platform   {sys.platform}")
