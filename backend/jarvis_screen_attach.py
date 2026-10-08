"""jarvis_screen_attach.py - "look at this" can hand the owner the PICTURE, so
they can say "look at this" with a chart or an error message and ask about it.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py;
the wiring is screen-attach.patch). The owner's decision of 2026-10-07:
`.dsh-scratch/SCREEN-ATTACH-DESIGN.md` - "one action: press the key, the PC
takes one look, and the cleaned picture lands in the question box with a
thumbnail of exactly what will be sent."

WHY THIS IS NOT "put the old hotkey back". The retired `capture_screen`
(desktop commands.rs) grabbed the whole monitor itself and attached the RAW
JPEG to the question. It knew nothing about the owner's Never look at list,
could not spot a password box, and painted nothing black; its own comment says
the same cleaning must come first if it is ever wired to a model. Nothing here
takes a picture. The PC does, exactly as it already does for an ordinary look
- `Screen._grab`, the ONE place the pause rules run in their ONE order (the
Never look at list, the lock screen and admin prompts, Jarvis's own windows,
capture protection, the password box, and the same check again after the
grab) - and the picture that comes back is `jarvis_screen.clean_picture(...,
want_png=True)`, the ONE cleaner every picture of the screen already goes
through (jarvis_picture.py), which paints every key, password and card number
SOLID BLACK. There is no second cleaner here and no picture path that can
bypass that one.

WHAT CROSSES THE BOUNDARY. Only the cleaner's own `png` - the same bytes a
picture model is already allowed to be shown - base64'd in the answer to
`POST /api/screen {"do": "look", "want": "picture"}`. The RAW capture never
leaves this module: it is a local name that is dropped as soon as the words
and the cleaned picture have been taken from it, exactly as in `Screen._read`.
Nothing is written to disk, nothing is logged, and no word from the screen
reaches this answer (see `answer` below).

FAIL CLOSED, THE DESIGN'S ONE DECISION (SCREEN-ATTACH-DESIGN.md, "The
security decision that should be explicit, not assumed"): `clean_picture` can
answer `ok: False`, `unchecked: True` or `blocked: True` - it could not verify
it had painted everything. Any of those, and no picture is handed back: the
answer carries a plain sentence instead and the app attaches nothing. The
look's WORDS still happened and are still held for the question (`ok: true`,
the usual note), because refusing the picture must not take away the look the
owner already had - the design's "The owner can still type their question
without a picture" is honoured, and so is the ordinary look it replaces.

THE LOOK ITSELF IS UNCHANGED. All the checks, the words, the two-minute hold
for follow-up questions, the note, the audit line and the events are the
engine's own; this module only takes the picture out of the same grab on its
way past (see `_read_with_picture`, which replaces `Screen._read`'s six lines
of field-setting so that the picture is decoded and checked ONCE, not twice).
Picture mode (jarvis_screen_picture.py) is started exactly as `Screen._take`
starts it, so a look with the switch on says the same thing it always did.

NOT DONE HERE, SAID PLAINLY: a password shown with a show-password eye, or a
box with nothing written beside it, still has no shape a pattern can tell from
other words (jarvis_secrets.py). The Never look at list and the password-box
pause are the other two locks; none is perfect alone.
"""
from __future__ import annotations

import base64
import json
import struct
from typing import Optional
from urllib.parse import urlsplit

import jarvis_screen as SC

#: The route this module takes over. It is jarvis_screen.py's own route: the
#: picture rides on a LOOK, so a second route would be a second thing to keep
#: in step with the session rules.
ROUTE = SC.ROUTE
#: The one field that turns an ordinary look into one that also hands back the
#: cleaned picture. Absent - or anything else - and this module is not
#: involved at all (see `handle_post`).
WANT = "picture"
#: The only picture type that is ever built here. `_size_of` below refuses
#: anything that is not really a PNG, so this is checked, not assumed.
MIME = "image/png"

#: The plain sentences the app shows when there is no picture. They name no
#: program, no site, no title and no word from the screen.
NOT_CHECKED = ("The picture could not be checked for passwords and keys, so it was not "
               "attached. Nothing from it was sent. Your question can still be asked "
               "without it.")
NOT_MADE = ("The picture of your screen could not be prepared, so it was not attached. "
            "Nothing from it was sent. Your question can still be asked without it.")
BLOCKED = ("That window does not allow a picture of itself to be taken, so nothing was "
           "attached. Your question can still be asked without it.")
LOOK_FAILED = ("Jarvis could not finish looking at your screen just now, so nothing was read "
               "and nothing was attached. Try again.")

#: The most pixels a picture of a screen may claim (a 4K screen is 8.3 M; the
#: number is a sanity bound on a header, not a resize).
MAX_SIDE = 20000
_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _size_of(png) -> Optional[tuple]:
    """(width, height) of a real PNG's IHDR - or None, which means "do not
    hand this on". The cleaner's own encoder writes exactly this shape
    (jarvis_picture.encode_png -> jarvis_screen_win.png_from_bgra), so a
    refusal here is damage or something that is not a PNG at all, and either
    way the app is given no picture."""
    try:
        b = bytes(png)
    except Exception:
        return None
    if len(b) < 24 or not b.startswith(_PNG_SIG) or b[12:16] != b"IHDR":
        return None
    w, h = struct.unpack(">II", b[16:24])
    if not (0 < w <= MAX_SIDE and 0 < h <= MAX_SIDE):
        return None
    return w, h


def picture_of(cleaned) -> Optional[tuple]:
    """(png bytes, width, height) from a `clean_picture(..., want_png=True)`
    result, or None when NO picture may cross the boundary.

    None for every way the cleaner says it could not do its job - `ok: False`,
    `unchecked: True`, `blocked: True` - and for a `png` that is missing or is
    not a PNG. The design chose this: an unverified picture of the screen is
    the exact failure the retired whole-monitor grab was removed for."""
    if not isinstance(cleaned, dict):
        return None
    if cleaned.get("ok") is False or cleaned.get("unchecked") is True \
            or cleaned.get("blocked") is True:
        return None
    size = _size_of(cleaned.get("png"))
    if size is None:
        return None
    return bytes(cleaned["png"]), size[0], size[1]


def why_no_picture(cleaned) -> str:
    """The plain sentence for a refused picture - never a word from the
    screen, never the cleaner's own jargon."""
    c = cleaned if isinstance(cleaned, dict) else {}
    if c.get("blocked") is True:
        return BLOCKED
    if c.get("ok") is False or c.get("unchecked") is True:
        return NOT_CHECKED
    return NOT_MADE


def _read_with_picture(g, cleaned, items) -> None:
    """`Screen._read`, with the picture already cleaned AND kept.

    Exactly the fields `Screen._read` sets from `clean_picture(picture,
    ocr=...)`, from the ONE result that was asked for `want_png=True` - so a
    look with a picture does ONE decode and ONE text read, not two. Every
    value still comes from the one door: the words with each hidden run
    replaced, the count of what was hidden, and "the check could not run"
    when that is the truth. Always sets `g.ready`, whatever happens."""
    c = cleaned if isinstance(cleaned, dict) else {}
    try:
        ocr_text, ocr_left = SC._ocr_words(c)
        ui_text_, ui_left, ui_hidden, ui_bad = SC.ui_words_checked(items)
        g.ocr_text, g.ocr_left, g.ui_text, g.ui_left = ocr_text, ocr_left, ui_text_, ui_left
        g.hidden = int(c.get("hidden") or 0) + int(ui_hidden or 0)
        g.unchecked = bool(c.get("unchecked")) or bool(ui_bad)
        png = c.get("png")
        SC._audit("screen.look", {"mode": g.mode, "ocr_chars": len(ocr_text),
                                  "ui_chars": len(ui_text_), "hidden": g.hidden,
                                  "attach": True,
                                  "png_bytes": len(png) if isinstance(png, (bytes, bytearray)) else 0})
    finally:
        g.ready.set()


def look_with_picture(engine=None, *, whole: bool = False) -> dict:
    """ONE look, and the cleaned picture of it. `engine` defaults to the PC's
    own (`jarvis_screen.ENGINE`).

    -> the ordinary look's answer (`{"ok", "note"}`, or `{"ok": False,
        "paused", "said"}` when there was no look at all), plus, when the
        cleaner could hand one back:
          "picture": {"data": <base64 PNG>, "mime": "image/png",
                      "width": int, "height": int, "bytes": int}
        or, when it could not:
          "picture_why": one plain sentence (`why_no_picture`).

    Never raises; never writes anything; never puts a word from the screen in
    the answer (the words go only to the question's turn, through the held
    look, exactly as they always did)."""
    try:
        return _one_look_with_picture(engine, whole=whole)
    except Exception:
        # Nothing predicted this. A half-taken look is refused with plain words
        # rather than handed back, and an app never sees a class name.
        return {"ok": False, "said": LOOK_FAILED}


def _one_look_with_picture(engine, *, whole: bool = False) -> dict:
    eng = engine if engine is not None else SC.ENGINE
    if not eng.built():
        return {"ok": False, "error": SC.not_built_words()}
    # The engine's own grab: the pause rules, in their one order, checked
    # before the picture and again after it. The picture this returns has
    # every Never-look window already painted SOLID BLACK
    # (jarvis_screen_win.take_picture); it is dropped at the end of this
    # function either way.
    got, why = eng._grab("look", whole)
    if got is None:
        return {"ok": False, "paused": why, "said": SC.said_for(why)}
    picture, items, before = got
    g = eng._glance_for("look", before)
    # Picture mode, if the owner turned it on: started exactly as `_take`
    # starts it, so the note and the model's text say the same as always.
    SC._start_picture(g, picture, before)
    # The one door. This is the only picture that is ever handed on, and it is
    # the cleaner's own output - not the capture.
    cleaned = SC.clean_picture(picture, ocr=eng.ocr, want_png=True)
    _read_with_picture(g, cleaned, items)
    picture = items = None                 # the raw capture is gone from here
    SC._wait_picture(g)
    with eng._lock:
        old, eng._look = eng._look, g
    if old is not g:
        SC._cancel_picture(old)
    eng._emit()
    out = {"ok": True, "note": SC.looked_note(g)}
    pic = picture_of(cleaned)
    if pic is None:
        out["picture_why"] = why_no_picture(cleaned)
    else:
        png, width, height = pic
        out["picture"] = {"data": base64.b64encode(png).decode("ascii"), "mime": MIME,
                          "width": width, "height": height, "bytes": len(png)}
    return out


def handle_post(body, local: bool, engine=None) -> tuple:
    """(status code, body) for one POST /api/screen.

    A body that is not a `do: "look"` asking for the picture is handed
    STRAIGHT to jarvis_screen.handle_post - the session verbs, "Watch with
    me", "stop" and "drop" behave exactly as they did, from the same code.
    This module only ever answers the one case it was added for."""
    if not isinstance(body, dict):
        return SC.handle_post(ROUTE, body, local)
    do = str(body.get("do") or "")
    if do != "look" or body.get("want") != WANT:
        return SC.handle_post(ROUTE, body, local)
    if not local:
        # Looking is this PC's own act (jarvis_screen.LOCAL_DOS): a phone
        # cannot ask for a picture of a screen it is not sitting at.
        return 403, {"ok": False, "error": SC.LOCAL_ONLY_SAYS}
    eng = engine if engine is not None else SC.ENGINE
    if not eng.built():
        return 503, SC._answer({"ok": False, "error": SC.not_built_words()})
    out = look_with_picture(eng, whole=body.get("whole") is True)
    out.pop("part", None)                  # never handed to an app
    return 200, SC._answer(out)


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_POST` so `POST /api/screen` is answered here, with
    the picture added to a look that asks for it. Every other path goes
    straight to the original.

    WHY THE WHOLE ROUTE, NOT ONLY THE ONE BODY. A request body can be read
    once. Deciding "is this the picture's look?" means reading it, and the
    screen route's own handler would then read an empty stream. So this
    wrapper reads it once and hands the parsed body to
    `jarvis_screen.handle_post` itself - the same function the other wrapper
    calls, so nothing about the session verbs moves. Installed after
    screen.patch's own block, so it wraps it.

    The origin and token checks run first, exactly as the screen route's do;
    a failure is the same plain answer. Nothing here logs anything."""
    post0 = handler_cls.do_POST
    if getattr(post0, "_jarvis_screen_attach", False):
        return "  screen     a look's cleaned picture (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def _local(self) -> bool:
        try:
            try:
                mine = self.connection.getsockname()[0]
            except Exception:
                mine = None
            return SC.is_local(self.client_address[0], mine)
        except Exception:
            return False

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != ROUTE:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"ok": False, "error": type(exc).__name__})
        try:
            code, out = handle_post(body, _local(self))
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_POST._jarvis_screen_attach = True
    handler_cls.do_POST = do_POST
    return "  screen     a look can hand back the cleaned picture of the screen"
