"""jarvis_form_review.py - "fill in the form, show me, then send it": the
SECOND card, the picture that rides on it, and the one route that serves it
(docs/FORM-REVIEW-DESIGN.md, the owner's decision of 2026-09-30).

NEW MODULE, shipped whole; form-review.patch adds the gate action and one
install() call to jarvis_hud.py. The step order and every last check live in
jarvis_browser_control.run() (its `review`, `snapshot` and `fingerprint`
hooks); the "never on a turn that read outside text" refusal is in
jarvis_agent.py. This file is the part in between.

THE FLOW. A browser plan may end in ONE click marked `final` - the click that
sends a form. run() fills everything before it, stops, takes ONE picture of
the page (`capture`), and calls the hook `make_review()` builds. The hook
raises a card under the gate action `browser_form_submit` (tier ask, a risky
approval, never auto or notify, never "always allow", decided by tapping
only). Its text is the site, every step that was done with every word typed
or chosen, and "Jarvis will now click <name>. It cannot be undone." The card's
`detail` is {"text": <that>, "picture": <id>} - `picture` only when there is
one. Only on a yes does run() re-check that the page is the one the owner
looked at (address, the button, every field) and click.

THE PICTURE. Visible browser only (Playwright `page.screenshot`, the whole
page, JPEG). The headless engine has no pixels: its card says "No picture -
this browser has no window" and still needs the second card. It is:

  - held IN MEMORY ONLY, in this module, keyed by a random id; never written
    to disk, never logged, never put in an event, status or audit line,
    never handed to any model, and NOT run through jarvis_screen.clean_picture
    (the owner's answer 1: the owner has to READ the name, phone and email);
  - one at a time: a new review drops the old picture;
  - dropped when the card is decided, when it runs out of time, or after ten
    minutes, whichever is first;
  - scaled to at most 1,600 px on its longest side, JPEG quality 70, at most
    1.5 MiB. Bigger is scaled down (Pillow, when it is installed); with no
    Pillow, a picture over a cap is NOT sent at all and the card says so in
    words - the words are still there to read;
  - served only by GET /api/form-review/picture?id=<id>, behind the server's
    own origin and token checks, and only for an id whose card still waits.
    Anything else, including a guess, is a 404 {"ok": false} that says nothing
    of why.

Standard library only (Pillow, if there, is used to scale). No I/O but the one
screenshot and the route.
"""
from __future__ import annotations

import base64
import hashlib
import importlib
import io
import json
import re
import secrets
import threading
import time
from typing import Callable, Optional
from urllib.parse import parse_qs, urlsplit

#: The gate action of the second card. Tier "ask" only.
ACTION = "browser_form_submit"
PICTURE_ROUTE = "/api/form-review/picture"

MAX_SIDE = 1600
JPEG_QUALITY = 70
MAX_BYTES = int(1.5 * 1024 * 1024)
#: How long a picture is kept if nobody decides. Longer than the gate's own
#: card timeout, so the picture is there for as long as the card is.
KEEP_SECONDS = 600
#: The gate keeps 4,000 characters of a card's detail (jarvis_agent
#: _GATE_DETAIL_LIMIT). A card that would not fit is refused, never cut: the
#: owner is never asked to approve words they were not shown.
CARD_LIMIT = 3900

NO_WINDOW = "No picture - this browser has no window."
NOT_SENT = "Nothing was sent."

_ID_OK = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


class NoPicture(Exception):
    """The picture could not be made; `plain` is the reason, for the card."""

    def __init__(self, plain: str):
        super().__init__(plain)
        self.plain = plain


# --------------------------------------------------------------------------
#   The picture store - memory only
# --------------------------------------------------------------------------

_LOCK = threading.Lock()
_STORE: dict = {}          # id -> {"jpeg", "width", "height", "expires", "timer"}
_clock: Callable[[], float] = time.monotonic


def _drop_locked(pid: str) -> None:
    e = _STORE.pop(pid, None)
    if e and e.get("timer") is not None:
        try:
            e["timer"].cancel()
        except Exception:
            pass


def _purge_locked() -> None:
    now = _clock()
    for pid in [k for k, e in _STORE.items() if e["expires"] <= now]:
        _drop_locked(pid)


def put(jpeg: bytes, width: int, height: int) -> str:
    """Keep ONE picture, and return its random id. Any earlier picture is
    dropped first: one review at a time."""
    pid = secrets.token_urlsafe(18)
    with _LOCK:
        for old in list(_STORE):
            _drop_locked(old)
        timer = threading.Timer(KEEP_SECONDS, drop, args=(pid,))
        timer.daemon = True
        _STORE[pid] = {"jpeg": bytes(jpeg), "width": int(width), "height": int(height),
                       "expires": _clock() + KEEP_SECONDS, "timer": timer}
        timer.start()
    return pid


def get(pid) -> Optional[dict]:
    """The picture for an id whose card still waits, else None."""
    if not isinstance(pid, str) or not _ID_OK.match(pid):
        return None
    with _LOCK:
        _purge_locked()
        e = _STORE.get(pid)
        return dict(e) if e else None


def drop(pid) -> None:
    with _LOCK:
        _drop_locked(str(pid))


def held() -> int:
    """How many pictures are held right now (for the tests and nothing else)."""
    with _LOCK:
        _purge_locked()
        return len(_STORE)


def _reset_for_tests() -> None:
    global _clock
    with _LOCK:
        for pid in list(_STORE):
            _drop_locked(pid)
    _clock = time.monotonic


# --------------------------------------------------------------------------
#   The picture: taken from the visible browser's page, then made small
# --------------------------------------------------------------------------

def jpeg_size(data: bytes) -> tuple:
    """(width, height) from a JPEG's own header, or (0, 0)."""
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


def fit(data: bytes) -> dict:
    """{"jpeg", "width", "height"} inside the caps, or raises NoPicture.
    Scaled down with Pillow when it is installed; with none, a picture that is
    already inside the caps is used as it is and a bigger one is refused in
    words (never sent unscaled, never cut)."""
    data = bytes(data or b"")
    w, h = jpeg_size(data)
    if not (w and h):
        raise NoPicture("the picture could not be read back")
    if max(w, h) <= MAX_SIDE and len(data) <= MAX_BYTES:
        return {"jpeg": data, "width": w, "height": h}
    try:
        # By name, as jarvis_screen_picture.py does: Pillow is optional here.
        Image = importlib.import_module("PIL.Image")
    except Exception:
        raise NoPicture("the page is too big to show in one picture here (Pillow, which "
                        "scales it down, is not installed)") from None
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        img = img.convert("RGB")
        scale = min(1.0, MAX_SIDE / float(max(img.size)))
        if scale < 1.0:
            img = img.resize((max(1, int(img.size[0] * scale)),
                              max(1, int(img.size[1] * scale))), Image.LANCZOS)
        quality = JPEG_QUALITY
        while True:
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=quality, optimize=True)
            out = buf.getvalue()
            if len(out) <= MAX_BYTES or quality <= 30:
                break
            quality -= 10
        if len(out) > MAX_BYTES:
            raise NoPicture("the picture is still too big after scaling it down")
        return {"jpeg": out, "width": img.size[0], "height": img.size[1]}
    except NoPicture:
        raise
    except Exception:
        raise NoPicture("the picture could not be scaled down") from None


def _page_of(session: str):
    import jarvis_browser_control as B
    page = B._sessions.get(session)
    if page is None:
        raise NoPicture("the browser tab is not open")
    return page


def capture(session: str) -> dict:
    """ONE picture of the whole page in the visible browser's tab `session`,
    inside the caps. Kept nowhere: the caller holds it. Raises NoPicture."""
    page = _page_of(session)
    try:
        data = page.screenshot(type="jpeg", quality=JPEG_QUALITY, full_page=True,
                               scale="css", timeout=8000)
    except NoPicture:
        raise
    except Exception:
        raise NoPicture("the browser could not take a picture of the page") from None
    return fit(data)


#: In the page: one row per form field - what it is and what it holds. The
#: rows are hashed here in Python and dropped; they are never kept or shown.
_FIELDS_JS = """() => Array.from(document.querySelectorAll('input,select,textarea'))
  .slice(0, 400).map(e => [e.tagName, e.type || '', e.name || '', e.id || '',
    e.type === 'checkbox' || e.type === 'radio' ? String(!!e.checked) : String(e.value || ''),
    String(!!e.disabled)])"""


def fingerprint(session: str) -> Optional[str]:
    """A hash of every field's real content in the visible tab - including a
    password box's, which the accessibility tree cannot show. Compared, never
    kept or shown."""
    page = _page_of(session)
    rows = page.evaluate(_FIELDS_JS)
    blob = json.dumps(rows, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
#   The second card
# --------------------------------------------------------------------------

def _label(role: str, name: str, within: str) -> str:
    where = f' (inside "{within}")' if within else ""
    return f'{role} "{name}"{where}'


def card_text(info: dict, *, has_picture: bool) -> str:
    """The card: the site, every step done with every word, what is about to
    be clicked, and what the picture is (or why there is none). Built only
    from `info` (jarvis_browser_control's own record) - no model words."""
    site = info.get("site") or "an unknown site"
    fin = info.get("final") or {}
    lines = [f"Jarvis wants to submit a form on {site}. It goes only if you approve, and "
             "nothing was sent yet.", "",
             f"Site: {site}", "", "What Jarvis did on the page, in order:"]
    steps = info.get("steps") or []
    if not steps:
        lines.append("  (nothing - the form was already on the page)")
    for n, st in enumerate(steps, 1):
        act = st.get("action")
        if act == "navigate":
            lines.append(f"  {n}. opened {st.get('value')!r}")
        elif act == "click":
            lines.append(f"  {n}. clicked {_label(st.get('role', ''), st.get('name', ''), st.get('within', ''))}")
        elif act == "select":
            lines.append(f"  {n}. chose {st.get('value')!r} in "
                         f"{_label(st.get('role', ''), st.get('name', ''), st.get('within', ''))}")
        else:
            lines.append(f"  {n}. typed {st.get('value')!r} into "
                         f"{_label(st.get('role', ''), st.get('name', ''), st.get('within', ''))}")
    lines.append("")
    if has_picture:
        lines.append("The picture shown with this card is the page exactly as it looks now "
                     "- nothing in it is hidden or covered, so check every detail.")
    else:
        why = (info.get("no_picture") or NO_WINDOW).rstrip(".")
        lines.append(why[:1].upper() + why[1:] + ". Read the words above carefully: they "
                     "are all you have to check.")
    lines += ["",
              f'Jarvis will now click {_label(fin.get("role", "button"), fin.get("name", ""), fin.get("within", ""))}. '
              "It cannot be undone.",
              "",
              "If you say no: nothing is sent, and the filled-in form stays open in the "
              "browser for you."]
    return "\n".join(lines)


def _said_yes(verdict) -> bool:
    """A person's yes, and nothing else - the same rule as jarvis_agent's
    _a_person_said_yes, kept here so this module imports nothing from it."""
    if getattr(verdict, "allowed", False) is not True:
        return False
    outcome = getattr(verdict, "outcome", None)
    if outcome is not None:
        return outcome == "approved"
    return getattr(verdict, "tier", None) == "ask"


def make_review(checker: Callable, *, tier_of: Optional[Callable[[str], str]] = None,
                cannot_ask: Optional[Callable[[], str]] = None,
                set_status: Optional[Callable] = None,
                card_answered: Optional[Callable] = None,
                card_shown: Optional[Callable] = None) -> Callable[[dict], dict]:
    """The `review` hook for jarvis_browser_control.run().

    `checker(action, detail, prompt)` is the same gate call every card uses.
    `tier_of(action)` says the action's configured tier: anything but "ask"
    refuses without raising a card (a card that could not end in a person
    deciding is never raised). `cannot_ask()` returns a plain reason, or "",
    for a limit on cards this turn. `set_status`, `card_answered` and
    `card_shown` are the agent's own bookkeeping around any card.

    The hook never raises for a refusal: it returns {"approved": False,
    "reason": <plain words>}. The picture is held only while the card waits
    and is dropped in a `finally`, whatever happens."""
    def review(info: dict) -> dict:
        def refuse(reason: str) -> dict:
            return {"approved": False, "reason": reason}
        if tier_of is not None:
            try:
                tier = tier_of(ACTION)
            except Exception:
                tier = ""
            if tier != "ask":
                return refuse(f"{ACTION} is not set to \"ask\", so no card could be raised - "
                              f"tell the owner ({NOT_SENT.lower()})")
        if cannot_ask is not None:
            why = cannot_ask()
            if why:
                return refuse(why)
        pic = info.get("picture")
        has_pic = isinstance(pic, dict) and bool(pic.get("jpeg"))
        text = card_text(info, has_picture=has_pic)
        if len(json.dumps({"text": text, "picture": "x" * 32})) >= CARD_LIMIT:
            return refuse("the filled-in form is too long to show in full on one card, so "
                          "nobody was asked")
        pid = ""
        try:
            detail = {"text": text}
            if has_pic:
                pid = put(pic["jpeg"], pic.get("width", 0), pic.get("height", 0))
                detail["picture"] = pid
            if set_status:
                set_status("approval")
            verdict = checker(ACTION, detail, f"submit a form on {info.get('site') or 'a site'}")
            if card_answered:
                card_answered(verdict)
            if set_status:
                set_status("thinking")
            if card_shown:
                card_shown(verdict)
        finally:
            if pid:
                drop(pid)
        if _said_yes(verdict):
            return {"approved": True, "reason": ""}
        outcome = str(getattr(verdict, "outcome", "") or "")
        if outcome == "timed_out":
            return refuse("the card ran out of time")
        if outcome == "denied":
            return refuse("you said no")
        why = str(getattr(verdict, "reason", "") or "").strip()[:200]
        return refuse(why or "it was not approved")
    return review


# --------------------------------------------------------------------------
#   The route
# --------------------------------------------------------------------------

def handle_get(query: str = "") -> tuple:
    """GET /api/form-review/picture?id= - the picture of a card that still
    waits, else 404 {"ok": false} (a guess, an old id and a decided card all
    look the same)."""
    pid = (parse_qs(str(query or "")).get("id") or [""])[0]
    e = get(pid)
    if e is None:
        return 404, {"ok": False}
    return 200, {"ok": True, "jpeg": base64.b64encode(e["jpeg"]).decode("ascii"),
                 "width": e["width"], "height": e["height"]}


def install(handler_cls, *, origin_ok, token_ok, read_body=None) -> str:
    """Wrap `handler_cls.do_GET` so the picture route is answered here, after
    the server's own origin and token checks. Everything else goes straight
    to the original."""
    get0 = handler_cls.do_GET
    if getattr(get0, "_jarvis_form_review", False):
        return "  form       Form review picture (already on)"

    def do_GET(self):
        parsed = urlsplit(str(getattr(self, "path", "") or ""))
        if parsed.path.rstrip("/") != PICTURE_ROUTE:
            return get0(self)
        try:
            if not origin_ok(self):
                return self._send(403, {"error": "cross-origin request refused"})
            if not token_ok(self):
                return self._send(401, {"error": "bad or missing X-Jarvis-Token"})
        except Exception:
            return self._send(401, {"error": "bad or missing X-Jarvis-Token"})
        try:
            code, out = handle_get(parsed.query)
        except Exception:
            code, out = 404, {"ok": False}
        return self._send(code, out)

    do_GET._jarvis_form_review = True
    handler_cls.do_GET = do_GET
    return "  form       Form review: the picture of a form waiting to be sent"
