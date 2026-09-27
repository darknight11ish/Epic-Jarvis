"""jarvis_news.py - news headlines in the morning briefing, from RSS/Atom
feed addresses the owner names.

NEW MODULE, shipped whole. news.patch adds one call at start-up,
`install(Handler, ...)` (the same shape as jarvis_stop_all.py and
jarvis_documents.py), which answers GET /api/news, POST /api/news/add and
POST /api/news/remove. docs/JARVIS-API.md section (see backend/README.md
"News headlines").

THE OWNER'S DECISION (CLAUDE.md, 2026-09-27, feasibility I49; design source
docs/CUTTING-EDGE-2026-09-26-round3-knowledge.md, question 2): "News
headlines and 'tell me when this page changes': yes, the safe version - one
card per address the owner adds, read-only, never follows links elsewhere,
never acts on what it reads, outside text; queued with the small items."

THE LIST - empty by default, kept in news_feeds.json in the Jarvis settings
folder, the same shape as "Folders Jarvis may look in" (jarvis_documents.py) -
except there is no dedicated settings screen for it in either app: it is
added and removed by the owner's own words, exactly like "tell me when"
needs no setup form ("add this feed: <url>", "remove that feed: <url>",
"what news feeds do i have" - jarvis_quick.py's `_run_news_add` etc., no
model). `request_add`/`request_remove` are the same functions the HTTP
routes below call, so a settings screen can still be added later without
changing this module.
  * Adding a feed: ONE approval card (action `change_own_config`, tier
    "ask" only - the shape of every setting that lets Jarvis reach one more
    thing), from either app. The card shows the address in full and says
    plainly: headlines only, never the article text, and Jarvis never
    follows a link on the feed anywhere else.
  * Removing one: at once, no card, from either app.
  * Refused outright: anything that is not `http://` or `https://`, and any
    address that resolves - by a REAL DNS lookup, not spelling, done again
    on every fetch - to this PC or a private network address
    (`jarvis_local_http.private_fetch_problem`; the same guard "tell me
    when this page changes" uses, since both are an address the owner
    typed meant to be on the open internet).

WHAT JARVIS READS, AND NEVER READS
One plain GET of the FEED address itself - never a linked article, ever
("never follows links elsewhere" is not a policy on top of the code, it is
the whole of what this module knows how to do: there is no function here
that follows a link). Only each item's TITLE is kept, at most
MAX_HEADLINES_PER_FEED per feed, each capped at MAX_HEADLINE_CHARS. The
feed's other fields (description, content, author) are never read. A
document is refused outright if it declares a DOCTYPE or an ENTITY: a real
RSS or Atom feed never needs either, and refusing them is the one thing
that keeps this module's other-people's-XML entirely out of that trouble
(an external entity fetch, or an internal one crafted to blow up in
memory - "billion laughs") without adding a dependency such as defusedxml
for a threat a plain refusal already removes.

HEADLINES ARE OUTSIDE TEXT
A feed can say anything in its own words, so a headline is treated exactly
like a calendar title or an email's From line (jarvis_briefing.py's own
reasoning): never learned as a fact, and a briefing line that shows one
marks the turn as having read outside text.

THE GATE, EVERY FETCH
Each fetch (for the briefing, or "read me the news") asks jarvis_gate as
`news_read` first, like the morning briefing's other reads, and only runs
when that tier is "auto" - a fetch is not something Jarvis can ask about
every time the briefing runs, so a stricter tier means the section is left
out and says why, the same shape jarvis_briefing.py already gives weather
and email.

    python3 test_news.py
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

PATH = "/api/news"
ADD_ROUTE = "/api/news/add"
REMOVE_ROUTE = "/api/news/remove"

# --------------------------------------------------------------------------
#   Words both apps show (jarvis-desktop/src/news.js, jarvis-client
#   net/News.kt - see the briefing's shared wording tests for the pattern)
# --------------------------------------------------------------------------

TITLE = "News feeds"
DETAIL = ("Jarvis can show headlines in your morning briefing from RSS or Atom feed "
          "addresses you add here - headlines only, never the article text, and it never "
          "follows a link on the feed anywhere else. None are listed at first. Adding one "
          "takes an approval card; removing one is instant, from either app.")
EMPTY = "No feeds yet, so the briefing shows no news."
MISSING = "Your PC's Jarvis cannot show news feeds yet - run apply-patches.ps1 on the PC."
WAITING = "Waiting for your yes on the approval card."
REMOVE_LABEL = "Remove"
MAX_FEEDS = 10
MAX_HEADLINES_PER_FEED = 5
MAX_HEADLINE_CHARS = 200
MAX_URL = 500
FEED_TIMEOUT = 10.0
MAX_FEED_BYTES = 2 * 1024 * 1024

CARD_ACTION = "change_own_config"
GATE_ACTION = "news_read"

#: How the last card went, in words the apps show (folders.py's own list).
LAST_WORDS = {
    "added": "Added. The briefing can show its headlines now.",
    "denied": "You said no, so that feed was not added.",
    "timed_out": "Nobody answered the card in time, so that feed was not added.",
    "withdrawn": "You removed it before the card was answered, so it was not added.",
    "refused": "The card could not be answered, so that feed was not added.",
    "failed": "It was approved, but the list could not be saved, so that feed was not added.",
}


# --------------------------------------------------------------------------
#   Settings, the gate, the clock - replaceable, so the tests open nothing
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def settings_path() -> Path:
    return _config_dir() / "news_feeds.json"


def _tier(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-news-card", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    # Counts and outcomes only. Never a feed's address.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   The list
# --------------------------------------------------------------------------

_S_LOCK = threading.RLock()
_DAMAGED = "the list of news feeds is damaged, so the briefing shows no news - add them again"


def load() -> dict:
    """{"feeds": [{"id", "url", "title", "added"}], "why": str}."""
    try:
        raw = settings_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"feeds": [], "why": ""}
    except OSError as exc:
        return {"feeds": [], "why": f"the list of news feeds could not be read "
                                    f"({type(exc).__name__}), so the briefing shows no news"}
    try:
        doc = json.loads(raw)
        items = doc.get("feeds") if isinstance(doc, dict) else None
        if not isinstance(items, list):
            raise ValueError
        out = []
        for it in items[:MAX_FEEDS]:
            if not isinstance(it, dict) or not isinstance(it.get("url"), str):
                raise ValueError
            added = it.get("added")
            out.append({"id": str(it.get("id") or uuid.uuid4().hex[:10]), "url": it["url"],
                        "title": str(it.get("title") or ""),
                        "added": float(added) if isinstance(added, (int, float))
                        and not isinstance(added, bool) else 0.0})
    except Exception:
        return {"feeds": [], "why": _DAMAGED}
    return {"feeds": out, "why": ""}


def feeds() -> list:
    """The listed feeds' addresses, as kept."""
    return [f["url"] for f in load()["feeds"]]


def _save(items: list) -> None:
    with _S_LOCK:
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({"feeds": items, "changed": time.time()}, indent=1),
                       encoding="utf-8")
        os.replace(tmp, p)


def _key(url: str) -> str:
    return url.strip().rstrip("/").lower()


def check_feed(url) -> str:
    """The address, as it would be kept, or ValueError with a sentence.
    Syntax only - never a network call, so listing or checking a feed's
    settings never opens a socket. `add_feed`/the route also runs
    `private_fetch_problem` before ever raising a card."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("say the feed's address, starting with http:// or https://")
    raw = url.strip()
    if len(raw) > MAX_URL or any(ord(ch) < 0x20 for ch in raw):
        raise ValueError("that is not a web address")
    if not re.match(r"^https?://", raw, re.IGNORECASE):
        raise ValueError("a feed's address starts with http:// or https://")
    return raw


# --------------------------------------------------------------------------
#   Reading a feed - one GET, titles only, never a link on it
# --------------------------------------------------------------------------

class _FeedRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses to follow a redirect anywhere the private-address check
    would refuse in the first place."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        import jarvis_local_http as LH
        problem = LH.private_fetch_problem(newurl)
        if problem:
            raise urllib.error.HTTPError(
                req.full_url, code,
                f"refused to follow a redirect to {newurl}: {problem}", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_fetch(url: str) -> bytes:
    import jarvis_local_http as LH
    req = urllib.request.Request(url, headers={"User-Agent": "Jarvis (news headlines)",
                                                "Accept": "application/rss+xml, "
                                                          "application/atom+xml, "
                                                          "application/xml, text/xml"})
    # public_urlopen, not urlopen: the private-address check is made again on
    # the connection itself, against the address it connects to (DNS
    # rebinding between read_feed's check and this connect - the
    # security/privacy audit of 2026-09-27).
    with LH.public_urlopen(req, FEED_TIMEOUT, _FeedRedirect()) as resp:
        return resp.read(MAX_FEED_BYTES + 1)[:MAX_FEED_BYTES]


def _text_of(el) -> str:
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


class _Declares(Exception):
    pass


def _declares_doctype(raw: bytes) -> bool:
    """Does `raw` declare a DOCTYPE or an ENTITY, in ANY encoding the XML
    parser itself would read it in?

    The byte search alone was not enough (security/privacy audit,
    2026-09-27): a feed sent as UTF-16 spells "<!DOCTYPE" with a zero byte
    after every letter, so the search found nothing while ElementTree -
    which reads UTF-16 - expanded its entities. So the same parser
    (expat) reads it once first, and is stopped the moment it meets either
    declaration, before any entity is expanded. A document it cannot read
    at all is left to ElementTree, which then fails on it too."""
    if re.search(rb"<!DOCTYPE|<!ENTITY", raw, re.IGNORECASE):
        return True
    import xml.parsers.expat

    def _stop(*_args):
        raise _Declares()

    p = xml.parsers.expat.ParserCreate()
    p.StartDoctypeDeclHandler = _stop
    p.EntityDeclHandler = _stop
    try:
        p.Parse(raw, True)
    except _Declares:
        return True
    except Exception:
        return False
    return False


def parse_headlines(raw: bytes, cap: int = MAX_HEADLINES_PER_FEED) -> list:
    """Titles only, from an RSS 2.0 (<rss><channel><item><title>) or Atom
    (<feed><entry><title>) document - whichever it is. Refuses outright a
    document with a DOCTYPE or an ENTITY declaration (see the module
    docstring's "HEADLINES ARE OUTSIDE TEXT" section, above that): a real
    feed never needs either, so refusing them keeps this parser out of
    XML's entity tricks without a second dependency."""
    if _declares_doctype(raw):
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    out = []
    for item in root.iter():
        tag = item.tag.rsplit("}", 1)[-1] if isinstance(item.tag, str) else ""
        if tag not in ("item", "entry"):
            continue
        title = ""
        for child in item:
            ctag = child.tag.rsplit("}", 1)[-1] if isinstance(child.tag, str) else ""
            if ctag == "title":
                title = _text_of(child)
                break
        if title:
            out.append(title[:MAX_HEADLINE_CHARS])
        if len(out) >= cap:
            break
    return out


def feed_title(raw: bytes) -> str:
    """The feed's OWN title (<channel><title> or <feed><title>), for the
    list - "" if it cannot be read. Never shown as a headline."""
    if _declares_doctype(raw):
        return ""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return ""
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str) else ""
        if tag == "title":
            return _text_of(el)[:120]
    return ""


@dataclass
class Deps:
    tier_of: Callable[[str], str] = _tier
    gate: Callable = _gate
    #: (url) -> raw bytes. None: the real one (_default_fetch).
    fetch: Optional[Callable[[str], bytes]] = None


DEPS = Deps()


def read_feed(url: str, *, deps: Optional[Deps] = None, purpose: str = "the morning briefing"
              ) -> dict:
    """One GET of `url`, gated as `news_read`, only when that tier is
    "auto" or "notify" (see the module docstring's "THE GATE" section - the
    same two tiers the briefing's weather and calendar reads accept, since
    this runs about once a day, not every few minutes like a "tell me
    when" look). {"ok", "headlines": [...], "title": str} or
    {"ok": False, "why": str}."""
    deps = deps or DEPS
    import jarvis_local_http as LH
    problem = LH.private_fetch_problem(url)
    if problem:
        return {"ok": False, "why": problem}
    if deps.tier_of(GATE_ACTION) not in ("auto", "notify"):
        return {"ok": False, "why": "your settings ask for a yes each time Jarvis reads a "
                                    "news feed, and the briefing does not raise a card for "
                                    "that"}
    text = (f"Jarvis would like to fetch {url} for {purpose}: headlines only, from a feed you "
            "already approved - never an article's own page.")
    try:
        v = deps.gate(GATE_ACTION, {"text": text, "for": purpose, "url": url}, text)
    except Exception:
        v = None
    if getattr(v, "allowed", False) is not True:
        return {"ok": False, "why": "the approval gate did not let this read run"}
    fetch = deps.fetch or _default_fetch
    try:
        raw = fetch(url)
    except Exception as exc:
        return {"ok": False, "why": f"the feed did not answer ({type(exc).__name__})"}
    return {"ok": True, "headlines": parse_headlines(raw), "title": feed_title(raw)}


# --------------------------------------------------------------------------
#   The briefing's News section (jarvis_briefing.py calls this; its own
#   _news_source() gives the "What it includes" line, the same shape as
#   _weather_source, since it also needs [autonomy.tiers] read the same
#   way jarvis_briefing.Deps does)
# --------------------------------------------------------------------------

def read_news(*, deps: Optional[Deps] = None) -> dict:
    """Every listed feed, read in turn (never in parallel - a slow or dead
    feed then costs seconds, never opens several sockets to servers the
    owner has not necessarily vetted for that). A section for
    jarvis_briefing.build(), the same shape as a weather/calendar section:
    {"key": "news", "title", "state", "summary", "items"}. `read` is not
    set here: jarvis_briefing.py marks the turn once a headline is really
    IN the briefing text, the same way it marks calendar and email."""
    deps = deps or DEPS
    st = load()
    if st["why"]:
        return {"key": "news", "title": TITLE, "state": "failed", "summary": st["why"],
                "items": []}
    rows = st["feeds"]
    if not rows:
        return {"key": "news", "title": TITLE, "state": "empty", "summary": EMPTY, "items": []}
    items, failed = [], 0
    for row in rows:
        out = read_feed(row["url"], deps=deps)
        if not out.get("ok"):
            failed += 1
            continue
        label = row.get("title") or out.get("title") or row["url"]
        for h in out.get("headlines") or []:
            items.append(f"{label}: {h}")
    if not items:
        why = ("Not read: none of your feeds answered." if failed == len(rows)
               else "Your feeds had no headlines right now.")
        return {"key": "news", "title": TITLE, "state": "empty" if failed < len(rows)
               else "failed", "summary": why, "items": []}
    summary = f"{len(items)} headline{'s' if len(items) != 1 else ''}" + (
        f" ({failed} feed{'s' if failed != 1 else ''} did not answer)" if failed else "") + "."
    return {"key": "news", "title": TITLE, "state": "ok", "summary": summary, "items": items}


# --------------------------------------------------------------------------
#   The view
# --------------------------------------------------------------------------

def view(*, here: bool = True) -> dict:
    st = load()
    with _P_LOCK:
        waiting = dict(_P_STATE["pending"]) or None
        last = dict(_P_STATE["last"]) or None
    return {
        "available": True, "title": TITLE, "detail": DETAIL,
        "feeds": [{"id": f["id"], "url": f["url"], "title": f["title"], "added": f["added"]}
                  for f in st["feeds"]],
        "empty": EMPTY, "why": st["why"], "can_add": bool(here), "max": MAX_FEEDS,
        "waiting": {"url": waiting["url"]} if waiting else None,
        "waiting_words": WAITING if waiting else "",
        "last": last, "remove_label": REMOVE_LABEL,
    }


# --------------------------------------------------------------------------
#   Adding - ONE card, from either app; removing - at once
# --------------------------------------------------------------------------

_P_LOCK = threading.Lock()
_P_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}, "latest": {}}


def card(url: str) -> str:
    return "\n".join([
        "Let Jarvis show headlines from this feed?",
        "",
        f"Feed: {url}",
        "",
        "From now on, Jarvis's morning briefing (and \"read me the news\") can show this "
        "feed's headlines. It reads only the feed itself, on a plain schedule - never an "
        "article's own page, and never any other link on the feed. The article text is "
        "never read, only each item's title.",
        "",
        "Refused if that address turns out to lead to this PC or a private network address, "
        "checked again on every read, in case that changes.",
        "",
        "Headlines are outside text: a headline can say anything, so it is never learned as "
        "a fact about you, and it marks the conversation as having read outside text, "
        "exactly like a calendar title.",
        "",
        "Removing the feed from the list is instant, from either app.",
        "",
        "If you did not just do this, say no.",
        "",
        "If you say no: nothing changes.",
    ])


def _finish(pid: str, outcome: str, why: str = "") -> None:
    with _P_LOCK:
        if _P_STATE["pending"].get("id") == pid:
            _P_STATE["pending"].clear()
        _P_STATE["withdrawn"].discard(pid)
        if _P_STATE["latest"].get("id") not in (None, pid):
            return
        _P_STATE["last"].clear()
        _P_STATE["last"].update(outcome=outcome, why=why, at=time.time(),
                                message=LAST_WORDS.get(outcome, ""))
    _audit("news.add.card", {"outcome": outcome})


def _add_now(url: str) -> None:
    with _S_LOCK:
        st = load()
        items = [] if st["why"] else [dict(f) for f in st["feeds"]]
        if any(_key(f["url"]) == _key(url) for f in items):
            return
        if len(items) >= MAX_FEEDS:
            raise OverflowError("the list is full")
        items.append({"id": uuid.uuid4().hex[:10], "url": url, "title": "", "added": time.time()})
        _save(items)


def _person_said_yes(v) -> bool:
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


def _decide(pid: str, url: str, gate: Callable, tier_of: Callable,
            write: Callable[[str], None]) -> None:
    text = card(url)
    detail = {"text": text, "what": "let Jarvis read one more news feed",
              "setting": "news feeds", "to": url,
              # True: approving it is what lets Jarvis fetch this address from
              # the internet (jarvis_tellme's page card says the same).
              "leaves_this_pc": True}
    try:
        v = gate(CARD_ACTION, detail, text)
    except Exception as exc:
        return _finish(pid, "refused", f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(CARD_ACTION) != "ask":
        return _finish(pid, "refused", f"the gate answered at tier {vtier!r}, which is not "
                                       f"a person saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, outcome)
        return _finish(pid, "refused", str(getattr(v, "reason", "refused"))[:200])
    with _S_LOCK:
        with _P_LOCK:
            withdrawn = pid in _P_STATE["withdrawn"]
        if withdrawn:
            return _finish(pid, "withdrawn")
        try:
            write(url)
        except Exception as exc:
            return _finish(pid, "failed", type(exc).__name__)
    _audit("news.added", {"count": len(feeds())})
    _finish(pid, "added")


def request_add(body, *, gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
                spawn: Optional[Callable] = None,
                write: Optional[Callable[[str], None]] = None) -> tuple:
    """POST /api/news/add {"url"}. (code, body). 202 and ONE card."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    write = write or _add_now
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": 'need {"url": "<a feed address>"}'}
    try:
        url = check_feed(body.get("url"))
    except ValueError as exc:
        return 400, {"ok": False, "error": _sentence(exc)}
    import jarvis_local_http as LH
    problem = LH.private_fetch_problem(url)
    if problem:
        return 400, {"ok": False, "error": problem}
    st = load()
    for f in st["feeds"]:
        if _key(f["url"]) == _key(url):
            return 200, {"ok": True, "changed": False, "view": view(),
                         "message": "That feed is already on the list."}
    if len(st["feeds"]) >= MAX_FEEDS:
        return 409, {"ok": False, "error": f"The list already has {MAX_FEEDS} feeds - remove "
                                           f"one first."}
    t = tier_of(CARD_ACTION)
    if t != "ask":
        return 503, {"ok": False, "error": (
            f"{CARD_ACTION} is tier {t!r} in jarvis-framework.toml; adding a feed needs a "
            f"person to say yes, so it must be 'ask'")}
    with _P_LOCK:
        if _P_STATE["pending"]:
            return 409, {"ok": False, "error": "A card to add a feed is already waiting - "
                                               "answer it first."}
        pid = uuid.uuid4().hex
        _P_STATE["pending"].update(id=pid, url=url, since=time.time())
        _P_STATE["latest"]["id"] = pid
    try:
        spawn(lambda: _decide(pid, url, gate, tier_of, write))
    except Exception:
        with _P_LOCK:
            _P_STATE["pending"].clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "view": view(),
                 "message": "Waiting for your approval. Nothing is added unless you approve "
                            "the card."}


def request_remove(body) -> tuple:
    """POST /api/news/remove {"url"} or {"id"}. At once, no card, either app."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": 'need {"url": "<a feed on the list>"} or {"id"}'}
    want_url = body.get("url") if isinstance(body.get("url"), str) else ""
    want_id = body.get("id") if isinstance(body.get("id"), str) else ""
    if not want_url and not want_id:
        return 400, {"ok": False, "error": 'need {"url": "<a feed on the list>"} or {"id"}'}
    removed = False
    with _S_LOCK:
        with _P_LOCK:
            p = _P_STATE["pending"]
            if p and ((want_url and _key(p.get("url", "")) == _key(want_url))):
                _P_STATE["withdrawn"].add(p["id"])
                p.clear()
                removed = True
        st = load()
        items = [dict(f) for f in st["feeds"]]
        kept = [f for f in items
                if not ((want_id and f["id"] == want_id)
                        or (want_url and _key(f["url"]) == _key(want_url)))]
        if len(kept) != len(items):
            try:
                _save(kept)
            except Exception as exc:
                return 500, {"ok": False, "error": f"could not save the list "
                                                   f"({type(exc).__name__})"}
            removed = True
    _audit("news.removed", {"count": len(feeds())})
    return 200, {"ok": True, "changed": removed, "view": view(),
                 "message": ("Removed. The briefing no longer shows that feed." if removed
                             else "That feed was not on the list.")}


def _sentence(exc) -> str:
    s = str(exc).strip() or type(exc).__name__
    s = s[:1].upper() + s[1:]
    return s if s.endswith((".", "?", "!")) else s + "."


# --------------------------------------------------------------------------
#   "Read me the news" (jarvis_quick.py, without the model)
# --------------------------------------------------------------------------

def sentence(*, deps: Optional[Deps] = None) -> dict:
    """{"said", "read"} - one answer for "read me the news" / "what's in
    the news". Its own gate check, its own read marker; never the model."""
    sec = read_news(deps=deps)
    if sec["state"] in ("empty", "failed"):
        return {"said": sec["summary"], "read": []}
    lines = [sec["summary"]] + [f"- {i}" for i in sec["items"][:15]]
    return {"said": "\n".join(lines), "read": [GATE_ACTION]}


# --------------------------------------------------------------------------
#   The route both apps call
# --------------------------------------------------------------------------

def handle_get() -> tuple:
    return 200, view()


def handle_post(route: str, body) -> tuple:
    if route == ADD_ROUTE:
        return request_add(body)
    return request_remove(body)


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so the news routes are
    answered here, after the server's own origin and token checks. Every
    other request goes straight to the original."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_news", False):
        _ARMED = True
        return "  news       News feeds (already on)"

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

    def do_GET(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get()
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in (ADD_ROUTE, REMOVE_ROUTE):
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
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_news = True
    do_POST._jarvis_news = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    return f"  news       News feeds: {len(feeds())} listed"


_ARMED = False


def _reset_for_tests() -> None:
    global _ARMED
    with _P_LOCK:
        _P_STATE["pending"].clear()
        _P_STATE["withdrawn"].clear()
        _P_STATE["last"].clear()
        _P_STATE["latest"].clear()
    _ARMED = False
