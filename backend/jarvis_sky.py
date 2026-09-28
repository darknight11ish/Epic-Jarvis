"""jarvis_sky.py - the sun, the moon and the weather behind the animal faces.

NEW MODULE, shipped whole, with its town list `jarvis_sky_places.py`.
sky.patch adds one call at start-up, `install(Handler, ...)` (the same shape
as jarvis_news.py), which answers GET /api/sky and POST /api/sky.
docs/JARVIS-API.md section 59; backend/README.md "The sky behind the animals".

THE OWNER'S DECISIONS (CLAUDE.md, 2026-09-28)
  * "Sun and moon behind the animals, optional (off by default): the real
    sun and moon for the date and time - sunrise and sunset, the moon's
    phase (full, waxing, waning) and its rising and setting - worked out on
    the owner's own devices from a town the owner types once on the PC (the
    phone gets it from the PC). Nothing goes online for it."
  * "Weather in the animals' scene, optional (off by default): rain, snow or
    wind. Two sources to choose from in settings: the owner's own Home
    Assistant (stays on the home network), or Open-Meteo online (free, no
    key; it receives the rough location, so turning it on raises an approval
    card, like any new way out of the PC; turning it off is immediate)."

WHAT THIS MODULE DOES, AND WHAT IT DOES NOT
The sun and moon are NOT worked out here: each app does that itself
(jarvis-desktop/src/sky.js, the phone's face/Sky.kt), from the place this
module keeps, so the phone's sky keeps moving while the PC cannot be
reached. This module keeps the settings, turns a town's name into a rough
position from a list it carries (never online), reads the weather from the
source the owner chose, and hands both apps one small read-only view.

LOCATION IS PRIVATE (rule 1)
  * The town is turned into numbers from `jarvis_sky_places.py` (GeoNames'
    towns, CC BY 4.0), on this PC. No geocoding service is ever asked.
  * Only the position rounded to 0.1 degree (about 11 km) is kept, beside
    the name the owner typed as the list spells it. It is in sky.json in the
    Jarvis settings folder, next to every other setting.
  * It is never written to a log or the audit log (counts and outcomes only),
    never put into an approval card except the Open-Meteo one (which exists
    to show exactly what would be sent), and never offered to the AI model.
  * It goes to the owner's own apps over the pairing link (GET /api/sky,
    behind the token like every other read) and, ONLY if the owner approved
    the Open-Meteo card for that very position, to api.open-meteo.com.
  * The town is set on the PC only (`from_this_pc`), as the owner decided;
    forgetting it is at once, from either app.

THE WEATHER'S TWO SOURCES
  * "home_assistant": the owner's own Home Assistant weather device - the same
    device, environment variables and read the morning briefing uses
    (jarvis_briefing._weather_source for "is it set up, may it read without a
    card", jarvis_home.weather_entity() for which device), read with ONE plain
    GET of that device's state (jarvis_home.plan_states / run), through the
    gate as `home_read` and only when that tier is auto (a notice every 20
    minutes would be noise, the reasoning "tell me when" gives) - the scene
    never raises a card and never sends a notice. Stays on the owner's own networks
    (jarvis_local_http.plain_http_problem, as every Home Assistant read).
    Choosing it needs no card: it adds no new way out.
  * "open_meteo": ONE plain GET of a fixed address,
    https://api.open-meteo.com/v1/forecast, carrying exactly two numbers - the
    rounded latitude and longitude - and the names of the four weather values
    wanted. No key, no cookie, no name, nothing else of the owner's. No proxy,
    no redirect followed, answers capped at 64 KB, 10 seconds at most, and the
    host checked by a real DNS lookup on the connection itself to be on the
    open internet (jarvis_local_http.public_urlopen, the rule news feeds use).
    Turning it ON is ONE approval card (action `change_own_config`, tier "ask"
    only - the card of every setting that lets Jarvis reach one more thing),
    from either app, naming the exact numbers it sends; the approval is for
    THAT position, so typing another town switches it off again until a new
    card is approved. Turning it OFF, or choosing another source, is at once.
    ARCHITECTURE section 4 lists it as its own way out.
  * Either way: read only while an app is showing a face and asking (GET
    /api/sky starts a read in the background when the last is older than
    REFRESH_S; there is no timer of its own), at most every 20 minutes, a
    failure waits RETRY_S before trying again, and a failure is quiet - no
    weather is drawn, and the status line says why in plain words.
  * The weather is turned into five numbers 0..1 (rain, snow, wind, cloud,
    fog) and a drift direction. It is never shown to the AI model, never
    learned from and never read aloud: it is decoration.

    python3 test_sky.py
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

PATH = "/api/sky"

SOURCES = ("off", "home_assistant", "open_meteo")
OPEN_METEO_HOST = "api.open-meteo.com"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
#: Read the weather again after this long, while an app keeps asking.
REFRESH_S = 20 * 60
#: After a failure, wait this long before trying again.
RETRY_S = 30 * 60
FETCH_TIMEOUT = 10.0
MAX_BODY = 64 * 1024
MAX_PLACE_CHARS = 120

CARD_ACTION = "change_own_config"
HOME_ACTION = "home_read"

# --------------------------------------------------------------------------
#   Words both apps show (jarvis-desktop/src/sky-settings.js, the phone's
#   net/SkySettings.kt fall back to the same words when the PC sends none)
# --------------------------------------------------------------------------

TITLE = "Sun, moon and weather"
SHOW_LABEL = "Show the sun and moon behind the animal"
SHOW_DETAIL = ("The real sun and moon for your town - sunrise and sunset, and the moon's shape "
               "(full, waxing, waning) - worked out on your own devices. Nothing goes online "
               "for it. For the animal faces; the others are not changed.")
PLACE_LABEL = "Your town"
PLACE_DETAIL = ("Type it once on the PC. Jarvis finds it in a list of towns it carries and keeps "
                "only a rough position (about 11 km). Not found? Type the position instead, "
                "like 39.7, -105.0.")
PLACE_PHONE = "Your town is typed on the PC, in Settings, Appearance."
PLACE_NONE = "No town yet, so there is no sun or moon to show. Type your town on the PC."
FORGET_LABEL = "Forget my town"
WEATHER_LABEL = "Weather in the animal's scene"
WEATHER_DETAIL = "Rain, snow or wind behind the animal. Off by default."
MISSING = ("Your PC's Jarvis cannot show the sun, moon or weather yet - run apply-patches.ps1 "
           "on the PC.")
WAITING = "Waiting for your yes on the approval card."

CHOICES = (
    {"id": "off", "label": "Off (default)", "why": "No weather is drawn."},
    {"id": "home_assistant", "label": "My Home Assistant",
     "why": ("Reads the weather device your Home Assistant already has. Stays on your home "
             "network. Needs Home Assistant set up for Jarvis on the PC.")},
    {"id": "open_meteo", "label": "Open-Meteo (online)",
     "why": ("Free, no key. Sends your rough position (about 11 km) to api.open-meteo.com "
             "about every 20 minutes while a face is showing - nothing else. Turning it on "
             "takes an approval card; turning it off is instant.")},
)

#: How the last Open-Meteo card went, in words the apps show.
LAST_WORDS = {
    "changed": "Approved. The weather now comes from Open-Meteo.",
    "denied": "You said no, so Open-Meteo was not switched on.",
    "timed_out": "Nobody answered the card in time, so Open-Meteo was not switched on.",
    "withdrawn": "You chose something else before the card was answered, so Open-Meteo "
                 "was not switched on.",
    "refused": "The card could not be answered, so Open-Meteo was not switched on.",
    "failed": "It was approved, but the setting could not be saved, so Open-Meteo was not "
              "switched on.",
    "moved": "Your town changed, so Open-Meteo was switched off: it was approved for the "
             "old position. Choose it again to send the new one.",
}

#: Home Assistant's weather conditions -> the five numbers. Anything else
#: (including "exceptional") draws nothing: a condition is outside text.
HA_WEATHER = {
    "clear-night": {}, "sunny": {},
    "partlycloudy": {"cloud": 0.45},
    "cloudy": {"cloud": 0.9},
    "fog": {"fog": 0.7, "cloud": 0.6},
    "rainy": {"rain": 0.5, "cloud": 0.85},
    "pouring": {"rain": 1.0, "cloud": 1.0},
    "lightning": {"cloud": 0.9},
    "lightning-rainy": {"rain": 0.8, "cloud": 1.0},
    "hail": {"rain": 0.6, "cloud": 0.9},
    "snowy": {"snow": 0.6, "cloud": 0.85},
    "snowy-rainy": {"rain": 0.4, "snow": 0.4, "cloud": 0.9},
    "windy": {"wind": 0.7},
    "windy-variant": {"wind": 0.7, "cloud": 0.6},
}

#: WMO weather codes (Open-Meteo's `weather_code`) -> the five numbers.
#: Thunder is drawn as heavy rain: nothing in the scene ever flashes.
WMO = {
    0: {}, 1: {"cloud": 0.2}, 2: {"cloud": 0.5}, 3: {"cloud": 0.9},
    45: {"fog": 0.7, "cloud": 0.6}, 48: {"fog": 0.8, "cloud": 0.6},
    51: {"rain": 0.2}, 53: {"rain": 0.3}, 55: {"rain": 0.4},
    56: {"rain": 0.3}, 57: {"rain": 0.4},
    61: {"rain": 0.4}, 63: {"rain": 0.6}, 65: {"rain": 0.9},
    66: {"rain": 0.5}, 67: {"rain": 0.8},
    71: {"snow": 0.3}, 73: {"snow": 0.6}, 75: {"snow": 0.9}, 77: {"snow": 0.3},
    80: {"rain": 0.4}, 81: {"rain": 0.6}, 82: {"rain": 0.9},
    85: {"snow": 0.5}, 86: {"snow": 0.8},
    95: {"rain": 0.8}, 96: {"rain": 0.8}, 99: {"rain": 0.9},
}

#: The five numbers, in plain words, for the status line.
def weather_words(now: Optional[dict]) -> str:
    if not now:
        return ""
    bits = []
    rain, snow = now.get("rain", 0), now.get("snow", 0)
    if rain >= 0.75:
        bits.append("heavy rain")
    elif rain >= 0.35:
        bits.append("rain")
    elif rain > 0.02:
        bits.append("light rain")
    if snow >= 0.75:
        bits.append("heavy snow")
    elif snow >= 0.35:
        bits.append("snow")
    elif snow > 0.02:
        bits.append("light snow")
    if now.get("fog", 0) > 0.3:
        bits.append("fog")
    if not bits:
        c = now.get("cloud", 0)
        bits.append("cloudy" if c >= 0.7 else "partly cloudy" if c >= 0.3 else "clear")
    if now.get("wind", 0) >= 0.5:
        bits.append("windy")
    s = ", ".join(bits)
    return s[:1].upper() + s[1:]


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
    return _config_dir() / "sky.json"


def _tier(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-sky", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    # Counts and outcomes only. Never a town, a position or a condition.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _from_this_pc(peer, local) -> bool:
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:
        # Cannot tell: not this PC, so the town is not changed (fail closed).
        return False


# --------------------------------------------------------------------------
#   The settings file
# --------------------------------------------------------------------------

_S_LOCK = threading.RLock()
DEFAULTS = {"show": False, "place": None, "weather": "off", "open_meteo_for": ""}


def _round1(x: float) -> float:
    # Halves away from zero, then tidy: 39.75 -> 39.8, -104.95 -> -105.0.
    return float(f"{math.floor(abs(x) * 10 + 0.5) / 10 * (1 if x >= 0 else -1):.1f}")


def _clean_place(p) -> Optional[dict]:
    if not isinstance(p, dict):
        return None
    try:
        lat, lon = float(p.get("lat")), float(p.get("lon"))
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 90 and abs(lon) <= 180):
        return None
    name = " ".join(str(p.get("name") or "").split())[:MAX_PLACE_CHARS]
    return {"name": name, "lat": _round1(lat), "lon": _round1(lon)}


def load() -> dict:
    """The settings, checked. A damaged or missing file is the defaults
    (off, no town, no weather) - never a guess that sends anything."""
    try:
        doc = json.loads(settings_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return dict(DEFAULTS, why="")
    except Exception as exc:
        return dict(DEFAULTS, why=f"the sky settings could not be read ({type(exc).__name__}), "
                                  f"so they are off")
    if not isinstance(doc, dict):
        return dict(DEFAULTS, why="the sky settings are damaged, so they are off")
    src = doc.get("weather") if doc.get("weather") in SOURCES else "off"
    place = _clean_place(doc.get("place"))
    om_for = str(doc.get("open_meteo_for") or "")
    # Open-Meteo only ever for the position its card named.
    if src == "open_meteo" and (place is None or om_for != position_key(place)):
        src = "off"
    return {"show": doc.get("show") is True, "place": place, "weather": src,
            "open_meteo_for": om_for, "why": ""}


def _save(**changes) -> dict:
    with _S_LOCK:
        cur = load()
        cur.pop("why", None)
        cur.update(changes)
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(dict(cur, changed=time.time()), indent=1), encoding="utf-8")
        os.replace(tmp, p)
        return load()


def position_key(place: Optional[dict]) -> str:
    if not place:
        return ""
    return f"{place['lat']:.1f},{place['lon']:.1f}"


# --------------------------------------------------------------------------
#   Finding a town - from the list this PC carries, never online
# --------------------------------------------------------------------------

_INDEX: dict = {}
_I_LOCK = threading.Lock()


def _fold(text: str) -> str:
    """Lower case, no accents, punctuation as spaces, "saint" as "st"."""
    t = unicodedata.normalize("NFKD", str(text or ""))
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).casefold()
    t = re.sub(r"[^\w]+", " ", t, flags=re.UNICODE).replace("_", " ")
    words = ["st" if w in ("saint", "st") else w for w in t.split()]
    return " ".join(words)


def _index() -> dict:
    with _I_LOCK:
        if _INDEX:
            return _INDEX
        import jarvis_sky_places as P
        rows, by = [], {}
        for line in P.DATA.splitlines():
            parts = line.split("\t")
            if len(parts) != 6:
                continue
            name, cc, region, lat, lon, pop = parts
            try:
                row = (name, cc, region, float(lat), float(lon), int(pop))
            except ValueError:
                continue
            rows.append(row)
            by.setdefault(_fold(name), []).append(row)
        countries = {}
        for line in P.COUNTRIES.splitlines():
            code, _, name = line.partition("\t")
            if code and name:
                countries[code] = name
        states = {}
        for line in P.US_STATES.splitlines():
            code, _, name = line.partition("\t")
            if code and name:
                states[code] = name
        _INDEX.update(rows=rows, by=by, countries=countries, states=states,
                      folded_names=sorted(by))
        return _INDEX


def _label(row, idx) -> str:
    name, cc, region = row[0], row[1], row[2]
    country = idx["countries"].get(cc, cc)
    return ", ".join(x for x in (name, region, country) if x)


_COORD = re.compile(
    r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*°?\s*([NS])?\s*[,;\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*°?\s*([EW])?\s*$",
    re.IGNORECASE)


def parse_position(text: str) -> Optional[dict]:
    """"39.7, -105.0", "39.7 -105", "39.7N 105.0W" -> {lat, lon}, or None."""
    m = _COORD.match(str(text or ""))
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(3))
    if m.group(2):
        lat = -abs(lat) if m.group(2).upper() == "S" else abs(lat)
    if m.group(4):
        lon = -abs(lon) if m.group(4).upper() == "W" else abs(lon)
    if abs(lat) > 90 or abs(lon) > 180:
        return None
    return {"lat": lat, "lon": lon}


def find_place(text) -> dict:
    """{"ok": True, "place": {name, lat, lon}, "also": [labels]} or
    {"ok": False, "error": a sentence}. Never a network call."""
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "error": "Type your town, or its position like 39.7, -105.0."}
    raw = " ".join(text.split())[:MAX_PLACE_CHARS]
    pos = parse_position(raw)
    if pos is not None:
        p = _clean_place({"name": f"{_round1(pos['lat']):.1f}, {_round1(pos['lon']):.1f}", **pos})
        return {"ok": True, "place": p, "also": []}
    idx = _index()
    town, _, rest = raw.partition(",")
    key = _fold(town)
    quals = [_fold(q) for q in rest.split(",") if _fold(q)]
    if not key:
        return {"ok": False, "error": "Type your town, or its position like 39.7, -105.0."}
    found = list(idx["by"].get(key, []))
    if not found:
        # "New York" is "New York City" in the list: a name that starts with
        # every word typed.
        for name in idx["folded_names"]:
            if name.startswith(key + " "):
                found.extend(idx["by"][name])
    if not found:
        return {"ok": False, "error": (f"\"{town.strip()}\" is not in the list of towns Jarvis "
                                       f"carries (towns of about 15,000 people or more in the "
                                       f"US, Canada, the UK, Ireland, Australia and New Zealand; "
                                       f"50,000 or more elsewhere). Try a bigger town nearby, or "
                                       f"type the position instead, like 39.7, -105.0.")}

    def matches(row, q):
        name, cc, region = row[0], row[1], row[2]
        country = idx["countries"].get(cc, "")
        state_code = next((c for c, n in idx["states"].items() if n == region), "")
        return q in (_fold(cc), _fold(country), _fold(region), _fold(state_code)) or \
            (q in ("usa", "us", "america", "united states of america") and cc == "US") or \
            (q in ("uk", "britain", "great britain", "england", "scotland", "wales",
                   "northern ireland") and cc == "GB")

    if quals:
        picked = [r for r in found if all(matches(r, q) for q in quals)]
        if not picked:
            return {"ok": False, "error": (f"Jarvis knows {town.strip()}, but not in "
                                           f"{rest.strip()}. Try the state or country's full "
                                           f"name, or type the position instead.")}
        found = picked
    found.sort(key=lambda r: -r[5])
    best = found[0]
    p = _clean_place({"name": _label(best, idx), "lat": best[3], "lon": best[4]})
    also = [_label(r, idx) for r in found[1:4]]
    return {"ok": True, "place": p, "also": also}


# --------------------------------------------------------------------------
#   The weather, read and cached
# --------------------------------------------------------------------------

_W_LOCK = threading.Lock()
_W: dict = {"key": "", "now": None, "at": 0.0, "status": "", "failed_at": 0.0,
            "busy": False, "source": "off"}


def _number(v) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) and abs(v) < 1e6 else None


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _wind_from(speed_ms: Optional[float], bearing: Optional[float], lat: Optional[float]) -> tuple:
    """(wind 0..1, dir +1 right / -1 left on screen). A wind of 14 m/s (a
    near gale) or more is 1. `bearing` is where the wind comes FROM,
    degrees; it blows toward bearing + 180. The frame looks toward the
    equator (sky.js), so facing south east is on the left and west on the
    right; facing north, the other way round."""
    wind = _clamp01((speed_ms or 0.0) / 14.0)
    if bearing is None:
        return wind, 1
    toward = math.radians((bearing + 180.0) % 360.0)
    east_part = math.sin(toward)          # + blowing toward the east
    facing_south = (lat is None) or lat >= 0
    right = -east_part if facing_south else east_part
    return wind, (1 if right >= 0 else -1)


def _now_of(cond: dict, wind: float, direction: int, at: float) -> dict:
    return {"rain": _clamp01(float(cond.get("rain", 0.0))),
            "snow": _clamp01(float(cond.get("snow", 0.0))),
            "wind": _clamp01(max(wind, float(cond.get("wind", 0.0)))),
            "cloud": _clamp01(float(cond.get("cloud", 0.0))),
            "fog": _clamp01(float(cond.get("fog", 0.0))),
            "dir": direction, "at": round(at, 3)}


_TO_MS = {"m/s": 1.0, "km/h": 1 / 3.6, "mph": 0.44704, "kn": 0.514444, "ft/s": 0.3048}


def parse_home(out: dict, lat: Optional[float], at: float) -> tuple:
    """jarvis_home.run()'s answer for ONE weather device -> (now, None) or
    (None, why)."""
    if not isinstance(out, dict) or not out.get("ok"):
        why = str((out or {}).get("reason") or "Home Assistant did not answer")
        return None, why[:200]
    states = out.get("states") or []
    if not states or not isinstance(states[0], dict):
        return None, "Home Assistant sent no weather"
    st = states[0]
    cond = HA_WEATHER.get(str(st.get("state") or ""))
    if cond is None:
        return None, "your Home Assistant's weather device gave a condition Jarvis does not draw"
    attrs = {}
    try:
        a = json.loads(st.get("attributes") or "{}")
        attrs = a if isinstance(a, dict) else {}
    except ValueError:
        attrs = {}
    speed = _number(attrs.get("wind_speed"))
    unit = str(attrs.get("wind_speed_unit") or "km/h")
    if speed is not None:
        speed *= _TO_MS.get(unit, 1 / 3.6)
    wind, direction = _wind_from(speed, _number(attrs.get("wind_bearing")), lat)
    return _now_of(cond, wind, direction, at), None


def parse_open_meteo(raw: bytes, lat: Optional[float], at: float) -> tuple:
    try:
        doc = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return None, "Open-Meteo answered, but not with weather Jarvis can read"
    cur = doc.get("current") if isinstance(doc, dict) else None
    if not isinstance(cur, dict):
        return None, "Open-Meteo answered, but not with weather Jarvis can read"
    code = _number(cur.get("weather_code"))
    cond = dict(WMO.get(int(code), {})) if code is not None else {}
    cc = _number(cur.get("cloud_cover"))
    if cc is not None:
        cond["cloud"] = max(float(cond.get("cloud", 0.0)), _clamp01(cc / 100.0))
    wind, direction = _wind_from(_number(cur.get("wind_speed_10m")),
                                 _number(cur.get("wind_direction_10m")), lat)
    return _now_of(cond, wind, direction, at), None


def open_meteo_url(place: dict) -> str:
    """The ONE address Open-Meteo is ever sent: the rounded position and the
    names of four values. Nothing else of the owner's."""
    return (f"{OPEN_METEO_URL}?latitude={place['lat']:.1f}&longitude={place['lon']:.1f}"
            "&current=weather_code,cloud_cover,wind_speed_10m,wind_direction_10m"
            "&wind_speed_unit=ms")


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """A weather answer has no business redirecting (jarvis_search's reason)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "refused to follow a redirect",
                                     headers, fp)


def _default_open_meteo_fetch(url: str) -> bytes:
    import jarvis_local_http as LH
    if urlsplit(url).hostname != OPEN_METEO_HOST or not url.startswith(OPEN_METEO_URL + "?"):
        raise ValueError("not the Open-Meteo address")
    req = urllib.request.Request(url, headers={"User-Agent": "Jarvis (weather for the face)",
                                               "Accept": "application/json"})
    with LH.public_urlopen(req, FETCH_TIMEOUT, _RefuseRedirect()) as resp:
        body = resp.read(MAX_BODY + 1)
    if len(body) > MAX_BODY:
        raise ValueError("the answer was too large")
    return body


class Deps:
    """What the reads need, replaceable in tests (no socket, no gate)."""

    def __init__(self, *, tier_of=None, gate=None, home_fetch=None, open_meteo_fetch=None,
                 home_ready=None, clock=None, spawn=None):
        self.tier_of = tier_of or _tier
        self.gate = gate or _gate
        self.home_fetch = home_fetch            # jarvis_home.run's `fetch`
        self.open_meteo_fetch = open_meteo_fetch or _default_open_meteo_fetch
        self.home_ready = home_ready or _home_ready
        self.clock = clock or time.time
        self.spawn = spawn or _spawn


def _home_ready() -> dict:
    """The morning briefing's own answer to "can the weather be read from
    Home Assistant without a card?" - {"state": on|off|asks, "said"}."""
    try:
        import jarvis_briefing as B
        d = B.Deps()
        return B._weather_source(d, d.tools_enabled())
    except Exception as exc:
        return {"state": "off", "said": f"Home Assistant could not be checked "
                                        f"({type(exc).__name__})."}


#: Why the Home Assistant weather is not read, when the fix is a setting on
#: the PC rather than time: the status line then does not promise a retry.
HA_NOT_SET_UP = "Home Assistant is not set up for Jarvis on this PC"
HA_ASKS = ("your settings ask for a yes, or a notice, each time Jarvis reads Home Assistant - "
           "the scene reads it every 20 minutes, so it needs that read set to happen quietly "
           "(\"What asks first\", Home Assistant reading)")
_SETTING_REASONS = (HA_NOT_SET_UP, HA_ASKS, "Open-Meteo needs your town - type it on the PC first")


def read_home(place: Optional[dict], deps: Deps) -> tuple:
    """One read of the owner's own Home Assistant weather device, through
    the gate as home_read, only at tier auto. (now, None) or (None, why)."""
    ready = deps.home_ready()
    if ready.get("state") != "on":
        return None, HA_ASKS if ready.get("state") == "asks" else HA_NOT_SET_UP
    # "auto" only, like "tell me when"'s looks: at "notify" the owner would be
    # told about a read every 20 minutes.
    if deps.tier_of(HOME_ACTION) != "auto":
        return None, HA_ASKS
    import jarvis_home as HOME
    p = HOME.plan_states([HOME.weather_entity()])
    if p.reason_empty:
        return None, str(p.reason_empty)[:200]
    text = HOME.describe(p)
    try:
        v = deps.gate(HOME_ACTION, {"text": text, "for": "the weather in the animal's scene"},
                      text)
    except Exception:
        v = None
    if getattr(v, "allowed", False) is not True:
        return None, "the approval gate did not let this read run"
    out = HOME.run(p, fetch=deps.home_fetch, approved=True)
    return parse_home(out, place["lat"] if place else None, deps.clock())


def read_open_meteo(place: Optional[dict], s: dict, deps: Deps) -> tuple:
    if not place:
        return None, "Open-Meteo needs your town - type it on the PC first"
    # The approval is for THIS position (load() drops the source otherwise;
    # checked again here, immediately before anything is sent).
    if s.get("open_meteo_for") != position_key(place):
        return None, "Open-Meteo was approved for a different position"
    try:
        raw = deps.open_meteo_fetch(open_meteo_url(place))
    except urllib.error.HTTPError as exc:
        return None, f"Open-Meteo answered with an error (HTTP {exc.code})"
    except Exception as exc:
        return None, f"Open-Meteo did not answer ({type(exc).__name__})"
    return parse_open_meteo(raw, place["lat"], deps.clock())


def _cache_key(s: dict) -> str:
    return f"{s['weather']}|{position_key(s['place']) if s['weather'] == 'open_meteo' else ''}"


def refresh(deps: Optional[Deps] = None, *, wait: bool = False) -> None:
    """Start a read when the last is too old (never two at once). `wait`
    runs it here (tests, and the first read after a source is chosen)."""
    deps = deps or DEPS
    s = load()
    key = _cache_key(s)
    now = deps.clock()
    with _W_LOCK:
        if s["weather"] == "off":
            _W.update(key=key, now=None, at=0.0, status="", failed_at=0.0, source="off")
            return
        if _W["key"] != key:
            _W.update(key=key, now=None, at=0.0, status="", failed_at=0.0, source=s["weather"])
        if _W["busy"]:
            return
        if _W["now"] is not None and now - _W["at"] < REFRESH_S:
            return
        if _W["failed_at"] and now - _W["failed_at"] < RETRY_S:
            return
        _W["busy"] = True

    def work():
        try:
            if s["weather"] == "home_assistant":
                got, why = read_home(s["place"], deps)
            else:
                got, why = read_open_meteo(s["place"], s, deps)
        except Exception as exc:
            got, why = None, f"something went wrong ({type(exc).__name__})"
        with _W_LOCK:
            _W["busy"] = False
            if _W["key"] != key:
                return
            if got is not None:
                _W.update(now=got, at=deps.clock(), status="", failed_at=0.0)
            else:
                _W.update(now=None, at=0.0, status=why, failed_at=deps.clock())
        _audit("sky.weather.read", {"source": s["weather"], "ok": got is not None})

    if wait:
        work()
    else:
        try:
            deps.spawn(work)
        except Exception:
            with _W_LOCK:
                _W["busy"] = False


DEPS = Deps()


def _source_words(src: str) -> str:
    return {"home_assistant": "your Home Assistant", "open_meteo": "Open-Meteo"}.get(src, "")


def weather_view(s: dict) -> dict:
    with _W_LOCK:
        w = dict(_W)
    with _P_LOCK:
        waiting = bool(_P_STATE["pending"])
        last = dict(_P_STATE["last"]) or None
    src = s["weather"]
    now = w["now"] if w["key"] == _cache_key(s) and src != "off" else None
    if waiting:
        status = WAITING
    elif src == "off":
        status = "Off."
    elif now is not None:
        status = f"{weather_words(now)}, from {_source_words(src)}."
    elif w["status"] and w["key"] == _cache_key(s):
        status = f"No weather drawn: {w['status'].rstrip('.')}."
        if w["status"] not in _SETTING_REASONS:
            status += f" Jarvis tries again in about {RETRY_S // 60} minutes."
    else:
        status = f"Reading the weather from {_source_words(src)}..."
    return {"source": src, "choices": [dict(c) for c in CHOICES], "now": now,
            "status": status, "waiting": waiting, "last": last,
            "label": WEATHER_LABEL, "detail": WEATHER_DETAIL}


def view(*, here: bool = True) -> dict:
    s = load()
    place = s["place"]
    return {
        "available": True, "title": TITLE,
        "show": s["show"], "show_label": SHOW_LABEL, "show_detail": SHOW_DETAIL,
        "place": dict(place) if place else None,
        "place_label": PLACE_LABEL,
        "place_detail": PLACE_DETAIL if here else PLACE_PHONE,
        "place_none": PLACE_NONE, "forget_label": FORGET_LABEL,
        "can_set_place": bool(here),
        "weather": weather_view(s),
        "why": s.get("why", ""),
    }


# --------------------------------------------------------------------------
#   Changes: show at once; the town on the PC only; the weather source -
#   off and Home Assistant at once, Open-Meteo ONE card
# --------------------------------------------------------------------------

_P_LOCK = threading.Lock()
_P_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}, "latest": {}}


def card(place: dict) -> str:
    pos = position_key(place).replace(",", ", ")
    return "\n".join([
        "Let Jarvis get the weather for the animal's scene from Open-Meteo?",
        "",
        f"Sends: your rough position, {pos} (rounded to about 11 km) - nothing else. No "
        "name, no account, no key.",
        f"To: {OPEN_METEO_HOST}, a free weather service on the internet, about every 20 "
        "minutes while a face is showing.",
        "Back: the weather now - rain, snow, cloud and wind - drawn behind the animal. It is "
        "never given to the AI model.",
        "",
        "Turning it off is instant, from either app. Typing another town switches it off "
        "until you approve the new position.",
        "",
        "If you did not just do this, say no.",
        "",
        "If you say no: no weather from Open-Meteo, and nothing is sent.",
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
    _audit("sky.open_meteo.card", {"outcome": outcome})


def _person_said_yes(v) -> bool:
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


def _decide(pid: str, place: dict, gate: Callable, tier_of: Callable) -> None:
    text = card(place)
    detail = {"text": text, "what": "get the weather for the animal's scene from Open-Meteo",
              "setting": "weather in the animal's scene", "to": OPEN_METEO_HOST,
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
        s = load()
        if position_key(s["place"]) != position_key(place):
            return _finish(pid, "moved")
        try:
            _save(weather="open_meteo", open_meteo_for=position_key(place))
        except Exception as exc:
            return _finish(pid, "failed", type(exc).__name__)
    _finish(pid, "changed")


def _withdraw_pending() -> None:
    with _P_LOCK:
        if _P_STATE["pending"]:
            _P_STATE["withdrawn"].add(_P_STATE["pending"]["id"])
            _P_STATE["pending"].clear()


def request_weather(src, *, gate: Optional[Callable] = None,
                    tier_of: Optional[Callable] = None, spawn: Optional[Callable] = None,
                    here: bool = True) -> tuple:
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if src not in SOURCES:
        return 400, {"ok": False, "error": "That is not one of the three choices."}
    s = load()
    if src != "open_meteo":
        # Off, or the owner's own Home Assistant: at once. Choosing anything
        # else also withdraws a waiting Open-Meteo card.
        _withdraw_pending()
        try:
            s = _save(weather=src, open_meteo_for="" if src == "off" else s["open_meteo_for"])
        except Exception as exc:
            return 500, {"ok": False, "error": f"could not save ({type(exc).__name__})"}
        _audit("sky.weather.source", {"source": src})
        said = ("No weather is drawn now." if src == "off"
                else "The weather now comes from your Home Assistant.")
        return 200, {"ok": True, "said": said, "view": view(here=here)}
    if s["weather"] == "open_meteo":
        return 200, {"ok": True, "said": "Open-Meteo is already on.", "view": view(here=here)}
    if not s["place"]:
        return 409, {"ok": False, "error": "Open-Meteo needs your town first - type it in "
                                           "Settings on the PC."}
    t = tier_of(CARD_ACTION)
    if t != "ask":
        return 503, {"ok": False, "error": (
            f"{CARD_ACTION} is tier {t!r} in jarvis-framework.toml; switching Open-Meteo on "
            f"needs a person to say yes, so it must be 'ask'")}
    place = dict(s["place"])
    with _P_LOCK:
        if _P_STATE["pending"]:
            return 202, {"ok": True, "waiting": True, "said": WAITING, "view": view(here=here)}
        pid = uuid.uuid4().hex
        _P_STATE["pending"].update(id=pid, since=time.time())
        _P_STATE["latest"]["id"] = pid
    try:
        spawn(lambda: _decide(pid, place, gate, tier_of))
    except Exception:
        with _P_LOCK:
            _P_STATE["pending"].clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True,
                 "said": ("Waiting for your approval. Nothing is sent to Open-Meteo unless you "
                          "approve the card, on your PC or phone."),
                 "view": view(here=here)}


def request_place(text, *, here: bool) -> tuple:
    if not here:
        return 403, {"ok": False, "error": "Your town is typed on the PC, in Settings, "
                                           "Appearance - never sent from the phone."}
    got = find_place(text)
    if not got["ok"]:
        return 400, {"ok": False, "error": got["error"]}
    place = got["place"]
    with _S_LOCK:
        s = load()
        moved = s["weather"] == "open_meteo" and position_key(place) != s["open_meteo_for"]
        changes = {"place": place}
        if moved:
            changes.update(weather="off", open_meteo_for="")
        _withdraw_pending()
        try:
            _save(**changes)
        except Exception as exc:
            return 500, {"ok": False, "error": f"could not save ({type(exc).__name__})"}
    if moved:
        with _P_LOCK:
            _P_STATE["last"].clear()
            _P_STATE["last"].update(outcome="moved", why="", at=time.time(),
                                    message=LAST_WORDS["moved"])
    _audit("sky.place.set", {"moved_open_meteo_off": moved})
    said = f"Set to {place['name']}."
    if got["also"]:
        said += (" Also found: " + "; ".join(got["also"]) + ". To pick another, add its state "
                 "or country after a comma.")
    if moved:
        said += " " + LAST_WORDS["moved"]
    return 200, {"ok": True, "said": said, "view": view(here=here)}


def forget_place(*, here: bool) -> tuple:
    """At once, from either app: less is known, never more."""
    with _S_LOCK:
        s = load()
        changes = {"place": None}
        if s["weather"] == "open_meteo":
            changes.update(weather="off", open_meteo_for="")
        _withdraw_pending()
        try:
            _save(**changes)
        except Exception as exc:
            return 500, {"ok": False, "error": f"could not save ({type(exc).__name__})"}
    _audit("sky.place.forget", {})
    return 200, {"ok": True, "said": "Forgotten. There is no sun or moon to show until you "
                                     "type a town again.", "view": view(here=here)}


def handle_post(body, *, here: bool, deps: Optional[Deps] = None) -> tuple:
    """POST /api/sky with ONE change:
         {"show": true|false}               at once, either app
         {"place": "Denver"}                the PC only
         {"forget_place": true}             at once, either app
         {"weather": "off"|"home_assistant"|"open_meteo"}
    """
    if not isinstance(body, dict) or len(body) != 1:
        return 400, {"ok": False, "error": "Send one change at a time."}
    (k, v), = body.items()
    if k == "show":
        if not isinstance(v, bool):
            return 400, {"ok": False, "error": "show is true or false."}
        try:
            _save(show=v)
        except Exception as exc:
            return 500, {"ok": False, "error": f"could not save ({type(exc).__name__})"}
        _audit("sky.show", {"on": v})
        said = ("The sun and moon now show behind the animal." if v
                else "The sun and moon are no longer shown.")
        return 200, {"ok": True, "said": said, "view": view(here=here)}
    if k == "place":
        return request_place(v, here=here)
    if k == "forget_place":
        if v is not True:
            return 400, {"ok": False, "error": "forget_place is true."}
        return forget_place(here=here)
    if k == "weather":
        code, out = request_weather(v, here=here)
        if code == 200 and v != "off":
            refresh(deps)
        return code, out
    return 400, {"ok": False, "error": f"{k!r} is not a sky setting."}


def handle_get(*, here: bool, deps: Optional[Deps] = None) -> tuple:
    refresh(deps)
    return 200, view(here=here)


# --------------------------------------------------------------------------
#   The route both apps call
# --------------------------------------------------------------------------

def _peer_local(handler) -> tuple:
    peer = (getattr(handler, "client_address", None) or ("",))[0]
    try:
        local = handler.connection.getsockname()[0]
    except Exception:
        local = None
    return peer, local


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so /api/sky is answered here,
    after the server's own origin and token checks. Every other request goes
    straight to the original."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_sky", False):
        _ARMED = True
        return "  sky        Sun, moon and weather (already on)"

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
            code, out = handle_get(here=_from_this_pc(*_peer_local(self)))
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        try:
            code, out = handle_post(body, here=_from_this_pc(*_peer_local(self)))
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_sky = True
    do_POST._jarvis_sky = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    s = load()
    return (f"  sky        Sun, moon and weather: sun and moon {'on' if s['show'] else 'off'}, "
            f"weather {s['weather'].replace('_', ' ')}")


_ARMED = False


def _reset_for_tests() -> None:
    global _ARMED
    with _P_LOCK:
        _P_STATE["pending"].clear()
        _P_STATE["withdrawn"].clear()
        _P_STATE["last"].clear()
        _P_STATE["latest"].clear()
    with _W_LOCK:
        _W.update(key="", now=None, at=0.0, status="", failed_at=0.0, busy=False, source="off")
    _ARMED = False
