"""VoiceStudio, as a SEPARATE program on this PC that Jarvis only ever CALLS.

NEW MODULE, shipped whole. No patch, no route, no card and no import of
VoiceStudio's code: this file speaks HTTP to `127.0.0.1:11439` and nothing
else, which is the one arrangement the licence lane called CLEAN
(EVAL\\REPORT-LEGAL.md section 2a - the AGPL-3.0 program stays a separate,
unmodified program, so nothing is conveyed and nothing is derived here).

WHY THIS SHAPE (the owner's Q3/Q4/Q5, forwarded 2026-11-04)
  * Q3. "Jarvis starts it when needed (sidecar on demand)". VoiceStudio is
    big - ~1.95 GB of the 8 GB card resident, 546 MB of RAM idle, 3.04 GB of
    weights on disk - and the measured coexistence verdict is CONTENTION:
    beside Jarvis's own two resident models the box had 382 MiB free at its
    peak and the driver paged ~1.9 GB into system RAM (MEASURE\\RESULTS.md
    section 4). So it is NEVER resident beside Jarvis: no boot task, no
    service, no import at start-up. It runs when someone starts it, and it is
    asked to release its model when it is done.
  * Q4. The two model licences are accepted by the OWNER, once, in
    VoiceStudio's own terms - never by this module. Until they are, every
    speech request is HTTP 403 and this module says so in plain words and
    names the exact two repositories (section 3 of RESULTS.md).
  * Q5. Nothing here is AGPL, nothing here is VoiceStudio's code, and no
    weights are shipped or fetched. The licence class of every engine and
    voice is stated in plain words: `commercial_ok` only where a model is
    really cleared (currently NONE, because VoiceStudio's own paperwork
    clears no model - REPORT-LEGAL.md section 3.1), otherwise
    `personal_non_commercial_only`, which is this project's Rule 5.

WHAT IT SENDS, IN ONE SENTENCE: the text you asked it to speak, to
`127.0.0.1:11439` - this PC and nowhere else. No memory, no conversation, no
file, no picture, no token, no key. It opens no route and raises no card; the
caller decides what a refusal means (the speech code's rule is "never
silence": fall back and say why).

THE MEASURED NUMBERS IT IS BUILT AROUND (2026-11-04, this PC; every one is
also a constant below, so `tools/measure_voicestudio.py` re-reports the same
numbers rather than copying them):

    first start -> /health 200     32.06 s   (later start 16.66 s)
    model preload after health      8.92 s
    first ever speech call        267.97 s   (+ 3.043 GB of weights)
    warm speech call          1.70 - 1.98 s   for ~2.5 s of audio (RTF 0.66-0.79)
    resident VRAM                  1,945 MB  app-reported (~1,750-1,900 MiB delta)
    idle RAM                         546 MB  working set
    peak free VRAM on the 8 GB card   382 MiB  -> CONTENTION

TWO START-UP RACES IT HANDLES, both measured, both worth not misreading:
  1. `/health` answers 503 with a step and a label while it starts, then 200.
     A caller that treated "not 200" as "dead" would report a healthy start
     as a failure. `health()` and `wait_for_model_loaded()` report the step.
  2. A request fired the INSTANT `/health` turns 200 can hit a half-imported
     `transformers` and answer 400 `cannot import name 'AutoFeatureExtractor'`.
     The next request succeeds. `synthesize()` retries that ONE measured
     shape a bounded number of times and says it did; it is not a blanket
     retry of every error.

HOW IT REPORTS, AND WHAT IT NEVER DOES
  * Every public function returns plain data and honest words. `health()`,
    `wait_for_model_loaded()`, `stop()` and `first_run_license_gate()` never
    raise for "not running" - they return `running: False` and a sentence a
    person can act on. `synthesize()` raises, because a caller asking for
    audio must decide what to do instead (the existing speech code answers
    with its own voice and says why).
  * `stop()` asks VoiceStudio to release ITS OWN model by the ids VoiceStudio
    itself reports at `/model/loaded`. It cannot unload an Ollama lane: the
    only socket it has is 11439, and the ids come from the server, never
    from this file. Jarvis's model lanes are not touched, ever.
  * It never starts a process, never installs anything, never downloads a
    weight, and never accepts a licence. Those are the owner's actions, done
    through the owner's own tools (`tools/voicestudio_sidecar.ps1`).
  * It never goes through a proxy: every call is opened with an EMPTY proxy
    table (`jarvis_local_http.opener()`, the CONN-1 fix), because a request
    to a program on this PC must not travel to another machine first.

OFF BY DEFAULT, WITH ITS OWN SWITCH, AND SINCE 2026-11-13 A TYPED ONE.
`[voicestudio] enabled` in `jarvis-framework.toml` is `false` in the shipped
template. `synthesize()` refuses while it is false; the read-only questions (is
it running, what can it speak with, has the licence been accepted) still
answer, because asking is not using.

THE SWITCH IS NOW REACHABLE THREE WAYS, and all three are the same write:
`set_enabled()` below (the raw writer), the typed sentences "turn on
voicestudio" / "turn off voicestudio" and their state question (through
`request_enabled()`, so ON is ONE `change_own_config` card plus Windows Hello
and OFF is instant), and the desktop Settings row ("A second voice program
(VoiceStudio)", Settings, The PC itself) which reads and writes the same value.
Before 2026-11-13 the only door was a hand edit of the settings file, which the
awareness audit measured as the one real control gap left in the project (its
GAP-9/C-7). What is STILL not built is the speaking-voice wiring:
`jarvis_speech.py` does not import this module yet, so switching it on alone
changes nothing you would hear. That wiring is the named next slice.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

#: Where VoiceStudio's backend listens when `tools/voicestudio_sidecar.ps1`
#: starts it. 11439 is the next free number in Jarvis's own local block
#: (11434 everyday, 11435 second card, 11436 third card, 11437 picture
#: reader) and is NOT VoiceStudio's own 3900 default, so the owner's own
#: VoiceStudio window can run beside it without a collision (RESULTS.md
#: section 2 measured 127.0.0.1:11439 only; no 0.0.0.0/LAN socket).
HOST = "127.0.0.1"
PORT = 11439
BASE_URL = f"http://{HOST}:{PORT}"

#: Jarvis's own local services. `_base()` REFUSES every one of them, so a
#: later edit cannot quietly point this client at a model lane and ask it to
#: unload something. The numbers are the ones docs/MODEL-TOPOLOGY.md and
#: docs/JARVIS-API.md give: 11434 everyday Ollama, 11435 the second card,
#: 11436 the third card, 11437 the picture reader, 11450 the pooled coder.
#: 11439 is VoiceStudio's and nobody else's.
JARVIS_LANE_PORTS = (11434, 11435, 11436, 11437, 11450)

#: The switch. Off in the shipped template; see the module docstring.
SWITCH_SECTION = "voicestudio"
SWITCH_KEY = "enabled"

#: The measured numbers, one place, cited. RESULTS.md is the evidence file;
#: it lives outside this repository's tree (`.dsh-scratch/`), which is why
#: each figure is also written down here with its section.
STARTUP_FIRST_SECONDS = 32.06      # RESULTS.md section 2: spawn -> /health 200
STARTUP_WARM_SECONDS = 16.66       # RESULTS.md section 2: DB already migrated
MODEL_PRELOAD_SECONDS = 8.92       # RESULTS.md section 2: the preload after health
FIRST_CALL_SECONDS = 267.97        # RESULTS.md section 4: download + load + generate
WARM_CALL_SECONDS = (1.70, 1.98)   # RESULTS.md section 4: warm calls, ~2.5 s audio
WARM_CALL_RTF = (0.66, 0.79)       # RESULTS.md section 4: real-time factor
RESIDENT_VRAM_MB = 1945.3          # RESULTS.md section 4: /model/loaded reports it
IDLE_RAM_MB = 546.2                # RESULTS.md section 2: working set, no model
WEIGHTS_BYTES = 3_043_000_000      # RESULTS.md section 4: 3.043 GB on the first call
MEASURED_PEAK_FREE_MIB = 382       # RESULTS.md section 4: the box peak -> CONTENTION

#: How long a caller should wait before calling a start a failure. Measured
#: 32.06 s first, 16.66 s later: 90 s leaves room for a slow disk and still
#: ends in words rather than a hang.
STARTUP_TIMEOUT_SECONDS = 90.0

#: The two model licences that must be accepted once, in VoiceStudio's own
#: terms, or EVERY speech call is 403 (RESULTS.md section 3). The labels are
#: the server's own recorded labels, so the words cannot drift from what the
#: screen would say.
LICENCE_REPOS = ("k2-fsa/OmniVoice", "eustlb/higgs-audio-v2-tokenizer")
LICENCE_LABELS = {
    "k2-fsa/OmniVoice": "CC-BY-NC (version unspecified); Higgs Audio 2; Meta Llama 3",
    "eustlb/higgs-audio-v2-tokenizer": "no licence was found in its metadata (NOASSERTION)",
}

#: The ONLY two licence classes this module may report. `commercial_ok` is
#: for Apache-2.0/MIT weights whose terms were actually reviewed;
#: `personal_non_commercial_only` is everything else, which is this project's
#: Rule 5 (non-commercial build). Nothing is `commercial_ok` today, and that
#: is not an omission: VoiceStudio's own inventory says no model record makes
#: a commercial-use claim (REPORT-LEGAL.md section 3.1).
LICENSE_CLASSES = ("commercial_ok", "personal_non_commercial_only")
DEFAULT_LICENSE_CLASS = "personal_non_commercial_only"

#: Engines whose terms ARE reviewed and permit commercial output. Empty on
#: purpose - see LICENSE_CLASSES. Adding an engine here is a licensing
#: decision with evidence, never a convenience.
COMMERCIALLY_CLEARED_ENGINES: tuple = ()

#: Per-engine notes. Only the engine this PC measured (omnivoice) has a note
#: written from evidence; every other engine falls back to the fail-closed
#: sentence below. VoiceStudio lists 16 engines and its own paperwork clears
#: none of them, so "not reviewed here" is the honest answer for all of them.
_ENGINE_NOTES = {
    "omnivoice": ("CC-BY-NC (version unspecified) + Higgs Audio 2 + Meta Llama 3 terms, "
                  "measured on this PC 2026-11-04: personal, non-commercial use only."),
}
_ENGINE_NOTE_UNREVIEWED = (
    "Not reviewed on this PC. VoiceStudio's own inventory clears no model, so treat it "
    "as personal, non-commercial use only (this project's Rule 5).")
_VOICE_NOTE = (
    "A voice is data on this PC; the licence that matters is the engine that speaks it, "
    "and every engine here is personal, non-commercial use only today.")

#: The measured cold-start 400. A request fired the instant /health turns 200
#: can hit a half-imported transformers; the next one succeeds (RESULTS.md
#: section 4). Matched on the ONE measured phrase, never as a blanket retry.
_COLD_START_MARKS = ("cannot import name 'AutoFeatureExtractor'", "cannot import name",
                     "AutoFeatureExtractor")
_COLD_START_TRIES = 3
_COLD_START_WAIT_SECONDS = 2.0

#: How much of a server body may appear in an error sentence. Enough to be
#: useful, short enough that a log line stays a log line.
_BODY_IN_WORDS = 300

START_COMMAND = ("powershell -NoProfile -ExecutionPolicy Bypass -File "
                 "tools\\voicestudio_sidecar.ps1 -Start")


# --------------------------------------------------------------------------
#   Errors: each one carries the plain words a caller can show a person
# --------------------------------------------------------------------------

class VoiceStudioError(Exception):
    """Something about VoiceStudio went wrong, with words a person can read."""

    def __init__(self, words: str, **detail):
        super().__init__(words)
        self.words = words
        self.detail = detail


class VoiceStudioRefused(VoiceStudioError):
    """This module will not make the call at all (a non-loopback address)."""


class VoiceStudioUnavailable(VoiceStudioError):
    """The switch is off, or nothing is listening on 11439."""


class VoiceStudioLicenceGate(VoiceStudioError):
    """VoiceStudio answered 403 because a model licence has not been accepted."""

    def __init__(self, words: str, gate: dict = None):
        super().__init__(words)
        self.gate = dict(gate or {})


# --------------------------------------------------------------------------
#   The switch (off by default): [voicestudio] enabled in the settings file
# --------------------------------------------------------------------------

def _framework_section() -> dict:
    """`[voicestudio]` from the owner's settings file, or {}.

    Guarded and lazy, exactly like `jarvis_vault_organizer._framework_section`:
    this module loads on a PC whose framework module is absent (the suites
    exercise it that way), and an unreadable file means OFF - the fail-closed
    direction for a program that would take ~1.95 GB of the graphics card.
    """
    try:
        import jarvis_framework as fw
        return (fw.load_framework() or {}).get(SWITCH_SECTION, {}) or {}
    except Exception:                                     # noqa: BLE001
        return {}


def enabled() -> bool:
    """Is VoiceStudio switched on? False unless the owner's file says true."""
    return _framework_section().get(SWITCH_KEY) is True


#: The setting's own dotted name, the same one `contract/feature-controls.json`
#: records and the one a Settings row is keyed by.
SETTING_KEY = f"{SWITCH_SECTION}.{SWITCH_KEY}"

#: The one approval action turning it ON goes through (tier "ask" in the shipped
#: `[autonomy.tiers]`). Windows Hello is that card's PC half.
ACTION_ON = "change_own_config"

STATE_ON = (
    f"VoiceStudio is on. Its switch is [{SWITCH_SECTION}] {SWITCH_KEY} in "
    f"jarvis-framework.toml. The program itself is still started by hand with "
    f"tools\\voicestudio_sidecar.ps1 -Start, and it is not connected to the voice "
    f"Jarvis answers in yet.")
STATE_OFF = (
    f"VoiceStudio is off. Its switch is [{SWITCH_SECTION}] {SWITCH_KEY} in "
    f"jarvis-framework.toml; turning it on is one approval card plus Windows Hello - "
    f"say \"turn on voicestudio\", or use its row in Settings, under The PC itself. "
    f"Nothing starts the program for you: it is started by hand with "
    f"tools\\voicestudio_sidecar.ps1 -Start.")
SET_ON = (
    f"VoiceStudio is on now. Nothing was started and nothing was loaded: it still "
    f"starts by hand with tools\\voicestudio_sidecar.ps1 -Start, and the speaking "
    f"voice is the next slice, so nothing you hear changes yet.")
SET_OFF = (
    "VoiceStudio is off. Nothing was started or stopped: its own program keeps "
    "running if you started it, and this switch only decides whether Jarvis may ask "
    "it to speak.")
ALREADY_ON = "VoiceStudio is already on. Nothing was changed."
ALREADY_OFF = "VoiceStudio is already off. Nothing was changed."
WAITING_WORDS = ("Waiting for your approval card in the Jarvis bar - VoiceStudio stays "
                 "off until it is answered.")
REFUSED_WORDS = ("The approval card was not approved, so VoiceStudio stayed off. "
                 "Nothing was changed.")
ON_CARD = ("Turn on VoiceStudio? Jarvis may then ask the separate VoiceStudio program on "
           "this PC to speak. The program is NOT started by this: it still starts by "
           "hand, and the speaking voice is not wired yet, so nothing you hear changes.")


def _switch_words() -> str:
    """The switch sentence for the state it is really in - one source."""
    return STATE_ON if enabled() else STATE_OFF


def state() -> dict:
    """{"enabled", "words"} - the switch as the chat answer and a row read it."""
    on = enabled()
    return {"enabled": on, "words": STATE_ON if on else STATE_OFF}


# --------------------------------------------------------------------------
#   Loopback only: an ADDRESS, never a name
# --------------------------------------------------------------------------

def _base(base: str = None) -> str:
    """The base URL to use, refused unless it is a loopback ADDRESS.

    A name is refused on purpose (`localhost` included): a name is a lookup,
    and a lookup can answer anything. VoiceStudio binds `127.0.0.1` and
    nothing else, so that is the only address this client has any business
    dialling.
    """
    value = (base or BASE_URL).strip()
    try:
        parsed = urllib.parse.urlsplit(value)
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        raise VoiceStudioRefused(
            f"That is not an address VoiceStudio can be called at ({value[:80]!r}): an address "
            f"needs a host and a real port, like {BASE_URL}.")
    if parsed.scheme not in ("http", "https"):
        raise VoiceStudioRefused(
            f"VoiceStudio is only talked to over http on this PC, not {parsed.scheme or 'nothing'}.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise VoiceStudioRefused(
            f"{host or 'that address'} is a name, not this PC's own address. VoiceStudio is "
            f"only ever talked to at {HOST}:{PORT}, by address, so a name cannot redirect it.")
    if not (address.is_loopback):
        raise VoiceStudioRefused(
            f"{host} is not this PC. VoiceStudio is only talked to at {HOST}:{PORT}; nothing "
            f"about it may leave this machine.")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise VoiceStudioRefused(
            "The VoiceStudio address must be just an address - no path, query or fragment.")
    if port in JARVIS_LANE_PORTS:
        raise VoiceStudioRefused(
            f"{HOST}:{port} is one of Jarvis's own model lanes, not VoiceStudio. This "
            f"client is only ever pointed at VoiceStudio's own {PORT}, so a mistake here can "
            f"never unload a model Jarvis is using.")
    return f"{parsed.scheme}://{parsed.netloc}"


# --------------------------------------------------------------------------
#   HTTP: never through a proxy, bounded, and honest about what came back
# --------------------------------------------------------------------------

def _opener():
    """An opener with an EMPTY proxy table.

    `jarvis_local_http.opener()` is the shared CONN-1 fix and is used whenever
    it is importable (it is shipped whole). The two-line fallback is the same
    rule, so a checkout without that module still cannot send a sentence to a
    proxy: on Windows "bypass proxy for local addresses" does NOT cover
    `127.0.0.1`, so urllib's default opener really would.
    """
    try:
        import jarvis_local_http as lh
        return lh.opener()
    except Exception:                                     # noqa: BLE001
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))


class _Reply:
    """One HTTP answer, reduced to what a caller needs."""

    __slots__ = ("status", "headers", "body", "seconds")

    def __init__(self, status: int, headers, body: bytes, seconds: float):
        self.status = status
        self.headers = headers
        self.body = body
        self.seconds = seconds

    def json(self) -> dict:
        try:
            value = json.loads(self.body.decode("utf-8", "replace"))
        except Exception:                                 # noqa: BLE001
            return {}
        return value if isinstance(value, dict) else {}

    def content_type(self) -> str:
        try:
            return str(self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        except Exception:                                 # noqa: BLE001
            return ""

    def words(self) -> str:
        """Up to ~300 characters of the body, one line, for an error sentence."""
        try:
            text = self.body.decode("utf-8", "replace")
        except Exception:                                 # noqa: BLE001
            return ""
        text = " ".join(text.split())
        return text[:_BODY_IN_WORDS]


def _request(method: str, path: str, body: dict = None, timeout: float = 10.0,
             base: str = None) -> _Reply:
    """One request to VoiceStudio. Raises VoiceStudioError, never leaks urllib's."""
    root = _base(base)
    url = root + path
    data = None
    headers = {"Accept": "application/json, audio/*"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.monotonic()
    try:
        with _opener().open(req, timeout=max(0.5, float(timeout))) as reply:
            return _Reply(int(getattr(reply, "status", reply.getcode()) or 0),
                          reply.headers, reply.read(), time.monotonic() - started)
    except urllib.error.HTTPError as exc:
        # An HTTP error IS an answer: 403's licence gate and 400's cold-start
        # race are both read from it, so it is returned, not raised.
        try:
            payload = exc.read()
        except Exception:                                 # noqa: BLE001
            payload = b""
        return _Reply(int(exc.code or 0), exc.headers, payload, time.monotonic() - started)
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise VoiceStudioUnavailable(_not_running_words(reason), reason=str(reason))
    except (TimeoutError, OSError) as exc:
        raise VoiceStudioUnavailable(_not_running_words(exc), reason=str(exc))
    except ValueError as exc:
        raise VoiceStudioRefused(f"That is not an address VoiceStudio can be called at ({exc}).")


def _not_running_words(reason=None) -> str:
    tail = f" ({reason})" if reason else ""
    return (f"VoiceStudio is not running on {HOST}:{PORT}{tail}. Start it with: {START_COMMAND} "
            f"- a first start took 32.06 s here, a later one 16.66 s, and it is only ever "
            f"started when it is needed.")


def _port_words() -> str:
    return (f"VoiceStudio answers on {HOST}:{PORT} only. If something else is listening there, "
            f"stop it: this client never speaks to any other program.")


# --------------------------------------------------------------------------
#   Health, startup progress and the model
# --------------------------------------------------------------------------

def health(timeout: float = 2.5, base: str = None) -> dict:
    """Is it running, and is it ready? Never raises for "not running".

    `/health` answers 503 with a step and a label while it starts (measured:
    ml_imports is the long one, 16.47 s), then 200. Both are reported as what
    they are, because a start reported as a failure is worse than no report.
    """
    try:
        reply = _request("GET", "/health", timeout=timeout, base=base)
    except VoiceStudioUnavailable as exc:
        return {"ok": False, "running": False, "ready": False, "why": "not_running",
                "words": exc.words, "base": _base(base)}
    except VoiceStudioError as exc:
        return {"ok": False, "running": None, "ready": False, "why": "bad_answer",
                "words": exc.words, "base": _base(base)}
    body = reply.json()
    status = str(body.get("status") or "").lower()
    if reply.status == 200 and status == "ok":
        return {"ok": True, "running": True, "ready": True, "status": status,
                "device": body.get("device") or "", "version": body.get("version") or "",
                "seconds": round(reply.seconds, 3), "words": _ready_words(body), "base": _base(base)}
    if reply.status == 503 or status == "starting":
        step, label = body.get("step") or "", body.get("label") or ""
        return {"ok": False, "running": True, "ready": False, "status": status or "starting",
                "step": step, "label": label, "version": body.get("version") or "",
                "seconds": round(reply.seconds, 3),
                "words": _starting_words(step, label), "base": _base(base)}
    return {"ok": False, "running": True, "ready": False, "status": status or f"http {reply.status}",
            "status_code": reply.status, "seconds": round(reply.seconds, 3),
            "words": (f"VoiceStudio is running but answered the health check with an error "
                      f"(code {reply.status}), so it is not ready yet. Read its log in "
                      f"VoiceStudio's own folder. {_port_words()}"),
            "base": _base(base)}


def _ready_words(body: dict) -> str:
    device = body.get("device") or "this PC"
    version = body.get("version") or "unknown"
    return f"VoiceStudio is running and ready (version {version}, {device})."


def _starting_words(step: str, label: str) -> str:
    what = label or step or "starting"
    return (f"VoiceStudio is still starting: {what}. A first start took 32.06 s on this PC and a "
            f"later one 16.66 s, so this is normal for the first half minute.")


def startup_progress(timeout: float = 2.5, base: str = None) -> dict:
    """What it is doing before it can serve: the step, its label, the seconds.

    `/startup/progress` answers while `/health` is still 503, which is the
    difference between "starting at step X" and "dead" (it is also the route
    the measured report used to separate the two).
    """
    try:
        reply = _request("GET", "/startup/progress", timeout=timeout, base=base)
    except VoiceStudioUnavailable as exc:
        return {"ok": False, "running": False, "why": "not_running", "words": exc.words}
    except VoiceStudioError as exc:
        return {"ok": False, "running": None, "why": "bad_answer", "words": exc.words}
    body = reply.json()
    status = str(body.get("status") or "").lower()
    step, label = body.get("step") or "", body.get("label") or ""
    done = []
    for item in body.get("steps") or []:
        if isinstance(item, dict) and item.get("state") == "done":
            done.append(str(item.get("id") or ""))
    elapsed = body.get("elapsed_s")
    if status == "ready":
        words = "VoiceStudio has finished starting."
    elif status == "failed":
        error = body.get("error") or {}
        words = (f"VoiceStudio failed while starting, at {label or step or 'an unknown step'}: "
                 f"{error.get('message') or 'no reason was given'}. The full log is in "
                 f"VoiceStudio's own folder.")
    else:
        words = _starting_words(step, label)
    return {"ok": reply.status == 200, "running": True, "status": status, "step": step,
            "label": label, "elapsed_s": elapsed, "done": done,
            "error": body.get("error") or None, "words": words,
            "seconds": round(reply.seconds, 3)}


def model_loaded(timeout: float = 2.5, base: str = None) -> dict:
    """What VoiceStudio itself says it has loaded right now.

    Ids come from the server, never from this file - which is why `stop()`
    can only ever unload VoiceStudio's own models.
    """
    try:
        reply = _request("GET", "/model/loaded", timeout=timeout, base=base)
    except VoiceStudioUnavailable as exc:
        return {"ok": False, "running": False, "models": [], "count": 0, "words": exc.words}
    except VoiceStudioError as exc:
        return {"ok": False, "running": None, "models": [], "count": 0, "words": exc.words}
    body = reply.json()
    models = [m for m in (body.get("models") or []) if isinstance(m, dict)]
    count = int(body.get("count") or len(models) or 0)
    if count:
        named = ", ".join(str(m.get("name") or m.get("id") or "a model") for m in models)
        words = (f"VoiceStudio is holding {count} model(s): {named}. It reloads one on the next "
                 f"speech request, which took 27.41 s here after a restart.")
    else:
        words = ("VoiceStudio is running but holds no model, so it is not using the graphics "
                 "card right now. The next speech request loads one (27.41 s measured).")
    return {"ok": reply.status == 200, "running": True, "models": models, "count": count,
            "words": words}


def wait_for_model_loaded(timeout: float = STARTUP_TIMEOUT_SECONDS, base: str = None,
                          progress=None) -> dict:
    """Wait (bounded) for a model to be loaded, reporting each step.

    Three outcomes and each one is named: not running (returns at once - a
    timeout would be a lie), loaded (with what), or still not loaded after
    `timeout` seconds (with the last step it reported, so the words say where
    it is stuck rather than "timed out").
    """
    started = time.monotonic()
    deadline = started + max(0.0, float(timeout))
    last = {}
    while True:
        state = health(base=base)
        last = state
        if state.get("running") is False:
            return {"ok": False, "why": "not_running", "waited": 0.0,
                    "words": state.get("words") or _not_running_words()}
        if state.get("ready"):
            loaded = model_loaded(base=base)
            if loaded.get("count"):
                return {"ok": True, "why": "loaded", "waited": round(time.monotonic() - started, 2),
                        "models": loaded.get("models") or [], "count": loaded.get("count") or 0,
                        "words": loaded.get("words") or "", "health": state}
            note = ("VoiceStudio is ready but has not loaded a model yet; it loads one on the "
                    "first speech request (up to 27.41 s measured).")
            if progress is not None:
                _tell(progress, {"ok": False, "why": "no_model", "waited": 0.0, "words": note})
        else:
            note = state.get("words") or _starting_words("", "")
            if progress is not None:
                _tell(progress, {"ok": False, "why": "starting",
                                 "waited": round(time.monotonic() - started, 2),
                                 "step": state.get("step") or "", "words": note})
        if time.monotonic() >= deadline:
            waited = round(time.monotonic() - started, 2)
            step = last.get("label") or last.get("step") or ""
            where = f" It last reported: {step}." if step else ""
            return {"ok": False, "why": "timeout", "waited": waited, "health": last,
                    "words": (f"VoiceStudio did not load a model within {timeout:g} s.{where} "
                              f"Its log is in VoiceStudio's own folder; if it has stopped, "
                              f"start it again with: {START_COMMAND}")}
        time.sleep(1.0)


def _tell(progress, report: dict) -> None:
    """Call a caller's progress function, and never let it break the wait."""
    try:
        progress(report)
    except Exception:                                     # noqa: BLE001
        pass


# --------------------------------------------------------------------------
#   What it can speak with: engines and voices, each with its licence class
# --------------------------------------------------------------------------

def _licence_for_engine(engine_id: str) -> tuple:
    """(license_class, note) for one engine id. Fail-closed by default."""
    engine_id = str(engine_id or "").strip().lower()
    if engine_id in COMMERCIALLY_CLEARED_ENGINES:
        return "commercial_ok", f"{engine_id}: reviewed and cleared for commercial use."
    return DEFAULT_LICENSE_CLASS, _ENGINE_NOTES.get(engine_id, _ENGINE_NOTE_UNREVIEWED)


def engines(timeout: float = 5.0, base: str = None) -> list:
    """The TTS engines this VoiceStudio install lists, each with its dossier.

    Read from `GET /engines/tts` (the same inventory its own Settings page
    shows), never guessed and never cached: which engines exist depends on
    what the owner installed.
    """
    reply = _request("GET", "/engines/tts", timeout=timeout, base=base)
    if reply.status != 200:
        raise VoiceStudioError(
            f"VoiceStudio answered with an error (code {reply.status}) when asked for its "
            f"engines, so its engine list could not be read. {_port_words()}", status=reply.status, body=reply.words())
    body = reply.json()
    active = str(body.get("active") or "")
    rows = []
    for entry in body.get("backends") or []:
        if not isinstance(entry, dict):
            continue
        engine_id = str(entry.get("id") or "")
        license_class, note = _licence_for_engine(engine_id)
        rows.append({
            "id": engine_id,
            "name": str(entry.get("name") or engine_id),
            "available": bool(entry.get("available")),
            "active": engine_id == active,
            "license_class": license_class,
            "license_note": note,
            "license_required": bool(entry.get("license_required")),
            "license_accepted": entry.get("license_accepted"),
            "supports_cloning": entry.get("supports_cloning"),
        })
    return rows


def voices(timeout: float = 5.0, base: str = None) -> list:
    """Voices this install offers, each with the class of the engine behind it.

    `GET /v1/audio/voices` returns the OpenAI voice aliases (`default`,
    `alloy`, ...) plus the owner's own voice profiles. A profile is data on
    this PC; the licence that matters is the engine that would speak it, so
    the class on a voice row is the engine's class, and the note says so.
    """
    reply = _request("GET", "/v1/audio/voices", timeout=timeout, base=base)
    if reply.status != 200:
        raise VoiceStudioError(
            f"VoiceStudio answered with an error (code {reply.status}) when asked for its "
            f"voices, so its voice list could not be read. {_port_words()}", status=reply.status, body=reply.words())
    body = reply.json()
    active = ""
    for entry in body.get("engines") or []:
        if isinstance(entry, dict) and entry.get("active"):
            active = str(entry.get("id") or "")
            break
    if not active:
        for entry in body.get("engines") or []:
            if isinstance(entry, dict) and entry.get("id"):
                active = str(entry.get("id"))
                break
    license_class, _note = _licence_for_engine(active)
    rows = []
    for entry in body.get("voices") or []:
        if not isinstance(entry, dict):
            continue
        voice_id = str(entry.get("voice_id") or entry.get("id") or "")
        rows.append({
            "id": voice_id,
            "name": str(entry.get("name") or voice_id),
            "type": str(entry.get("type") or ""),
            "language": str(entry.get("language") or ""),
            "active_engine": active,
            "license_class": license_class,
            "license_note": _VOICE_NOTE,
        })
    return rows


# --------------------------------------------------------------------------
#   Speaking: text in, audio bytes out (WAV or MP3 as the server returns)
# --------------------------------------------------------------------------

#: The default model id. `tts-1` is the OpenAI alias that routes to whatever
#: engine is active, so a caller that does not choose an engine keeps working
#: when the owner changes engines (measured working: 2.61 s, RESULTS.md
#: section 4). A caller that names an engine id from `engines()` gets it.
DEFAULT_MODEL = "tts-1"
MAX_INPUT_CHARS = 4096                      # the server's own max_length


def sniff_format(data: bytes) -> str:
    """'wav', 'mp3' or '' from the bytes themselves.

    The server returns the format that was asked for and sets Content-Type to
    match; this is the same answer read from the body, so a caller that only
    got bytes can still name what it has.
    """
    if not data or len(data) < 4:
        return ""
    head = data[:12]
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:3] == b"ID3" or (head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "mp3"
    return ""


def synthesize(text: str, voice: str = "default", engine: str = None,
               response_format: str = "wav", timeout: float = 120.0,
               base: str = None) -> bytes:
    """Ask VoiceStudio to say `text`; return the audio bytes as it sent them.

    `response_format="wav"` is the default because WAV needs no ffmpeg on
    this PC (both were measured working; MP3 took 2.93 s against WAV's
    1.70-1.98 s). `engine` is an id from `engines()`; leaving it out sends
    `tts-1`, the alias for whichever engine is active.

    Raises `VoiceStudioUnavailable` when the switch is off or nothing is
    listening, `VoiceStudioLicenceGate` on the 403 that means a model licence
    has not been accepted, and `VoiceStudioError` for anything else. Every
    message is a sentence, not a stack trace, because the existing speech
    code puts it in front of the owner.
    """
    words = str(text or "")
    if not words.strip():
        raise VoiceStudioError("There is nothing to say: the text is empty.")
    if len(words) > MAX_INPUT_CHARS:
        raise VoiceStudioError(
            f"That sentence is {len(words)} characters; VoiceStudio takes at most "
            f"{MAX_INPUT_CHARS}, so it has to be split first.")
    if not enabled():
        raise VoiceStudioUnavailable(_switch_words())
    fmt = str(response_format or "wav").strip().lower()
    if fmt not in ("wav", "mp3"):
        raise VoiceStudioError(
            f"VoiceStudio is asked for wav or mp3 here, not {fmt or 'nothing'}: wav needs no "
            f"extra program on this PC and mp3 was measured working. Other formats need ffmpeg.")

    payload = {"model": str(engine or DEFAULT_MODEL), "input": words,
               "voice": str(voice or "default"), "response_format": fmt}
    last_words = ""
    for attempt in range(1, _COLD_START_TRIES + 1):
        reply = _request("POST", "/v1/audio/speech", body=payload, timeout=timeout, base=base)
        if reply.status == 200:
            ctype = reply.content_type()
            audio = reply.body
            if not audio:
                raise VoiceStudioError(
                    f"VoiceStudio answered 200 to a speech request with an empty body. Nothing "
                    f"to play was returned.")
            if not ctype.startswith("audio/"):
                raise VoiceStudioError(
                    f"VoiceStudio answered 200 with {ctype or 'no content type'} instead of "
                    f"audio, so it was not audio that came back. First line: {reply.words()}")
            if fmt == "wav" and sniff_format(audio) not in ("wav", ""):
                raise VoiceStudioError(
                    f"VoiceStudio was asked for wav and answered {sniff_format(audio)}, so the "
                    f"caller would have tried to play the wrong thing.")
            return audio
        if reply.status == 403:
            gate = first_run_license_gate(base=base)
            raise VoiceStudioLicenceGate(
                gate.get("words") or _licence_words_fallback(), gate=gate)
        if _is_cold_start_race(reply):
            last_words = _cold_start_words(reply, attempt)
            if attempt < _COLD_START_TRIES:
                # The measured fix is that the NEXT request succeeds, so the
                # only wait is a short one - no silent 30 s block inside a
                # speech call whose caller already set its own timeout.
                time.sleep(_COLD_START_WAIT_SECONDS)
                continue
            raise VoiceStudioError(last_words)
        if reply.status == 503:
            waited = wait_for_model_loaded(timeout=min(STARTUP_TIMEOUT_SECONDS, timeout), base=base)
            if waited.get("ok") and attempt < _COLD_START_TRIES:
                continue
            raise VoiceStudioUnavailable(
                f"VoiceStudio is running but not ready to speak yet. {waited.get('words') or ''} "
                f"Nothing was sent to any other machine.")
        raise VoiceStudioError(
            f"VoiceStudio answered with an error (code {reply.status}) to the speech request. "
            f"{reply.words() or 'No reason was given.'}".strip())
    raise VoiceStudioError(last_words or "VoiceStudio could not be asked to speak.")


def _is_cold_start_race(reply: _Reply) -> bool:
    """The ONE measured transient: a 400 naming the half-imported transformers."""
    if reply.status not in (400, 500):
        return False
    text = reply.body.decode("utf-8", "replace")
    return any(mark in text for mark in _COLD_START_MARKS)


def _cold_start_words(reply: _Reply, attempt: int) -> str:
    return (f"VoiceStudio was still finishing its start-up when the speech request arrived "
            f"(attempt {attempt} of {_COLD_START_TRIES}): the request hit a half-loaded part of "
            f"its speech runtime. This is the race measured on 2026-11-04, and the next request "
            f"succeeds. Its own words: {reply.words()}")


# --------------------------------------------------------------------------
#   The first-run licence gate (403), in plain words and exact commands
# --------------------------------------------------------------------------

def _licence_words_fallback() -> str:
    names = "; ".join(f"{repo} ({LICENCE_LABELS.get(repo, 'terms not read')})"
                      for repo in LICENCE_REPOS)
    return (f"VoiceStudio will not speak until two model licences are accepted on this PC, in "
            f"VoiceStudio's own terms: {names}. Until then every speech request answers 403. "
            f"They are accepted once, by you, not by Jarvis: ask this module for "
            f"first_run_license_gate() for the exact commands, or open VoiceStudio's own page.")


def first_run_license_gate(timeout: float = 5.0, base: str = None) -> dict:
    """The 403 detector: which of the two licences still needs accepting.

    Reads `GET /models/licenses/acceptance/<repo>` for each measured
    repository. Returns `gate: True` when any is not accepted, with one plain
    sentence and the exact two commands per licence (the fingerprint in the
    accept command is read from the server, so it is not a placeholder).

    It NEVER accepts a licence. Accepting is the owner saying yes to terms
    about someone else's model; a program that clicked that for him would be
    the one thing this whole feature must not do.
    """
    try:
        state = health(timeout=timeout, base=base)
    except VoiceStudioError as exc:
        return {"gate": False, "running": None, "repos": [], "words": exc.words}
    if state.get("running") is False:
        return {"gate": False, "running": False, "repos": [], "words": state.get("words") or ""}
    repos, rows = [], []
    for repo in LICENCE_REPOS:
        row = {"repo_id": repo, "license": LICENCE_LABELS.get(repo, "terms not read"),
               "state": "unknown", "required": True, "fingerprint": ""}
        try:
            reply = _request("GET", "/models/licenses/acceptance/" + repo,
                             timeout=timeout, base=base)
            body = reply.json()
            if reply.status == 200 and body:
                row.update({
                    "license": str(body.get("license") or row["license"]),
                    "category": str(body.get("category") or ""),
                    "required": bool(body.get("required", True)),
                    "state": str(body.get("state") or "unknown"),
                    "fingerprint": str(body.get("fingerprint") or ""),
                })
            else:
                row["state"] = f"could not be read (HTTP {reply.status})"
        except VoiceStudioUnavailable as exc:
            return {"gate": False, "running": False, "repos": [], "words": exc.words}
        except VoiceStudioError as exc:
            row["state"] = f"could not be read ({exc.words})"
        repos.append(repo)
        rows.append(row)
    waiting = [r for r in rows if str(r.get("state")).lower() not in ("accepted", "not_required")]
    if not waiting:
        return {"gate": False, "running": True, "repos": rows,
                "words": ("Both model licences are accepted on this PC, so VoiceStudio can "
                          "speak. They are personal, non-commercial use only.")}
    commands = []
    for row in waiting:
        commands.extend(_licence_commands(row))
    names = "; ".join(f"{r['repo_id']} - {r['license']}" for r in waiting)
    many = len(waiting)
    words = (f"VoiceStudio will not speak yet: {many} model licence"
             f"{'' if many == 1 else 's'} still {'has' if many == 1 else 'have'} to be accepted "
             f"on this PC, in VoiceStudio's own terms. {names}. This is not a purchase and not "
             f"an account: "
             f"accepting each one is a single POST to VoiceStudio on this PC, and it is YOUR "
             f"yes, not Jarvis's. Until then every speech request answers 403. The two commands "
             f"for each one are in `commands` here, and the fingerprint they need is read from "
             f"this PC rather than typed.")
    return {"gate": True, "running": True, "repos": rows, "commands": commands,
            "words": words, "nothing_accepted": "Jarvis did not accept anything."}


def _licence_commands(row: dict) -> list:
    """The exact two commands for one repository, the fingerprint already filled in."""
    repo = row.get("repo_id") or ""
    read = f'curl.exe -s "http://{HOST}:{PORT}/models/licenses/acceptance/{repo}"'
    fingerprint = row.get("fingerprint") or ""
    accept = (f'curl.exe -s -X POST "http://{HOST}:{PORT}/models/licenses/accept" '
              f'-H "Content-Type: application/json" '
              f'-d "{{\\"repo_id\\": \\"{repo}\\", \\"fingerprint\\": \\"{fingerprint}\\", '
              f'\\"accepted\\": true}}"')
    out = [read, accept]
    if not fingerprint:
        out.append(f"# The second command needs the \"fingerprint\" from the first answer. "
                   f"Run the first command and put that value in place of {{fingerprint}}.")
    return out


# --------------------------------------------------------------------------
#   Releasing the card: unload VoiceStudio's OWN model, never a Jarvis lane
# --------------------------------------------------------------------------

def stop(timeout: float = 10.0, base: str = None) -> dict:
    """Ask VoiceStudio to release its model; leave the program itself running.

    The measured answer to the contention verdict is to let the sidecar's own
    model go (~1.9 GB back) rather than to kill the owner's program: the
    process holds 546 MB of RAM idle and reloads in 27.41 s (measured after a
    restart). Idempotent, and never raises for "not running".

    It unloads by the ids `/model/loaded` reports as `unloadable`, over the
    one socket to 11439. It cannot touch an Ollama lane: those are 11434,
    11435 and 11436, and no code path here builds an id of its own.
    """
    loaded = model_loaded(timeout=timeout, base=base)
    if loaded.get("running") is False:
        return {"ok": True, "running": False, "unloaded": [], "kept": [],
                "words": "VoiceStudio was already not running, so there was nothing to unload."}
    if not loaded.get("ok"):
        return {"ok": False, "running": True, "unloaded": [], "kept": [],
                "words": loaded.get("words") or "VoiceStudio's loaded models could not be read."}
    unloaded, kept, failed = [], [], []
    for model in loaded.get("models") or []:
        model_id = str(model.get("id") or "")
        if not model_id:
            continue
        if not model.get("unloadable"):
            kept.append(model_id)
            continue
        try:
            reply = _request("POST", "/model/unload/" + urllib.parse.quote(model_id, safe=""),
                             timeout=timeout, base=base)
        except VoiceStudioError as exc:
            failed.append(f"{model_id} ({exc.words})")
            continue
        if reply.status in (200, 202, 204):
            unloaded.append(model_id)
        else:
            failed.append(f"{model_id} (HTTP {reply.status}: {reply.words()})")
    if failed:
        words = ("VoiceStudio kept some of its models loaded: " + "; ".join(failed) +
                 ". Its own /model/loaded page is the authority on what is still held.")
        return {"ok": False, "running": True, "unloaded": unloaded, "kept": kept,
                "failed": failed, "words": words}
    if not unloaded:
        words = ("VoiceStudio is running and holds nothing this client may unload"
                 + (f" (kept: {', '.join(kept)})" if kept else "") + "; the graphics card is "
                 "not held by a model it can release.")
        return {"ok": True, "running": True, "unloaded": [], "kept": kept, "words": words}
    words = (f"VoiceStudio released {', '.join(unloaded)}. The program is still running (546 MB "
             f"of RAM idle) and will reload a model on the next speech request, which took "
             f"27.41 s here. Nothing belonging to Jarvis was unloaded.")
    return {"ok": True, "running": True, "unloaded": unloaded, "kept": kept, "words": words}


# --------------------------------------------------------------------------
#   The switch's writer: [voicestudio] enabled, through the same file it reads
# --------------------------------------------------------------------------

#: Held around the read-modify-write, so two changes cannot interleave.
_CFG_LOCK = threading.Lock()

#: A section header in the settings file, and the one boolean line inside it.
_SECTION_HEAD = re.compile(r"^[ \t]*\[[ \t]*" + SWITCH_SECTION + r"[ \t]*\][ \t]*(?:#.*)?$")
_ANY_HEAD = re.compile(r"^[ \t]*\[")
_ENABLED_LINE = re.compile(r"^(?P<lead>[ \t]*" + SWITCH_KEY + r"[ \t]*=[ \t]*)"
                           r"(?P<val>true|false)(?P<rest>[ \t]*(?:#.*)?)$")
_SETTINGS_MISSING = (
    "Jarvis could not find your settings file (jarvis-framework.toml), so VoiceStudio "
    "was not changed.")
_SETTINGS_HAND_EDIT = (
    "Your settings file (jarvis-framework.toml) is written in a way this switch cannot "
    "change safely, so nothing was changed. Edit the line by hand in Notepad, under "
    "[voicestudio], then restart Jarvis.")


def _framework_module():
    """`jarvis_framework` when this PC has it, else None (the suites' case)."""
    try:
        import jarvis_framework as fw
        return fw
    except Exception:                                     # noqa: BLE001
        return None


def _toml_path():
    """The settings file `_framework_section()` reads, or None."""
    fw = _framework_module()
    try:
        got = fw.config_path() if fw is not None else None
    except Exception:                                     # noqa: BLE001
        got = None
    return Path(got) if got else None


def _parse(text: str) -> dict:
    """The settings file as data. Raises VoiceStudioError with plain words."""
    try:
        import tomllib
    except ImportError:                                   # Python < 3.11
        try:
            import tomli as tomllib                       # type: ignore
        except ImportError:
            raise VoiceStudioError(
                "This PC's Python cannot read the settings file (it needs Python 3.11 "
                "or newer), so nothing was changed.")
    try:
        return tomllib.loads(text)
    except Exception:
        raise VoiceStudioError(
            "Your settings file (jarvis-framework.toml) has a mistake in it, so nothing "
            "was changed. Open it in Notepad and fix it first.")


def rewrite_enabled(text: str, on: bool) -> str:
    """`text` with ONE `[voicestudio] enabled` line set. Pure; raises.

    The same discipline `jarvis_asks_first.rewrite` uses for a tier line: parse
    first, change one line, insert the line or the section only when it is
    really absent, parse the result, and compare it to the input with exactly
    this one value changed - so a mis-shaped file is refused instead of being
    rewritten.
    """
    if not isinstance(on, bool):
        raise VoiceStudioError("The VoiceStudio switch takes on or off, not that.")
    before = _parse(text)
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    heads = [i for i, line in enumerate(lines) if _SECTION_HEAD.match(line)]
    if len(heads) > 1:
        raise VoiceStudioError(_SETTINGS_HAND_EDIT)
    want = "true" if on else "false"
    if heads:
        start = heads[0] + 1
        end = next((i for i in range(start, len(lines)) if _ANY_HEAD.match(lines[i])),
                   len(lines))
        hits = [i for i in range(start, end) if _ENABLED_LINE.match(lines[i])]
        if len(hits) > 1:
            raise VoiceStudioError(_SETTINGS_HAND_EDIT)
        if hits:
            m = _ENABLED_LINE.match(lines[hits[0]])
            lines[hits[0]] = f"{m.group('lead')}{want}{m.group('rest')}"
        else:
            section = (before.get(SWITCH_SECTION) or {})
            if SWITCH_KEY in section:
                # Present, but not as one plain line in that table.
                raise VoiceStudioError(_SETTINGS_HAND_EDIT)
            lines.insert(start, f"{SWITCH_KEY} = {want}")
    else:
        if SWITCH_SECTION in before:
            # The file has the name, but not as a table this can find.
            raise VoiceStudioError(_SETTINGS_HAND_EDIT)
        while lines and not lines[-1].strip():
            lines.pop()
        lines.extend(["", f"[{SWITCH_SECTION}]", f"{SWITCH_KEY} = {want}", ""])
    out = nl.join(lines)
    after = _parse(out)
    # Compared as JSON text: TOML dates are written the same way on both sides,
    # and any change other than this one value is a difference.
    want_doc = json.loads(json.dumps(before, default=str))
    want_doc.setdefault(SWITCH_SECTION, {})[SWITCH_KEY] = on
    if json.loads(json.dumps(after, default=str)) != want_doc:
        raise VoiceStudioError(_SETTINGS_HAND_EDIT)
    return out


def set_enabled(on: bool) -> tuple:
    """Write `[voicestudio] enabled` and say what really happened. (ok, words).

    The RAW writer, and deliberately not the door: `request_enabled()` is what
    the typed sentence and the Settings row call, because turning it ON is ONE
    `change_own_config` card while OFF is instant. It writes atomically (parse,
    change one line, parse again and compare, temporary file, move into place)
    and it NEVER starts, stops or calls VoiceStudio - the switch decides whether
    Jarvis MAY ask the separate program to speak, and the program is still
    started by hand.
    """
    if not isinstance(on, bool):
        raise ValueError("the VoiceStudio switch takes on or off, not that")
    path = _toml_path()
    if path is None or not path.is_file():
        return False, _SETTINGS_MISSING
    before = enabled()
    with _CFG_LOCK:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            return False, (f"Your settings file could not be read ({type(exc).__name__}), "
                           f"so nothing was changed.")
        try:
            new = rewrite_enabled(text, on)
        except VoiceStudioError as exc:
            return False, exc.words
        tmp = path.with_name(path.name + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8", newline="") as handle:
                handle.write(new)
            os.replace(tmp, path)
        except OSError as exc:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            return False, (f"Your settings file could not be written "
                           f"({type(exc).__name__}), so nothing was changed.")
    fw = _framework_module()
    try:
        if fw is not None:
            fw.reload_framework()
    except Exception:                                     # noqa: BLE001
        pass
    after = enabled()
    if after is not on:
        return False, ("Your settings file was written, but it still reads "
                       f"{'on' if after else 'off'}, so I will not claim it changed. "
                       "Nothing else was touched.")
    try:
        if fw is not None:
            fw.audit_log("voicestudio.switch",
                         {"enabled": bool(on), "changed": before != on})
    except Exception:                                     # noqa: BLE001
        pass
    if before == on:
        return True, (ALREADY_ON if on else ALREADY_OFF)
    return True, (SET_ON if on else SET_OFF)


def _gate(action: str, detail: dict, prompt: str):
    """`jarvis_gate.check()`, failing CLOSED on any error (jarvis_wifi's shape).

    `change_own_config` is tier "ask": the call blocks until the owner answers
    the card, and the answer is the permission. Windows Hello is that card's PC
    half, and no model answer can reach this - the only callers are the
    deterministic chat/Live sentences and the Settings row.
    """
    class _Refused:
        allowed = False
        outcome = "refused"

        def __init__(self, reason):
            self.reason = reason
    try:
        import jarvis_gate  # type: ignore
    except Exception as exc:                              # noqa: BLE001
        return _Refused(f"the approval gate is not available here ({exc})")
    try:
        return jarvis_gate.check(action, detail, prompt=prompt)
    except Exception as exc:                              # noqa: BLE001
        return _Refused(f"the approval gate failed ({exc})")


def _tier(action: str) -> str:
    fw = _framework_module()
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:                                     # noqa: BLE001
        return f"unreadable"


def request_enabled(on, *, gate=None, write=None) -> tuple:
    """One switch change, through the ONE path the sentence and the row share.

    Turning it ON raises exactly ONE `change_own_config` card and nothing is
    written until the owner answers it; turning it OFF is instant and cardless
    (taking an ability away is always safe). Returns (http code, body) with
    `words` always saying what really happened - a waiting card is never
    reported as on.
    """
    if not isinstance(on, bool):
        return 400, {"ok": False, "error": 'need {"enabled": true|false}'}
    if not on:
        if not enabled():
            return 200, {"ok": True, "enabled": False, "changed": False,
                         "words": ALREADY_OFF, "message": ALREADY_OFF}
        try:
            ok, words = (write or set_enabled)(False)
        except Exception as exc:                          # noqa: BLE001
            ok, words = False, (f"The VoiceStudio switch could not be saved "
                                f"({type(exc).__name__}), so nothing was changed.")
        if not ok:
            return 503, {"ok": False, "enabled": True, "changed": False,
                         "error": words, "words": words, "message": words}
        return 200, {"ok": True, "enabled": False, "changed": True,
                     "words": SET_OFF, "message": SET_OFF}
    if enabled():
        return 200, {"ok": True, "enabled": True, "changed": False,
                     "words": ALREADY_ON, "message": ALREADY_ON}
    tier = _tier(ACTION_ON)
    if tier != "ask":
        return 503, {"ok": False, "enabled": False, "changed": False,
                     "error": (f"{ACTION_ON} is tier {tier!r} in jarvis-framework.toml; "
                               f"turning VoiceStudio on needs a person to say yes, so it "
                               f"must be 'ask'"),
                     "words": "The rule that needs your yes is not in place, so nothing "
                              "was changed."}
    verdict = (gate or _gate)(ACTION_ON,
                              {"text": ON_CARD, "setting": SETTING_KEY,
                               "leaves_this_pc": False}, ON_CARD)
    if not getattr(verdict, "allowed", False):
        if not hasattr(verdict, "tier"):
            # The GATE ITSELF is missing or threw, so no card was ever raised.
            # That is not the owner saying no, and it must not be reported as
            # one (nor as a raw ImportError sentence).
            said = ("The approval card could not be raised on this PC, so VoiceStudio "
                    "stayed off and nothing was changed.")
            return 503, {"ok": False, "enabled": False, "changed": False,
                         "waiting": False, "error": said, "words": said}
        waiting = bool(getattr(verdict, "waiting", False)
                       or str(getattr(verdict, "outcome", "")).lower()
                       in ("waiting", "pending", "asked", "ask"))
        if waiting:
            return 202, {"ok": True, "enabled": False, "changed": False,
                         "waiting": True, "words": WAITING_WORDS,
                         "message": WAITING_WORDS}
        reason = str(getattr(verdict, "reason", "") or "").strip()
        said = reason or REFUSED_WORDS
        return 403, {"ok": False, "enabled": False, "changed": False,
                     "waiting": False, "error": said, "words": said}
    try:
        ok, words = (write or set_enabled)(True)
    except Exception as exc:                              # noqa: BLE001
        ok, words = False, (f"The VoiceStudio switch could not be saved "
                            f"({type(exc).__name__}), so nothing was changed.")
    if not ok:
        return 503, {"ok": False, "enabled": False, "changed": False,
                     "error": words, "words": words, "message": words}
    return 200, {"ok": True, "enabled": True, "changed": True,
                 "words": SET_ON, "message": SET_ON}


# --------------------------------------------------------------------------
#   One status card, for a caller that wants the whole picture
# --------------------------------------------------------------------------

def status(base: str = None) -> dict:
    """Everything a caller might show, in one dict, and it never raises.

    The card says the port, the switch, whether it is running, what it has
    loaded, the two licence classes and the measured cost - so a Settings row
    or a `-Status` print can be built from one call without re-deriving the
    numbers.
    """
    out = {"base": BASE_URL, "host": HOST, "port": PORT, "enabled": False,
           "running": False, "ready": False, "models": [], "words": "",
           "license_classes": list(LICENSE_CLASSES),
           "measured": measured(), "start_command": START_COMMAND}
    try:
        out["enabled"] = enabled()
    except Exception:                                     # noqa: BLE001
        out["enabled"] = False
    if not out["enabled"]:
        out["words"] = _switch_words()
        return out
    try:
        state = health(base=base)
    except Exception as exc:                              # noqa: BLE001
        out["words"] = f"VoiceStudio's health could not be asked ({type(exc).__name__})."
        return out
    out.update({k: state.get(k) for k in ("running", "ready", "device", "version")})
    out["words"] = state.get("words") or ""
    if state.get("running"):
        try:
            out["models"] = model_loaded(base=base).get("models") or []
        except Exception:                                 # noqa: BLE001
            out["models"] = []
    return out


def measured() -> dict:
    """The measured facts as data, so a report prints numbers rather than copies them."""
    return {
        "startup_first_seconds": STARTUP_FIRST_SECONDS,
        "startup_later_seconds": STARTUP_WARM_SECONDS,
        "preload_seconds": MODEL_PRELOAD_SECONDS,
        "first_call_seconds": FIRST_CALL_SECONDS,
        "warm_call_seconds": list(WARM_CALL_SECONDS),
        "warm_call_rtf": list(WARM_CALL_RTF),
        "resident_vram_mb": RESIDENT_VRAM_MB,
        "idle_ram_mb": IDLE_RAM_MB,
        "weights_bytes": WEIGHTS_BYTES,
        "peak_free_vram_mib": MEASURED_PEAK_FREE_MIB,
        "coexistence": "CONTENTION",
        "source": "VOICESTUDIO-EVAL/MEASURE/RESULTS.md (2026-11-04)",
    }
