"""jarvis_price_radar.py: the flight price radar (F1) - READ-ONLY, OFF, NO NETWORK.

    python3 test_price_radar.py   (the runner: python -B backend/run_suites.py test_price_radar.py)

WHAT THIS PROVES, IN PLAIN WORDS. F1 is the flight engine and the price
history store for the anti-surveillance price radar the owner approved on
2026-10-21. It builds Google Flights' `tfs` query parameter in pure Python,
reads the public search page's inline payload, keeps a SQLite price history
with a last-known-good snapshot and stale-on-failure semantics, and does
nothing else: the feature switch is OFF by default, there is no live network
in this suite, and there is NO checkout/booking path anywhere.

WHAT IS CHECKED HERE:

  1. **Byte parity with the reference implementations.** The recorded `tfs`
     golden values from `punitarani/fli` (the MIT Python reference, as pinned
     in its TypeScript port's test file) are copied below and every one this
     module can build must match BYTE FOR BYTE. A malformed token is quietly
     answered as a different query by Google, so this is the strongest check
     the engine has.
  2. **The tolerant parser**: price in whole integer cents, lowest price,
     airline, stops, duration, optional price level; missing/unusable prices
     are `unavailable` (never 0, never invented); malformed rows are skipped,
     a malformed page never raises.
  3. **The store**: versioned idempotent schema, last-known-good, failed fetch
     = stale with NO price, the outside-text diff (drops/material changes,
     target, low price), and the gate taint latch on a real change.
  4. **The hard invariants**: switch off = zero network; strict SSRF allowlist
     (only the one https Google page URL; redirects refused); no
     cookies/authorization headers; 403/429 = blocked_by_site_challenge, one
     attempt only; poll floor >= 300 s with seeded +/-30% jitter; no
     POST/PUT/checkout/booking surface at all; the disclosure words the owner
     approved are the ones in the module constants.
  5. **F2/F3 integration points**: set_sources/register_alert_renderer and the
     explicit PriceStore; the core imports nothing from the sources module.

ALL FIXTURES ARE SYNTHETIC OR RECORDED - no request is made by this suite.
The endpoint is UNOFFICIAL (a public search page) and may break; that is said
on every card and must not be claimed otherwise.
"""
import json
import logging
import os
import sqlite3
import sys
import tempfile
import traceback
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_price_radar.py", "jarvis_sqlite.py", "jarvis_local_http.py")
import jarvis_price_radar as R  # noqa: E402

FAILED, PASSED = [], []
TMP = Path(tempfile.mkdtemp(prefix=".jarvis-price-radar-tests-"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    print(f"skip  {why}")


# ==========================================================================
#   1. tfs byte parity with punitarani/fli (MIT)
# ==========================================================================

#: The golden values recorded in `fli-js/tests/search/tfs.test.ts`, generated
#: by the Python reference implementation (`fli/search/_proto.py` +
#: `_tfs.py`, pinned from main commit 881aee5, read 2026-10-21). The travel
#: dates are 2030 on purpose: the token depends only on the dates in the
#: filters, never on "today", so these never go stale.
TFS_GOLDENS = {
    "alliance_exclude_oneworld":
        "CBwQAhooEgoyMDMwLTA5LTE1OghPTkVXT1JMRGoHCAESA0pGS3IHCAESA0xBWEABSAFwAZgBAg",
    "alliance_exclude_skyteam":
        "CBwQAhonEgoyMDMwLTA5LTE1OgdTS1lURUFNagcIARIDSkZLcgcIARIDTEFYQAFIAXABmAEC",
    "alliance_exclude_star_alliance":
        "CBwQAhotEgoyMDMwLTA5LTE1Og1TVEFSX0FMTElBTkNFagcIARIDSkZLcgcIARIDTEFYQAFIAXABmAEC",
    "alliance_include_oneworld":
        "CBwQAhooEgoyMDMwLTA5LTE1MghPTkVXT1JMRGoHCAESA0pGS3IHCAESA0xBWEABSAFwAZgBAg",
    "alliance_include_skyteam":
        "CBwQAhonEgoyMDMwLTA5LTE1MgdTS1lURUFNagcIARIDSkZLcgcIARIDTEFYQAFIAXABmAEC",
    "alliance_include_star_alliance":
        "CBwQAhotEgoyMDMwLTA5LTE1Mg1TVEFSX0FMTElBTkNFagcIARIDSkZLcgcIARIDTEFYQAFIAXABmAEC",
    "alliance_include_two_exclude_one":
        "CBwQAhpAEgoyMDMwLTA5LTE1MghPTkVXT1JMRDINU1RBUl9BTExJQU5DRToHU0tZVEVBTWoHCAESA0pGS3IHCAESA0xBWEABSAFwAZgBAg",
    "cabin_business": "CBwQAhoeEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYQAFIA3ABmAEC",
    "cabin_economy": "CBwQAhoeEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYQAFIAXABmAEC",
    "cabin_first": "CBwQAhoeEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYQAFIBHABmAEC",
    "cabin_premium_economy": "CBwQAhoeEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYQAFIAnABmAEC",
    "kitchen_sink_round_trip":
        "CBwQAhpIEgoyMDMwLTA5LTE1KAEyCE9ORVdPUkxEagcIARIDSkZLagcIARIDRVdScgcIARIDTEhScgcIARIDTEdXegNEVUKIATyQAfABGkgSCjIwMzAtMDktMTkoATIIT05FV09STERqBwgBEgNMSFJqBwgBEgNMR1dyBwgBEgNKRktyBwgBEgNFV1J6A0RVQogBPJAB8AFAAUABQAJAA0gDcAGYAQE",
    "layover_airport_and_min":
        "CBwQAhomEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYegNPUkSIAXhAAUgBcAGYAQI",
    "layover_full":
        "CBwQAhovEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYegNPUkR6A0RGV4gBWpAB2ARAAUgBcAGYAQI",
    "layover_max_only":
        "CBwQAhoiEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYkAGsAkABSAFwAZgBAg",
    "multi_airport":
        "CBwQAho5EgoyMDMwLTEwLTE1agcIARIDQk9NagcIARIDREVMagcIARIDQU1EcgcIARIDT1JEcgcIARIDRFRXQAFIAXABmAEC",
    "one_way_jfk_lax": "CBwQAhoeEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYQAFIAXABmAEC",
    "pax_adult_child":
        "CBwQAhoeEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYQAFAAkgBcAGYAQI",
    "pax_adult_lap_infant":
        "CBwQAhoeEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYQAFAA0gBcAGYAQI",
    "pax_adult_seat_infant":
        "CBwQAhoeEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYQAFABEgBcAGYAQI",
    "pax_family_mix":
        "CBwQAhoeEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYQAFAAUACQANABEgBcAGYAQI",
    "pax_full_house":
        "CBwQAhoeEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYQAFAAUABQAFAAkACQANABEAESAFwAZgBAg",
    "pax_single_adult": "CBwQAhoeEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYQAFIAXABmAEC",
    "pax_two_adults": "CBwQAhoeEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYQAFAAUgBcAGYAQI",
    "pax_two_adults_two_lap_infants":
        "CBwQAhoeEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYQAFAAUADQANIAXABmAEC",
    "round_trip_jfk_lax":
        "CBwQAhoeEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYGh4SCjIwMzAtMDktMTlqBwgBEgNMQVhyBwgBEgNKRktAAUgBcAGYAQE",
    "round_trip_selected_connecting_outbound":
        "CBwQAhpgEgoyMDMwLTA5LTE1Ih8KA0pGSxIKMjAzMC0wOS0xNRoDT1JEKgJBQTIDMTAwIh8KA09SRBIKMjAzMC0wOS0xNRoDTEhSKgJBQTIDMjAwagcIARIDSkZLcgcIARIDTEhSGh4SCjIwMzAtMDktMTlqBwgBEgNMSFJyBwgBEgNKRktAAUgBcAGYAQE",
    "round_trip_selected_outbound":
        "CBwQAho_EgoyMDMwLTA5LTE1Ih8KA0pGSxIKMjAzMC0wOS0xNRoDTEhSKgJCQTIDMTc4agcIARIDSkZLcgcIARIDTEhSGh4SCjIwMzAtMDktMTlqBwgBEgNMSFJyBwgBEgNKRktAAUgBcAGYAQE",
    "stops_any": "CBwQAhoeEgoyMDMwLTA5LTE1agcIARIDSkZLcgcIARIDTEFYQAFIAXABmAEC",
    "stops_non_stop": "CBwQAhogEgoyMDMwLTA5LTE1KABqBwgBEgNKRktyBwgBEgNMQVhAAUgBcAGYAQI",
    "stops_one_stop_or_fewer":
        "CBwQAhogEgoyMDMwLTA5LTE1KAFqBwgBEgNKRktyBwgBEgNMQVhAAUgBcAGYAQI",
    "stops_two_or_fewer_stops":
        "CBwQAhogEgoyMDMwLTA5LTE1KAJqBwgBEgNKRktyBwgBEgNMQVhAAUgBcAGYAQI",
    "sweep_one_way_date_override":
        "CBwQAhoeEgoyMDMwLTExLTAyagcIARIDSkZLcgcIARIDTEFYQAFIAXABmAEC",
    "sweep_round_trip_date_override":
        "CBwQAhoeEgoyMDMwLTExLTAyagcIARIDSkZLcgcIARIDTEFYGh4SCjIwMzAtMTEtMDlqBwgBEgNMQVhyBwgBEgNKRktAAUgBcAGYAQE",
}

OUT, RET, MULTI = "2030-09-15", "2030-09-19", "2030-10-15"


def _leg(origin, dest, date, airline, number):
    return {"origin": origin, "dest": dest, "date": date,
            "airline": airline, "flight_number": number}


def _build_cases():
    return {
        "one_way_jfk_lax": lambda: R.build_tfs(["JFK"], ["LAX"], OUT),
        "round_trip_jfk_lax": lambda: R.build_tfs(["JFK"], ["LAX"], OUT, return_date=RET),
        "round_trip_selected_outbound": lambda: R.build_tfs(
            ["JFK"], ["LHR"], OUT, return_date=RET,
            selected_legs=[_leg("JFK", "LHR", OUT, "BA", "178")]),
        "round_trip_selected_connecting_outbound": lambda: R.build_tfs(
            ["JFK"], ["LHR"], OUT, return_date=RET,
            selected_legs=[_leg("JFK", "ORD", OUT, "AA", "100"),
                           _leg("ORD", "LHR", OUT, "AA", "200")]),
        "multi_airport": lambda: R.build_tfs(["BOM", "DEL", "AMD"], ["ORD", "DTW"], MULTI),
        "cabin_economy": lambda: R.build_tfs(["JFK"], ["LAX"], OUT, cabin="economy"),
        "cabin_premium_economy": lambda: R.build_tfs(["JFK"], ["LAX"], OUT,
                                                     cabin="premium_economy"),
        "cabin_business": lambda: R.build_tfs(["JFK"], ["LAX"], OUT, cabin="business"),
        "cabin_first": lambda: R.build_tfs(["JFK"], ["LAX"], OUT, cabin="first"),
        "stops_any": lambda: R.build_tfs(["JFK"], ["LAX"], OUT),
        "stops_non_stop": lambda: R.build_tfs(["JFK"], ["LAX"], OUT, max_stops=0),
        "stops_one_stop_or_fewer": lambda: R.build_tfs(["JFK"], ["LAX"], OUT, max_stops=1),
        "stops_two_or_fewer_stops": lambda: R.build_tfs(["JFK"], ["LAX"], OUT, max_stops=2),
        "pax_single_adult": lambda: R.build_tfs(["JFK"], ["LAX"], OUT, adults=1),
        "pax_two_adults": lambda: R.build_tfs(["JFK"], ["LAX"], OUT, adults=2),
        "pax_adult_child": lambda: R.build_tfs(["JFK"], ["LAX"], OUT, children=1),
        "pax_adult_lap_infant": lambda: R.build_tfs(["JFK"], ["LAX"], OUT, infants_on_lap=1),
        "pax_adult_seat_infant": lambda: R.build_tfs(["JFK"], ["LAX"], OUT,
                                                     infants_in_seat=1),
        "pax_family_mix": lambda: R.build_tfs(["JFK"], ["LAX"], OUT, adults=2, children=1,
                                              infants_in_seat=1, infants_on_lap=1),
        "pax_full_house": lambda: R.build_tfs(["JFK"], ["LAX"], OUT, adults=4, children=2,
                                              infants_in_seat=2, infants_on_lap=1),
        "pax_two_adults_two_lap_infants": lambda: R.build_tfs(
            ["JFK"], ["LAX"], OUT, adults=2, infants_on_lap=2),
        "alliance_include_oneworld": lambda: R.build_tfs(["JFK"], ["LAX"], OUT,
                                                         alliances=["ONEWORLD"]),
        "alliance_include_skyteam": lambda: R.build_tfs(["JFK"], ["LAX"], OUT,
                                                        alliances=["SKYTEAM"]),
        "alliance_include_star_alliance": lambda: R.build_tfs(
            ["JFK"], ["LAX"], OUT, alliances=["STAR_ALLIANCE"]),
        "alliance_exclude_oneworld": lambda: R.build_tfs(
            ["JFK"], ["LAX"], OUT, alliances_exclude=["ONEWORLD"]),
        "alliance_exclude_skyteam": lambda: R.build_tfs(
            ["JFK"], ["LAX"], OUT, alliances_exclude=["SKYTEAM"]),
        "alliance_exclude_star_alliance": lambda: R.build_tfs(
            ["JFK"], ["LAX"], OUT, alliances_exclude=["STAR_ALLIANCE"]),
        "alliance_include_two_exclude_one": lambda: R.build_tfs(
            ["JFK"], ["LAX"], OUT, alliances=["ONEWORLD", "STAR_ALLIANCE"],
            alliances_exclude=["SKYTEAM"]),
        "layover_airport_and_min": lambda: R.build_tfs(
            ["JFK"], ["LAX"], OUT, layover_airports=["ORD"], min_layover=120),
        "layover_max_only": lambda: R.build_tfs(["JFK"], ["LAX"], OUT, max_layover=300),
        "layover_full": lambda: R.build_tfs(["JFK"], ["LAX"], OUT,
                                            layover_airports=["ORD", "DFW"],
                                            min_layover=90, max_layover=600),
        "kitchen_sink_round_trip": lambda: R.build_tfs(
            ["JFK", "EWR"], ["LHR", "LGW"], OUT, return_date=RET, cabin="business",
            max_stops=1, adults=2, children=1, infants_on_lap=1,
            alliances=["ONEWORLD"], layover_airports=["DUB"],
            min_layover=60, max_layover=240),
        "sweep_one_way_date_override": lambda: R.build_tfs(
            ["JFK"], ["LAX"], "2030-11-02"),
        "sweep_round_trip_date_override": lambda: R.build_tfs(
            ["JFK"], ["LAX"], "2030-11-02", return_date="2030-11-09"),
    }


def t_tfs_byte_parity():
    cases = _build_cases()
    check("every golden has a case in this suite",
          set(cases) == set(TFS_GOLDENS), sorted(set(cases) ^ set(TFS_GOLDENS)))
    bad = []
    for name, build in cases.items():
        got = build()
        if got != TFS_GOLDENS[name]:
            bad.append(name)
    check(f"all {len(TFS_GOLDENS)} recorded tfs tokens are byte-identical to the reference",
          bad == [], bad)
    # A malformed token is answered as a different query, so the properties
    # are pinned too, not only the bytes:
    one = R.build_tfs(["JFK"], ["LAX"], OUT)
    check("the token is URL-safe base64 without padding",
          "=" not in one and "+" not in one and "/" not in one, one)
    decoded = R.base64.urlsafe_b64decode(one + "=" * ((4 - len(one) % 4) % 4))
    check("the token decodes to the envelope's constant fields",
          decoded[0:4] == b"\x08\x1c\x10\x02", decoded[:6])
    check("MaxStops.ANY omits the ceiling (writing 0 would mean non-stop)",
          one != R.build_tfs(["JFK"], ["LAX"], OUT, max_stops=0))
    check("a one-way token ends with field 19 = 2",
          decoded[-3:] == b"\x98\x01\x02", decoded[-3:])
    rt = R.base64.urlsafe_b64decode(
        R.build_tfs(["JFK"], ["LAX"], OUT, return_date=RET)
        + "=" * ((4 - len(R.build_tfs(["JFK"], ["LAX"], OUT, return_date=RET)) % 4) % 4))
    check("a round-trip token ends with field 19 = 1", rt[-3:] == b"\x98\x01\x01", rt[-3:])
    check("every airport in a multi-airport segment reaches the request",
          all(code.encode() in R.base64.urlsafe_b64decode(
              R.build_tfs(["BOM", "DEL", "AMD"], ["ORD", "DTW"], MULTI)
              + "=" * ((4 - len(R.build_tfs(["BOM", "DEL", "AMD"], ["ORD", "DTW"], MULTI)) % 4) % 4))
              for code in ("BOM", "DEL", "AMD", "ORD", "DTW")))
    # Passenger codes are money (a lap infant is ~10%, a seat infant ~100%).
    lap = R.build_tfs(["JFK"], ["LAX"], OUT, adults=1, infants_on_lap=1)
    seat = R.build_tfs(["JFK"], ["LAX"], OUT, adults=1, infants_in_seat=1)
    one_adult = R.build_tfs(["JFK"], ["LAX"], OUT)
    check("a lap infant (code 3) and a seat infant (code 4) are different tokens",
          lap != seat and lap != one_adult and seat != one_adult)
    check("passenger counts are refused when zero or over the limit",
          _raises(ValueError, lambda: R.passenger_codes(adults=0))
          and _raises(ValueError, lambda: R.passenger_codes(adults=6, children=4)))
    check("a bad IATA code / cabin / date is refused, not guessed",
          _raises(ValueError, lambda: R.iata("JF"))
          and _raises(ValueError, lambda: R.build_tfs(["JFK"], ["LAX"], OUT, cabin="cargo"))
          and _raises(ValueError, lambda: R.date_window("2026-13-01")))
    window = R.date_window("2030-09-15", days=2)
    check("a +/-2 date window is five ISO dates, in order",
          window == ["2030-09-13", "2030-09-14", "2030-09-15",
                     "2030-09-16", "2030-09-17"], window)


def _raises(kind, fn):
    try:
        fn()
    except kind:
        return True
    except Exception:
        return False
    return False


# ==========================================================================
#   2. The tolerant parser (page payload -> integer cents, never invented)
# ==========================================================================

def _leg_row(duration=420):
    leg = [None] * 23
    leg[11] = duration
    leg[22] = ["AA", "171"]
    return leg


def _row(price=295.0, airline="AA", legs=1, duration=420, with_price=True):
    detail = [airline, [airline + " Air"], [_leg_row(duration) for _ in range(legs)]]
    while len(detail) < 10:
        detail.append(None)
    detail[9] = duration
    price_block = [[None, price], "USD"] if with_price else []
    return [detail, price_block]


def _payload(rows, level=None):
    payload = [None, None, [rows], [], None, [level] if level is not None else None]
    return payload


def _page_html(payload, *, key="ds:1"):
    return ("<html><script>AF_initDataCallback({key: 'ds:0', hash: '0', "
            'data:["other"], sideChannel: {}});</script>'
            f"<script>AF_initDataCallback({{key: '{key}', hash: '1', "
            f"data:{json.dumps(payload)}, sideChannel: {{}}}});</script></html>")


def t_parser():
    parsed = R.parse_payload(_payload([_row(295.0), _row(320.5)]))
    check("a normal page: two priced itineraries are read", len(parsed["itineraries"]) == 2,
          parsed)
    check("the LOWEST price in whole integer cents is 29500",
          parsed["ok"] and parsed["lowest_price_cents"] == 29500, parsed)
    first = parsed["itineraries"][0]
    check("airline, stops and duration decode too",
          first["airline"] == "AA" and first["stops"] == 0
          and first["duration_minutes"] == 420, first)
    check("cents are exact to the cent: 1249.99 -> 124999",
          R.parse_payload(_payload([_row(1249.99)]))["lowest_price_cents"] == 124999)
    check("a two-leg itinerary is one stop",
          R.parse_payload(_payload([_row(legs=2)]))["itineraries"][0]["stops"] == 1)
    check("a zero-decimal currency (JPY) keeps whole units, not x100",
          R.parse_payload(_payload([_row(45000)]), currency="JPY")["lowest_price_cents"] == 45000)
    unknown = R.parse_payload(_payload([_row(100.0)]), currency="ZZZ")
    check("an unknown currency is unavailable, never a guessed cents value",
          unknown["ok"] is False and unknown["itineraries"][0]["price_cents"] is None, unknown)
    level = R.parse_payload(_payload([_row(200.0)], level="low"))
    check("the optional low/typical/high price level is read when present",
          level["itineraries"][0]["price_level"] == "low", level)
    check("... and is None, never guessed, when the payload does not carry one",
          R.parse_payload(_payload([_row(200.0)]))["itineraries"][0]["price_level"] is None)
    for label, payload in (("None", None), ("a string", "not json"),
                           ("an empty object", {}), ("empty lists", [None, None, [[]], []])):
        got = R.parse_payload(payload)
        check(f"a malformed payload ({label}) is unavailable, never a crash or a price",
              got["ok"] is False and got["lowest_price_cents"] is None, got)
    missing_price = R.parse_payload(_payload([_row(with_price=False)]))
    check("a row with no price is skipped, and no price is invented",
          missing_price["ok"] is False and missing_price["lowest_price_cents"] is None,
          missing_price)
    mixed = R.parse_payload(_payload([_row(with_price=False), _row(310.0)]))
    check("one unusable row does not lose the usable ones",
          mixed["ok"] and mixed["lowest_price_cents"] == 31000, mixed)
    broken = R.parse_payload(_payload([["not a row"], _row(280.0)]))
    check("a malformed row is skipped rather than killing the page",
          broken["ok"] and broken["lowest_price_cents"] == 28000, broken)
    second_group = [None, None, [[]], [[_row(199.0)]]]
    check("rows in the second section are parsed as well",
          R.parse_payload(second_group)["lowest_price_cents"] == 19900)
    html = _page_html(_payload([_row(295.0)]))
    page = R.parse_page(html)
    check("a rendered page with a ds:1 blob parses", page["ok"]
          and page["lowest_price_cents"] == 29500, page)
    check("a page without ds:1 is unavailable", R.parse_page("<html>nothing</html>")["ok"] is False)
    check("an unparseable ds:1 blob is unavailable, not an exception",
          R.parse_page(_page_html("oops"))["ok"] is False)
    check("extract_payload skips ds:0 and finds ds:1",
          R.extract_payload(_page_html([1, 2])) == [1, 2])
    check("extract_payload of no html is None", R.extract_payload("") is None)


# ==========================================================================
#   3. SSRF allowlist, one read-only GET, and the challenge rule
# ==========================================================================

class FakeResponse:
    def __init__(self, body=b"<html>ok</html>", status=200):
        self._body = body if isinstance(body, bytes) else str(body).encode()
        self.status = status
        self.headers = {"Content-Type": "text/html"}

    def read(self, n=-1):
        return self._body[:n] if isinstance(n, int) and n >= 0 else self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _opener_returning(response, calls):
    def opener(req, timeout, handlers):
        calls.append(req)
        return response
    return opener


def t_ssrf_and_fetch():
    good = R.page_url(R.build_tfs(["JFK"], ["LAX"], OUT), currency="USD")
    check("the one allowed page URL passes the allowlist", R.page_problem(good) == "", good)
    bad_urls = [
        ("loopback", "https://127.0.0.1/travel/flights?tfs=abc"),
        ("rfc1918", "https://10.0.0.5/travel/flights?tfs=abc"),
        ("cgnat", "https://100.64.0.9/travel/flights?tfs=abc"),
        ("link-local metadata", "https://169.254.169.254/travel/flights?tfs=abc"),
        ("another host", "https://evil.example/travel/flights?tfs=abc"),
        ("plain http", "http://www.google.com/travel/flights?tfs=abc"),
        ("a port", "https://www.google.com:8080/travel/flights?tfs=abc"),
        ("userinfo", "https://u:p@www.google.com/travel/flights?tfs=abc"),
        ("another path", "https://www.google.com/travel/flights/booking?tfs=abc"),
        ("a tracker parameter", "https://www.google.com/travel/flights?tfs=abc&utm_source=x"),
        ("no tfs", "https://www.google.com/travel/flights?hl=en"),
    ]
    for label, url in bad_urls:
        check(f"SSRF/allowlist refuses {label}", R.page_problem(url) != "", R.page_problem(url))
    calls = []
    check("a refused URL never reaches the opener",
          _raises(R.PriceRadarRefused, lambda: R.fetch_page(
              "http://127.0.0.1/travel/flights?tfs=abc",
              opener=_opener_returning(FakeResponse(), calls)))
          and calls == [])
    calls = []
    html = R.fetch_page(good, opener=_opener_returning(FakeResponse(_page_html(
        _payload([_row(295.0)]))), calls))
    check("a valid page URL is fetched once and returned as text",
          "<html>" in html and len(calls) == 1, (len(calls), html[:40]))
    req = calls[0]
    lowered = {k.lower() for k in req.headers}
    check("the request carries no Cookie/Authorization/cache validators",
          not (lowered & {"cookie", "authorization", "if-none-match", "if-modified-since"}),
          sorted(lowered))
    check("the request is a GET of the page", req.get_method() == "GET", req.get_method())
    cache = next((v for k, v in req.headers.items() if k.lower() == "cache-control"), "")
    check("the request says it does not want a cached copy", "no-cache" in cache, cache)
    for label, status, kind in (("403", 403, R.BlockedBySiteChallenge),
                                ("429", 429, R.BlockedBySiteChallenge),
                                ("500", 500, R.FetchFailed)):
        calls2 = []
        def _attempt(status=status, calls2=calls2):
            R.fetch_page(R.page_url("abc"),
                         opener=_opener_returning(FakeResponse(b"x", status), calls2))
        check(f"HTTP {label} raises {kind.__name__}, and is tried ONCE",
              _raises(kind, _attempt) and len(calls2) == 1, (label, len(calls2)))

    def boom(req, timeout, handlers):
        raise urllib.error.URLError("no network")

    check("a network error is FetchFailed (stale), never a price",
          _raises(R.FetchFailed, lambda: R.fetch_page(good, opener=boom)))
    handler = R._NoRedirect()

    class _Req:
        full_url = good

    check("a redirect is refused outright",
          _raises(urllib.error.HTTPError, lambda: handler.redirect_request(
              _Req(), None, 302, "found", {}, "https://127.0.0.1/")))


# ==========================================================================
#   4. The switch, the poll floor, and the disclosure wording
# ==========================================================================

class _FakeFw:
    def __init__(self, section):
        self._section = section

    def load_framework(self):
        return {"price_radar": self._section} if self._section is not None else {}


def t_switch_and_poll_floor():
    real = R.fw
    try:
        R.fw = None
        check("[price_radar] enabled: the default is OFF", R.enabled() is False)
        R.fw = _FakeFw({"enabled": True})
        check("[price_radar] enabled = true turns it on", R.enabled() is True)
        for value in ("false", "0", "no", "off", ""):
            R.fw = _FakeFw({"enabled": value})
            check(f"[price_radar] enabled = {value!r}: OFF", R.enabled() is False)

        class _Broken:
            def load_framework(self):
                raise RuntimeError("unreadable")

        R.fw = _Broken()
        check("a config that cannot be read means OFF, never ON", R.enabled() is False)
    finally:
        R.fw = real
    import random as _random
    floor = R.POLL_FLOOR_SECONDS
    now = 1_000_000.0
    rng = _random.Random(7)
    stamps = [R.next_check_at(now, rng=rng) for _ in range(50)]
    check("the poll floor is at least 300 s", floor >= 300, floor)
    check("every next check is >= floor*(1-30%) out",
          all(t >= now + floor * (1 - R.POLL_JITTER_FRACTION) for t in stamps),
          min(t - now for t in stamps))
    check("... and <= floor*(1+30%) out",
          all(t <= now + floor * (1 + R.POLL_JITTER_FRACTION) for t in stamps),
          max(t - now for t in stamps))
    check("jitter is not a constant tick", len({round(t - now, 3) for t in stamps}) > 1)
    check("asking for a faster floor is raised to the hard floor",
          R.next_check_at(0.0, rng=_random.Random(1), floor=1) >= floor * 0.7)
    check("the approved disclosure wording is the module's constant",
          R.DISCLOSURE.startswith("Checks public product and flight prices without "
                                  "sending cookies, saved logins, or tracking tags")
          and "never logs in, holds seats, or starts a checkout" in R.DISCLOSURE)
    check("the per-result footer is exact",
          R.RESULT_FOOTER == "Checked as a new visitor (no cookies or account used).")
    check("the steering row is the approved sentence",
          R.steering_row(124999, 129999)
          == ("This store showed two different prices at the same time: $1,249.99 "
              "(Desktop · via search referral) vs. $1,299.99 (Mobile · direct)."),
          R.steering_row(124999, 129999))
    check("the proxy footer is the approved sentence",
          R.proxy_note("Tailscale exit")
          == "Checked via configured proxy (Tailscale exit).", R.proxy_note("Tailscale exit"))
    check("the endpoint is described as unofficial everywhere it is named",
          "unofficial" in R.UNOFFICIAL_NOTE.lower()
          and "not a booking tool" in R.UNOFFICIAL_NOTE.lower())
    # No checkout/booking surface exists in this module at all.
    names = {name.lower() for name in dir(R)}
    forbidden = [n for n in names if any(word in n for word in
                                         ("checkout", "booking", "book_", "cart",
                                          "hold_seat", "pnr"))]
    check("no checkout/booking/seat-hold API exists in the module", forbidden == [], forbidden)
    check("the module does not export HTTP verbs other than the one GET",
          not any(hasattr(R, verb) for verb in ("post", "put", "delete", "patch")))


# ==========================================================================
#   5. The store: whole cents, last-known-good, stale, the outside-text diff
# ==========================================================================

def _store(name="price-radar.db"):
    return R.PriceStore(str(TMP / name))


def t_store():
    store = _store("store.db")
    with store._open() as db:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        journal = str(db.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    check("the store creates the schema and a version", version == R.SCHEMA_VERSION)
    check("the database runs under the project's #673 pragmas (WAL)", journal == "wal", journal)
    route = store.add_route("JFK", "LAX", OUT, target_price_cents=25000, now=1000.0)
    check("a route is registered with a target in whole cents",
          route.get("id") and route.get("target_price_cents") == 25000, route)
    again = store.add_route("JFK", "LAX", OUT, target_price_cents=25000, now=1000.0)
    check("the same route twice is one row", route["id"] == again["id"]
          and len(store.routes()) == 1, store.routes())
    check("a target that is not whole cents is refused",
          _raises(ValueError, lambda: store.add_route("JFK", "LAX", OUT,
                                                      target_price_cents=24999.5)))
    check("a bad airport code is refused", _raises(ValueError, lambda: store.add_route(
        "JF", "LAX", OUT)))
    check("not due before the floor+jitter window passes", store.due(route["id"], now=1000.0) is False)
    check("due once the window has passed", store.due(route["id"], now=10_000.0) is True)

    parsed = R.parse_payload(_payload([_row(249.99)]))
    snap = store.record(route["id"], parsed, now=2000.0)
    check("a successful check records the last-known-good price",
          snap["ok"] and store.latest(route["id"], good_only=True)["lowest_price_cents"] == 24999)
    check("last_good_at is carried for the card", store.last_good_at(route["id"]))

    store.record(route["id"], parsed, now=3000.0)
    change = store.diff(route["id"])
    check("an unchanged price is not a change", change["changed"] is False, change)

    lower = R.parse_payload(_payload([_row(199.99)]))
    store.record(route["id"], lower, now=4000.0)
    change = store.diff(route["id"])
    check("a price drop is a change with the cents delta",
          change["changed"] and change["price_delta_cents"] == -5000, change)
    check("the diff text is plain words, in dollars, and says it is outside text",
          "dropped from $249.99 to $199.99" in change["text"]
          and R.RESULT_FOOTER in change["text"], change["text"])
    check("a target reached is called out",
          "at or below your target of $250.00" in change["text"], change["text"])

    stale = store.record_stale(route["id"], R.BLOCKED_REASON, now=5000.0)
    check("a failed/challenged check is stale with the reason and no price",
          stale["stale"] is True and stale["reason"] == R.BLOCKED_REASON
          and "lowest_price_cents" not in stale, stale)
    latest = store.latest(route["id"])
    check("... and the stale row invents no price", latest["lowest_price_cents"] is None, latest)
    check("... and the last good snapshot is untouched (20000 cents -> 19999)",
          store.latest(route["id"], good_only=True)["lowest_price_cents"] == 19999)
    stale_diff = store.diff(route["id"])
    check("a stale check alerts nothing (no text, no change)",
          stale_diff["changed"] is False and stale_diff["stale"] is True
          and stale_diff["text"] == "", stale_diff)

    low = R.parse_payload(_payload([_row(180.0)], level="low"))
    store.record(route["id"], low, now=6000.0)
    low_diff = store.diff(route["id"])
    check("a low price level is called out in plain words",
          "low price" in low_diff["text"], low_diff["text"])
    # The taint latch, spied: a real change calls it, a stale one does not.
    latches = []
    real_latch = R._latch_gate
    try:
        R._latch_gate = lambda: (latches.append("latched"), True)[1]
        store2 = _store("latches.db")
        r2 = store2.add_route("JFK", "LAX", OUT, now=1000.0)
        store2.record(r2["id"], R.parse_payload(_payload([_row(300.0)])), now=2000.0)
        store2.record(r2["id"], R.parse_payload(_payload([_row(250.0)])), now=3000.0)
        store2.diff(r2["id"])
        check("a real change latches the gate taint once", latches == ["latched"], latches)
        latches.clear()
        store2.record_stale(r2["id"], R.BLOCKED_REASON, now=4000.0)
        store2.diff(r2["id"])
        check("a stale failure does not latch (nothing was read)", latches == [], latches)
        store2.close()
    finally:
        R._latch_gate = real_latch

    reused = _store("reopen.db")
    r3 = reused.add_route("JFK", "LAX", OUT, now=1000.0)
    reused.close()
    reopened = _store("reopen.db")
    check("opening the same database again is idempotent and keeps the rows",
          len(reopened.routes()) == 1 and reopened.routes()[0]["id"] == r3["id"])
    reopened.close()
    store.close()

    check("the default database file is price-radar.db in the settings folder",
          R.store_path().name == "price-radar.db")
    cents_store = _store("cents.db")
    cents_route = cents_store.add_route("JFK", "LAX", "2030-09-22", now=1000.0)
    cents_store.record(cents_route["id"], R.parse_payload(_payload([_row(1249.99)])), now=2000.0)
    recorded = cents_store.latest(cents_route["id"], good_only=True)["lowest_price_cents"]
    check("only integer whole cents ever reach the database",
          isinstance(recorded, int) and recorded == 124999, recorded)
    cents_store.close()


# ==========================================================================
#   6. check_route: switch off = zero network; challenge/failure recording
# ==========================================================================

def t_check_route():
    store = _store("route-checks.db")
    route = store.add_route("JFK", "LAX", OUT, currency="USD", now=1000.0)
    calls = []
    opener = _opener_returning(FakeResponse(_page_html(_payload([_row(295.0)]))), calls)
    off = R.check_route(store, route, opener=opener, enabled=False, now=10_000.0)
    check("switch OFF: no check, no network, no request built",
          off["checked"] is False and off["network"] is False
          and off["reason"] == "switched_off" and calls == [], off)
    not_due = R.check_route(store, route, opener=opener, enabled=True, now=1000.0)
    check("not due: still no network (poll floor)", not_due["network"] is False
          and calls == [], not_due)
    ok = R.check_route(store, route, opener=opener, enabled=True, now=10_000.0)
    check("a due, enabled check does ONE read-only fetch and records a price",
          ok["checked"] and ok["network"] and ok["ok"] and len(calls) == 1, ok)
    check("... and the recorded price is whole cents", ok["snapshot"]["lowest_price_cents"] == 29500)

    # A challenge: stale reason, no retry, last good kept, no alert.
    store2 = _store("challenge.db")
    r2 = store2.add_route("JFK", "LAX", RET, now=1000.0)
    store2.record(r2["id"], R.parse_payload(_payload([_row(350.0)])), now=2000.0)
    challenge_calls = []
    blocked = R.check_route(
        store2, r2, enabled=True, now=20_000.0,
        opener=_opener_returning(FakeResponse(b"challenge", 429), challenge_calls))
    check("a 429 is recorded as blocked_by_site_challenge, tried once",
          blocked["ok"] is False and blocked["reason"] == R.BLOCKED_REASON
          and len(challenge_calls) == 1, (blocked, len(challenge_calls)))
    check("... the stale row has NO price", store2.latest(r2["id"])["lowest_price_cents"] is None)
    check("... the last good price is untouched",
          store2.latest(r2["id"], good_only=True)["lowest_price_cents"] == 35000)
    check("... and nothing is alerted", store2.diff(r2["id"])["text"] == "")
    store2.close()

    store3 = _store("failure.db")
    r3 = store3.add_route("JFK", "LAX", MULTI, now=1000.0)
    store3.record(r3["id"], R.parse_payload(_payload([_row(400.0)])), now=2000.0)

    def boom(req, timeout, handlers):
        raise OSError("network down")

    failed = R.check_route(store3, r3, enabled=True, now=30_000.0, opener=boom)
    check("a network failure is stale fetch_failed, no invented price",
          failed["ok"] is False and failed["reason"] == R.FETCH_FAILED
          and store3.latest(r3["id"])["lowest_price_cents"] is None, failed)
    check("... last good still 40000", store3.latest(r3["id"], good_only=True)
          ["lowest_price_cents"] == 40000)
    store3.close()

    # An unavailable page (no ds:1) records stale unavailable, not a price.
    store4 = _store("unavailable.db")
    r4 = store4.add_route("JFK", "LAX", "2030-09-20", now=1000.0)
    no_payload = R.check_route(
        store4, r4, enabled=True, now=40_000.0,
        opener=_opener_returning(FakeResponse(b"<html>no payload</html>"), []))
    check("a page without a payload is unavailable and stale, never 0",
          no_payload["ok"] is False and no_payload["stale"] is True
          and store4.latest(r4["id"])["lowest_price_cents"] is None, no_payload)
    store4.close()
    store.close()

    # Words never logged: a full check prints/logs nothing at all.
    import contextlib
    import io
    store5 = _store("silent.db")
    r5 = store5.add_route("JFK", "LAX", "2030-09-21", now=1000.0)
    out, err = io.StringIO(), io.StringIO()
    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = _Capture()
    logging.getLogger().addHandler(handler)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            R.check_route(store5, r5, enabled=True, now=50_000.0,
                          opener=_opener_returning(
                              FakeResponse(_page_html(_payload([_row(299.0)]))), []))
    finally:
        logging.getLogger().removeHandler(handler)
    check("a full check prints and logs NOTHING (no page words, no prices)",
          out.getvalue() == "" and err.getvalue() == "" and records == [],
          (out.getvalue(), err.getvalue(), records[:3]))
    store5.close()


# ==========================================================================
#   7. F2/F3 integration points, and the module stays standalone
# ==========================================================================

def t_integration_points():
    check("F2 can install its sources without the core importing them",
          callable(R.set_sources) and R.sources() == ())
    R.set_sources([object(), object()])
    check("set_sources/sources round-trip", len(R.sources()) == 2)
    R.set_sources([])
    check("alert_text is empty when nothing changed",
          R.alert_text(_quiet_store(), 1) == "")

    store = _store("alerts.db")
    route = store.add_route("JFK", "LAX", OUT, now=1000.0)
    store.record(route["id"], R.parse_payload(_payload([_row(300.0)])), now=2000.0)
    store.record(route["id"], R.parse_payload(_payload([_row(250.0)])), now=3000.0)
    core = R.alert_text(store, route["id"])
    check("without a renderer the core words include the diff, the footer and the "
          "unofficial warning", R.RESULT_FOOTER in core and "unofficial" in core.lower(), core)
    R.register_alert_renderer(lambda st, rid, change: "CARD: " + change["text"])
    custom = R.alert_text(store, route["id"])
    check("a registered renderer owns the card words", custom.startswith("CARD: "), custom)
    R.register_alert_renderer(None)
    check("... and can be removed again", R.alert_text(store, route["id"]).startswith(
        "The price dropped"), R.alert_text(store, route["id"]))
    store.close()

    # The core never imports the F2/F3 module; if one exists it is a separate
    # shipped file and this suite does not need it. The integration is by the
    # functions above, not by an import.
    check("this core has not imported the F2 sources module",
          "jarvis_price_sources" not in sys.modules, sorted(
              m for m in sys.modules if m.startswith("jarvis_price")))


def _quiet_store():
    store = _store("quiet.db")
    route = store.add_route("JFK", "LAX", MULTI, now=1000.0)
    store.record(route["id"], R.parse_payload(_payload([_row(300.0)])), now=2000.0)
    store.record(route["id"], R.parse_payload(_payload([_row(300.0)])), now=3000.0)
    return store


# ==========================================================================
#   Main
# ==========================================================================

def main():
    print("jarvis_price_radar.py: the flight price radar (F1) - "
          "READ-ONLY, OFF, NO NETWORK IN THIS SUITE\n")
    for name, fn in (
        ("tfs-parity", t_tfs_byte_parity),
        ("parser", t_parser),
        ("ssrf", t_ssrf_and_fetch),
        ("switch", t_switch_and_poll_floor),
        ("store", t_store),
        ("check-route", t_check_route),
        ("integration", t_integration_points),
    ):
        print(f"-- {name}")
        try:
            fn()
        except Exception:
            FAILED.append(name)
            print(f"FAIL  {name} raised\n        {traceback.format_exc()}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
