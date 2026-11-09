"""test_wifi_reconnect.py - the auto Wi-Fi reconnect (2026-11-08).

    python3 backend/test_wifi_reconnect.py

WHAT THIS IS FOR. The owner asked for a feature that "defaults on but can be
changed in settings or chat with jarvis, that jarvis if its running on a desktop
and the desktop has lost internet connection, that it will tell the desktop to
try to reconnect to password protected networks (that have already been
connected to in the past on that desktop) every 2 hours on its own if its still
offline."

This suite proves the promises in `backend/jarvis_wifi.py` without touching the
live connection: every Windows call is a `FakeLocal`, every network probe is a
fake, and the state file is this suite's own temp file.

  * ON by default; a damaged file fails SAFE (off); OFF is immediate and stops
    every path; ON restores the default (cardless both ways, and why).
  * the 2-hour spacing: due, not due, and a 3-hour sleep gap is one check.
  * the offline gate: ONLINE does nothing; a fine Wi-Fi with a broken VPN/upstream
    is `upstream_down` and does NOT touch Wi-Fi; only a broken Wi-Fi link acts.
  * saved-profile-only: OPEN profiles are never candidates, an unreadable profile
    is kept out, only `secure` profiles are tried, the current one first, and at
    most MAX_PROFILES_PER_CYCLE in one cycle (bounded, no hammering).
  * no key and no name: no `key=clear`, no export, no `netsh wlan disconnect`,
    and the state file never contains a network name.
  * idle-only: a streaming answer / standby / running task SKIPS the cycle and
    says so, and the 2-hour clock still moves.
  * dry run: it logs what it WOULD do and never calls Windows' connect.
  * the route: GET/POST the switch, PC-only, one setting only, honest failures.
  * the deterministic chat/Live sentences (jarvis_quick.match) resolve to this
    module's intents, and a MODEL ANSWER CAN NEVER TOGGLE IT (no model tool; the
    route refuses another device).
  * the source pins: the ONE real netsh connect call is inside `_RealLocal`, and
    nothing in the module prints or reads a key.

Hermetic: its own temp OPENJARVIS_HOME / OPENJARVIS_CONFIG_DIR, and it refuses to
run unless those point inside its own temp folder. No model, no network, no card,
no live backend, no Windows call.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
# `jarvis_quick.py` is an owner-only file carried as the published base, not a
# SHIPPED module; under run_suites it is already importable, and a direct run
# gets it from the base folder explicitly.
if not (HERE / "jarvis_quick.py").exists():
    sys.path.insert(0, str(REPO / "jarvis-backend"))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-wifi-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_SCHEDULE_DB"] = str(_TMP / "schedule.db")
_HOME = _TMP / "home"
_HOME.mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_HOME"] = str(_HOME)
os.environ["JARVIS_HOME"] = str(_HOME)
os.environ.pop("JARVIS_WIFI_DRY_RUN", None)

import jarvis_quick as Q  # noqa: E402
import jarvis_wifi as W  # noqa: E402

PASSED, FAILED = [], []


def check(name: str, ok, detail=None) -> None:
    if ok:
        PASSED.append(name)
        print(f"ok    {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}" + (f" | {detail!r}" if detail is not None else ""))


def _require_own_home() -> None:
    home = os.environ.get("OPENJARVIS_HOME") or ""
    try:
        same = bool(home) and Path(home).resolve() == _HOME.resolve()
    except OSError:
        same = False
    if not same:
        print("FAIL  the suite's OPENJARVIS_HOME is not its own temp folder")
        sys.exit(1)
    if not str(W.state_path()).startswith(str(_TMP)):
        print("FAIL  jarvis_wifi.state_path() is outside this suite's temp folder")
        sys.exit(1)


def _reset(**doc) -> None:
    """Write the state file (or remove it) before a case."""
    path = W.state_path()
    if not doc:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _doc() -> dict:
    try:
        return json.loads(W.state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


class FakeLocal(W.Local):
    """Every Windows read/write the module needs, recorded and never real."""

    def __init__(self, rows=None, facts=None, connect_result=(True, "connected"),
                 after_connect=None):
        self.rows = list(rows or [])
        self.facts = dict(facts or {"adapter": True, "up": True,
                                    "profile": "Home", "ipv4": "Internet"})
        self.connect_result = connect_result
        self.after_connect = dict(after_connect or {})
        self.connects = []
        self.profile_reads = 0

    def profiles(self):
        self.profile_reads += 1
        return list(self.rows)

    def connection(self):
        return dict(self.facts)

    def connect(self, name):
        self.connects.append(name)
        self.facts.update(self.after_connect)
        return self.connect_result


def _profiles(*specs):
    return [{"name": name, "secure": secure, "auto": auto}
            for name, secure, auto in specs]


def _match(sentence: str):
    intent = Q.match(sentence)
    return None if intent is None else intent.name


# --------------------------------------------------------------------------
#   1. The switch: ON by default, fails SAFE, OFF at once
# --------------------------------------------------------------------------

def the_switch() -> None:
    _reset()
    check("a missing file is the shipped default ON", W.enabled() is True)
    st = W.state()
    check("the state says ON and known", st["enabled"] is True and st["known"] is True)
    check("the state carries the PC's own words",
          isinstance(st["words"], str) and "2 hours" in st["words"])
    check("the state counts saved profiles without naming one",
          "profiles" not in st or "saved" in json.dumps(st).lower())

    _reset(enabled=False)
    check("a saved OFF is read back", W.enabled() is False)
    check("the OFF words say Jarvis never touches the choice",
          "never touches this PC" in W.state_words())

    W.state_path().write_text("{not json", encoding="utf-8")
    check("a damaged file fails SAFE (off)", W.enabled() is False)
    check("a damaged file is not reported as known", W.state()["known"] is False)

    _reset()
    off = W.set_enabled(False)
    check("OFF changes at once and says so", off["changed"] is True
          and off["enabled"] is False and "off now" in off["words"])
    again = W.set_enabled(False)
    check("a repeated OFF says nothing was changed",
          again["changed"] is False and "already off" in again["words"])
    on = W.set_enabled(True)
    check("ON restores the shipped default cardless",
          on["changed"] is True and on["enabled"] is True
          and "on now" in on["words"] and "card" not in on["words"].lower())
    check("the state file holds the switch",
          _doc().get("enabled") is True)
    try:
        W.set_enabled("yes")
        check("a bad value is refused", False)
    except ValueError:
        check("a bad value is refused", True)


# --------------------------------------------------------------------------
#   2. The 2-hour spacing
# --------------------------------------------------------------------------

def the_spacing() -> None:
    now = 1_800_000_000.0
    _reset(enabled=True)
    check("a file with no last check is due", W.due(now) is True)
    _reset(enabled=True, last_check_at=now - 60)
    check("a check one minute old is not due", W.due(now) is False)
    _reset(enabled=True, last_check_at=now - W.CHECK_INTERVAL_S + 1)
    check("one second before two hours is not due", W.due(now) is False)
    _reset(enabled=True, last_check_at=now - W.CHECK_INTERVAL_S)
    check("exactly two hours is due", W.due(now) is True)
    _reset(enabled=True, last_check_at=now - 3 * 60 * 60)
    check("a 3-hour sleep gap is ONE due check, not a burst", W.due(now) is True)
    check("the interval is the owner's 2 hours", W.CHECK_INTERVAL_S == 7200)


# --------------------------------------------------------------------------
#   3. The offline gate: no internet is not the same as no Wi-Fi
# --------------------------------------------------------------------------

def the_diagnosis() -> None:
    def diag(rows=None, facts=None, reachable=False):
        fake = FakeLocal(rows=rows, facts=facts)
        return W.diagnose(local=fake, probe=lambda: reachable)

    got = diag(facts={"adapter": False, "up": False, "profile": "", "ipv4": ""})
    check("no adapter is reported, never acted on",
          got["class"] == W.CLASS_NO_ADAPTER and got["wifi_broken"] is False)
    got = diag(facts={"adapter": True, "up": False, "profile": "", "ipv4": ""})
    check("a disconnected Wi-Fi is the one Wi-Fi-broken case",
          got["class"] == W.CLASS_WIFI_DISCONNECTED and got["wifi_broken"] is True)
    got = diag(facts={"adapter": True, "up": True, "profile": "Home",
                      "ipv4": "NoTraffic"})
    check("connected but no internet is Wi-Fi-broken",
          got["class"] == W.CLASS_WIFI_NO_INTERNET and got["wifi_broken"] is True)
    got = diag(reachable=True)
    check("a working internet is online and untouched",
          got["class"] == W.CLASS_ONLINE and got["wifi_broken"] is False)
    got = diag(reachable=False)
    check("Wi-Fi fine + real probe failed is UPSTREAM, and Wi-Fi is NOT touched",
          got["class"] == W.CLASS_UPSTREAM and got["wifi_broken"] is False)
    check("the upstream words say it is not the Wi-Fi",
          "not the Wi-Fi" in got["words"])


# --------------------------------------------------------------------------
#   4. Reading the saved store; only saved password-protected profiles
# --------------------------------------------------------------------------

def the_saved_store() -> None:
    listed = ("\r\nProfiles on interface Wi-Fi 2:\r\n\r\n"
              "User profiles\r\n"
              "-------------\r\n"
              "    All User Profile     : Home\r\n"
              "    All User Profile     : Phone\r\n")
    rows = W._parse_profiles(listed)
    check("the real netsh list shape is parsed",
          [r["name"] for r in rows] == ["Home", "Phone"])
    check("the list step reads no security field", "secure" not in rows[0])

    secure_detail = (
        "Profile Home on interface Wi-Fi 2:\r\n"
        "    Network type            : Infrastructure\r\n"
        "    Security key            : Present\r\n"
        "    Connection mode         : Connect automatically\r\n"
        "    Authentication          : WPA2-Personal\r\n"
        "    Cipher                  : CCMP\r\n")
    open_detail = (
        "Profile Cafe on interface Wi-Fi 2:\r\n"
        "    Connection mode         : Connect automatically\r\n"
        "    Authentication          : Open\r\n")
    facts = W._parse_profile_detail(secure_detail)
    check("a password-protected profile is secure and auto",
          facts["secure"] is True and facts["auto"] is True)
    facts = W._parse_profile_detail(open_detail)
    check("an OPEN profile is never secure", facts["secure"] is False)
    facts = W._parse_profile_detail(
        "Profile X\r\n    Authentication          : WPA2-Personal\r\n")
    check("an authentication alone (no stored key) is not secure",
          facts["secure"] is False)

    rows = [{"name": n, "secure": s, "auto": True, "id": i}
            for i, (n, s) in enumerate(
                [("Home", True), ("Cafe", False), ("Phone", True)], start=1)]
    usable = W._usable(rows)
    check("only password-protected rows are usable",
          [r["name"] for r in usable] == ["Home", "Phone"])
    order = W.candidate_order(rows, current="Phone")
    check("the network in use is tried first, then the rest",
          [r["name"] for r in order] == ["Phone", "Home"])
    planned = W.plan(rows, current="Phone")
    blob = json.dumps(planned)
    check("the plan names profiles only by their saved position",
          "Home" not in blob and "Phone" not in blob
          and planned[0]["current"] is True)
    check("the plan is bounded", len(W.plan(
        [{"name": f"N{i}", "secure": True, "auto": True, "id": i}
         for i in range(1, 9)])) == W.MAX_PROFILES_PER_CYCLE)


# --------------------------------------------------------------------------
#   5. One bounded 2-hourly check
# --------------------------------------------------------------------------

def the_check() -> None:
    now = 1_800_000_000.0
    _reset(enabled=False)
    fake = FakeLocal(rows=_profiles(("Home", True, True)),
                     facts={"adapter": True, "up": False, "profile": "",
                            "ipv4": ""})
    got = W.check_once(now=now, local=fake, probe=lambda: False)
    check("OFF stops the check before anything is read",
          got["ran"] is False and fake.profile_reads == 0 and not fake.connects)

    _reset(enabled=True, last_check_at=now - 60)
    fake = FakeLocal(rows=_profiles(("Home", True, True)),
                     facts={"adapter": True, "up": False, "profile": "",
                            "ipv4": ""})
    got = W.check_once(now=now, local=fake, probe=lambda: False)
    check("inside the two hours nothing runs", got["ran"] is False)

    _reset(enabled=True)
    fake = FakeLocal(facts={"adapter": True, "up": True, "profile": "Home",
                            "ipv4": "Internet"})
    got = W.check_once(now=now, local=fake, probe=lambda: True)
    check("online does nothing and says so",
          got["class"] == W.CLASS_ONLINE and not fake.connects)
    check("the online check still moves the clock",
          _doc().get("last_check_at") == now)

    _reset(enabled=True)
    fake = FakeLocal(rows=_profiles(("Home", True, True)),
                     facts={"adapter": True, "up": True, "profile": "Home",
                            "ipv4": "Internet"})
    got = W.check_once(now=now, local=fake, probe=lambda: False)
    check("Wi-Fi fine + probe failed: upstream, and the Wi-Fi is NOT reconnected",
          got["class"] == W.CLASS_UPSTREAM and not fake.connects)

    _reset(enabled=True)
    fake = FakeLocal(rows=_profiles(("Home", True, True), ("Phone", True, True)),
                     facts={"adapter": True, "up": False, "profile": "",
                            "ipv4": ""},
                     after_connect={"up": True, "ipv4": "Internet",
                                    "profile": "Home"})
    got = W.check_once(now=now, local=fake, probe=lambda: True,
                       sleep=lambda _s: None)
    check("a disconnected Wi-Fi is reconnected using the saved profile",
          got["reconnected"] is True and fake.connects == ["Home"])
    check("the reconnected words name no network",
          "Home" not in got["words"] and "saved profile" not in got["words"].lower())
    check("the state file keeps the calm record",
          str(_doc().get("last", {}).get("words") or "").startswith("The desktop's Wi-Fi"))

    _reset(enabled=True)
    fake = FakeLocal(rows=[], facts={"adapter": True, "up": False,
                                     "profile": "", "ipv4": ""})
    got = W.check_once(now=now, local=fake, probe=lambda: False)
    check("a PC with no saved password-protected profile says so and does nothing",
          got["class"] == "no_saved_profiles" and not fake.connects
          and "no saved" in got["words"].lower())

    _reset(enabled=True)
    fake = FakeLocal(rows=_profiles(("Home", True, True)),
                     facts={"adapter": True, "up": False, "profile": "",
                            "ipv4": ""}, connect_result=(True, "ok"))
    got = W.check_once(now=now, local=fake, probe=lambda: False,
                       sleep=lambda _s: None)
    check("a link that never comes back is bounded to one saved profile",
          got["reconnected"] is False and len(fake.connects) == 1)
    check("the failed attempt says it will try again in 2 hours",
          "2 hours" in got["words"])

    _reset(enabled=True)
    fake = FakeLocal(rows=_profiles(("Home", True, True)),
                     facts={"adapter": True, "up": False, "profile": "",
                            "ipv4": ""})
    got = W.check_once(now=now, local=fake, probe=lambda: False,
                       busy=lambda: "a task is running")
    check("a busy moment SKIPS the cycle and never touches the network",
          got["class"] == "skipped" and not fake.connects)
    check("a skipped cycle still moves the two-hour clock",
          _doc().get("last_check_at") == now)

    _reset(enabled=True)
    fake = FakeLocal(rows=_profiles(("Home", True, True)),
                     facts={"adapter": True, "up": False, "profile": "",
                            "ipv4": ""})
    os.environ["JARVIS_WIFI_DRY_RUN"] = "1"
    try:
        got = W.check_once(now=now, local=fake, probe=lambda: False)
        check("dry run never calls Windows' connect",
              not fake.connects and got["dry_run"] is True)
        check("dry run says what it would do, without a network name",
              "Dry run" in got["words"] and "Home" not in got["words"])
        check("dry run is written down as a dry run",
              _doc().get("last", {}).get("dry_run") is True)
    finally:
        os.environ.pop("JARVIS_WIFI_DRY_RUN", None)

    # The first evidence of a real attempt is a durable log line too, not only
    # the state file: the project's own audit log gets one line per cycle.
    _reset(enabled=True)
    fake = FakeLocal(rows=_profiles(("Home", True, True)),
                     facts={"adapter": True, "up": False, "profile": "",
                            "ipv4": ""})
    audited = []
    original_audit = W._audit
    W._audit = lambda event, detail: audited.append((event, detail))  # type: ignore[assignment]
    try:
        W.check_once(now=now, local=fake, probe=lambda: False,
                     sleep=lambda _s: None)
    finally:
        W._audit = original_audit  # type: ignore[assignment]
    lines = [e for e, _d in audited if e == "wifi_reconnect_attempt"]
    check("every real attempt writes one durable log line", len(lines) == 1)
    check("that log line carries counts and no name",
          audited and "Home" not in str(audited))

    # The clock is the file's: a second call at the same instant is not due.
    _reset(enabled=True, last_check_at=now)
    fake = FakeLocal(rows=_profiles(("Home", True, True)),
                     facts={"adapter": True, "up": False, "profile": "",
                            "ipv4": ""})
    got = W.check_once(now=now, local=fake, probe=lambda: False)
    check("the 2-hour spacing holds across calls", got["ran"] is False)


# --------------------------------------------------------------------------
#   6. The route: one switch, PC-only, honest failures
# --------------------------------------------------------------------------

def _fake_handler(route: str, *, body: bytes = b"", peer: str = "127.0.0.1",
                  origin: bool = True, token: bool = True):
    """A Handler double for install(): records what _send was told."""

    class Handler:
        do_GET = lambda self: None        # replaced by install()
        do_POST = lambda self: None

        def __init__(self):
            self.sent = []
            self.path = route
            self.client_address = (peer, 55555)
            if body:
                self.rfile = __import__("io").BytesIO(body)

        def _send(self, code, out):
            self.sent.append((code, out))
            return code

    def origin_ok(_self):
        return origin

    def token_ok(_self):
        return token

    def read_body(self):
        return getattr(self, "rfile", __import__("io").BytesIO(b"")).read()

    return Handler, origin_ok, token_ok, read_body


def the_route() -> None:
    _reset()
    code, out = W.handle_get(W.ROUTE_PATH)
    check("GET returns the switch", code == 200 and out["enabled"] is True)
    code, out = W.handle_get("/api/other")
    check("GET refuses another route", code == 404)
    code, out = W.handle_get(W.ROUTE_PATH, peer="192.168.1.20")
    check("the switch is PC-only", code == 403 and "desktop" in json.dumps(out))
    code, out = W.handle_post(W.ROUTE_PATH, {"enabled": False}, peer="::1")
    check("POST turns it off from this PC", code == 200 and out["enabled"] is False)
    code, out = W.handle_post(W.ROUTE_PATH, {"enabled": "no"})
    check("POST refuses a bad value", code == 400)
    code, out = W.handle_post(W.ROUTE_PATH, {"enabled": True, "x": 1})
    check("POST refuses an unknown setting", code == 400)
    code, out = W.handle_post(W.ROUTE_PATH, "nope")   # type: ignore[arg-type]
    check("POST refuses a non-object body", code == 400)

    _reset(enabled=False)
    Handler, origin_ok, token_ok, read_body = _fake_handler(W.ROUTE_PATH)
    W.install(Handler, origin_ok=origin_ok, token_ok=token_ok,
              read_body=read_body)
    # The wrapped GET answers its own route through _send.
    fake = Handler()
    fake.do_GET()
    check("install() wraps the route and answers from the state file",
          fake.sent and fake.sent[-1][0] == 200)

    Handler2, o2, t2, r2 = _fake_handler("/api/other")
    W.install(Handler2, origin_ok=o2, token_ok=t2, read_body=r2)
    fake = Handler2()
    check("another route is delegated untouched", fake.do_GET() is None)

    Handler3, o3, t3, r3 = _fake_handler(W.ROUTE_PATH, origin=False)
    W.install(Handler3, origin_ok=o3, token_ok=t3, read_body=r3)
    fake = Handler3()
    fake.do_GET()
    check("a cross-origin read is refused", fake.sent[-1][0] == 403)


# --------------------------------------------------------------------------
#   7. The watcher is armed only by a real install, and stops cleanly
# --------------------------------------------------------------------------

def the_watcher() -> None:
    _reset(enabled=True, last_check_at=0)
    banner = W.watch_start()
    check("the watcher arms with a banner", "armed" in banner)
    check("the watcher thread is alive and named",
          W._WATCH["thread"] is not None
          and W._WATCH["thread"].is_alive())
    check("stopping the watcher works", W.watch_stop() is True)

    # install() with a fake handler must NOT arm it (installing a route must
    # never start background work), and dry run must not arm it either.
    W.watch_stop()
    Handler, origin_ok, token_ok, read_body = _fake_handler(W.ROUTE_PATH)
    line = W.install(Handler, origin_ok=origin_ok, token_ok=token_ok,
                     read_body=read_body)
    check("a fake handler install leaves the watcher off",
          W._WATCH["thread"] is None or not W._WATCH["thread"].is_alive())
    check("and the banner says so", "NOT armed" in line or "dry run" in line)


# --------------------------------------------------------------------------
#   8. The deterministic chat/Live sentences, never the model
# --------------------------------------------------------------------------

def the_chat_sentences() -> None:
    cases = [
        ("is the auto wi-fi reconnect on?", "self_wifi_reconnect"),
        ("is the automatic WiFi reconnect enabled?", "self_wifi_reconnect"),
        ("turn off the auto wi-fi reconnect", "wifi_reconnect_set"),
        ("disable the automatic wifi reconnect", "wifi_reconnect_set"),
        ("turn on the auto wi-fi reconnect", "wifi_reconnect_set"),
        ("what does the wi-fi reconnect do?", "wifi_reconnect_about"),
        ("what is the automatic wifi reconnect?", "wifi_reconnect_about"),
        ("when will it try the wi-fi again?", "wifi_reconnect_when"),
        ("when is the next wi-fi reconnect check?", "wifi_reconnect_when"),
        ("when will jarvis try to reconnect to the wi-fi?", "wifi_reconnect_when"),
    ]
    for sentence, want in cases:
        got = _match(sentence)
        check(f"chat: {sentence!r} -> {want}", got == want, got)
    check("an unrelated sentence is not claimed",
          _match("turn off the kitchen light") != "wifi_reconnect_set")
    check("a plain network question is not claimed",
          _match("what wifi am I on?") is None,
          _match("what wifi am I on?"))

    _reset(enabled=True)
    state_intent = Q.match("is the auto wi-fi reconnect on?")
    check("the state sentence resolves to a read-only intent",
          state_intent is not None and state_intent.name == "self_wifi_reconnect")
    on_intent = Q.match("turn off the auto wi-fi reconnect")
    check("the change sentence carries its action",
          on_intent is not None and on_intent.f.get("on") is False)


# --------------------------------------------------------------------------
#   9. Source pins: one real connect call, no key, no name, no disconnect
# --------------------------------------------------------------------------

def the_source_pins() -> None:
    """The real Windows surface, exercised through its own function.

    No test here may read the module's source text (tools/check_no_source_pins.py),
    so every promise is proved by CALLING the code with an injected runner:

      * the real store read runs only `netsh wlan show ...` - never an export,
        never a plaintext key, never a disconnect;
      * the ONE real connect runs exactly `netsh wlan connect name=<saved>` and
        nothing else;
      * a fake-driven check spawns no program at all; and
      * the rows this module keeps carry only the four documented fields -
        a key or a password has nowhere to go.
    """
    original = W._run_argv
    calls = []

    def recorder(argv, timeout=15.0):
        calls.append([str(a) for a in argv])
        if "profiles" in argv:
            return 0, ("\r\nUser profiles\r\n------------\r\n"
                       "    All User Profile     : Home\r\n")
        return 0, ("Profile Home on interface Wi-Fi 2:\r\n"
                   "    Security key            : Present\r\n"
                   "    Connection mode         : Connect automatically\r\n"
                   "    Authentication          : WPA2-Personal\r\n")

    W._run_argv = recorder  # type: ignore[assignment]
    try:
        rows = W._RealLocal().profiles()
        ok, _detail = W._RealLocal().connect("Home")
    finally:
        W._run_argv = original  # type: ignore[assignment]
    flat = [arg for call in calls for arg in call]
    show_calls = [c for c in calls if c[:3] == ["netsh", "wlan", "show"]]
    check("the real store read asks Windows only for the profile list/detail",
          show_calls and len(show_calls) == len(calls) - 1
          and all(c[:4] in (["netsh", "wlan", "show", "profiles"],
                            ["netsh", "wlan", "show", "profile"])
                  for c in show_calls))
    check("the real store read never exports and never asks for a key",
          not any("export" in a for a in flat)
          and not any("key=clear" in a for a in flat)
          and not any("keyMaterial" in a for a in flat))
    check("never a disconnect: the only write is the one connect",
          not any("disconnect" in a for a in flat)
          and calls[-1] == ["netsh", "wlan", "connect", "name=Home"])
    check("the real connect is reported by its exit code", ok is True)
    check("the profile rows carry four documented fields and nothing else",
          rows and set(rows[0]) == {"name", "secure", "auto"}
          and rows[0]["secure"] is True)

    # A module-level read-only field set: `profiles()` never invents a key field.
    check("the saved-profile rows this module keeps have no key field",
          set(W._parse_profiles(
              "    All User Profile     : Home\n")[0]) == {"name"}
          and set(W._parse_profile_detail(
              "    Security key            : Present\n"
              "    Authentication          : WPA2-Personal\n")) ==
          {"secure", "auto", "authentication"})

    # A check with the injected fake must never reach a real program.
    _reset(enabled=True)
    calls[:] = []
    W._run_argv = recorder  # type: ignore[assignment]
    try:
        fake = FakeLocal(rows=_profiles(("Home", True, True)),
                         facts={"adapter": True, "up": False, "profile": "",
                                "ipv4": ""})
        W.check_once(now=1_800_000_000.0, local=fake, probe=lambda: False,
                     sleep=lambda _s: None)
    finally:
        W._run_argv = original  # type: ignore[assignment]
    check("a fake-driven check spawns no program at all", calls == [])


# --------------------------------------------------------------------------
#   main
# --------------------------------------------------------------------------

def main() -> int:
    _require_own_home()
    for name, fn in [
        ("the switch", the_switch),
        ("the spacing", the_spacing),
        ("the diagnosis", the_diagnosis),
        ("the saved store", the_saved_store),
        ("one bounded check", the_check),
        ("the route", the_route),
        ("the watcher", the_watcher),
        ("the chat sentences", the_chat_sentences),
        ("the source pins", the_source_pins),
    ]:
        print(f"\n-- {name} --")
        try:
            fn()
        except Exception:
            traceback.print_exc()
            FAILED.append(name)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    code = main()
    try:
        shutil.rmtree(_TMP, ignore_errors=True)
    except Exception:
        pass
    sys.exit(code)
