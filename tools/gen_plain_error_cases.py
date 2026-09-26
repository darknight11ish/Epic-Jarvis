#!/usr/bin/env python3
"""Writes the plain-words contract file for both apps, and checks it.

    python3 tools/gen_plain_error_cases.py            # write both copies
    python3 tools/gen_plain_error_cases.py --check    # compare only

WHAT IT IS FOR (the creativity audit, 2026-09-25, item 5: "error messages
in plain words, with the fix on the spot"). When something goes wrong, both
apps say the SAME short sentence, then ONE concrete thing to do - a button
or the exact place in Settings - with the technical details behind a
"Details" toggle for bug reports, and never a secret in them. This file is
the one list of those words, and of the rules that pick them:

    jarvis-desktop/tests/fixtures/plain-error-cases.json
    jarvis-client/app/src/test/resources/contract/plain-error-cases.json

(byte-identical). Each app keeps its own copy of the words in code
(jarvis-desktop/src/plain-errors.js, src-tauri/src/plain_errors.rs for the
three the Rust side says itself, and the phone's net/PlainErrors.kt) and its
tests fail if a word differs from this file:

  * `kinds` - every kind of failure: what happened (`says`), what to do
    (`fix`), and the one button (`button`, `action`; "" and "none" when the
    fix is something to do on the PC). The words live HERE: this file is
    their source. An action is an id each app turns into its own place:
    "retry" (ask again), "reconnect" (the link), "connection" (the
    connection settings: the desktop's Settings -> Connection, the phone's
    Checks), "models" (the desktop's Brain, the phone's Brain -> Model).
  * `statuses` - the words for a wait: "Thinking…", and "Waking up the
    model…" when the PC says the model is still loading (jarvis_agent's
    "loading" status word), "Answering…" once words arrive.
  * `classify` - what each app must pick for a failure, described the same
    way on both sides: a network failure's kind, an HTTP status and whether
    the PC said a sentence, the stream's error `code` (jarvis_agent.
    ERROR_CODES - taken from the backend, not typed here), and so on.
  * `scrub` - text the Details may be built from, with the parts that must
    be gone (tokens, keys, passwords, email addresses, the Windows user
    name) and the parts that must stay (an address, a status code). Both
    apps' scrubbers must pass every case. The rules are the backend's log
    scrubber's (backend/jarvis_scrub.py), and every `gone` value is checked
    here against that scrubber too, so the three never disagree about what
    is a secret.
  * `manner` - the words of "How Jarvis talks" (warm and brief, or plain),
    from backend/jarvis_manner.py itself, for both apps' settings.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", tempfile.mkdtemp(prefix="jarvis-plain-"))
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_agent as AG  # noqa: E402
import jarvis_manner as MANNER  # noqa: E402
import jarvis_scrub as SCRUB  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "plain-error-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "plain-error-cases.json")
COPIES = (DESKTOP, PHONE)

#: The buttons, by action. The same label wherever the action is offered.
BUTTONS = {
    "retry": "Try again",
    "reconnect": "Reconnect",
    "connection": "Check the connection settings",
    "models": "Choose a model",
    "none": "",
}

#: Every kind of failure, in plain words: what happened, what to do, and
#: the one button. Short sentences; no codes, no "HTTP", no jargon.
KINDS = {
    "pc_unreachable": (
        "Your PC isn't answering.",
        "It may be asleep or switched off, or Tailscale or NordVPN Meshnet may be off at one "
        "end. Wake the PC, check the private network on both, then try again.",
        "retry"),
    "jarvis_not_running": (
        "Jarvis isn't running on your PC.",
        "The PC is on, but Jarvis is not started. On the PC, open Jarvis Desktop's Settings, "
        "then More options, and press Start under \"Starting Jarvis for you\" (it needs \"Let "
        "Jarvis Desktop start and stop Jarvis\" on). Or start it in PowerShell, the way you set "
        "it up. Then try again.",
        "retry"),
    "name_not_found": (
        "This device can't find your PC by its name.",
        "Check that Tailscale or NordVPN Meshnet is on here, and that the PC's name in the "
        "connection settings is right.",
        "connection"),
    "device_offline": (
        "This device isn't connected to a network.",
        "Turn on Wi-Fi or mobile data, then try again.",
        "retry"),
    "connection_dropped": (
        "The connection to your PC dropped.",
        "Try again. If it keeps happening, check the private network is steady at both ends.",
        "retry"),
    "link_stale": (
        "The connection to your PC is catching up.",
        "Nothing can be sent until it does. Wait a moment, or reconnect.",
        "reconnect"),
    "token_wrong": (
        "Your PC didn't accept this app's pairing key.",
        "Enter the key again in the connection settings. The PC's desktop app shows it: "
        "Settings, \"Show the token for my phone\".",
        "connection"),
    "not_paired": (
        "This app isn't connected to a PC yet.",
        "Add your PC's name and pairing key in the connection settings.",
        "connection"),
    "not_jarvis": (
        "Something answered at that address, but it isn't Jarvis.",
        "Check the PC's name and port in the connection settings.",
        "connection"),
    "backend_too_old": (
        "Your PC's Jarvis is too old for this.",
        "Update it: on the PC, run apply-patches.ps1, then restart Jarvis. The steps are in Help: \"How do I update Jarvis?\"",
        "none"),
    "feature_off": (
        "That part of Jarvis isn't running on your PC right now.",
        "Restart Jarvis on the PC. If it stays off, update it - the steps are in Help: \"How do I update Jarvis?\"",
        "none"),
    "server_error": (
        "Jarvis on your PC ran into a problem.",
        "Try again. If it keeps happening, restart Jarvis on the PC and send the Details with "
        "a bug report.",
        "retry"),
    "unreadable": (
        "Your PC answered in a way this app can't read.",
        "Update both: run apply-patches.ps1 on the PC, and install the latest app. The steps are in Help: \"How do I update Jarvis?\"",
        "none"),
    "timeout": (
        "Jarvis took too long to answer.",
        "Try again in a moment. If it keeps happening, restart Ollama on the PC.",
        "retry"),
    "model_missing": (
        "The AI model Jarvis uses isn't installed on your PC.",
        "Choose a model you have (Models, in the Brain on the PC or the phone), "
        "or install this one.",
        "models"),
    "model_not_running": (
        "The AI model isn't running on your PC.",
        "Open Ollama on the PC (or restart Jarvis), then try again.",
        "retry"),
    "model_stuck": (
        "The AI model stopped answering.",
        "Restart Ollama on the PC, then try again.",
        "retry"),
    "model_stopped": (
        "The AI model stopped in the middle of the answer.",
        "Try again. If it keeps happening, restart Ollama on the PC.",
        "retry"),
    "model_error": (
        "The AI model reported a problem.",
        "Try again. If it keeps happening, restart Ollama on the PC.",
        "retry"),
    "key_store_refused": (
        "Windows Credential Manager wouldn't save it.",
        "Nothing was written anywhere else. Try again; if it keeps failing, restart the PC "
        "and try once more.",
        "retry"),
    # The PC said what is wrong in a sentence of its own (a refusal with a
    # reason): that sentence IS the plain words, shown as it is.
    "pc_said": ("", "", "none"),
}

#: The waits. "loading" is jarvis_agent's status word for a model that is
#: not in memory yet.
STATUSES = {
    "thinking": "Thinking\u2026",
    "loading": "Waking up the model - the first answer after standby takes a little longer.",
    "working": "Working\u2026",
    "approval": "Waiting for your approval\u2026",
    "answering": "Answering\u2026",
}

#: The stream's `code` (jarvis_agent.ERROR_CODES) -> a kind above.
CODE_KINDS = {code: code for _, code in AG.ERROR_CODES}

#: The Details are at most this many characters, after scrubbing.
DETAILS_MAX = 600

#: What each app must pick. `input` is the failure, described the same way
#: on both sides; `kind` the answer.
CLASSIFY = [
    ("nothing listening (connection refused)", {"network": "refused"}, "jarvis_not_running"),
    ("no answer while connecting", {"network": "connect_timeout"}, "pc_unreachable"),
    ("no route to the PC", {"network": "no_route"}, "pc_unreachable"),
    ("the PC's name is not found", {"network": "unknown_host"}, "name_not_found"),
    ("this device has no network", {"network": "no_network"}, "device_offline"),
    ("connected, then no answer in time", {"network": "read_timeout"}, "timeout"),
    ("the connection broke", {"network": "dropped"}, "connection_dropped"),
    ("no PC address saved", {"not_paired": True}, "not_paired"),
    ("the link is stale", {"stale": True}, "link_stale"),
    ("401", {"http": 401}, "token_wrong"),
    ("403 with a sentence", {"http": 403, "said": "bad or missing X-Jarvis-Token"}, "token_wrong"),
    ("404, no sentence (no such route)", {"http": 404}, "backend_too_old"),
    ("501", {"http": 501}, "backend_too_old"),
    ("503 available false (the module is missing)", {"http": 503, "available": False},
     "backend_too_old"),
    ("503, no sentence", {"http": 503}, "feature_off"),
    ("503 with the PC's sentence", {"http": 503, "said": "the second card is not detected"},
     "pc_said"),
    ("400 with the PC's sentence", {"http": 400, "said": "send exactly one change"}, "pc_said"),
    ("404 with the PC's sentence (a model that is not installed)",
     {"http": 404, "said": "model \"qwen3:14b\" not found"}, "pc_said"),
    ("500, no sentence", {"http": 500}, "server_error"),
    ("502, no sentence", {"http": 502}, "server_error"),
    ("418, no sentence", {"http": 418}, "server_error"),
    ("an answer that is not what was expected", {"malformed": True}, "unreadable"),
    ("something that is not Jarvis", {"not_jarvis": True}, "not_jarvis"),
    ("Credential Manager refused", {"key_store": True}, "key_store_refused"),
    ("a stream error with an unknown code", {"code": "something_new", "said": "It broke."},
     "pc_said"),
    ("a stream error with no code", {"said": "The local model answered oddly."}, "pc_said"),
] + [(f"the stream's code {code}", {"code": code, "said": "(the PC's sentence)"}, kind)
     for code, kind in CODE_KINDS.items()]

# Fakes, built by concatenation so no real-looking secret sits in this file.
_TOKEN = "Qx7" + "k2mZr9Lw4Tn8Bv1Hs6Dj3Fp0Yc5Ge2Ua" + "9Wq4Ri7"          # 43 characters
_SK = "sk-" + "proj-" + "A1b2C3d4E5f6G7h8I9j0K1l2"
_GH = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz0123456789AB"
_TV = "tv" + "ly-" + "dev-" + "abcdefghijklmnopqrstuvwx"
_PW = "hunter2" + "Secret99"

#: The Details' scrubbing cases: `gone` must not survive, `kept` must.
SCRUB_CASES = [
    {"input": f"GET http://100.64.1.2:8765/api/version X-Jarvis-Token: {_TOKEN} failed",
     "gone": [_TOKEN], "kept": ["100.64.1.2:8765", "/api/version"]},
    {"input": f"failed to connect to /100.64.1.2 (port 8765) token={_TOKEN}&x=1",
     "gone": [_TOKEN], "kept": ["100.64.1.2", "8765"]},
    {"input": f"Authorization: Bearer {_SK}", "gone": [_SK], "kept": ["Authorization"]},
    {"input": f"Tavily said 401 for key {_TV}", "gone": [_TV], "kept": ["Tavily", "401"]},
    {"input": f"clone https://owner:{_PW}@github.com/x/y failed: {_GH}",
     "gone": [_PW, _GH], "kept": ["github.com"]},
    {"input": f"password = {_PW}", "gone": [_PW], "kept": ["password"]},
    {"input": "could not read C:\\Users\\JaneOwner\\.openjarvis\\manner.json",
     "gone": ["JaneOwner"], "kept": ["manner.json"]},
    {"input": "IMAP login for jane.owner@example.com refused", "gone": ["jane.owner@example.com"],
     "kept": ["IMAP login"]},
    {"input": "HTTP 503: the model is still loading", "gone": [],
     "kept": ["HTTP 503", "the model is still loading"]},
    {"input": "java.net.SocketTimeoutException: failed to connect to desktop.tail1234.ts.net/"
              "100.101.102.103 (port 8765) after 10000ms",
     "gone": [], "kept": ["SocketTimeoutException", "100.101.102.103", "8765", "10000ms"]},
]

#: A token the app holds is gone whatever it looks like (the apps pass it in).
KNOWN_TOKEN_CASE = {"token": "short-but-known", "input": "sent short-but-known to the PC",
                    "gone": ["short-but-known"], "kept": ["to the PC"]}


def _check_scrub_against_backend() -> None:
    """Every secret this file says must be gone, the backend's own log
    scrubber takes out too - so the apps and the log agree."""
    # The backend registers these two by value: the pairing token at start
    # (jarvis_scrub.install) and a search key each time it is read
    # (jarvis_search._key). The apps have no such list for search keys, so
    # their Details also take out the key SHAPES (sk-, tvly-, ghp_ ...).
    SCRUB.register_secret(_TOKEN)
    SCRUB.register_secret(_TV)
    for case in SCRUB_CASES:
        out = SCRUB.scrub_text(case["input"])
        for g in case["gone"]:
            assert g not in out, f"jarvis_scrub leaves {g!r} in {out!r}"


def cases() -> dict:
    _check_scrub_against_backend()
    kinds = {}
    for kind, (says, fix, action) in KINDS.items():
        assert action in BUTTONS, (kind, action)
        kinds[kind] = {"says": says, "fix": fix, "action": action, "button": BUTTONS[action]}
    for name, inp, kind in CLASSIFY:
        assert kind in KINDS, (name, kind)
    missing = set(KINDS) - {k for _, _, k in CLASSIFY}
    assert not missing, f"kinds no case picks: {missing}"
    for code in CODE_KINDS.values():
        assert code in KINDS, code
    view = MANNER.view()
    view.pop("manner", None)            # the setting, not a word
    return {
        "_about": ("The plain words both apps show when something goes wrong, the waits, and "
                   "\"How Jarvis talks\"; the rules that pick them; and the Details scrubber's "
                   "cases. Made by tools/gen_plain_error_cases.py - do not edit by hand."),
        "kinds": kinds,
        "buttons": BUTTONS,
        "statuses": STATUSES,
        "codes": CODE_KINDS,
        "details_max": DETAILS_MAX,
        "classify": [{"name": n, "input": i, "kind": k} for n, i, k in CLASSIFY],
        "scrub": SCRUB_CASES,
        "scrub_known_token": KNOWN_TOKEN_CASE,
        "manner": dict(view, said=dict(MANNER.SAID)),
    }


def render() -> str:
    return json.dumps(cases(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        stale = [p for p in COPIES
                 if not p.is_file() or p.read_text(encoding="utf-8").replace("\r\n", "\n") != text]
        for p in stale:
            print(f"{p.relative_to(ROOT)} is out of date: run python3 tools/gen_plain_error_cases.py")
        if stale:
            return 1
        print("plain-error-cases.json matches the producer (desktop and phone copies).")
        return 0
    for p in COPIES:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
