"""jarvis_search.py - web search, with a choice of four providers.

NEW MODULE, shipped whole. jarvis_agent.py offers it to the model as the
tool `web_search` (only when `[tools].enabled` names it), web-search.patch
serves its settings to both apps (GET /api/search, POST /api/search/settings
and /api/search/test), and jarvis_quick.py answers "which search should I
use?" from the words below, without the model.

THE OWNER'S DECISIONS (2026-09-25, CLAUDE.md "Decided 2026-09-25")
  - Four providers, SearXNG the default:
      searxng     a search program on this PC, in Docker, at
                  http://127.0.0.1:8888 unless the owner points it at another
                  of their own machines (this PC, the home network,
                  Tailscale or NordVPN Meshnet - jarvis_local_http's rule);
      duckduckgo  the `ddgs` Python library, DuckDuckGo ONLY
                  (backend="duckduckgo"). ddgs's own default, "auto", asks
                  Bing, Google, Brave, Yandex and others, which is not what
                  the owner chose - and if a future ddgs dropped its
                  DuckDuckGo engine, ddgs itself would quietly fall back to
                  "auto", so this module checks the engine is there first
                  and refuses if it is not;
      tavily      https://api.tavily.com/search with the owner's key;
      brave       https://api.search.brave.com/res/v1/web/search with the
                  owner's key.
    Whoogle is left out, and LEFT_OUT says why.
  - Each provider has a short "why use this one" line (WHY), served from the
    PC so both apps show the same words, and used for "which search should I
    use?" (explain()).
  - NO SILENT FALLBACK. If the chosen provider is down - SearXNG not
    running, its JSON output off (403), no key, a key refused, the month's
    allowance used up, rate-limited - the answer says so plainly and offers
    to switch ("SearXNG isn't running on this PC. Switch web search to
    DuckDuckGo?"). A search is never quietly sent to a different provider.
  - When a search asks first: see jarvis_agent.py, WEB_SEARCH_*. By default
    only when private things could slip in; "Ask before every web search"
    (ask_every_time here) makes it ask every time. Turning that ON is
    immediate; turning it OFF is one approval card (ACTION_ASK_LESS), like
    the other settings that loosen something.

THE PERMISSION MODEL (docs/ARCHITECTURE.md section 3)
    plan(query)       works out what would be sent and to whom. Opens NO
                      socket. A plan with a `problem` sends nothing.
    describe(plan)    the card: the EXACT search words, the service they go
                      to, whether a key goes with them, and what saying no
                      costs.
    run(plan, approved=True)   sends it. `approved` has no default of True.

RULE 1 - email, files, credentials and memory stay on this PC. Two guards:
  - a search whose words look like a password or key (jarvis_router's
    looks_like_a_secret, and jarvis_scrub.find_secret, which also knows the
    secrets this PC holds by value) is REFUSED at plan() time, with the
    kind of secret named and never the value;
  - after Jarvis has read email, files, notes, saved memories or other
    outside text, the search waits for a card that shows its exact words
    (jarvis_agent.py).

RULE 3 - the Tavily and Brave keys. Kept in Windows Credential Manager
(KEY_TARGETS, the same store and format as the pairing token -
jarvis_token_store.WindowsStore), put there on the PC only: the desktop's
Settings -> Web search, or `py -3 jarvis_search.py key tavily` (it asks for
the key without showing it). Never typed into the phone: sending a key over
the link to the PC would send it somewhere other than its one service. A key
is read fresh for each search, handed to jarvis_scrub.register_secret so the
log scrubber hides it by value, sent only to its own service's fixed https
address, never with a redirect (_RefuseRedirect), and never logged, printed,
put in a plan, a card, an error or an answer. Its name is not an environment
variable, so it cannot reach a child program (jarvis_child_env).

WHAT GOES OVER THE NETWORK, AND HOW
  - SearXNG: jarvis_local_http's opener - NO proxy, ever (it is on this PC
    or the owner's own network; a proxy is another machine).
  - Tavily and Brave: https only, to a fixed address. The system proxy, if
    the PC has one, is used as for every other https call here
    (jarvis_local_http.opener_for): a proxy sees only scrambled traffic and
    the host name, never the key or the words.
  - DuckDuckGo: ddgs makes its own connections (its `primp` client). Jarvis
    passes it no proxy; ddgs reads DDGS_PROXY by itself if that is set.
    Whether primp also uses the Windows system proxy is NOT checked here.
  - Every response is read up to MAX_BODY bytes; a longer one is refused.
    Every request has a TIMEOUT. Redirects are refused.

RESULTS ARE OUTSIDE TEXT. At most MAX_RESULTS, each {title, url, snippet},
cut to fixed lengths, tags and control characters taken out. jarvis_agent
labels them as data, checks them for planted instructions, and the turn -
and the rest of the conversation - counts as having read outside text, the
same as a web page.

Standard library only; `ddgs` is optional (requirements.txt). Opens nothing
on import.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid as _uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

# --------------------------------------------------------------------------
#   The providers, and the words both apps show
# --------------------------------------------------------------------------

PROVIDERS = ("searxng", "duckduckgo", "tavily", "brave")
DEFAULT_PROVIDER = "searxng"
DEFAULT_SEARXNG_URL = "http://127.0.0.1:8888"

LABEL = {
    "searxng": "SearXNG (on this PC)",
    "duckduckgo": "DuckDuckGo",
    "tavily": "Tavily",
    "brave": "Brave Search",
}

#: "Why use this one" - one or two plain sentences each. Both apps show
#: these words, read from GET /api/search; test_web_search.py checks the
#: desktop's and the phone's own copies (for an older PC) say the same.
WHY = {
    "searxng": (
        "Free, no key and no account: a search program that runs on this PC in "
        "Docker and asks several search engines for you, without their cookies "
        "or trackers. Those engines still see your internet address, and it "
        "needs Docker plus one setting (JSON) switched on."),
    "duckduckgo": (
        "Free, no key, and only one Python package to install (ddgs). It reads "
        "DuckDuckGo's public pages because there is no official way in, so it "
        "can be slowed down or stop working when DuckDuckGo changes, and "
        "DuckDuckGo still sees your internet address."),
    "tavily": (
        "Made for AI assistants: short, clean results, with 1,000 free credits "
        "a month (a basic search uses one). Needs a free account and a key, and "
        "Tavily sees what you search, tied to your key."),
    "brave": (
        "Brave's own independent index, with about $5 of free credit each "
        "month. Needs an account, a payment card to verify it, and a key, and "
        "Brave sees what you search, tied to your key."),
}

#: Why SearXNG is the default - for "why SearXNG?".
DEFAULT_WHY = ("SearXNG is the default because it costs nothing, needs no key or "
               "account, and runs on this PC, so no single search company keeps a "
               "record of your searches.")

#: Left out on purpose, with the reason - shown under the four in both apps.
LEFT_OUT = [
    {"id": "whoogle", "label": "Whoogle",
     "why": ("Not offered: its own README says it no longer returns results, since "
             "Google blocked searching without JavaScript in 2025.")},
]

NEEDS_KEY = frozenset({"tavily", "brave"})

#: Where each provider's words go, for the card. A fixed https address for
#: the two with keys - the key is sent there and nowhere else.
TAVILY_URL = "https://api.tavily.com/search"
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
DDG_HOST = "html.duckduckgo.com"

#: The Tavily and Brave keys, in Windows Credential Manager. The desktop
#: writes them under the same names (jarvis-desktop/src-tauri/src/
#: token_store.rs, SEARCH_KEY_TARGETS - test_web_search.py checks the text).
KEY_TARGETS = {
    "tavily": "Jarvis Backend/Tavily key",
    "brave": "Jarvis Backend/Brave Search key",
}

#: Where each key is made - for the apps and backend/README.md.
KEY_WHERE = {
    "tavily": "https://app.tavily.com (sign in, then API Keys)",
    "brave": "https://api-dashboard.search.brave.com (sign up, add a card, then API Keys)",
}

KEY_ENTRY = ("Keys are entered on the PC only - in the desktop app's Settings, Web "
             "search, or with one line in PowerShell (backend/README.md). The phone "
             "never asks for one: sending a key to the PC would send it somewhere "
             "other than its own service.")

MAX_RESULTS = 5
TITLE_CHARS = 150
SNIPPET_CHARS = 300
URL_CHARS = 500
MAX_QUERY_CHARS = 300
MAX_BODY = 1_000_000          # bytes read from one answer, at most
TIMEOUT = 15.0                # seconds for one request
DDG_GAP = 1.1                 # seconds between two DuckDuckGo searches, at least

#: The one harmless search "Test search" sends.
TEST_QUERY = "wikipedia"

#: The approval card for turning "Ask before every web search" OFF.
ACTION_ASK_LESS = "stop_asking_before_every_web_search"

#: The gate action a search is asked under, when it asks (jarvis_agent.py).
ACTION_SEARCH = "search_the_web"

ASK_EVERY_TIME_LABEL = "Ask before every web search"
ASK_EVERY_TIME_DETAIL = (
    "Off (the default): Jarvis asks first only when private things could slip "
    "into a search - after it has read your email, files, notes, saved memories "
    "or other outside text - and shows you the exact search words. On: it asks "
    "before every search. Turning this on is immediate; turning it off asks you "
    "with an approval card.")

#: The problem codes a search or a test can end in. The apps show `said`;
#: the code is for them to pick an icon or a button.
STATES = ("works", "not_running", "json_off", "key_missing", "key_refused",
          "quota_used", "rate_limited", "not_installed", "no_results", "timeout",
          "not_allowed", "blocked", "failed", "secret", "settings_damaged", "empty")


# --------------------------------------------------------------------------
#   Settings: <config folder>/web-search.json
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    """The same folder the rest of the backend uses, found the same way."""
    fw = sys.modules.get("jarvis_framework")
    if fw is None:
        try:
            import jarvis_framework as fw  # type: ignore
        except Exception:
            fw = None
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def settings_path() -> Path:
    return _config_dir() / "web-search.json"


_SETTINGS_LOCK = threading.Lock()

_DAMAGED = ("the web search settings file is damaged, so Jarvis does not know which "
            "search you chose and searches nothing. Choose a search again in Settings, "
            "Web search, to rewrite it")


def settings() -> dict:
    """{"provider", "searxng_url", "ask_every_time", "why"}.

    No file: the owner's defaults (SearXNG on this PC, asking only when
    private things could slip in). A damaged file fails CLOSED, both ways:
    no provider at all (a search is never sent to one the owner did not
    choose) and "ask every time" on."""
    try:
        raw = settings_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"provider": DEFAULT_PROVIDER, "searxng_url": DEFAULT_SEARXNG_URL,
                "ask_every_time": False, "why": ""}
    except OSError as exc:
        return {"provider": None, "searxng_url": DEFAULT_SEARXNG_URL,
                "ask_every_time": True,
                "why": f"the web search settings file could not be read "
                       f"({type(exc).__name__}), so Jarvis searches nothing"}
    try:
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise ValueError
    except Exception:
        return {"provider": None, "searxng_url": DEFAULT_SEARXNG_URL,
                "ask_every_time": True, "why": _DAMAGED}
    provider = doc.get("provider", DEFAULT_PROVIDER)
    url = doc.get("searxng_url", DEFAULT_SEARXNG_URL)
    ask = doc.get("ask_every_time", False)
    why = ""
    if provider not in PROVIDERS:
        provider, why = None, _DAMAGED
    if not isinstance(url, str) or searxng_url_problem(url):
        url, why = DEFAULT_SEARXNG_URL, why or _DAMAGED
        if provider == "searxng":
            provider = None
    if not isinstance(ask, bool):
        ask, why = True, why or _DAMAGED
    return {"provider": provider, "searxng_url": url, "ask_every_time": ask, "why": why}


def _save(**changes) -> dict:
    with _SETTINGS_LOCK:
        cur = settings()
        # A damaged file's provider stays unknown (null) until the owner
        # chooses one: changing another setting must not quietly pick one.
        new = {"provider": cur["provider"],
               "searxng_url": cur["searxng_url"],
               "ask_every_time": cur["ask_every_time"]}
        new.update(changes)
        new["changed"] = time.time()
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(new), encoding="utf-8")
        os.replace(tmp, p)
    return settings()


def searxng_url_problem(url: str) -> str:
    """"" when `url` is an address SearXNG may be reached at, else why not.

    Only this PC or the owner's own networks (jarvis_local_http's rule for
    plain http://, applied here to https:// too): SearXNG is the owner's own
    program, and a search program somewhere on the internet is not the
    choice the owner made. Judged by spelling alone - nothing is looked up.
    No user name or password in it, no query and no fragment."""
    url = str(url or "").strip()
    if not url:
        return "the address is empty"
    if len(url) > 200:
        return "the address is too long"
    if any(ord(c) < 33 or c in "\"'<>\\`" for c in url):
        return "the address has a space or a character an address cannot have"
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port   # raises ValueError for a bad port
    except ValueError:
        return "the address cannot be read"
    if parts.scheme.lower() not in ("http", "https"):
        return "the address must start with http:// or https://"
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return "the address must not hold a user name or password"
    if parts.query or parts.fragment:
        return "the address must not have a ? or # part"
    del port
    try:
        import jarvis_local_http as LH
    except Exception:
        return "jarvis_local_http.py is missing, so the address cannot be checked"
    host = parts.hostname or ""
    if not (LH._own_network(host) and LH._own_network(LH._dialled_host(url))):
        return (f"{host or 'that address'} is not this PC or one of your own networks "
                f"(your home network, Tailscale or NordVPN Meshnet). SearXNG runs on your "
                f"own machine; Jarvis does not send searches to a SearXNG on the internet")
    return ""


# --------------------------------------------------------------------------
#   The keys (rule 3) - Windows Credential Manager only
# --------------------------------------------------------------------------

#: Tests replace this with a factory of fake stores: target -> store with
#: read() / write(value) / delete().
_STORE_FACTORY: Optional[Callable[[str], object]] = None


def _store(provider: str):
    target = KEY_TARGETS[provider]
    if _STORE_FACTORY is not None:
        return _STORE_FACTORY(target)
    import jarvis_token_store as T
    return T.WindowsStore(target)


_KEY_RE = re.compile(r"^[\x21-\x7e]{8,200}$")


def key_problem(value) -> str:
    """"" for something that can be a key, else why not. Never quotes it."""
    if not isinstance(value, str):
        return "the key must be text"
    v = value.strip()
    if not v:
        return "the key is empty"
    if not _KEY_RE.match(v):
        return ("the key must be 8 to 200 plain characters with no spaces - check that "
                "the whole key was copied, and nothing else")
    return ""


def _key(provider: str) -> str:
    """The saved key, or "". Registered with the log scrubber so it is hidden
    by value wherever it might appear. Never logged or returned to an app."""
    if provider not in KEY_TARGETS:
        return ""
    try:
        value = (_store(provider).read() or "").strip()
    except Exception:
        return ""
    if key_problem(value):
        return ""
    try:
        import jarvis_scrub
        jarvis_scrub.register_secret(value)
    except Exception:
        pass
    return value


def key_saved(provider: str) -> Optional[bool]:
    """True / False, or None when Credential Manager cannot be asked."""
    if provider not in KEY_TARGETS:
        return None
    try:
        value = (_store(provider).read() or "").strip()
    except Exception:
        return None
    return bool(value) and not key_problem(value)


def save_key(provider: str, value: str) -> dict:
    """Save a key in Credential Manager. For the owner's own command line
    (`py -3 jarvis_search.py key tavily`); there is NO route for it - the
    desktop writes Credential Manager itself, and the phone never sends one."""
    if provider not in KEY_TARGETS:
        return {"ok": False, "error": "only Tavily and Brave Search use a key"}
    why = key_problem(value)
    if why:
        return {"ok": False, "error": why}
    try:
        store = _store(provider)
        store.write(value.strip())
        back = (store.read() or "").strip()
    except Exception as exc:
        # The exception's name only: some carry the value they were given.
        return {"ok": False, "error": f"Credential Manager refused ({type(exc).__name__})"}
    if back != value.strip():
        return {"ok": False, "error": "the key read back from Credential Manager did not match"}
    return {"ok": True, "said": f"Saved your {LABEL[provider]} key in Windows Credential "
                                f"Manager, as \"{KEY_TARGETS[provider]}\"."}


def forget_key(provider: str) -> dict:
    if provider not in KEY_TARGETS:
        return {"ok": False, "error": "only Tavily and Brave Search use a key"}
    try:
        _store(provider).delete()
    except Exception as exc:
        return {"ok": False, "error": f"Credential Manager refused ({type(exc).__name__})"}
    return {"ok": True, "said": f"Removed your {LABEL[provider]} key from this PC."}


# --------------------------------------------------------------------------
#   Is the provider ready? (no socket)
# --------------------------------------------------------------------------

def _ddgs_installed() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("ddgs") is not None
    except Exception:
        return False


PIP_LINE = "py -3 -m pip install ddgs"

#: Which other provider to OFFER when one is down - offered, never used.
_OFFER = {"searxng": "duckduckgo", "duckduckgo": "searxng",
          "tavily": "searxng", "brave": "searxng"}


def offer_line(provider: Optional[str]) -> str:
    other = _OFFER.get(provider or "", DEFAULT_PROVIDER)
    return (f"Switch web search to {LABEL[other]}? Say \"use {_SAY[other]} for web "
            f"search\", or choose it in Settings, Web search.")


_SAY = {"searxng": "SearXNG", "duckduckgo": "DuckDuckGo", "tavily": "Tavily",
        "brave": "Brave"}


def readiness(provider: Optional[str], s: Optional[dict] = None) -> tuple:
    """(state, said) worked out WITHOUT a socket: ("", "") when nothing
    stands in the way yet (SearXNG running or not is only known by asking)."""
    s = s or settings()
    if provider is None:
        return "settings_damaged", s.get("why") or _DAMAGED
    if provider == "searxng":
        why = searxng_url_problem(s.get("searxng_url") or "")
        if why:
            return "not_allowed", f"The SearXNG address cannot be used: {why}."
        return "", ""
    if provider == "duckduckgo":
        if not _ddgs_installed():
            return "not_installed", (
                "The DuckDuckGo search needs the ddgs package, which is not installed "
                f"on this PC. Install it with one line in PowerShell: {PIP_LINE}")
        return "", ""
    if not _key(provider):
        return "key_missing", (
            f"No {LABEL[provider]} key is saved on this PC. Add it in the desktop app's "
            f"Settings, Web search (get one at {KEY_WHERE[provider]}).")
    return "", ""


# --------------------------------------------------------------------------
#   The plan - built locally, read by a person, sends nothing
# --------------------------------------------------------------------------

@dataclass
class Plan:
    query: str
    provider: Optional[str]
    label: str
    host: str
    keyed: bool
    problem: str = ""        # non-empty: nothing will be sent, and this says why
    state: str = ""          # the problem's code (STATES)
    offer: str = ""
    searxng_url: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def clean_query(query) -> str:
    q = str(query or "")
    q = "".join(ch if ch.isprintable() else " " for ch in q)
    return " ".join(q.split())


def _secret_in(text: str) -> str:
    """The KIND of secret in `text`, or "". Never the value. Both detectors
    this project has: jarvis_router's shapes, and jarvis_scrub's (which also
    knows the secrets this PC holds by value - the pairing token, a saved
    key). When neither can be loaded, that is said as a refusal: the words
    cannot be checked, so they are not sent."""
    found, checked = "", False
    try:
        import jarvis_router
        checked = True
        hit = jarvis_router.looks_like_a_secret(text)
        if hit:
            # The kind only - its masked excerpt is still part of the value.
            found = str(hit).split(" (", 1)[0]
    except Exception:
        pass
    if not found:
        try:
            import jarvis_scrub
            checked = True
            hit = jarvis_scrub.find_secret(text)
            if hit:
                found = str(hit)
        except Exception:
            pass
    if not checked:
        return "unchecked"
    return found


def plan(query, *, s: Optional[dict] = None) -> Plan:
    """What would be sent, and to whom. Opens no socket."""
    s = s or settings()
    provider = s.get("provider")
    q = clean_query(query)
    host = ""
    if provider == "searxng":
        host = urllib.parse.urlsplit(s.get("searxng_url") or DEFAULT_SEARXNG_URL).netloc
    elif provider == "duckduckgo":
        host = DDG_HOST
    elif provider == "tavily":
        host = urllib.parse.urlsplit(TAVILY_URL).netloc
    elif provider == "brave":
        host = urllib.parse.urlsplit(BRAVE_URL).netloc
    p = Plan(query=q, provider=provider, label=LABEL.get(provider or "", "no search"),
             host=host, keyed=provider in NEEDS_KEY,
             searxng_url=(s.get("searxng_url") or "") if provider == "searxng" else "")
    if not q:
        p.state, p.problem = "empty", "There were no search words, so nothing was searched."
        return p
    if len(q) > MAX_QUERY_CHARS:
        p.state, p.problem = "empty", (
            f"Those search words are longer than {MAX_QUERY_CHARS} characters. Search with "
            f"fewer, shorter words. Nothing was sent.")
        return p
    kind = _secret_in(q)
    if kind == "unchecked":
        p.state, p.problem = "secret", (
            "Refused: Jarvis could not check the search words for passwords or keys on "
            "this PC (jarvis_router.py and jarvis_scrub.py are both missing), and a search "
            "sends its words to the internet. Nothing was sent.")
        return p
    if kind:
        p.state, p.problem = "secret", (
            f"Refused: the search words look like they hold {kind}, and a search sends its "
            f"words to the internet. Passwords and keys stay on this PC. Nothing was sent. "
            f"Search again without it.")
        return p
    state, said = readiness(provider, s)
    if state:
        p.state, p.problem = state, said
        p.offer = offer_line(provider) if state not in ("settings_damaged",) else ""
    return p


def describe(p: Plan) -> str:
    """The card text. The search words in full - never summarised."""
    if p.problem:
        return p.problem
    lines = [f"Search the web with {p.label} for:", "", f"    “{p.query}”", ""]
    if p.provider == "searxng":
        lines.append(f"What leaves this PC: these search words, and nothing else, to your "
                     f"SearXNG at {p.searxng_url}, which asks several search engines for "
                     f"you. Those engines see the words and your internet address.")
    elif p.provider == "duckduckgo":
        lines.append(f"What leaves this PC: these search words, and nothing else, to "
                     f"DuckDuckGo ({p.host}). DuckDuckGo sees them and your internet address.")
    else:
        lines.append(f"What leaves this PC: these search words, to {p.label} ({p.host}), "
                     f"with your {p.label} key - so {p.label} knows the search is yours. "
                     f"The key goes to {p.host} only.")
    lines += ["", f"What comes back - up to {MAX_RESULTS} results, each a title, a link and "
                  f"a short snippet - is read as outside text, like a web page.",
              "", "If you say no: nothing is searched, and Jarvis answers from what it "
                  "already knows."]
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Sending - only with a plan a person (or the owner's own question) allowed
# --------------------------------------------------------------------------

class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is refused, never followed: urllib copies every header -
    the key included - onto the redirect target, cross-host too, and a
    search answer has no business redirecting (jarvis_research's reason)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code,
                                     "refused to follow a redirect", headers, fp)


class SearchError(Exception):
    def __init__(self, state: str, said: str):
        super().__init__(said)
        self.state = state
        self.said = said


def _read_capped(resp) -> bytes:
    body = resp.read(MAX_BODY + 1)
    if len(body) > MAX_BODY:
        raise SearchError("failed", "The search answer was larger than Jarvis reads "
                                    f"({MAX_BODY // 1000} KB), so it was not used.")
    return body


def _http(req: urllib.request.Request, *, local: bool) -> tuple:
    """(status, body bytes). HTTP errors come back as their status, with
    their body (capped); a connection that fails raises."""
    import jarvis_local_http as LH
    op = (LH.opener(_RefuseRedirect) if local
          else LH.opener_for(req.full_url, _RefuseRedirect))
    try:
        with op.open(req, timeout=TIMEOUT) as r:
            return r.status, _read_capped(r)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(4096) if exc.fp is not None else b""
        except Exception:
            body = b""
        return exc.code, body


#: Tests replace this: (Request, local) -> (status, body bytes).
_HTTP: Optional[Callable] = None


def _send(req, *, local: bool):
    return (_HTTP or _http)(req, local=local)


def _json(body: bytes, who: str):
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        raise SearchError("failed", f"{who} answered, but not with search results Jarvis "
                                    f"can read.") from None


_TAG = re.compile(r"<[^>]{0,200}>")


def _clean(text, limit: int) -> str:
    t = html.unescape(_TAG.sub("", str(text or "")))
    t = "".join(ch if ch.isprintable() else " " for ch in t)
    t = " ".join(t.split())
    return t if len(t) <= limit else t[:limit - 1].rstrip() + "…"


def normalise(rows) -> list:
    """At most MAX_RESULTS {title, url, snippet}; a row without an http(s)
    link is dropped (a javascript: or data: link is not a result)."""
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        url = str(r.get("url") or r.get("href") or "").strip()
        if not re.match(r"^https?://", url, re.I) or len(url) > URL_CHARS:
            continue
        if any(ord(c) < 33 for c in url):
            continue
        title = _clean(r.get("title"), TITLE_CHARS) or url
        snippet = _clean(r.get("content") or r.get("description") or r.get("body")
                         or r.get("snippet"), SNIPPET_CHARS)
        out.append({"title": title, "url": url, "snippet": snippet})
        if len(out) >= MAX_RESULTS:
            break
    return out


def _connection_failed(provider: str, exc: BaseException, where: str) -> SearchError:
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, (TimeoutError,)) or "timed out" in str(reason).lower():
        return SearchError("timeout", f"{LABEL[provider]} did not answer in time.")
    if provider == "searxng":
        return SearchError("not_running", (
            f"SearXNG isn't running on this PC - nothing answered at {where}. Start it in "
            f"Docker Desktop (backend/README.md, \"Web search\"), or switch web search "
            f"to another provider."))
    return SearchError("failed", (
        f"Jarvis could not reach {LABEL[provider]} ({type(reason).__name__}). Check the "
        f"PC's internet connection."))


def _searxng(p: Plan) -> list:
    base = (p.searxng_url or DEFAULT_SEARXNG_URL).rstrip("/")
    url = f"{base}/search?" + urllib.parse.urlencode({"q": p.query, "format": "json"})
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "jarvis-search"})
    try:
        status, body = _send(req, local=True)
    except SearchError:
        raise
    except Exception as exc:
        raise _connection_failed("searxng", exc, base) from None
    if status == 403:
        raise SearchError("json_off", (
            "SearXNG is running, but its JSON output is switched off (it answered 403 "
            "Forbidden). Add json to the formats list in its settings.yml and restart it "
            "- backend/README.md, \"Web search\", has the exact steps."))
    if status == 429:
        raise SearchError("rate_limited", (
            "SearXNG refused: too many searches (its limiter is on). Set limiter: false in "
            "its settings.yml and restart it, or wait a minute."))
    if status in (301, 302, 303, 307, 308):
        raise SearchError("failed", "SearXNG answered with a redirect, which Jarvis does not "
                                    "follow. Check the SearXNG address in Settings.")
    if status != 200:
        raise SearchError("failed", f"SearXNG answered with an error (HTTP {status}).")
    doc = _json(body, "SearXNG")
    if not isinstance(doc, dict):
        raise SearchError("failed", "SearXNG answered, but not with search results.")
    return normalise(doc.get("results"))


def _tavily(p: Plan) -> list:
    key = _key("tavily")
    if not key:
        raise SearchError("key_missing", readiness("tavily")[1])
    data = json.dumps({"query": p.query, "max_results": MAX_RESULTS, "search_depth": "basic",
                       "include_answer": False, "include_raw_content": False,
                       "include_images": False}).encode("utf-8")
    req = urllib.request.Request(TAVILY_URL, data=data, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "jarvis-search", "Authorization": f"Bearer {key}"})
    try:
        status, body = _send(req, local=False)
    except SearchError:
        raise
    except Exception as exc:
        raise _connection_failed("tavily", exc, TAVILY_URL) from None
    if status in (401, 403):
        raise SearchError("key_refused", (
            "Tavily refused your key (it may be wrong or cancelled). Check it at "
            f"{KEY_WHERE['tavily']} and save it again in the desktop app's Settings, "
            "Web search."))
    if status in (432, 433):
        raise SearchError("quota_used", (
            "Your Tavily credits for this month are used up. They come back next month, "
            "or switch web search to another provider."))
    if status == 429:
        raise SearchError("rate_limited", "Tavily says too many searches just now. Wait a "
                                          "minute and try again.")
    if status != 200:
        raise SearchError("failed", f"Tavily answered with an error (HTTP {status}).")
    doc = _json(body, "Tavily")
    return normalise(doc.get("results") if isinstance(doc, dict) else None)


def _brave(p: Plan) -> list:
    key = _key("brave")
    if not key:
        raise SearchError("key_missing", readiness("brave")[1])
    url = BRAVE_URL + "?" + urllib.parse.urlencode({"q": p.query, "count": MAX_RESULTS})
    req = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": "jarvis-search",
        "X-Subscription-Token": key})
    try:
        status, body = _send(req, local=False)
    except SearchError:
        raise
    except Exception as exc:
        raise _connection_failed("brave", exc, BRAVE_URL) from None
    if status in (401, 403, 422):
        raise SearchError("key_refused", (
            "Brave Search refused your key (it may be wrong or cancelled). Check it at "
            f"{KEY_WHERE['brave']} and save it again in the desktop app's Settings, "
            "Web search."))
    if status == 402:
        raise SearchError("quota_used", (
            "Your Brave Search credit for this month is used up. It comes back next month, "
            "or switch web search to another provider."))
    if status == 429:
        raise SearchError("rate_limited", (
            "Brave Search says too many searches - either too fast, or this month's free "
            "credit is used up. Wait a minute and try again."))
    if status != 200:
        raise SearchError("failed", f"Brave Search answered with an error (HTTP {status}).")
    doc = _json(body, "Brave Search")
    web = doc.get("web") if isinstance(doc, dict) else None
    return normalise(web.get("results") if isinstance(web, dict) else None)


_DDG_LOCK = threading.Lock()
_DDG_LAST = [0.0]

#: Tests replace this: a module with DDGS and engines.ENGINES, like ddgs.
_DDGS_MODULE = None


def _ddgs():
    if _DDGS_MODULE is not None:
        return _DDGS_MODULE
    import ddgs
    return ddgs


def _ddg_engines(mod) -> dict:
    eng = getattr(mod, "engines", None)
    if eng is None:
        import importlib
        eng = importlib.import_module(mod.__name__ + ".engines")
    return dict((getattr(eng, "ENGINES", {}) or {}).get("text") or {})


def _duckduckgo(p: Plan) -> list:
    try:
        mod = _ddgs()
    except ImportError:
        raise SearchError("not_installed", readiness("duckduckgo")[1]) from None
    except Exception as exc:
        raise SearchError("failed", f"The ddgs package could not be loaded "
                                    f"({type(exc).__name__}).") from None
    try:
        engines = _ddg_engines(mod)
    except Exception:
        engines = {}
    if "duckduckgo" not in engines:
        # ddgs falls back to asking every engine it has when the one named is
        # not there - a search the owner did not choose. Refused instead.
        raise SearchError("failed", (
            "This version of the ddgs package has no DuckDuckGo search, so nothing was "
            "sent (it would have asked other search engines instead). Update it with: "
            "py -3 -m pip install -U ddgs"))
    with _DDG_LOCK:
        # Paced: DuckDuckGo has no official way in and limits fast callers.
        wait = _DDG_LAST[0] + DDG_GAP - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            rows = mod.DDGS(timeout=int(TIMEOUT)).text(
                p.query, backend="duckduckgo", max_results=MAX_RESULTS)
        except Exception as exc:
            name = type(exc).__name__
            text = str(exc).lower()
            if "ratelimit" in name.lower() or "202" in text or "ratelimit" in text:
                raise SearchError("rate_limited", (
                    "DuckDuckGo is limiting searches from this PC for a while. Try again "
                    "in a few minutes, or switch web search to another provider.")) from None
            if "timeout" in name.lower() or "timed out" in text:
                raise SearchError("timeout", "DuckDuckGo did not answer in time.") from None
            if "no results" in text:
                raise SearchError("no_results", (
                    "DuckDuckGo sent back no results. There may be none - or DuckDuckGo may "
                    "be limiting searches from this PC for a while (it does not say which)."
                )) from None
            raise SearchError("failed", f"The DuckDuckGo search failed ({name}). It can "
                                        f"break when DuckDuckGo changes its pages; "
                                        f"py -3 -m pip install -U ddgs may fix it.") from None
        finally:
            _DDG_LAST[0] = time.monotonic()
    return normalise(rows)


_PROVIDER_CALL = {"searxng": _searxng, "duckduckgo": _duckduckgo,
                  "tavily": _tavily, "brave": _brave}


def run(p: Plan, *, approved: bool = False) -> dict:
    """Send an allowed plan. Returns {"ok": True, "provider", "query",
    "results": [...]} or {"ok": False, "state", "error", "offer"} - and
    never tries another provider."""
    if not approved:
        return {"ok": False, "state": "failed", "error": "not approved; nothing was sent"}
    if p.problem:
        out = {"ok": False, "state": p.state, "error": p.problem}
        if p.offer:
            out["offer"] = p.offer
        return out
    # The card said whether a key goes with the words; the provider and the
    # SearXNG address are the ones the card named. If settings changed in
    # between, this is not the plan that was allowed.
    now = settings()
    if now.get("provider") != p.provider or (
            p.provider == "searxng" and now.get("searxng_url") != p.searxng_url):
        return {"ok": False, "state": "failed",
                "error": ("refused: the web search settings changed since this search was "
                          "planned, so it no longer matches what was shown. Nothing was "
                          "sent. Ask again.")}
    call = _PROVIDER_CALL.get(p.provider or "")
    if call is None:
        return {"ok": False, "state": "settings_damaged", "error": _DAMAGED}
    try:
        results = call(p)
    except SearchError as exc:
        out = {"ok": False, "state": exc.state, "error": exc.said}
        if exc.state not in ("no_results",):
            out["offer"] = offer_line(p.provider)
        return out
    except Exception as exc:
        return {"ok": False, "state": "failed", "offer": offer_line(p.provider),
                "error": f"The search failed ({type(exc).__name__}). Nothing else was tried."}
    out = {"ok": True, "provider": p.provider, "provider_label": p.label,
           "query": p.query, "results": results}
    if not results:
        out["note"] = f"{p.label} found nothing for those words."
    return out


def tool_result(out: dict) -> dict:
    """What the model reads. A failure carries the words to pass on, and
    says plainly not to search some other way (no silent fallback)."""
    if out.get("ok"):
        return out
    said = str(out.get("error") or "The search did not work.")
    if out.get("offer"):
        said = f"{said} {out['offer']}"
    return {"ok": False, "error": said,
            "tell_the_owner": ("Say this to the owner in plain words. Do not try to search "
                               "another way, and do not guess the results.")}


# --------------------------------------------------------------------------
#   The apps: GET /api/search, POST /api/search/settings, /api/search/test
# --------------------------------------------------------------------------

def view() -> dict:
    s = settings()
    providers = []
    for pid in PROVIDERS:
        state, said = readiness(pid, s)
        providers.append({
            "id": pid, "label": LABEL[pid], "why": WHY[pid],
            "needs_key": pid in NEEDS_KEY,
            "key_saved": key_saved(pid) if pid in NEEDS_KEY else None,
            "key_where": KEY_WHERE.get(pid, ""),
            "needs_docker": pid == "searxng",
            "ready": not state, "state": state, "said": said,
        })
    return {
        "available": True,
        "provider": s["provider"],
        "why": s["why"],
        "default": DEFAULT_PROVIDER,
        "default_why": DEFAULT_WHY,
        "providers": providers,
        "left_out": [dict(x) for x in LEFT_OUT],
        "searxng_url": s["searxng_url"],
        "searxng_default": DEFAULT_SEARXNG_URL,
        "ask_every_time": s["ask_every_time"],
        "ask_every_time_label": ASK_EVERY_TIME_LABEL,
        "ask_every_time_detail": ASK_EVERY_TIME_DETAIL,
        "key_entry": KEY_ENTRY,
        "test_query": TEST_QUERY,
        **card_state(),
    }


def handle_get() -> tuple:
    return 200, view()


def handle_settings(body) -> tuple:
    """POST /api/search/settings - ONE change per request:
       {"provider": id}            immediate
       {"searxng_url": address}    immediate; "" puts the default back
       {"ask_every_time": true}    immediate (stricter)
       {"ask_every_time": false}   202, ONE approval card (ACTION_ASK_LESS)"""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "the request must be a JSON object"}
    keys = [k for k in ("provider", "searxng_url", "ask_every_time") if k in body]
    if len(keys) != 1:
        return 400, {"ok": False, "error": ('send exactly one of {"provider": ...}, '
                                            '{"searxng_url": ...} or {"ask_every_time": ...}')}
    k = keys[0]
    if k == "provider":
        pid = body["provider"]
        if pid not in PROVIDERS:
            return 400, {"ok": False, "error": f"provider must be one of {', '.join(PROVIDERS)}"}
        s = _save(provider=pid)
        said = f"Web search now uses {LABEL[pid]}."
        state, why = readiness(pid, s)
        if state:
            said = f"{said} {why}"
        return 200, {"ok": True, "said": said, **view()}
    if k == "searxng_url":
        url = body["searxng_url"]
        if not isinstance(url, str):
            return 400, {"ok": False, "error": "searxng_url must be text"}
        url = url.strip().rstrip("/") or DEFAULT_SEARXNG_URL
        why = searxng_url_problem(url)
        if why:
            return 400, {"ok": False, "error": f"That SearXNG address cannot be used: {why}."}
        _save(searxng_url=url)
        return 200, {"ok": True, "said": f"SearXNG address set to {url}.", **view()}
    on = body["ask_every_time"]
    if not isinstance(on, bool):
        return 400, {"ok": False, "error": "ask_every_time must be true or false"}
    return request_ask_every_time(on)


def handle_test(body=None) -> tuple:
    """POST /api/search/test - one search for the fixed word TEST_QUERY
    through the chosen provider, and what happened in plain words. The
    owner pressed the button, and the words are fixed, never from a
    conversation, so no card. It is a real search: it uses one credit on
    Tavily, a little of Brave's credit, and counts toward DuckDuckGo's limit."""
    p = plan(TEST_QUERY)
    if p.problem:
        return 200, {"ok": False, "state": p.state, "said": p.problem,
                     "provider": p.provider, "offer": p.offer}
    out = run(p, approved=True)
    if out.get("ok"):
        n = len(out.get("results") or [])
        return 200, {"ok": True, "state": "works", "provider": p.provider,
                     "said": (f"{p.label} works: a test search for \"{TEST_QUERY}\" found "
                              f"{n} result{'s' if n != 1 else ''}."),
                     "results": n}
    return 200, {"ok": False, "state": out.get("state") or "failed", "provider": p.provider,
                 "said": out.get("error") or "It did not work.", "offer": out.get("offer", "")}


# --------------------------------------------------------------------------
#   "Ask before every web search": ON immediate, OFF one card
#   (the shape of jarvis_learning_switch.py)
# --------------------------------------------------------------------------

CARD_TEXT = "\n".join([
    "Stop asking before every web search.",
    "",
    "Jarvis goes back to the default: a search that comes straight from your own "
    "question, in a conversation where Jarvis has not read your email, files, notes, "
    "saved memories or other outside text, runs without a card. Every other search "
    "still shows you its exact words on a card first.",
    "",
    "Nothing is searched by this change, and nothing leaves this PC. You can turn "
    "\"Ask before every web search\" back on at any time, and that is instant.",
    "",
    "If you say no: Jarvis keeps asking before every web search.",
])

LAST_WORDS = {
    "changed": "You approved the card, so Jarvis asks first only when private things could "
               "slip into a search.",
    "denied": "The card was turned down, so Jarvis still asks before every web search.",
    "timed_out": "Nobody answered the card in time, so Jarvis still asks before every web "
                 "search.",
    "refused": "Your PC's settings do not let this be approved, so Jarvis still asks before "
               "every web search.",
    "withdrawn": "You turned \"Ask before every web search\" on again while the card waited, "
                 "so approving it changed nothing.",
    "failed": "It was approved, but the setting could not be saved, so Jarvis still asks "
              "before every web search.",
}

_LOCK = threading.Lock()
_SWITCH = threading.Lock()
_PENDING: dict = {}
_WITHDRAWN: set = set()
_LAST: dict = {}
_LATEST: dict = {}


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    try:
        import jarvis_framework as fw
        return str(fw.action_tier(action))
    except Exception as exc:
        return f"unreadable ({type(exc).__name__})"


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-search-card", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    try:
        import jarvis_framework as fw
        fw.audit_log(event, detail)
    except Exception:
        pass


def card_state() -> dict:
    with _LOCK:
        return {"waiting": bool(_PENDING), "last": dict(_LAST) or None}


def _finish(pid: str, outcome: str, why: str = "") -> None:
    with _LOCK:
        if _PENDING.get("id") == pid:
            _PENDING.clear()
        _WITHDRAWN.discard(pid)
        if _LATEST.get("id") not in (None, pid):
            return
        _LAST.clear()
        _LAST.update(outcome=outcome, why=why, at=time.time(),
                     message=LAST_WORDS.get(outcome, ""))
    _audit("web_search.card", {"outcome": outcome})


def _decide(pid: str, gate: Callable, tier_of: Callable[[str], str]) -> None:
    try:
        v = gate(ACTION_ASK_LESS, {"text": CARD_TEXT, "what": "stop asking before every web search",
                                   "leaves_this_pc": False}, CARD_TEXT)
    except Exception as exc:
        return _finish(pid, "refused", f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    if vtier != "ask" or tier_of(ACTION_ASK_LESS) != "ask":
        return _finish(pid, "refused",
                       f"the gate answered at tier {vtier!r}, which is not a person saying yes")
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, outcome)
        return _finish(pid, "refused", str(getattr(v, "reason", "refused")))
    with _SWITCH:
        with _LOCK:
            withdrawn = pid in _WITHDRAWN
        if withdrawn:
            return _finish(pid, "withdrawn")
        try:
            _save(ask_every_time=False)
        except Exception as exc:
            return _finish(pid, "failed", type(exc).__name__)
        _finish(pid, "changed")


def request_ask_every_time(on: bool, *, gate: Optional[Callable] = None,
                           tier_of: Optional[Callable[[str], str]] = None,
                           spawn: Optional[Callable] = None) -> tuple:
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if on:
        with _SWITCH:
            with _LOCK:
                if _PENDING:
                    _WITHDRAWN.add(_PENDING["id"])
                    _PENDING.clear()
            try:
                _save(ask_every_time=True)
            except Exception as exc:
                return 500, {"ok": False, "error": f"could not save ({type(exc).__name__})"}
        _audit("web_search.ask_every_time", {"on": True})
        return 200, {"ok": True, "waiting": False,
                     "said": "Jarvis now asks before every web search.", **view()}
    if settings()["ask_every_time"] is False:
        return 200, {"ok": True, "waiting": False,
                     "said": "Jarvis already asks only when private things could slip in.",
                     **view()}
    tier = tier_of(ACTION_ASK_LESS)
    if tier != "ask":
        return 503, {"ok": False, "error": (
            f"{ACTION_ASK_LESS} is tier {tier!r} in jarvis-framework.toml; turning \"Ask "
            f"before every web search\" off needs a person to say yes, so it must be 'ask'")}
    with _LOCK:
        if _PENDING:
            return 202, {"ok": True, "waiting": True,
                         "said": "A card to stop asking before every search is already "
                                 "waiting for your approval."}
        pid = _uuid.uuid4().hex
        _PENDING.update(id=pid, since=time.time())
        _LATEST["id"] = pid
    try:
        spawn(lambda: _decide(pid, gate, tier_of))
    except Exception:
        with _LOCK:
            _PENDING.clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True,
                 "said": "Waiting for your approval. Jarvis keeps asking before every web "
                         "search until you approve the card, on your PC or phone."}


def _reset_for_tests() -> None:
    with _LOCK:
        _PENDING.clear()
        _WITHDRAWN.clear()
        _LAST.clear()
        _LATEST.clear()
    _DDG_LAST[0] = 0.0


# --------------------------------------------------------------------------
#   "Which search should I use?" - from the same words, without the model
# --------------------------------------------------------------------------

def explain(which: Optional[str] = None) -> str:
    """The answer to "which search should I use?" (which=None) or "why
    SearXNG?" / "what about Tavily?" (which=an id, or "whoogle")."""
    s = settings()
    now = s.get("provider")
    if which == "whoogle":
        return f"Whoogle: {LEFT_OUT[0]['why']}"
    if which in PROVIDERS:
        out = f"{LABEL[which]}: {WHY[which]}"
        if which == DEFAULT_PROVIDER:
            out += f" {DEFAULT_WHY}"
        if now == which:
            out += " It is the one Jarvis uses now."
        return out
    lines = [f"Jarvis can search the web four ways. Now it uses "
             f"{LABEL[now] if now else 'none (the settings file is damaged)'}."]
    for pid in PROVIDERS:
        lines.append(f"- {LABEL[pid]}{' (the default)' if pid == DEFAULT_PROVIDER else ''}: "
                     f"{WHY[pid]}")
    lines.append(f"- {LEFT_OUT[0]['label']}: {LEFT_OUT[0]['why']}")
    lines.append(DEFAULT_WHY + " Change it in Settings, Web search, in either app, or say "
                 "\"use DuckDuckGo for web search\".")
    return "\n".join(lines)


def use(provider: str) -> str:
    """For "use DuckDuckGo for web search": the provider changed, in words."""
    code, out = handle_settings({"provider": provider})
    return str(out.get("said") or out.get("error") or "")


# --------------------------------------------------------------------------
#   For the owner, in the backend folder
# --------------------------------------------------------------------------

USAGE = """\
py -3 jarvis_search.py key tavily        save your Tavily key (it is asked for, not shown)
py -3 jarvis_search.py key brave         save your Brave Search key
py -3 jarvis_search.py forget-key tavily remove it from this PC (also: brave)
py -3 jarvis_search.py status            which search is chosen, and which keys are saved
py -3 jarvis_search.py test              one test search for "wikipedia" with the chosen search
"""


def _main(argv, *, ask_secret=None, out=print) -> int:
    if not argv:
        out(USAGE)
        return 2
    cmd = argv[0]
    if cmd in ("key", "forget-key"):
        if len(argv) != 2 or argv[1] not in KEY_TARGETS:
            out("Say which: tavily or brave.")
            return 2
        prov = argv[1]
        if cmd == "forget-key":
            r = forget_key(prov)
        else:
            if ask_secret is None:
                import getpass
                ask_secret = getpass.getpass
            value = ask_secret(f"Paste your {LABEL[prov]} key (it will not show), then "
                               f"press Enter: ")
            r = save_key(prov, value or "")
        out(r.get("said") or f"Not saved: {r.get('error')}.")
        return 0 if r.get("ok") else 1
    if cmd == "status":
        s = settings()
        out(f"Web search uses: {LABEL.get(s['provider'] or '', 'nothing')}"
            + (f" ({s['why']})" if s["why"] else ""))
        out(f"SearXNG address: {s['searxng_url']}")
        out(f"Ask before every web search: {'on' if s['ask_every_time'] else 'off'}")
        for prov in KEY_TARGETS:
            k = key_saved(prov)
            out(f"{LABEL[prov]} key: "
                + ("saved" if k else "not saved" if k is False else "cannot be checked here"))
        return 0
    if cmd == "test":
        code, r = handle_test({})
        out(r.get("said", ""))
        return 0 if r.get("ok") else 1
    out(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
