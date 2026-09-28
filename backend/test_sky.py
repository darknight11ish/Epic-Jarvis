"""test_sky.py - the sun, the moon and the weather behind the animal faces
(jarvis_sky.py, sky.patch; the owner's decisions of 2026-09-28).

    python3 backend/test_sky.py

Runs anywhere; no model, no real network (every read is injected, and
socket.connect is made to raise while the rules that must open nothing
run). What it proves:

1. Off by default, all of it: no sun and moon, no town, no weather. A
   damaged settings file means off, never a guess that sends something.
2. Finding a town is offline: well-known towns land where they are
   (checked against their published positions to 0.1 degree), a state or
   country after a comma picks between namesakes, a position can be typed
   instead, only the position rounded to 0.1 degree is kept, and nothing
   opens a socket.
3. The town is set from the PC only; forgetting it is at once, from either
   app, and switches Open-Meteo off.
4. The weather source: off and Home Assistant at once; Open-Meteo is ONE
   card (change_own_config, tier "ask" only) that names the exact numbers
   sent - only a person's "approved" switches it on, and only for THAT
   position (a new town switches it off again). Choosing another source
   withdraws a waiting card.
5. The Open-Meteo request carries only the rounded position and the names
   of four values, to the one fixed address; the real fetch refuses any
   other address. Its answer becomes five numbers; a failure is quiet (no
   weather) with a plain status line, and is not retried for RETRY_S.
6. Home Assistant: reused from the morning briefing (is it set up, may it
   read without a card); read through the gate as home_read, and only at
   tier auto (a notice every 20 minutes is noise); its condition and wind
   become the five numbers.
7. Reads happen only when an app asks (GET), at most every REFRESH_S.
8. The route and the patch: install() answers /api/sky after the server's
   own checks and passes everything else on; the PC-only rule comes from
   the connection itself; sky.patch applies after the rest of the stack
   and reverses; the modules are shipped; the town never reaches the audit
   log.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_sky.py", "jarvis_sky_places.py")
import _stack  # noqa: E402
import jarvis_sky as SK  # noqa: E402

FAILED, PASSED = [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-sky-"))
CONF = TMP / "config"
CONF.mkdir()
SK._config_dir = lambda: CONF
AUDIT = []
SK._audit = lambda event, detail: AUDIT.append((event, json.dumps(detail)))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond
                                                        else ""))


class Verdict:
    def __init__(self, allowed, outcome, tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier
        self.reason = outcome


def run_now(fn):
    fn()


def fresh():
    SK._reset_for_tests()
    try:
        SK.settings_path().unlink()
    except FileNotFoundError:
        pass


class NoSocket:
    """socket.connect raises while inside: "opens no socket" as a fact."""

    def __enter__(self):
        self.real = socket.socket.connect

        def refuse(*a, **k):
            raise AssertionError("a socket was opened")
        socket.socket.connect = refuse
        return self

    def __exit__(self, *exc):
        socket.socket.connect = self.real
        return False


APPROVE = lambda a, d, p: Verdict(True, "approved")  # noqa: E731
ASK = lambda a: "ask"  # noqa: E731


def t_off_by_default():
    fresh()
    v = SK.view()
    check("off by default: no sun and moon", v["show"] is False)
    check("off by default: no town", v["place"] is None)
    check("off by default: no weather", v["weather"]["source"] == "off" and v["weather"]["now"] is None)
    SK.settings_path().write_text("{not json", encoding="utf-8")
    s = SK.load()
    check("a damaged file means off, and says why",
          s["show"] is False and s["weather"] == "off" and s["place"] is None and s["why"])
    SK.settings_path().write_text(json.dumps({"show": True, "weather": "open_meteo",
                                              "place": {"name": "x", "lat": 40, "lon": -74},
                                              "open_meteo_for": "51.5,-0.1"}), encoding="utf-8")
    check("Open-Meteo in the file for another position reads as off",
          SK.load()["weather"] == "off")
    fresh()


# Published positions (Wikipedia / GeoNames), to 0.1 degree.
KNOWN = [("London", 51.5, -0.1), ("Denver", 39.7, -105.0), ("Sydney", -33.9, 151.2),
         ("New York", 40.7, -74.0), ("Tokyo", 35.7, 139.7), ("Sao Paulo", -23.5, -46.6),
         ("reykjavik", 64.1, -21.9), ("Saint Louis, Missouri", 38.6, -90.2)]


def t_find_place_offline():
    with NoSocket():
        for text, lat, lon in KNOWN:
            got = SK.find_place(text)
            ok = got["ok"] and abs(got["place"]["lat"] - lat) <= 0.15 \
                and abs(got["place"]["lon"] - lon) <= 0.15
            check(f"{text!r} is found near {lat}, {lon}", ok, repr(got))
        p = SK.find_place("Portland")
        check("Portland means the bigger one (Oregon), and names the others",
              p["ok"] and "Oregon" in p["place"]["name"] and any("Maine" in a for a in p["also"]))
        p2 = SK.find_place("Portland, Maine")
        check("a state after a comma picks it", p2["ok"] and "Maine" in p2["place"]["name"])
        p3 = SK.find_place("Portland, ME")
        check("a state's two letters work too", p3["ok"] and "Maine" in p3["place"]["name"])
        p4 = SK.find_place("London, Canada")
        check("a country after a comma picks it", p4["ok"] and "Canada" in p4["place"]["name"])
        p5 = SK.find_place("Paris, Texas")
        check("Paris, Texas is not Paris, France", p5["ok"] and "Texas" in p5["place"]["name"])
        p6 = SK.find_place("39.74, -104.99")
        check("a typed position works, rounded to 0.1",
              p6["ok"] and p6["place"]["lat"] == 39.7 and p6["place"]["lon"] == -105.0)
        p7 = SK.find_place("33.9S 151.2E")
        check("N/S/E/W letters work", p7["ok"] and p7["place"]["lat"] == -33.9
              and p7["place"]["lon"] == 151.2)
        bad = SK.find_place("Qwertyuiopville")
        check("an unknown town says so plainly, and how to type a position",
              not bad["ok"] and "39.7, -105.0" in bad["error"])
        check("nonsense positions are refused", not SK.find_place("95, 10")["ok"])
        check("an empty town is refused", not SK.find_place("  ")["ok"])
        got = SK.find_place("Denver")
        check("only 0.1 degree is kept", got["place"]["lat"] == round(got["place"]["lat"], 1))


def t_place_pc_only_and_forget():
    fresh()
    code, out = SK.handle_post({"place": "Denver"}, here=False)
    check("the town cannot be set from the phone", code == 403 and SK.load()["place"] is None)
    code, out = SK.handle_post({"place": "Denver"}, here=True)
    check("the town is set from the PC", code == 200 and SK.load()["place"]["lat"] == 39.7,
          repr(out))
    check("the phone's view says the town is typed on the PC",
          SK.view(here=False)["place_detail"] == SK.PLACE_PHONE)
    check("the town never reaches the audit log",
          not any("Denver" in d or "39.7" in d or "-105" in d for _, d in AUDIT))
    code, out = SK.handle_post({"forget_place": True}, here=False)
    check("forgetting is at once, from either app", code == 200 and SK.load()["place"] is None)
    code, out = SK.handle_post({"show": True}, here=False)
    check("showing the sun and moon is at once, from either app, no card",
          code == 200 and SK.load()["show"] is True)
    code, _ = SK.handle_post({"show": "yes"}, here=True)
    check("show must be true or false", code == 400)
    code, _ = SK.handle_post({"show": True, "place": "x"}, here=True)
    check("one change at a time", code == 400)
    fresh()


def t_weather_source_cards():
    fresh()
    code, out = SK.request_weather("open_meteo", gate=APPROVE, tier_of=ASK, spawn=run_now)
    check("Open-Meteo needs a town first", code == 409)
    SK.handle_post({"place": "Denver"}, here=True)
    seen = []

    def gate(a, d, p):
        seen.append((a, d, p))
        return Verdict(False, "denied")
    code, out = SK.request_weather("open_meteo", gate=gate, tier_of=ASK, spawn=run_now)
    check("switching Open-Meteo on raises ONE card", code == 202 and len(seen) == 1)
    a, d, p = seen[0]
    check("the card is change_own_config, leaves this PC, and names the host",
          a == "change_own_config" and d["leaves_this_pc"] is True and d["to"] == SK.OPEN_METEO_HOST)
    check("the card names the exact numbers sent", "39.7, -105.0" in p and "nothing else" in p)
    check("a no leaves it off", SK.load()["weather"] == "off"
          and SK.view()["weather"]["last"]["outcome"] == "denied")
    code, out = SK.request_weather("open_meteo", gate=APPROVE, tier_of=ASK, spawn=run_now)
    check("a yes switches it on", SK.load()["weather"] == "open_meteo"
          and SK.load()["open_meteo_for"] == "39.7,-105.0")
    code, out = SK.request_weather("open_meteo", gate=lambda *a: Verdict(True, "approved", "auto"),
                                   tier_of=lambda a: "auto", spawn=run_now)
    check("already on: no second card", code == 200)
    SK.request_weather("off", spawn=run_now)
    code, out = SK.request_weather("open_meteo", gate=lambda *a: Verdict(True, None, "auto"),
                                   tier_of=lambda a: "auto", spawn=run_now)
    check("a card tier other than ask is refused, never a silent yes",
          code == 503 and SK.load()["weather"] == "off")
    # A waiting card, then another source chosen: withdrawn.
    held = []
    SK.request_weather("open_meteo", gate=APPROVE, tier_of=ASK, spawn=held.append)
    check("while the card waits, the status says so", SK.view()["weather"]["status"] == SK.WAITING)
    SK.request_weather("home_assistant", spawn=run_now)
    held[0]()
    check("choosing another source withdraws a waiting card",
          SK.load()["weather"] == "home_assistant"
          and SK.view()["weather"]["last"]["outcome"] == "withdrawn")
    # On for one position; a new town switches it off.
    SK.request_weather("open_meteo", gate=APPROVE, tier_of=ASK, spawn=run_now)
    code, out = SK.handle_post({"place": "London"}, here=True)
    check("a new town switches Open-Meteo off, and says why",
          SK.load()["weather"] == "off" and "switched off" in out["said"])
    # Approved after the town changed: refused.
    held = []
    SK.request_weather("open_meteo", gate=APPROVE, tier_of=ASK, spawn=held.append)
    SK._P_STATE["pending"].clear()          # as if a different app had moved the town
    SK._save(place={"name": "x", "lat": 10.0, "lon": 10.0})
    held[0]()
    check("a yes for an old position switches nothing on", SK.load()["weather"] == "off")
    check("home assistant and off need no card",
          SK.request_weather("home_assistant", gate=None, spawn=run_now)[0] == 200
          and SK.request_weather("off", spawn=run_now)[0] == 200)
    check("an unknown source is refused", SK.request_weather("brave")[0] == 400)
    fresh()


OM_ANSWER = json.dumps({"latitude": 39.7, "current": {"weather_code": 63, "cloud_cover": 90,
                                                      "wind_speed_10m": 7.0,
                                                      "wind_direction_10m": 270}}).encode()


def _clock(t):
    return lambda: t[0]


def t_open_meteo_reads():
    fresh()
    SK.handle_post({"place": "Denver"}, here=True)
    SK.request_weather("open_meteo", gate=APPROVE, tier_of=ASK, spawn=run_now)
    urls, t = [], [1000.0]

    def fetch(url):
        urls.append(url)
        return OM_ANSWER
    deps = SK.Deps(open_meteo_fetch=fetch, clock=_clock(t), spawn=run_now)
    SK.refresh(deps)
    check("one request", len(urls) == 1)
    check("it carries only the rounded position and four value names",
          urls[0] == ("https://api.open-meteo.com/v1/forecast?latitude=39.7&longitude=-105.0"
                      "&current=weather_code,cloud_cover,wind_speed_10m,wind_direction_10m"
                      "&wind_speed_unit=ms"), urls[0])
    now = SK.view()["weather"]["now"]
    check("moderate rain and heavy cloud become numbers",
          abs(now["rain"] - 0.6) < 1e-9 and abs(now["cloud"] - 0.9) < 1e-9, repr(now))
    check("a west wind blows toward the east: to the LEFT, facing south", now["dir"] == -1)
    check("7 m/s is half the wind scale", abs(now["wind"] - 0.5) < 1e-9)
    check("the status line says it in words", SK.view()["weather"]["status"] ==
          "Rain, windy, from Open-Meteo.", SK.view()["weather"]["status"])
    t[0] += 60
    SK.refresh(deps)
    check("not read again within REFRESH_S", len(urls) == 1)
    t[0] += SK.REFRESH_S
    SK.refresh(deps)
    check("read again after REFRESH_S", len(urls) == 2)

    def broken(url):
        raise TimeoutError("slow")
    deps2 = SK.Deps(open_meteo_fetch=broken, clock=_clock(t), spawn=run_now)
    t[0] += SK.REFRESH_S + 1
    SK.refresh(deps2)
    w = SK.view()["weather"]
    check("a failure is quiet: no weather drawn", w["now"] is None)
    check("and says why in plain words", "did not answer (TimeoutError)" in w["status"], w["status"])
    n = []
    deps3 = SK.Deps(open_meteo_fetch=lambda u: n.append(u) or OM_ANSWER, clock=_clock(t),
                    spawn=run_now)
    t[0] += 60
    SK.refresh(deps3)
    check("not retried within RETRY_S", n == [])
    t[0] += SK.RETRY_S
    SK.refresh(deps3)
    check("retried after RETRY_S", len(n) == 1 and SK.view()["weather"]["now"] is not None)
    with NoSocket():
        try:
            SK._default_open_meteo_fetch("https://example.com/v1/forecast?latitude=1")
            refused = False
        except ValueError:
            refused = True
    check("the real fetch refuses any other address, before any socket", refused)
    got, why = SK.parse_open_meteo(b"<html>", 40.0, 1.0)
    check("an answer that is not weather is refused, quietly", got is None and "not with" in why)
    fresh()


def t_home_assistant_reads():
    fresh()
    SK.handle_post({"place": "Denver"}, here=True)
    SK.request_weather("home_assistant", spawn=run_now)
    import os
    os.environ["JARVIS_HOME_URL"] = "http://192.168.1.20:8123"
    gates, t = [], [5000.0]

    def gate(a, d, p):
        gates.append(a)
        return Verdict(True, None, "auto")

    def home_fetch(q):
        return {"state": "snowy", "attributes": {"wind_speed": 36.0, "wind_speed_unit": "km/h",
                                                 "wind_bearing": 90}}
    deps = SK.Deps(gate=gate, tier_of=lambda a: "auto", home_fetch=home_fetch, clock=_clock(t),
                   home_ready=lambda: {"state": "on", "said": ""}, spawn=run_now)
    SK.refresh(deps)
    now = SK.view()["weather"]["now"]
    check("read through the gate as home_read", gates == ["home_read"])
    check("snow and wind become numbers", now and abs(now["snow"] - 0.6) < 1e-9
          and abs(now["wind"] - 10 / 14) < 1e-6, repr(now))
    check("an east wind blows toward the west: to the RIGHT, facing south", now["dir"] == 1)
    check("the status names Home Assistant", "from your Home Assistant" in
          SK.view()["weather"]["status"])
    SK._reset_for_tests()
    deps2 = SK.Deps(gate=gate, tier_of=lambda a: "ask", home_fetch=home_fetch, clock=_clock(t),
                    home_ready=lambda: {"state": "on", "said": ""}, spawn=run_now)
    gates.clear()
    SK.refresh(deps2)
    w = SK.view()["weather"]
    check("tier ask: not read, never a card, and it says why",
          gates == [] and w["now"] is None and "ask for a yes" in w["status"], w["status"])
    SK._reset_for_tests()
    deps2b = SK.Deps(gate=gate, tier_of=lambda a: "notify", home_fetch=home_fetch,
                     clock=_clock(t), home_ready=lambda: {"state": "on", "said": ""},
                     spawn=run_now)
    SK.refresh(deps2b)
    check("tier notify: not read either (a notice every 20 minutes would be noise)",
          gates == [] and SK.view()["weather"]["now"] is None)
    SK._reset_for_tests()
    deps3 = SK.Deps(gate=gate, tier_of=lambda a: "auto", home_fetch=home_fetch, clock=_clock(t),
                    home_ready=lambda: {"state": "off", "said": ""}, spawn=run_now)
    SK.refresh(deps3)
    check("not set up: says so", "not set up" in SK.view()["weather"]["status"])
    ready = SK._home_ready()
    check("readiness is the morning briefing's own answer (a dict with a state)",
          isinstance(ready, dict) and ready.get("state") in ("on", "off", "asks"))
    got, why = SK.parse_home({"ok": True, "states": [{"state": "exceptional", "attributes": "{}"}]},
                             40.0, 1.0)
    check("a condition Jarvis does not draw draws nothing", got is None and why)
    os.environ.pop("JARVIS_HOME_URL", None)
    fresh()


def t_lockdown_stops_the_weather():
    """Lockdown (jarvis_asks_first.py; security audit 2026-09-28 #2): no
    Open-Meteo fetch and no Home Assistant read while it is on, the weather
    already drawn is dropped, and it reads again once Lockdown is off."""
    fresh()
    SK.handle_post({"place": "Denver"}, here=True)
    SK.request_weather("open_meteo", gate=APPROVE, tier_of=ASK, spawn=run_now)
    urls, t, locked = [], [1000.0], {"on": False}

    def fetch(url):
        urls.append(url)
        return OM_ANSWER
    deps = SK.Deps(open_meteo_fetch=fetch, clock=_clock(t), spawn=run_now,
                   lockdown_on=lambda: locked["on"])
    SK.refresh(deps)
    check("before Lockdown: read once", len(urls) == 1 and SK.view()["weather"]["now"])
    locked["on"] = True
    t[0] += SK.REFRESH_S + 1
    SK.refresh(deps)
    w = SK.view()["weather"]
    check("Lockdown on: no fetch, and the drawn weather is dropped",
          len(urls) == 1 and w["now"] is None, (len(urls), w["now"]))
    check("... it says why, with no promise to try again",
          "Lockdown is on" in w["status"] and "tries again" not in w["status"], w["status"])
    with NoSocket():
        got, why = SK.read_open_meteo(SK.load()["place"], SK.load(), deps)
    check("the Open-Meteo read itself refuses under Lockdown, before any socket",
          got is None and why == SK.LOCKDOWN_WHY and len(urls) == 1)
    deps_bad = SK.Deps(open_meteo_fetch=fetch, clock=_clock(t), spawn=run_now,
                       lockdown_on=lambda: (_ for _ in ()).throw(OSError("unreadable")))
    SK.refresh(deps_bad)
    check("a Lockdown check that cannot be read counts as on", len(urls) == 1)
    locked["on"] = False
    t[0] += 1
    SK.refresh(deps)
    check("Lockdown off: read again at once, no retry wait",
          len(urls) == 2 and SK.view()["weather"]["now"] is not None, len(urls))

    gates = []

    def gate(a, d, p):
        gates.append(a)
        return Verdict(True, None, "auto")
    hd = SK.Deps(gate=gate, tier_of=lambda a: "auto", home_fetch=lambda q: {},
                 clock=_clock(t), home_ready=lambda: {"state": "on", "said": ""},
                 spawn=run_now, lockdown_on=lambda: True)
    got, why = SK.read_home(SK.load()["place"], hd)
    check("Home Assistant is not read under Lockdown either, and Lockdown is the reason",
          got is None and why == SK.LOCKDOWN_WHY and gates == [], why)
    fresh()


def t_get_reads_only_when_asked():
    fresh()
    SK.handle_post({"place": "Denver"}, here=True)
    SK.request_weather("open_meteo", gate=APPROVE, tier_of=ASK, spawn=run_now)
    n = []
    deps = SK.Deps(open_meteo_fetch=lambda u: n.append(u) or OM_ANSWER, spawn=run_now)
    code, v = SK.handle_get(here=True, deps=deps)
    check("GET starts a read when none is fresh", code == 200 and len(n) == 1)
    SK.handle_get(here=True, deps=deps)
    check("and not again straight after", len(n) == 1)
    SK.request_weather("off", spawn=run_now)
    SK.handle_get(here=True, deps=deps)
    check("off: nothing is read, and the old weather is gone",
          len(n) == 1 and SK.view()["weather"]["now"] is None)
    fresh()


def t_install_wraps_the_route():
    fresh()
    hits = []

    class H:
        def __init__(self, peer="127.0.0.1"):
            self.sent = None
            self._body = b"{}"
            self.client_address = (peer, 5555)

        def do_GET(self):
            hits.append("get0")

        def do_POST(self):
            hits.append("post0")

        def _send(self, code, out):
            self.sent = (code, out)
            return self.sent

    line = SK.install(H, origin_ok=lambda self: True, token_ok=lambda self: True,
                      read_body=lambda self: self._body)
    check("install returns a banner line", "Sun, moon and weather" in line)
    h = H()
    h.path = "/api/sky"
    h.do_GET()
    check("GET /api/sky is answered here", h.sent[0] == 200 and h.sent[1]["available"])
    h2 = H()
    h2.path = "/api/other"
    h2.do_GET()
    h2.do_POST()
    check("other routes pass through", hits == ["get0", "post0"])
    real = SK._from_this_pc
    SK._from_this_pc = lambda peer, local: peer == "127.0.0.1"
    try:
        h3 = H(peer="100.101.102.103")
        h3.path = "/api/sky"
        h3._body = json.dumps({"place": "Denver"}).encode()
        h3.do_POST()
        check("POST a town from another device: 403", h3.sent[0] == 403)
        h4 = H()
        h4.path = "/api/sky"
        h4._body = json.dumps({"place": "Denver"}).encode()
        h4.do_POST()
        check("POST a town from this PC: 200", h4.sent[0] == 200)
    finally:
        SK._from_this_pc = real

    fresh()


def _rehearse():
    order = _stack.order()
    if "sky.patch" not in order:
        return False, "sky.patch is not in apply-patches.ps1's list", None, None
    before_list = order[:order.index("sky.patch")]
    patch = (HERE / "sky.patch").read_text(encoding="utf-8")
    text, log = _stack.stand_in("jarvis_hud.py", before_list)
    if text is None:
        return False, "; ".join(log), None, None
    git = shutil.which("git")
    d = Path(tempfile.mkdtemp(prefix="jarvis-sky-patch-"))
    try:
        (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
        (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
        r = subprocess.run([git, "apply", "--include", "jarvis_hud.py", "p.patch"], cwd=d,
                           capture_output=True, text=True)
        if r.returncode != 0:
            return False, r.stderr, None, None
        after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        r = subprocess.run([git, "apply", "-R", "--include", "jarvis_hud.py", "p.patch"],
                           cwd=d, capture_output=True, text=True)
        if r.returncode != 0 or (d / "jarvis_hud.py").read_text(encoding="utf-8") != text:
            return False, f"does not reverse cleanly: {r.stderr}", None, None
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return True, "", text, after


def t_the_patch():
    if not shutil.which("git"):
        return check("SKIP - git is not installed", True)
    ok, why, before, after = _rehearse()
    check("sky.patch applies to what the earlier patches wrote, and reverses", ok, why)
    if not ok:
        return
    i = after.index("# sky.patch")
    j = after.index("# Before the main socket", i)
    blk = after[i:j]
    check("the added block passes origin_ok/token_ok/read_body into jarvis_sky.install",
          "import jarvis_sky" in blk and "origin_ok=_origin_ok" in blk
          and "token_ok=_token_ok" in blk and "read_body=_read_body" in blk)
    try:
        compile("def f(self, bind, Handler):\n" + blk, "<patched block>", "exec")
        check("the patched block compiles", True)
    except SyntaxError as exc:
        check("the patched block compiles", False, str(exc))
    import _where
    check("both modules are shipped", "jarvis_sky.py" in _where.SHIPPED
          and "jarvis_sky_places.py" in _where.SHIPPED)


if __name__ == "__main__":
    for fn in (t_off_by_default, t_find_place_offline, t_place_pc_only_and_forget,
               t_weather_source_cards, t_open_meteo_reads, t_home_assistant_reads,
               t_lockdown_stops_the_weather, t_get_reads_only_when_asked, t_install_wraps_the_route, t_the_patch):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
