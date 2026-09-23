"""jarvis_notes.py - lets Jarvis search the owner's own notes. Nothing else.

WHAT IT IS FOR
The second of the four integrations docs/ANDROID-FEATURE-AUDIT.md named:
"notes (Obsidian/Joplin local REST) ... read-only first, no cloud keys."
Both apps run a REST server ON THE OWNER'S OWN MACHINE that a local token
unlocks - Joplin's Web Clipper API (`http://127.0.0.1:41184`, a token
generated in Options -> Web Clipper) and the Obsidian Local REST API
community plugin (`https://127.0.0.1:27124` by default, an API key the
plugin generates). Neither needs an account, a cloud key, or an OAuth
registration - the whole point of choosing them.

ONE BACKEND, PICKED FROM WHAT IS CONFIGURED, NEVER BOTH AT ONCE
An owner runs Joplin or Obsidian, essentially never both for the same
notes. `_resolve_backend()` picks whichever this owner has actually set up -
`JARVIS_NOTES_BACKEND` if given explicitly, otherwise whichever token/key is
present - and `plan()` builds a request for that one backend only. Wanting
support for switching later is real; guessing which of two different REST
APIs and two different response shapes to merge results from is not this
module's job today.

READ-ONLY, ON PURPOSE, WITH NO GROWTH PATH LEFT HALF-BUILT
Search only. Both APIs can also create and edit notes - not implemented
here, same reasoning `jarvis_email.py`'s docstring gives for leaving out
SMTP: a write is a materially different, higher-consequence action (it
changes the owner's actual notes) than a read.

Correction, 2026-09-23: this paragraph used to say the desktop's `#log`/
`#joplin` prefixes were an existing capture path "wired through OpenJarvis's
own tool registry". They were not - they asked the model for tools that
existed nowhere, so nothing was ever filed. Writing a note now lives in its
own module, `jarvis_note_capture.py`, with its own plan/describe/gate/run
and its own action names; this one stays a read.

THE PERMISSION MODEL, WHICH IS THE POINT
    plan(query, limit)     Works out the ONE search request this would make -
                            literal URL, no token in it - against whichever
                            backend is configured. Opens no socket.
    run(plan, approved)    Executes that one request and normalises whichever
                            backend answered into the same small shape.

Same split, same reason, as `jarvis_calendar.py` and `jarvis_email.py`: a
request to the owner's own local server is still a request leaving this
process, and this module does not decide on its own that it may be sent.
See backend/README.md's `notes-wiring` section for the exact `jarvis_gate`/
`jarvis-framework.toml` lines and the tier this ships with - the same "a
pure read defaults to auto" reasoning `jarvis_calendar.py`'s docstring gives
applies here unchanged.

WHY THE TOKEN IS NEVER IN THE URL `describe()` PRINTS
Joplin's own API takes its token as a query-string parameter
(`?token=...`), not a header - there is no other option in its documented
API. Printing the plan's URL verbatim, the way `jarvis_calendar.py` and
`jarvis_research.py` both do, would put a live secret on the approval card
and in the audit log, which is exactly what `docs/ARCHITECTURE.md`'s
credential rules exist to prevent. So the URL a `Plan` carries and
`describe()` prints is deliberately the token-FREE form; the token (Joplin)
or the `Authorization` header (Obsidian) is added only inside the real
fetch function, read fresh from the environment, the same way
`jarvis_calendar.py` adds its Basic-auth header only inside `_default_fetch`.

CREDENTIALS - NEVER STORED HERE, NEVER LOGGED, NEVER ON A CARD
`JARVIS_JOPLIN_TOKEN` / `JARVIS_OBSIDIAN_API_KEY` are read fresh from the
environment on every call. This module never writes them to disk.

TESTING WITHOUT A REAL JOPLIN OR OBSIDIAN INSTANCE
`run()` takes an injectable `fetch`, exactly the shape `jarvis_calendar.py`'s
own `fetch` uses: given the token-free `Plan`, it returns the backend's raw
parsed JSON, and only `_default_fetch` (never called by anything in this
file except itself) does the real network call and adds the real credential.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from typing import Callable, Optional

BACKEND_ENV = "JARVIS_NOTES_BACKEND"       # "joplin" | "obsidian", optional override
JOPLIN_URL_ENV = "JARVIS_JOPLIN_URL"
JOPLIN_TOKEN_ENV = "JARVIS_JOPLIN_TOKEN"
OBSIDIAN_URL_ENV = "JARVIS_OBSIDIAN_URL"
OBSIDIAN_KEY_ENV = "JARVIS_OBSIDIAN_API_KEY"

_DEFAULT_JOPLIN_URL = "http://127.0.0.1:41184"
_DEFAULT_OBSIDIAN_URL = "https://127.0.0.1:27124"

_MAX_RESULTS = 20
_MAX_TITLE_CHARS = 200
_MAX_SNIPPET_CHARS = 400


def _resolve_backend() -> Optional[str]:
    explicit = os.environ.get(BACKEND_ENV, "").strip().lower()
    if explicit in ("joplin", "obsidian"):
        return explicit
    if os.environ.get(JOPLIN_TOKEN_ENV, "").strip():
        return "joplin"
    if os.environ.get(OBSIDIAN_KEY_ENV, "").strip():
        return "obsidian"
    return None


def authenticated() -> bool:
    """Whether a token/key is configured for the resolved backend."""
    backend = _resolve_backend()
    if backend == "joplin":
        return bool(os.environ.get(JOPLIN_TOKEN_ENV, "").strip())
    if backend == "obsidian":
        return bool(os.environ.get(OBSIDIAN_KEY_ENV, "").strip())
    return False


# --------------------------------------------------------------------------
#   The plan - one request, worked out locally, sent to no one yet
# --------------------------------------------------------------------------

@dataclass
class Plan:
    backend: Optional[str]     # "joplin" | "obsidian" | None
    query: str
    limit: int
    url: str = ""               # token-free - see the module docstring
    if_refused: str = ""
    authenticated: bool = False
    reason_empty: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def plan(query: str, limit: int = 10) -> Plan:
    """Work out the one search request this would make. Opens no socket."""
    query = str(query).strip()
    limit = max(1, min(_MAX_RESULTS, int(limit)))
    backend = _resolve_backend()
    if_refused = "nothing is searched; these notes stay unknown to Jarvis"

    if not query:
        return Plan(backend=backend, query=query, limit=limit,
                     if_refused=if_refused, reason_empty="the search query is empty")
    if backend is None:
        return Plan(
            backend=None, query=query, limit=limit, if_refused=if_refused,
            reason_empty=(
                f"neither {JOPLIN_TOKEN_ENV} nor {OBSIDIAN_KEY_ENV} is set - "
                "there is no notes app configured to search"))

    if backend == "joplin":
        base = os.environ.get(JOPLIN_URL_ENV, "").strip() or _DEFAULT_JOPLIN_URL
        url = (f"{base.rstrip('/')}/search?query="
               + urllib.parse.quote(query, safe="")
               + f"&limit={limit}&fields=id,title,body")
    else:
        base = os.environ.get(OBSIDIAN_URL_ENV, "").strip() or _DEFAULT_OBSIDIAN_URL
        url = (f"{base.rstrip('/')}/search/simple/?query="
               + urllib.parse.quote(query, safe="")
               + "&contextLength=" + str(_MAX_SNIPPET_CHARS))

    return Plan(backend=backend, query=query, limit=limit, url=url,
                if_refused=if_refused, authenticated=authenticated())


def describe(p: Plan) -> str:
    """The card text. The literal, token-free URL - never a summary of it."""
    if p.reason_empty:
        return (f"Jarvis would like to search notes for \"{p.query}\", but "
                f"{p.reason_empty}. Nothing would be sent.")
    auth_line = (
        f"Authenticated: this will send the configured {p.backend} "
        "token/key to that local server, over that one request."
        if p.authenticated else
        f"No {'token' if p.backend == 'joplin' else 'API key'} is configured "
        "- this request will very likely be refused, which both apps "
        "require for any real use."
    )
    lines = [
        f"Jarvis would like to search your {p.backend.title()} notes for "
        f"\"{p.query}\" (up to {p.limit} result(s)).",
        "",
        f"1 request, to {p.url}",
        auth_line,
        "",
        "What leaves this machine: the search text above, and the "
        "credential if configured - both to that one local server. Not "
        "your other notes, not your conversation.",
        "",
        f"If you say no: {p.if_refused}",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Execution - one request, then a normalised, bounded read
# --------------------------------------------------------------------------

class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """Stops a redirect from carrying the credential to another host.

    The same guard `jarvis_home`, `jarvis_research` and `jarvis_calendar`
    each already carry, and the one module doing authenticated HTTP that was
    left without it. `urllib` copies every header except
    content-length/content-type onto the redirect target, cross-host
    included, so a 302 hands over the Obsidian bearer key. Rule 3 says a key
    is "sent only to the one service it authenticates against"; following a
    redirect is precisely how it stops being.

    This matters more here than the shared default suggests: the endpoints
    are env-configurable (`JARVIS_JOPLIN_URL`/`JARVIS_OBSIDIAN_URL`) and
    Joplin's default is plain `http://127.0.0.1:41184`, so whatever answers
    on that port can redirect.

    Refused rather than stripped, for the reason the other three give: a 401
    from a silently stripped header reads as "wrong key" and sends the owner
    hunting in the wrong place.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"refused to follow a redirect to {newurl}: the notes credential "
            f"would have been sent there. Point the notes URL at the final "
            f"address instead.",
            headers,
            fp,
        )


def _scrub_secrets(message: str) -> str:
    """`message` with the Joplin token and the Obsidian key taken out.

    THE LEAK THIS CLOSES (docs/EXTRACTION-RESEARCH-2026-09-23.md, reproduced
    there): Joplin takes its token in the URL, and urllib quotes the whole URL
    in some errors. Set JARVIS_JOPLIN_URL without its "http://" and every
    search failed with `ValueError: unknown url type: '127.0.0.1:41184/search?
    ...&token=<the real token>'` - and run() put that sentence in its result,
    which reaches the model, the screen and the logs. A control character in
    the address does the same through http.client's InvalidURL, and a
    refused redirect's message carries the redirect target. So every error
    passes through here, in every spelling the secret can take in a URL.
    """
    s = str(message)
    for env in (JOPLIN_TOKEN_ENV, OBSIDIAN_KEY_ENV):
        secret = os.environ.get(env, "")
        if not secret.strip():
            continue
        for form in {secret, secret.strip(), urllib.parse.quote(secret, safe=""),
                     urllib.parse.quote_plus(secret)}:
            if form:
                s = s.replace(form, "[secret hidden]")
    return s


def _default_fetch(p: Plan):
    """The real call. Adds the real credential fresh from the environment -
    never cached, never logged, never part of the `Plan` a card was shown
    for, and never followed onto a redirect (see `_RefuseRedirect`).
    Returns the backend's raw parsed JSON."""
    headers = {"Accept": "application/json"}
    url = p.url
    if p.backend == "joplin":
        token = os.environ.get(JOPLIN_TOKEN_ENV, "")
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}token={urllib.parse.quote(token, safe='')}"
    else:
        key = os.environ.get(OBSIDIAN_KEY_ENV, "")
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(_RefuseRedirect)
    with opener.open(req, timeout=20.0) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _normalize_joplin(raw, limit: int) -> list:
    items = (raw or {}).get("items", []) if isinstance(raw, dict) else []
    out = []
    for item in items[:limit]:
        out.append({
            "title": str(item.get("title", ""))[:_MAX_TITLE_CHARS],
            "snippet": str(item.get("body", ""))[:_MAX_SNIPPET_CHARS],
            "ref": str(item.get("id", "")),
        })
    return out


def _normalize_obsidian(raw, limit: int) -> list:
    out = []
    for item in (raw or [])[:limit] if isinstance(raw, list) else []:
        matches = item.get("matches") or []
        snippet = matches[0].get("context", "") if matches else ""
        out.append({
            "title": str(item.get("filename", ""))[:_MAX_TITLE_CHARS],
            "snippet": str(snippet)[:_MAX_SNIPPET_CHARS],
            "ref": str(item.get("filename", "")),
        })
    return out


def run(p: Plan, *, fetch: Optional[Callable[[Plan], object]] = None,
        approved: bool = False) -> dict:
    """Execute an approved plan. `approved` has no default of True.

    `fetch` is injectable so the normalisation below can be proven with no
    socket, the same technique `jarvis_calendar.run()`'s `fetch` uses.
    """
    if not approved:
        return {"ok": False, "reason": "not approved; nothing was searched",
                "plan": p.as_dict()}
    if p.reason_empty:
        return {"ok": False, "reason": p.reason_empty, "results": []}

    getter = fetch or _default_fetch
    try:
        raw = getter(p)
    except Exception as exc:
        # Scrubbed: this sentence goes back to the model, onto the screen and
        # into logs, and urllib quotes the whole URL - Joplin's token is in
        # its query string - in some of its errors. See _scrub_secrets().
        return {"ok": False,
                "reason": _scrub_secrets(f"the request failed: {type(exc).__name__}: {exc}"),
                "results": []}

    normalize = _normalize_joplin if p.backend == "joplin" else _normalize_obsidian
    results = normalize(raw, p.limit)
    return {"ok": True, "results": results, "backend": p.backend, "query": p.query}
