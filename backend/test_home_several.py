"""Several smart-home devices on ONE approval card.

    python3 test_home_several.py

The owner's decision of 2026-09-25, after the creativity audit (CLAUDE.md;
docs/CREATIVITY-AUDIT-2026-09-25.md, plan item 9): "turn off the kitchen,
hall and bedroom lights" is one card, every device listed in full; locks,
alarms, doors and covers always get a card of their own; one decision about
a fully listed set, never a standing permission. What it proves, with no
Home Assistant anywhere (the requests go to a recorder, never a socket):

  - jarvis_home.plan_services: one CALL per device, the same service and
    data on each, every one printed on the card, opening no socket; each call
    carries the read-only readback that decides whether it worked; one
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
import urllib.error
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
    would have been sent, and answers like Home Assistant.

    A service call is answered the way HA answers one - HTTP 200, with the
    list of states it says changed - and a READBACK is answered the way
    `GET /api/states/<eid>` answers, with the state the entity now holds.
    `state_of` sets that per device, which is how "the call was accepted but
    the device did not respond" is staged: the POST still succeeds, and the
    readback is the only thing that says `unavailable`.
    """

    def __init__(self, fail=(), state_of=None, default_state="on"):
        self.sent, self.fail = [], set(fail)
        self.state_of = dict(state_of or {})
        self.default_state = default_state

    def _state(self, eid):
        return self.state_of.get(eid, self.default_state)

    def __call__(self, q):
        self.sent.append((q.method, q.url, dict(q.body or {})))
        if q.entity_id in self.fail:
            raise TimeoutError("no answer")
        if q.method == "GET":
            return {"entity_id": q.entity_id, "state": self._state(q.entity_id),
                    "attributes": {}}
        return [{"entity_id": q.entity_id, "state": self._state(q.entity_id)}]

    @property
    def calls(self):
        """Only the requests that ACT, in the order they were sent. The
        readbacks are in `sent` too - they really do go out - but they are
        not calls, and an assertion about "exactly the listed set" is about
        the calls."""
        return [s for s in self.sent if s[0] == "POST"]

    @property
    def readbacks(self):
        return [s for s in self.sent if s[0] == "GET"]

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
    check("three lights: three CALLS, one per device, in the order given",
          [q.entity_id for q in H.service_queries(p)] == LIGHTS and not p.reason_empty,
          p.reason_empty)
    check("... each call followed by that device's own readback",
          [(q.method, q.entity_id) for q in p.queries]
          == [("POST", e) if i % 2 == 0 else ("GET", e)
              for e in LIGHTS for i in (0, 1)], [(q.method, q.entity_id) for q in p.queries])
    check("... all the same service, and every readback a GET of /api/states/",
          all(q.url == f"{URL}/api/services/light/turn_off" and q.method == "POST"
              for q in H.service_queries(p))
          and [(q.method, q.url, q.body) for q in p.queries if q.verify]
          == [("GET", f"{URL}/api/states/{e}", None) for e in LIGHTS])
    check("... each body names its own device and nothing else",
          [q.body for q in H.service_queries(p)] == [{"entity_id": e} for e in LIGHTS])
    check("... lights are not heavy", p.heavy is False)
    check("... and the readback is not one of the calls",
          all(q.verify is False for q in H.service_queries(p))
          and all(q.verify for q in p.queries if q.method == "GET"))
    first = text.splitlines()[0]
    check("the card's FIRST line names every device and the action",
          first == ("Jarvis would like to call light.turn_off on 3 Home Assistant devices: "
                    "light.kitchen, light.hall, light.bedroom."), first)
    check("the card says it is one decision about exactly these, nothing later",
          "One decision about exactly these 3 devices" in text
          and "Nothing is added after you approve" in text
          and "no permission for anything later" in text, text)
    check("the card says in plain words that each device is read back after its call",
          "reads that device back to check it really responded" in text
          and "not proof" in text and "unavailable or unknown" in text, text)
    for i, e in enumerate(LIGHTS, 1):
        check(f"the card lists {e} with its exact request, body and readback",
              f"  {i}. {e}: light.turn_off" in text
              and f'body: {{"entity_id": "{e}"}}' in text
              and f"then GET {URL}/api/states/{e}" in text, text)
    check("the card says what saying no costs", "If you say no: nothing happens; every "
          "one of these devices is left exactly as it is" in text)
    check("the token is on no card", "not-a-token" not in text)
    with Env():
        dim = H.plan_services("light", "turn_on", LIGHTS[:2], {"brightness_pct": 30})
    check("service data goes to every device",
          [q.body for q in H.service_queries(dim)]
          == [{"brightness_pct": 30, "entity_id": e} for e in LIGHTS[:2]])


def t_one_device_is_exactly_the_old_card():
    with Env():
        one = H.plan_services("light", "turn_on", ["light.kitchen"], {"brightness": 200})
        old = H.plan_service("light", "turn_on", "light.kitchen", {"brightness": 200})
        twice = H.plan_services("light", "turn_off", ["light.hall", "light.hall", " light.hall "])
    check("one device: the same plan and card as before",
          H.describe(one) == H.describe(old) and one.queries == old.queries)
    check("the same device named three times is one device, one call, one readback",
          len(H.service_queries(twice)) == 1
          and H.service_queries(twice)[0].entity_id == "light.hall"
          and len(twice.queries) == 2)


def t_the_cap():
    with Env():
        ten = H.plan_services("light", "turn_off", [f"light.room{i}" for i in range(H.MAX_GROUP)])
        eleven = H.plan_services("light", "turn_off",
                                 [f"light.room{i}" for i in range(H.MAX_GROUP + 1)])
    check(f"{H.MAX_GROUP} devices: one card", len(H.service_queries(ten)) == H.MAX_GROUP)
    check(f"{H.MAX_GROUP} devices: and one readback each, so {2 * H.MAX_GROUP} requests",
          len(ten.queries) == 2 * H.MAX_GROUP, len(ten.queries))
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
              len(H.service_queries(ok)) == 2, ok.reason_empty)
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
              len(H.service_queries(lock)) == 1 and lock.heavy and "HEAVY" in H.describe(lock))
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
    check("approved: exactly the three listed calls, in the card's order",
          [b["entity_id"] for _, _, b in rec.calls] == LIGHTS and len(rec.calls) == 3,
          rec.sent)
    check("... each one immediately followed by its own device's readback",
          [u for _, u, _ in rec.readbacks] == [f"{URL}/api/states/{e}" for e in LIGHTS]
          and len(rec.sent) == 6, rec.sent)
    check("... and each device's answer comes back, verified against its state",
          out.get("ok") is True and [r["entity_id"] for r in out.get("results", [])] == LIGHTS
          and all(r.get("verified") is True and r.get("state_after")
                  for r in out.get("results", [])), out)
    rec2 = Recorder(fail={"light.hall"})
    out2 = H.run(p, fetch=rec2, approved=True)
    check("one device fails: the others were still sent",
          [b["entity_id"] for _, _, b in rec2.calls] == LIGHTS, rec2.sent)
    check("... and a device whose call never succeeded is never read back",
          [u for _, u, _ in rec2.readbacks]
          == [f"{URL}/api/states/light.kitchen", f"{URL}/api/states/light.bedroom"],
          rec2.sent)
    check("... and the answer says which one did not work",
          out2.get("ok") is False and "light.hall" in out2.get("reason", "")
          and "1 of 3" in out2.get("reason", ""), out2)
    check("... while the two that did are still verified",
          [bool(r.get("verified")) for r in out2.get("results", [])] == [True, False, True],
          out2)


def t_the_state_decides_whether_it_worked():
    """The defect this whole change is for: Home Assistant answers the service
    call with HTTP 200 and the entity did not respond.

    A 200 means "I took the call", not "the light came on". An unplugged
    light, a device that has dropped off the mesh and a renamed entity all
    answer 200 and change nothing. The readback is what tells the truth, and
    these are the two halves of it, one device and three.
    """
    with Env():
        one = H.plan_services("light", "turn_on", ["light.kitchen"])
        many = H.plan_services("light", "turn_off", LIGHTS)

    rec = Recorder(state_of={"light.kitchen": "unavailable"})
    out = H.run(one, fetch=rec, approved=True)
    check("BITES: the call is accepted (HTTP 200) and the device is unavailable -> NOT ok",
          out.get("ok") is False, out)
    check("... and the reason says which device, what state, and that it did not respond",
          out.get("reason") == ("light.kitchen is unavailable in Home Assistant, so it did "
                                "not respond"), out.get("reason"))
    check("... and the state it found is carried back, so nothing is guessed",
          out.get("state_after") == "unavailable", out)
    check("... and it is never called verified", "verified" not in out
          or out.get("verified") is not True, out)
    check("... and the readback really was sent, after the call",
          [m for m, _, _ in rec.sent] == ["POST", "GET"], rec.sent)

    rec2 = Recorder(state_of={"light.hall": "unknown"})
    out2 = H.run(many, fetch=rec2, approved=True)
    check("BITES: one device out of three is unknown -> the set is not ok",
          out2.get("ok") is False, out2)
    hall = [r for r in out2.get("results", []) if r["entity_id"] == "light.hall"]
    hall = hall[0] if hall else {}
    check("... that device is marked not ok, with its own sentence",
          hall.get("ok") is False and hall.get("state_after") == "unknown"
          and hall.get("reason") == ("light.hall is unknown in Home Assistant, so it did "
                                     "not respond"), hall)
    check("... and the devices that DID respond stay verified",
          [bool(r.get("verified")) for r in out2.get("results", [])] == [True, False, True],
          out2)
    check("... and the summary names the one that did not",
          "1 of 3" in out2.get("reason", "") and "light.hall" in out2.get("reason", ""),
          out2.get("reason"))

    # PASS: a device that really did respond is verified, with the state it
    # reports - not with the state anybody expected.
    rec3 = Recorder(state_of={"light.kitchen": "on"})
    out3 = H.run(one, fetch=rec3, approved=True)
    check("PASS: an entity that answers with a real state is verified",
          out3.get("ok") is True and out3.get("verified") is True
          and out3.get("state_after") == "on", out3)
    check("PASS: the state reported is Home Assistant's own answer, verbatim",
          out3.get("state_after") == "on" and out3.get("response") is not None, out3)
    check("... and an unexpected-but-real state is still reported, not invented away",
          H.run(one, fetch=Recorder(state_of={"light.kitchen": "off"}), approved=True)
          .get("state_after") == "off")

    # A readback that FAILS is not evidence either: never a false done.
    def half_recorder(fail_read):
        def fetch(q):
            if q.method == "GET":
                raise urllib.error.HTTPError(q.url, fail_read, "x", {}, None)
            return [{"entity_id": q.entity_id, "state": "on"}]
        return fetch
    r404 = H.run(one, fetch=half_recorder(404), approved=True)
    check("BITES: a readback answering 404 is not a success",
          r404.get("ok") is False and "404" in r404.get("reason", "")
          and "not reported as done" in r404.get("reason", ""), r404)

    # An answer with no state at all is not evidence either.
    r_blank = H.run(one, fetch=lambda q: {} if q.method == "GET" else [], approved=True)
    check("BITES: a readback with no state at all is not a success",
          r_blank.get("ok") is False and "no state" in r_blank.get("reason", ""), r_blank)


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
    H.service_queries(p)[1].body["entity_id"] = "lock.front_door"
    out = H.run(p, fetch=rec, approved=True)
    check("a body changed after the plan was made: nothing is sent", rec.sent == []
          and out["ok"] is False)
    with Env():
        p = H.plan_services("light", "turn_off", LIGHTS)
    H.service_queries(p)[0].url = H.service_queries(p)[0].url.replace("light/turn_off",
                                                                     "lock/unlock")
    out = H.run(p, fetch=rec, approved=True)
    check("a call retargeted at another service after the plan was made: nothing is sent",
          rec.sent == [] and out["ok"] is False)
    with Env():
        p = H.plan_services("light", "turn_off", LIGHTS)
    one_back = p.queries[1]
    one_back.url = f"{URL}/api/services/lock/unlock"
    out = H.run(p, fetch=rec, approved=True)
    check("the READBACK turned into a service call after the plan was made: nothing is sent",
          rec.sent == [] and out["ok"] is False, out)
    with Env():
        one = H.plan_service("light", "turn_on", "light.kitchen")
    one.queries[0].url = one.queries[0].url.replace("light/turn_on", "lock/unlock")
    out = H.run(one, fetch=rec, approved=True)
    check("the same holds for a one-device plan", rec.sent == [] and out["ok"] is False)
    # The digest is the first gate; the pairing is the second, for a plan whose
    # digest was taken over a set that never had a readback in it. Belt and
    # braces: recompute the digest honestly and the pairing still refuses.
    with Env():
        unpaired = H.plan_service("light", "turn_on", "light.kitchen")
    unpaired.queries = [q for q in unpaired.queries if not q.verify]
    unpaired.digest = H._digest(unpaired.queries)
    rec3 = Recorder()
    out = H.run(unpaired, fetch=rec3, approved=True)
    check("a plan with a matching digest but NO readback still sends nothing",
          out["ok"] is False and rec3.sent == [] and "readback" in out["reason"], out)
    with Env():
        orphan = H.plan_service("light", "turn_on", "light.kitchen")
    orphan.queries = [q for q in orphan.queries if not q.verify] + [
        H._readback_query(URL, "light.hall")]
    orphan.queries[0].verify = True
    orphan.digest = H._digest(orphan.queries)
    rec4 = Recorder()
    out = H.run(orphan, fetch=rec4, approved=True)
    check("a plan that is nothing but readbacks sends nothing",
          out.get("ok") is False and rec4.sent == []
          and "no service call" in out.get("reason", ""), out)
    check("... and describe() says so in words rather than raising",
          "no service call" in H.describe(orphan), H.describe(orphan))


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
    check("... and saying each is read back afterwards",
          "reads that device back to check it really responded" in card, card)
    check("after the yes, exactly those three were sent",
          [b["entity_id"] for _, _, b in rec.calls] == LIGHTS, rec.sent)
    check("... each followed by its readback, so a 200 is never the whole story",
          [u for _, u, _ in rec.readbacks] == [f"{URL}/api/states/{e}" for e in LIGHTS],
          rec.sent)
    check("the model is told how each went", '"results"' in (told[-1] if told else ""), told)
    check("... and whether each was verified against its state",
          '"verified": true' in (told[-1] if told else ""), told)
    denied = Gate(Verdict(False, "ask", "denied"))
    with Env(), Recorder() as rec:
        turn([call(1, {"domain": "light", "service": "turn_off", "entity_ids": LIGHTS})], denied)
    check("a denied card sends nothing at all", len(denied.asked) == 1 and rec.sent == [])
    both = Gate(Verdict(True, "ask", "approved"))
    with Env(), Recorder() as rec:
        turn([call(1, {"domain": "light", "service": "turn_off",
                       "entity_id": "light.kitchen", "entity_ids": ["light.hall"]})], both)
    check("entity_id and entity_ids together: one card for both devices",
          len(both.asked) == 1 and [b["entity_id"] for _, _, b in rec.calls]
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
          and len(rec.calls) == 3 * AG.CARDS_PER_TURN
          and len(rec.sent) == 6 * AG.CARDS_PER_TURN,
          (len(gate.asked), len(rec.calls), len(rec.sent)))


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
               t_the_state_decides_whether_it_worked,
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
