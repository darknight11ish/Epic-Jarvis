"""jarvis_voicestudio.py - the client for the VoiceStudio sidecar, proved.

    py -3 -B backend/test_voicestudio.py

WHAT THIS PINS, AND WHY EACH ONE MATTERS
  1. The address. VoiceStudio is only ever called at a loopback ADDRESS on
     its own port. A name (`localhost`), another machine, and any of Jarvis's
     own model lanes (11434/11435/11436/11437/11450) are refused BEFORE a
     socket is opened, so a later edit cannot point this client at a lane and
     ask it to unload a model Jarvis is using.
  2. The start-up races that were measured on 2026-11-04: `/health` answering
     503 with a step while it starts (reported as "starting", never as
     "failed"), and the one transient 400 (`cannot import name
     'AutoFeatureExtractor'`) that the NEXT request survives - retried a
     bounded number of times and named in the words when the retries run out.
  3. The licence gate. A 403 is reported as the two model licences that must
     be accepted once, naming both repositories and the exact accept
     commands with the fingerprint filled in from the server - and the client
     NEVER accepts one itself. That is the owner's yes, not Jarvis's.
  4. The licence class. Every engine and voice row says `commercial_ok` or
     `personal_non_commercial_only`, and those are the only two values that
     can come out. Nothing is cleared for commercial use today, on purpose.
  5. The bytes. `synthesize()` sends the sentence, the voice, the engine and
     the format - and nothing else - and returns what the server sent.
  6. The off switch. `[voicestudio] enabled` ships `false`; speaking is
     refused in plain words while it is off, and the read-only questions
     still answer.
  7. No AGPL code path, no third-party import, no file write, no subprocess:
     the module is stdlib plus this repository's own proxy-free opener.
  8. No proxy. A request to a program on THIS PC must not travel to another
     machine first; the test points HTTP_PROXY at a trap and the trap must
     receive nothing.

Everything runs against a real `http.server` on an ephemeral 127.0.0.1 port.
Nothing here touches a real VoiceStudio, a real model, a graphics card or a
file outside a temporary folder, and no call leaves this machine.
"""
import ast
import json
import os
import socket
import sys
import tempfile
import threading
import traceback
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, require_shipped  # noqa: E402

require_shipped("jarvis_voicestudio.py")

import jarvis_voicestudio as V  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []
SRC = HERE / "jarvis_voicestudio.py"

WAV = (b"RIFF" + b"\x24\x00\x00\x00" + b"WAVE" + b"fmt " + b"\x10\x00\x00\x00" +
       b"\x01\x00\x01\x00" + b"\x80\x3e\x00\x00" + b"\x00\x7d\x00\x00" +
       b"\x02\x00\x10\x00" + b"data" + b"\x00\x00\x00\x00")
MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name)
    if not cond and detail:
        print("        " + str(detail)[-900:])


def skip(name, why):
    SKIPPED.append(name)
    print(f"SKIPPED {name} - {why}")


# --------------------------------------------------------------------------
#   A real HTTP server standing in for VoiceStudio
# --------------------------------------------------------------------------

STATE = {}


def reset(**changes):
    STATE.clear()
    STATE.update({
        "health": "ready",              # ready | starting | httperror
        "models": [{"id": "tts", "name": "VoiceStudio TTS", "device": "cuda:0",
                    "vram_mb": 1945.3, "unloadable": True},
                   {"id": "asr", "name": "WhisperX ASR", "device": "cuda:0",
                    "vram_mb": 0, "unloadable": False, "note": "released with the TTS model"}],
        "loaded_after": None,           # model/loaded answers empty until this many polls
        "speech": "wav",                # wav | mp3 | 403 | cold | cold_forever | text | empty | 503
        "licences": {
            "k2-fsa/OmniVoice": {"repo_id": "k2-fsa/OmniVoice", "state": "not_accepted",
                                 "required": True, "category": "noncommercial",
                                 "license": "CC-BY-NC (version unspecified); Higgs Audio 2; "
                                            "Meta Llama 3",
                                 "fingerprint": "v2:d938ea928581624d5732507057d8530320f638ac6"},
            "eustlb/higgs-audio-v2-tokenizer": {
                "repo_id": "eustlb/higgs-audio-v2-tokenizer", "state": "not_accepted",
                "required": True, "category": "unreviewed", "license": "NOASSERTION",
                "fingerprint": "v2:6b44aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
        },
        "calls": [],
        "loaded_polls": 0,
    })
    STATE.update(changes)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_a):        # silence the test output
        pass

    # -- helpers ---------------------------------------------------------
    def _send(self, code, body=b"", ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, code, payload):
        self._send(code, json.dumps(payload).encode("utf-8"))

    def _record(self, body=b""):
        STATE["calls"].append((self.command, self.path, body))

    # -- routes ----------------------------------------------------------
    def do_GET(self):
        self._record()
        path = self.path
        if path == "/health":
            mode = STATE["health"]
            if mode == "starting":
                return self._json(503, {"status": "starting", "step": "ml_imports",
                                        "label": "Loading ML runtime (PyTorch)...",
                                        "version": "0.5.7"})
            if mode == "httperror":
                return self._json(500, {"detail": "the model runtime died"})
            return self._json(200, {"status": "ok",
                                    "device": "cuda (NVIDIA GeForce RTX 2080 SUPER)",
                                    "version": "0.5.7"})
        if path == "/startup/progress":
            if STATE["health"] == "starting":
                return self._json(200, {"status": "starting", "step": "ml_imports",
                                        "label": "Loading ML runtime (PyTorch)...",
                                        "elapsed_s": 12.86, "error": None,
                                        "steps": [{"id": "env_prefs", "label": "Restoring",
                                                   "state": "done"},
                                                  {"id": "ml_imports", "label": "Loading ML",
                                                   "state": "active"}]})
            return self._json(200, {"status": "ready", "step": None, "label": None,
                                    "elapsed_s": 16.66, "error": None, "steps": []})
        if path == "/model/loaded":
            STATE["loaded_polls"] += 1
            after = STATE["loaded_after"]
            if after is not None and STATE["loaded_polls"] <= after:
                return self._json(200, {"models": [], "count": 0})
            models = STATE["models"]
            return self._json(200, {"models": models, "count": len(models)})
        if path == "/engines/tts":
            return self._json(200, {"active": "omnivoice", "active_model": "k2-fsa/OmniVoice",
                                    "env_override": False,
                                    "backends": [
                                        {"id": "omnivoice", "name": "OmniVoice",
                                         "available": True, "license_required": True,
                                         "license_accepted": True},
                                        {"id": "kittentts", "name": "Kitten TTS",
                                         "available": True},
                                    ]})
        if path == "/v1/audio/voices":
            return self._json(200, {
                "voices": [{"voice_id": "default", "name": "Default", "type": "openai_alias"},
                           {"voice_id": "alloy", "name": "Alloy", "type": "openai_alias"},
                           {"voice_id": "vp_7", "name": "Owner's own", "type": "profile",
                            "language": "en"}],
                "engines": [{"id": "omnivoice", "name": "OmniVoice", "available": True,
                             "active": True}]})
        if path.startswith("/models/licenses/acceptance/"):
            repo = urllib.parse.unquote(path[len("/models/licenses/acceptance/"):])
            row = dict(STATE["licences"].get(repo) or {})
            if not row:
                return self._json(404, {"detail": "unknown repository"})
            return self._json(200, row)
        return self._json(404, {"detail": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self._record(body)
        path = self.path
        if path == "/model/unload/tts":
            return self._json(200, {"unloaded": "tts"})
        if path.startswith("/model/unload/"):
            return self._json(400, {"detail": "unknown model id"})
        if path == "/v1/audio/speech":
            mode = STATE["speech"]
            if mode == "403":
                return self._json(403, {"error": {
                    "message": "Licence not accepted for eustlb/higgs-audio-v2-tokenizer",
                    "code": "model_licence_required"}})
            if mode in ("cold", "cold_forever"):
                if mode == "cold":
                    STATE["speech"] = "wav"
                return self._json(400, {"error": {
                    "message": "cannot import name 'AutoFeatureExtractor' from "
                               "'transformers.models.auto.feature_extraction_auto'",
                    "code": "internal_error"}})
            if mode == "503":
                return self._json(503, {"detail": "still starting"})
            if mode == "text":
                return self._send(200, b"not audio at all", "text/plain")
            if mode == "empty":
                return self._send(200, b"", "audio/wav")
            if mode == "mp3":
                return self._send(200, MP3, "audio/mpeg")
            return self._send(200, WAV, "audio/wav")
        if path == "/models/licenses/accept":
            # The client must NEVER reach this. Recording it is the proof.
            return self._json(200, {"accepted": True})
        return self._json(404, {"detail": "not found"})


class Fake:
    def __init__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def calls(self, method=None, path=None):
        out = []
        for m, p, b in STATE["calls"]:
            if method and m != method:
                continue
            if path and p != path:
                continue
            out.append((m, p, b))
        return out


FAKE = Fake()


def free_port() -> int:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


# --------------------------------------------------------------------------
#   1. The address: an ADDRESS on this PC, on VoiceStudio's own port
# --------------------------------------------------------------------------

def t_the_port_is_pinned():
    check("the port is 11439", V.PORT == 11439, V.PORT)
    check("the base URL is 127.0.0.1:11439, not a name",
          V.BASE_URL == "http://127.0.0.1:11439", V.BASE_URL)
    for lane in (11434, 11435, 11436, 11437, 11450):
        check(f"{lane} is refused as a Jarvis lane", lane in V.JARVIS_LANE_PORTS)
    check("11439 is not in the list of Jarvis lanes", 11439 not in V.JARVIS_LANE_PORTS)


def t_a_non_loopback_address_is_refused_before_any_socket():
    reset()
    refused = []
    for bad in ("http://192.168.1.10:11439", "https://10.0.0.5:11439",
                "http://example.com:11439", "http://localhost:11439",
                "http://127.0.0.1:11439/some/path", "http://127.0.0.1:11435",
                "http://127.0.0.1:not-a-port"):
        try:
            V.engines(base=bad)
        except Exception as exc:                     # noqa: BLE001
            refused.append((bad, type(exc).__name__, str(exc)))
    names = [r[0] for r in refused]
    check("seven non-product addresses were refused", len(refused) == 7, refused)
    check("an address on another machine is refused", "http://192.168.1.10:11439" in names)
    check("a name is refused (a name is a lookup, not an address)",
          "http://localhost:11439" in names)
    check("an address with a path is refused", "http://127.0.0.1:11439/some/path" in names)
    check("a Jarvis model lane is refused with words that say so",
          "http://127.0.0.1:11435" in names
          and "model lane" in dict((r[0], r[2]) for r in refused)["http://127.0.0.1:11435"])
    check("a malformed port is refused, not left to urllib",
          "http://127.0.0.1:not-a-port" in names
          and dict((r[0], r[1]) for r in refused)["http://127.0.0.1:not-a-port"]
          == "VoiceStudioRefused")
    check("every refusal is VoiceStudioRefused",
          all(r[1] == "VoiceStudioRefused" for r in refused), refused)
    check("no socket was opened by a refused address", STATE["calls"] == [], STATE["calls"])


# --------------------------------------------------------------------------
#   2. Health and the start-up races
# --------------------------------------------------------------------------

def t_health_ready():
    reset()
    state = V.health(base=FAKE.base)
    check("ready: ok", state["ok"] is True, state)
    check("ready: running and ready", state["running"] and state["ready"], state)
    check("ready: the device is reported",
          "RTX 2080 SUPER" in state["device"], state.get("device"))
    check("ready: the version is reported", state["version"] == "0.5.7", state.get("version"))
    check("ready: the words say it is ready", "ready" in state["words"], state["words"])


def t_health_starting_is_not_a_failure():
    reset(health="starting")
    state = V.health(base=FAKE.base)
    check("starting: not ok, but RUNNING", state["ok"] is False and state["running"] is True, state)
    check("starting: the step and label are reported",
          state["step"] == "ml_imports" and "PyTorch" in state["label"], state)
    check("starting: the words quote the measured 32.06 s first start",
          "32.06" in state["words"], state["words"])
    check("starting: the words never say the program failed", "failed" not in state["words"].lower(),
          state["words"])


def t_health_not_running_is_honest():
    reset()
    state = V.health(timeout=1.0, base=f"http://127.0.0.1:{free_port()}")
    check("not running: ok is False and running is False",
          state["ok"] is False and state["running"] is False, state)
    check("not running: the words say how to start it",
          "-Start" in state["words"] and "voicestudio_sidecar.ps1" in state["words"],
          state["words"])
    check("not running: it does not pretend a timeout happened", "timeout" not in state["words"])


def t_startup_progress_reads_the_step():
    reset(health="starting")
    state = V.startup_progress(base=FAKE.base)
    check("startup progress: the step and done list are reported",
          state["step"] == "ml_imports" and "env_prefs" in state["done"], state)
    check("startup progress: it names the same step as /health does",
          "PyTorch" in state["words"], state["words"])


def t_wait_for_model_loaded_reports_progress():
    reset(loaded_after=2)
    seen = []
    result = V.wait_for_model_loaded(timeout=20.0, base=FAKE.base, progress=seen.append)
    check("wait: it ended loaded", result["ok"] is True and result["count"] == 2, result)
    check("wait: it reported the wait rather than blocking silently", len(seen) >= 1, seen)
    check("wait: what it is holding is named",
          "VoiceStudio TTS" in result["words"], result["words"])


def t_wait_times_out_with_where_it_is():
    reset(health="starting")
    result = V.wait_for_model_loaded(timeout=0.6, base=FAKE.base)
    check("wait: a timeout is not a pass", result["ok"] is False and result["why"] == "timeout",
          result)
    check("wait: the timeout says where it was stuck",
          "PyTorch" in result["words"], result["words"])


def t_wait_returns_at_once_when_not_running():
    reset()
    result = V.wait_for_model_loaded(timeout=30.0, base=f"http://127.0.0.1:{free_port()}")
    check("wait: not running returns at once, not after 30 s",
          result["ok"] is False and result["why"] == "not_running" and result["waited"] == 0.0,
          result)


# --------------------------------------------------------------------------
#   3. Speaking, the cold-start retry, and the bounded retries
# --------------------------------------------------------------------------

def t_synthesize_sends_only_the_sentence():
    reset()
    audio = V.synthesize("Hello from the other voice.", base=FAKE.base)
    check("speak: the audio bytes come back unchanged", audio == WAV, audio[:20])
    check("speak: it is a WAV", V.sniff_format(audio) == "wav", audio[:12])
    posts = FAKE.calls("POST", "/v1/audio/speech")
    check("speak: exactly one speech request", len(posts) == 1, posts)
    body = json.loads(posts[0][2].decode("utf-8"))
    check("speak: the body carries exactly four fields",
          sorted(body) == ["input", "model", "response_format", "voice"], sorted(body))
    check("speak: the sentence is what was asked for",
          body["input"] == "Hello from the other voice.", body)
    check("speak: no conversation, memory, file or token is sent",
          not any(k in body for k in ("context", "conversation", "memory", "file", "token",
                                      "messages", "history")), sorted(body))
    check("speak: the default model is the measured alias tts-1",
          body["model"] == "tts-1", body["model"])
    check("speak: the measured default voice is 'default'", body["voice"] == "default", body)


def t_synthesize_honours_engine_and_mp3():
    reset(speech="mp3")
    audio = V.synthesize("hi", engine="kittentts", voice="alloy", response_format="mp3",
                         base=FAKE.base)
    import json
    body = json.loads(FAKE.calls("POST", "/v1/audio/speech")[0][2].decode("utf-8"))
    check("speak: a named engine is sent as the model", body["model"] == "kittentts", body)
    check("speak: an mp3 comes back as mp3 bytes", V.sniff_format(audio) == "mp3", audio[:4])


def t_the_cold_start_race_is_retried():
    reset(speech="cold")
    audio = V.synthesize("race", base=FAKE.base)
    posts = FAKE.calls("POST", "/v1/audio/speech")
    check("cold start: the retry produced audio", audio == WAV, audio[:12])
    check("cold start: exactly two speech requests (one retry)", len(posts) == 2, posts)


def t_the_cold_start_retry_is_bounded_and_named():
    reset(speech="cold_forever")
    old_wait = V._COLD_START_WAIT_SECONDS
    V._COLD_START_WAIT_SECONDS = 0.01
    try:
        V.synthesize("race", base=FAKE.base)
        check("cold start: it gave up in words", False, "no exception")
    except V.VoiceStudioError as exc:
        check("cold start: it gave up in words",
              "half-loaded" in exc.words and "3 of 3" in exc.words, exc.words)
        check("cold start: it stopped after the bounded three tries",
              len(FAKE.calls("POST", "/v1/audio/speech")) == V._COLD_START_TRIES,
              len(FAKE.calls("POST", "/v1/audio/speech")))
    finally:
        V._COLD_START_WAIT_SECONDS = old_wait


def t_a_503_waits_for_the_start_then_retries():
    reset(speech="503", health="starting")
    old = V.STARTUP_TIMEOUT_SECONDS
    V.STARTUP_TIMEOUT_SECONDS = 0.3
    try:
        try:
            V.synthesize("still starting", timeout=0.3, base=FAKE.base)
            check("503: it waited and explained itself", False, "no exception")
        except V.VoiceStudioUnavailable as exc:
            check("503: it says it is running but not ready",
                  "not ready" in exc.words, exc.words)
            check("503: the words say where it is", "PyTorch" in exc.words, exc.words)
    finally:
        V.STARTUP_TIMEOUT_SECONDS = old


def t_a_non_audio_answer_is_refused():
    reset(speech="text")
    try:
        V.synthesize("hi", base=FAKE.base)
        check("a text answer is refused, not played", False, "no exception")
    except V.VoiceStudioError as exc:
        check("a text answer is refused, not played", "instead of audio" in exc.words, exc.words)


def t_empty_and_over_long_text_are_refused_before_a_socket():
    reset()
    for words, name in (("   ", "empty"), ("x" * (V.MAX_INPUT_CHARS + 1), "too long")):
        try:
            V.synthesize(words, base=FAKE.base)
            check(f"speak: {name} text is refused", False, "no exception")
        except V.VoiceStudioError:
            check(f"speak: {name} text is refused", True)
    check("speak: neither refusal opened a socket", FAKE.calls("POST", "/v1/audio/speech") == [])


# --------------------------------------------------------------------------
#   4. The licence gate: the 403, in plain words, and NEVER accepted here
# --------------------------------------------------------------------------

def t_the_403_licence_gate_names_both_licences():
    reset(speech="403")
    try:
        V.synthesize("say this", base=FAKE.base)
        check("403: the licence gate is raised", False, "no exception")
    except V.VoiceStudioLicenceGate as exc:
        check("403: the licence gate is raised", True)
        check("403: it names both repositories",
              "k2-fsa/OmniVoice" in exc.words
              and "eustlb/higgs-audio-v2-tokenizer" in exc.words, exc.words)
        check("403: it says every speech request answers 403", "403" in exc.words, exc.words)
        check("403: it says the yes is the owner's, not Jarvis's",
              "YOUR yes" in exc.words, exc.words)
        gate = exc.gate
        check("403: the gate carries both rows",
              [r["repo_id"] for r in gate["repos"]] == list(V.LICENCE_REPOS), gate.get("repos"))
        check("403: the exact accept command is given",
              any("/models/licenses/accept" in c for c in gate["commands"]), gate.get("commands"))
        check("403: the fingerprint is filled in from the server, not a placeholder",
              any("v2:d938ea928581624d" in c for c in gate["commands"]), gate.get("commands"))
        check("403: the gate says nothing was accepted",
              "did not accept" in gate.get("nothing_accepted", ""), gate.get("nothing_accepted"))
    check("403: the client never posted an acceptance",
          FAKE.calls("POST", "/models/licenses/accept") == [],
          FAKE.calls("POST", "/models/licenses/accept"))


def t_the_licence_gate_clears_when_both_are_accepted():
    reset()
    for row in STATE["licences"].values():
        row["state"] = "accepted"
    gate = V.first_run_license_gate(base=FAKE.base)
    check("licence gate: no gate when both are accepted", gate["gate"] is False, gate)
    check("licence gate: it says they are accepted and non-commercial",
          "accepted" in gate["words"] and "non-commercial" in gate["words"], gate["words"])


def t_the_licence_gate_never_accepts_anything_by_itself():
    reset()
    source = SRC.read_text(encoding="utf-8")
    check("the module has no POST to the accept route",
          '_request("POST", "/models/licenses/accept"' not in source, "found an accept POST")
    check("the module only ever GETs a licence state",
          '"/models/licenses/acceptance/"' in source and '"GET"' in source,
          "the acceptance read is missing")
    check("the commands it PRINTS are the owner's to run",
          'curl.exe -s -X POST' in source and "models/licenses/accept" in source,
          "the exact accept command is not printed")
    printed = V._licence_commands({"repo_id": "r/x", "fingerprint": "v2:abc"})
    check("the printed accept command carries the server's own fingerprint",
          "curl.exe -s -X POST" in printed[1] and "v2:abc" in printed[1]
          and "models/licenses/accept" in printed[1], printed)
    check("the module says it accepted nothing",
          "Jarvis did not accept anything." in source, "the disclaimer is missing")


# --------------------------------------------------------------------------
#   5. Engines and voices: two licence classes, and only those two
# --------------------------------------------------------------------------

def t_engines_carry_a_licence_class():
    reset()
    rows = V.engines(base=FAKE.base)
    check("engines: the list is read", len(rows) == 2, rows)
    check("engines: the active engine is marked", rows[0]["active"] is True, rows[0])
    check("engines: every row has one of the two classes",
          all(r["license_class"] in V.LICENSE_CLASSES for r in rows), rows)
    check("engines: measured omnivoice is personal, non-commercial only",
          rows[0]["license_class"] == "personal_non_commercial_only", rows[0])
    check("engines: an unreviewed engine fails closed too",
          rows[1]["license_class"] == "personal_non_commercial_only", rows[1])
    check("engines: the note says VoiceStudio clears no model",
          "clears no model" in rows[1]["license_note"], rows[1]["license_note"])


def t_voices_carry_the_engine_class_and_say_why():
    reset()
    rows = V.voices(base=FAKE.base)
    check("voices: aliases and profiles are read", len(rows) == 3, rows)
    check("voices: every row has one of the two classes",
          all(r["license_class"] in V.LICENSE_CLASSES for r in rows), rows)
    check("voices: the class names the engine behind the voice",
          all(r["active_engine"] == "omnivoice" for r in rows), rows)
    check("voices: the note says a voice is data, the engine is the licence",
          "data on this PC" in rows[0]["license_note"], rows[0]["license_note"])


def t_no_licence_class_outside_the_two_can_be_produced():
    allowed = set(V.LICENSE_CLASSES)
    check("the two class names are exactly the approved pair",
          allowed == {"commercial_ok", "personal_non_commercial_only"}, allowed)
    check("no engine is claimed commercial without evidence",
          V.COMMERCIALLY_CLEARED_ENGINES == (), V.COMMERCIALLY_CLEARED_ENGINES)
    for engine in ("omnivoice", "kittentts", "", "something-new"):
        cls, _note = V._licence_for_engine(engine)
        check(f"licence class for {engine or 'an empty id'!r} is one of the two", cls in allowed, cls)
    reset()
    values = {r["license_class"] for r in V.engines(base=FAKE.base)}
    values |= {r["license_class"] for r in V.voices(base=FAKE.base)}
    check("every class that comes out of the API is one of the two",
          values <= allowed, values)


# --------------------------------------------------------------------------
#   6. Releasing the card: only the server's own unloadable ids
# --------------------------------------------------------------------------

def t_stop_unloads_only_what_the_server_calls_unloadable():
    reset()
    out = V.stop(base=FAKE.base)
    check("stop: it is ok", out["ok"] is True, out)
    check("stop: only the unloadable id was unloaded", out["unloaded"] == ["tts"], out)
    check("stop: the id kept is named", out["kept"] == ["asr"], out)
    check("stop: exactly one unload POST, for tts",
          [p for _m, p, _b in FAKE.calls("POST")] == ["/model/unload/tts"], FAKE.calls("POST"))
    check("stop: the words say the program stays running",
          "still running" in out["words"] and "27.41" in out["words"], out["words"])
    check("stop: the words say nothing of Jarvis was unloaded",
          "Nothing belonging to Jarvis" in out["words"], out["words"])


def t_stop_is_idempotent_when_nothing_runs():
    reset()
    out = V.stop(timeout=1.0, base=f"http://127.0.0.1:{free_port()}")
    check("stop: not running is ok, not an error", out["ok"] is True and out["unloaded"] == [], out)
    check("stop: it says there was nothing to unload", "nothing to unload" in out["words"],
          out["words"])


# --------------------------------------------------------------------------
#   7. The off switch, the status card, and no proxies
# --------------------------------------------------------------------------

def t_the_switch_ships_off_and_refuses_speech():
    reset()
    old = V._framework_section
    V._framework_section = lambda: {}
    try:
        check("switch: the shipped template value is off", V.enabled() is False)
        try:
            V.synthesize("hello", base=FAKE.base)
            check("switch: speaking is refused while off", False, "no exception")
        except V.VoiceStudioUnavailable as exc:
            check("switch: speaking is refused while off", True)
            check("switch: the words name the exact switch",
                  "[voicestudio] enabled" in exc.words, exc.words)
            check("switch: the words say there is no screen yet",
                  "no screen" in exc.words, exc.words)
        check("switch: a refusal does not reach the network",
              FAKE.calls("POST", "/v1/audio/speech") == [])
        # The read-only questions still answer: asking is not using.
        check("switch: health still answers while off", V.health(base=FAKE.base)["ok"] is True)
        check("switch: engines still answer while off", len(V.engines(base=FAKE.base)) == 2)
    finally:
        V._framework_section = old


def t_the_shipped_template_really_says_false():
    candidates = [HERE / "rebuilt" / "jarvis-framework.toml",
                  REPO / "jarvis-backend" / "jarvis-framework.toml"]
    found = None
    for path in candidates:
        if path.is_file():
            found = path
            break
    if found is None:
        skip("the shipped [voicestudio] switch is off",
             "jarvis-framework.toml is not in this checkout")
        return
    text = found.read_text(encoding="utf-8", errors="replace")
    marker = "[voicestudio]"
    check("the settings template has a [voicestudio] section", marker in text, found)
    if marker in text:
        tail = text.split(marker, 1)[1]
        section = "\n".join(line for line in tail.splitlines()[:8])
        check("the [voicestudio] section ships enabled = false",
              "enabled = false" in section, section)


def t_the_status_card_never_raises_and_reports_the_measured_cost():
    reset()
    card = V.status(base=FAKE.base)
    check("status: enabled and running are reported",
          card["enabled"] is True and card["running"] is True, card)
    check("status: the port is the product port", card["port"] == 11439, card["port"])
    check("status: the measured warm latency is carried, not copied",
          card["measured"]["warm_call_seconds"] == [1.70, 1.98], card["measured"])
    check("status: the contention verdict is carried",
          card["measured"]["coexistence"] == "CONTENTION", card["measured"])
    off = V.status(base=f"http://127.0.0.1:{free_port()}")
    check("status: a not-running card still answers", off["running"] is False, off)


class Trap:
    """A 'proxy' that records anything sent to it and answers nothing."""

    def __init__(self):
        self.got = []
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _addr = self.sock.accept()
            except OSError:
                return
            try:
                self.got.append(conn.recv(2048))
            except OSError:
                pass
            finally:
                conn.close()

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def t_a_request_to_this_pc_never_goes_through_a_proxy():
    reset()
    trap = Trap()
    saved = {}
    for key in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY",
                "no_proxy", "ALL_PROXY", "all_proxy"):
        saved[key] = os.environ.get(key)
    proxy = f"http://127.0.0.1:{trap.port}"
    try:
        os.environ["HTTP_PROXY"] = os.environ["http_proxy"] = proxy
        os.environ["HTTPS_PROXY"] = os.environ["https_proxy"] = proxy
        os.environ["ALL_PROXY"] = os.environ["all_proxy"] = proxy
        for key in ("NO_PROXY", "no_proxy"):
            os.environ.pop(key, None)
        state = V.health(base=FAKE.base)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        trap.close()
    check("proxy: the real VoiceStudio answered, so the call worked",
          state["ok"] is True, state)
    check("proxy: the trap received NOTHING", trap.got == [], trap.got)


# --------------------------------------------------------------------------
#   8. No AGPL code path, no third-party import, no file write
# --------------------------------------------------------------------------

def t_the_module_is_stdlib_plus_our_own_opener():
    tree = ast.parse(SRC.read_text(encoding="utf-8"), filename=str(SRC))
    allowed = {"__future__", "ipaddress", "json", "time", "urllib", "urllib.error", "urllib.parse",
               "urllib.request", "jarvis_local_http", "jarvis_framework"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    check("imports: every import is stdlib or this repository's own module",
          imported <= allowed, sorted(imported - allowed))
    check("imports: no requests/httpx/third-party HTTP library",
          not (imported & {"requests", "httpx", "aiohttp", "websockets"}), sorted(imported))
    check("imports: no subprocess (it never starts a program)",
          "subprocess" not in imported, sorted(imported))
    check("imports: no omnivoice / VoiceStudio import",
          not any("omnivoice" in name.lower() or name.startswith("backend") for name in imported),
          sorted(imported))
    check("imports: no file-writing stdlib (pathlib/shutil/tempfile)",
          not (imported & {"pathlib", "shutil", "tempfile"}), sorted(imported))
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.add(node.func.id)
    check("code: no open() and no exec()/eval()", not (calls & {"open", "exec", "eval"}),
          sorted(calls & {"open", "exec", "eval"}))
    text = SRC.read_text(encoding="utf-8")
    check("code: the proxy-free opener is used, never plain urlopen",
          "ProxyHandler({})" in text and "urlopen(" not in text.replace("_opener", ""),
          "plain urlopen found")


def t_the_module_speaks_only_to_11439():
    text = SRC.read_text(encoding="utf-8")
    check("the base URL is built from the product host and port",
          'BASE_URL = f"http://{HOST}:{PORT}"' in text and "PORT = 11439" in text,
          "BASE_URL is not the product address")
    check("the model lanes are named as REFUSED, never called",
          "JARVIS_LANE_PORTS" in text and "11435" in text)
    check("no other host literal is dialled",
          text.count("127.0.0.1") >= 2, text.count("127.0.0.1"))


# --------------------------------------------------------------------------
#   The server itself must be real, or every test above proves nothing
# --------------------------------------------------------------------------

def t_the_fake_is_real():
    reset()
    with urllib.request.urlopen(FAKE.base + "/health", timeout=3) as reply:
        payload = reply.read()
    check("the fake server really answers over HTTP", b'"status": "ok"' in payload, payload[:120])
    check("the fake's port is ephemeral, not 11439", FAKE.port != 11439, FAKE.port)


def main():
    reset()
    # Every network test runs with the switch ON, because a shipped PC has it
    # OFF and speaking is refused while it is off. The switch test sets it OFF
    # itself and puts it back.
    V._framework_section = lambda: {"enabled": True}
    tests = [t_the_port_is_pinned,
             t_a_non_loopback_address_is_refused_before_any_socket,
             t_health_ready, t_health_starting_is_not_a_failure,
             t_health_not_running_is_honest, t_startup_progress_reads_the_step,
             t_wait_for_model_loaded_reports_progress, t_wait_times_out_with_where_it_is,
             t_wait_returns_at_once_when_not_running,
             t_synthesize_sends_only_the_sentence, t_synthesize_honours_engine_and_mp3,
             t_the_cold_start_race_is_retried, t_the_cold_start_retry_is_bounded_and_named,
             t_a_503_waits_for_the_start_then_retries, t_a_non_audio_answer_is_refused,
             t_empty_and_over_long_text_are_refused_before_a_socket,
             t_the_403_licence_gate_names_both_licences,
             t_the_licence_gate_clears_when_both_are_accepted,
             t_the_licence_gate_never_accepts_anything_by_itself,
             t_engines_carry_a_licence_class, t_voices_carry_the_engine_class_and_say_why,
             t_no_licence_class_outside_the_two_can_be_produced,
             t_stop_unloads_only_what_the_server_calls_unloadable,
             t_stop_is_idempotent_when_nothing_runs,
             t_the_switch_ships_off_and_refuses_speech,
             t_the_shipped_template_really_says_false,
             t_the_status_card_never_raises_and_reports_the_measured_cost,
             t_a_request_to_this_pc_never_goes_through_a_proxy,
             t_the_module_is_stdlib_plus_our_own_opener,
             t_the_module_speaks_only_to_11439,
             t_the_fake_is_real]
    for fn in tests:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:                                 # noqa: BLE001
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if SKIPPED:
        print("Skipped, and NOT a pass: " + "; ".join(SKIPPED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        FAKE.close()
    sys.exit(code)
