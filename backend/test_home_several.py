"""Several smart-home devices on ONE approval card.

    python3 test_home_several.py

The owner's decision of 2026-09-25, after the creativity audit (CLAUDE.md;
docs/CREATIVITY-AUDIT-2026-09-25.md, plan item 9): "turn off the kitchen,
hall and bedroom lights" is one card, every device listed in full; locks,
alarms, doors and covers always get a card of their own; one decision about
a fully listed set, never a standing permission. What it proves, with no
Home Assistant anywhere (the requests go to a recorder, never a socket):

  - jarvis_home.plan_services: one request per device, the same service and
    data on each, every one printed on the card, opening no socket; one
    device is exactly plan_service; repeats counted once;
  - at most MAX_GROUP devices - a longer list is refused, never cut;
  - never grouped: locks, alarms, covers, valves, sirens, cameras, scripts,
    scenes, automations, buttons, and anything whose id says door, gate,
    garage, lock or alarm - and never a `data` that names its own target;
  - run(): only with approved=True; exactly the listed requests, in the
    card's order; a device that fails does not stop the others; a plan whose
    requests were changed after it was made sends NOTHING (the digest);
  - the chat loop: one home_control call naming three lights raises ONE
    card, counted once toward the five-cards limit, and after a yes exactly
    those three are sent; a denied card sends nothing; a set with a lock in
    it, or too many devices, is refused before any card.
"""
import json
import os
import socket
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_home.py", "jarvis_agent.py", "jarvis_local_http.py")
sys.path.append(str(HERE / "rebuilt"))
import jarvis_home as H  # noqa: E402
import jarvis_agent as AG  # noqa: E402
from test_agent import NoRealIO, scripted_stream, answer_text  # noqa: E402

FAILED, PASSED = [], []

URL = "https://ha.local:8123"
LIGHTS = ["light.kitchen", "light.hall", "light.bedroom"]


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Env:
    """JARVIS_HOME_URL / JARVIS_HOME_TOKEN for one block. The token is a
    plain word, nothing shaped like a real one."""

    def __init__(self, url=URL, token="not-a-token"):
        self.want = {H.URL_ENV: url, H.TOKEN_ENV: token}

    def __enter__(self):
        self.saved = {k: os.environ.get(k) for k in self.want}
        for k, v in self.want.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


class NoNetwork:
    def __enter__(self):
        self.real = socket.socket.connect

        def boom(*a, **k):
            raise AssertionError("a socket was opened")
        socket.socket.connect = boom
        return self

    def __exit__(self, *a):
        socket.socket.connect = self.real
        return False


class Recorder:
    """Stands in for jarvis_home._default_fetch: records every request that
    would have been sent, and answers like Home Assistant."""

    def __init__(self, fail=()):
        self.sent, self.fail = [], set(fail)

    def __call__(self, q):
        self.sent.append((q.method, q.url, dict(q.body or {})))
        if q.entity_id in self.fail:
            raise TimeoutError("no answer")
        return [{"entity_id": q.entity_id, "state": "off"}]

    def __enter__(self):
        self.real = H._default_fetch
        H._default_fetch = self
        return self

    def __exit__(self, *a):
        H._default_fetch = self.real
        return False


# --------------------------------------------------------------------------
#   The plan and the card
# --------------------------------------------------------------------------

def t_one_card_lists_every_device():
    with Env(), NoNetwork():
        p = H.plan_services("light", "turn_off", LIGHTS)
        text = H.describe(p)
    check("three lights: three requests, one per device, in the order given",
          [q.entity_id for q in p.queries] == LIGHTS and not p.reason_empty, p.reason_empty)
    check("... all the same service", all(
        q.url == f"{URL}/api/services/light/turn_off" and q.method == "POST"
        for q in p.queries))
    check("... each body names its own device and nothing else",
          [q.body for q in p.queries] == [{"entity_id": e} for e in LIGHTS])
    check("... lights are not heavy", p.heavy is False)
    first = text.splitlines()[0]
    check("the card's FIRST line names every device and the action",
          first == ("Jarvis would like to call light.turn_off on 3 Home Assistant devices: "
                    "light.kitchen, light.hall, light.bedroom."), first)
    check("the card says it is one decision about exactly these, nothing later",
          "One decision about exactly these 3 devices" in text
          and "Nothing is added after you approve" in text
          and "no permission for anything later" in text, text)
    for i, e in enumerate(LIGHTS, 1):
        check(f"the card lists {e} with its exact request and body",
              f"  {i}. {e}: light.turn_off" in text
              and f'body: {{"entity_id": "{e}"}}' in text, text)
    check("the card says what saying no costs", "If you say no: nothing happens; every "
          "one of these devices is left exactly as it is" in text)
    check("the token is on no card", "not-a-token" not in text)
    with Env():
        dim = H.plan_services("light", "turn_on", LIGHTS[:2], {"brightness_pct": 30})
    check("service data goes to every device",
          [q.body for q in dim.queries] == [{"brightness_pct": 30, "entity_id": e}
                                            for e in LIGHTS[:2]])


def t_one_device_is_exactly_the_old_card():
    with Env():
        one = H.plan_services("light", "turn_on", ["light.kitchen"], {"brightness": 200})
        old = H.plan_service("light", "turn_on", "light.kitchen", {"brightness": 200})
        twice = H.plan_services("light", "turn_off", ["light.hall", "light.hall", " light.hall "])
    check("one device: the same plan and card as before",
          H.describe(one) == H.describe(old) and one.queries == old.queries)
    check("the same device named three times is one device, one request",
          len(twice.queries) == 1 and twice.queries[0].entity_id == "light.hall")


def t_the_cap():
    with Env():
        ten = H.plan_services("light", "turn_off", [f"light.room{i}" for i in range(H.MAX_GROUP)])
        eleven = H.plan_services("light", "turn_off",
                                 [f"light.room{i}" for i in range(H.MAX_GROUP + 1)])
    check(f"{H.MAX_GROUP} devices: one card", len(ten.queries) == H.MAX_GROUP)
    check(f"{H.MAX_GROUP + 1} devices: refused, never cut to {H.MAX_GROUP}",
          eleven.queries == [] and "at most 10" in eleven.reason_empty, eleven.reason_empty)
    check("MAX_GROUP is 10", H.MAX_GROUP == 10)


def t_never_grouped():
    with Env():
        for other in ("lock.front_door", "alarm_control_panel.home", "cover.garage",
                      "valve.water_main", "siren.hall", "camera.porch", "script.good_night",
                      "scene.movie", "automation.lights_out", "button.open_gate",
                      "switch.garage_door", "switch.front_door", "switch.back_gate",
                      "switch.alarm_panel"):
            p = H.plan_services("homeassistant", "turn_off", ["light.kitchen", other])
            check(f"never grouped: {other}", p.queries == [] and other in p.reason_empty
                  and "card of its own" in p.reason_empty, p.reason_empty)
        ok = H.plan_services("homeassistant", "turn_off", ["light.kitchen", "light.outdoor"])
        check("CONTROL: 'door' inside another word (light.outdoor) is not a door",
              len(ok.queries) == 2, ok.reason_empty)
        svc = H.plan_services("lock", "lock", ["light.kitchen", "light.hall"])
        check("a lock service is never grouped, whatever the ids", svc.queries == [],
              svc.reason_empty)
        for key in ("entity_id", "area_id", "device_id"):
            p = H.plan_services("light", "turn_off", LIGHTS, {key: "lock.front_door"})
            check(f"a group whose data names its own target ({key}) is refused",
                  p.queries == [] and key in p.reason_empty, p.reason_empty)
        bad = H.plan_services("light", "turn_off", ["light.kitchen", "../../api/x"])
        check("one bad id refuses the whole set (nothing is quietly dropped)",
              bad.queries == [], bad.reason_empty)
        # A single lock is still allowed - on a card of its own, marked HEAVY.
        lock = H.plan_services("lock", "unlock", ["lock.front_door"])
        check("one lock on its own: its own card, HEAVY",
              len(lock.queries) == 1 and lock.heavy and "HEAVY" in H.describe(lock))
        garage = H.plan_service("switch", "turn_on", "switch.garage_door")
        check("a switch whose id says garage door is HEAVY on its own card",
              garage.heavy and "HEAVY" in H.describe(garage))
    with Env(url=None):
        p = H.plan_services("light", "turn_off", LIGHTS)
    check("no Home Assistant set up: refused, nothing sent",
          p.queries == [] and H.URL_ENV in p.reason_empty)


# --------------------------------------------------------------------------
#   Running it
# --------------------------------------------------------------------------

def t_run_sends_exactly_the_listed_set():
    with Env():
        p = H.plan_services("light", "turn_off", LIGHTS)
    rec = Recorder()
    out = H.run(p, fetch=rec)
    check("without approved=True nothing is sent", out["ok"] is False and rec.sent == [])
    out = H.run(p, fetch=rec, approved=True)
    check("approved: exactly the three listed requests, in the card's order",
          [b["entity_id"] for _, _, b in rec.sent] == LIGHTS and len(rec.sent) == 3, rec.sent)
    check("... and each device's answer comes back",
          out["ok"] is True and [r["entity_id"] for r in out["results"]] == LIGHTS, out)
    rec2 = Recorder(fail={"light.hall"})
    out2 = H.run(p, fetch=rec2, approved=True)
    check("one device fails: the others were still sent",
          [b["entity_id"] for _, _, b in rec2.sent] == LIGHTS, rec2.sent)
    check("... and the answer says which one did not work",
          out2["ok"] is False and "light.hall" in out2["reason"]
          and "1 of 3" in out2["reason"], out2)


def t_nothing_is_added_after_the_card():
    with Env():
        p = H.plan_services("light", "turn_off", LIGHTS)
        extra = H.plan_service("lock", "unlock", "lock.front_door").queries[0]
    p.queries.append(extra)
    rec = Recorder()
    out = H.run(p, fetch=rec, approved=True)
    check("a request added after the plan was made: NOTHING is sent",
          out["ok"] is False and rec.sent == [] and "nothing was sent" in out["reason"], out)
    with Env():
        p = H.plan_services("light", "turn_off", LIGHTS)
    p.queries[1].body["entity_id"] = "lock.front_door"
    out = H.run(p, fetch=rec, approved=True)
    check("a body changed after the plan was made: nothing is sent", rec.sent == []
          and out["ok"] is False)
    with Env():
        one = H.plan_service("light", "turn_on", "light.kitchen")
    one.queries[0].url = one.queries[0].url.replace("light/turn_on", "lock/unlock")
    out = H.run(one, fetch=rec, approved=True)
    check("the same holds for a one-device plan", rec.sent == [] and out["ok"] is False)


# --------------------------------------------------------------------------
#   The chat loop
# --------------------------------------------------------------------------

class Verdict:
    def __init__(self, allowed, tier, outcome):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.reason, self.action, self.request_id = outcome, "x", None


class Gate:
    def __init__(self, verdict):
        self.verdict, self.asked = verdict, []

    def __call__(self, action, detail, prompt):
        self.asked.append((action, detail))
        return self.verdict


def call(i, args):
    return {"id": str(i), "function": {"name": "home_control", "arguments": json.dumps(args)}}


def turn(calls, gate):
    responses = [{"choices": [{"message": {"role": "assistant", "tool_calls": calls}}]},
                 {"choices": [{"message": {"role": "assistant", "content": "done"}}]}]
    opener, bodies = scripted_stream(responses)
    streamed = []
    real_tier = AG._tier_of
    AG._tier_of = lambda action: "ask"
    try:
        with NoRealIO():
            AG.run_local_turn([{"role": "user", "content": "lights off", "provenance": "typed"}],
                              "qwen3:8b", ollama_url="http://127.0.0.1:11434",
                              stream_out=streamed.append, gate_check=gate, open_stream=opener,
                              enabled_tools={"home_control"})
    finally:
        AG._tier_of = real_tier
    told = [m["content"] for m in bodies[-1]["messages"] if m.get("role") == "tool"]
    return told, answer_text(streamed)


def t_the_loop_asks_once_for_the_set():
    gate = Gate(Verdict(True, "ask", "approved"))
    with Env(), Recorder() as rec:
        told, _ = turn([call(1, {"domain": "light", "service": "turn_off",
                                 "entity_ids": LIGHTS})], gate)
    check("three lights in one call: ONE card", len(gate.asked) == 1, gate.asked)
    card = gate.asked[0][1]["text"] if gate.asked else ""
    check("... listing every one", all(e in card for e in LIGHTS), card)
    check("after the yes, exactly those three were sent",
          [b["entity_id"] for _, _, b in rec.sent] == LIGHTS, rec.sent)
    check("the model is told how each went", '"results"' in (told[-1] if told else ""), told)
    denied = Gate(Verdict(False, "ask", "denied"))
    with Env(), Recorder() as rec:
        turn([call(1, {"domain": "light", "service": "turn_off", "entity_ids": LIGHTS})], denied)
    check("a denied card sends nothing at all", len(denied.asked) == 1 and rec.sent == [])
    both = Gate(Verdict(True, "ask", "approved"))
    with Env(), Recorder() as rec:
        turn([call(1, {"domain": "light", "service": "turn_off",
                       "entity_id": "light.kitchen", "entity_ids": ["light.hall"]})], both)
    check("entity_id and entity_ids together: one card for both devices",
          len(both.asked) == 1 and [b["entity_id"] for _, _, b in rec.sent]
          == ["light.kitchen", "light.hall"], rec.sent)


def t_a_group_counts_once_toward_the_limit():
    gate = Gate(Verdict(True, "ask", "approved"))
    calls = [call(i, {"domain": "light", "service": "turn_off",
                      "entity_ids": [f"light.a{i}", f"light.b{i}", f"light.c{i}"]})
             for i in range(AG.CARDS_PER_TURN)]
    with Env(), Recorder() as rec:
        turn(calls, gate)
    check(f"{AG.CARDS_PER_TURN} calls of three lights: {AG.CARDS_PER_TURN} cards, "
          f"{3 * AG.CARDS_PER_TURN} lights", len(gate.asked) == AG.CARDS_PER_TURN
          and len(rec.sent) == 3 * AG.CARDS_PER_TURN, (len(gate.asked), len(rec.sent)))


def t_the_loop_refuses_a_set_that_cannot_share_a_card():
    for label, args, want in (
            ("a lock among the lights",
             {"domain": "homeassistant", "service": "turn_off",
              "entity_ids": ["light.kitchen", "lock.front_door"]}, "card of its own"),
            ("eleven lights",
             {"domain": "light", "service": "turn_off",
              "entity_ids": [f"light.r{i}" for i in range(11)]}, "at most 10"),
            ("no device at all", {"domain": "light", "service": "turn_off"}, "entity_id")):
        gate = Gate(Verdict(True, "ask", "approved"))
        with Env(), Recorder() as rec:
            told, _ = turn([call(1, args)], gate)
        check(f"{label}: no card, nothing sent", gate.asked == [] and rec.sent == [],
              (gate.asked, rec.sent))
        check(f"{label}: the model is told why, so it can ask again properly",
              bool(told) and want in told[-1], told)


if __name__ == "__main__":
    for fn in (t_one_card_lists_every_device, t_one_device_is_exactly_the_old_card, t_the_cap,
               t_never_grouped, t_run_sends_exactly_the_listed_set,
               t_nothing_is_added_after_the_card, t_the_loop_asks_once_for_the_set,
               t_a_group_counts_once_toward_the_limit,
               t_the_loop_refuses_a_set_that_cannot_share_a_card):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
