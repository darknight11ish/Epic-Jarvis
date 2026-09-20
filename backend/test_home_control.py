"""jarvis_home.py: reads named Home Assistant entities, and separately -
more carefully - calls one Home Assistant service. Proves `plan_states()`/
`plan_service()` open no socket, `run()` cannot be tricked into acting
without approval, and a lock/alarm/cover action is marked heavy.

    python3 test_home_control.py
"""
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _where import BACKEND, REPO  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_home as H

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


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


def with_env(url=None, token=None):
    class _Ctx:
        def __enter__(self2):
            keys = (H.URL_ENV, H.TOKEN_ENV)
            self2.saved = {k: os.environ.get(k) for k in keys}
            for k, v in zip(keys, (url, token)):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            return self2

        def __exit__(self2, *a):
            for k, v in self2.saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            return False
    return _Ctx()


# ── plan_states(): opens no socket, refuses cleanly with nothing configured ──

with with_env():
    with NoNetwork():
        p_empty = H.plan_states(["light.kitchen"])
    check("no URL configured -> reason_empty is set", bool(p_empty.reason_empty))
    text = H.describe(p_empty)
    check("describe() says why, sends nothing",
          "not set" in text and "Nothing would be sent" in text)

with with_env():
    p_none = H.plan_states([])
    check("no entity ids given -> refuses before needing a URL",
          "no entity ids" in p_none.reason_empty)

with with_env(url="http://ha.local:8123", token="tok123"):
    with NoNetwork():
        p = H.plan_states(["light.kitchen", "lock.front_door"])
    check("plan_states() opens no socket", True)
    check("a query is built per entity", len(p.queries) == 2)
    check("the URL names the entity", p.queries[0].url.endswith("/api/states/light.kitchen"))
    check("the token never appears in any query URL",
          all("tok123" not in q.url for q in p.queries))
    check("get_states plans are never marked heavy", p.heavy is False)

with with_env(url="http://ha.local:8123"):
    many = [f"light.room{i}" for i in range(50)]
    p = H.plan_states(many)
    check("entity list is capped", len(p.queries) == H._MAX_ENTITIES)

# ── plan_service(): opens no socket, marks lock/alarm/cover heavy ────────

with with_env(url="http://ha.local:8123", token="tok123"):
    with NoNetwork():
        p_light = H.plan_service("light", "turn_on", "light.kitchen", {"brightness": 200})
        p_lock = H.plan_service("lock", "unlock", "lock.front_door")
        p_alarm = H.plan_service("alarm_control_panel", "alarm_disarm", "alarm_control_panel.home")
        p_cover = H.plan_service("cover", "open_cover", "cover.garage")
    check("plan_service() opens no socket", True)
    check("a light action is not heavy", p_light.heavy is False)
    check("a lock action is heavy", p_lock.heavy is True)
    check("an alarm action is heavy", p_alarm.heavy is True)
    check("a cover action is heavy", p_cover.heavy is True)
    check("the service body carries entity_id and extra data",
          p_light.queries[0].body == {"entity_id": "light.kitchen", "brightness": 200})
    check("the token never appears in the service URL",
          "tok123" not in p_light.queries[0].url)
    check("the URL names the domain and service",
          p_light.queries[0].url.endswith("/api/services/light/turn_on"))

with with_env(url="http://ha.local:8123"):
    p_bad = H.plan_service("", "turn_on", "light.kitchen")
    check("a missing domain refuses before needing a URL",
          "are all required" in p_bad.reason_empty)

# ── describe(): the literal request and body, never the token ────────────

with with_env(url="http://ha.local:8123", token="tok123"):
    text = H.describe(H.plan_states(["light.kitchen"]))
    check("describe() prints the literal URL", "/api/states/light.kitchen" in text)
    check("describe() says a token will be sent, never what it is",
          "will send the configured Home Assistant access token" in text and "tok123" not in text)

    lock_text = H.describe(H.plan_service("lock", "unlock", "lock.front_door"))
    check("describe() calls out a heavy action plainly", "marked HEAVY" in lock_text)
    light_text = H.describe(H.plan_service("light", "turn_on", "light.kitchen"))
    check("describe() says nothing about heaviness for a normal action",
          "HEAVY" not in light_text)
    check("describe() prints the literal POST body",
          '"entity_id": "light.kitchen"' in light_text)

with with_env(url="http://ha.local:8123", token=None):
    text = H.describe(H.plan_states(["light.kitchen"]))
    check("unauthenticated calls this out rather than staying silent",
          "No access token is configured" in text)

# ── run(): refuses without approval ───────────────────────────────────────

with with_env(url="http://ha.local:8123", token="tok123"):
    p = H.plan_states(["light.kitchen"])
    unapproved = H.run(p)
    check("run() without approval does nothing (read)", unapproved["ok"] is False)

    p_svc = H.plan_service("lock", "unlock", "lock.front_door")
    unapproved_svc = H.run(p_svc)
    check("run() without approval does nothing (service call)", unapproved_svc["ok"] is False)

# ── run(): get_states, normalised and bounded ─────────────────────────────

with with_env(url="http://ha.local:8123", token="tok123"):
    p = H.plan_states(["light.kitchen", "lock.front_door"])
    calls = []

    def fake_fetch(query):
        calls.append(query.entity_id)
        if query.entity_id == "light.kitchen":
            return {"state": "on", "attributes": {"brightness": 180}}
        return {"state": "locked", "attributes": {}}

    out = H.run(p, fetch=fake_fetch, approved=True)
    check("run() calls fetch once per entity", calls == ["light.kitchen", "lock.front_door"])
    check("run() succeeds when fetch succeeds", out["ok"] is True)
    check("both states are read", len(out["states"]) == 2)
    check("state is captured correctly", out["states"][0]["state"] == "on")
    check("attributes are captured as a JSON string",
          "180" in out["states"][0]["attributes"])

    def failing_fetch(query):
        raise TimeoutError("no route to host")

    failed = H.run(p, fetch=failing_fetch, approved=True)
    check("a failure mid-read is reported, not raised", failed["ok"] is False)
    check("the failure names which entity failed", "light.kitchen" in failed["reason"])

# ── run(): call_service, exactly one request ──────────────────────────────

with with_env(url="http://ha.local:8123", token="tok123"):
    p = H.plan_service("lock", "unlock", "lock.front_door")
    calls = []

    def fake_fetch(query):
        calls.append(query)
        return [{"entity_id": "lock.front_door", "state": "unlocked"}]

    out = H.run(p, fetch=fake_fetch, approved=True)
    check("run() calls fetch exactly once for a service call", len(calls) == 1)
    check("the service call succeeds when fetch succeeds", out["ok"] is True)
    check("the response is returned verbatim", out["response"][0]["state"] == "unlocked")

    def failing_service_fetch(query):
        raise RuntimeError("HTTP 401 Unauthorized")

    failed = H.run(p, fetch=failing_service_fetch, approved=True)
    check("a failed service call is reported, not raised", failed["ok"] is False)
    check("the failure reason is legible", "401" in failed["reason"])

# ── heavy is decided by the ENTITY too, not only the service domain ───────

with with_env(url="http://ha.local:8123", token="tok123"):
    # `homeassistant.turn_on/turn_off/toggle` are real services that FORWARD
    # to the entity's own domain. Classifying on the service domain alone
    # left the approval card for an unlock without its "this is marked
    # HEAVY" line - the one line that says the front door is involved.
    forwarded = H.plan_service("homeassistant", "turn_off", "lock.front_door")
    check("homeassistant.turn_off on a lock is heavy", forwarded.heavy is True)
    check("and the card says so", "HEAVY" in H.describe(forwarded).upper(),
          H.describe(forwarded))

    for dom in ("alarm_control_panel", "cover"):
        fwd = H.plan_service("homeassistant", "turn_on", f"{dom}.garage")
        check(f"homeassistant.turn_on on a {dom} entity is heavy", fwd.heavy is True)

    # CONTROL: the same forwarding service on an ordinary entity must NOT
    # become heavy, or the marking stops meaning anything.
    light = H.plan_service("homeassistant", "turn_on", "light.kitchen")
    check("CONTROL: homeassistant.turn_on on a light is not heavy", light.heavy is False)
    check("CONTROL: a direct lock.unlock is still heavy",
          H.plan_service("lock", "unlock", "lock.front_door").heavy is True)

# ── an entity id is not free text, and never reaches a URL raw ────────────

with with_env(url="http://ha.local:8123", token="tok123"):
    # plan_states ships at tier `auto` - no card, so nobody sees the URL
    # before it is sent. A traversal in an id would have reached the wire as
    # a request to a completely different route, under a standing grant
    # given to a read.
    traversal = H.plan_states(["../../api/services/lock/unlock"])
    check("a path traversal in an entity id is refused outright",
          traversal.queries == [], repr(traversal.queries))
    check("and the plan says why", "entity id" in traversal.reason_empty,
          traversal.reason_empty)

    for hostile in ("light.kitchen?x=1", "light.kitchen#frag", "light kitchen",
                    "light.kitchen/../../x", "LIGHT.KITCHEN"):
        p_bad = H.plan_states([hostile])
        check(f"refused: {hostile!r}", p_bad.queries == [], repr(p_bad.queries))

    # A good id still works, and is percent-encoded on the way in - belt and
    # braces, so even a shape check that is one day loosened cannot let a
    # path separator through.
    good = H.plan_states(["light.kitchen"])
    check("a real entity id still plans a read", len(good.queries) == 1)
    check("and lands on the states route",
          good.queries[0].url == "http://ha.local:8123/api/states/light.kitchen",
          good.queries[0].url)

    # A mixed list keeps the good ones and drops the rest, rather than
    # failing the whole read.
    mixed = H.plan_states(["light.kitchen", "../evil"])
    check("a mixed list keeps only the real ids", len(mixed.queries) == 1, repr(mixed.queries))
    check("and the one it kept is the real one",
          mixed.queries[0].entity_id == "light.kitchen")

    bad_service = H.plan_service("lock", "unlock", "../../states")
    check("plan_service refuses a bad entity id too", bad_service.queries == [],
          repr(bad_service.queries))
    bad_domain = H.plan_service("../services", "unlock", "lock.front_door")
    check("plan_service refuses a domain that is not one segment",
          bad_domain.queries == [], repr(bad_domain.queries))


print()
if FAILED:
    print(f"{len(FAILED)} failed: {', '.join(FAILED)}")
    sys.exit(1)
print(f"{len(PASSED)} passed - reads are bounded and auto, actions are explicit, approved, and heavy where it matters")
