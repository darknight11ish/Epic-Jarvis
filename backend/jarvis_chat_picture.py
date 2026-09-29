"""jarvis_chat_picture.py - the pictures the owner ATTACHES to a chat get the
same "black out the secrets" treatment a look at the screen already has,
BEFORE any model sees them.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py;
no patch: jarvis_agent.py, which calls it, is itself a whole module). The
owner's answer of 2026-09-29, "Yes, clean them too" (CLAUDE.md), to the
screen-safety audit's note that an ordinary picture attached to a chat went
through jarvis_agent untouched, while only screen looks were cleaned.

WHAT IT DOES, IN PLAIN WORDS
  For every picture in the messages of a chat turn (both apps send it inside
  the newest message, as a `data:` address), it asks the ONE door the screen
  already uses - jarvis_screen.clean_picture, which is jarvis_picture.clean
  behind it: find anything that looks like a key, token, password, card
  number, IBAN, wallet, email or IP address in the words read from the picture
  and paint those places SOLID BLACK (never a blur). Then:
    * NOTHING needed hiding: the picture goes on exactly as it came (the same
      bytes, the same part - not even re-encoded);
    * SOMETHING was hidden: the cleaned PNG goes on instead. The original
      never does. The model is told, in words, that some places were hidden
      (a count, never what they were);
    * the picture CANNOT be checked (no text reader, no way to open it, its
      words came without positions, the check failed or took too long, it is
      not a `data:` picture, or there are more than MAX_PICTURES): it is NOT
      handed on - not to a picture model on the second card, not to a text
      model that reads its words, not to anything. The part is replaced by a
      plain line that says a picture was withheld and why, so the model does
      not guess what it showed, and the owner is told in the answer itself
      (`info["said"]`), never by the model alone. FAIL CLOSED.
  The words read from a picture (for a model that cannot see pictures) come
  from the same reading, with each hidden run shown as [hidden] - so the
  words a model gets were never read from the uncleaned picture. They are
  returned as `info["words"]`, keyed by the sha256 of the bytes that go on,
  so jarvis_agent.with_picture_text does not read the picture a second time.

WHAT IT DOES NOT CHANGE
  A picture is still OUTSIDE TEXT and never learned from (jarvis_agent's rules
  for a picture's caption and words are untouched); it is still never sent to
  an online model (jarvis_router keeps a picture turn on this PC); it is
  never written anywhere and never logged. This module only ever returns
  copies: the caller's `messages` are not changed. Counts only leave it: how
  many pictures, how many places were hidden.

SAID PLAINLY (the apps' help and docs/JARVIS-API.md 62.13 say the same): a
pattern is a guess from the SHAPE of words. A password shown with a
show-password eye, text too small or stylised for Windows' reader, a QR code
and a photo of a card are NOT caught here either. A JPEG (what both apps
attach) can only be painted on when Windows can decode it for jarvis_ocr
(want_pixels); where that is not possible the picture is withheld, not
guessed at. On a machine that is not Windows, or without the text reader,
every attached picture is withheld.

Tested on any machine: backend/test_chat_picture.py.
"""
from __future__ import annotations

import base64
import hashlib
from typing import Callable, Optional

#: The most pictures one turn's messages may carry to a model; the newest ones
#: are checked first, the rest are withheld (jarvis_agent's own reading cap is
#: the same number).
MAX_PICTURES = 3

#: The sentence both apps show where a picture is attached (the desktop's
#: attachment chip, the phone's line under the box). One source of truth:
#: backend/test_chat_picture.py checks both apps say exactly this.
OWNER_LINE = "Secrets in pictures you attach are covered with black boxes before Jarvis looks."

NOT_INSTALLED = "the part of Jarvis that checks pictures is not installed"
NOT_A_DATA_PICTURE = "it is not a picture this PC can open (only pictures sent inside the message are used)"
TOO_MANY = "more pictures were attached than can be checked at once"
FAILED = "the check could not be finished"
NOT_CHECKED = "the picture could not be checked"

#: What the model reads where a picture was withheld. Backend text, not the
#: owner's and not from the picture.
WITHHELD_FOR_MODEL = (
    "[A picture was attached to this message but was NOT shown to any model: this PC could not "
    "check it for private things (a password, a key, a card number) first, because {why}. Say so "
    "plainly and never guess what it showed.]")
#: What the model reads after a picture in which places were hidden.
HIDDEN_FOR_MODEL = (
    "[{n} private-looking place(s) in the picture attached to this message - a password, a key, a "
    "card number, an email or web address - were hidden (covered with black, or shown as [hidden] "
    "in its words). Never guess what they were.]")


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _sentence(why: str) -> str:
    """One reason as text that ends without a full stop, on one line. The
    checker's own "Jarvis could not check this picture ..., so it is not using
    it." is dropped from the front (the lines above already say it), leaving
    the reason itself."""
    w = " ".join(str(why or "").split())
    try:
        import jarvis_secrets
        pre = " ".join(str(jarvis_secrets.NOT_CHECKED).split())
        if w.startswith(pre):
            w = w[len(pre):].strip()
            if w.startswith("(") and w.endswith(")"):
                w = w[1:-1].strip()
    except Exception:
        pass
    return w.rstrip(" .;,") or NOT_CHECKED


def said_withheld(n: int, why: str) -> str:
    """The line the ANSWER ITSELF carries when picture(s) were not passed on
    (jarvis_agent.tell_owner) - written by code, so the owner is told even if
    the model does not pass it on."""
    what = "The picture you attached was" if n == 1 else f"{n} pictures you attached were"
    return (f"({what} not used: this PC could not check {'it' if n == 1 else 'them'} for keys, "
            f"passwords and card numbers first - {_sentence(why)}. Nothing was sent anywhere.)")


def note_line(covered_places: int, checked: int) -> str:
    """The short note beside the answer (jarvis_agent's `announce`): a count,
    never what was hidden. "" when there was nothing to say."""
    if covered_places:
        return (f"covered {covered_places} private-looking "
                f"{_plural(covered_places, 'place', 'places')} in your "
                f"{_plural(checked, 'picture', 'pictures')} with black before Jarvis looked")
    if checked:
        return (f"checked your {_plural(checked, 'picture', 'pictures')} for keys, passwords and "
                "card numbers: nothing needed hiding")
    return ""


# --------------------------------------------------------------------------
#   Message plumbing
# --------------------------------------------------------------------------

def _image_part(part) -> bool:
    """The same test jarvis_agent._image_part makes (kept here so the module
    stands alone)."""
    return isinstance(part, dict) and (part.get("type") in ("image_url", "image", "input_image")
                                       or "image_url" in part)


def _uri_of(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _with_uri(part: dict, uri: str) -> dict:
    """A copy of one image part carrying `uri`, in the shape it came in."""
    new = dict(part)
    if isinstance(part.get("image_url"), dict):
        new["image_url"] = dict(part["image_url"], url=uri)
    elif "image_url" in part:
        new["image_url"] = uri
    else:
        new["image"] = uri
    return new


def _text(words: str) -> dict:
    return {"type": "text", "text": words}


def _bytes_of(part) -> Optional[bytes]:
    try:
        import jarvis_ocr
        return jarvis_ocr.image_bytes(part)
    except Exception:
        return None


def _door() -> Optional[Callable]:
    """The one door screen pictures go through, or None."""
    try:
        import jarvis_screen
        fn = getattr(jarvis_screen, "clean_picture", None)
        return fn if callable(fn) else None
    except Exception:
        return None


def _picture_slots(messages: list) -> list:
    """[(message index, part index)] of every image part, NEWEST first."""
    slots = []
    for mi in range(len(messages) - 1, -1, -1):
        m = messages[mi]
        c = m.get("content") if isinstance(m, dict) else None
        if isinstance(c, list):
            for pi in range(len(c) - 1, -1, -1):
                if _image_part(c[pi]):
                    slots.append((mi, pi))
    return slots


def has_picture(messages) -> bool:
    return bool(_picture_slots(list(messages or [])))


def _empty_info() -> dict:
    return {"pictures": 0, "passed": 0, "covered": 0, "hidden": 0, "withheld": 0, "why": [],
            "words": {}, "note": "", "said": ""}


def _finish(info: dict) -> dict:
    if info["withheld"]:
        info["said"] = said_withheld(info["withheld"], info["why"][0] if info["why"] else "")
    info["note"] = note_line(info["hidden"], info["passed"])
    return info


def withhold_all(messages, why: str = NOT_CHECKED) -> tuple:
    """(messages, info): a copy with EVERY picture replaced by the plain line
    that says it was withheld. The fail-closed answer when nothing can be
    trusted. Never raises."""
    msgs = list(messages or [])
    info = _empty_info()
    try:
        for mi, pi in _picture_slots(msgs):
            content = list(msgs[mi]["content"])
            content[pi] = _text(WITHHELD_FOR_MODEL.format(why=_sentence(why)))
            msgs[mi] = dict(msgs[mi], content=content)
            info["pictures"] += 1
            info["withheld"] += 1
        if info["withheld"]:
            info["why"].append(_sentence(why))
    except Exception:
        # Not even that worked: drop every list-shaped message's pictures.
        msgs = [dict(m, content=[p for p in m["content"] if not _image_part(p)])
                if isinstance(m, dict) and isinstance(m.get("content"), list) else m
                for m in msgs]
    return msgs, _finish(info)


# --------------------------------------------------------------------------
#   The whole thing
# --------------------------------------------------------------------------

def _check_one(part, door: Callable, reader: Optional[Callable]) -> dict:
    """{"part": the part to send on, or None when withheld, "why", "hidden",
    "words": {"ok","text","left_out"} or None, "key": sha256 of the bytes that
    go on}. Never raises."""
    image = _bytes_of(part)
    if not image:
        return {"part": None, "why": NOT_A_DATA_PICTURE, "hidden": 0, "words": None, "key": ""}
    try:
        res = door(image, ocr=reader, want_png=True) if reader is not None \
            else door(image, want_png=True)
    except Exception:
        return {"part": None, "why": FAILED, "hidden": 0, "words": None, "key": ""}
    if not isinstance(res, dict) or not res.get("ok") or not res.get("png"):
        why = ""
        if isinstance(res, dict):
            why = str(res.get("png_why") or res.get("why") or "")
        return {"part": None, "why": why or NOT_CHECKED, "hidden": 0, "words": None, "key": ""}
    png, hidden = bytes(res["png"]), int(res.get("hidden") or 0)
    words = {"ok": True, "text": str(res.get("text") or ""), "left_out": int(res.get("left_out") or 0),
             "why": ""}
    if hidden <= 0:
        # Nothing to hide: the picture as it came - the very same part.
        return {"part": part, "why": "", "hidden": 0, "words": words,
                "key": hashlib.sha256(image).hexdigest()}
    if png == image:
        # Something was said to be hidden but the bytes are the original's:
        # never trust that. Fail closed.
        return {"part": None, "why": NOT_CHECKED, "hidden": 0, "words": None, "key": ""}
    return {"part": _with_uri(part, _uri_of(png)), "why": "", "hidden": hidden, "words": words,
            "key": hashlib.sha256(png).hexdigest()}


def clean_messages(messages, *, reader: Optional[Callable] = None,
                   clean: Optional[Callable] = None, limit: int = MAX_PICTURES) -> tuple:
    """(messages, info): a copy of `messages` in which every picture is either
    the cleaned one, the very same one (nothing needed hiding), or a plain
    line saying it was withheld and why. `reader(image)` is the text reader
    (jarvis_ocr.read_text's shape, with each word's position); `clean` is the
    door (default jarvis_screen.clean_picture: `clean(image, ocr=reader,
    want_png=True)`). Never changes `messages`; never raises - on anything
    unexpected every picture is withheld.

    info: {"pictures", "passed" (went on: cleaned or as they were), "covered"
    (of those, how many were painted on), "hidden" (places hidden, all
    pictures), "withheld", "why": [distinct reasons], "words": {sha256 of the
    bytes that go on: {"ok", "text", "left_out", "why"}}, "note": for the
    answer's note, "said": for the answer itself (only when something was
    withheld)}."""
    msgs = list(messages or [])
    slots = _picture_slots(msgs)
    if not slots:
        return msgs, _empty_info()
    try:
        door = clean or _door()
        if door is None:
            return withhold_all(msgs, NOT_INSTALLED)
        info = _empty_info()
        for n, (mi, pi) in enumerate(slots):
            part = msgs[mi]["content"][pi]
            info["pictures"] += 1
            if n >= max(0, int(limit)):
                got = {"part": None, "why": TOO_MANY, "hidden": 0, "words": None, "key": ""}
            else:
                got = _check_one(part, door, reader)
            content = list(msgs[mi]["content"])
            if got["part"] is None:
                info["withheld"] += 1
                why = _sentence(got["why"])
                if why not in info["why"]:
                    info["why"].append(why)
                content[pi] = _text(WITHHELD_FOR_MODEL.format(why=why))
            else:
                info["passed"] += 1
                content[pi] = got["part"]
                if got["hidden"]:
                    info["covered"] += 1
                    info["hidden"] += got["hidden"]
                    # right AFTER the picture, so the model reads it beside it
                    content.insert(pi + 1, _text(HIDDEN_FOR_MODEL.format(n=got["hidden"])))
                if got["words"] is not None and got["key"]:
                    info["words"][got["key"]] = got["words"]
            msgs[mi] = dict(msgs[mi], content=content)
        return msgs, _finish(info)
    except Exception:
        return withhold_all(list(messages or []), FAILED)


def reader_for(info: dict) -> Callable:
    """A text reader for jarvis_agent.with_picture_text that answers from what
    `clean_messages` already read (and cleaned), so a picture is read ONCE and
    its words never come from the uncleaned picture. A picture it does not
    know (there should be none) is refused, never read raw."""
    words = dict((info or {}).get("words") or {})

    def read(image: bytes) -> dict:
        try:
            got = words.get(hashlib.sha256(bytes(image)).hexdigest())
        except Exception:
            got = None
        if got is not None:
            return dict(got)
        return {"ok": False, "text": "", "left_out": 0, "why": NOT_CHECKED}
    return read
