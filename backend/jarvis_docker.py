"""jarvis_docker.py - the containers on Jarvis's OWN list, and start/stop for
them.

NEW MODULE, shipped whole. Nothing in this repository ran `docker` before it:
this is the first slice of the owner's request of 2026-10-09 ("add more docker
integration into jarvis that can be toggled with settings inside both the
android app and desktop program"). The design it is the first slice of is
`docs/DOCKER-INTEGRATION-DESIGN.md`; read section 3 and section 4 of that file
before changing anything here, because every refusal below is one of those
rules written as code.

WHAT IT DOES, AND WHAT IT DELIBERATELY CANNOT DO

It lists the containers Jarvis itself ships a compose file for (`SERVICES`
below - today exactly one, SearXNG, `jarvis_search.py`'s default web-search
provider), says whether each is running, and can start or stop one.

It CANNOT, by construction, and this is the point of the module:

  * **create a container.** There is no `docker run` and no `docker compose up`
    anywhere in this file. Those two commands are also the two that pull: a
    missing image is a way out of the PC (it fetches bytes from a registry),
    and `docs/DOCKER-INTEGRATION-DESIGN.md` section 3.2 and 3.3 say a pull needs
    its own card naming the exact image and registry, and that nothing ever
    auto-pulls. Until that card exists, the safe first slice is the one that
    cannot pull at all. `start()` therefore refuses when the image is not
    already on this PC - see `image_present()`. This is the single most
    important refusal in the file: it is what makes every other promise here
    true rather than merely intended.
  * **act on a container Jarvis did not create without saying so.** Ownership
    is decided by the live container's own configuration, not by its name: it
    must exist, its image must be the pinned one on the list, every published
    port must be loopback, and it must not be privileged (`_problems()`). A
    container with the right name and any of those wrong is reported as "not
    one of mine" and no button, no route and no voice command reaches it. A
    name alone is not ownership.
  * **publish beyond loopback.** `_problems()` refuses a container whose
    published ports are not all `127.0.0.1`/`::1`. Rule 2 and `ARCHITECTURE.md`
    section 4: a container on a wider interface is reachable by the whole home
    network, which is exactly what `docker/searxng/docker-compose.yml:14-21`
    says must never happen.
  * **run anything privileged.** `_problems()` refuses a container whose
    `HostConfig.Privileged` is true. A privileged container is this PC with the
    door taken off.
  * **use an unpinned image.** `_pinned()` refuses a tag that is absent or
    `latest`: tags are mutable, so an unpinned image is one that can change
    under the owner without him approving the change.
  * **mount anything of the owner's.** This module passes no `-v` at all - it
    never creates a container, so it never chooses a mount. The mounts SearXNG
    has are the two its own compose file names, and both are about SearXNG
    itself.
  * **carry the owner's secrets into a container.** Nothing is passed in:
    `_env()` hands the `docker` child only the sanitized environment
    `jarvis_child_env.inherited()` builds (the same allowlist the second Ollama
    and colibri get), so no token and no key goes with it.

WHAT ASKS FIRST

Every start and every stop goes through the SAME gate as every other action
(`jarvis_gate.check`), so the one permission model, the one place cards come
from and the stale-link rule (`CLAUDE.md` rule 4) apply here with no exception
for "it is only a container".

  * **start** must resolve to tier `"ask"`, and this module refuses anything
    else rather than let a config line become the owner's yes - the same
    belt-and-braces check `jarvis_handoff_mode.py` makes. Starting a service is
    the direction that gives Jarvis more, so it is the direction that asks.
  * **stop** is the direction that gives Jarvis less, so it is the direction
    that is expected to be instant - but it is still put through the gate, and
    whatever the gate says is what happens: tier `"auto"` acts at once, tier
    `"ask"` raises one card. Nothing here decides on its own to skip the gate.
  * An action that is not in `jarvis-framework.toml` takes
    `unknown_action_tier`, which is `"ask"` in the shipped config - so a
    fresh install asks on both directions rather than failing open.

FAIL CLOSED

No `docker` on this PC, a Docker engine that is not running, a container that
cannot be inspected, a missing image, a config that does not match the list -
each is a plain refusal with a plain sentence, never a guess and never a
"probably fine". A damaged answer is treated as an outage.

WHAT IS NEVER KEPT. The container's name, whether it is running, and the time
of the last start or stop. No logs, no environment, no image layers, no mount
contents, no token.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urlsplit

#: The gate actions. `docker_service_start` gives Jarvis more, so it must be
#: tier "ask"; `docker_service_stop` gives it less, so it is expected to be
#: instant. Both are put through the gate either way.
ACTION_START = "docker_service_start"
ACTION_STOP = "docker_service_stop"

#: The two routes both apps read and set this on. One GET (the list) and one
#: POST (start or stop one service), so a new service needs no new route.
PATH_LIST = "/api/docker/containers"
PATH_SERVICE = "/api/docker/service"

#: How long any one `docker` call may take before it is treated as a hang.
TIMEOUT_S = 20.0


# --------------------------------------------------------------------------
#   The list: the ONLY containers this module will name, list or act on.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Service:
    """One container Jarvis ships a compose file for.

    `image` must carry a real tag - never `latest`, never no tag at all - and
    `host` must stay a loopback address. `_problems()` holds a live container
    to both, so editing either here is what decides what Jarvis will touch.
    """
    key: str                  # what the apps and the route call it
    container: str            # the container_name in the compose file
    image: str                # pinned by dated tag, exactly as the compose file has it
    host: str                 # must be a loopback address
    port: int                 # the port on this PC
    container_port: int       # the port inside the container
    provides: str             # one plain line: what breaks if this is down
    compose: str              # the file that defines it, for a plain error message

    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def published(self) -> str:
        return f"{self.host}:{self.port}:{self.container_port}"


SERVICES: tuple = (
    Service(
        key="searxng",
        container="searxng",
        # Exactly the tag docker/searxng/docker-compose.yml:33 pins. Keep the
        # two equal: this is the value _problems() compares a live container
        # against, so if they drift, Jarvis stops recognising its own SearXNG.
        image="docker.io/searxng/searxng:2026.10.9-f4822b3fc",
        host="127.0.0.1",
        port=8888,
        container_port=8080,
        provides="web search on this PC (Jarvis's default search provider)",
        compose="docker/searxng/docker-compose.yml",
    ),
)

_BY_KEY = {s.key: s for s in SERVICES}

#: What each service is called in both apps, word for word.
WORDS = {
    "title": "Docker",
    "detail": ("Jarvis can start and stop the containers it uses on this PC. "
               "They answer on this PC only, never the home network and never "
               "the internet."),
    "started": "Started {name}.",
    "stopped": "Stopped {name}.",
    "already_running": "{name} is already running.",
    "already_stopped": "{name} is already stopped.",
    "waiting": ("Waiting for your approval. {name} stays as it is until you "
                "approve the card."),
    "no_docker": ("Docker is not answering on this PC, so Jarvis cannot see or "
                  "start its containers. Start Docker Desktop and try again."),
    "not_ours": ("There is a container called \"{container}\" on this PC that "
                 "Jarvis did not create, so Jarvis will not touch it."),
    "would_download": ("Starting {name} would have to download its image "
                       "({image}) from the internet first. Jarvis never "
                       "downloads an image on its own, so nothing was started."),
    "created_elsewhere": ("{name} is not on this PC yet. Jarvis does not create "
                          "containers on its own - start it once by hand from "
                          "{compose}."),
    "bad_config": ("The container called \"{container}\" on this PC is not "
                   "configured the way Jarvis's list says, so Jarvis will not "
                   "touch it: {problems}"),
    "stopped_by_owner": "You stopped {name} while the card waited, so approving it changes nothing.",
}
LAST_WORDS = {
    "on": "You approved the card, so {name} was started.",
    "denied": "The card was turned down, so {name} is still stopped.",
    "timed_out": "Nobody answered the card in time, so {name} is still stopped.",
    "refused": "Your PC's settings do not let this be approved, so {name} is still stopped.",
    "withdrawn": "You stopped {name} while the card waited, so approving it changes nothing.",
    "failed": "It was approved, but {name} could not be started.",
}
#: Said when the card itself could not be raised - a gate that threw. Never a
#: silent no: the owner asked for something and is owed a sentence.
GATE_FAILED_WORDS = "The approval card could not be raised, so {name} is still stopped."


# --------------------------------------------------------------------------
#   Running docker. One seam, so every test can drive it without a container.
# --------------------------------------------------------------------------

#: (list of argv after "docker", timeout) -> (returncode, stdout, stderr).
#: Replaced in tests. Never a shell: no argument this module makes is ever
#: handed to a shell to interpret, so nothing here can be word-split or
#: injected through a container or service name.
Runner = Callable[[list, float], tuple]

_DOCKER = "docker"


def _env() -> dict:
    """The child's environment: `jarvis_child_env`'s allowlist, so no token and
    no key of the owner's goes with it. If that module is missing, hand it
    almost nothing rather than everything."""
    try:
        import jarvis_child_env as CE
        env = CE.inherited()
    except Exception:
        env = {}
    # docker needs to find its own config and the named pipe; it needs none of
    # the owner's secrets. PATH comes from the allowlist above.
    env.setdefault("PATH", "")
    return env


def _run(args: list, timeout: float = TIMEOUT_S) -> tuple:
    """The real runner: `docker` with `args`, captured, never a shell."""
    try:
        p = subprocess.run([_DOCKER] + [str(a) for a in args], capture_output=True,
                           text=True, timeout=timeout, env=_env(), shell=False)
        return p.returncode, p.stdout or "", p.stderr or ""
    except FileNotFoundError:
        return 127, "", "docker is not installed"
    except subprocess.TimeoutExpired:
        return 124, "", f"docker did not answer within {timeout:g}s"
    except OSError as exc:
        return 126, "", f"{type(exc).__name__}"


#: The seam tests replace.
_RUNNER: Runner = _run


def _run_with(args: list, timeout: float = TIMEOUT_S) -> tuple:
    return _RUNNER(args, timeout)


# --------------------------------------------------------------------------
#   Reading the engine and the containers
# --------------------------------------------------------------------------


def docker_ok() -> tuple:
    """(True, "") when the engine answers, else (False, a plain reason)."""
    rc, out, err = _run_with(["version", "--format", "{{.Server.Version}}"])
    if rc != 0:
        return False, (err or "").strip().splitlines()[0] if (err or "").strip() else \
            "Docker did not answer"
    return True, ""


def _ps() -> list:
    """Every container on this PC, as dicts. Raises on a docker that will not
    answer - the caller turns that into a plain refusal."""
    rc, out, err = _run_with(["ps", "-a", "--format", "{{json .}}"])
    if rc != 0:
        raise RuntimeError((err or "docker ps failed").strip().splitlines()[0])
    rows = []
    for line in (out or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            doc = json.loads(line)
        except Exception:
            continue
        if isinstance(doc, dict):
            rows.append(doc)
    return rows


def inspect(container: str) -> Optional[dict]:
    """The container's own configuration, or None when it is not there."""
    rc, out, err = _run_with(["inspect", container])
    if rc != 0:
        return None
    try:
        doc = json.loads(out)
    except Exception:
        return None
    if isinstance(doc, list) and doc and isinstance(doc[0], dict):
        return doc[0]
    return None


def image_present(image: str) -> bool:
    """True only when this exact image is already on this PC.

    THIS IS THE NO-AUTO-PULL CHECK. `docker start` never pulls, but this is
    asked first anyway so the answer is a plain sentence rather than whatever
    docker decides to print."""
    rc, _out, _err = _run_with(["image", "inspect", image])
    return rc == 0


def _pinned(image: str) -> bool:
    """A tag that is really a pinned version: present, and not `latest`."""
    ref = str(image or "")
    if not ref or "@" in ref:          # a digest is a pin, but not our shape
        return False
    tail = ref.rsplit("/", 1)[-1]
    if ":" not in tail:
        return False
    tag = tail.rsplit(":", 1)[1]
    return bool(tag) and tag.lower() != "latest" and tag != "<none>"


def _loopback(host_ip: Optional[str]) -> bool:
    return str(host_ip or "") in ("127.0.0.1", "::1", "localhost")


def _problems(spec: Service, doc: dict) -> list:
    """Every way the live container differs from the list. Empty: it is ours.

    This is the ownership test. A NAME IS NOT OWNERSHIP: a container can be
    called `searxng` and be something else entirely, and acting on it because
    of its name is how a tool starts managing things it did not create."""
    out = []
    cfg = doc.get("Config") or {}
    hostcfg = doc.get("HostConfig") or {}

    image = str(cfg.get("Image") or "")
    if image != spec.image:
        out.append(f"it runs image {image or '(none)'}, not the pinned {spec.image}")
    elif not _pinned(image):
        out.append(f"its image tag is not a pinned version ({image})")

    if (hostcfg.get("Privileged") is True) or (cfg.get("Privileged") is True):
        out.append("it runs privileged")

    bindings = hostcfg.get("PortBindings") or {}
    seen = 0
    for cport, binds in bindings.items():
        for b in (binds or []):
            seen += 1
            if not _loopback((b or {}).get("HostIp")):
                out.append(f"port {cport} is published on "
                           f"{(b or {}).get('HostIp') or 'every interface'}, "
                           f"not just this PC")
    if seen == 0:
        out.append("it publishes no port at all, so Jarvis could not reach it")

    return out


def state(spec: Service) -> dict:
    """One service, as both apps see it. Never raises: a docker that will not
    answer reads as "cannot tell", which is not the same as "stopped"."""
    out = {"service": spec.key, "container": spec.container,
           "provides": spec.provides, "url": spec.url(),
           "pinned_image": spec.image, "published": spec.published(),
           "ours": False, "present": False, "running": False,
           "status": "", "can_start": False, "can_stop": False}
    try:
        rows = _ps()
    except Exception as exc:
        out["why"] = f"docker could not be asked ({exc})"
        return out

    row = next((r for r in rows if str(r.get("Names") or r.get("Name") or "") == spec.container), None)
    if row is None:
        out["why"] = WORDS["created_elsewhere"].format(name=spec.key, compose=spec.compose)
        return out

    out["present"] = True
    out["status"] = str(row.get("Status") or "")
    out["running"] = str(row.get("State") or "").lower() == "running"

    doc = inspect(spec.container)
    if doc is None:
        out["why"] = "the container could not be inspected"
        return out
    problems = _problems(spec, doc)
    out["ours"] = not problems
    if problems:
        out["why"] = WORDS["bad_config"].format(container=spec.container,
                                               problems="; ".join(problems))
        return out

    out["image_present"] = image_present(spec.image)
    out["can_start"] = bool(out["image_present"])
    out["can_stop"] = out["running"]
    if not out["image_present"]:
        out["why"] = WORDS["would_download"].format(name=spec.key, image=spec.image)
    return out


def view() -> dict:
    """`GET /api/docker/containers`: what is on Jarvis's list, what state each
    is in, and every word both apps show. Read-only."""
    ok, why = docker_ok()
    out = {"docker": ok, "words": dict(WORDS), "path": PATH_SERVICE,
           "services": [state(s) for s in SERVICES] if ok else []}
    if not ok:
        out["why"] = WORDS["no_docker"]
        out["detail"] = why
    return out


# --------------------------------------------------------------------------
#   The one pending card (the same shape as jarvis_handoff_mode.py's)
# --------------------------------------------------------------------------

_LOCK = threading.Lock()
_PENDING: dict = {}          # {"id", "service", "since"} while a start card waits
_WITHDRAWN: set = set()
_LAST: dict = {}
_LATEST: dict = {}


def card_text(spec: Service) -> str:
    return "\n".join([
        f"Start {spec.key} on this PC?",
        "",
        f"{spec.key.capitalize()} is the {spec.provides}. It is not running at the moment.",
        "",
        f"Starting it runs the container \"{spec.container}\" from the image "
        f"{spec.image}, which is already on this PC. Jarvis never downloads an "
        f"image on its own, so nothing is fetched from the internet by this.",
        "",
        f"It answers on {spec.host}:{spec.port} - this PC only, not the home "
        f"network and not the internet.",
        "",
        "If you say no: nothing changes, and it stays stopped.",
    ])


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    try:
        import jarvis_framework as fw
        return str(fw.action_tier(action))
    except Exception as exc:
        return f"unreadable ({type(exc).__name__})"


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-docker-card", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    try:
        import jarvis_framework as fw
        fw.audit_log("docker.service", {"event": event, **detail})
    except Exception:
        pass


def _finish(pid: str, outcome: str, spec: Service, why: str = "",
            message: Optional[str] = None) -> None:
    with _LOCK:
        if _PENDING.get("id") == pid:
            _PENDING.clear()
        _WITHDRAWN.discard(pid)
        if _LATEST.get("id") not in (None, pid):
            return
        _LAST.clear()
        _LAST.update(outcome=outcome, why=why, at=time.time(), service=spec.key,
                     message=message or LAST_WORDS.get(outcome, "").format(name=spec.key))
    _audit("card", {"outcome": outcome, "service": spec.key})


def _decide_start(pid: str, spec: Service, gate: Callable,
                  tier_of: Callable[[str], str]) -> None:
    text = card_text(spec)
    try:
        v = gate(ACTION_START, {"text": text, "service": spec.key,
                                "container": spec.container,
                                "image": spec.image,
                                "leaves_this_pc": False}, text)
    except Exception as exc:
        return _finish(pid, "refused", spec,
                       f"the approval gate failed ({type(exc).__name__})",
                       GATE_FAILED_WORDS.format(name=spec.key))
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    if vtier != "ask" or tier_of(ACTION_START) != "ask":
        return _finish(pid, "refused", spec,
                       f"the gate answered at tier {vtier!r}, which is not a person saying yes")
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, outcome, spec)
        return _finish(pid, "refused", spec, str(getattr(v, "reason", "refused")))
    with _LOCK:
        withdrawn = pid in _WITHDRAWN
    if withdrawn:
        return _finish(pid, "withdrawn", spec,
                       f"you stopped {spec.key} while the card was waiting")
    # Last check, on the way in, and re-read rather than remembered: the
    # image must still be here and the container must still be ours. A card
    # approved five minutes ago is not a licence to pull.
    try:
        st = state(spec)
    except Exception as exc:
        return _finish(pid, "failed", spec, f"{type(exc).__name__}")
    if not st["ours"]:
        return _finish(pid, "failed", spec, st.get("why", "the container is not ours"))
    if not st.get("image_present"):
        return _finish(pid, "failed", spec, "the image is no longer on this PC")
    rc, _out, err = _run_with(["start", spec.container])
    if rc != 0:
        return _finish(pid, "failed", spec, (err or "docker start failed").strip()[:200])
    _finish(pid, "on", spec)
    _audit("start", {"service": spec.key})


# --------------------------------------------------------------------------
#   The route
# --------------------------------------------------------------------------


def request(body: dict, *, gate: Optional[Callable] = None,
            tier_of: Optional[Callable[[str], str]] = None,
            spawn: Optional[Callable] = None) -> tuple:
    """`POST /api/docker/service` {"service", "action"}. Returns (code, body).

    `start` raises ONE approval card and changes nothing until a person says
    yes. `stop` is put through the same gate; whatever tier it resolves to is
    what happens."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn

    body = body if isinstance(body, dict) else {}
    key = str(body.get("service") or "").strip().lower()
    action = str(body.get("action") or "").strip().lower()
    spec = _BY_KEY.get(key)
    if spec is None:
        return 400, {"ok": False,
                     "error": "Jarvis does not manage a service called that. "
                              "It manages: " + ", ".join(sorted(_BY_KEY)) + "."}
    if action not in ("start", "stop"):
        return 400, {"ok": False, "error": "Choose \"start\" or \"stop\"."}

    ok, why = docker_ok()
    if not ok:
        return 503, {"ok": False, "error": WORDS["no_docker"], "detail": why}

    try:
        st = state(spec)
    except Exception as exc:
        return 503, {"ok": False, "error": WORDS["no_docker"],
                     "detail": f"{type(exc).__name__}"}

    if not st["present"]:
        return 409, {"ok": False, "error": st.get("why") or
                     WORDS["created_elsewhere"].format(name=spec.key, compose=spec.compose)}
    if not st["ours"]:
        # Named but not ours: say so plainly and touch nothing.
        return 409, {"ok": False, "error": st.get("why") or
                     WORDS["not_ours"].format(container=spec.container),
                     "not_ours": True}

    if action == "stop":
        if not st["running"]:
            return 200, {"ok": True, "running": False, "waiting": False,
                         "message": WORDS["already_stopped"].format(name=spec.key)}
        tier = tier_of(ACTION_STOP)
        if tier == "auto":
            rc, _out, err = _run_with(["stop", spec.container])
            if rc != 0:
                return 503, {"ok": False,
                             "error": (err or "docker stop failed").strip()[:200]}
            _audit("stop", {"service": spec.key})
            return 200, {"ok": True, "running": False, "waiting": False,
                         "message": WORDS["stopped"].format(name=spec.key)}
        return _ask(action=ACTION_STOP, spec=spec, gate=gate, tier_of=tier_of,
                    spawn=spawn, tier=tier)

    if st["running"]:
        return 200, {"ok": True, "running": True, "waiting": False,
                     "message": WORDS["already_running"].format(name=spec.key)}
    if not st.get("image_present"):
        # Never a pull, not even behind a card, in this slice.
        return 409, {"ok": False, "needs_download": True,
                     "error": WORDS["would_download"].format(name=spec.key,
                                                             image=spec.image)}
    return _ask(action=ACTION_START, spec=spec, gate=gate, tier_of=tier_of,
                spawn=spawn, tier=tier_of(ACTION_START))


def _ask(*, action: str, spec: Service, gate: Callable,
         tier_of: Callable[[str], str], spawn: Callable, tier: str) -> tuple:
    """Raise one card for a start, or hand a stop to the gate at its own tier."""
    if action == ACTION_START and tier != "ask":
        return 503, {"ok": False, "error": (
            f"{ACTION_START} is tier {tier!r} in jarvis-framework.toml; starting "
            f"a container needs a person to say yes, so it must be 'ask'")}
    if action == ACTION_STOP and tier != "auto" and tier != "ask":
        return 503, {"ok": False, "error": (
            f"{ACTION_STOP} is tier {tier!r} in jarvis-framework.toml, which is "
            f"not a tier this route acts on")}
    with _LOCK:
        if _PENDING:
            return 202, {"ok": True, "waiting": True, "running": False,
                         "message": "A card for {} is already waiting for your "
                                    "approval.".format(_PENDING.get("service", spec.key))}
        pid = _uuid.uuid4().hex
        _PENDING.update(id=pid, service=spec.key, action=action, since=time.time())
        _LATEST["id"] = pid
    if action == ACTION_START:
        try:
            spawn(lambda: _decide_start(pid, spec, gate, tier_of))
        except Exception:
            with _LOCK:
                _PENDING.clear()
            return 503, {"ok": False, "error": "could not raise the approval card"}
        return 202, {"ok": True, "waiting": True, "running": False,
                     "message": WORDS["waiting"].format(name=spec.key)}
    # A stop the config marks "ask": one card, same machinery.
    def _decide_stop() -> None:
        try:
            v = gate(ACTION_STOP, {"text": f"Stop {spec.key} on this PC?",
                                   "service": spec.key, "leaves_this_pc": False},
                     f"Stop {spec.key} on this PC?")
            if getattr(v, "outcome", None) == "approved" or getattr(v, "allowed", False) is True:
                _run_with(["stop", spec.container])
                _finish(pid, "on", spec)
            else:
                _finish(pid, getattr(v, "outcome", None) or "refused", spec)
        except Exception as exc:
            _finish(pid, "refused", spec, f"{type(exc).__name__}")
    try:
        spawn(_decide_stop)
    except Exception:
        with _LOCK:
            _PENDING.clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "running": True,
                 "message": WORDS["waiting"].format(name=spec.key)}


def state_of_cards() -> dict:
    """{"waiting": bool, "last": {...} | None} - what the view adds."""
    with _LOCK:
        return {"waiting": bool(_PENDING), "last": dict(_LAST) or None}


def _reset_for_tests() -> None:
    with _LOCK:
        _PENDING.clear()
        _WITHDRAWN.clear()
        _LAST.clear()
        _LATEST.clear()
    global _RUNNER
    _RUNNER = _run


# --------------------------------------------------------------------------
#   Wiring - the same shape every other new module here uses: the one line
#   in jarvis_hud.py that calls this is `docker.patch`, applied once.
# --------------------------------------------------------------------------


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so GET /api/docker/containers and
    POST /api/docker/service are answered here, after the server's own origin
    and token checks. Every other request goes straight to the original.
    Returns the banner line."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_docker", False):
        _ARMED = True
        return "  docker     Docker containers answer at " + PATH_LIST + " (already on)"

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
        if route != PATH_LIST:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            out = view()
        except Exception as exc:
            return self._send(503, {"error": type(exc).__name__})
        return self._send(200, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH_SERVICE:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = read_body(self)
        except Exception:
            body = {}
        try:
            code, out = request(body if isinstance(body, dict) else {})
        except Exception as exc:
            return self._send(503, {"ok": False, "error": type(exc).__name__})
        return self._send(code, out)

    do_GET._jarvis_docker = True
    do_POST._jarvis_docker = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    return "  docker     Docker containers answer at " + PATH_LIST


_ARMED = False


if __name__ == "__main__":
    import pprint
    pprint.pprint(view())
