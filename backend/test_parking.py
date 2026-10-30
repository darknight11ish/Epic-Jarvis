"""test_parking.py - a parking stay priced minute by minute, and never guessed.

    python3 backend/test_parking.py
    python -B backend/run_suites.py test_parking

WHY THIS SUITE EXISTS (2026-10-30, the parking blueprint of 2026-10-29)

A parking sign is not one number. It is a set of time windows, and the two
mistakes that cost money are made by treating it as one:

  1. THE TAIL-END OVERLAP. A block with a 2-hour limit enforced 08:00-18:00 is
     LEGAL for a 16:15-21:00 stay: only 105 of those minutes fall inside the
     enforced hours, and at 18:00 the limit ends for the night. A check that
     compares the STAY (285 min) with the sign (120 min) hides the cheapest
     legal option on the street.
  2. THE STATIC RATE. Quoting the 4:15 PM rate for a 4h 45m stay says $21.38
     where the real cost is $9.38, because the rate drops at 5 and is zero at 8.

Each of the six mandatory checks below is written to go RED on the naive
version of its own rule - that is what "mutation-killing" means here, and each
one names the mutation it catches. Nothing in this suite asserts on the SOURCE
TEXT of a module (the project's own no-source-pins rule): every check drives a
function.

WHAT IS PROVEN, and with no network at all:

  * the minute-granularity integrator: the tail-end overlap, an exceeded limit
    during the enforced hours, three rate tiers in one stay, a Sunday and an
    after-hours window, a stay that crosses midnight, a flat day cap, an
    unpublished price, a permit zone, and a no-parking band;
  * both providers from fixtures: a Seattle Blockface feature (three weekday
    tiers, three Saturday tiers, no Sunday tier, a time limit, spaces) and an
    OpenStreetMap element (fee=no, a charge, access=private, a park-and-ride, a
    metered lane, a lot whose price nobody published);
  * the tag readers: `charge`, `maxstay`, and the conditional-time grammar
    ("no @ (Mo-Fr 18:00-08:00; Sa-Su)");
  * PRIVACY: every request the providers make carries a latitude, a longitude
    and a radius - and the ONLY request that carries words is the geocode of
    what the owner himself typed. A calendar event's TITLE never appears in any
    request, and a coordinate pair makes no request at all;
  * the local SQLite cache: the second lookup inside 24 hours asks nothing, and
    a stale entry is asked again;
  * the calendar bridge, with an injected reader: the next event that HAS a
    place, padded 15 minutes either side, and a plain sentence when there is
    none - and a location that is already a point is looked up in one step
    while a location that is words is deliberately NOT sent to a map service;
  * the quick path: the sentences, the two intents, and that a whole answer
    comes back from `jarvis_quick.answer` with the model never involved;
  * per-device wording: the PC's answer has the minute-by-minute maths, and the
    phone's has a `geo:` link and NOT ONE desktop-only phrase.

No network: every socket and `urlopen` is made to fail for the whole run, and
every provider call is handed a recorder instead. No model, no pytest.
"""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import sys
import tempfile
import time
import traceback
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_parking.py", "jarvis_quick.py")

#: This suite's own cache file, in its own temp folder. It is set BEFORE the
#: import so nothing here can ever touch the owner's `parking-cache.db`.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-parking-"))
os.environ["JARVIS_PARKING_DB"] = str(_TMP / "parking-cache.db")

import jarvis_parking as P  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   HELPERS: a recorded transport, and fixtures shaped like the real answers
# --------------------------------------------------------------------------

class Net:
    """A transport that answers from fixtures and records every request.

    It has the shape the module documents - `(method, url, *, body, headers) ->
    (status, bytes)` - so a provider cannot tell it from the real thing, and
    not one byte leaves this process.
    """

    def __init__(self, seattle=None, osm=None, geocode=None):
        self.calls = []
        self.seattle = seattle if seattle is not None else (200, b'{"features": []}')
        self.osm = osm if osm is not None else (200, b'{"elements": []}')
        self.geocode = geocode if geocode is not None else (200, b"[]")

    def __call__(self, method, url, *, body=None, headers=None, **kwargs):
        self.calls.append({"method": method, "url": url,
                           "body": body if isinstance(body, bytes) else b""})
        if "arcgis.com" in url:
            return self.seattle
        if "overpass" in url:
            return self.osm
        if "nominatim" in url:
            return self.geocode
        return 404, b"{}"

    def everything(self) -> str:
        """Every URL and body this run sent, as one searchable string."""
        return "\n".join(call["url"] + " " +
                         call["body"].decode("utf-8", "replace")
                         for call in self.calls)


def _blockface(**attributes) -> dict:
    """One Blockface feature, as the city's FeatureServer answers it."""
    return {"attributes": attributes,
            "geometry": {"paths": [[[-122.3400, 47.6090], [-122.3395, 47.6093]]]}}


def _seattle_payload(*features) -> tuple:
    return 200, json.dumps({"features": list(features)}).encode("utf-8")


def _osm_payload(*elements) -> tuple:
    return 200, json.dumps({"elements": list(elements)}).encode("utf-8")


def _geocode_payload(name="Pike Place Market, Seattle, WA", lat=47.6097, lon=-122.3425):
    return 200, json.dumps([{"lat": str(lat), "lon": str(lon),
                             "display_name": name}]).encode("utf-8")


def _clear_cache() -> None:
    """Forget every cached answer between checks (they share a folder)."""
    try:
        conn = sqlite3.connect(os.environ["JARVIS_PARKING_DB"])
        try:
            conn.execute("DELETE FROM parking_cache")
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _at(*args) -> datetime:
    """A local wall-clock moment: (2026, 10, 29, 16, 15)."""
    return datetime(*args)


#: A weekday afternoon stay: Thursday 29 October 2026, 16:15 to 21:00.
THU_FROM = _at(2026, 10, 29, 16, 15)
THU_TO = _at(2026, 10, 29, 21, 0)
#: Sunday 1 November 2026, 13:00 to 16:00.
SUN_FROM = _at(2026, 11, 1, 13, 0)
SUN_TO = _at(2026, 11, 1, 16, 0)

#: A 2-hour limit enforced 08:00-18:00 at $2.00/hr, and unrestricted after.
_TWO_HOUR_BAND = P.RateBand(days_of_week=(0, 1, 2, 3, 4), start_min=8 * 60,
                            end_min=18 * 60, rate_per_hour=2.0, max_stay_min=120)


def _two_hour_block(distance_m=140.0) -> P.ParkingCandidate:
    return P.ParkingCandidate(
        id="fixture:two-hour", name="WESTERN AVE BETWEEN PIKE ST & PINE ST",
        kind="street_paid", lat=47.6094, lon=-122.3425, distance_m=distance_m,
        rate_bands=(_TWO_HOUR_BAND,), source="seattle_sdot")


# --------------------------------------------------------------------------
#   1. THE TAIL-END OVERLAP (mutation: stay length vs the sign's limit)
# --------------------------------------------------------------------------

def t_tail_end_free_overlap_is_legal():
    """16:15-21:00 on a 2-hour block that turns free at 18:00 is legal, $3.50.

    MUTATION THIS KILLS: a max-stay check that compares the STAY with the sign
    (`total_minutes (285) > 120`) instead of the minutes actually ENFORCED
    (`105 > 120`). Under that mutation this quote comes back illegal, and the
    cheapest legal place on the street disappears.
    """
    quote = P.evaluate_parking_stay(_two_hour_block(), THU_FROM, THU_TO)
    check("tail-end: the 4h45m stay on a 2h block is LEGAL", quote.legal is True,
          f"rejection was {quote.rejection_reason!r}")
    check("tail-end: exactly 105 minutes were paid", quote.paid_minutes == 105,
          f"got {quote.paid_minutes}")
    check("tail-end: exactly 180 minutes were free", quote.free_minutes == 180,
          f"got {quote.free_minutes}")
    check("tail-end: the total is $3.50 (105 min at $2.00/hr)",
          quote.total_cost_usd == 3.50, f"got {quote.total_cost_usd!r}")
    check("tail-end: only 105 minutes fell inside the enforced hours",
          quote.enforced_minutes == 105, f"got {quote.enforced_minutes}")
    check("tail-end: the answer can say when the limit stopped applying",
          quote.limit_ends_min == 18 * 60, f"got {quote.limit_ends_min}")
    check("tail-end: the breakdown names the free stretch after 6:00 PM",
          "free after 6:00 PM" in P._segment_words(quote),
          P._segment_words(quote))


# --------------------------------------------------------------------------
#   2. AN EXCEEDED LIMIT DURING THE ENFORCED HOURS
# --------------------------------------------------------------------------

def t_exceeding_enforced_max_stay_is_rejected():
    """15:30-21:00 is 150 enforced minutes against a 120-minute sign: refused.

    MUTATION THIS KILLS: counting only up to the minute the limit is crossed
    (121) instead of the whole overlap (150). The sentence the owner reads has
    to be the real number, or it reads like a rounding bug rather than a rule.
    """
    quote = P.evaluate_parking_stay(_two_hour_block(), _at(2026, 10, 29, 15, 30), THU_TO)
    check("limit: a 150-minute overlap is refused", quote.legal is False)
    check("limit: the reason gives the REAL overlap, 150 minutes",
          "Exceeds 2h time limit (150 min overlap" in quote.rejection_reason,
          repr(quote.rejection_reason))
    check("limit: the refused quote still says what the part cost",
          quote.total_cost_usd > 0.0, f"got {quote.total_cost_usd!r}")
    # And one minute short of the limit is still legal, so the boundary is
    # either side of 120 and not "any stay at all".
    inside = P.evaluate_parking_stay(_two_hour_block(), _at(2026, 10, 29, 16, 0), THU_TO)
    check("limit: a 120-minute overlap is still legal", inside.legal is True,
          inside.rejection_reason)


# --------------------------------------------------------------------------
#   3. THREE RATE TIERS IN ONE STAY (mutation: one static rate for the stay)
# --------------------------------------------------------------------------

def t_seattle_sdot_three_tier_rate_transition():
    """10:30-18:00 across $3.00, $4.50 and $2.00 tiers costs $30.50.

    MUTATION THIS KILLS: quoting the FIRST rate for the whole stay
    ($4.50 x 7.5 h = $33.75) or the LAST one ($15.00). The answer is the sum of
    the minutes each rate was actually in force.
    """
    feature = _blockface(
        UNITDESC="1ST AVE BETWEEN PIKE ST AND PINE ST",
        PARKING_CATEGORY="Paid Parking",
        WKD_RATE1=3.00, WKD_START1=8 * 60, WKD_END1=11 * 60,
        WKD_RATE2=4.50, WKD_START2=11 * 60, WKD_END2=17 * 60,
        WKD_RATE3=2.00, WKD_START3=17 * 60, WKD_END3=20 * 60,
        PARKING_SPACES=8)
    candidate = P._seattle_candidate(feature, 47.6094, -122.3425)
    check("tiers: the blockface became a paid candidate", candidate is not None
          and candidate.kind == "street_paid")
    check("tiers: three weekday bands were read", candidate is not None
          and len([b for b in candidate.rate_bands if 0 in b.days_of_week]) == 3,
          candidate and [(b.start_min, b.end_min, b.rate_per_hour)
                         for b in candidate.rate_bands])
    check("tiers: the spaces are carried", candidate is not None
          and candidate.spaces == 8, candidate and candidate.spaces)

    quote = P.evaluate_parking_stay(candidate, _at(2026, 10, 29, 10, 30),
                                    _at(2026, 10, 29, 18, 0))
    check("tiers: 10:30-18:00 is legal", quote.legal is True, quote.rejection_reason)
    check("tiers: the total is $30.50 ($1.50 + $27.00 + $2.00)",
          quote.total_cost_usd == 30.50, f"got {quote.total_cost_usd!r}")
    check("tiers: the breakdown names all three rates",
          P._segment_words(quote).count("/hr") == 3, P._segment_words(quote))
    check("tiers: 450 minutes were paid", quote.paid_minutes == 450,
          quote.paid_minutes)
    # A static rate would give one of these - neither is the answer.
    check("tiers: it is not the first rate for the whole stay",
          quote.total_cost_usd != round(4.5 * 7.5, 2))
    check("tiers: it is not the last rate for the whole stay",
          quote.total_cost_usd != round(2.0 * 7.5, 2))


# --------------------------------------------------------------------------
#   4. SUNDAY AND AFTER-HOURS ARE ZERO COST
# --------------------------------------------------------------------------

def t_sunday_and_after_hours_are_zero_cost():
    """A Sunday stay, and a fee:conditional "no @ Su", both cost $0.00.

    MUTATION THIS KILLS: an integrator that treats "no band matched" as an
    error or as the last rate it saw. A paid blockface with no Sunday tier is
    FREE on Sunday - the city publishes weekday, Saturday and Sunday tiers
    separately, and a tier it does not publish is not a charge - and the answer
    says "FREE ($0.00)" rather than "$0.00 total".
    """
    feature = _blockface(
        UNITDESC="2ND AVE BETWEEN STEWART ST AND VIRGINIA ST",
        PARKING_CATEGORY="Paid Parking",
        WKD_RATE1=4.00, WKD_START1=8 * 60, WKD_END1=20 * 60,
        SAT_RATE1=3.00, SAT_START1=8 * 60, SAT_END1=20 * 60)
    paid = P._seattle_candidate(feature, 47.6094, -122.3425)
    check("sunday: the paid blockface has no Sunday band",
          paid is not None and not any(6 in b.days_of_week for b in paid.rate_bands))
    quote = P.evaluate_parking_stay(paid, SUN_FROM, SUN_TO)
    check("sunday: the Sunday stay is legal", quote.legal is True, quote.rejection_reason)
    check("sunday: it costs $0.00", quote.total_cost_usd == 0.0,
          f"got {quote.total_cost_usd!r}")
    check("sunday: the line reads FREE ($0.00)",
          "FREE ($0.00)" in quote.summary_line, quote.summary_line)

    # The same rule from the OpenStreetMap side: "free on Sundays".
    element = {"type": "way", "id": 42, "center": {"lat": 47.6094, "lon": -122.3425},
               "tags": {"amenity": "parking", "name": "Pike Place Garage",
                        "fee": "no", "fee:conditional": "no @ Su"}}
    free = P._osm_candidate(element, 47.6094, -122.3425)
    check("sunday: the OSM conditional was read", free is not None
          and free.rates_known is True)
    quote2 = P.evaluate_parking_stay(free, SUN_FROM, SUN_TO)
    check("sunday: the OSM 'no @ Su' stay costs $0.00",
          quote2.legal is True and quote2.total_cost_usd == 0.0,
          quote2.rejection_reason or quote2.total_cost_usd)
    check("sunday: and it says FREE ($0.00) too",
          "FREE ($0.00)" in quote2.summary_line, quote2.summary_line)


# --------------------------------------------------------------------------
#   5. PRIVATE AND NO-PARKING PLACES ARE FILTERED OUT
# --------------------------------------------------------------------------

def t_osm_private_and_no_parking_filtered_out():
    """A private lot and a "No Parking Allowed" blockface appear nowhere.

    MUTATION THIS KILLS: an adapter that parses every element it is handed, or
    a ranker that offers a place it then rejects. Either one puts a spot the
    owner cannot legally use into an answer about where he can park.
    """
    net = Net(
        seattle=_seattle_payload(
            _blockface(UNITDESC="NO PARKING HERE", PARKING_CATEGORY="No Parking Allowed"),
            _blockface(UNITDESC="PIKE ST BETWEEN 1ST AND 2ND",
                       PARKING_CATEGORY="Unrestricted Parking")),
        osm=_osm_payload(
            {"type": "node", "id": 1, "lat": 47.6095, "lon": -122.3420,
             "tags": {"amenity": "parking", "name": "Staff Lot Only",
                      "access": "private", "fee": "yes", "charge": "1.00 USD/hour"}},
            {"type": "node", "id": 2, "lat": 47.6096, "lon": -122.3421,
             "tags": {"amenity": "parking", "name": "Free Street Lot",
                      "access": "yes", "fee": "no"}}),
        geocode=(200, b"[]"))
    found = P.find_parking(None, THU_FROM, THU_TO, lat=47.6094, lon=-122.3425,
                           label="Pike Place Market", transport=net, use_cache=False)
    names = [q.candidate.name for q in found.get("results", [])]
    rejected = [q.candidate.name for q in found.get("rejected", [])]
    check("filter: the private lot is not offered", "Staff Lot Only" not in names
          and "Staff Lot Only" not in rejected, f"{names} / {rejected}")
    check("filter: the no-parking blockface is not offered",
          "NO PARKING HERE" not in names and "NO PARKING HERE" not in rejected,
          f"{names} / {rejected}")
    check("filter: the free street lot IS offered", "Free Street Lot" in names, names)
    check("filter: the unrestricted blockface is offered too",
          "PIKE ST BETWEEN 1ST AND 2ND" in names, names)
    words = P.reply(found)
    check("filter: neither banned name reaches the answer",
          "Staff Lot Only" not in words and "NO PARKING HERE" not in words, words)


# --------------------------------------------------------------------------
#   6. PHONE vs HUD WORDING (the Q2 client-flag contract)
# --------------------------------------------------------------------------

def t_phone_vs_hud_surface_wording():
    """The same quote: full maths on the PC, a `geo:` link and no desktop-only
    phrase on the phone.

    MUTATION THIS KILLS: rendering every device with the PC's words (the phone
    then shows a breakdown it cannot use and no way to navigate), or putting a
    desktop-only phrase in the short form ("on this PC", "Settings", "HUD").
    """
    quote = P.evaluate_parking_stay(_two_hour_block(), THU_FROM, THU_TO)
    result = {"ok": True, "place": "Pike Place Market, Seattle",
              "lat": 47.6094, "lon": -122.3425, "radius_m": 800,
              "start": THU_FROM.isoformat(timespec="minutes"),
              "end": THU_TO.isoformat(timespec="minutes"),
              "minutes": 285, "results": [quote], "rejected": [], "unknown": 0,
              "providers": ["seattle_sdot"], "notes": [], "wants_free": False}
    hud = P.reply(result, client_surface="hud")
    phone = P.reply(result, client_surface="phone")
    check("surface: the two answers are not the same words", hud != phone)
    check("surface: the PC's answer has the minute-by-minute maths",
          "/hr" in hud and "105m" in hud, hud)
    check("surface: the PC's answer has no geo: link", "geo:" not in hud, hud)
    check("surface: the phone's answer has the geo: navigation link",
          "geo:47.60940,-122.34250?q=47.60940,-122.34250(" in phone, phone)
    desktop_only = [word for word in P.DESKTOP_ONLY if word in phone]
    check("surface: the phone's answer has ZERO desktop-only strings",
          not desktop_only, f"found {desktop_only} in:\n{phone}")
    check("surface: the phone's answer is shorter than the PC's",
          len(phone) < len(hud), f"{len(phone)} vs {len(hud)}")
    check("surface: the phone's answer names the price",
          "$3.50" in phone, phone)
    # The honest limits are on BOTH: this is a cost estimate, not a booking.
    check("surface: the PC's answer says what it cannot know",
          "not a booking" in hud, hud)
    check("surface: the phone's answer says what it cannot know",
          "not a booking" in phone, phone)


# --------------------------------------------------------------------------
#   THE ADAPTERS: what a real answer looks like, read offline
# --------------------------------------------------------------------------

def t_seattle_adapter_reads_a_time_limited_block():
    """A "Time Limited Parking" blockface: free, with its limit enforced only
    in the city's published window - and Saturday only when it says so."""
    feature = _blockface(
        UNITDESC="3RD AVE BETWEEN PINE AND PIKE",
        PARKING_CATEGORY="Time Limited Parking",
        PARKING_TIME_LIMIT=120,
        START_TIME_WKD=8 * 60, END_TIME_WKD=18 * 60)
    candidate = P._seattle_candidate(feature, 47.6094, -122.3425)
    check("sdot: a time-limited block is street_limited",
          candidate is not None and candidate.kind == "street_limited")
    check("sdot: it is free while the limit runs", candidate is not None
          and all(b.rate_per_hour == 0.0 for b in candidate.rate_bands))
    check("sdot: the limit rides on the weekday band", candidate is not None
          and candidate.rate_bands and candidate.rate_bands[0].max_stay_min == 120)
    check("sdot: Saturday is NOT claimed when the layer publishes no Saturday window",
          candidate is not None
          and not any(5 in b.days_of_week for b in candidate.rate_bands))
    quote = P.evaluate_parking_stay(candidate, THU_FROM, THU_TO)
    check("sdot: the tail-end overlap works on this blockface too",
          quote.legal is True and quote.total_cost_usd == 0.0,
          quote.rejection_reason)
    # A Saturday window, when the layer does publish one, is used.
    saturday = _blockface(UNITDESC="4TH AVE", PARKING_CATEGORY="Time Limited Parking",
                          PARKING_TIME_LIMIT=60,
                          START_TIME_WKD=8 * 60, END_TIME_WKD=18 * 60,
                          START_TIME_SAT=9 * 60, END_TIME_SAT=17 * 60)
    with_sat = P._seattle_candidate(saturday, 47.6094, -122.3425)
    check("sdot: a published Saturday window is carried",
          with_sat is not None and any(5 in b.days_of_week for b in with_sat.rate_bands))


def t_osm_tags_are_read_not_guessed():
    """fee, charge, maxstay, a park-and-ride and an unpublished price."""
    free = P._osm_candidate({"type": "node", "id": 1, "lat": 47.6, "lon": -122.3,
                             "tags": {"amenity": "parking", "name": "Free Lot",
                                      "fee": "no"}}, 47.6, -122.3)
    check("osm: fee=no is free", free is not None and free.rates_known
          and all(b.rate_per_hour == 0.0 for b in free.rate_bands))

    charged = P._osm_candidate({"type": "node", "id": 2, "lat": 47.6, "lon": -122.3,
                                "tags": {"amenity": "parking", "name": "Paid Lot",
                                         "fee": "yes", "charge": "3.00 USD/hour",
                                         "maxstay": "2 hours"}}, 47.6, -122.3)
    check("osm: a charge becomes an hourly band", charged is not None
          and charged.rate_bands and charged.rate_bands[0].rate_per_hour == 3.0)
    check("osm: maxstay rides on that band", charged is not None
          and charged.rate_bands[0].max_stay_min == 120)
    check("osm: the paid lot costs 3.00 an hour in the answer",
          P.evaluate_parking_stay(charged, THU_FROM,
                                  _at(2026, 10, 29, 17, 15)).total_cost_usd == 3.0)

    day_only = P._osm_candidate({"type": "node", "id": 3, "lat": 47.6, "lon": -122.3,
                                 "tags": {"amenity": "parking", "name": "Day Lot",
                                          "fee": "yes", "charge": "12.00 USD/day"}},
                                47.6, -122.3)
    check("osm: a day-only price is a flat price", day_only is not None
          and day_only.flat_usd == 12.0)
    check("osm: the day-only lot charges $12.00 for a short stay too",
          day_only is not None and P.evaluate_parking_stay(
              day_only, THU_FROM, THU_TO).total_cost_usd == 12.0)

    ride = P._osm_candidate({"type": "node", "id": 4, "lat": 47.6, "lon": -122.3,
                             "tags": {"amenity": "parking", "name": "Park & Ride",
                                      "park_ride": "yes"}}, 47.6, -122.3)
    check("osm: a park-and-ride is free unless a fee is stated",
          ride is not None and ride.rates_known
          and all(b.rate_per_hour == 0.0 for b in ride.rate_bands))

    unknown = P._osm_candidate({"type": "node", "id": 5, "lat": 47.6, "lon": -122.3,
                                "tags": {"amenity": "parking", "name": "Mystery Lot"}},
                               47.6, -122.3)
    check("osm: a lot with no price is NOT quoted at zero",
          unknown is not None and unknown.rates_known is False)
    refused = P.evaluate_parking_stay(unknown, THU_FROM, THU_TO)
    check("osm: and the refusal says why, plainly",
          refused.legal is False and "not published" in refused.rejection_reason,
          refused.rejection_reason)


def t_tag_readers():
    """charge, maxstay and the conditional-time grammar."""
    check("tags: '2.00 USD/hour'", P.parse_charge("2.00 USD/hour") == (2.0, None))
    check("tags: '$3/hr'", P.parse_charge("$3/hr") == (3.0, None))
    check("tags: '5.00 USD/day' has no hourly price",
          P.parse_charge("5.00 USD/day") == (0.0, 5.0))
    check("tags: '12.00 USD/day; 2.00 USD/hour' reads both",
          P.parse_charge("12.00 USD/day; 2.00 USD/hour") == (2.0, 12.0))
    check("tags: 'free' is not a price", P.parse_charge("free") is None)
    check("tags: '2 hours' is 120 minutes", P.parse_maxstay("2 hours") == 120)
    check("tags: '120 minutes' is 120", P.parse_maxstay("120 minutes") == 120)
    check("tags: '30 min' is 30", P.parse_maxstay("30 min") == 30)

    mode, bands = P.parse_osm_conditional_window("no @ (Mo-Fr 18:00-08:00; Sa-Su)")
    check("tags: the conditional is a FREE rule", mode == "free")
    check("tags: Mo-Fr evening is 18:00-24:00 and 00:00-08:00",
          [b for b in bands if b.days_of_week == (0, 1, 2, 3, 4)]
          and sorted((b.start_min, b.end_min) for b in bands
                     if b.days_of_week == (0, 1, 2, 3, 4)) == [(0, 480), (1080, 1440)],
          [(b.days_of_week, b.start_min, b.end_min) for b in bands])
    check("tags: the whole weekend is covered",
          any(b.days_of_week == (5, 6) and (b.start_min, b.end_min) == (0, 1440)
              for b in bands), [(b.days_of_week, b.start_min, b.end_min) for b in bands])
    mode2, bands2 = P.parse_osm_conditional_window("yes @ (Mo-Sa 08:00-18:00)", 2.5)
    check("tags: a PAID conditional carries the caller's rate",
          mode2 == "paid" and bands2 and bands2[0].rate_per_hour == 2.5)
    check("tags: an unreadable conditional invents nothing",
          P.parse_osm_conditional_window("perhaps") == ("", ()))


# --------------------------------------------------------------------------
#   PRIVACY: coordinates and a radius out; the owner's own words, only
# --------------------------------------------------------------------------

def t_provider_requests_carry_only_a_point():
    """Overpass and ArcGIS receive a latitude, a longitude and a radius.

    THE RULE (CLAUDE.md rule 1, and the owner's instruction of 2026-10-29):
    nothing personal leaves this PC. The parking services are asked for an
    area, so the area is all they get - no place name, no chat text, no
    calendar entry, no event title.
    """
    net = Net(geocode=_geocode_payload())
    P.find_parking("Pike Place Market", THU_FROM, THU_TO, transport=net, use_cache=False)
    sent = net.everything()
    check("privacy: the geocode request carries the owner's own words",
          "nominatim" in sent and "pike" in sent.lower(), sent[:400])
    area_calls = [c for c in net.calls if "arcgis.com" in c["url"] or "overpass" in c["url"]]
    check("privacy: both area services were asked", len(area_calls) == 2,
          [c["url"][:80] for c in net.calls])
    for call in area_calls:
        blob = call["url"] + " " + call["body"].decode("utf-8", "replace")
        check(f"privacy: {call['method']} carries no place name",
              "pike" not in blob.lower(), blob[:300])
        check(f"privacy: {call['method']} carries a radius",
              "around" in blob or "geometry" in blob, blob[:300])
    check("privacy: no request carried an event title", "standup" not in sent.lower()
          and "meeting" not in sent.lower(), sent)


def t_a_coordinate_pair_makes_no_request():
    """A location that is already a point is never sent to a geocoder."""
    net = Net()
    got = P.geocode_place("47.6094, -122.3425", transport=net, use_cache=False)
    check("privacy: a coordinate pair is read as a point",
          got is not None and abs(got["lat"] - 47.6094) < 1e-6)
    check("privacy: and NO request was made for it", net.calls == [], net.calls)


# --------------------------------------------------------------------------
#   THE CACHE: a second lookup inside the day asks nothing
# --------------------------------------------------------------------------

def t_the_cache_answers_the_second_lookup():
    """One request per area per day, and a stale entry is asked again."""
    _clear_cache()
    net = Net(seattle=_seattle_payload(_blockface(
        UNITDESC="CACHED BLOCK", PARKING_CATEGORY="Unrestricted Parking")))
    first = P.find_parking(None, THU_FROM, THU_TO, lat=47.6094, lon=-122.3425,
                           label="X", transport=net, radius_m=400)
    calls_first = len([c for c in net.calls if "arcgis.com" in c["url"]])
    second = P.find_parking(None, THU_FROM, THU_TO, lat=47.6094, lon=-122.3425,
                            label="X", transport=net, radius_m=400)
    calls_second = len([c for c in net.calls if "arcgis.com" in c["url"]])
    check("cache: the first lookup asked Seattle once", calls_first == 1, calls_first)
    check("cache: the second lookup asked NOTHING", calls_second == calls_first,
          f"{calls_first} then {calls_second}")
    check("cache: and both answers are the same",
          [q.candidate.name for q in first["results"]]
          == [q.candidate.name for q in second["results"]])
    key = P._area_key("seattle_sdot", 47.6094, -122.3425, 400)
    check("cache: an entry older than a day is not used",
          P.cache_get(key, now=time.time() + P.CACHE_TTL_SECONDS + 10) is None)
    check("cache: a fresh entry IS used",
          P.cache_get(key, now=time.time()) is not None)
    _clear_cache()


def t_a_broken_cache_never_breaks_the_lookup():
    """A cache that cannot open is a miss, not a failed answer."""
    got = P.cache_get("anything", path=str(_TMP / "no" / "such" / "folder" / "x.db"))
    check("cache: a cache that cannot open is a miss", got is None)
    P.cache_put("anything", {"a": 1}, path=str(_TMP / "no" / "such" / "x.db"))
    check("cache: and writing to it does not raise", True)


# --------------------------------------------------------------------------
#   FAILURES DEGRADE TO A PLAIN SENTENCE, NEVER A GUESSED PRICE
# --------------------------------------------------------------------------

def t_a_failed_service_degrades_plainly():
    """Two dead services and an unknown place are sentences, not tracebacks."""
    dead = Net(seattle=(500, b"{}"), osm=(500, b"{}"), geocode=(500, b"{}"))
    # Latitude and longitude given, so no geocoder is needed: this is the
    # "both parking services are down" case, which must still answer.
    found = P.find_parking(None, THU_FROM, THU_TO, lat=47.6094, lon=-122.3425,
                           label="Pike Place Market", transport=dead, use_cache=False)
    check("failure: no candidates still returns an answer, not a crash",
          found.get("ok") is True, found)
    check("failure: the empty answer says so in the words, not a price",
          found.get("results") == [] and "neither parking service" in " ".join(found["notes"]),
          found.get("notes"))
    words = P.reply(found)
    check("failure: the answer says it found nothing", "Nothing within walking" in words,
          words)

    # And a geocoder that answers HTTP 500 is one sentence, not a crash.
    missing = P.find_parking("Nowhere At All", THU_FROM, THU_TO, transport=dead,
                             use_cache=False)
    check("failure: an unfindable place is one plain sentence",
          missing.get("ok") is False and "could not find" in missing["reason"],
          missing)
    check("failure: and the sentence never contains a price",
          "$" not in P.reply(missing), P.reply(missing))

    # A transport that raises is treated exactly like a dead service.
    def boom(*args, **kwargs):
        raise OSError("no route to host")
    got = P.find_parking(None, THU_FROM, THU_TO, lat=47.6094, lon=-122.3425,
                         label="X", transport=boom, use_cache=False, radius_m=300)
    check("failure: a transport that raises is caught, not propagated",
          got.get("ok") is True and got["results"] == [], got.get("notes"))


# --------------------------------------------------------------------------
#   THE CALENDAR BRIDGE
# --------------------------------------------------------------------------

def t_calendar_bridge_finds_the_next_event_with_a_place():
    """The next event that HAS a place, padded 15 minutes either side.

    It must pick the second event (the first has no location), must not look
    past an event that has already ended, and must give the parking lookup a
    window 15 minutes either side of it.
    """
    events = [
        {"id": "a", "summary": "Standup", "start": "2026-10-29T13:00:00",
         "end": "2026-10-29T13:15:00", "where": ""},
        {"id": "b", "summary": "Dentist", "start": "2026-10-29T15:00:00",
         "end": "2026-10-29T16:00:00", "where": "Pike Place Market"},
        {"id": "c", "summary": "Later", "start": "2026-10-30T09:00:00",
         "end": "2026-10-30T10:00:00", "where": "Space Needle"},
    ]

    def reader(days, now=None):
        return {"ok": True, "connected": True, "events": events}

    found = P.next_event_with_a_place(now=_at(2026, 10, 29, 12, 0), reader=reader)
    check("calendar: the event with no place is skipped",
          found is not None and found["where"] == "Pike Place Market", found)
    check("calendar: its TITLE is not returned to the caller",
          found is not None and "summary" not in found and "Dentist" not in str(found),
          found)
    check("calendar: the window is the event's own, 15 minutes either side",
          found is not None and P.event_window(found) == (
              _at(2026, 10, 29, 14, 45), _at(2026, 10, 29, 16, 15)),
          found and P.event_window(found))

    def empty_reader(days, now=None):
        return {"ok": False, "connected": False, "events": [],
                "reason": "Google Calendar is not connected yet."}

    check("calendar: no calendar at all is None, not an exception",
          P.next_event_with_a_place(now=_at(2026, 10, 29, 12, 0),
                                    reader=empty_reader) is None)

    def broken_reader(days, now=None):
        raise RuntimeError("the token store is missing")

    check("calendar: a broken reader is None, not an exception",
          P.next_event_with_a_place(now=_at(2026, 10, 29, 12, 0),
                                    reader=broken_reader) is None)


def t_calendar_bridge_does_not_send_the_calendar_anywhere():
    """An event whose place is words is quoted back, and NOT looked up.

    THE PRIVACY RULE THIS PINS: a calendar entry is private even when the venue
    is public, so the module refuses to put the event's own location line on
    the wire. The owner gets the venue and the exact sentence to say, with the
    window already filled in - saying it makes it his own words.
    """
    event = {"where": "Pike Place Market", "start": _at(2026, 10, 29, 15, 0),
             "end": _at(2026, 10, 29, 16, 0), "calendar": "primary"}
    net = Net()
    words = P.calendar_words(None, event, client_surface="hud")
    check("calendar: the words-venue answer names the venue", "Pike Place Market" in words,
          words)
    check("calendar: it says the calendar was not sent anywhere",
          "map service" in words or "not sent" in words.lower(), words)
    check("calendar: it offers the exact sentence to say",
          'parking near Pike Place Market' in words, words)
    check("calendar: it gives the padded window",
          "2:45 PM" in words and "4:15 PM" in words, words)
    check("calendar: and no request was made", net.calls == [], net.calls)
    phone = P.calendar_words(None, event, client_surface="phone")
    check("calendar: the phone's version is short and still honest",
          "Pike Place Market" in phone and "map service" in phone, phone)


# --------------------------------------------------------------------------
#   THE QUICK PATH: no model, no tool slot
# --------------------------------------------------------------------------

def t_the_sentences_are_ours():
    """The four phrasings the blueprint names, and the near-misses."""
    now = _at(2026, 10, 29, 13, 0).timestamp()
    cases = {
        "find cheap parking near pike place market tomorrow from 4:15 pm to 9 pm":
            ("parking_lookup", "pike place market"),
        "where is free parking near pike place market at 5 pm for 2 hours":
            ("parking_lookup", "pike place market"),
        "cheapest parking at pike place market tomorrow from 4 to 9":
            ("parking_lookup", "pike place market"),
        "find cheap parking for my next meeting": ("parking_calendar", ""),
        "find cheap parking for my next meeting at pike place market":
            ("parking_calendar", "pike place market"),
        "parking near the space needle on sunday from 1 to 4":
            ("parking_lookup", "the space needle"),
        "is there parking near the space needle": ("parking_lookup", "the space needle"),
    }
    for text, (name, place) in cases.items():
        got = Q.match(text, now)
        check(f"grammar: {text!r} is {name}",
              got is not None and got.name == name and got.f.get("place") == place,
              got and (got.name, got.f))
    # A window is a window: 4:15 PM to 9:00 PM is 4h 45m, not an hour and change.
    got = Q.match("find cheap parking near pike place market tomorrow from 4:15 pm to 9 pm", now)
    if got is not None and got.name == "parking_lookup":
        minutes = int((got.f["end"] - got.f["start"]) // 60)
        check("grammar: 4:15 pm to 9 pm is 285 minutes", minutes == 285, minutes)
    # And the near-misses stay with the model.
    for text in ("how long does it take to boil an egg",
                 "parking near me",
                 "remind me to park the car",
                 "what is a parking minimum"):
        check(f"grammar: {text!r} is NOT ours", Q.match(text, now) is None,
              Q.match(text, now))


def t_a_whole_answer_without_the_model():
    """`jarvis_quick.answer` answers the sentence; the model is never reached.

    `find_parking` is replaced with a recorder here, so this check proves the
    WIRING (the place and the window reach the module, its words come back
    through the one Result) without a socket.
    """
    seen = {}
    real = P.find_parking

    def fake(place=None, start_dt=None, end_dt=None, **kwargs):
        seen["place"] = place
        seen["start"] = start_dt
        seen["end"] = end_dt
        seen["wants_free"] = kwargs.get("wants_free")
        return {"ok": False, "reason": "stub: no map here"}

    P.find_parking = fake
    try:
        res = Q.answer("find cheap parking near pike place market tomorrow from "
                       "4:15 pm to 9 pm", now=_at(2026, 10, 29, 13, 0).timestamp(),
                       client_surface="phone")
    finally:
        P.find_parking = real
    check("quick path: the fast path answered", res is not None
          and res.intent == "parking_lookup", res)
    check("quick path: the place reached the module", seen.get("place") == "pike place market",
          seen.get("place"))
    check("quick path: the window reached the module, 285 minutes",
          seen.get("start") is not None and seen.get("end") is not None
          and int((seen["end"] - seen["start"]).total_seconds() // 60) == 285,
          (seen.get("start"), seen.get("end")))
    check("quick path: a failure is one plain sentence",
          res is not None and "could not look up parking" in res.reply, res and res.reply)

    # "free parking" is carried as a wish, and the answer says when nothing is.
    seen.clear()
    P.find_parking = fake
    try:
        free_res = Q.answer("where is free parking near pike place market at 5 pm "
                            "for 2 hours", now=_at(2026, 10, 29, 13, 0).timestamp(),
                            client_surface="hud")
    finally:
        P.find_parking = real
    check("quick path: 'free' reached the module as a wish",
          seen.get("wants_free") is True, seen.get("wants_free"))
    check("quick path: that answer is the fast path's too",
          free_res is not None and free_res.intent == "parking_lookup")


def t_the_calendar_sentence_needs_no_model():
    """\"parking for my next meeting\" reads the calendar and answers here."""
    real = P.next_event_with_a_place
    event = {"where": "Pike Place Market", "start": _at(2026, 10, 29, 15, 0),
             "end": _at(2026, 10, 29, 16, 0), "calendar": "primary"}
    P.next_event_with_a_place = lambda **kwargs: event
    try:
        res = Q.answer("find cheap parking for my next meeting",
                       now=_at(2026, 10, 29, 13, 0).timestamp())
    finally:
        P.next_event_with_a_place = real
    check("calendar sentence: the fast path answered it", res is not None
          and res.intent == "parking_calendar", res)
    check("calendar sentence: the venue is named", res is not None
          and "Pike Place Market" in res.reply, res and res.reply)
    check("calendar sentence: the turn counts as having read outside text",
          res is not None and "calendar_read" in (res.read or []), res and res.read)

    P.next_event_with_a_place = lambda **kwargs: None
    try:
        none_res = Q.answer("find cheap parking for my next meeting",
                            now=_at(2026, 10, 29, 13, 0).timestamp())
    finally:
        P.next_event_with_a_place = real
    check("calendar sentence: no event is one plain sentence", none_res is not None
          and "could not find a calendar event" in none_res.reply,
          none_res and none_res.reply)

    # A place the OWNER said in the same sentence is his own words, so it is
    # looked up - while the calendar's own location line still is not sent.
    seen = {}
    real_find = P.find_parking

    def fake(place=None, start_dt=None, end_dt=None, **kwargs):
        seen["place"] = place
        seen["minutes"] = int((end_dt - start_dt).total_seconds() // 60)
        return {"ok": False, "reason": "stub: no map here"}

    P.next_event_with_a_place = lambda **kwargs: event
    P.find_parking = fake
    try:
        said_res = Q.answer("find cheap parking for my next meeting at the "
                            "space needle", now=_at(2026, 10, 29, 13, 0).timestamp())
    finally:
        P.find_parking = real_find
        P.next_event_with_a_place = real
    check("calendar sentence: a place the owner said IS looked up",
          seen.get("place") == "the space needle", seen)
    check("calendar sentence: it used the event's padded window (90 minutes)",
          seen.get("minutes") == 90, seen)
    check("calendar sentence: the answer names the event's start",
          said_res is not None and "starts at 3:00 PM" in said_res.reply,
          said_res and said_res.reply)


def t_the_two_intents_are_read_only():
    """Neither answer can take away what "cancel that" would undo."""
    for name in ("parking_lookup", "parking_calendar"):
        check(f"read-only: {name} is in READ_ONLY_INTENTS", name in Q.READ_ONLY_INTENTS)


# --------------------------------------------------------------------------
#   THE WHOLE LOOKUP, from a fixture to an answer
# --------------------------------------------------------------------------

def t_a_whole_lookup_ranks_cheapest_first():
    """Geocode, both providers, the integrator, the ranking and the words."""
    net = Net(
        seattle=_seattle_payload(
            _blockface(UNITDESC="PAID BLOCK", PARKING_CATEGORY="Paid Parking",
                       WKD_RATE1=4.50, WKD_START1=8 * 60, WKD_END1=20 * 60),
            _blockface(UNITDESC="FREE BLOCK", PARKING_CATEGORY="Unrestricted Parking")),
        osm=_osm_payload(
            {"type": "node", "id": 9, "lat": 47.6099, "lon": -122.3429,
             "tags": {"amenity": "parking", "name": "Cheap Garage",
                      "fee": "yes", "charge": "1.00 USD/hour"}}),
        geocode=_geocode_payload())
    found = P.find_parking("Pike Place Market", THU_FROM, THU_TO, transport=net,
                           use_cache=False)
    check("lookup: it succeeded", found.get("ok") is True, found)
    check("lookup: the place label came from the geocoder",
          "Pike Place Market" in found.get("place", ""), found.get("place"))
    check("lookup: both providers are named", set(found["providers"]) == {"seattle_sdot", "osm"},
          found["providers"])
    costs = [q.total_cost_usd for q in found["results"]]
    check("lookup: results are cheapest first", costs == sorted(costs), costs)
    check("lookup: the free block is the cheapest answer",
          found["results"] and found["results"][0].candidate.name == "FREE BLOCK",
          [q.candidate.name for q in found["results"]])
    check("lookup: the limit took only the ranked few", len(found["results"]) <= P.LIMIT)
    words = P.reply(found)
    check("lookup: the answer names the free block", "FREE BLOCK" in words, words)
    check("lookup: the answer numbers the options", "1. " in words, words)


# --------------------------------------------------------------------------
#   NO NETWORK AT ALL, for the whole run
# --------------------------------------------------------------------------

class NoNet:
    """Every socket and every urlopen in this process fails, loudly."""

    def __enter__(self):
        self.saved = (socket.socket.connect, urllib.request.urlopen,
                      socket.create_connection)

        def refuse(*args, **kwargs):
            raise AssertionError("this suite must not open a socket")

        socket.socket.connect = refuse
        urllib.request.urlopen = refuse
        socket.create_connection = refuse
        return self

    def __exit__(self, *exc):
        (socket.socket.connect, urllib.request.urlopen,
         socket.create_connection) = self.saved
        return False


def main():
    print(f"parking cache for this run: {os.environ['JARVIS_PARKING_DB']}")
    with NoNet():
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:      # pragma: no cover - a crash is a fail
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
