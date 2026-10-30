"""jarvis_parking.py - what a parking stay costs, minute by minute, from public data.

A parking sign is not one number. It is a set of time windows - a weekday
morning rate, an afternoon rate, an evening rate, a Saturday rate, a Sunday
that is free, a "2 hour max" that itself only applies during the day - and the
only honest answer to "what will this cost me from 4:15 to 9:00 on Thursday"
is to walk the stay one minute at a time and add up whichever window is in
force at that minute.

That is what `evaluate_parking_stay` does, and it is the whole point of this
module. Two mistakes it exists to avoid, both of which cost the owner money:

1. THE TAIL-END OVERLAP. A blockface with a 2-hour limit enforced 08:00-18:00
   looks illegal for a 4h 45m stay - but from 16:15 to 18:00 the car is only
   parked for 105 of those minutes during the enforced hours, and at 18:00 the
   limit expires for the night. Parking 16:15-21:00 there is legal, and cheaper
   than any garage. A check that compares the STAY's length with the sign's
   limit hides it. This one compares the ENFORCED minutes.
2. THE STATIC RATE. Quoting the 4:15 PM rate for the whole stay says $21.38
   where the real cost is $9.38, because the rate drops at 5 and goes to zero
   at 8.

WHAT IT IS, AND WHAT IT IS NOT (said plainly, because this project does not
claim more than the evidence supports)

* It is a COST ESTIMATE built from public parking data. It is **not** a
  booking, a reservation, or navigation.
* It does **not** know: tow-away and no-stopping signs that are not in the
  data, a permit zone the owner does not hold, a ramp or garage whose price is
  not published in a form this file can read, a sign that changed since the
  data was last refreshed, or the cost of the ticket if the owner overstays.
* A place whose price is NOT published is never quoted as $0.00. It carries
  `rates_known=False`, `evaluate_parking_stay` refuses to price it, and the
  answer says how many nearby places were left out for that reason instead of
  guessing.

WHERE THE PRICES COME FROM - two public services, no key, no account

* Seattle SDOT's **Blockface** layer on the City of Seattle's ArcGIS REST
  service: per-block curb pricing (`WKD_RATE1..3`, `SAT_RATE*`, `SUN_RATE*`,
  the minute-offsets those rates start and end at, `PARKING_TIME_LIMIT` and
  `PARKING_SPACES`). Zero API key. Only asked for when the point is inside
  Seattle's own bounding box.
* **OpenStreetMap** through the Overpass API: off-street lots and garages, and
  mapped street-parking lanes, anywhere in the world. It also runs beside the
  Seattle layer so surface lots and garages are not missing.
* **Nominatim** turns a place NAME into a latitude and longitude - the one
  lookup that necessarily carries words rather than a point.

WHAT LEAVES THIS PC, EXACTLY (CLAUDE.md rule 1; the owner's own instruction of
2026-10-29: "never send personal data - send coordinates/radius only")

* To Overpass and to Seattle's ArcGIS service: a latitude, a longitude and a
  radius. Nothing else - no name, no address, no chat text, no calendar entry.
* To Nominatim: the place NAME the owner himself typed or said (or, for the
  calendar bridge, the calendar event's own LOCATION line - and only ever after
  he asked about that event). Never a chat message, never an event TITLE, never
  a note, never a person's name out of memory.
* No API key, no token, no cookie, no account is involved anywhere.
* Every answer is cached in a local SQLite file (`parking-cache.db`, beside
  this module, 24 hours) so a repeated question makes no request at all.

THE NETWORK IS INJECTABLE, AND THE TESTS ALWAYS INJECT IT

Every function that would touch the network takes `transport=`, a callable
`transport(method, url, *, body=None, headers=None) -> (status, bytes)`. The
suites pass a recorder, so `backend/test_parking.py` makes no request at all
and CI never reaches Seattle, Overpass or Nominatim.

THE CALENDAR BRIDGE, AND ITS ONE HONEST LIMIT

`next_event_with_a_place` reads the next event that has a location, through
`jarvis_google_calendar.list_events` when that module and a way in are
available, and degrades to "no event" in one sentence when they are not. It
gives the parking lookup the event's WINDOW (start - 15 min to end + 15 min).

It deliberately does NOT send the event's location line to a public map
service. A calendar entry is private even when the venue is public, and this
module's rule is that only a name the owner said out loud, or a latitude and
longitude, ever leaves the PC. So the calendar answer quotes the venue back
locally and offers the exact sentence to say, with the times already filled in;
saying it makes it the owner's own words and the lookup proceeds normally. If
the event's location already IS a coordinate pair, there is nothing to send and
the lookup runs in one step.

WHAT THIS FILE DOES NOT DO

No card, no model, no route, no file except its own cache. It changes nothing:
every function here reads public data and returns words. There is no
`find_parking` model tool either - it would take one of the six tool slots on
the 8 GB card, and the deterministic quick path in `jarvis_quick.py` answers
the same sentences for zero model tokens.

Standard library only (`urllib.request`, `urllib.parse`, `json`, `math`, `re`,
`sqlite3`, `datetime`), so `requirements.lock` does not move.

DESIGN BORROWED FROM OPEN SOURCE, NO CODE COPIED

The curb-regulation time-window model follows the Open Mobility Foundation's
Curb Data Specification and SharedStreets' CurbLR; the "one normalized
candidate per source" adapter shape follows ParkenDD/parkapi-sources-v3; the
OpenStreetMap tag reading follows MapComplete and street_parking.py; the
conditional-time grammar follows opening_hours.js (as a SPEC, not a port); and
the Overpass query shape follows overpy. Each is credited in
THIRD-PARTY-NOTICES.txt; none is a dependency, and no line of theirs is here.
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, List, Optional, Tuple

# --------------------------------------------------------------------------
#   Where the public data lives, and how much of it we ask for
# --------------------------------------------------------------------------

#: Seattle's own bounding box, as the blueprint and the city's open data
#: describe it: (lat_min, lon_min, lat_max, lon_max). Outside this, the SDOT
#: blockface layer is not asked at all - it would only return nothing.
SEATTLE_BBOX = (47.48, -122.44, 47.74, -122.24)

#: The Blockface layer's own query endpoint (City of Seattle GeoData). Public
#: domain, no key, no account.
SEATTLE_BLOCKFACE_URL = (
    "https://services.arcgis.com/ZOyb2t4B0UYuYNYH/arcgis/rest/services/"
    "Blockface/FeatureServer/0/query")

#: OpenStreetMap's Overpass API: off-street lots and garages, and mapped
#: street-parking lanes, anywhere in the world.
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

#: Nominatim: a place name to a latitude and longitude. Public instance, no
#: key. Its usage policy asks for an identifying User-Agent and at most one
#: request a second - both honoured below.
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

#: Says who is asking, as Nominatim's policy requires. It carries nothing
#: about the owner: no name, no machine name, no account, no version of his
#: system that could identify him.
USER_AGENT = "EpicJarvis/1.0 (local personal assistant; parking cost estimate)"

#: How long a cached answer is used before the public service is asked again.
CACHE_TTL_SECONDS = 24 * 60 * 60

#: The cache's own file, beside this module (never in the repository).
CACHE_NAME = "parking-cache.db"

#: An environment override so a suite (or a second install) can point the
#: cache somewhere else without touching this file.
CACHE_ENV = "JARVIS_PARKING_DB"

#: How far around the destination to look, in metres. 800 m is a ten-minute
#: walk: far enough to find a blockface, close enough to be worth parking on.
RADIUS_M = 800

#: How many legal options an answer ranks. Three on the PC, two on the phone.
LIMIT = 3

#: ~80 m a minute is an ordinary walking pace on a city street.
WALK_M_PER_MIN = 80.0

#: How far either side of a calendar event the parking window reaches, so the
#: owner is parked and back in the room without cutting it fine.
PAD_MINUTES = 15

#: Nominatim asks for at most one request a second. This module remembers when
#: it last asked and waits the remainder - only for a real geocode that was not
#: cached, which on a normal second question there never is.
_NOMINATIM_MIN_GAP = 1.1
_last_geocode_at = 0.0

#: The least a place name may be, and the most this file will send.
_MIN_PLACE_CHARS = 2
_MAX_PLACE_CHARS = 120

#: A day of minutes, so the loop and the band arithmetic share one constant.
_DAY_MIN = 24 * 60

#: Python's own weekday() order, which every RateBand uses: Monday is 0.
_WEEKDAYS = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")


# --------------------------------------------------------------------------
#   The dataclasses: a band, a place, and what a stay there costs
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class RateBand:
    """One time-of-day rule, as a parking sign states it.

    `[start_min, end_min)` are MINUTES AFTER MIDNIGHT on the days named by
    `days_of_week` (0 = Monday, Python's `datetime.weekday()`), so 480 is 08:00
    and 1020 is 17:00. A band that ends where it starts is not a thing here:
    a window that crosses midnight is written as two bands, which is also how
    the conditional-time parser below emits it.
    """

    days_of_week: Tuple[int, ...]
    start_min: int
    end_min: int
    #: US dollars an hour while this band is in force. 0.0 is free.
    rate_per_hour: float
    #: A maximum stay, in minutes, enforced while this band is in force. It is
    #: counted over the minutes that MATCH this band, never over the whole
    #: stay - that difference is the tail-end overlap this module gets right.
    max_stay_min: Optional[int] = None
    #: True for a rule that forbids parking outright (a tow-away window, a
    #: permit-only zone). `evaluate_parking_stay` refuses the stay there.
    no_parking: bool = False


@dataclass(frozen=True)
class CostSegment:
    """One unbroken stretch of a stay at one rate - what the answer shows.

    `start_min` is the clock the stretch began at, as minutes after midnight,
    and `limit_min` is the maximum stay in force during it (None when the sign
    states none). A 4h 45m stay across three rate tiers is three segments, and
    saying so is how "$9.38" becomes believable.
    """

    minutes: int
    rate_per_hour: float
    start_min: int
    limit_min: Optional[int] = None


@dataclass(frozen=True)
class ParkingCandidate:
    """One place one could park, normalized across the two providers.

    `kind` is "street_free", "street_paid", "street_limited", "lot" or
    "garage". `rate_bands` is the whole sign; an empty tuple with
    `rates_known=True` means genuinely unrestricted (free) parking, which is
    different from `rates_known=False`, which means "nobody published the
    price" and is never quoted.
    """

    id: str
    name: str
    kind: str
    lat: float
    lon: float
    distance_m: float
    spaces: Optional[int] = None
    rpz_zone: Optional[str] = None
    daily_max_usd: Optional[float] = None
    rate_bands: Tuple[RateBand, ...] = field(default_factory=tuple)
    source: str = "osm"
    source_url: str = ""
    #: False when the source says there IS parking here but not what it costs.
    #: Such a place is counted and named, never priced.
    rates_known: bool = True
    #: The price of a place that publishes only a DAY price. Charged flat for
    #: any stay, so a short stay is over-quoted rather than under-quoted.
    flat_usd: Optional[float] = None


@dataclass(frozen=True)
class StayQuote:
    """What one stay at one candidate costs, and whether it is legal at all."""

    candidate: ParkingCandidate
    legal: bool
    rejection_reason: str
    total_cost_usd: float
    paid_minutes: int
    free_minutes: int
    enforced_minutes: int
    max_stay_limit_min: Optional[int]
    walk_minutes: int
    summary_line: str
    #: The stretch-by-stretch breakdown the answer prints (see CostSegment).
    segments: Tuple[CostSegment, ...] = field(default_factory=tuple)
    #: The clock the paid stretch ended and free parking began, in minutes
    #: after midnight, or None when the stay never becomes free.
    free_from_min: Optional[int] = None
    #: The clock a maximum stay stopped applying (the sign's own window
    #: ending), or None when no limit was in force at all.
    limit_ends_min: Optional[int] = None


# --------------------------------------------------------------------------
#   Small shared words and arithmetic
# --------------------------------------------------------------------------

def clock_words(minute_of_day: int) -> str:
    """480 -> "8:00 AM", 1080 -> "6:00 PM", 0 -> "midnight"."""
    minute_of_day = int(minute_of_day) % _DAY_MIN
    if minute_of_day == 0:
        return "midnight"
    hour, minute = divmod(minute_of_day, 60)
    mer = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return f"{hour12}:{minute:02d} {mer}"


def _minute_of_day(moment: datetime) -> int:
    return moment.hour * 60 + moment.minute


def length_words(minutes: int) -> str:
    """285 -> "4h 45m", 120 -> "2h", 45 -> "45m"."""
    minutes = max(0, int(minutes))
    hours, rest = divmod(minutes, 60)
    if hours and rest:
        return f"{hours}h {rest}m"
    if hours:
        return f"{hours}h"
    return f"{rest}m"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Metres between two points on the Earth, good enough for a walk."""
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2.0) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2)
    return 2.0 * radius * math.asin(min(1.0, math.sqrt(a)))


def in_seattle(lat: float, lon: float) -> bool:
    """Is this point inside Seattle's own bounding box?"""
    lat_min, lon_min, lat_max, lon_max = SEATTLE_BBOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def _money(value: float) -> str:
    return f"${value:.2f}"


def _price_label(quote: "StayQuote", *, total: bool = False) -> str:
    """"FREE" or "$3.50", with "total" when the answer is the whole stay."""
    if quote.total_cost_usd == 0.0:
        return "FREE"
    return _money(quote.total_cost_usd) + (" total" if total else "")


# --------------------------------------------------------------------------
#   THE INTEGRATOR: what a stay costs, minute by minute
# --------------------------------------------------------------------------

def _band_for(cand: ParkingCandidate, moment: datetime) -> Optional[RateBand]:
    """The band in force at `moment`, or None for unrestricted minutes."""
    weekday = moment.weekday()
    minute = _minute_of_day(moment)
    for band in cand.rate_bands:
        if weekday in band.days_of_week and band.start_min <= minute < band.end_min:
            return band
    return None


def evaluate_parking_stay(
    cand: ParkingCandidate,
    start_dt: datetime,
    end_dt: datetime,
    allow_rpz_permit: Optional[str] = None,
) -> StayQuote:
    """Walk `[start_dt, end_dt)` one minute at a time across `cand.rate_bands`.

    Correct for, and tested against, all of:
      * rate tiers that change during the stay (morning -> afternoon ->
        evening -> overnight free),
      * a maximum stay whose own window ENDS during the stay (the legal
        tail-end overlap),
      * a stay that crosses midnight, and a Sunday or an after-hours window
        that is free,
      * a flat daily cap on an off-street lot or garage,
      * a permit zone, and a rule that forbids parking outright.

    It never guesses a price: a candidate whose price is not published
    (`rates_known=False`) is returned illegal with that as the reason.
    """
    total_minutes = int((end_dt - start_dt).total_seconds() // 60)
    if total_minutes <= 0:
        raise ValueError("end_dt must be after start_dt")

    walk_minutes = max(1, int(round(cand.distance_m / WALK_M_PER_MIN)))

    def refuse(reason: str, *, cost: float = 0.0, paid: int = 0, free: int = 0,
               enforced: int = 0, limit: Optional[int] = None) -> StayQuote:
        return StayQuote(candidate=cand, legal=False, rejection_reason=reason,
                         total_cost_usd=round(cost, 2), paid_minutes=paid,
                         free_minutes=free, enforced_minutes=enforced,
                         max_stay_limit_min=limit, walk_minutes=walk_minutes,
                         summary_line="")

    if not cand.rates_known:
        return refuse("the price here is not published in a form I can read, "
                      "so I will not guess one")

    if cand.rpz_zone and cand.rpz_zone != allow_rpz_permit:
        return refuse(f"a restricted parking zone (permit {cand.rpz_zone}), and "
                      f"no permit for it is saved")

    cost = 0.0
    paid_min = 0
    free_min = 0
    active_limit: Optional[int] = None
    limit_ends_min: Optional[int] = None
    free_from_min: Optional[int] = None
    saw_paid = False
    days_seen = set()
    segments: List[CostSegment] = []
    #: How many of the stay's minutes fall inside a band that carries a maximum
    #: stay, per limit, in the order the limits were met. It is counted over the
    #: WHOLE stay rather than stopping at the first minute over, because the
    #: honest sentence names the real overlap - "150 min during the 2h limit",
    #: not "121 minutes, which is the 121st minute I noticed".
    enforced_by_limit: dict = {}

    # One entry per minute of the stay, in order: (rate, limited, minute-of-day).
    for offset in range(total_minutes):
        moment = start_dt + timedelta(minutes=offset)
        minute_of_day = _minute_of_day(moment)
        days_seen.add(moment.date())
        band = _band_for(cand, moment)

        if band is None:
            # Outside every rule: unrestricted, and free.
            free_min += 1
            if active_limit is not None and limit_ends_min is None:
                limit_ends_min = minute_of_day
            active_limit = None
            if saw_paid and free_from_min is None:
                free_from_min = minute_of_day
            if segments and segments[-1].rate_per_hour == 0.0 \
                    and segments[-1].limit_min is None \
                    and segments[-1].start_min + segments[-1].minutes == minute_of_day:
                segments[-1] = CostSegment(segments[-1].minutes + 1, 0.0,
                                           segments[-1].start_min, None)
            else:
                segments.append(CostSegment(1, 0.0, minute_of_day, None))
            continue

        if band.no_parking:
            return refuse(f"No parking allowed at {clock_words(minute_of_day)}",
                          cost=cost, paid=paid_min, free=free_min,
                          enforced=sum(enforced_by_limit.values()),
                          limit=band.max_stay_min)

        if band.rate_per_hour > 0:
            cost += band.rate_per_hour / 60.0
            paid_min += 1
            saw_paid = True
        else:
            free_min += 1
            if saw_paid and free_from_min is None:
                free_from_min = minute_of_day

        rate = float(band.rate_per_hour)
        if band.max_stay_min:
            active_limit = band.max_stay_min
            enforced_by_limit[band.max_stay_min] = \
                enforced_by_limit.get(band.max_stay_min, 0) + 1
        else:
            if active_limit is not None and limit_ends_min is None:
                limit_ends_min = minute_of_day
            active_limit = None

        if segments and segments[-1].rate_per_hour == rate \
                and segments[-1].limit_min == band.max_stay_min \
                and segments[-1].start_min + segments[-1].minutes == minute_of_day:
            segments[-1] = CostSegment(segments[-1].minutes + 1, rate,
                                       segments[-1].start_min, band.max_stay_min)
        else:
            segments.append(CostSegment(1, rate, minute_of_day, band.max_stay_min))

    enforced_total = sum(enforced_by_limit.values())
    for limit, counted in enforced_by_limit.items():
        if counted > limit:
            return refuse(
                f"Exceeds {limit // 60}h time limit "
                f"({counted} min overlap during enforced hours)",
                cost=cost, paid=paid_min, free=free_min,
                enforced=counted, limit=limit)

    if cand.daily_max_usd is not None and cand.daily_max_usd >= 0:
        # A lot or garage caps a DAY, so a stay touching two dates may use the
        # cap twice - and the answer below says when that happened.
        cost = min(cost, float(cand.daily_max_usd) * max(1, len(days_seen)))
    if cand.flat_usd is not None:
        # A place that publishes only a day price charges it for each day the
        # stay touches. The free/piecewise arithmetic above still ran, so the
        # segments still show what the sign says; the total is the price the
        # place publishes.
        cost = float(cand.flat_usd) * max(1, len(days_seen))

    cost = round(cost, 2)
    if cost == 0.0:
        cost_label = "FREE ($0.00)"
    else:
        cost_label = f"{_money(cost)} total"
    summary = (f"{cand.name} - {cost_label} - "
               f"{int(round(cand.distance_m))} m walk (~{walk_minutes} min)")
    # The limit the answer names: the one that governed the most of the stay,
    # not whatever the last minute happened to be under.
    reported_limit = (max(enforced_by_limit, key=lambda k: enforced_by_limit[k])
                      if enforced_by_limit else None)
    return StayQuote(candidate=cand, legal=True, rejection_reason="",
                     total_cost_usd=cost, paid_minutes=paid_min,
                     free_minutes=free_min, enforced_minutes=enforced_total,
                     max_stay_limit_min=reported_limit, walk_minutes=walk_minutes,
                     summary_line=summary, segments=tuple(segments),
                     free_from_min=free_from_min, limit_ends_min=limit_ends_min)


# --------------------------------------------------------------------------
#   Reading an OpenStreetMap sign: charge, maxstay, conditional windows
# --------------------------------------------------------------------------

_CURRENCY = r"(?:US\$|\$|USD|usd)"


def parse_charge(text) -> Optional[Tuple[float, Optional[float]]]:
    """An OSM `charge` tag -> (dollars an hour, dollars a day or None).

    Accepts the forms OpenStreetMap actually uses: "2.00 USD/hour", "$3/hr",
    "5.00 USD/day", "2 USD per hour", "12.00 USD/day; 2.00 USD/hour". None
    when the text holds no price this file can read - never a guess.

    A day price with no hourly one comes back as `(0.0, day)`: there is no
    honest hourly rate to divide it into, and the caller charges the day price
    for any stay instead (`ParkingCandidate.flat_usd`).
    """
    raw = str(text or "").strip().lower().replace(",", ".")
    if not raw:
        return None
    hourly: Optional[float] = None
    daily: Optional[float] = None
    for part in re.split(r"[;|]", raw):
        piece = part.strip()
        if not piece:
            continue
        amount = _first_number(piece)
        if amount is None:
            continue
        if re.search(r"\b(day|daily|d)\b|/d\b", piece):
            if daily is None:
                daily = amount
        elif re.search(r"\b(hour|hourly|hr|h)\b|/h\b", piece):
            if hourly is None:
                hourly = amount
        elif hourly is None:
            # A bare amount with no unit at all: read as an hourly price, which
            # is the unit `charge` uses by convention.
            hourly = amount
    if hourly is None and daily is None:
        return None
    return (hourly or 0.0, daily)


def _first_number(text: str) -> Optional[float]:
    """The first number in a string, or None. "$3/hr" -> 3.0."""
    m = re.search(r"\d+(?:\.\d+)?", str(text or ""))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def parse_maxstay(text) -> Optional[int]:
    """An OSM `maxstay` tag -> minutes. "2 hours", "120 minutes", "30 min"."""
    raw = str(text or "").strip().lower()
    if not raw:
        return None
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(minutes?|mins?|m|hours?|hrs?|h|days?|d)", raw)
    if not m:
        return None
    amount = float(m.group(1).replace(",", "."))
    unit = m.group(2)
    if unit.startswith("d"):
        minutes = amount * _DAY_MIN
    elif unit.startswith("h"):
        minutes = amount * 60
    else:
        minutes = amount
    if minutes <= 0:
        return None
    return int(round(minutes))


def _day_set(text: str) -> Tuple[int, ...]:
    """'Mo-Fr' -> (0, 1, 2, 3, 4); 'Sa,Su' -> (5, 6); 'PH' -> ().

    An unknown token is skipped rather than guessed at, so a string this file
    does not fully understand can only produce FEWER windows, never invented
    ones.
    """
    days = set()
    for piece in re.split(r"\s*,\s*", text.strip()):
        token = piece.strip()
        if not token:
            continue
        first, _, last = token.partition("-")
        if last:
            a = _weekday_index(first)
            b = _weekday_index(last)
            if a is None or b is None:
                continue
            if a <= b:
                days.update(range(a, b + 1))
            else:
                days.update(range(a, 7))
                days.update(range(0, b + 1))
            continue
        index = _weekday_index(token)
        if index is not None:
            days.add(index)
    return tuple(sorted(days))


def _weekday_index(token: str) -> Optional[int]:
    """'Mo', 'mo', 'Mo.' -> 0. None for a day name this file does not know
    (`PH` - public holidays - is deliberately none of them: a rule about a
    holiday is not a rule about a weekday)."""
    word = str(token or "").strip().rstrip(".").title()[:2]
    return _WEEKDAYS.index(word) if word in _WEEKDAYS else None


def _minute_intervals(text: str) -> List[Tuple[int, int]]:
    """'18:00-08:00' -> [(1080, 1440), (0, 480)]; a window crosses midnight."""
    out: List[Tuple[int, int]] = []
    for piece in re.split(r"\s*,\s*", text.strip()):
        m = re.fullmatch(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", piece.strip())
        if not m:
            continue
        start = int(m.group(1)) * 60 + int(m.group(2))
        end = int(m.group(3)) * 60 + int(m.group(4))
        if start == end:
            continue
        if start < end:
            out.append((start, min(end, _DAY_MIN)))
        else:
            out.append((start, _DAY_MIN))
            out.append((0, min(end, _DAY_MIN)))
    return out


def _complement(covered: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """The minutes of a day NOT in `covered`, as ascending intervals."""
    merged: List[Tuple[int, int]] = []
    for start, end in sorted(covered):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    gaps: List[Tuple[int, int]] = []
    cursor = 0
    for start, end in merged:
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < _DAY_MIN:
        gaps.append((cursor, _DAY_MIN))
    return gaps


def parse_osm_conditional_window(text, rate_per_hour: float = 0.0) -> Tuple[str, Tuple[RateBand, ...]]:
    """An OSM `fee:conditional` tag -> ("free"|"paid", bands).

    The two forms OpenStreetMap actually carries:

      "no @ (Mo-Fr 18:00-08:00; Sa-Su)"   - FREE in those windows (and the rest
                                            of the week keeps the `fee`/`charge`
                                            rules)
      "yes @ (Mo-Sa 08:00-18:00)"         - PAID in those windows only, at
                                            `rate_per_hour` (the caller's own
                                            reading of `charge`, because the
                                            conditional tag does not repeat the
                                            price)

    Returns ("", ()) when the text cannot be read, so the caller keeps the
    ordinary `fee` reading rather than inventing a window.
    """
    raw = str(text or "").strip()
    if not raw:
        return "", ()
    m = re.fullmatch(r"(yes|no)\s*@\s*\((.*)\)\s*", raw, re.IGNORECASE)
    if not m:
        return "", ()
    mode = "paid" if m.group(1).lower() == "yes" else "free"
    rate = float(rate_per_hour) if mode == "paid" else 0.0
    bands: List[RateBand] = []
    for rule in re.split(r"\s*;\s*", m.group(2)):
        rule = rule.strip()
        if not rule:
            continue
        day_part, _, time_part = rule.partition(" ")
        days = _day_set(day_part)
        # A rule with no clock is the whole day: "Sa-Su" in
        # "no @ (Mo-Fr 18:00-08:00; Sa-Su)" means free all Sunday and Saturday.
        intervals = _minute_intervals(time_part) if time_part.strip() else [(0, _DAY_MIN)]
        if not days or not intervals:
            continue
        for start, end in intervals:
            bands.append(RateBand(days_of_week=days, start_min=start, end_min=end,
                                  rate_per_hour=rate))
    if not bands:
        return "", ()
    return mode, tuple(bands)


# --------------------------------------------------------------------------
#   The cache: one SQLite file, 24 hours, never a reason to fail
# --------------------------------------------------------------------------

def cache_path() -> str:
    """Where the cache lives: `JARVIS_PARKING_DB`, else beside this module."""
    override = os.environ.get(CACHE_ENV) or ""
    if override:
        return override
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), CACHE_NAME)


def _cache_ready(path: str) -> Optional[sqlite3.Connection]:
    """A closed-on-exit connection with the one table, or None if it will not."""
    try:
        conn = sqlite3.connect(path, timeout=5)
        conn.execute("CREATE TABLE IF NOT EXISTS parking_cache ("
                     "key TEXT PRIMARY KEY, fetched_at REAL NOT NULL, "
                     "payload TEXT NOT NULL)")
        conn.commit()
        return conn
    except Exception:
        return None


def cache_get(key: str, *, path: Optional[str] = None,
              ttl: float = CACHE_TTL_SECONDS, now: Optional[float] = None) -> Optional[dict]:
    """The cached JSON for `key`, or None. Never raises: a broken cache is a
    cache miss, not a failed lookup."""
    conn = _cache_ready(path or cache_path())
    if conn is None:
        return None
    try:
        row = conn.execute("SELECT fetched_at, payload FROM parking_cache "
                           "WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        moment = time.time() if now is None else now
        if float(row[0]) + float(ttl) < moment:
            return None
        return json.loads(row[1])
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def cache_put(key: str, payload: dict, *, path: Optional[str] = None,
              now: Optional[float] = None) -> None:
    """Store one answer for 24 hours. Never raises: a cache that cannot write
    leaves the lookup working, only slower."""
    conn = _cache_ready(path or cache_path())
    if conn is None:
        return
    try:
        conn.execute("INSERT OR REPLACE INTO parking_cache (key, fetched_at, payload) "
                     "VALUES (?, ?, ?)",
                     (key, time.time() if now is None else now,
                      json.dumps(payload, sort_keys=True)))
        conn.commit()
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _area_key(provider: str, lat: float, lon: float, radius_m: int) -> str:
    # Four decimals is about 11 m: a radius does not change over that, and the
    # cache stays useful as the owner walks down a street.
    return f"{provider}:{lat:.4f}:{lon:.4f}:{int(radius_m)}"


def _place_key(place: str) -> str:
    return "geocode:" + " ".join(str(place).lower().split())[:_MAX_PLACE_CHARS]


# --------------------------------------------------------------------------
#   The one way out: an injectable transport, so no test ever calls the net
# --------------------------------------------------------------------------

def default_transport(method: str, url: str, *, body: Optional[bytes] = None,
                      headers: Optional[dict] = None,
                      timeout: float = 8.0) -> Tuple[int, bytes]:
    """One HTTPS request, and its (status, bytes).

    The only function in this file that touches the network. Every caller takes
    a `transport=` that defaults to this one, and the suites always pass their
    own, so a test run makes no request at all.

    EIGHT SECONDS, because this runs inside a chat turn and Overpass's own
    query carries `[timeout:8]`: a parking answer may be slow, but it may not
    leave the owner waiting on a service that has stopped answering.
    """
    request = urllib.request.Request(url, data=body, method=str(method).upper())
    request.add_header("User-Agent", USER_AGENT)
    for name, value in (headers or {}).items():
        request.add_header(str(name), str(value))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return int(getattr(response, "status", 200) or 200), response.read()


def _payload(status: int, raw, *, what: str) -> dict:
    """The JSON body of a response, or a plain refusal naming `what`.

    A LIST is a valid body here: Nominatim answers with a JSON array, and
    treating that as "something unexpected" made every place name unfindable.
    """
    if status != 200:
        return {"ok": False, "reason": f"{what} did not answer"}
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        got = json.loads(raw or "null")
    except Exception:
        return {"ok": False, "reason": f"{what} did not answer in a form I can read"}
    if not isinstance(got, (dict, list)):
        return {"ok": False, "reason": f"{what} did not answer in a form I can read"}
    return {"ok": True, "body": got}


# --------------------------------------------------------------------------
#   Provider 1: Seattle SDOT Blockface (ArcGIS REST), no API key
# --------------------------------------------------------------------------

#: The attribute names this file reads, in the casing the city's own document
#: uses. The query asks for every field (`outFields=*`) rather than this list,
#: because a layer whose field list has changed must not turn a valid query
#: into "Invalid field" - and every read below is case-insensitive, since a
#: layer's field names have been re-cased without notice more than once.
_SDOT_READ = ("UNITDESC", "PARKING_CATEGORY", "PARKING_TIME_LIMIT",
              "PARKING_SPACES", "RPZ_ZONE", "START_TIME_WKD", "END_TIME_WKD",
              "START_TIME_SAT", "END_TIME_SAT",
              "WKD_RATE1..3", "WKD_START1..3", "WKD_END1..3",
              "SAT_RATE1..3", "SAT_START1..3", "SAT_END1..3",
              "SUN_RATE1..3", "SUN_START1..3", "SUN_END1..3")


def _attr(attributes: dict, name: str):
    """One attribute, whatever case the service used for it."""
    if not isinstance(attributes, dict):
        return None
    if name in attributes:
        return attributes[name]
    lowered = {str(k).lower(): v for k, v in attributes.items()}
    value = lowered.get(name.lower())
    if value is not None:
        return value
    return lowered.get(name.lower().replace("_", ""), None)


def _number(value) -> Optional[float]:
    """A number out of a JSON value that may be a string, or None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _minutes_value(value) -> Optional[int]:
    """A minute-of-day out of an ArcGIS value, or None.

    The city stores these as minutes past midnight in the documented layer,
    but a layer has also carried "08:00" strings; both are read, and anything
    else is None rather than a guessed midnight.
    """
    number = _number(value)
    if number is not None:
        if 0 <= number <= _DAY_MIN:
            return int(number)
        return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", str(value or "").strip())
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def _rate_bands_from_tiers(attributes: dict, prefix: str,
                           days: Tuple[int, ...]) -> List[RateBand]:
    """The three rate tiers of one day-kind (WKD/SAT/SUN) as RateBands."""
    bands: List[RateBand] = []
    for index in (1, 2, 3):
        rate = _number(_attr(attributes, f"{prefix}_RATE{index}"))
        start = _minutes_value(_attr(attributes, f"{prefix}_START{index}"))
        end = _minutes_value(_attr(attributes, f"{prefix}_END{index}"))
        if rate is None or start is None or end is None:
            continue
        if rate < 0 or start >= _DAY_MIN or end > _DAY_MIN or start >= end:
            continue
        bands.append(RateBand(days_of_week=days, start_min=start, end_min=end,
                              rate_per_hour=float(rate)))
    return bands


def _geometry_point(geometry) -> Optional[Tuple[float, float]]:
    """A representative (lat, lon) of an ArcGIS geometry, or None."""
    if not isinstance(geometry, dict):
        return None
    x, y = geometry.get("x"), geometry.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return float(y), float(x)
    points: List[Tuple[float, float]] = []
    paths = geometry.get("paths")
    if isinstance(paths, list):
        for path in paths:
            if isinstance(path, list):
                for pair in path:
                    if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                        points.append((float(pair[1]), float(pair[0])))
    rings = geometry.get("rings")
    if isinstance(rings, list):
        for ring in rings:
            if isinstance(ring, list):
                for pair in ring:
                    if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                        points.append((float(pair[1]), float(pair[0])))
    if not points:
        return None
    points = points[:400]
    return (sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points))


def _seattle_candidate(feature: dict, lat: float, lon: float) -> Optional[ParkingCandidate]:
    """One Blockface feature as a candidate, or None when it is not parking.

    A blockface the city marks "No Parking Allowed" is dropped here rather than
    offered and rejected: there is no stay to price on it, and offering it
    would only make a list longer.
    """
    attributes = feature.get("attributes") if isinstance(feature, dict) else None
    if not isinstance(attributes, dict):
        return None
    category = " ".join(str(_attr(attributes, "PARKING_CATEGORY") or "").split()).lower()
    if not category or "no parking" in category or "tow" in category:
        return None
    point = _geometry_point(feature.get("geometry"))
    if point is None:
        return None
    cand_lat, cand_lon = point
    distance = haversine_m(lat, lon, cand_lat, cand_lon)
    name = " ".join(str(_attr(attributes, "UNITDESC") or "").split()) or "a Seattle blockface"
    limit = _minutes_value(_attr(attributes, "PARKING_TIME_LIMIT"))
    if limit is not None and limit <= 0:
        limit = None
    spaces = _number(_attr(attributes, "PARKING_SPACES"))
    rpz = _attr(attributes, "RPZ_ZONE")
    rpz_zone = str(rpz).strip() if rpz not in (None, "", 0, "0") else None

    bands: List[RateBand] = []
    kind = "street_paid"
    rates_known = True
    #: The city's own enforcement window for a time limit, as minutes past
    #: midnight. The documented layer carries `START_TIME_WKD`/`END_TIME_WKD`
    #: (and their Saturday twins); when a layer does not, its rate tier's start
    #: and end are the only window it published, and failing that the ordinary
    #: enforcement day - said here rather than hidden, and never invented for a
    #: day the layer says nothing about.
    weekday_window = (_minutes_value(_attr(attributes, "START_TIME_WKD"))
                      or _minutes_value(_attr(attributes, "WKD_START1")))
    weekday_end = (_minutes_value(_attr(attributes, "END_TIME_WKD"))
                   or _minutes_value(_attr(attributes, "WKD_END1")))
    saturday_window = _minutes_value(_attr(attributes, "START_TIME_SAT"))
    saturday_end = _minutes_value(_attr(attributes, "END_TIME_SAT"))

    if "unrestricted" in category:
        kind = "street_free"
    elif "time limited" in category:
        kind = "street_limited"
        # A time-limited block is FREE and the limit is the whole story. Its
        # hours are the city's own window when it publishes one.
        #
        # THE SATURDAY READING IS THE SAFE ONE, on purpose: when the layer
        # publishes a Saturday window, that window is used; when it publishes
        # none, the limit still applies on Saturday with the weekday's hours
        # (the ordinary "2 hour parking ... except Sunday" sign) rather than
        # being called free. Being wrong in that direction refuses a stay that
        # might have been legal; being wrong the other way hands the owner a
        # ticket, and this file is never allowed to do that.
        if limit:
            bands.append(RateBand(days_of_week=(0, 1, 2, 3, 4),
                                  start_min=weekday_window or 8 * 60,
                                  end_min=weekday_end or 18 * 60,
                                  rate_per_hour=0.0, max_stay_min=limit))
            if saturday_window is not None and saturday_end is not None:
                bands.append(RateBand(days_of_week=(5,),
                                      start_min=saturday_window,
                                      end_min=saturday_end,
                                      rate_per_hour=0.0, max_stay_min=limit))
            else:
                bands.append(RateBand(days_of_week=(5,),
                                      start_min=weekday_window or 8 * 60,
                                      end_min=weekday_end or 18 * 60,
                                      rate_per_hour=0.0, max_stay_min=limit))
    elif "paid" in category or "car share" in category:
        bands.extend(_rate_bands_from_tiers(attributes, "WKD", (0, 1, 2, 3, 4)))
        bands.extend(_rate_bands_from_tiers(attributes, "SAT", (5,)))
        bands.extend(_rate_bands_from_tiers(attributes, "SUN", (6,)))
        if limit:
            # The limit rides on the PAID windows only: after they end the curb
            # is unrestricted, which is the tail-end overlap this module exists
            # to get right.
            bands = [RateBand(b.days_of_week, b.start_min, b.end_min,
                              b.rate_per_hour, limit) for b in bands]
        if not bands:
            rates_known = False
    elif rpz_zone:
        # A permit zone: parking is legal for a permit holder and not for
        # anyone else. `evaluate_parking_stay` refuses it unless the owner says
        # he holds that permit; a holder pays nothing for the curb itself.
        kind = "street_limited"
    else:
        # A category this file does not know, with no price: named as unknown
        # rather than quoted at zero.
        kind = "street_limited"
        rates_known = False

    return ParkingCandidate(
        id="sdot:" + str(_attr(attributes, "UNITDESC") or "")[:80] + f":{cand_lat:.5f},{cand_lon:.5f}",
        name=name, kind=kind, lat=cand_lat, lon=cand_lon,
        distance_m=round(distance, 1), spaces=int(spaces) if spaces else None,
        rpz_zone=rpz_zone, daily_max_usd=None, rate_bands=tuple(bands),
        source="seattle_sdot", source_url=SEATTLE_BLOCKFACE_URL,
        rates_known=rates_known)


def _envelope(lat: float, lon: float, radius_m: float) -> Tuple[float, float, float, float]:
    """(lon_min, lat_min, lon_max, lat_max) around a point, for Esri."""
    dlat = radius_m / 111320.0
    coslat = max(0.01, math.cos(math.radians(lat)))
    dlon = radius_m / (111320.0 * coslat)
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def seattle_candidates(lat: float, lon: float, radius_m: int = RADIUS_M, *,
                       transport: Optional[Callable] = None,
                       use_cache: bool = True) -> List[ParkingCandidate]:
    """Seattle's own blockfaces within `radius_m`, priced from the city's data.

    One GET, cached for a day. Returns [] - never raises - when the service
    does not answer, so a Seattle lookup still answers from OpenStreetMap.
    """
    key = _area_key("seattle_sdot", lat, lon, radius_m)
    payload = cache_get(key) if use_cache else None
    if payload is None:
        xmin, ymin, xmax, ymax = _envelope(lat, lon, radius_m)
        query = urllib.parse.urlencode({
            "where": "1=1",
            "geometry": f"{xmin:.6f},{ymin:.6f},{xmax:.6f},{ymax:.6f}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326", "outSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*", "returnGeometry": "true",
            "resultRecordCount": "300", "f": "json",
        })
        call = transport or default_transport
        try:
            status, raw = call("GET", SEATTLE_BLOCKFACE_URL + "?" + query)
        except Exception:
            return []
        got = _payload(status, raw, what="Seattle's blockface service")
        if not got.get("ok"):
            return []
        payload = got["body"]
        if use_cache:
            cache_put(key, payload)
    features = payload.get("features")
    if not isinstance(features, list):
        return []
    out: List[ParkingCandidate] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        cand = _seattle_candidate(feature, lat, lon)
        if cand is not None and cand.distance_m <= radius_m * 1.35:
            out.append(cand)
    return out


# --------------------------------------------------------------------------
#   Provider 2: OpenStreetMap through Overpass, anywhere in the world
# --------------------------------------------------------------------------

#: The one compact query: off-street lots and garages, plus mapped street
#: parking lanes, within `radius_m` of the destination. `out center` gives a
#: way a single point, so a way and a node are priced the same way.
OVERPASS_QUERY = """[out:json][timeout:8];
(
  node["amenity"="parking"]["access"!~"private|no"](around:{radius},{lat},{lon});
  way["amenity"="parking"]["access"!~"private|no"](around:{radius},{lat},{lon});
  way["highway"]["parking:both"](around:{radius},{lat},{lon});
  way["highway"]["parking:left"](around:{radius},{lat},{lon});
  way["highway"]["parking:right"](around:{radius},{lat},{lon});
);
out center tags qt;"""

#: Operators whose lots are park-and-ride lots: free unless a fee is stated.
_TRANSIT_OPERATORS = ("skagit transit", "sound transit", "wsdot", "community transit",
                      "pierce transit", "king county metro", "everett transit")


def _osm_point(element: dict) -> Optional[Tuple[float, float]]:
    """A node's or a way's (lat, lon); `out center` puts a way's in `center`."""
    if not isinstance(element, dict):
        return None
    center = element.get("center")
    if isinstance(center, dict):
        lat, lon = _number(center.get("lat")), _number(center.get("lon"))
        if lat is not None and lon is not None:
            return (lat, lon)
    lat, lon = _number(element.get("lat")), _number(element.get("lon"))
    if lat is not None and lon is not None:
        return (lat, lon)
    return None


def _osm_candidate(element: dict, lat: float, lon: float) -> Optional[ParkingCandidate]:
    """One OSM element as a candidate, or None when it is not parking to offer.

    `access=private` or `access=no` is dropped: it is not the owner's to park
    on, and offering it would be a wrong answer rather than a cheap one.
    """
    tags = element.get("tags") if isinstance(element, dict) else None
    if not isinstance(tags, dict):
        return None
    access = str(tags.get("access") or "").strip().lower()
    if access in ("private", "no", "customers", "employees"):
        return None
    point = _osm_point(element)
    if point is None:
        return None
    cand_lat, cand_lon = point
    distance = haversine_m(lat, lon, cand_lat, cand_lon)

    amenity = str(tags.get("amenity") or "").strip().lower()
    parking_lane = any(tags.get(key) for key in ("parking:both", "parking:left",
                                                "parking:right"))
    if amenity != "parking" and not parking_lane:
        return None

    name = " ".join(str(tags.get("name") or "").split())
    if not name:
        name = ("a parking lane" if parking_lane and amenity != "parking"
                else "a parking lot")
    kind = "lot"
    if amenity == "parking":
        if str(tags.get("parking") or "").lower() == "multi-storey" \
                or str(tags.get("parking") or "").lower() == "underground":
            kind = "garage"
    elif parking_lane:
        kind = "street_paid"

    charge = parse_charge(tags.get("charge"))
    fee_tag = str(tags.get("fee") or "").strip().lower()
    maxstay = parse_maxstay(tags.get("maxstay"))
    operator = str(tags.get("operator") or "").lower()
    park_ride = str(tags.get("park_ride") or "").strip().lower() in ("yes", "true", "1")
    transit = any(word in operator for word in _TRANSIT_OPERATORS)
    daily_max = charge[1] if charge else None
    hourly = charge[0] if charge else None

    modes: dict = {}
    for side in ("both", "left", "right"):
        value = str(tags.get(f"parking:{side}:fee") or "").strip().lower()
        if value in ("no", "yes"):
            modes[side] = value == "yes"
    conditional = (tags.get("fee:conditional")
                   or tags.get("parking:both:fee:conditional") or "")

    bands: List[RateBand] = []
    rates_known = True
    #: The price of a place that publishes only a DAY price (a garage that says
    #: "12.00 USD/day" and nothing else). Charged flat for any stay: that
    #: over-quotes a short stay and never under-quotes a long one, which is the
    #: only direction this file is allowed to be wrong in.
    flat_usd: Optional[float] = None
    #: A free block with a published maximum stay ("2 hour parking, no charge"):
    #: at most that long, free. Its limit is applied to the whole week when the
    #: tag gives no window at all, which can only ever REJECT a stay - the safe
    #: direction, never a cheap promise that turns into a ticket.
    free_limit = maxstay if (fee_tag == "no" or (modes and not any(modes.values()))) else None

    if fee_tag == "no" or (modes and not any(modes.values())):
        kind = "street_free" if parking_lane else kind
        if free_limit and not conditional:
            bands.append(RateBand(days_of_week=tuple(range(7)), start_min=0,
                                  end_min=_DAY_MIN, rate_per_hour=0.0,
                                  max_stay_min=free_limit))
    elif fee_tag == "yes" or hourly is not None or daily_max is not None:
        if hourly:
            # The stated rate covers every day: a lot that publishes an hourly
            # price does not also publish the hours it applies, so the price is
            # taken as always-on and the daily cap (when given) still applies.
            bands.append(RateBand(days_of_week=tuple(range(7)), start_min=0,
                                  end_min=_DAY_MIN, rate_per_hour=float(hourly),
                                  max_stay_min=maxstay))
        elif daily_max is not None:
            flat_usd = float(daily_max)
    elif park_ride or transit:
        kind = "lot"
    else:
        # There IS parking here; nobody says what it costs. Counted, never
        # priced - this is the honest case the answer names out loud.
        rates_known = False

    if conditional:
        mode, windows = parse_osm_conditional_window(conditional, hourly or 0.0)
        if windows and mode == "free":
            # Free in the named windows. The limit, when the block has one,
            # rides on the FREE windows; outside them the ordinary charge
            # applies, and its own price is what the caller already parsed.
            free_bands = [RateBand(w.days_of_week, w.start_min, w.end_min, 0.0,
                                   free_limit) for w in windows]
            if hourly:
                paid_windows = []
                for weekday in range(7):
                    covered = [(w.start_min, w.end_min) for w in windows
                               if weekday in w.days_of_week]
                    for start, end in _complement(covered):
                        paid_windows.append(RateBand((weekday,), start, end,
                                                     float(hourly), maxstay))
                bands = paid_windows + free_bands
                rates_known = True
            elif fee_tag == "yes":
                # Free after hours, and a price outside them that this file
                # cannot read: the whole place is left out rather than priced
                # at zero for a stay that would really be charged.
                bands = []
                rates_known = False
            else:
                bands = free_bands
                rates_known = True
        elif windows and mode == "paid":
            if not hourly:
                # Paid in the named windows, at a price this file cannot read:
                # left out rather than quoted at zero.
                bands = []
                rates_known = False
            else:
                bands = [RateBand(w.days_of_week, w.start_min, w.end_min,
                                  float(hourly), maxstay) for w in windows]
                rates_known = True
                kind = "street_paid" if parking_lane else kind

    if not bands and flat_usd is None and rates_known \
            and kind in ("lot", "garage") and fee_tag != "no":
        # A lot with no price at all is not a free lot. (A lot that publishes
        # only a DAY price is priced by `flat_usd` above and is not this case.)
        if not (park_ride or transit):
            rates_known = False

    spaces = _number(tags.get("capacity"))
    return ParkingCandidate(
        id="osm:" + str(element.get("type") or "n") + ":" + str(element.get("id") or ""),
        name=name[:120], kind=kind, lat=cand_lat, lon=cand_lon,
        distance_m=round(distance, 1),
        spaces=int(spaces) if spaces else None,
        rpz_zone=None, daily_max_usd=daily_max,
        rate_bands=tuple(bands), source="osm",
        source_url="https://www.openstreetmap.org/", rates_known=rates_known,
        flat_usd=flat_usd)


def osm_candidates(lat: float, lon: float, radius_m: int = RADIUS_M, *,
                   transport: Optional[Callable] = None,
                   use_cache: bool = True) -> List[ParkingCandidate]:
    """Off-street lots, garages and street lanes within `radius_m`, from OSM.

    One POST, cached for a day. Returns [] - never raises - on any failure.
    """
    key = _area_key("osm", lat, lon, radius_m)
    payload = cache_get(key) if use_cache else None
    if payload is None:
        query = OVERPASS_QUERY.format(radius=int(radius_m), lat=f"{lat:.6f}",
                                      lon=f"{lon:.6f}")
        body = urllib.parse.urlencode({"data": query}).encode("utf-8")
        call = transport or default_transport
        try:
            status, raw = call("POST", OVERPASS_URL, body=body,
                               headers={"Content-Type": "application/x-www-form-urlencoded"})
        except Exception:
            return []
        got = _payload(status, raw, what="OpenStreetMap's parking data")
        if not got.get("ok"):
            return []
        payload = got["body"]
        if use_cache:
            cache_put(key, payload)
    elements = payload.get("elements")
    if not isinstance(elements, list):
        return []
    out: List[ParkingCandidate] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        cand = _osm_candidate(element, lat, lon)
        if cand is not None and cand.distance_m <= radius_m * 1.35:
            out.append(cand)
    return out


# --------------------------------------------------------------------------
#   A place name to a point (Nominatim), the one lookup that carries words
# --------------------------------------------------------------------------

_COORDINATES = re.compile(
    r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


def looks_like_coordinates(text) -> Optional[Tuple[float, float]]:
    """"47.6094, -122.3425" (or a `geo:` URI) -> (lat, lon), else None."""
    raw = str(text or "").strip()
    raw = re.sub(r"^geo:", "", raw, flags=re.IGNORECASE)
    raw = raw.split("?", 1)[0]
    m = _COORDINATES.match(raw)
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return (lat, lon)
    return None


def geocode_place(place: str, *, transport: Optional[Callable] = None,
                  use_cache: bool = True) -> Optional[dict]:
    """"Pike Place Market" -> {"lat", "lon", "label"}, or None.

    The ONE request in this file that carries words rather than a point, and
    the words are the owner's own (what he typed or said), never a chat
    message, a calendar title or anything read out of memory. A coordinate
    pair given instead of a name makes no request at all.
    """
    name = " ".join(str(place or "").split())[:_MAX_PLACE_CHARS]
    if len(name) < _MIN_PLACE_CHARS:
        return None
    coordinates = looks_like_coordinates(name)
    if coordinates is not None:
        return {"lat": coordinates[0], "lon": coordinates[1],
                "label": f"{coordinates[0]:.4f}, {coordinates[1]:.4f}"}
    key = _place_key(name)
    payload = cache_get(key) if use_cache else None
    if payload is None:
        global _last_geocode_at
        wait = _NOMINATIM_MIN_GAP - (time.monotonic() - _last_geocode_at)
        if wait > 0:
            time.sleep(wait)
        _last_geocode_at = time.monotonic()
        query = urllib.parse.urlencode({"q": name, "format": "jsonv2", "limit": "1"})
        call = transport or default_transport
        try:
            status, raw = call("GET", NOMINATIM_URL + "?" + query)
        except Exception:
            return None
        got = _payload(status, raw, what="the map's place lookup")
        if not got.get("ok"):
            return None
        body = got["body"]
        payload = {"results": body if isinstance(body, list) else []}
        if use_cache:
            cache_put(key, payload)
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list) or not results:
        return None
    first = results[0]
    if not isinstance(first, dict):
        return None
    lat, lon = _number(first.get("lat")), _number(first.get("lon"))
    if lat is None or lon is None:
        return None
    label = " ".join(str(first.get("display_name") or name).split())
    return {"lat": lat, "lon": lon, "label": label[:160]}


# --------------------------------------------------------------------------
#   The lookup the quick path calls
# --------------------------------------------------------------------------

def _dedupe(candidates: List[ParkingCandidate], radius_m: int) -> List[ParkingCandidate]:
    """One candidate per place: two providers describing one lot is one lot."""
    seen: set = set()
    out: List[ParkingCandidate] = []
    for cand in sorted(candidates, key=lambda c: c.distance_m):
        if cand.distance_m > radius_m * 1.35:
            continue
        key = (" ".join(cand.name.lower().split())[:60],
               round(cand.lat, 4), round(cand.lon, 4))
        if key in seen:
            continue
        seen.add(key)
        out.append(cand)
    return out


def find_parking(place=None, start_dt: Optional[datetime] = None,
                 end_dt: Optional[datetime] = None, *, transport: Optional[Callable] = None,
                 radius_m: int = RADIUS_M, limit: int = LIMIT,
                 allow_rpz_permit: Optional[str] = None,
                 use_cache: bool = True, lat: Optional[float] = None,
                 lon: Optional[float] = None, label: Optional[str] = None,
                 wants_free: bool = False) -> dict:
    """Price every kind of parking near `place` for one stay, cheapest first.

    Returns a dict, never raises:
        {"ok": True, "place", "lat", "lon", "radius_m", "start", "end",
         "minutes", "results": [StayQuote], "rejected": [StayQuote],
         "unknown": <how many places publish no price>, "notes": [plain words]}

    or {"ok": False, "reason": "<one plain sentence>"}. `results` holds only
    LEGAL stays, ranked by (cost, distance); a place that would be a ticket is
    never in it. When `lat`/`lon` are given, no geocoding happens at all.
    """
    start_dt = start_dt or datetime.now()
    end_dt = end_dt or (start_dt + timedelta(hours=2))
    if end_dt <= start_dt:
        return {"ok": False, "reason": "the end time has to be after the start time"}
    minutes = int((end_dt - start_dt).total_seconds() // 60)
    notes: List[str] = []

    if lat is None or lon is None:
        if place is None or not str(place).strip():
            return {"ok": False, "reason": "I did not catch where to look"}
        found = geocode_place(place, transport=transport, use_cache=use_cache)
        if found is None:
            return {"ok": False,
                    "reason": f"I could not find {str(place).strip()} on the map, "
                              f"so I have no street to price"}
        lat, lon = found["lat"], found["lon"]
        label = label or found["label"]
    label = label or f"{lat:.4f}, {lon:.4f}"

    providers: List[str] = []
    candidates: List[ParkingCandidate] = []
    if in_seattle(lat, lon):
        seattle = seattle_candidates(lat, lon, radius_m, transport=transport,
                                     use_cache=use_cache)
        if seattle:
            providers.append("seattle_sdot")
        candidates.extend(seattle)
    osm = osm_candidates(lat, lon, radius_m, transport=transport,
                         use_cache=use_cache)
    if osm:
        providers.append("osm")
    candidates.extend(osm)
    if not candidates:
        notes.append("neither parking service had anything published within "
                     f"{int(radius_m)} m")
    candidates = _dedupe(candidates, radius_m)

    results: List[StayQuote] = []
    rejected: List[StayQuote] = []
    unknown = 0
    for cand in candidates:
        if not cand.rates_known:
            unknown += 1
            continue
        quote = evaluate_parking_stay(cand, start_dt, end_dt,
                                      allow_rpz_permit=allow_rpz_permit)
        (results if quote.legal else rejected).append(quote)

    results.sort(key=lambda q: (round(q.total_cost_usd, 2), q.candidate.distance_m))
    return {
        "ok": True, "place": label, "lat": lat, "lon": lon,
        "radius_m": int(radius_m),
        "start": start_dt.isoformat(timespec="minutes"),
        "end": end_dt.isoformat(timespec="minutes"),
        "minutes": minutes,
        "results": results[:max(1, int(limit))],
        "rejected": rejected,
        "unknown": unknown,
        "providers": providers,
        "notes": notes,
        "wants_free": bool(wants_free),
    }


# --------------------------------------------------------------------------
#   The calendar bridge: the next event that has a place
# --------------------------------------------------------------------------

def next_event_with_a_place(*, now: Optional[datetime] = None, reader=None,
                            days_ahead: int = 1) -> Optional[dict]:
    """The next upcoming calendar event with a non-empty location, or None.

    `reader` is injected for the tests; in the product it is
    `jarvis_google_calendar.list_events`, imported lazily, so a backend
    without it (or with no calendar connected) simply answers None - one plain
    sentence in the reply, never an exception in the middle of a chat turn.

    The event's TITLE is never returned to the caller and never leaves this
    function: only the times, the location line and the calendar's own name.
    """
    moment = now or datetime.now()
    if reader is None:
        def reader(days, now=None):          # noqa: F811 - the lazy default
            import jarvis_google_calendar as G
            return G.list_events(days, now=now)
    try:
        got = reader(max(1, int(days_ahead)), now=moment)
    except Exception:
        return None
    if not isinstance(got, dict) or not got.get("ok"):
        return None
    events = got.get("events")
    if not isinstance(events, list):
        return None
    for event in events:
        if not isinstance(event, dict):
            continue
        where = " ".join(str(event.get("where") or "").split())
        if not where:
            continue
        start = _parse_event_time(event.get("start"))
        end = _parse_event_time(event.get("end"))
        if start is None:
            continue
        if end is None or end <= start:
            end = start + timedelta(hours=1)
        if end <= moment:
            continue
        return {"where": where[:160], "start": start, "end": end,
                "calendar": str(event.get("calendar") or "")[:60]}
    return None


def _parse_event_time(value) -> Optional[datetime]:
    """An ISO time from a calendar row, or None. All-day dates are not times."""
    text = str(value or "").strip()
    if not text or "T" not in text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        # Parking signs are the owner's own wall clock, so an aware time is
        # brought to this PC's local time rather than compared across zones.
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def event_window(event: dict, *, pad_minutes: int = PAD_MINUTES) -> Tuple[datetime, datetime]:
    """The stay a calendar event needs: its own window, padded either side."""
    start = event["start"] - timedelta(minutes=int(pad_minutes))
    end = event["end"] + timedelta(minutes=int(pad_minutes))
    return start, end


# --------------------------------------------------------------------------
#   The words: full breakdown on the PC, short and tappable on the phone
# --------------------------------------------------------------------------

#: Words that only make sense on the PC. The phone's answer is checked against
#: this list by the suite, so a later edit cannot quietly put a desktop-only
#: phrase on the phone.
DESKTOP_ONLY = ("HUD", "hud", "desktop", "Desktop", "on this PC", "this PC",
                "Settings", "the card", "approval", "approve", "window")

#: Said with every answer, on both devices: what this is not.
NOT_KNOWING = ("That is a cost estimate from public parking data, not a booking: "
               "it cannot see a tow-away sign or a stop sign, a permit zone you "
               "do not hold, or a sign that has changed.")


def _segment_words(quote: StayQuote) -> str:
    """The minute-by-minute breakdown: "105m @ $2.00/hr + 180m free after 6:00 PM"."""
    if not quote.segments:
        return ""
    parts: List[str] = []
    for index, segment in enumerate(quote.segments):
        reached = (index + 1 == len(quote.segments)
                   and quote.free_from_min is not None
                   and segment.rate_per_hour == 0.0)
        if segment.rate_per_hour > 0:
            parts.append(f"{segment.minutes}m @ {_money(segment.rate_per_hour)}/hr")
        elif reached:
            parts.append(f"{segment.minutes}m free after {clock_words(quote.free_from_min)}")
        else:
            parts.append(f"{segment.minutes}m free")
    note = " + ".join(parts)
    if quote.total_cost_usd == 0.0 and not quote.max_stay_limit_min:
        # "FREE (285m free)" repeats itself: a stay that costs nothing needs no
        # breakdown unless a sign's limit was part of the answer.
        return ""
    if quote.max_stay_limit_min and quote.limit_ends_min is not None:
        note += (f"; {length_words(quote.max_stay_limit_min)} limit ends at "
                 f"{clock_words(quote.limit_ends_min)}")
    elif quote.max_stay_limit_min:
        note += f"; {length_words(quote.max_stay_limit_min)} limit"
    return note


def _window_words(result: dict) -> str:
    start = datetime.fromisoformat(result["start"])
    end = datetime.fromisoformat(result["end"])
    return (f"{start.strftime('%a')} {clock_words(_minute_of_day(start))} - "
            f"{clock_words(_minute_of_day(end))}, {length_words(result['minutes'])}")


def _geo_uri(quote: StayQuote) -> str:
    """The one-tap navigation link Android turns into a map button."""
    lat = f"{quote.candidate.lat:.5f}"
    lon = f"{quote.candidate.lon:.5f}"
    name = urllib.parse.quote_plus(quote.candidate.name[:60] or "Parking")
    return f"geo:{lat},{lon}?q={lat},{lon}({name})"


def _limits_line(result: dict, *, phone: bool) -> str:
    """What this answer cannot know - on BOTH devices, because it is the one
    sentence that keeps an estimate from reading like a booking.

    A provider that failed is named on the phone too (one clause, not the whole
    list): "Nothing within walking distance is legal" is a claim about the
    world, and it must never be printed when what really happened is that a
    service did not answer.
    """
    text = NOT_KNOWING
    if result.get("unknown"):
        count = int(result["unknown"])
        text += (f" {count} place{'s' if count != 1 else ''} nearby "
                 f"{'do' if count != 1 else 'does'} not publish a price, so "
                 f"{'they are' if count != 1 else 'it is'} left out rather than "
                 f"guessed.")
    notes = [str(n) for n in (result.get("notes") or []) if str(n).strip()]
    if notes:
        kept = notes[:1] if phone else notes
        joined = "; ".join(kept)
        # A note starts a sentence here, so it is capitalised rather than left
        # reading as a continuation of "That is a cost estimate...".
        text += " " + joined[:1].upper() + joined[1:] + "."
    return text


def hud_words(result: dict) -> str:
    """The full breakdown: every legal option, its minute-by-minute maths."""
    if not result.get("ok"):
        return f"I could not look up parking: {result.get('reason', 'the lookup failed')}."
    window = _window_words(result)
    lines = [f"Cheapest legal parking near {result['place']} ({window}):"]
    results = result.get("results") or []
    if not results:
        lines.append("Nothing within walking distance is legal for that whole "
                     "window at a price I can read.")
        rejected = result.get("rejected") or []
        if rejected:
            lines.append("The nearest place cannot be used: "
                         + rejected[0].rejection_reason + ".")
    else:
        for index, quote in enumerate(results, start=1):
            note = _segment_words(quote)
            lines.append(
                f"{index}. {quote.candidate.name} - {_price_label(quote, total=True)}"
                + (f" ({note})" if note else "")
                + f" - {int(round(quote.candidate.distance_m))} m walk "
                  f"(~{quote.walk_minutes} min)")
        if result.get("wants_free") and results[0].total_cost_usd > 0:
            lines.append("Nothing nearby is free for that window; this is the "
                         "cheapest legal one.")
        # Only worth a line when the BEST option is not itself free: otherwise
        # it repeats the number above it.
        if results[0].total_cost_usd > 0.0 and any(q.total_cost_usd == 0.0
                                                   for q in results):
            lines.append("Free for that window: "
                         + "; ".join(q.candidate.name for q in results
                                     if q.total_cost_usd == 0.0) + ".")
    lines.append(_limits_line(result, phone=False))
    return "\n".join(lines)


def phone_words(result: dict) -> str:
    """Two thumb-sized options and a `geo:` link each, and nothing the phone
    cannot do."""
    if not result.get("ok"):
        return f"I could not look up parking: {result.get('reason', 'the lookup failed')}."
    window = _window_words(result)
    lines = [f"Parking near {result['place']} - {window}:"]
    results = (result.get("results") or [])[:2]
    if not results:
        lines.append("Nothing within walking distance is legal for that whole "
                     "window at a price I can read.")
        rejected = result.get("rejected") or []
        if rejected:
            lines.append("The nearest place cannot be used: "
                         + rejected[0].rejection_reason + ".")
    else:
        for index, quote in enumerate(results, start=1):
            price = _price_label(quote)
            lines.append(f"{index}. {price} - {quote.candidate.name} - "
                         f"{quote.walk_minutes} min walk")
            lines.append(f"   {_geo_uri(quote)}")
        if result.get("wants_free") and results[0].total_cost_usd > 0:
            lines.append("Nothing nearby is free for that window.")
    lines.append(_limits_line(result, phone=True))
    return "\n".join(lines)


def reply(result: dict, *, client_surface: str = "hud") -> str:
    """The answer, in the words the device that asked can actually use.

    `client_surface` is "hud" for the PC's own screen (the full breakdown) and
    "phone" for a phone (two options, a `geo:` link, and not one desktop-only
    phrase). Anything else is treated as the PC: a fuller answer never breaks a
    client, a shorter one might.
    """
    if str(client_surface).strip().lower() == "phone":
        return phone_words(result)
    return hud_words(result)


# --------------------------------------------------------------------------
#   The calendar answer, which must not send the calendar anywhere
# --------------------------------------------------------------------------

def calendar_words(result: dict, event: dict, *, client_surface: str = "hud") -> str:
    """What to say when the owner asked about his next meeting's parking.

    When the event's location is already a coordinate pair, `result` holds a
    real lookup and its own answer is returned. Otherwise this quotes the venue
    back and gives the exact sentence to say - deliberately NOT sending the
    calendar's own words to a public map service.
    """
    if result is not None:
        head = (f"Your next event with a place starts at "
                f"{clock_words(_minute_of_day(event['start']))} - parking for "
                f"its window:\n")
        return head + reply(result, client_surface=client_surface)
    where = event["where"]
    start, end = event_window(event)
    when = (f"{clock_words(_minute_of_day(start))} to "
            f"{clock_words(_minute_of_day(end))}")
    phone = str(client_surface).strip().lower() == "phone"
    if phone:
        return (f"Your next event with a place is at {where}, {when}. "
                f"Say \"parking near {where}\" and I will price it - I do not "
                f"send your calendar's own words to a map service.")
    return (f"Your next event with a place is at {where}, and parking for it "
            f"would run {when} (15 minutes either side). I have not sent the "
            f"event's own words to a map service, on purpose: say \"parking "
            f"near {where}\" and I will look it up from your own words.")
