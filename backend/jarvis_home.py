"""jarvis_home.py - lets Jarvis read Home Assistant entity states, and,
separately and more carefully, call one Home Assistant service.

WHAT IT IS FOR
The last of the four integrations docs/ANDROID-FEATURE-AUDIT.md named:
"home (Home Assistant's MCP server) ... read-only first, no cloud keys."
This module talks to Home Assistant's own long-standing REST API instead
(`/api/states`, `/api/services`) rather than its newer MCP server, for the
same reason this project has never taken an MCP client dependency anywhere
else (`docs/ANDROID-FEATURE-AUDIT.md`'s own table notes Ollama has no native
MCP client, issue #7865, open since 2024) - the REST API needs nothing but
`urllib`, already does everything this module needs, and is the API Home
Assistant has supported longest. "Keyless" here means what it means in the
other three integrations: no OAuth registration, no cloud account - a
long-lived access token the owner generates themselves, in their own
Home Assistant profile page, for their own instance.

THE ONE WAY THIS MODULE IS NOT LIKE THE OTHER THREE
`jarvis_calendar.py`, `jarvis_email.py`, and `jarvis_notes.py` only ever
read. Home Assistant's entire reason for existing is to also ACT on the
physical world - lock a door, open a garage, arm an alarm - and
docs/ANDROID-FEATURE-AUDIT.md's own phrase for this integration is "home
control means more cards", not "home reading". So this module has two
separate entry points that must never be confused for each other:

    plan_states(entity_ids)              READ. One GET per entity named,
                                          nothing else. Ships tier `auto` -
                                          see jarvis_calendar.py's docstring
                                          for why a pure read defaults there.
    plan_service(domain, service, ...)   ACT. One POST, to one named
                                          service, on one named entity.
                                          Ships tier `ask`, same as
                                          `jarvis_browser_control.py`'s
                                          "never auto" reasoning: this
                                          changes something real, not data.
                                          `_is_heavy_service` marks a lock,
                                          alarm, or cover action `heavy` -
                                          the same signal
                                          `jarvis_ui_control.Step.heavy`
                                          uses - because "the front door is
                                          now unlocked" is a materially
                                          bigger consequence than "the
                                          kitchen light is now on", even
                                          though both are one API call.

Both still go through the same `describe()`/`run()` shape, and `run()` still
refuses without `approved=True` - a module that can act on the physical
world must not be one call away from doing it by accident, more than any
other module in this project.

WHY ENTITIES ARE NAMED EXPLICITLY, NEVER DISCOVERED
Home Assistant's `/api/states` with no entity id returns EVERY entity in the
house in one response - lights, locks, cameras, presence sensors, all of it.
`plan_states()` takes a list of entity ids and reads only those, capped at
`_MAX_ENTITIES` - the same bounded-and-explicit shape
`jarvis_ui_control.plan()`'s named `requests` already uses, and for the same
reason: a card that says "read `lock.front_door`" is something a person can
approve with their eyes open, and a card that says "read the whole house"
is not a request, it is a standing grant.

CREDENTIALS - NEVER STORED HERE, NEVER LOGGED, NEVER ON A CARD
`JARVIS_HOME_URL` and `JARVIS_HOME_TOKEN` are read fresh from the
environment on every call. This module never writes the token to disk and
never puts it in a `Plan`, a `Query`, or `describe()`'s output.

TESTING WITHOUT A REAL HOME ASSISTANT
`run()` takes an injectable `fetch`, exactly the shape
`jarvis_calendar.py`'s own `fetch` uses - given a token-free `Query`, it
returns the parsed JSON Home Assistant would have, and only `_default_fetch`
(never called by anything in this file except itself) does the real network
call and adds the real bearer token.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional

URL_ENV = "JARVIS_HOME_URL"
TOKEN_ENV = "JARVIS_HOME_TOKEN"

_MAX_ENTITIES = 20
_MAX_ATTRIBUTES_CHARS = 500

# A lock, an alarm panel, or a cover (garage doors and roller shutters are
# both HA's "cover" domain) changes something with real physical or security
# consequence. Everything else - lights, switches, climate, media players -
# is still a real actuation and still tier `ask`, just not `heavy` on top of
# it. This is a judgment call, stated as one: extend this set on the
# owner's own machine if their home has a domain that belongs in it too.
_HEAVY_DOMAINS = frozenset({"lock", "alarm_control_panel", "cover"})


def _configured() -> bool:
    return bool(os.environ.get(URL_ENV, "").strip())


def authenticated() -> bool:
    """Whether an access token is configured. Never reveals the token."""
    return bool(os.environ.get(TOKEN_ENV, "").strip())


# An entity id is `<domain>.<object_id>`, and Home Assistant's own rule is
# that both halves are lowercase ASCII letters, digits and underscores. Used
# to REFUSE anything else rather than to clean it up: an id is not free text,
# and a value that does not look like one is a mistake or an attack, neither
# of which is improved by guessing what was meant.
_ENTITY_ID_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


# One path segment of a Home Assistant domain or service name, same
# character rule as an entity id's two halves.
_SEGMENT_RE = re.compile(r"^[a-z0-9_]+$")


def _is_valid_entity_id(eid: str) -> bool:
    return bool(_ENTITY_ID_RE.match(eid))


def _is_heavy_service(domain: str, entity_id: str = "") -> bool:
    """Whether this call deserves the `heavy` marking.

    BOTH halves are checked, and the entity's half is the one that was
    missing. `homeassistant.turn_on` / `turn_off` / `toggle` are real
    services in the `homeassistant` domain that FORWARD to the entity's own
    domain - so `homeassistant.turn_off` on `lock.front_door` unlocks a
    door, and classifying on the service domain alone ("homeassistant") left
    the approval card without the "this is marked HEAVY" line for exactly
    that. The entity id is what says what is actually being operated.
    """
    if domain.strip().lower() in _HEAVY_DOMAINS:
        return True
    entity_domain = str(entity_id).strip().lower().split(".", 1)[0]
    return bool(entity_domain) and entity_domain in _HEAVY_DOMAINS


# --------------------------------------------------------------------------
#   The plan - one or more requests, worked out locally, sent to no one yet
# --------------------------------------------------------------------------

@dataclass
class Query:
    url: str
    method: str
    why: str = ""
    entity_id: str = ""
    body: Optional[dict] = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Plan:
    kind: str                    # "get_states" | "call_service"
    queries: list = field(default_factory=list)
    heavy: bool = False
    if_refused: str = ""
    authenticated: bool = False
    reason_empty: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        return d


def plan_states(entity_ids: list) -> Plan:
    """Work out one GET per named entity. Opens no socket."""
    raw = [str(e).strip() for e in (entity_ids or []) if str(e).strip()]
    raw = raw[:_MAX_ENTITIES]
    if_refused = "nothing is read; these entities' state stays unknown to Jarvis"

    # Refused, not sanitised. These ids come from the model, and this plan
    # ships at tier `auto` - no card, so nobody sees the URL before it is
    # sent. `../../api/services/lock/unlock` interpolated into the path
    # reaches the wire as a REQUEST TO UNLOCK A DOOR under the standing
    # grant a read was given, and a `?` or `#` re-splits the URL somewhere
    # else entirely. Both are shut here, in two independent ways: a shape
    # check that rejects anything that is not `<domain>.<object_id>`, and
    # `quote(..., safe="")` below so that even a value that passed the shape
    # check cannot change the path's structure.
    bad = [e for e in raw if not _is_valid_entity_id(e)]
    ids = [e for e in raw if _is_valid_entity_id(e)]
    if not ids:
        if bad:
            return Plan(kind="get_states", if_refused=if_refused,
                         authenticated=authenticated(),
                         reason_empty=("none of those look like Home Assistant "
                                       "entity ids (domain.object_id), so nothing "
                                       f"was read: {', '.join(repr(b) for b in bad)}"))
        return Plan(kind="get_states", if_refused=if_refused,
                     authenticated=authenticated(),
                     reason_empty="no entity ids were given to read")
    base = os.environ.get(URL_ENV, "").strip()
    if not base:
        return Plan(kind="get_states", if_refused=if_refused,
                     authenticated=authenticated(),
                     reason_empty=f"{URL_ENV} is not set - there is no Home Assistant to read")

    queries = [
        Query(url=f"{base.rstrip('/')}/api/states/{urllib.parse.quote(eid, safe='')}",
              method="GET",
              why=f"read the current state of {eid}", entity_id=eid)
        for eid in ids
    ]
    return Plan(kind="get_states", queries=queries, if_refused=if_refused,
                authenticated=authenticated())


def plan_service(domain: str, service: str, entity_id: str,
                  data: Optional[dict] = None) -> Plan:
    """Work out the one service call this would make. Opens no socket."""
    domain = str(domain).strip()
    service = str(service).strip()
    entity_id = str(entity_id).strip()
    if_refused = "nothing happens; the entity is left exactly as it is"

    if not domain or not service or not entity_id:
        return Plan(kind="call_service", if_refused=if_refused,
                     authenticated=authenticated(),
                     reason_empty="domain, service, and entity_id are all required")
    # Same shape rule as plan_states, for the same reason - and here the
    # domain and service go into the path too. A service name is one
    # segment, not a path.
    if not _is_valid_entity_id(entity_id):
        return Plan(kind="call_service", if_refused=if_refused,
                     authenticated=authenticated(),
                     reason_empty=(f"{entity_id!r} does not look like a Home Assistant "
                                   "entity id (domain.object_id), so nothing was sent"))
    if not _SEGMENT_RE.match(domain) or not _SEGMENT_RE.match(service):
        return Plan(kind="call_service", if_refused=if_refused,
                     authenticated=authenticated(),
                     reason_empty=(f"{domain!r}.{service!r} is not a Home Assistant "
                                   "domain and service, so nothing was sent"))
    base = os.environ.get(URL_ENV, "").strip()
    if not base:
        return Plan(kind="call_service", if_refused=if_refused,
                     authenticated=authenticated(),
                     reason_empty=f"{URL_ENV} is not set - there is no Home Assistant to control")

    body = {"entity_id": entity_id, **(data or {})}
    heavy = _is_heavy_service(domain, entity_id)
    quoted = urllib.parse.quote
    query = Query(
        url=(f"{base.rstrip('/')}/api/services/"
             f"{quoted(domain, safe='')}/{quoted(service, safe='')}"),
        method="POST",
        why=f"call {domain}.{service} on {entity_id}", entity_id=entity_id, body=body)
    return Plan(kind="call_service", queries=[query], heavy=heavy,
                if_refused=if_refused, authenticated=authenticated())


def describe(p: Plan) -> str:
    """The card text. Every URL and body in full - never a summary."""
    if p.reason_empty:
        verb = "read" if p.kind == "get_states" else "control"
        return f"Jarvis would like to {verb} Home Assistant, but {p.reason_empty}. Nothing would be sent."

    auth_line = (
        "Authenticated: this will send the configured Home Assistant access "
        "token to that server, over each request below."
        if p.authenticated else
        "No access token is configured - this request will very likely be "
        "refused, which Home Assistant requires for any real use."
    )
    if p.kind == "get_states":
        lines = [
            f"Jarvis would like to read the current state of {len(p.queries)} "
            "Home Assistant entit" + ("y" if len(p.queries) == 1 else "ies") + ":",
            "",
            auth_line,
            "",
        ]
        for i, q in enumerate(p.queries, 1):
            lines += [f"  {i}. GET {q.url}", f"     why: {q.why}", ""]
    else:
        q = p.queries[0]
        heavy_line = (
            "This is marked HEAVY: it changes a lock, an alarm, or a cover, "
            "which is a materially bigger consequence than most Home "
            "Assistant actions." if p.heavy else ""
        )
        lines = [
            f"Jarvis would like to call the Home Assistant service on "
            f"\"{q.entity_id}\": {q.why}.",
            "",
            auth_line,
        ]
        if heavy_line:
            lines += ["", heavy_line]
        lines += [
            "",
            f"  POST {q.url}",
            f"     body: {json.dumps(q.body, ensure_ascii=False)}",
            "",
        ]
    lines += [
        "What leaves this machine: exactly the request(s) above, and the "
        "access token if configured - both to that one Home Assistant "
        "server. Nothing else.",
        "",
        f"If you say no: {p.if_refused}",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Execution - only the enumerated request(s)
# --------------------------------------------------------------------------

class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """Stops a redirect from carrying the bearer token to another host.

    `urllib` copies every header except content-length/content-type onto the
    redirect target, cross-host included, so a 302 from the Home Assistant
    host - or from anything that can answer as it: plain `http://`, DNS, a
    reverse proxy - hands over the long-lived token. Rule 3 says a key is
    "sent only to the one service it authenticates against"; following a
    redirect is precisely how it stops being.

    (CPython 3.13 strips `Authorization` across hosts. This does not depend
    on running that version, and still refuses a same-host redirect, which
    3.13 would follow with the header intact.)

    Refused rather than stripped, deliberately: an authenticated REST call
    to `/api/states/...` has no legitimate reason to redirect, and a 401
    from a silently stripped header reads as "wrong token" and sends the
    owner hunting in the wrong place. This says what actually happened.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"refused to follow a redirect to {newurl}: the Home Assistant "
            f"token would have been sent there. Point {URL_ENV} at the final "
            f"address instead.",
            headers,
            fp,
        )


def _default_fetch(q: Query) -> dict:
    """The real call. Adds the real bearer token fresh from the environment -
    never cached, never logged, never part of a `Query`/`Plan` a card was
    shown for, and never followed onto a redirect (see `_RefuseRedirect`)."""
    token = os.environ.get(TOKEN_ENV, "")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if q.body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(q.body).encode("utf-8")
    req = urllib.request.Request(q.url, data=data, method=q.method, headers=headers)
    opener = urllib.request.build_opener(_RefuseRedirect)
    with opener.open(req, timeout=20.0) as r:
        raw = r.read().decode("utf-8", "replace")
        return json.loads(raw) if raw.strip() else {}


def run(p: Plan, *, fetch: Optional[Callable[[Query], dict]] = None,
        approved: bool = False) -> dict:
    """Execute an approved plan, one query at a time. `approved` has no
    default of True - the module that can act on the physical world must
    not be one call away from doing it by accident, more than any other
    module in this project.

    `fetch` is injectable so the parsing below can be proven with no socket,
    the same technique `jarvis_calendar.run()`'s `fetch` uses.
    """
    if not approved:
        return {"ok": False, "reason": "not approved; nothing was done",
                "plan": p.as_dict()}
    if p.reason_empty:
        return {"ok": False, "reason": p.reason_empty}

    getter = fetch or _default_fetch

    if p.kind == "get_states":
        states = []
        for q in p.queries:
            try:
                raw = getter(q)
            except Exception as exc:
                return {"ok": False,
                        "reason": f"reading {q.entity_id} failed: {type(exc).__name__}: {exc}",
                        "states": states}
            attrs = json.dumps(raw.get("attributes", {}), ensure_ascii=False)
            states.append({
                "entity_id": q.entity_id,
                "state": raw.get("state", ""),
                "attributes": attrs[:_MAX_ATTRIBUTES_CHARS],
            })
        return {"ok": True, "states": states}

    # call_service - exactly one query
    q = p.queries[0]
    try:
        raw = getter(q)
    except Exception as exc:
        return {"ok": False,
                "reason": f"the service call failed: {type(exc).__name__}: {exc}"}
    return {"ok": True, "entity_id": q.entity_id, "response": raw}
