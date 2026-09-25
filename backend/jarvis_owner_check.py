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

import hashlib
import hmac
import io
import ipaddress
import json
import os
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

#: The shipped approval_timeout_seconds, used when a row carries no
#: `expires_in` (a backend without approval-expiry.patch).
DEFAULT_TIME_LEFT = 180.0

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
    when the name lookup misses an adapter. Anything that cannot be placed
    counts as this PC, so it asks. A program on the PC cannot make its
    request come from the phone's address; it would need another device.
    """
    p = _ip(peer)
    if p is None:
        return True
    if p.is_loopback or p.is_unspecified:
        return True
    lo = _ip(local)
    if lo is not None and p == lo:
        return True
    return p in (own_addresses() if own is None else frozenset(_ip(a) for a in own))


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
#: Longer than any card waits (180 s shipped), so a stamp never outlives the
#: card it was made for by much.
_STAMP_TTL = 15 * 60.0


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


def _verify_windows(message: str, timeout: float) -> str:
    """Runs the check in a child process (this file, `--hello`). A mistake in
    the Windows calls can then end only the child - read as "failed", so the
    approval is refused - never the backend. The message goes in on stdin,
    never on a command line other programs can list."""
    try:
        r = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).resolve()), "--hello"],
            input=json.dumps({"message": message, "timeout": float(timeout)}),
            capture_output=True, text=True, timeout=float(timeout) + 10.0,
            env=_child_env(),
            # CREATE_NO_WINDOW: no console flashes up. The check's own small
            # window, and Windows Hello's prompt, are not affected.
            creationflags=0x08000000,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return FAILED_
    return parse_child_answer(r.returncode, r.stdout)


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


def _hello_child(message: str, timeout: float) -> str:  # pragma: no cover - Windows only
    """The check itself, in the child process. Windows only.

    The desktop's lock.rs `hello::verify`, in Python: availability first,
    then the prompt over a small window of this process's own (a desktop
    program "should" pass one - the backend has none, so it makes one),
    falling back to the plain prompt if Windows refuses that form. At most
    two tries, and only for temporary failures: a dismissed prompt is an
    answer and is never asked again.
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
        try:
            status = ctypes.c_int(0)
            while True:
                if method(info, 7, ctypes.POINTER(ctypes.c_int))(info, ctypes.byref(status)) < 0:
                    return None
                if status.value != 0:            # 0 Started
                    break
                if time.monotonic() > deadline:
                    method(info, 9)(info)        # Cancel: the prompt closes
                    return None
                pump()
                time.sleep(0.05)
            if status.value != 1:                # 1 Completed; 2 Canceled, 3 Error
                return None
            value = ctypes.c_int32(0)
            if method(op, 8, ctypes.POINTER(ctypes.c_int32))(op, ctypes.byref(value)) < 0:
                return None
            return value.value
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


def _time_left(row: dict) -> float:
    try:
        left = float(row.get("expires_in"))
    except (TypeError, ValueError):
        return DEFAULT_TIME_LEFT
    return left if left == left else DEFAULT_TIME_LEFT   # NaN


def _find(rows, request_id) -> Optional[dict]:
    want = str(request_id).strip()
    for r in rows or ():
        if isinstance(r, dict) and str(r.get("id")).strip() == want:
            return r
    return None


def _pending_rows() -> list:
    import jarvis_gate
    return list(jarvis_gate.pending())


def approve_check(body, *, peer, local=None, pending: Callable[[], list] = None,
                  own=None) -> Optional[tuple]:
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
    if is_risky(row) and from_this_pc(peer, local, own):
        left = _time_left(row)
        if left <= 0:
            return 409, {"ok": False, "error": GONE, "owner_check": "gone"}
        if not _PROMPT.acquire(timeout=left):
            return 409, {"ok": False, "error": GONE, "owner_check": "gone"}
        try:
            outcome = verify(approval_message(row), max(1.0, _time_left(row)))
        finally:
            _PROMPT.release()
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
        if again is None or ("expires_in" in again and _time_left(again) <= 0):
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
            refused = approve_check(body, peer=peer, local=local)
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
            ask = json.loads(sys.stdin.read() or "{}")
            said = _hello_child(str(ask.get("message") or "Approve a Jarvis action"),
                                float(ask.get("timeout") or DEFAULT_TIME_LEFT))
        except Exception:
            said = FAILED_
        print(json.dumps({"outcome": said if said in OUTCOMES else FAILED_}))
        sys.exit(0)
    print(f"  armed      {armed()}")
    print(f"  platform   {sys.platform}")
