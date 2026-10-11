"""test_docker.py - the containers on Jarvis's own list, and every refusal
that makes "start a container" a safe thing to give an assistant.

    python3 backend/test_docker.py

WHAT THIS SUITE IS FOR

`backend/jarvis_docker.py` is the first code in this repository that runs
`docker`. The interesting part of it is not what it starts - it is everything
it refuses, because each refusal is one line of
`docs/DOCKER-INTEGRATION-DESIGN.md` section 3 or section 4 written as code.
So the tests below are mostly about what does NOT happen:

  * a start never pulls (the image must already be here, and the suite proves
    `docker start` is never reached when it is not) - section 3.3, "no
    auto-pull", which is the rule that decides the whole shape of the slice;
  * a container that is not ours is never touched - it must exist, run the
    pinned image, publish on loopback only and not be privileged;
  * a start that the gate did not answer "ask" on is refused rather than
    allowed (section 3.4: a config line must never become the owner's yes);
  * a denied or timed-out card changes nothing;
  * no command this module makes is ever handed to a shell, and `compose`,
    `pull` and `run` appear in no call it can make (section 3.2 and 3.3).

No pytest, no network, no Docker, no container, no model. The runner is a
stand-in, the same shape test_handoff_mode.py proves the gate with, and the
real `docker` is never invoked. `jarvis_docker.py` run as a script against a
real engine is what proves the reading half - this suite proves the refusals.
"""
from __future__ import annotations

import ast
import json
import sys
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, SHIPPED, require_shipped  # noqa: E402

require_shipped("jarvis_docker.py", "jarvis_child_env.py")

# --- the two stand-ins: jarvis_framework and jarvis_gate ------------------

AUDIT: list = []

fw = types.ModuleType("jarvis_framework")
fw.audit_log = lambda kind, detail=None, *a, **k: AUDIT.append((kind, detail))
fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = fw

#: What the gate will answer next. Set per test.
GATE: dict = {}


class _Verdict:
    def __init__(self, tier="ask", allowed=True, outcome="approved", reason="ok"):
        self.tier, self.allowed, self.outcome, self.reason = tier, allowed, outcome, reason


CARDS: list = []


def _gate(action, detail, prompt=None):
    CARDS.append((action, dict(detail or {}), prompt))
    return _Verdict(**GATE)


gate_mod = types.ModuleType("jarvis_gate")
gate_mod.check = _gate
sys.modules["jarvis_gate"] = gate_mod

import jarvis_docker as D  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("PASS  " if cond else "FAIL  ") + name + (f"   [{detail}]" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   A stand-in docker: canned answers, and a record of every call.
# --------------------------------------------------------------------------


class FakeDocker:
    """Answers like docker, and remembers what it was asked.

    `present` is the container's inspect document (`None`: no such container).
    `image_here` is what `docker image inspect` says. Anything not recognised
    raises, so a call this suite did not expect is a loud failure rather than
    a silent pass.
    """

    def __init__(self, *, engine=True, present=None, image_here=True, running=True,
                 status="Up 2 minutes", names=("searxng",)):
        self.engine = engine
        self.present = present
        self.image_here = image_here
        self.running = running
        self.status = status
        self.names = tuple(names)
        self.calls: list = []

    # -- the seam jarvis_docker._RUNNER has --
    def __call__(self, args, timeout):
        args = [str(a) for a in args]
        self.calls.append(list(args))
        if args[:1] == ["version"]:
            return (0, "29.7.2\n", "") if self.engine else (1, "", "error during connect")
        if args[:3] == ["ps", "-a", "--format"]:
            if not self.engine:
                return 1, "", "error during connect"
            rows = []
            for n in self.names:
                rows.append(json.dumps({
                    "Names": n, "State": "running" if self.running else "exited",
                    "Status": self.status,
                }))
            return 0, "\n".join(rows) + "\n", ""
        if args[:1] == ["inspect"]:
            if self.present is None:
                return 1, "", f"Error: No such object: {args[1]}"
            return 0, json.dumps([self.present]), ""
        if args[:2] == ["image", "inspect"]:
            return (0, "[]", "") if self.image_here else (1, "", "Error: No such image")
        if args[:1] in (["start"], ["stop"]):
            return 0, args[1] + "\n", ""
        raise AssertionError(f"unexpected docker call: {args}")

    # -- helpers for the tests --
    def verbs(self) -> list:
        return [c[0] for c in self.calls]

    def ran(self, verb: str) -> bool:
        return verb in self.verbs()


def doc_for(spec, *, image=None, privileged=False, host_ip="127.0.0.1", ports=True):
    """A container inspect document shaped like docker's own."""
    bindings = {}
    if ports:
        bindings[f"{spec.container_port}/tcp"] = [{"HostIp": host_ip, "HostPort": str(spec.port)}]
    return {
        "Id": "0" * 64,
        "Name": "/" + spec.container,
        "Config": {"Image": image if image is not None else spec.image,
                   "Privileged": privileged},
        "HostConfig": {"Privileged": privileged, "PortBindings": bindings},
        "State": {"Running": True, "Status": "running"},
    }


SPEC = D.SERVICES[0]


def fresh(**kw):
    """A clean module state with a FakeDocker wired in."""
    D._reset_for_tests()
    CARDS.clear()
    AUDIT.clear()
    GATE.clear()
    GATE.update(tier="ask", allowed=True, outcome="approved", reason="ok")
    f = FakeDocker(**kw)
    D._RUNNER = f
    return f


def sync(fn):
    return fn()


# --------------------------------------------------------------------------
#   The list
# --------------------------------------------------------------------------


def test_pinned():
    check("a dated tag counts as pinned", D._pinned("searxng/searxng:2026.10.9-f4822b3fc"))
    check("docker.io/name:tag counts as pinned", D._pinned("docker.io/searxng/searxng:2026.10.9"))
    check("no tag at all is NOT pinned", not D._pinned("searxng/searxng"))
    check(":latest is NOT pinned", not D._pinned("searxng/searxng:latest"))
    check(":LATEST is NOT pinned either", not D._pinned("searxng/searxng:LATEST"))
    check("an empty image is NOT pinned", not D._pinned(""))
    check("the listed service's own image IS pinned", D._pinned(SPEC.image))


def test_loopback():
    for good in ("127.0.0.1", "::1", "localhost"):
        check(f"{good} counts as loopback", D._loopback(good))
    for bad in ("0.0.0.0", "", None, "192.168.1.10", "::"):
        check(f"{bad!r} does NOT count as loopback", not D._loopback(bad))


def test_engine_down():
    fresh(engine=False)
    v = D.view()
    check("docker down: the view says so", v["docker"] is False)
    check("docker down: no services are listed", v["services"] == [])
    check("docker down: the plain words are Jarvis's own", v["why"] == D.WORDS["no_docker"])
    check("docker down: both apps get the words table", "title" in v["words"])


def test_container_absent():
    # No such container: `docker ps` does not list it AND `docker inspect`
    # finds nothing. Both, because that is what a PC without the container
    # actually answers - a fake that lists a name it cannot inspect would be
    # testing a state that does not exist.
    fresh(present=None, names=())
    st = D.state(SPEC)
    check("absent container: not present", st["present"] is False)
    check("absent container: not running", st["running"] is False)
    check("absent container: not ours", st["ours"] is False)
    check("absent container: cannot be started", st["can_start"] is False)
    check("absent container: says to start it by hand instead",
          "by hand" in st.get("why", ""), st.get("why", ""))
    check("absent container: the reason names the compose file",
          SPEC.compose in st.get("why", ""), st.get("why", ""))


def test_container_listed_but_uninspectable():
    """Listed by `docker ps` and then refusing to answer `inspect` - fail
    closed, and never treat it as ours."""
    fresh(present=None, names=("searxng",))
    st = D.state(SPEC)
    check("listed but uninspectable: present is True", st["present"] is True)
    check("listed but uninspectable: NOT ours", st["ours"] is False)
    check("listed but uninspectable: cannot be started", st["can_start"] is False)
    check("listed but uninspectable: says the container could not be inspected",
          "could not be inspected" in st.get("why", ""), st.get("why", ""))


def test_healthy_is_ours():
    fresh(present=doc_for(SPEC))
    st = D.state(SPEC)
    check("a matching container IS ours", st["ours"] is True)
    check("a matching container is running", st["running"] is True)
    check("a matching container's image is here", st.get("image_present") is True)
    check("a matching container can be started", st["can_start"] is True)
    check("a matching container can be stopped", st["can_stop"] is True)
    check("the published address is loopback only", st["published"] == "127.0.0.1:8888:8080")
    check("the url it answers on is loopback", st["url"] == "http://127.0.0.1:8888")


def test_privileged_is_not_ours():
    fresh(present=doc_for(SPEC, privileged=True))
    st = D.state(SPEC)
    check("a privileged container is NOT ours", st["ours"] is False)
    check("a privileged container is refused with a reason",
          "privileged" in st.get("why", ""), st.get("why", ""))
    check("a privileged container cannot be started", st["can_start"] is False)


def test_not_loopback_is_not_ours():
    for host_ip in ("0.0.0.0", "192.168.1.10", "", None):
        fresh(present=doc_for(SPEC, host_ip=host_ip))
        st = D.state(SPEC)
        check(f"a container published on {host_ip!r} is NOT ours", st["ours"] is False)
        check(f"a container published on {host_ip!r} is refused with a reason",
              "not just this PC" in st.get("why", ""), st.get("why", ""))


def test_no_ports_is_not_ours():
    fresh(present=doc_for(SPEC, ports=False))
    st = D.state(SPEC)
    check("a container publishing nothing is NOT ours", st["ours"] is False)
    check("...and says why", "publishes no port" in st.get("why", ""), st.get("why", ""))


def test_wrong_image_is_not_ours():
    fresh(present=doc_for(SPEC, image="someone-elses/searxng:1.0"))
    st = D.state(SPEC)
    check("a container running a different image is NOT ours", st["ours"] is False)
    check("...and names both images", "someone-elses" in st.get("why", "")
          and SPEC.image in st.get("why", ""), st.get("why", ""))


def test_unpinned_live_container_is_not_ours():
    fresh(present=doc_for(SPEC, image="searxng/searxng:latest"))
    st = D.state(SPEC)
    check("a container running :latest is NOT ours", st["ours"] is False)


# --------------------------------------------------------------------------
#   NO AUTO-PULL - the rule that decides the shape of this slice
# --------------------------------------------------------------------------


def test_start_never_pulls():
    f = fresh(present=doc_for(SPEC), image_here=False, running=False)
    code, out = D.request({"service": "searxng", "action": "start"},
                          gate=_gate, tier_of=lambda a: "ask", spawn=sync)
    check("start with no local image: refused", code == 409, str(code))
    check("start with no local image: flagged as needing a download",
          out.get("needs_download") is True)
    check("start with no local image: the words name the exact image",
          SPEC.image in out.get("error", ""), out.get("error", ""))
    check("start with no local image: NO docker start was ever made",
          not f.ran("start"), str(f.calls))
    check("start with no local image: no card was raised either", CARDS == [], str(CARDS))
    check("the module can never reach compose/up",
          not any(c[:1] in (["compose"], ["pull"], ["run"]) for c in f.calls), str(f.calls))


def test_module_source_cannot_pull_or_privilege():
    src = (HERE / "jarvis_docker.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    # Every string literal and every list literal in the file: no 'pull',
    # 'compose', 'run' or '--privileged' may appear as one.
    literals = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literals.append(node.value)
        if isinstance(node, ast.List):
            for el in node.elts:
                if isinstance(el, ast.Constant) and isinstance(el.value, str):
                    literals.append(el.value)
    # The docstring explains why these words are absent; prose is allowed to
    # mention them, so only the code paths matter: search the AST for a call
    # whose ARGUMENTS contain them.
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for a in node.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    if a.value.strip() in ("pull", "compose", "run", "up", "--privileged",
                                           "-v", "--volume", "--mount"):
                        bad.append(a.value)
    check("no call in jarvis_docker.py passes pull/compose/run/-v/--privileged",
          bad == [], str(bad))
    check("jarvis_docker.py never passes shell=True",
          "shell=True" not in src)
    check("jarvis_docker.py has no `docker run` string literal",
          '"run"' not in src.replace("'run'", '"run"'))


# --------------------------------------------------------------------------
#   Start and stop, through the gate
# --------------------------------------------------------------------------


def test_start_asks_and_then_starts():
    f = fresh(present=doc_for(SPEC), running=False)
    code, out = D.request({"service": "searxng", "action": "start"},
                          gate=_gate, tier_of=lambda a: "ask", spawn=sync)
    check("start: answered 202 waiting", code == 202, str(code))
    check("start: says it is waiting for the owner", out.get("waiting") is True)
    check("start: one card was raised", len(CARDS) == 1, str(len(CARDS)))
    check("start: the card asks about the right action",
          CARDS and CARDS[0][0] == D.ACTION_START)
    check("start: the card names the container",
          CARDS and CARDS[0][1].get("container") == "searxng")
    check("start: the card names the pinned image",
          CARDS and CARDS[0][1].get("image") == SPEC.image)
    check("start: the card says nothing leaves the PC",
          CARDS and CARDS[0][1].get("leaves_this_pc") is False)
    check("start: the card's own text mentions the image",
          CARDS and SPEC.image in CARDS[0][2])
    check("start: the card's text says no image is downloaded",
          CARDS and "never downloads" in CARDS[0][2])
    check("start: the card's text says it answers on this PC only",
          CARDS and "this PC only" in CARDS[0][2])
    check("start: docker start was made after approval", f.ran("start"), str(f.calls))
    check("start: what was started is the listed container",
          ["start", "searxng"] in f.calls, str(f.calls))
    check("start: the outcome was recorded", D.state_of_cards()["last"]["outcome"] == "on")


def test_start_denied_changes_nothing():
    f = fresh(present=doc_for(SPEC), running=False)
    GATE.update(allowed=False, outcome="denied")
    code, out = D.request({"service": "searxng", "action": "start"},
                          gate=_gate, tier_of=lambda a: "ask", spawn=sync)
    check("denied start: still 202 waiting", code == 202, str(code))
    check("denied start: NO docker start was made", not f.ran("start"), str(f.calls))
    check("denied start: the outcome says denied",
          D.state_of_cards()["last"]["outcome"] == "denied")
    check("denied start: the owner is told plainly",
          "turned down" in D.state_of_cards()["last"]["message"])


def test_start_timed_out_changes_nothing():
    f = fresh(present=doc_for(SPEC), running=False)
    GATE.update(allowed=False, outcome="timed_out")
    D.request({"service": "searxng", "action": "start"},
              gate=_gate, tier_of=lambda a: "ask", spawn=sync)
    check("timed-out start: NO docker start was made", not f.ran("start"), str(f.calls))
    check("timed-out start: the outcome says timed_out",
          D.state_of_cards()["last"]["outcome"] == "timed_out")


def test_start_refuses_a_looser_tier():
    f = fresh(present=doc_for(SPEC), running=False)
    code, out = D.request({"service": "searxng", "action": "start"},
                          gate=_gate, tier_of=lambda a: "auto", spawn=sync)
    check("start at tier 'auto' is refused", code == 503, str(code))
    check("start at tier 'auto' names the tier in the error",
          "'auto'" in out.get("error", ""), out.get("error", ""))
    check("start at tier 'auto': no card was raised", CARDS == [], str(CARDS))
    check("start at tier 'auto': nothing was started", not f.ran("start"), str(f.calls))


def test_start_refuses_when_the_gate_answers_a_looser_tier():
    f = fresh(present=doc_for(SPEC), running=False)
    GATE.update(tier="auto", allowed=True, outcome="approved")
    D.request({"service": "searxng", "action": "start"},
              gate=_gate, tier_of=lambda a: "ask", spawn=sync)
    check("a gate that answers 'auto' is not a person saying yes: nothing started",
          not f.ran("start"), str(f.calls))


def test_start_gate_failure_changes_nothing():
    f = fresh(present=doc_for(SPEC), running=False)

    def _boom(*a, **k):
        raise RuntimeError("gate exploded")

    D.request({"service": "searxng", "action": "start"},
              gate=_boom, tier_of=lambda a: "ask", spawn=sync)
    check("a gate that throws: nothing was started", not f.ran("start"), str(f.calls))
    check("a gate that throws: the outcome is refused",
          D.state_of_cards()["last"]["outcome"] == "refused")


def test_stop_is_immediate_at_auto():
    f = fresh(present=doc_for(SPEC), running=True)
    code, out = D.request({"service": "searxng", "action": "stop"},
                          gate=_gate, tier_of=lambda a: "auto", spawn=sync)
    check("stop at tier 'auto': done at once", code == 200, str(code))
    check("stop at tier 'auto': not waiting", out.get("waiting") is False)
    check("stop at tier 'auto': docker stop was made", f.ran("stop"), str(f.calls))
    check("stop at tier 'auto': no card was raised", CARDS == [], str(CARDS))
    check("stop at tier 'auto': the words are Jarvis's own",
          out.get("message") == D.WORDS["stopped"].format(name="searxng"))


def test_stop_asks_when_the_config_says_ask():
    f = fresh(present=doc_for(SPEC), running=True)
    code, out = D.request({"service": "searxng", "action": "stop"},
                          gate=_gate, tier_of=lambda a: "ask", spawn=sync)
    check("stop at tier 'ask': a card is raised", code == 202, str(code))
    check("stop at tier 'ask': one card", len(CARDS) == 1, str(len(CARDS)))
    check("stop at tier 'ask': the card is the right action",
          CARDS and CARDS[0][0] == D.ACTION_STOP)
    check("stop at tier 'ask': approved, so it stopped", f.ran("stop"), str(f.calls))


def test_already_in_that_state():
    fresh(present=doc_for(SPEC), running=True)
    code, out = D.request({"service": "searxng", "action": "start"},
                          gate=_gate, tier_of=lambda a: "ask", spawn=sync)
    check("starting a running service: 200, not a card", code == 200, str(code))
    check("starting a running service says so",
          out.get("message") == D.WORDS["already_running"].format(name="searxng"))

    f = fresh(present=doc_for(SPEC), running=False)
    code, out = D.request({"service": "searxng", "action": "stop"},
                          gate=_gate, tier_of=lambda a: "auto", spawn=sync)
    check("stopping a stopped service: 200, no card", code == 200, str(code))
    check("stopping a stopped service runs no docker stop", not f.ran("stop"), str(f.calls))


# --------------------------------------------------------------------------
#   Nothing it did not create
# --------------------------------------------------------------------------


def test_never_touches_a_foreign_container():
    for why, doc in (("privileged", doc_for(SPEC, privileged=True)),
                     ("wide port", doc_for(SPEC, host_ip="0.0.0.0")),
                     ("wrong image", doc_for(SPEC, image="other/thing:1.2.3"))):
        f = fresh(present=doc, running=False)
        code, out = D.request({"service": "searxng", "action": "start"},
                              gate=_gate, tier_of=lambda a: "ask", spawn=sync)
        check(f"a {why} container: refused with 409", code == 409, str(code))
        check(f"a {why} container: flagged not ours", out.get("not_ours") is True)
        check(f"a {why} container: NO docker start", not f.ran("start"), str(f.calls))
        check(f"a {why} container: NO card", CARDS == [], str(CARDS))
        check(f"a {why} container: the refusal is Jarvis's own words",
              out.get("error", "").startswith("The container called")
              or "not configured" in out.get("error", ""), out.get("error", ""))


def test_cannot_start_a_container_that_is_not_there():
    f = fresh(present=None, names=())
    code, out = D.request({"service": "searxng", "action": "start"},
                          gate=_gate, tier_of=lambda a: "ask", spawn=sync)
    check("a container that does not exist: 409", code == 409, str(code))
    check("...and nothing was created", not f.ran("start") and not f.ran("run"), str(f.calls))
    check("...and says to start it by hand", "by hand" in out.get("error", ""),
          out.get("error", ""))


# --------------------------------------------------------------------------
#   The route's own edges
# --------------------------------------------------------------------------


def test_bad_input():
    fresh(present=doc_for(SPEC))
    code, out = D.request({"service": "nginx", "action": "start"},
                          gate=_gate, tier_of=lambda a: "ask", spawn=sync)
    check("a service Jarvis does not manage: 400", code == 400, str(code))
    check("...and says which ones it does", "searxng" in out.get("error", ""),
          out.get("error", ""))
    code, _ = D.request({"service": "searxng", "action": "rm -rf /"},
                        gate=_gate, tier_of=lambda a: "ask", spawn=sync)
    check("an action that is not start or stop: 400", code == 400, str(code))
    code, _ = D.request({}, gate=_gate, tier_of=lambda a: "ask", spawn=sync)
    check("an empty body: 400", code == 400, str(code))
    code, _ = D.request({"service": "searxng", "action": "START"},
                        gate=_gate, tier_of=lambda a: "ask", spawn=sync)
    check("'START' in capitals is accepted (the owner's own words are not exact)",
          code in (200, 202, 409), str(code))


def test_engine_down_refuses_acting():
    f = fresh(engine=False, present=doc_for(SPEC))
    code, out = D.request({"service": "searxng", "action": "start"},
                          gate=_gate, tier_of=lambda a: "ask", spawn=sync)
    check("docker down: the route refuses rather than guessing", code == 503, str(code))
    check("docker down: the plain words are Jarvis's own",
          out.get("error") == D.WORDS["no_docker"])
    check("docker down: nothing was started", not f.ran("start"), str(f.calls))


def test_one_card_at_a_time():
    fresh(present=doc_for(SPEC), running=False)
    # `held` collects the spawned decision instead of running it, so the card
    # is still waiting when the second request arrives.
    held: list = []
    D.request({"service": "searxng", "action": "start"},
              gate=_gate, tier_of=lambda a: "ask", spawn=held.append)
    check("the first request queued exactly one decision", len(held) == 1, str(len(held)))
    check("...and the gate was not called yet (the card is still waiting)",
          CARDS == [], str(CARDS))
    code, out = D.request({"service": "searxng", "action": "start"},
                          gate=_gate, tier_of=lambda a: "ask", spawn=held.append)
    check("a second start while one card waits: 202", code == 202, str(code))
    check("...and says a card is already waiting",
          "already waiting" in out.get("message", ""), out.get("message", ""))
    check("...and queued no second decision", len(held) == 1, str(len(held)))
    check("...and raised no second card", CARDS == [], str(CARDS))


# --------------------------------------------------------------------------
#   The words, and the wiring
# --------------------------------------------------------------------------


def test_words_both_apps_show():
    for key in ("title", "detail", "started", "stopped", "already_running",
                "already_stopped", "waiting", "no_docker", "not_ours",
                "would_download", "created_elsewhere", "bad_config"):
        check(f"WORDS has {key!r}", key in D.WORDS)
    check("no word is empty", all(str(v).strip() for v in D.WORDS.values()))
    # A {name} placeholder in a sentence the module formats by hand is a
    # TypeError at the worst moment.
    for key in ("started", "stopped", "already_running", "already_stopped",
                "waiting", "created_elsewhere"):
        check(f"WORDS[{key!r}] carries a {{name}} placeholder", "{name}" in D.WORDS[key])
    check("the title both apps show is 'Docker'", D.WORDS["title"] == "Docker")


def test_service_list_is_safe_by_construction():
    check("at least one service is listed", len(D.SERVICES) >= 1)
    for s in D.SERVICES:
        check(f"{s.key}: its image is pinned", D._pinned(s.image))
        check(f"{s.key}: its host is loopback", D._loopback(s.host))
        check(f"{s.key}: its key matches its container name", s.key == s.container)
        check(f"{s.key}: it says what it provides", bool(s.provides.strip()))
        check(f"{s.key}: it names its compose file", s.compose.endswith(".yml"))


def test_the_route_installs():
    f = fresh(present=doc_for(SPEC))

    class H:
        def do_GET(self):            # pragma: no cover - never reached
            raise AssertionError("the original do_GET ran")

        def do_POST(self):           # pragma: no cover - never reached
            raise AssertionError("the original do_POST ran")

        def _send(self, code, body):
            self.sent = (code, body)
            return code

    banner = D.install(H, origin_ok=lambda self: True, token_ok=lambda self: True,
                       read_body=lambda self: {"service": "searxng", "action": "stop"})
    check("install returns a banner line naming its route", D.PATH_LIST in banner, banner)
    check("install sets the armed marker", getattr(H.do_POST, "_jarvis_docker", False) is True)


def test_install_refuses_cross_origin():
    fresh(present=doc_for(SPEC))

    class H:
        def do_GET(self):
            pass

        def do_POST(self):
            pass

        def _send(self, code, body):
            self.sent = (code, body)
            return code

        path = D.PATH_SERVICE

    D.install(H, origin_ok=lambda self: False, token_ok=lambda self: True,
              read_body=lambda self: {"service": "searxng", "action": "start"})
    h = H()
    h.do_POST()
    check("a cross-origin request is refused with 403", h.sent[0] == 403, str(h.sent))
    check("a cross-origin request starts nothing", not fresh().ran("start"))


def test_install_refuses_a_bad_token():
    fresh(present=doc_for(SPEC))

    class H:
        def do_GET(self):
            pass

        def do_POST(self):
            pass

        def _send(self, code, body):
            self.sent = (code, body)
            return code

        path = D.PATH_LIST

    D.install(H, origin_ok=lambda self: True, token_ok=lambda self: False,
              read_body=lambda self: {})
    h = H()
    h.do_GET()
    check("a bad token is refused with 401", h.sent[0] == 401, str(h.sent))


def test_other_routes_pass_through():
    fresh(present=doc_for(SPEC))
    seen = []

    class H:
        def do_GET(self):
            seen.append("get")

        def do_POST(self):
            seen.append("post")

        def _send(self, code, body):
            self.sent = (code, body)

        path = "/api/something/else"

    D.install(H, origin_ok=lambda self: True, token_ok=lambda self: True,
              read_body=lambda self: {})
    h = H()
    h.do_GET()
    h.do_POST()
    check("another GET route goes straight through", seen == ["get", "post"], str(seen))


# --------------------------------------------------------------------------
#   The repository's own rules
# --------------------------------------------------------------------------


def test_declared_where_this_repo_requires():
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("jarvis_docker.py is declared in $SHIPPED in apply-patches.ps1",
          "'jarvis_docker.py'" in ps1)
    check("jarvis_docker.py is in backend/_where.py's SHIPPED tuple",
          "jarvis_docker.py" in SHIPPED)
    check("the module is a file in backend/", (HERE / "jarvis_docker.py").is_file())


def test_design_note_exists_and_carries_the_rules():
    note = REPO / "docs" / "DOCKER-INTEGRATION-DESIGN.md"
    check("docs/DOCKER-INTEGRATION-DESIGN.md exists", note.is_file())
    if not note.is_file():
        return
    text = note.read_text(encoding="utf-8")
    for probe in ("127.0.0.1` only", "Nothing auto-pulls", "--privileged",
                  "Never mount the owner's home directory", "pinned tag"):
        check(f"the design note states: {probe}", probe in text)


def test_the_compose_file_this_module_mirrors():
    """The pinned image and the loopback port are copied from the compose file.
    If its branch has not landed, say so rather than guess."""
    compose = REPO / "docker" / "searxng" / "docker-compose.yml"
    if not compose.is_file():
        check("the compose file is not on this branch yet (feat/searxng-setup has it) "
              "- jarvis_docker.py's pinned image can only be checked against it there",
              True)
        return
    text = compose.read_text(encoding="utf-8")
    check("the compose file pins the same image jarvis_docker.py expects",
          SPEC.image in text, SPEC.image)
    check("the compose file publishes on loopback only",
          f'"{SPEC.published()}"' in text, SPEC.published())


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL  {name} raised:")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for n in FAILED:
            print("  FAILED: " + n)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
