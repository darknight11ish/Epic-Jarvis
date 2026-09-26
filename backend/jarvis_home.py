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
    plan_services(domain, service, ids)  ACT on several named entities with
                                          the same service - ONE card for
                                          the set (below).
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

SEVERAL DEVICES ON ONE CARD (the owner's decision of 2026-09-25, after the
creativity audit): "turn off the kitchen, hall and bedroom lights" is ONE
card, not three. `plan_services()` takes the named entities (at most
MAX_GROUP) and plans one POST per entity - the same service, the same data,
each printed in full on the card - so the card is one decision about a
fully listed set, which docs/ARCHITECTURE.md section 2 already allows ("one
decision about one bounded set of things, every one of them shown in full")
and never a standing permission. Locks, alarms, doors, covers and the other
entities in `_stands_alone()` are never grouped: each gets a card of its
own, as before. The plan carries a digest of exactly the requests the card
listed, and `run()` refuses a plan whose requests no longer match it, so
nothing can be added after the card was approved.

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

import jarvis_local_http

URL_ENV = "JARVIS_HOME_URL"
TOKEN_ENV = "JARVIS_HOME_TOKEN"

_MAX_ENTITIES = 20
_MAX_ATTRIBUTES_CHARS = 500

# A lock, an alarm panel, or a cover (garage doors and roller shutters are
# both HA's "cover" domain) changes something with real physical or security
# consequence - so do a valve (water or gas) and a siren, added 2026-09-25
# with several-devices cards. Everything else - lights, switches, climate,
# media players - is still a real actuation and still tier `ask`, just not
# `heavy` on top of it. This is a judgment call, stated as one: extend this
# set on the owner's own machine if their home has a domain that belongs in
# it too.
_HEAVY_DOMAINS = frozenset({"lock", "alarm_control_panel", "cover", "valve", "siren"})

# An entity whose own id says it is a door, a gate, a lock or an alarm is
# treated as heavy too, whatever its domain: a garage opener is very often a
# plain `switch.garage_door` or `button.open_gate`. Whole words of the id
# only ("door" in `switch.front_door`, not in `light.outdoor`).
_HEAVY_WORDS = frozenset({"door", "doors", "gate", "gates", "garage", "lock", "locks",
                          "alarm", "alarms", "security", "safe", "siren", "valve"})

# Never grouped with other devices, though not `heavy` on their own: a
# camera (turning one off is a security matter), and the entities that run
# other things - a script, a scene, an automation, a button - because Jarvis
# cannot see what they would change, and one of them may well unlock a door.
_ALONE_DOMAINS = frozenset({"camera", "script", "scene", "automation", "button",
                            "input_button"})

#: At most this many devices on one card (the owner's decision of
#: 2026-09-25). A longer list is refused, never cut: every device on the card
#: is exactly what runs.
MAX_GROUP = 10


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
    entity_domain, _, object_id = str(entity_id).strip().lower().partition(".")
    if entity_domain and entity_domain in _HEAVY_DOMAINS:
        return True
    return any(w in _HEAVY_WORDS for w in object_id.split("_"))


def _stands_alone(domain: str, entity_id: str) -> bool:
    """Whether this entity always gets an approval card of its own, and is
    never one of several on a card: heavy (a lock, an alarm, a door, a
    cover...), or a camera, script, scene, automation or button."""
    if _is_heavy_service(domain, entity_id):
        return True
    if str(domain).strip().lower() in _ALONE_DOMAINS:
        return True
    return str(entity_id).strip().lower().split(".", 1)[0] in _ALONE_DOMAINS


def _digest(queries) -> str:
    """A fingerprint of exactly the requests a plan will send, taken when the
    plan is made - the card shows those requests; run() checks the plan
    still holds exactly them."""
    import hashlib
    rows = [[q.method, q.url, q.body] for q in queries]
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


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
    kind: str                    # "get_states" | "call_service" | "get_forecast"
    queries: list = field(default_factory=list)
    heavy: bool = False
    if_refused: str = ""
    authenticated: bool = False
    reason_empty: str = ""
    digest: str = ""             # call_service: _digest of the requests planned

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
    insecure = jarvis_local_http.plain_http_problem(base, URL_ENV, "the Home Assistant token")
    if insecure:     # security audit L7
        return Plan(kind="get_states", if_refused=if_refused,
                     authenticated=authenticated(), reason_empty=insecure)

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
    insecure = jarvis_local_http.plain_http_problem(base, URL_ENV, "the Home Assistant token")
    if insecure:     # security audit L7
        return Plan(kind="call_service", if_refused=if_refused,
                     authenticated=authenticated(), reason_empty=insecure)

    # `data` is model-supplied (jarvis_agent._prepare_home_control passes
    # args["data"] straight through), and it used to be spread AFTER
    # entity_id - so `data={"entity_id": "lock.front_door"}` won, and the
    # call operated an entity that had passed no validation and appeared
    # nowhere in the headline. Worse, `heavy` was classified from the
    # argument that had just been overridden, so
    # `turn_off light.kitchen data={"entity_id":"lock.front_door"}`
    # unlocked a door on a card with no "this is marked HEAVY" line at all -
    # and notice_for turns that weight into interrupt-the-owner rather than
    # wait-to-be-found. _is_heavy_service's own docstring promises "the
    # entity id is what says what is actually being operated"; this is what
    # makes that true.
    #
    # area_id/device_id are refused rather than classified: both address
    # things this module cannot resolve to an entity, so neither can be
    # weighed, and "turn off the garage" must not arrive weightless.
    extra = dict(data or {})
    for fan_out in ("area_id", "device_id"):
        if fan_out in extra:
            return Plan(kind="call_service", if_refused=if_refused,
                         authenticated=authenticated(),
                         reason_empty=(f"{fan_out} cannot be checked against what it "
                                       "would actually operate, so nothing was sent - "
                                       "name the entity instead"))
    target = str(extra.pop("entity_id", entity_id)).strip()
    if not _is_valid_entity_id(target):
        return Plan(kind="call_service", if_refused=if_refused,
                     authenticated=authenticated(),
                     reason_empty=(f"{target!r} does not look like a Home Assistant "
                                   "entity id (domain.object_id), so nothing was sent"))
    # entity_id written LAST, so nothing in `data` can displace it again.
    body = {**extra, "entity_id": target}
    heavy = _is_heavy_service(domain, target)
    entity_id = target
    quoted = urllib.parse.quote
    query = Query(
        url=(f"{base.rstrip('/')}/api/services/"
             f"{quoted(domain, safe='')}/{quoted(service, safe='')}"),
        method="POST",
        why=f"call {domain}.{service} on {entity_id}", entity_id=entity_id, body=body)
    return Plan(kind="call_service", queries=[query], heavy=heavy,
                if_refused=if_refused, authenticated=authenticated(),
                digest=_digest([query]))


def _unique(ids) -> list:
    out = []
    for e in ids or []:
        e = str(e).strip()
        if e and e not in out:
            out.append(e)
    return out


def group_problem(domain: str, service: str, entity_ids, data: Optional[dict] = None) -> str:
    """"" when these entities may share ONE card, else why not, in words
    the model can act on. Only for two or more entities - one is always
    plan_service's business. Opens no socket and reads nothing."""
    ids = _unique(entity_ids)
    if len(ids) < 2:
        return ""
    if len(ids) > MAX_GROUP:
        return (f"{len(ids)} devices is too many for one approval card - at most "
                f"{MAX_GROUP}. Ask for them in smaller groups")
    bad = [e for e in ids if not _is_valid_entity_id(e)]
    if bad:
        return ("these do not look like Home Assistant entity ids (domain.object_id): "
                + ", ".join(repr(b) for b in bad))
    extra = dict(data or {})
    for key in ("entity_id", "area_id", "device_id"):
        if key in extra:
            return (f"'{key}' cannot go in data when several devices are named - list "
                    f"every device in entity_ids instead")
    alone = [e for e in ids if _stands_alone(domain, e)]
    if alone:
        return ("a lock, alarm, door, cover, camera, script, scene or button always gets "
                "an approval card of its own, so it cannot be one of several: "
                + ", ".join(alone) + ". Ask for "
                + ("it" if len(alone) == 1 else "each of them")
                + " in a call of its own, and the other devices together")
    return ""


def plan_services(domain: str, service: str, entity_ids,
                  data: Optional[dict] = None) -> Plan:
    """Work out the same service call on each of several named entities -
    one POST each, all on ONE card (MAX_GROUP at most; nothing in
    `_stands_alone` grouped). One entity is exactly plan_service. Opens no
    socket."""
    ids = _unique(entity_ids)
    if len(ids) <= 1:
        return plan_service(domain, service, ids[0] if ids else "", data)
    domain = str(domain).strip()
    service = str(service).strip()
    if_refused = "nothing happens; every one of these devices is left exactly as it is"

    def refused(why: str) -> Plan:
        return Plan(kind="call_service", if_refused=if_refused,
                    authenticated=authenticated(), reason_empty=why)

    if not domain or not service:
        return refused("domain and service are both required")
    if not _SEGMENT_RE.match(domain) or not _SEGMENT_RE.match(service):
        return refused(f"{domain!r}.{service!r} is not a Home Assistant domain and "
                       "service, so nothing was sent")
    problem = group_problem(domain, service, ids, data)
    if problem:
        return refused(problem)
    base = os.environ.get(URL_ENV, "").strip()
    if not base:
        return refused(f"{URL_ENV} is not set - there is no Home Assistant to control")
    insecure = jarvis_local_http.plain_http_problem(base, URL_ENV, "the Home Assistant token")
    if insecure:     # security audit L7
        return refused(insecure)
    quoted = urllib.parse.quote
    url = (f"{base.rstrip('/')}/api/services/"
           f"{quoted(domain, safe='')}/{quoted(service, safe='')}")
    # entity_id written LAST in each body, as in plan_service; group_problem
    # has already refused a `data` that names an entity, area or device.
    queries = [Query(url=url, method="POST", why=f"call {domain}.{service} on {eid}",
                     entity_id=eid, body={**dict(data or {}), "entity_id": eid})
               for eid in ids]
    return Plan(kind="call_service", queries=queries, heavy=False,
                if_refused=if_refused, authenticated=authenticated(),
                digest=_digest(queries))


#: "Lights, plugs and fans without a card" (jarvis_asks_first.py, the
#: owner's decision of 2026-09-26): the only domains, services and `data`
#: keys such a change may use. A plug is Home Assistant's `switch` domain.
EVERYDAY_DOMAINS = frozenset({"light", "switch", "fan"})
EVERYDAY_SERVICES = frozenset({"turn_on", "turn_off", "toggle"})
EVERYDAY_DATA = frozenset({"brightness", "brightness_pct", "brightness_step",
                           "brightness_step_pct", "color_name", "color_temp",
                           "color_temp_kelvin", "kelvin", "rgb_color", "hs_color", "xy_color",
                           "transition", "percentage", "preset_mode", "direction",
                           "oscillating"})


def everyday_problem(p: Plan) -> str:
    """"" when every request in this call_service plan is an everyday switch
    of a light, plug or fan - which, with the owner's setting on, may run
    without a card - else why not. When in doubt, it is not: the call then
    goes to the gate and its card, as before. Opens no socket.

    Each request must: call light, switch or fan's own turn_on, turn_off or
    toggle (not the `homeassistant` domain, which forwards to anything); on
    an entity of that SAME domain; that is not heavy and does not stand
    alone (a lock, alarm, door, gate, garage, cover, valve, camera, scene,
    script, button - by domain or by a word in its id: "switch.garage_door"
    is a door); with no `data` beyond a short list of brightness, colour and
    fan-speed keys."""
    if not isinstance(p, Plan) or p.kind != "call_service" or p.reason_empty or not p.queries:
        return "not a change Jarvis could check"
    if p.heavy:
        return "it includes a lock, alarm, door or cover"
    for q in p.queries:
        tail = str(q.url or "").rsplit("/api/services/", 1)
        parts = tail[1].split("/") if len(tail) == 2 else []
        if len(parts) != 2:
            return "not a change Jarvis could check"
        domain, service = (urllib.parse.unquote(x) for x in parts)
        eid = str(q.entity_id or "")
        if domain not in EVERYDAY_DOMAINS or eid.split(".", 1)[0] != domain:
            return "only lights, plugs and fans go without a card"
        if service not in EVERYDAY_SERVICES:
            return "only on, off and toggle go without a card"
        if _stands_alone(domain, eid):
            return "a lock, alarm, door, cover or similar always gets a card of its own"
        body = q.body if isinstance(q.body, dict) else {}
        if body.get("entity_id") != eid or any(k not in EVERYDAY_DATA for k in body
                                                if k != "entity_id"):
            return "that setting is not one that goes without a card"
    return ""


# --------------------------------------------------------------------------
#   The weather forecast - a third, tiny shape, READ ONLY (2026-09-26)
# --------------------------------------------------------------------------
#
# The owner chose "briefing weather from the owner's own Home Assistant"
# (CLAUDE.md, the cutting-edge decision; the feasibility audit's I75). Home
# Assistant already fetches a forecast for its weather device (many
# installs have "Forecast Home", from met.no); Jarvis asks HA for it, so
# Jarvis itself opens no new connection to any weather service.
#
# HA hands a forecast out only through a SERVICE CALL,
# `POST /api/services/weather/get_forecasts?return_response` - the same
# address shape that ACTS (turns a light on). So this is NOT plan_service
# and never goes through home_control or its card: plan_forecast() builds
# exactly two requests, both fixed here - one GET of the weather device's
# state (for "now" and the temperature unit) and one POST to that one
# service with a body of exactly {"entity_id", "type"} - and run() refuses a
# "get_forecast" plan unless its requests are exactly those, rebuilt from
# the plan's own entity (FORECAST_URL_TAIL, _forecast_problem). No other
# domain, service, body key or query can be reached through it, and
# test_home_control.py proves that with tampered plans. It is a read at tier
# `auto`, under the same gate action as every Home Assistant read
# (`home_read`), and the forecast is OUTSIDE TEXT: whoever reads it marks
# the conversation as having read Home Assistant.
#
# Which device: JARVIS_HOME_WEATHER on the PC (a Windows user setting, like
# JARVIS_HOME_URL), or HA's usual "weather.forecast_home" when it is not
# set. There is no screen for it in either app (the feasibility audit's
# Overwhelm guardrail: "no weather source setting").

WEATHER_ENV = "JARVIS_HOME_WEATHER"
WEATHER_DEFAULT = "weather.forecast_home"
FORECAST_TYPES = ("daily", "twice_daily", "hourly")
#: The one service address a forecast plan may use, after the base URL.
FORECAST_URL_TAIL = "/api/services/weather/get_forecasts?return_response"
_WEATHER_ID_RE = re.compile(r"^weather\.[a-z0-9_]+$")
#: HA's weather conditions (its `weather` integration's own list), in plain
#: words. Anything else is left out, not shown: a condition is text from
#: outside, and a word this list does not know says nothing useful.
CONDITIONS = {
    "clear-night": "clear", "cloudy": "cloudy", "exceptional": "unusual weather",
    "fog": "foggy", "hail": "hail", "lightning": "thunderstorms",
    "lightning-rainy": "thunderstorms and rain", "partlycloudy": "partly cloudy",
    "pouring": "heavy rain", "rainy": "rain", "snowy": "snow", "snowy-rainy": "sleet",
    "sunny": "sunny", "windy": "windy", "windy-variant": "windy and cloudy",
}
_MAX_DAYS = 7


def weather_entity() -> str:
    """The weather device Jarvis reads: JARVIS_HOME_WEATHER, or HA's usual
    one. Not checked here - plan_forecast refuses one that is not
    `weather.<name>`."""
    return os.environ.get(WEATHER_ENV, "").strip() or WEATHER_DEFAULT


def _forecast_queries(base: str, entity_id: str, kind: str) -> list:
    b = base.rstrip("/")
    return [
        Query(url=f"{b}/api/states/{urllib.parse.quote(entity_id, safe='')}", method="GET",
              why=f"read the weather now, from {entity_id}", entity_id=entity_id),
        Query(url=b + FORECAST_URL_TAIL, method="POST",
              why=f"read the {kind.replace('_', ' ')} forecast of {entity_id}",
              entity_id=entity_id, body={"entity_id": entity_id, "type": kind}),
    ]


def plan_forecast(entity_id: Optional[str] = None, kind: str = "daily") -> Plan:
    """The weather now and the forecast, from ONE named weather device.
    Two fixed requests, nothing else. Opens no socket."""
    entity_id = str(entity_id if entity_id is not None else weather_entity()).strip()
    if_refused = "the weather is not read; the briefing says it is not available"

    def refused(why: str) -> Plan:
        return Plan(kind="get_forecast", if_refused=if_refused,
                    authenticated=authenticated(), reason_empty=why)

    if not _WEATHER_ID_RE.match(entity_id):
        return refused(f"{entity_id!r} is not a Home Assistant weather device "
                       f"(weather.<name>) - check {WEATHER_ENV}")
    if kind not in FORECAST_TYPES:
        return refused(f"{kind!r} is not a kind of forecast Home Assistant gives")
    base = os.environ.get(URL_ENV, "").strip()
    if not base:
        return refused(f"{URL_ENV} is not set - there is no Home Assistant to read")
    insecure = jarvis_local_http.plain_http_problem(base, URL_ENV, "the Home Assistant token")
    if insecure:
        return refused(insecure)
    queries = _forecast_queries(base, entity_id, kind)
    return Plan(kind="get_forecast", queries=queries, if_refused=if_refused,
                authenticated=authenticated(), digest=_digest(queries))


def _forecast_problem(p: Plan) -> str:
    """"" when this get_forecast plan holds exactly the two requests
    plan_forecast makes for its own weather device, and nothing else - else
    why not. So no other service, body or address can ride on it."""
    if not isinstance(p, Plan) or p.kind != "get_forecast" or len(p.queries) != 2:
        return "not a weather plan"
    get, post = p.queries
    eid = str(get.entity_id or "")
    if not _WEATHER_ID_RE.match(eid) or post.entity_id != eid:
        return "not a weather device"
    body = post.body if isinstance(post.body, dict) else None
    if body is None or set(body) != {"entity_id", "type"} or body.get("entity_id") != eid \
            or body.get("type") not in FORECAST_TYPES:
        return "not the forecast request"
    base = os.environ.get(URL_ENV, "").strip()
    want = _forecast_queries(base, eid, body["type"]) if base else []
    if not want or [(q.method, q.url, q.body) for q in p.queries] != \
            [(q.method, q.url, q.body) for q in want]:
        return "not the two weather requests"
    if not p.digest or p.digest != _digest(p.queries):
        return "the plan's requests are not the ones it was made with"
    return ""


def _number(v) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if v == v and abs(v) < 1e6 else None


def _forecast_rows(raw, entity_id: str) -> list:
    """The forecast entries HA returned, tidied: date (YYYY-MM-DD, as HA
    wrote it), condition (plain words or ""), high, low, rain chance."""
    resp = raw.get("service_response") if isinstance(raw, dict) else None
    if not isinstance(resp, dict):
        resp = raw if isinstance(raw, dict) else {}
    one = resp.get(entity_id) if isinstance(resp.get(entity_id), dict) else {}
    forecast = one.get("forecast")
    out = []
    for e in (forecast if isinstance(forecast, list) else [])[:_MAX_DAYS * 2]:
        if not isinstance(e, dict):
            continue
        day = str(e.get("datetime") or "")[:10]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            continue
        rain = _number(e.get("precipitation_probability"))
        out.append({"date": day,
                    "condition": CONDITIONS.get(str(e.get("condition") or ""), ""),
                    "high": _number(e.get("temperature")),
                    "low": _number(e.get("templow")),
                    "rain_chance": int(round(rain)) if rain is not None and 0 <= rain <= 100
                    else None})
    return out[:_MAX_DAYS]


def _run_forecast(p: Plan, getter) -> dict:
    problem = _forecast_problem(p)
    if problem:
        return {"ok": False, "reason": f"{problem}, so nothing was sent"}
    get, post = p.queries
    try:
        state = getter(get)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"ok": False, "reason": f"Home Assistant has no device called {get.entity_id}. "
                                           f"Set {WEATHER_ENV} on this PC to your weather "
                                           "device's id"}
        return {"ok": False, "reason": f"Home Assistant answered {exc.code} to the weather read"}
    except Exception as exc:
        return {"ok": False, "reason": f"the weather read failed: {type(exc).__name__}"}
    try:
        raw = getter(post)
    except urllib.error.HTTPError as exc:
        return {"ok": False, "reason": (f"Home Assistant answered {exc.code} to the forecast "
                                        "request; an older Home Assistant cannot hand out "
                                        "forecasts this way")}
    except Exception as exc:
        return {"ok": False, "reason": f"the forecast read failed: {type(exc).__name__}"}
    state = state if isinstance(state, dict) else {}
    attrs = state.get("attributes")
    attrs = attrs if isinstance(attrs, dict) else {}
    unit = attrs.get("temperature_unit")
    unit = unit if unit in ("°C", "°F") else "°"
    now = {"condition": CONDITIONS.get(str(state.get("state") or ""), ""),
           "temp": _number(attrs.get("temperature"))}
    return {"ok": True, "entity_id": get.entity_id, "unit": unit, "now": now,
            "days": _forecast_rows(raw, get.entity_id)}


def describe(p: Plan) -> str:
    """The card text. Every URL and body in full - never a summary."""
    if p.reason_empty:
        verb = "read" if p.kind in ("get_states", "get_forecast") else "control"
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
    elif p.kind == "get_forecast":
        lines = [
            f"Jarvis would like to read the weather from Home Assistant's "
            f"{p.queries[0].entity_id} - the forecast Home Assistant already has. "
            "It changes nothing.",
            "",
            auth_line,
            "",
        ]
        for i, q in enumerate(p.queries, 1):
            lines += [f"  {i}. {q.method} {q.url}", f"     why: {q.why}"]
            if q.body is not None:
                lines.append(f"     body: {json.dumps(q.body, ensure_ascii=False)}")
            lines.append("")
    elif len(p.queries) > 1:
        n = len(p.queries)
        action = p.queries[0].why.split(" on ", 1)[0].replace("call ", "", 1)
        lines = [
            f"Jarvis would like to call {action} on {n} Home Assistant devices: "
            + ", ".join(q.entity_id for q in p.queries) + ".",
            "",
            f"One decision about exactly these {n} devices, each listed below with "
            "its exact request. Nothing is added after you approve, and it gives "
            "no permission for anything later.",
            "",
            auth_line,
            "",
        ]
        for i, q in enumerate(p.queries, 1):
            lines += [f"  {i}. {q.entity_id}: {action}",
                      f"     POST {q.url}",
                      f"     body: {json.dumps(q.body, ensure_ascii=False)}"]
        lines.append("")
    else:
        q = p.queries[0]
        heavy_line = (
            "This is marked HEAVY: it changes a lock, an alarm, a door, a "
            "cover, a valve or a siren, which is a materially bigger "
            "consequence than most Home Assistant actions." if p.heavy else ""
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
    several = p.kind == "call_service" and len(p.queries) > 1
    lines += [
        (f"What leaves this machine: exactly the {len(p.queries)} requests above, and "
         "the access token if configured - all to that one Home Assistant server. "
         "Nothing else." if several else
         "What leaves this machine: exactly the request(s) above, and the "
         "access token if configured - both to that one Home Assistant "
         "server. Nothing else."),
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
    # Plain http:// (home network, Tailscale, Meshnet) never via a proxy -
    # jarvis_local_http.opener_for (security audit L7).
    opener = jarvis_local_http.opener_for(q.url, _RefuseRedirect)
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

    if p.kind == "get_forecast":
        # Read only: exactly the two fixed weather requests, or nothing.
        return _run_forecast(p, getter)
    if p.kind != "call_service":
        return {"ok": False, "reason": "not a plan this module makes, so nothing was sent"}

    # call_service - exactly the requests the card listed, and nothing else.
    if not p.queries or not p.digest or p.digest != _digest(p.queries):
        return {"ok": False,
                "reason": "the plan's requests are not the ones it was made with, so "
                          "nothing was sent"}
    if len(p.queries) == 1:
        q = p.queries[0]
        try:
            raw = getter(q)
        except Exception as exc:
            return {"ok": False,
                    "reason": f"the service call failed: {type(exc).__name__}: {exc}"}
        return {"ok": True, "entity_id": q.entity_id, "response": raw}
    # Several devices, one at a time, in the card's order. A device that
    # fails does not stop the others - each was approved, by name - and the
    # answer says which worked.
    results = []
    for q in p.queries:
        try:
            results.append({"entity_id": q.entity_id, "ok": True, "response": getter(q)})
        except Exception as exc:
            results.append({"entity_id": q.entity_id, "ok": False,
                            "reason": f"the service call failed: {type(exc).__name__}: {exc}"})
    out = {"ok": all(r["ok"] for r in results), "results": results}
    if not out["ok"]:
        failed = [r["entity_id"] for r in results if not r["ok"]]
        out["reason"] = (f"{len(failed)} of {len(results)} did not work: "
                         + ", ".join(failed))
    return out


# --------------------------------------------------------------------------
#   Is Jarvis's token an administrator's? (the feasibility audit's I81)
# --------------------------------------------------------------------------
#
# A token made by a separate, NON-administrator "Jarvis" user in Home
# Assistant cannot use HA's admin-only parts - templates, the stream of
# every event in the house, firing events, the error log - so a leaked
# token can do less. (It can still switch every device: HA gives every user
# that. This narrows the damage; it does not remove it.) The live preflight
# (selftest.py --preflight) warns when the token is an administrator's;
# backend/README.md, "Home Assistant: a user of its own for Jarvis", says
# how to make one.
#
# How it tells, with two requests that read nothing of the house:
#   GET  /api/           "API running." for any token HA accepts;
#   POST /api/template   {"template": "ok"} - HA renders templates for an
#                        administrator's token only (HA's api/__init__.py,
#                        read by the 2026-09-26 research; not checked on the
#                        owner's HA). The constant text "ok" reads nothing.
# Only the preflight calls this; Jarvis's own reads never do.

ADMIN_PROBE_TAIL = "/api/template"
ADMIN_PROBE_BODY = {"template": "ok"}


def _default_probe(method: str, url: str, body: Optional[dict]) -> int:
    """The HTTP status HA answers - through the same opener as every other
    request here: never a proxy for plain http, never a redirect."""
    token = os.environ.get(TOKEN_ENV, "")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    opener = jarvis_local_http.opener_for(url, _RefuseRedirect)
    try:
        with opener.open(req, timeout=10.0) as r:
            r.read(4096)
            return int(r.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def check_token(*, probe: Optional[Callable] = None) -> dict:
    """{"state", "why"}: "not_set_up", "insecure", "refused" (HA does not
    accept the token), "unreachable", "user" (a plain user's - good) or
    "admin" (an administrator's). Never the token itself. Never raises."""
    base = os.environ.get(URL_ENV, "").strip()
    if not base or not authenticated():
        return {"state": "not_set_up", "why": "Home Assistant is not set up on this PC"}
    insecure = jarvis_local_http.plain_http_problem(base, URL_ENV, "the Home Assistant token")
    if insecure:
        return {"state": "insecure", "why": insecure}
    ask = probe or _default_probe
    b = base.rstrip("/")
    try:
        first = ask("GET", b + "/api/", None)
    except Exception as exc:
        return {"state": "unreachable",
                "why": f"Home Assistant did not answer ({type(exc).__name__})"}
    if first in (401, 403):
        return {"state": "refused", "why": "Home Assistant does not accept Jarvis's token"}
    if first != 200:
        return {"state": "unreachable", "why": f"Home Assistant answered {first}"}
    try:
        second = ask("POST", b + ADMIN_PROBE_TAIL, dict(ADMIN_PROBE_BODY))
    except Exception as exc:
        return {"state": "unreachable",
                "why": f"Home Assistant did not answer ({type(exc).__name__})"}
    if second == 200:
        return {"state": "admin", "why": "the token belongs to an administrator"}
    if second in (401, 403):
        return {"state": "user", "why": "the token belongs to a user who is not an administrator"}
    return {"state": "unreachable", "why": f"Home Assistant answered {second} to the check"}
