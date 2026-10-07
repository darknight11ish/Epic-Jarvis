"""jarvis_youtube.py - "Quiz me on a YouTube video": read a video's CAPTION TEXT
after the owner's own card, then quiz the owner on it.

NEW MODULE, shipped whole. youtube.patch adds the gate lines (the new action
`youtube_captions_read`) and ONE install block in jarvis_hud.py. Design:
docs/STUDY-FROM-TEXT-DESIGN.md section 5 (Slice B) and section 14 (the frozen
contract the apps build from). API: docs/JARVIS-API.md section 112.

THE OWNER'S DECISION (2026-09-30): reading a YouTube video's captions is
allowed, ONE CARD PER LINK, caption text only, never video or audio. The owner
accepts that this breaks YouTube's terms and may be blocked. It reverses the
2026-09-26 "left out" decision for caption text only.

WHAT IT DOES, IN PLAIN WORDS
  1. The owner pastes a YouTube link in the Quiz page of either app.
  2. Jarvis checks the link's SHAPE (no network): it must be one video on
     youtube.com / youtu.be. Playlists, channels, other sites, lookalike
     hosts, links with a name/password in them, odd ports and non-web
     schemes are refused before any card.
  3. ONE approval card (gate action `youtube_captions_read`, tier "ask")
     shows the exact link and says plainly: this breaks YouTube's terms and
     may be blocked; only caption text is fetched (no video, no audio); the
     link tells YouTube which video the owner is studying; it is a named way
     out of the PC (docs/ARCHITECTURE.md section 4).
  4. Only after a real yes: the caption text is fetched (the
     `youtube-transcript-api` package, MIT, pinned in requirements.txt; no key,
     no sign-in, no cookies, no proxy service), cleaned, cut to the quiz's
     20,000-character limit if longer (and it says so), and handed to
     jarvis_quiz.start_outside() as OUTSIDE text.
  5. The quiz is the ordinary Quiz (section 98): in memory only, marked by the
     local model, crisis check on every answer. Nothing is learned from the
     captions, nothing is written to disk here, nothing goes to chat history.

THE RULES IT KEEPS (each has a test in test_youtube.py)
  * The card is raised BEFORE any network call, one per link, never a standing
    permission: a second link is a second card. Anything but a person's yes
    fetches nothing.
  * Caption text only. The one thing sent to YouTube is the video id (in the
    library's own requests to youtube.com). No video, no audio, no comments, no
    other link is ever followed. No captions -> a plain message; there is no
    speech-to-text fallback and no other site is tried.
  * The link is never logged or written to the audit log (only outcomes).
  * The caption text is OUTSIDE text: the quiz is marked provenance "outside",
    the text can say anything so it only ever reaches the model as fenced data
    (jarvis_quiz), and it is never learned, saved or read into memory.
  * Not from a turn that already read outside text or private things: `start()`
    refuses with `tainted=True` (a chat door, if one is ever built, must pass
    it - the card would be misleading otherwise).
  * Errors are said in plain words. No exception text (it can hold the link).

WHAT IS NOT CHECKED
  The library was never run against the live site in the build container (the
  network policy). YouTube often blocks data-centre addresses and changes its
  pages; the owner's home connection is the realistic case. The tests use a
  stand-in transport and never touch the network.

    python3 test_youtube.py
"""
from __future__ import annotations

import html
import json
import re
import threading
import time
import unicodedata
import urllib.parse
import uuid
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

PATH = "/api/youtube"
QUIZ_ROUTE = "/api/youtube/quiz"

ACTION = "youtube_captions_read"

# ---- limits ---------------------------------------------------------------
LINK_MAX = 300                    # characters of a pasted link
TEXT_MAX = 20000                  # the quiz's own limit (jarvis_quiz.TEXT_MAX)
TEXT_MIN = 200                    # the quiz's own minimum (jarvis_quiz.TEXT_MIN)
RAW_MAX = 400000                  # characters read from the library before cutting
SNIPPET_MAX = 30000               # caption lines read at most
FETCH_SECONDS = 40.0              # wall-clock limit on the library's requests
EXPIRY_SECONDS = 60 * 60
KEEP_REQUESTS = 5
DEFAULT_LANGUAGES = ("en",)
DEFAULT_TITLE = "Quiz on a YouTube video"
COUNT_DEFAULT = 5

HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"})
_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_LANG = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?$")
_PATH_KINDS = ("shorts", "embed", "live", "v")

# ---- the words both apps show (word for word; JARVIS-API section 112) ------
TITLE = "Quiz me on a YouTube video"
INTRO = ("Paste a YouTube link and Jarvis reads the video's captions (the words shown as "
         "subtitles), then quizzes you on them. It asks with a card first, every time.")
TERMS = ("This breaks YouTube's terms and may be blocked. Only the caption text is fetched - "
         "never the video or its sound. The link tells YouTube which video you are studying.")
OUTSIDE_LINE = ("The captions are treated as outside text: Jarvis never learns facts from them. "
                "Your answers are marked by the model on this PC.")
STATE_WORDS = {
    "waiting": "Waiting for your yes on the approval card.",
    "fetching": "Reading the captions from YouTube...",
    "writing": "Writing the questions...",
    "ready": "Ready.",
    "denied": "You said no, so nothing was fetched.",
    "timed_out": "Nobody answered the card in time, so nothing was fetched.",
    "withdrawn": "You cancelled before the card was answered, so nothing was fetched.",
    "refused": "The card could not be answered, so nothing was fetched.",
    "failed": "Could not make a quiz from that video.",
}

#: code -> (status, plain words). Nothing here quotes the link or an exception.
CLASSES = {
    "bad_link": (400, "That does not look like a link. Paste the video's address, which "
                      "starts with https."),
    "not_a_web_link": (400, "That is not a web link. A YouTube address starts with https."),
    "link_has_login": (400, "That link has a name or password in it, so Jarvis will not use "
                            "it. Paste the plain video address."),
    "not_youtube": (400, "That is not a YouTube video link. Jarvis only reads captions from "
                         "youtube.com or youtu.be."),
    "playlist_link": (400, "That link is a playlist. Paste the link to one video."),
    "no_video": (400, "That link does not point to one video. Paste a video's own address."),
    "bad_count": (400, "Ask for between 1 and 10 questions."),
    "bad_language": (400, "The caption language must be a short code such as en or es."),
    "outside_text_turn": (409, "Jarvis has just read outside text or private things in this "
                               "conversation, so it will not fetch a video's captions now. "
                               "Start from the Quiz page."),
    "request_waiting": (409, "A YouTube card is already waiting. Answer it first."),
    "too_many_quizzes": (409, "Three quizzes are already open. Finish or stop one first."),
    "card_unavailable": (503, "Jarvis could not raise the approval card. Nothing was fetched."),
    "tier_not_ask": (503, "This needs your yes every time, but the settings file says "
                          "otherwise, so it is switched off."),
    "not_found": (404, "That YouTube request is not open any more. Start a new one."),
    "already_started": (409, "It is already reading the captions and can no longer be "
                             "cancelled."),
    # ---- failures after a yes (shown as a failed request's message) ----
    "no_captions": (200, "No captions for this video. The person who posted it may have turned "
                         "them off, or there are none."),
    "no_captions_language": (200, "This video has no captions in that language."),
    "video_unavailable": (200, "YouTube says this video is not available. It may be private, "
                               "removed, or blocked where you are."),
    "age_restricted": (200, "This video is age-restricted. Jarvis does not sign in to YouTube, "
                            "so it cannot read its captions."),
    "youtube_refused": (200, "YouTube refused the request. It sometimes blocks programs like "
                             "this one - try again later. Nothing was changed."),
    "youtube_failed": (200, "Could not read the captions from YouTube. It may have changed how "
                            "it works. Nothing was changed."),
    "fetch_timeout": (200, "YouTube took too long to answer. Nothing was changed - try again "
                           "later."),
    "library_missing": (200, "Your PC's Jarvis does not have the caption reader installed yet "
                             "- run apply-patches.ps1 on the PC."),
    "too_little_text": (200, "The captions are too short to make a quiz from."),
    "model_unavailable": (200, "The model on this PC did not answer. Nothing was changed - "
                               "try again in a moment."),
    "quiz_failed": (200, "The captions were read, but a quiz could not be made from them."),
}


class YouTubeError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
        self.status, self.message = CLASSES[code]


# ---------------------------------------------------------------------------
#   1. The link - shape only, never a network call
# ---------------------------------------------------------------------------

def parse_link(link) -> dict:
    """{"video_id", "canonical", "changed"} or YouTubeError. `changed` is True
    when the pasted text was not already the canonical address (so the card
    shows both)."""
    if not isinstance(link, str) or not link.strip():
        raise YouTubeError("bad_link")
    raw = link.strip()
    if len(raw) > LINK_MAX or any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7f
                                  for ch in raw) or "\\" in raw:
        raise YouTubeError("bad_link")
    if not raw.isascii():
        # Lookalike letters (a Cyrillic "a" in the host) and hidden marks.
        raise YouTubeError("not_youtube" if re.match(r"^\w+://", raw) or "." in raw
                           else "bad_link")
    if "://" not in raw:
        raise YouTubeError("not_a_web_link" if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", raw)
                           else "bad_link")
    try:
        u = urllib.parse.urlsplit(raw)
    except ValueError:
        raise YouTubeError("bad_link")
    if u.scheme.lower() not in ("http", "https"):
        raise YouTubeError("not_a_web_link")
    if "@" in u.netloc:
        raise YouTubeError("link_has_login")
    try:
        port = u.port
    except ValueError:
        raise YouTubeError("not_youtube")
    host = (u.hostname or "").lower()
    if host not in HOSTS or port is not None or u.netloc.endswith(":"):
        raise YouTubeError("not_youtube")
    query = urllib.parse.parse_qs(u.query, keep_blank_values=True)
    if "list" in query or u.path.rstrip("/").lower() == "/playlist":
        raise YouTubeError("playlist_link")
    parts = [p for p in u.path.split("/") if p]
    vid = None
    if host.endswith("youtu.be"):
        if len(parts) == 1:
            vid = parts[0]
    elif parts == ["watch"]:
        vs = query.get("v", [])
        if len(vs) == 1:
            vid = vs[0]
    elif len(parts) == 2 and parts[0].lower() in _PATH_KINDS:
        vid = parts[1]
    if vid is None or not _ID.match(vid):
        raise YouTubeError("no_video")
    canonical = f"https://www.youtube.com/watch?v={vid}"
    return {"video_id": vid, "canonical": canonical, "changed": raw != canonical}


# ---------------------------------------------------------------------------
#   2. The card
# ---------------------------------------------------------------------------

def card(parsed: dict) -> str:
    lines = ["Let Jarvis read this YouTube video's captions?", "",
             f"Video: {parsed['canonical']}"]
    if parsed.get("changed"):
        lines.append("(Jarvis uses only the video's own address; anything else in the link you "
                     "pasted is dropped.)")
    lines += [
        "",
        "Jarvis will fetch this video's caption text from YouTube - the words shown as "
        "subtitles - on this PC, then quiz you on it. Nothing else is sent. The address itself "
        "tells YouTube which video you are studying.",
        "",
        "This breaks YouTube's terms and may be blocked. YouTube may refuse the request, and "
        "it may block this PC's address for a while. You chose to accept that.",
        "",
        "Only caption text is fetched: never the video, never its sound, never the comments. "
        "Jarvis does not sign in to YouTube and never follows any other link. A video with no "
        "captions cannot be used.",
        "",
        "This is a way out of this PC: your PC will contact YouTube.",
        "",
        "The captions are outside text: they can say anything, so Jarvis never learns a fact "
        "about you from them and never saves them. The quiz on them is kept in memory only.",
        "",
        "One card covers this one link. Another video is another card.",
        "",
        "If you did not just do this, say no.",
        "",
        "If you say no: nothing is fetched.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
#   3. The pieces the tests replace: the gate, the transport, the quiz, the clock
# ---------------------------------------------------------------------------

def _tier(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-youtube", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    # Outcomes only. Never a link, a video id or any caption text.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def default_fetch(video_id: str, languages) -> list:
    """The one real transport: the youtube-transcript-api package. Returns
    [{"text", "start"}]. Raises the package's own errors (mapped by name in
    `_code_of`) or ImportError when it is not installed. No proxy, no cookies."""
    from youtube_transcript_api import YouTubeTranscriptApi
    got = YouTubeTranscriptApi().fetch(video_id, languages=list(languages))
    out = []
    for i, sn in enumerate(got):
        if i >= SNIPPET_MAX:
            break
        out.append({"text": getattr(sn, "text", ""), "start": getattr(sn, "start", 0.0)})
    return out


def default_quiz(text: str, count: int, title: str) -> dict:
    import jarvis_quiz
    return jarvis_quiz.start_outside(text, count, title, "youtube")


def default_open_count() -> int:
    import jarvis_quiz
    return jarvis_quiz.open_count()


_STATE = {"fetch": None, "quiz": None, "open_count": None, "gate": None, "tier_of": None,
          "spawn": None, "now": time.time}


def configure(*, fetch=None, quiz=None, open_count=None, gate=None, tier_of=None,
              spawn=None, now=None) -> None:
    """Inject stand-ins (tests). No arguments puts everything back."""
    _STATE.update(fetch=fetch, quiz=quiz, open_count=open_count, gate=gate,
                  tier_of=tier_of, spawn=spawn, now=now or time.time)


def _dep(name: str, default):
    return _STATE.get(name) or default


# ---------------------------------------------------------------------------
#   4. Fetching and cleaning the caption text
# ---------------------------------------------------------------------------

_TAGS = re.compile(r"<[^>]{0,200}>")
_ZERO = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)


def _code_of(exc: BaseException) -> str:
    names = {c.__name__ for c in type(exc).__mro__}
    if isinstance(exc, ImportError):
        return "library_missing"
    if isinstance(exc, (TimeoutError,)):
        return "fetch_timeout"
    for name, code in (("TranscriptsDisabled", "no_captions"),
                       ("NoTranscriptFound", "no_captions_language"),
                       ("AgeRestricted", "age_restricted"),
                       ("VideoUnavailable", "video_unavailable"),
                       ("VideoUnplayable", "video_unavailable"),
                       ("InvalidVideoId", "video_unavailable"),
                       ("RequestBlocked", "youtube_refused"),
                       ("IpBlocked", "youtube_refused")):
        if name in names:
            return code
    return "youtube_failed"


def _run_with_deadline(fn: Callable[[], object], seconds: float):
    """The library sets no timeout of its own, so its requests run in a helper
    thread and are abandoned (the thread is a daemon) after `seconds`."""
    box: dict = {}

    def work():
        try:
            box["v"] = fn()
        except BaseException as exc:  # noqa: BLE001 - handed back to the caller
            box["e"] = exc

    t = threading.Thread(target=work, name="jarvis-youtube-fetch", daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise TimeoutError("captions fetch")
    if "e" in box:
        raise box["e"]
    return box["v"]


def clean_text(snippets) -> tuple:
    """(text, minutes_covered_or_None, truncated). Joins the caption lines,
    decodes entities, drops leftover tags, control and zero-width characters,
    collapses spaces, and cuts at TEXT_MAX on a word boundary. `minutes` is
    how far into the video the kept text reaches."""
    parts, total, last_start, cut = [], 0, 0.0, False
    for sn in snippets or []:
        if not isinstance(sn, dict):
            continue
        t = sn.get("text")
        if not isinstance(t, str):
            continue
        t = html.unescape(_TAGS.sub(" ", t)).translate(_ZERO)
        t = "".join(" " if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") else c for c in t)
        t = " ".join(t.split())
        if not t:
            continue
        st = sn.get("start")
        parts.append((t, float(st) if isinstance(st, (int, float)) and not isinstance(st, bool)
                      else last_start))
        total += len(t) + 1
        if total > RAW_MAX:
            cut = True
            break
    kept, size = [], 0
    truncated = cut
    for t, st in parts:
        if size + len(t) + (1 if kept else 0) > TEXT_MAX:
            room = TEXT_MAX - size - (1 if kept else 0)
            if room > 40:
                piece = t[:room]
                if " " in piece:
                    piece = piece[:piece.rfind(" ")]
                if piece:
                    kept.append(piece)
                    last_start = st
            truncated = True
            break
        kept.append(t)
        size += len(t) + (1 if len(kept) > 1 else 0)
        last_start = st
    text = " ".join(kept)
    minutes = int(last_start // 60) + 1 if text and truncated else None
    return text, minutes, truncated


def fetch_captions(video_id: str, languages=DEFAULT_LANGUAGES) -> tuple:
    """(text, minutes, truncated) or YouTubeError."""
    fetch = _dep("fetch", default_fetch)
    try:
        got = _run_with_deadline(lambda: fetch(video_id, tuple(languages)), FETCH_SECONDS)
    except YouTubeError:
        raise
    except BaseException as exc:  # noqa: BLE001 - mapped to plain words, never quoted
        raise YouTubeError(_code_of(exc))
    text, minutes, truncated = clean_text(got)
    if len(text.strip()) < TEXT_MIN:
        raise YouTubeError("too_little_text")
    return text, minutes, truncated


# ---------------------------------------------------------------------------
#   5. Requests: in memory only, one waiting at a time
# ---------------------------------------------------------------------------

_LOCK = threading.RLock()
_REQS: dict = {}          # id -> dict (insertion order)


def _now() -> float:
    return _STATE["now"]()


def _purge() -> None:
    now = _now()
    for k in [k for k, r in _REQS.items()
              if now - r["touched"] > EXPIRY_SECONDS and r["state"] not in ("waiting", "fetching", "writing")]:
        del _REQS[k]
    while len(_REQS) > KEEP_REQUESTS:
        old = next((k for k, r in _REQS.items() if r["state"] not in ("waiting", "fetching", "writing")), None)
        if old is None:
            break
        del _REQS[old]


def _view(r: dict) -> dict:
    return {"id": r["id"], "state": r["state"], "message": r["message"], "link": r["link"],
            "truncated": r["truncated"], "minutes": r["minutes"], "error": r["error"],
            "quiz": r["quiz"], "provenance": "outside", "source": "youtube"}


def _set(r: dict, state: str, *, message: str = "", error: Optional[str] = None) -> None:
    with _LOCK:
        r["state"] = state
        r["message"] = message or STATE_WORDS.get(state, "")
        r["error"] = error
        r["touched"] = _now()


def _fail(r: dict, code: str) -> None:
    _set(r, "failed", message=CLASSES[code][1], error=code)
    _audit("youtube.captions", {"outcome": "failed", "error": code})


def _person_said_yes(v) -> bool:
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


def _decide(r: dict, parsed: dict, count: int, title: str, languages: tuple) -> None:
    gate = _dep("gate", _gate)
    tier_of = _dep("tier_of", _tier)
    text = card(parsed)
    detail = {"text": text, "what": "read a YouTube video's captions for a quiz",
              "to": parsed["canonical"], "leaves_this_pc": True}
    try:
        v = gate(ACTION, detail, text)
    except Exception:
        _set(r, "refused")
        _audit("youtube.card", {"outcome": "refused"})
        return
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(ACTION) != "ask":
        _set(r, "refused")
        _audit("youtube.card", {"outcome": "refused"})
        return
    if not _person_said_yes(v):
        state = outcome if outcome in ("denied", "timed_out") else "refused"
        _set(r, state)
        _audit("youtube.card", {"outcome": state})
        return
    with _LOCK:
        if r["state"] == "withdrawn":
            _audit("youtube.card", {"outcome": "withdrawn"})
            return
        _set(r, "fetching")
    _audit("youtube.card", {"outcome": "approved"})
    try:
        body, minutes, truncated = fetch_captions(parsed["video_id"], languages)
    except YouTubeError as e:
        return _fail(r, e.code)
    except Exception:
        return _fail(r, "youtube_failed")
    with _LOCK:
        r["minutes"], r["truncated"] = minutes, truncated
        _set(r, "writing")
    try:
        quiz = _dep("quiz", default_quiz)(body, count, title)
    except Exception as exc:  # jarvis_quiz.QuizError carries a .code
        code = getattr(exc, "code", "")
        return _fail(r, code if code in ("model_unavailable", "too_many_quizzes") and code in CLASSES
                     else "quiz_failed")
    finally:
        body = ""  # the caption text is not kept here once the quiz holds it
    with _LOCK:
        r["quiz"] = quiz
        msg = STATE_WORDS["ready"]
        if truncated:
            msg = (f"Ready. The video is long, so the quiz covers only the first part"
                   + (f" (about {minutes} minutes)." if minutes else "."))
        _set(r, "ready", message=msg)
    _audit("youtube.captions", {"outcome": "ready", "truncated": bool(truncated)})


def start(body, *, tainted: bool = False) -> tuple:
    """POST /api/youtube/quiz {"url", "count"?, "title"?, "language"?}. (code, body).
    202 and ONE card; nothing is fetched before a yes."""
    if not isinstance(body, dict):
        return _refuse("bad_link")
    try:
        if tainted:
            raise YouTubeError("outside_text_turn")
        parsed = parse_link(body.get("url"))
        count = body.get("count", COUNT_DEFAULT)
        if count is None:
            count = COUNT_DEFAULT
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10:
            raise YouTubeError("bad_count")
        lang = body.get("language")
        languages = DEFAULT_LANGUAGES
        if lang is not None:
            if not isinstance(lang, str) or not _LANG.match(lang.strip()):
                raise YouTubeError("bad_language")
            languages = (lang.strip(),)
        title = body.get("title")
        title = " ".join(title.split())[:80] if isinstance(title, str) and title.strip() else DEFAULT_TITLE
        if _dep("tier_of", _tier)(ACTION) != "ask":
            raise YouTubeError("tier_not_ask")
        if _dep("open_count", default_open_count)() >= 3:
            raise YouTubeError("too_many_quizzes")
    except YouTubeError as e:
        return _refuse(e.code)
    with _LOCK:
        _purge()
        if any(r["state"] == "waiting" for r in _REQS.values()):
            return _refuse("request_waiting")
        rid = uuid.uuid4().hex[:12]
        r = {"id": rid, "state": "waiting", "message": STATE_WORDS["waiting"],
             "link": parsed["canonical"], "truncated": False, "minutes": None, "error": None,
             "quiz": None, "touched": _now()}
        _REQS[rid] = r
    try:
        _dep("spawn", _spawn)(lambda: _decide(r, parsed, count, title, languages))
    except Exception:
        with _LOCK:
            _REQS.pop(rid, None)
        return _refuse("card_unavailable")
    with _LOCK:
        _purge()
    return 202, {"ok": True, "waiting": True, "request": _view(r),
                 "message": "Waiting for your yes. Nothing is fetched unless you approve the card."}


def _refuse(code: str) -> tuple:
    status, words = CLASSES[code]
    return status, {"ok": False, "error": code, "message": words}


def show(rid: str) -> tuple:
    with _LOCK:
        _purge()
        r = _REQS.get(rid)
        if r is None:
            return _refuse("not_found")
        return 200, {"ok": True, "request": _view(r)}


def cancel(rid: str) -> tuple:
    with _LOCK:
        r = _REQS.get(rid)
        if r is None:
            return _refuse("not_found")
        if r["state"] != "waiting":
            if r["state"] in ("fetching", "writing"):
                return _refuse("already_started")
            return 200, {"ok": True, "request": _view(r)}
        _set(r, "withdrawn")
        return 200, {"ok": True, "request": _view(r)}


def status() -> tuple:
    """GET /api/youtube: that the feature is here, its words and limits, and the
    newest request (if any)."""
    with _LOCK:
        _purge()
        newest = next(reversed(_REQS.values()), None)
        return 200, {"ok": True, "available": True, "title": TITLE, "intro": INTRO,
                     "terms": TERMS, "outside": OUTSIDE_LINE,
                     "limits": {"link": LINK_MAX, "text": TEXT_MAX,
                                "count_min": 1, "count_max": 10},
                     "latest": _view(newest) if newest else None}


# ---------------------------------------------------------------------------
#   6. Routes
# ---------------------------------------------------------------------------

_ROUTE = re.compile(r"^/api/youtube/([0-9a-f]{12})(?:/(cancel))?$")


def owns(method: str, route: str) -> bool:
    if method == "GET":
        return route == PATH or bool(re.match(r"^/api/youtube/[0-9a-f]{12}$", route))
    if route == QUIZ_ROUTE:
        return True
    m = _ROUTE.match(route)
    return bool(m and m.group(2))


def handle_get(route: str) -> tuple:
    if route == PATH:
        return status()
    m = _ROUTE.match(route)
    return show(m.group(1)) if m and not m.group(2) else _refuse("not_found")


def handle_post(route: str, body) -> tuple:
    if route == QUIZ_ROUTE:
        return start(body)
    m = _ROUTE.match(route)
    if m and m.group(2) == "cancel":
        return cancel(m.group(1))
    return _refuse("not_found")


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so the YouTube routes are answered
    here, after the server's own origin and token checks (the shape
    jarvis_quiz.install uses). Every other request goes to the original."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_youtube", False):
        return "  youtube    Quiz on a YouTube video (already on)"

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

    def _path(self) -> str:
        return urllib.parse.urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")

    def do_GET(self):
        route = _path(self)
        if not owns("GET", route):
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = _path(self)
        if not owns("POST", route):
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        try:
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_youtube = True
    do_POST._jarvis_youtube = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return "  youtube    Quiz on a YouTube video (one card per link, caption text only)"


def _reset_for_tests() -> None:
    with _LOCK:
        _REQS.clear()
    configure()
