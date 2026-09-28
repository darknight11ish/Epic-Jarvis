"""jarvis_handoff.py - "Solve it here": a captcha or sign-in page handed to the
owner's phone.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside
jarvis_chatbot_routes.py, which answers its routes; no patch). The owner's
decision (CLAUDE.md, 2026-09-28, "A captcha can be handed to the owner's
phone"): when a chatbot website or a customer-support chat pauses at a
captcha, a sign-in page or an "unusual activity" page, the phone gets an
alert and offers "Solve it here" - a live picture of THAT ONE browser window
only, sent PC to phone over Tailscale/Meshnet, never saved, and the owner's
taps and typing passed to that window only while Jarvis is paused there.
Solving it on the PC still works. Jarvis itself never solves a captcha.

IN PLAIN WORDS, WHAT HAPPENS
  * A conversation (jarvis_chatbot.py) or a support chat (jarvis_support.py)
    pauses with the code "captcha", "login" or "unusual" - its adapter saw
    that page and stopped (jarvis_chatbot_web.py). Its browser window stays
    open on the PC, exactly as before. offer() says so; both apps read it on
    GET /api/chatbot/status (`handoff`), and the phone raises an alert that
    names the site and the reason only.
  * The owner taps "Solve it here". start() opens a hand-off for THAT paused
    session only - no card: nothing leaves the owner's own devices, and
    nothing is done but what the owner does. The hosts the window may show
    during the hand-off are fixed now: the site's own, its sign-in hosts,
    and the one the window shows at this moment.
  * frame() takes ONE picture of that window's page (Playwright's own
    screenshot of that one page - never the screen, never another window or
    tab) as a small JPEG, hands it back in the answer and keeps nothing: not
    on disk, not in memory after the answer. At most FRAMES_PER_S a second.
  * input() passes ONE tap, a few typed characters, one key from a short
    list or one scroll to that page - the owner's own input, nothing else.
    Jarvis adds nothing, clicks nothing by itself and reads nothing it types.
  * EVERY picture and every input first checks, again, that the session is
    STILL paused at that same page's code with the same window, and that the
    window still shows one of the fixed hosts. When any of that stops being
    true the hand-off ends at once and says why: the owner pressed Resume or
    Stop, the window went to another site ("left"), the window closed, Stop
    everything, nobody asked for a picture for IDLE_S (the phone left the
    screen), or MOST_S passed.

WHAT IT NEVER DOES
  * Solve, skip, click or type anything by itself. There is no code here that
    decides where to tap: the only coordinates it uses are the phone's.
  * Picture or touch any page but the paused session's own - not the chatbot
    websites' other windows, not a support widget's other frames on their
    own, not the desktop, not another tab the site opened (the owner uses
    the PC for that).
  * Keep a picture, or log a typed character: the audit line carries counts
    and the key's name for special keys, never text.
  * Run while nothing is paused at an owner page. No route answers a picture
    or passes an input otherwise (test_handoff.py checks that, in code and in
    behaviour).
  * Hide anything from the site: it is the same visible window, driven the
    same open way. No stealth plug-in, no change to how the browser presents
    itself, no script injected into the page, no captcha solving. A tap
    passed on this way reaches the page as Playwright's own mouse event;
    some captchas can tell, and refuse it - the apps say so, and offer
    "Solve it on the PC instead".

THE PHONE'S SIDE (docs/JARVIS-API.md section 60.8): pictures are asked for
only while the "Solve it here" screen is on screen, and never while App lock
has the app locked; input is held on a stale link (rule 4), and ending never
is. The desktop shows the same alert and points at the window on the PC.

Standard library only. No I/O at import.
"""
from __future__ import annotations

import base64
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

#: The pause codes a hand-off may start from: a page only the owner may get
#: past. Nothing else - "the agent asked if it is a bot", an identity check,
#: an unrecognised page - is ever handed on this way.
OWNER_CODES = ("captcha", "login", "unusual")
#: At most this many pictures a second (the phone asks about once a second).
FRAMES_PER_S = 2.0
#: JPEG quality: small enough for a phone link, clear enough to read a
#: captcha's picture grid.
JPEG_QUALITY = 60
#: No picture asked for this long: the phone left the screen - it ends.
IDLE_S = 45.0
#: However it goes, a hand-off ends after this long.
MOST_S = 15 * 60.0
#: Typed characters in one input.
TEXT_MOST = 200
#: One scroll, in page pixels, either way.
SCROLL_MOST = 1500
#: At most this many inputs in any INPUT_WINDOW_S seconds (a fast typist
#: tapping keys one by one stays well under it).
INPUTS_MOST = 30
INPUT_WINDOW_S = 3.0
#: The keys the phone may send by name. Nothing that reaches the browser
#: itself (no F-keys, no Ctrl shortcuts, no address bar).
KEYS = ("Enter", "Backspace", "Delete", "Tab", "Escape", "Space", "ArrowUp", "ArrowDown",
        "ArrowLeft", "ArrowRight")
#: A hand-off id.
_HID_PREFIX = "ho_"
#: Stop everything's name for this feature.
STOPPER = "handoff"
MODULE = "jarvis_handoff"

#: Why a hand-off ended, in whole sentences both apps show.
ENDED = {
    "owner": "You ended it.",
    "resumed": "The page is no longer waiting for you - the conversation carried on or was "
               "resumed.",
    "stopped": "The conversation stopped.",
    "left": "The window went to another site, so the hand-off ended. Nothing more is passed "
            "on - look at the window on the PC.",
    "closed": "The browser window closed.",
    "idle": "Nobody was looking at the picture for a while, so the hand-off ended.",
    "time": "The hand-off ended after 15 minutes.",
    "stop_all": "Stop everything ended it.",
    "replaced": "A new hand-off started.",
}

#: The sentences both apps show for this feature, word for word
#: (tools/gen_handoff_cases.py writes them into both apps' contract file).
WORDS = {
    "title": "Solve it here",
    "alert_title": "{site} needs you",
    "alert_locked": "A website Jarvis is using needs you",
    "alert_text": "Jarvis paused: {reason}. Solve it here, or in the window on the PC.",
    "reason_captcha": "a captcha (a \"prove you are a person\" check)",
    "reason_login": "a sign-in page",
    "reason_unusual": "an \"unusual activity\" page",
    "here_button": "Solve it here",
    "pc_button": "Solve it on the PC instead",
    "detail": ("A live picture of that one browser window on your PC, sent only to this "
               "phone and never saved. Your taps and typing go to that window only, and "
               "only while Jarvis is paused there. Jarvis never solves it for you."),
    "may_refuse": ("Some captchas refuse taps passed on from a phone this way. If it keeps "
                   "saying no, solve it on the PC instead."),
    "then_resume": "When it is done, press Resume. Resume asks with a card, as always.",
    "type_label": "Type into the page",
    "type_send": "Type it",
    "keys_label": "Keys",
    "scroll_up": "Scroll up",
    "scroll_down": "Scroll down",
    "end": "End",
    "held_stale": ("The link to your PC is catching up, so your taps and typing are held "
                   "until it is back."),
    "locked": "Unlock Jarvis to see the page.",
    "waiting": "Getting the picture...",
    "pc_title": "{site} needs you on this PC",
    "pc_text": ("Jarvis paused: {reason}. Deal with it in the browser window, then press "
                "Resume. Your phone can do it too (Solve it here)."),
    "new_window": ("If the site opens a new window or tab, finish there on the PC - only the "
                   "first window is passed on."),
}


def reason_words(code: str) -> str:
    return WORDS.get(f"reason_{code}", WORDS["reason_captcha"])


@dataclass
class Handoff:
    id: str
    kind: str                 # "chatbot" or "support"
    target: str               # the session's / support chat's id
    site: str                 # its name, for the words
    reason: str               # one of OWNER_CODES
    hosts: tuple              # the only hosts the window may show meanwhile
    started: float
    last_ask: float
    adapter: object = field(default=None, repr=False, compare=False)
    last_frame: float = -1e18
    width: int = 0            # the last picture's size, in page pixels
    height: int = 0
    frames: int = 0
    inputs: int = 0
    recent: list = field(default_factory=list)
    ended: str = ""


_LOCK = threading.RLock()
_CURRENT: Optional[Handoff] = None
#: The last hand-off that ended, for the apps to say why (id -> why). Small.
_ENDED: dict = {}
_clock: Callable[[], float] = time.monotonic


def _audit(event: str, detail: dict) -> None:
    """Counts and fixed words only - never a picture, never typed text."""
    try:
        import jarvis_framework as fw
        fw.audit_log("chatbot.handoff", {"event": event, **detail})
    except Exception:
        pass


# ============================================================================
#   What is paused at an owner page
# ============================================================================

def _is_window(adapter) -> bool:
    """A browser window this module can picture: a jarvis_chatbot_web
    adapter (or the support widget built on it) with its page open. An API
    service or a second local AI has no window, and is never offered."""
    return adapter is not None and callable(getattr(adapter, "_call", None)) \
        and hasattr(adapter, "_page") and hasattr(adapter, "chat_hosts")


def _targets() -> list:
    """Every session paused at an owner page, newest last, as
    (kind, id, site name, reason, adapter). A comparison's conversations are
    never here: a chatbot at a captcha is left out of a comparison, not
    paused (the owner's decision of 2026-09-28)."""
    out = []
    try:
        import jarvis_chatbot as CB
        with CB._LOCK:
            rows = list(CB._SESSIONS.values())
        for s in rows:
            if s.state == "paused" and s.paused_code in OWNER_CODES and not s.compare \
                    and _is_window(s.adapter):
                out.append(("chatbot", s.id, CB._name(s), s.paused_code, s.adapter))
    except Exception:
        pass
    try:
        import jarvis_support as SUP
        with SUP._LOCK:
            rows = list(SUP._CHATS.values())
        for c in rows:
            if c.state == "paused" and c.paused_code in OWNER_CODES and _is_window(c.widget):
                out.append(("support", c.id, c.company_name or c.company, c.paused_code,
                            c.widget))
    except Exception:
        pass
    return out


def _target(kind: str, target: str):
    for row in _targets():
        if row[0] == kind and row[1] == target:
            return row
    return None


def offer() -> dict:
    """What both apps read (GET /api/chatbot/status, `handoff`): is a page
    waiting for the owner, which site and why - never a picture, never a
    word from the page. `active` is the hand-off going on now, if any."""
    _sweep()
    rows = _targets()
    with _LOCK:
        cur = _CURRENT
        active = cur.id if cur is not None and not cur.ended else ""
        last_end = dict(_ENDED)
    if not rows:
        return {"available": False, "active": "", "ended": last_end}
    kind, tid, site, reason, _a = rows[-1]
    return {"available": True, "kind": kind, "id": tid, "site": site, "reason": reason,
            "reason_words": reason_words(reason),
            "title": WORDS["alert_title"].format(site=site),
            "text": WORDS["alert_text"].format(reason=reason_words(reason)),
            "active": active if cur is not None and cur.target == tid else "",
            "ended": last_end}


# ============================================================================
#   The one hand-off
# ============================================================================

def _end(h: Handoff, why: str) -> None:
    """Called with _LOCK held."""
    global _CURRENT
    if h.ended:
        return
    h.ended = why if why in ENDED else "owner"
    h.adapter = None
    _ENDED.clear()
    _ENDED[h.id] = h.ended
    if _CURRENT is h:
        _CURRENT = None
    _audit("end", {"why": h.ended, "frames": h.frames, "inputs": h.inputs,
                   "seconds": int(max(0.0, _clock() - h.started))})


def _sweep() -> None:
    """Ends a hand-off whose session is no longer paused at that page, or
    that nobody has looked at for IDLE_S, or that passed MOST_S."""
    with _LOCK:
        h = _CURRENT
    if h is None:
        return
    why = _why_not(h)
    if why:
        with _LOCK:
            _end(h, why)


def _why_not(h: Handoff) -> str:
    """"" while the hand-off may go on; else why it ends."""
    now = _clock()
    if h.ended:
        return h.ended
    if now - h.started >= MOST_S:
        return "time"
    if now - h.last_ask >= IDLE_S:
        return "idle"
    row = _target(h.kind, h.target)
    if row is None:
        return _gone_why(h)
    if row[4] is not h.adapter or row[3] != h.reason:
        return "resumed"
    return ""


def _gone_why(h: Handoff) -> str:
    try:
        if h.kind == "chatbot":
            import jarvis_chatbot as CB
            s = CB.get(h.target)
            state = s.state if s is not None else "stopped"
        else:
            import jarvis_support as SUP
            c = SUP.get(h.target)
            state = c.state if c is not None else "stopped"
    except Exception:
        state = "stopped"
    return "resumed" if state in ("running", "asking", "approved", "paused") else "stopped"


def _hosts_here(adapter) -> tuple:
    hosts = []
    for h in tuple(getattr(adapter, "chat_hosts", ()) or ()) \
            + tuple(getattr(adapter, "sign_in_hosts", ()) or ()):
        h = str(h or "").lower().rstrip(".")
        if h and h not in hosts:
            hosts.append(h)
    return tuple(hosts)


def _host_of(url: str) -> str:
    import jarvis_chatbot_web as W
    return W.host_path(url)[0]


def _page_host(adapter) -> str:
    """The host the window shows now. Runs on the window's own thread."""
    return adapter._call(lambda: _host_of(adapter._page.url) if adapter._page_alive() else "",
                         20)


def start(kind, target) -> tuple:
    """"Solve it here" was tapped. (http code, body). No card: nothing leaves
    the owner's own devices and nothing is done but what the owner does."""
    global _CURRENT
    kind, target = str(kind or ""), str(target or "")
    row = _target(kind, target)
    if row is None:
        return 409, {"ok": False, "error": "Nothing is waiting for you on a website right now."}
    _k, _t, site, reason, adapter = row
    try:
        now_host = _page_host(adapter)
    except Exception:
        now_host = ""
    if not now_host:
        return 409, {"ok": False, "error": ENDED["closed"]}
    hosts = _hosts_here(adapter)
    if now_host not in hosts:
        hosts = hosts + (now_host,)
    t = _clock()
    h = Handoff(id=_HID_PREFIX + secrets.token_hex(8), kind=kind, target=target, site=site,
                reason=reason, hosts=hosts, started=t, last_ask=t, adapter=adapter)
    with _LOCK:
        if _CURRENT is not None:
            _end(_CURRENT, "replaced")
        _CURRENT = h
        _ENDED.clear()
    _audit("start", {"kind": kind, "reason": reason, "hosts": len(hosts)})
    return 200, {"ok": True, "handoff": h.id, "site": site, "reason": reason,
                 "reason_words": reason_words(reason), "frames_per_s": FRAMES_PER_S,
                 "idle_s": IDLE_S}


def _mine(hid) -> tuple:
    """(handoff, None) when `hid` is the hand-off going on and it may go on;
    else (None, (code, body))."""
    hid = str(hid or "")
    with _LOCK:
        h = _CURRENT
        ended = _ENDED.get(hid, "")
    if h is None or h.id != hid:
        why = ended or "owner"
        return None, (410, {"ok": False, "ended": why, "error": ENDED.get(why, ENDED["owner"])})
    why = _why_not(h)
    if why:
        with _LOCK:
            _end(h, why)
        return None, (410, {"ok": False, "ended": why, "error": ENDED[why]})
    return h, None


def _on_window(h: Handoff, fn: Callable, timeout: float = 20.0):
    """Runs `fn(page)` on that window's own thread - after checking, there,
    that the page is alive and on one of the hand-off's hosts. Raises
    _Left when it is not."""
    adapter = h.adapter

    def here():
        if not adapter._page_alive():
            raise _Left("closed")
        page = adapter._page
        if _host_of(page.url) not in h.hosts:
            raise _Left("left")
        out = fn(page)
        # Checked again after: an input can take the page elsewhere.
        if not adapter._page_alive():
            raise _Left("closed")
        if _host_of(page.url) not in h.hosts:
            raise _Left("left")
        return out
    return adapter._call(here, timeout)


class _Left(Exception):
    def __init__(self, why: str):
        super().__init__(why)
        self.why = why


def _ended_answer(h: Handoff, why: str) -> tuple:
    with _LOCK:
        _end(h, why)
    return 410, {"ok": False, "ended": why, "error": ENDED[why]}


def jpeg_size(data: bytes) -> tuple:
    """(width, height) from a JPEG's own header, or (0, 0). The picture is
    in CSS pixels (scale="css"), so these are the page's own coordinates."""
    i, n = 2, len(data)
    if n < 4 or data[:2] != b"\xff\xd8":
        return 0, 0
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg = int.from_bytes(data[i + 2:i + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD,
                      0xCE, 0xCF):
            height = int.from_bytes(data[i + 5:i + 7], "big")
            width = int.from_bytes(data[i + 7:i + 9], "big")
            return width, height
        i += 2 + seg
    return 0, 0


def frame(hid) -> tuple:
    """ONE picture of that window's page, handed back and not kept."""
    h, refused = _mine(hid)
    if refused:
        return refused
    now = _clock()
    with _LOCK:
        wait = h.last_frame + 1.0 / FRAMES_PER_S - now
        h.last_ask = now
        if wait > 0:
            return 429, {"ok": False, "retry_ms": int(wait * 1000) + 1,
                         "error": "Too soon for another picture."}
        h.last_frame = now
    try:
        data = _on_window(h, lambda page: page.screenshot(type="jpeg", quality=JPEG_QUALITY,
                                                          scale="css", timeout=8000))
    except _Left as left:
        return _ended_answer(h, left.why)
    except Exception as exc:
        return 503, {"ok": False, "error": f"The picture could not be taken "
                                           f"({type(exc).__name__}). Try again."}
    data = bytes(data or b"")
    w, ht = jpeg_size(data)
    with _LOCK:
        h.width, h.height = w, ht
        h.frames += 1
        seq = h.frames
    return 200, {"ok": True, "handoff": h.id, "jpeg": base64.b64encode(data).decode("ascii"),
                 "width": w, "height": ht, "seq": seq, "site": h.site, "reason": h.reason}


def _event(body: dict, h: Handoff):
    """The one input, checked: (kind, args) or raises ValueError."""
    kind = str(body.get("type") or "")
    if kind == "tap":
        try:
            x, y = float(body.get("x")), float(body.get("y"))
        except (TypeError, ValueError):
            raise ValueError("A tap needs x and y.") from None
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError("A tap must be inside the picture.")
        if h.width <= 0 or h.height <= 0:
            raise ValueError("There is no picture yet to tap on.")
        return "tap", (round(x * (h.width - 1), 1), round(y * (h.height - 1), 1))
    if kind == "text":
        text = body.get("text")
        if not isinstance(text, str) or not text:
            raise ValueError("Nothing to type.")
        if len(text) > TEXT_MOST:
            raise ValueError(f"Type at most {TEXT_MOST} characters at a time.")
        if any((ord(c) < 32 or ord(c) == 127) for c in text):
            raise ValueError("Use the keys for Enter, Tab and the like.")
        return "text", (text,)
    if kind == "key":
        key = str(body.get("key") or "")
        if key not in KEYS:
            raise ValueError("That key cannot be passed on.")
        return "key", (key,)
    if kind == "scroll":
        try:
            dy = int(body.get("dy"))
        except (TypeError, ValueError):
            raise ValueError("A scroll needs dy.") from None
        return "scroll", (max(-SCROLL_MOST, min(SCROLL_MOST, dy)),)
    raise ValueError("type must be tap, text, key or scroll.")


def _relay(page, kind: str, args: tuple) -> None:
    """The owner's own input, passed to that one page. Nothing else."""
    if kind == "tap":
        page.mouse.click(args[0], args[1])
    elif kind == "text":
        page.keyboard.type(args[0])
    elif kind == "key":
        page.keyboard.press(" " if args[0] == "Space" else args[0])
    elif kind == "scroll":
        page.mouse.wheel(0, args[0])


def send_input(hid, body) -> tuple:
    """ONE input from the owner's phone, to that window only."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "Need a JSON object."}
    h, refused = _mine(hid)
    if refused:
        return refused
    try:
        kind, args = _event(body, h)
    except ValueError as exc:
        return 400, {"ok": False, "error": str(exc)}
    now = _clock()
    with _LOCK:
        h.recent = [t for t in h.recent if now - t < INPUT_WINDOW_S]
        if len(h.recent) >= INPUTS_MOST:
            return 429, {"ok": False, "retry_ms": 500, "error": "Slow down a little."}
        h.recent.append(now)
        h.last_ask = now
    try:
        _on_window(h, lambda page: _relay(page, kind, args))
    except _Left as left:
        return _ended_answer(h, left.why)
    except Exception as exc:
        return 503, {"ok": False, "error": f"That did not reach the page "
                                           f"({type(exc).__name__}). Try again."}
    with _LOCK:
        h.inputs += 1
    _audit("input", {"type": kind, "key": args[0] if kind == "key" else ""})
    return 200, {"ok": True}


def end(hid, why: str = "owner") -> tuple:
    """End the hand-off. Never held, never a card: it only makes Jarvis do
    less. Ending one that already ended is fine."""
    hid = str(hid or "")
    with _LOCK:
        h = _CURRENT
        if h is not None and h.id == hid:
            _end(h, why if why in ENDED else "owner")
    return 200, {"ok": True, "ended": True}


def _stop_everything() -> Optional[str]:
    with _LOCK:
        h = _CURRENT
        if h is None:
            return None
        _end(h, "stop_all")
    return "The hand-off of a website to your phone ended."


def _reset_for_tests(clock: Optional[Callable[[], float]] = None) -> None:
    global _CURRENT, _clock
    with _LOCK:
        _CURRENT = None
        _ENDED.clear()
    _clock = clock or time.monotonic


try:
    import jarvis_stop_all as _STOP_ALL
    _STOP_ALL.register(STOPPER, _stop_everything)
except Exception:  # pragma: no cover - shipped beside it on the PC
    pass
