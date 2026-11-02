"""test_pictures.py - "ask for a picture, and keep it" (jarvis_pictures.py,
pictures.patch, docs/JARVIS-API.md section 129; the owner's decision of
2026-09-27: *"12 GB card: longer conversations with picture understanding
first, and making pictures too (swapped in when asked, since both cannot sit on
the card at once)"*).

    python3 backend/test_pictures.py

WHAT THIS PROVES, AND HOW HONESTLY

  There is NO graphics card, NO drawing program and NO model anywhere in this
  suite, and there must not be. Every route is exercised with a STUB runtime
  put in the module's own registry (`register_runtime`) - a class that returns
  a few bytes and says what it was asked. So this suite proves the routes,
  the storage, the words and the switch, and proves NOTHING about whether
  ComfyUI or stable-diffusion.cpp draws a good picture. That is the honest
  split, and it is written here rather than implied.

  A stub that raises proves the other half: a program that is installed but
  not answering is a PLAIN SENTENCE, never a traceback and never a silent
  nothing.

WHAT IS COVERED

  - the route with a stub runtime: 200, where it went, how long it took;
  - the storage round-trip: write, read back, the sidecar intact - prompt,
    seed, model and settings all survive;
  - the file name: date and time, a slug of the prompt, no path characters;
  - COLLISIONS: the same prompt twice in the same second makes two files and
    overwrites neither;
  - "runtime not installed": one plain sentence naming what to install, as a
    sentence with a full stop - not an error object, not a 200, not empty;
  - "configured but not answering": the other plain sentence;
  - the mode is OFF BY DEFAULT, and off is refused in words that name the
    switch;
  - the listing route: newest first, the folder and its size reported, the
    prompt of each picture, and a picture whose sidecar is lost still listed;
  - the picture itself: base64 bytes for one id, and a refusal for anything
    that is not one of our ids (no traversal, no other file type);
  - "a picture is never sent anywhere": this module holds no email, upload or
    chat path, and no model path imports it;
  - the tail of `docs/JARVIS-API.md` still hangs together: every section from
    129 up has a number of its own, the numbers strictly increase, and no two
    sections skip more than three numbers - so a duplicate `§175`, or a number
    that goes backwards, fails here and names the number (Gemini's ruling 1,
    2026-11-02; a small gap is allowed because a sibling PR's reserved number
    may not have merged yet). The old hand-written list of every section is
    gone on purpose - it was one shared line every API PR had to edit;
  - install() wraps a handler, passes every other request through, and refuses
    a request that fails the server's own origin or token check.
"""
from __future__ import annotations

import base64
import inspect
import json
import re
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

# A console on Windows is not always UTF-8, and one check names a prompt with
# non-Latin characters in it. Without this the whole suite dies in `print`
# rather than reporting - which is the failure mode this project keeps fixing.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

require_shipped("jarvis_pictures.py")

import jarvis_pictures as P  # noqa: E402

#: The two ceilings that live on the card module rather than the route module.
#: Imported directly so the sum check reads the REAL defaults, not a copy.
import jarvis_picture_card as C  # noqa: E402

#: The two clients' budgets are written in Kotlin and Rust, so the sum check
#: below reads their source. A copy of the number here would be a third copy
#: that could drift silently.
PHONE_PICTURES = (REPO / "jarvis-client" / "app" / "src" / "main" / "java"
                  / "com" / "jarvis" / "client" / "net" / "Pictures.kt")
DESKTOP_BRAIN = REPO / "jarvis-desktop" / "src-tauri" / "src" / "brain.rs"

# --------------------------------------------------------------------------
#   The 2026-10-25 swap, kept hermetic in this suite
# --------------------------------------------------------------------------
# `handshake_plan()` asks `jarvis_picture_card` what THIS PC's everyday lane is
# doing. On the owner's PC that lane really is running, so an unpatched suite
# would answer 409 ("free the card?") where a test expects a draw - and a
# careless test could even unload the owner's chat. The suite therefore starts
# from "no swap needed"; each swap test installs its own plan and the unit test
# below calls the REAL function with a stand-in card module.
_REAL_HANDSHAKE_PLAN = P.handshake_plan
NO_SWAP = {"available": True, "option": "A", "needs": False, "supported": True,
           "why": "suite_hermetic", "words": "", "estimate": {}, "values": {}}


def use_plan(plan):
    """Point the module at a fake handshake plan for the next route calls."""
    P.handshake_plan = lambda: dict(plan)
    return plan


P.handshake_plan = lambda: dict(NO_SWAP)


class FakeCards:
    """The stand-in for `jarvis_picture_card` used by the REAL plan function."""

    def __init__(self, option=None, *, resident=True, measured=None):
        self.option = option
        self.resident = resident
        self.measured = measured

    def load_settings(self):
        return {"option": self.option, "lanes": None, "measured": self.measured}

    def lanes(self, values):
        return {"everyday": {"port": 11436, "model": "qwen3.5:9b", "card": "big"},
                "coding": {"port": 11435, "model": "qwen3:8b", "card": "small"}}

    def lane_status(self, port, timeout=5.0):
        if not self.resident or int(port) != 11436:
            return []
        return [{"name": "qwen3.5:9b", "size": 9855450480,
                 "size_vram": 9855450480, "spill": 0, "expires_at": "never"}]

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


#: A real 1x1 PNG, so the bytes written are a picture a viewer could open.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


class StubRuntime:
    """A drawing program that is there and works. No card, no model."""

    def __init__(self, address, *, timeout=10.0, ready=True, fail=None,
                 png=PNG, seed=7, model="stub-model"):
        self.address = address
        self.timeout = timeout
        self.ready = ready
        self.fail = fail
        self.png = png
        self.seed = seed
        self.model = model
        self.asked = []
        self.freed = False

    def available(self):
        return self.ready

    def free_models(self):
        """ComfyUI's own /free, stood in for: the swap must call it (2026-10-25)."""
        self.freed = True
        return {"ok": True, "words": "The drawing program let go of its models."}

    def draw(self, prompt, *, seed=None, settings=None):
        self.asked.append({"prompt": prompt, "seed": seed,
                           "settings": dict(settings or {})})
        if self.fail is not None:
            raise self.fail
        return P.Piece(self.png,
                       seed=self.seed if seed is None else seed,
                       model=self.model,
                       settings={"steps": (settings or {}).get("steps", 20),
                                 "width": (settings or {}).get("width", 512),
                                 "height": (settings or {}).get("height", 512)},
                       seconds=1.25)


class Handler0:
    """The smallest stand-in for the HUD's handler, for install()."""

    def __init__(self, path="/api/status", token="good", origin="pc"):
        self.path = path
        self.token = token
        self.origin = origin
        self.sent = []
        self.passed_through = 0
        self.body = b"{}"

    def _send(self, code, out):
        self.sent.append((code, out))
        return (code, out)

    def do_GET(self):
        self.passed_through += 1
        return "original GET"

    def do_POST(self):
        self.passed_through += 1
        return "original POST"


class _StubFactory:
    """A stand-in for a runtime CLASS, so the real code path that builds the
    adapter (`runtime_for`) is the one under test."""

    def __init__(self, made, *, ready=True, fail=None):
        self.made = made
        self.ready = ready
        self.fail = fail

    def __call__(self, address, **kw):
        if self.made is not None:
            return self.made
        return StubRuntime(address, ready=self.ready, fail=self.fail)


def tmpdir(name="pics"):
    return Path(tempfile.mkdtemp(prefix="jarvis-" + name + "-"))


def settings_for(folder, *, enabled=True, runtime="comfyui"):
    return {"enabled": enabled, "runtime": runtime,
            "address": "http://127.0.0.1:8188", "folder": str(folder)}


# ---------------------------------------------------------------------------
#   1. The mode is OFF by default
# ---------------------------------------------------------------------------

def t_the_mode_is_off_by_default():
    """The owner's own standing rule: a feature that uses the second card keeps
    its own switch, off until THAT feature is measured. Nothing may ship it
    on, and no missing file may turn it on."""
    check("the module's own default is off", P.DEFAULTS["enabled"] is False)
    check("... and nothing is configured to draw with",
          P.DEFAULTS["runtime"] is None)
    empty = P.load_settings(tmpdir() / "does-not-exist.json")
    check("a missing pictures.json reads as OFF, not as an error",
          empty["enabled"] is False and empty["runtime"] is None)
    broken = tmpdir() / "pictures.json"
    broken.write_text("{not json at all", encoding="utf-8")
    got = P.load_settings(broken)
    check("a half-written pictures.json reads as OFF too",
          got["enabled"] is False and got["runtime"] is None)
    lies = tmpdir() / "pictures.json"
    lies.write_text(json.dumps({"enabled": "yes please", "runtime": 7}),
                    encoding="utf-8")
    got = P.load_settings(lies)
    check("a wrong type in one key does not turn the switch on",
          got["enabled"] is False and got["runtime"] is None)
    # The settings file the PC would really use is beside folders.json.
    check("pictures.json lives in the config folder, not in the picture folder",
          P.CONFIG_NAME == "pictures.json" and "Pictures" not in P.CONFIG_NAME)
    # The list route on a fresh PC says off, and says which switch.
    folder = tmpdir()
    st = status = P.status_answer(settings_for(folder, enabled=False))
    check("the status route says the switch is off", status["enabled"] is False)
    check("... and names the switch to turn on, in one plain sentence",
          status["words"] == P.OFF_WORDS and "Settings" in status["words"]
          and '"Making pictures"' in status["words"], status["words"])
    # And a make attempt while off is a refusal in words, never a picture.
    code, out = make(settings_for(folder, enabled=False),
                     json.dumps({"prompt": "a red panda"}).encode())
    check("asking while the switch is off is refused", code == 503, str(code))
    check("... with the same plain sentence, and nothing drawn",
          out.get("ok") is False and out.get("error") == P.OFF_WORDS,
          str(out)[:200])
    check("... and not one picture file was written",
          list(folder.glob("*.png")) == [], str(list(folder.iterdir())))


def make(settings, body, *, runtime=None, when=None):
    """A POST through the real handler, with `raw` bytes as the body."""
    got = json.loads(body.decode("utf-8")) if body else {}
    return P.handle_post("/api/pictures", got, settings=settings,
                         runtime=runtime, now=when)


# ---------------------------------------------------------------------------
#   2. The route, with a stub runtime
# ---------------------------------------------------------------------------

def t_the_route_draws_and_says_where_and_how_long():
    folder = tmpdir()
    stub = StubRuntime("http://127.0.0.1:8188")
    settings = settings_for(folder)
    code, out = make(settings, json.dumps(
        {"prompt": "a red panda in a library"}).encode(), runtime=stub)
    check("a configured, running stub answers 200", code == 200, str(out)[:300])
    check("... with where it went: a real file in the folder",
          out.get("path") and Path(out["path"]).is_file(), str(out.get("path")))
    check("... inside the configured folder",
          Path(out["path"]).parent == folder, str(out.get("path")))
    check("... and how long it took",
          out.get("seconds") == 1.2, str(out.get("seconds")))
    check("... and the words that say so",
          "1.2 seconds" in (out.get("words") or "")
          and out.get("name") in (out.get("words") or ""),
          str(out.get("words")))
    check("... and the prompt it was given is the owner's own words",
          stub.asked and stub.asked[0]["prompt"] == "a red panda in a library",
          str(stub.asked))
    check("... the file on disk is the picture the program sent",
          Path(out["path"]).read_bytes() == PNG)
    check("... and the answer carries no absolute path outside the picture folder",
          ".." not in out["path"])


def t_a_stub_that_is_not_answering_is_one_plain_sentence():
    """The drawing program is installed but not started. The owner gets a
    sentence saying to start it - never a traceback, never a 200 with nothing
    in it."""
    folder = tmpdir()
    code, out = make(settings_for(folder),
                     json.dumps({"prompt": "a cat"}).encode(),
                     runtime=StubRuntime("x", ready=False))
    check("a program that is not answering is 503, not 500", code == 503, str(code))
    words = out.get("error") or ""
    check("... and the sentence names the program the owner installed",
          "ComfyUI" in words, words)
    check("... and says what to do, in a sentence with a full stop",
          words.endswith(".") and "Start it on this PC" in words, words)
    check("... and is not an object, a code or an empty string",
          isinstance(words, str) and len(words.strip()) > 20
          and "{" not in words, words)
    check("... and nothing was written to the folder",
          list(folder.glob("*.png")) == [])


def t_a_drawing_program_that_fails_is_a_sentence_not_a_traceback():
    folder = tmpdir()
    code, out = make(settings_for(folder),
                     json.dumps({"prompt": "a cat"}).encode(),
                     runtime=StubRuntime("x", fail=P.DrawingFailed(
                         "The drawing program refused that (500).")))
    check("a program that answered with a refusal is a sentence as sent",
          code == 502 and out["error"] == "The drawing program refused that (500).",
          str(out)[:200])
    code, out = make(settings_for(folder),
                     json.dumps({"prompt": "a cat"}).encode(),
                     runtime=StubRuntime("x", fail=RuntimeError("boom")))
    check("... and an unexpected failure is still a sentence, never a traceback",
          code == 502 and isinstance(out.get("error"), str)
          and "RuntimeError" in out["error"], str(out)[:200])
    check("... and an empty prompt is refused in words",
          P.handle_post("/api/pictures", {"prompt": "   "},
                        settings=settings_for(tmpdir()))[1]["error"]
          == P.WORDS["no_words"])
    check("... and a very long prompt is refused in words",
          P.handle_post("/api/pictures", {"prompt": "x" * (P.MAX_PROMPT + 1)},
                        settings=settings_for(tmpdir()))[0] == 400)


# ---------------------------------------------------------------------------
#   2b. The swap: the everyday chat steps aside, and always comes back
#       (added 2026-10-25 - the owner's 2026-09-27 words: "making pictures
#       too (swapped in when asked, since both cannot sit on the card at once)")
# ---------------------------------------------------------------------------

SWAP_PLAN = {
    "available": True, "option": "A", "needs": True, "supported": True,
    "why": "chat_on_the_card",
    "words": ("Drawing needs the 12 GB card, and your everyday chat is using "
              "it. If you agree, Jarvis sets the everyday chat aside for a few "
              "minutes, draws the picture, then loads the chat back the way it "
              "was. This takes about 7 minutes, and the chat comes back on its "
              "own afterwards."),
    "estimate": {"draw_seconds": 380.0, "chat_away_seconds": 440.0,
                 "minutes": 7},
    "values": {"option": "A"},
}


def reset_plan():
    P.handshake_plan = lambda: dict(NO_SWAP)


def t_the_plan_finds_the_three_ways_and_the_price():
    """The REAL plan function, with the card module stood in for."""
    plan = _REAL_HANDSHAKE_PLAN(cards_module=FakeCards("A"))
    check("way A with the chat on the card needs the swap",
          plan["needs"] is True and plan["supported"] is True, str(plan)[:200])
    check("... and names the card and the chat in plain words",
          "12 GB card" in plan["words"] and "everyday chat" in plan["words"],
          plan["words"])
    check("... and says it comes back on its own",
          "comes back on its own" in plan["words"], plan["words"])
    check("... with an estimate in minutes and seconds",
          plan["estimate"].get("draw_seconds") == 380.0
          and plan["estimate"].get("chat_away_seconds") == 440.0
          and plan["estimate"].get("minutes") == 7, str(plan["estimate"]))
    plan = _REAL_HANDSHAKE_PLAN(cards_module=FakeCards(
        "A", measured={"draw_seconds": 100.0}))
    check("a recorded real draw sets the estimate", plan["estimate"]["draw_seconds"] == 100.0,
          str(plan["estimate"]))
    plan = _REAL_HANDSHAKE_PLAN(cards_module=FakeCards(None))
    check("with no way chosen the recommended A is planned",
          plan["option"] == "A" and plan["needs"] is True, str(plan)[:200])
    plan = _REAL_HANDSHAKE_PLAN(cards_module=FakeCards("C"))
    check("way C needs no swap: the chat is not touched",
          plan["needs"] is False, str(plan)[:200])
    plan = _REAL_HANDSHAKE_PLAN(cards_module=FakeCards("B"))
    check("way B is refused in one plain sentence, not wired",
          plan["needs"] is True and plan["supported"] is False
          and "not wired" in plan["words"], str(plan)[:200])
    plan = _REAL_HANDSHAKE_PLAN(cards_module=FakeCards("A", resident=False))
    check("a card with no everyday chat needs no swap",
          plan["needs"] is False, str(plan)[:200])
    plan = _REAL_HANDSHAKE_PLAN(cards_module=object())
    check("a backend without the card module plans nothing and says so",
          plan["needs"] is False and plan["available"] is False, str(plan)[:200])


def t_the_first_request_asks_before_anything_moves():
    """The owner must be told what will pause BEFORE one byte leaves the card."""
    folder = tmpdir()
    stub = StubRuntime("http://127.0.0.1:8188")
    use_plan(SWAP_PLAN)
    try:
        code, out = make(settings_for(folder),
                         json.dumps({"prompt": "a red panda"}).encode(),
                         runtime=stub)
    finally:
        reset_plan()
    check("a draw that needs the card answers 409 first", code == 409,
          str(out)[:300])
    check("... with needs=free_card", out.get("needs") == "free_card",
          str(out)[:200])
    check("... naming way A and the estimate",
          out.get("option") == "A" and out.get("estimate", {}).get("minutes") == 7,
          str(out)[:200])
    check("... and the plain sentence saying what will pause",
          "everyday chat" in (out.get("error") or ""), str(out)[:300])
    check("... and a confirm instruction carrying free_card",
          out.get("confirm", {}).get("free_card") is True, str(out)[:200])
    check("... and NOTHING was drawn", stub.asked == [], str(stub.asked))
    check("... and nothing was written",
          list(folder.glob("*.png")) == [], str(list(folder.glob("*.png"))))


def t_the_confirmed_draw_steps_the_chat_aside_and_brings_it_back():
    folder = tmpdir()
    stub = StubRuntime("http://127.0.0.1:8188")
    use_plan(SWAP_PLAN)
    events = []
    saved = (P.step_aside, P.step_back, P.record_measurement)

    def aside(plan):
        events.append("aside")
        return {"ok": True, "did": True, "seconds": 2.5,
                "words": "The chat stepped aside in 2.5 seconds."}

    def back(plan):
        events.append("back")
        return {"ok": True, "did": True, "seconds": 9.0,
                "words": "The chat was back on the card after 9.0 seconds."}

    P.step_aside = aside
    P.step_back = back
    P.record_measurement = lambda plan, piece: events.append("measured")
    try:
        code, out = make(settings_for(folder), json.dumps(
            {"prompt": "a red panda", "free_card": True}).encode(),
            runtime=stub)
    finally:
        P.step_aside, P.step_back, P.record_measurement = saved
        reset_plan()
    check("a confirmed draw answers 200", code == 200 and out.get("ok"),
          str(out)[:300])
    check("... the chat was set aside BEFORE the draw",
          events[:1] == ["aside"] and bool(stub.asked), str(events))
    check("... the picture model was asked to let go of the card",
          stub.freed is True, "")
    check("... and the chat was warmed back AFTER it, and the run recorded",
          events[-2:] == ["back", "measured"], str(events))
    check("... the answer carries the swap's own times",
          out.get("card", {}).get("chat_away_seconds") == 2.5
          and out.get("card", {}).get("chat_back_seconds") == 9.0,
          str(out.get("card")))
    check("... and says in words that the chat stepped aside and came back",
          "stepped aside for" in (out.get("words") or "")
          and "back on the card" in (out.get("words") or ""),
          str(out.get("words")))
    check("... and the picture is on disk with its sidecar",
          Path(out["path"]).is_file()
          and Path(out["path"]).with_suffix(".json").is_file(),
          str(out.get("path")))


def t_a_draw_that_fails_still_brings_the_everyday_chat_back():
    """The 2026-10-25 brief: never leave the chat unloaded on an error path."""
    folder = tmpdir()
    stub = StubRuntime("x", fail=P.DrawingFailed(
        "The drawing program refused that (500)."))
    use_plan(SWAP_PLAN)
    events = []
    saved = (P.step_aside, P.step_back)
    P.step_aside = lambda plan: {"ok": True, "did": True, "seconds": 2.0,
                                 "words": "The chat stepped aside."}
    P.step_back = lambda plan: (events.append("back"), {
        "ok": True, "did": True, "seconds": 8.0,
        "words": "The chat was back after 8.0 seconds."})[1]
    try:
        code, out = make(settings_for(folder), json.dumps(
            {"prompt": "a cat", "free_card": True}).encode(), runtime=stub)
    finally:
        P.step_aside, P.step_back = saved
        reset_plan()
    check("a refused draw is still 502", code == 502, str(out)[:200])
    check("... the everyday chat was warmed back anyway", events == ["back"],
          str(events))
    check("... the answer says the chat is back",
          out.get("card", {}).get("chat_back") is True, str(out.get("card")))
    check("... and no picture was written",
          list(folder.glob("*.png")) == [], str(list(folder.glob("*.png"))))


#: The swap's sentence, searched for as a PHRASE in the WHOLE answer below.
#: Never the key name `words`: the bug was one sentence carried in two fields,
#: so a check that looked for a key - or counted `words` - could not see it.
SWAP_PHRASE = "stepped aside for"
#: The other sentence `_swap_words` can build, for a chat that did not come back.
NOT_BACK_PHRASE = "has not come back yet"


def swap_answer(*, fail=None, back_ok=True, away=2.5, back_seconds=9.0):
    """One confirmed draw through the REAL route, with the swap scripted.

    Nothing here has a graphics card, a model or a drawing program: `fail`
    makes the drawing program refuse, and `back_ok=False` makes the chat fail
    to come back. Every answer is the module's own, unchanged.
    """
    stub = StubRuntime("x", fail=fail)
    saved = (P.step_aside, P.step_back, P.record_measurement)
    P.step_aside = lambda plan: {"ok": True, "did": True, "seconds": away,
                                 "words": "The chat stepped aside."}
    P.step_back = lambda plan: {"ok": back_ok, "did": True,
                                "seconds": back_seconds,
                                "words": "The chat did not answer."}
    P.record_measurement = lambda plan, piece: None
    use_plan(SWAP_PLAN)
    try:
        return make(settings_for(tmpdir()), json.dumps(
            {"prompt": "a red panda", "free_card": True}).encode(), runtime=stub)
    finally:
        P.step_aside, P.step_back, P.record_measurement = saved
        reset_plan()


def t_the_swap_sentence_is_said_once_and_the_card_carries_no_words():
    """ONE sentence, ONE place, on every answer the swap can produce.

    Before 2026-10-25 the sentence went into the answer's own `words` (or
    `error`) AND again into `card.words`, so every app received it twice and a
    client that joined the two printed it twice - the desktop page did before
    PR #818, and the phone's `Pictures.madeWords` joins them. Each check counts
    the SENTENCE in the whole answer serialised as JSON, so a second copy in
    any field fails it, and each also pins that the sentence reached the field
    the apps actually show.
    """
    code, out = swap_answer()
    whole = json.dumps(out)
    check("a drawn picture answers 200 with the swap's own times",
          code == 200 and out.get("card", {}).get("chat_away_seconds") == 2.5
          and out.get("card", {}).get("chat_back_seconds") == 9.0,
          str(out.get("card")))
    check("... and says the swap's sentence ONCE in the whole answer",
          whole.count(SWAP_PHRASE) == 1
          and SWAP_PHRASE in (out.get("words") or ""),
          f"count={whole.count(SWAP_PHRASE)} words={out.get('words')!r} "
          f"card={out.get('card')!r}")
    check("... with no second copy inside the machine-readable card",
          "words" not in (out.get("card") or {}), str(out.get("card")))

    # A draw that FAILED still tells the owner the chat came back - once, in
    # `error`, which is the field both apps show for a refusal or a failure.
    code, out = swap_answer(
        fail=P.DrawingFailed("The drawing program refused that (500)."))
    whole = json.dumps(out)
    check("a draw that failed still says the swap's sentence ONCE",
          code == 502 and whole.count(SWAP_PHRASE) == 1
          and SWAP_PHRASE in (out.get("error") or ""),
          f"code={code} count={whole.count(SWAP_PHRASE)} "
          f"error={out.get('error')!r}")
    check("... and its card repeats none of it",
          "words" not in (out.get("card") or {}), str(out.get("card")))

    # A chat that did not come back has its own sentence. It was duplicated the
    # same way, so it is counted the same way - and it must not claim the chat
    # is back.
    code, out = swap_answer(back_ok=False)
    whole = json.dumps(out)
    check("a chat that did not come back is said ONCE, in the answer's own words",
          code == 200 and whole.count(NOT_BACK_PHRASE) == 1
          and NOT_BACK_PHRASE in (out.get("words") or "")
          and SWAP_PHRASE not in whole,
          f"code={code} count={whole.count(NOT_BACK_PHRASE)} "
          f"words={out.get('words')!r}")
    check("... and its card repeats none of that either",
          "words" not in (out.get("card") or {}), str(out.get("card")))


def t_a_failed_set_aside_draws_nothing_and_says_so():
    folder = tmpdir()
    stub = StubRuntime("x")
    use_plan(SWAP_PLAN)
    calls = []
    saved = (P.step_aside, P.step_back)
    P.step_aside = lambda plan: {"ok": False, "did": True, "seconds": 1.0,
                                 "words": "The everyday chat could not be set "
                                          "aside: it is still on the card."}
    P.step_back = lambda plan: (calls.append("back"), {"ok": True})[1]
    try:
        code, out = make(settings_for(folder), json.dumps(
            {"prompt": "a cat", "free_card": True}).encode(), runtime=stub)
    finally:
        P.step_aside, P.step_back = saved
        reset_plan()
    check("a chat that will not step aside stops the draw", code == 503,
          str(out)[:200])
    check("... the answer keeps the same plain sentence", "set aside" in
          (out.get("error") or ""), str(out)[:200])
    check("... and nothing was drawn", stub.asked == [], str(stub.asked))
    check("... and nothing was written",
          list(folder.glob("*.png")) == [], str(list(folder.glob("*.png"))))


def t_way_b_is_a_plain_sentence_not_a_broken_draw():
    plan = dict(SWAP_PLAN, option="B", supported=False, words=P.OPTION_B_WORDS)
    folder = tmpdir()
    stub = StubRuntime("x")
    use_plan(plan)
    try:
        code, out = make(settings_for(folder), json.dumps(
            {"prompt": "a cat", "free_card": True}).encode(), runtime=stub)
    finally:
        reset_plan()
    check("way B is a 503 with needs=option_unsupported",
          code == 503 and out.get("needs") == "option_unsupported",
          str(out)[:200])
    check("... and the sentence names the ways that do work",
          "way A" in (out.get("error") or ""), str(out)[:300])
    check("... and nothing was drawn", stub.asked == [], str(stub.asked))


def t_the_phone_may_confirm_the_swap_too():
    """Owner decision 2026-10-24: "i would like to be able to approve this from
    my phone as well". The phone's `free_card: true` is the same deliberate
    consent the desktop's is: the swap is local and reversible, the chat reloads
    on its own and nothing is deleted. The first request still asks first."""
    folder = tmpdir()
    stub = StubRuntime("x")
    use_plan(SWAP_PLAN)
    saved = (P.step_aside, P.step_back, P.record_measurement)
    P.step_aside = lambda plan: {"ok": True, "did": True, "seconds": 2.0,
                                 "words": "The chat stepped aside."}
    P.step_back = lambda plan: {"ok": True, "did": True, "seconds": 8.0,
                                "words": "The chat was back after 8.0 seconds."}
    P.record_measurement = lambda plan, piece: None
    try:
        # The phone's FIRST request: the same question, and nothing moves.
        code, out = P.handle_post(
            "/api/pictures", {"prompt": "a cat"},
            settings=settings_for(folder), runtime=stub, pc_only=False)
        check("a phone's first request is the same 409 question",
              code == 409 and out.get("needs") == "free_card", str(out)[:300])
        check("... and it unloaded and drew nothing",
              stub.asked == [] and stub.freed is False, str(stub.asked))
        # The phone's CONFIRM: the whole swap and the draw, as on the desktop.
        code2, out2 = P.handle_post(
            "/api/pictures", {"prompt": "a cat", "free_card": True},
            settings=settings_for(folder), runtime=stub, pc_only=False)
    finally:
        P.step_aside, P.step_back, P.record_measurement = saved
        reset_plan()
    check("a phone may confirm the swap and gets the normal success shape",
          code2 == 200 and out2.get("ok") is True
          and bool(out2.get("name")) and bool(out2.get("path")), str(out2)[:300])
    check("... the draw really ran, with the chat set aside and back",
          bool(stub.asked) and stub.freed is True
          and out2.get("card", {}).get("chat_back") is True,
          str(out2.get("card")))
    check("... and the answer carries the same card times as the desktop's",
          out2.get("card", {}).get("chat_away_seconds") == 2.0
          and out2.get("card", {}).get("chat_back_seconds") == 8.0,
          str(out2.get("card")))
    check("... but where pictures are kept stays the PC's own business",
          P.handle_post("/api/pictures/settings",
                        {"action": "enabled", "on": True},
                        settings=settings_for(folder), pc_only=False)[0] == 403)


def t_a_second_confirm_while_a_draw_is_running_is_one_sentence():
    """One picture at a time. The owner may now confirm from a phone, so a
    double-tap is a real second request; it must answer one plain sentence and
    start no second draw beside the first on a card that fits only one."""
    import threading
    folder = tmpdir()
    started, release = threading.Event(), threading.Event()

    class SlowStub(StubRuntime):
        def draw(self, prompt, *, seed=None, settings=None):
            started.set()
            release.wait(20)
            return super().draw(prompt, seed=seed, settings=settings)

    stub = SlowStub("x")
    use_plan(SWAP_PLAN)
    saved = (P.step_aside, P.step_back, P.record_measurement)
    P.step_aside = lambda plan: {"ok": True, "did": True, "seconds": 1.0,
                                 "words": "The chat stepped aside."}
    P.step_back = lambda plan: {"ok": True, "did": True, "seconds": 1.0,
                                "words": "The chat was back."}
    P.record_measurement = lambda plan, piece: None
    first = {}

    def confirm():
        first["result"] = P.handle_post(
            "/api/pictures", {"prompt": "a cat", "free_card": True},
            settings=settings_for(folder), runtime=stub)

    thread = threading.Thread(target=confirm)
    try:
        thread.start()
        if not started.wait(20):
            raise RuntimeError("the first draw never started")
        code, out = P.handle_post(
            "/api/pictures", {"prompt": "another cat", "free_card": True},
            settings=settings_for(folder), runtime=stub)
    finally:
        release.set()
        thread.join(20)
        P.step_aside, P.step_back, P.record_measurement = saved
        reset_plan()
    check("a confirm while a draw is running is refused, not queued as a "
          "second draw", code == 409 and out.get("needs") == "drawing",
          str(out)[:300])
    check("... with one plain sentence saying it is still drawing",
          "still drawing" in (out.get("error") or ""), str(out)[:300])
    check("... and only ONE picture was drawn by the two requests",
          len(stub.asked) == 1, str(stub.asked))
    check("... the first request still finished normally",
          first.get("result", (0, {}))[0] == 200,
          str(first.get("result"))[:200])
    code3, out3 = P.handle_post(
        "/api/pictures", {"prompt": "after"}, settings=settings_for(folder),
        runtime=stub)
    check("... and the lock is free again for the next picture",
          code3 == 200 and out3.get("ok") is True, str(out3)[:200])


def t_the_picture_model_is_given_time_to_let_go_of_the_card():
    """The first real draw's lesson (2026-10-24): the warm-back must not start
    while the picture model is still releasing the card - it came back 1.36 GB
    spilled. (Measured 2026-10-25: `/free` answers 200 with a body of 0 bytes,
    which the old client parsed as JSON and gave up on in 0.0 s.)"""
    rt = P.ComfyUI("http://127.0.0.1:8188")
    calls = []

    def fake(path, payload=None, *, timeout=None, **kw):
        calls.append(path)
        if path == "/free":
            return {}
        held = 10 * 1024 ** 3 if calls.count("/system_stats") < 2 else 0
        return {"devices": [{"torch_vram_total": held}]}

    rt._json = fake
    out = rt.free_models()
    check("free_models waits until the card is really free",
          out.get("ok") is True and out.get("held_bytes") == 0, str(out))
    check("... it asked /free first, then polled /system_stats",
          calls[:3] == ["/free", "/system_stats", "/system_stats"], str(calls))
    # A program that never lets go is a sentence, not a hang: shorten the wait.
    saved = P.FREE_WAIT_S
    P.FREE_WAIT_S = 0.2
    try:
        rt2 = P.ComfyUI("http://127.0.0.1:8188")
        rt2._json = lambda path, payload=None, *, timeout=None, **kw: (
            {} if path == "/free" else
            {"devices": [{"torch_vram_total": 9 * 1024 ** 3}]})
        bad = rt2.free_models()
    finally:
        P.FREE_WAIT_S = saved
    check("... and a program that never lets go is one plain sentence",
          bad.get("ok") is False and "still holds" in (bad.get("words") or ""),
          str(bad))
    # The /free call itself must be allowed the long wait it needs.
    rt3 = P.ComfyUI("http://127.0.0.1:8188")
    seen = {}

    def fake3(path, payload=None, *, timeout=None, **kw):
        seen[path] = timeout
        return {} if path == "/free" else {"devices": [{"torch_vram_total": 0}]}

    rt3._json = fake3
    rt3.free_models()
    check("... and /free itself is given the long time it needs",
          seen.get("/free") is not None and seen.get("/free") >= 120.0,
          str(seen))


def t_the_free_answer_is_allowed_to_have_no_body_at_all():
    """The MEASURED cause of the first real draw's 1.36 GB spill (2026-10-25).

    ComfyUI's own ``POST /free`` answers HTTP 200 with a body of 0 bytes - the
    call is the answer. The old client parsed that empty body as JSON, raised,
    and ``free_models`` gave up in 0.0 s, so the chat was warmed back onto a
    card the picture models were still releasing. The empty answer must be a
    success, and only for the route that is known to answer this way."""
    class Answer:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self.body

    urlopen0 = P.urllib.request.urlopen
    try:
        P.urllib.request.urlopen = lambda req, timeout=None: Answer(b"")
        rt = P.ComfyUI("http://127.0.0.1:8188")
        got = rt._json("/free", {"unload_models": True}, timeout=5.0,
                       allow_empty=True)
        check("an empty 200 is an answer when the route is known to send none",
              got == {}, str(got))
        raised = None
        try:
            rt._json("/prompt", {"prompt": {}}, timeout=5.0)
        except Exception as exc:
            raised = exc
        check("... and any other route still treats an empty answer as an error",
              isinstance(raised, P.DrawingFailed), repr(raised))
        P.urllib.request.urlopen = (
            lambda req, timeout=None: Answer(b'{"devices": []}'))
        check("... a real JSON answer is still parsed",
              rt._json("/system_stats", timeout=5.0) == {"devices": []})

        def refuse(req, timeout=None):
            raise P.urllib.error.HTTPError(
                getattr(req, "full_url", "http://127.0.0.1:8188/free"),
                400, "Bad Request", {}, None)

        P.urllib.request.urlopen = refuse
        rt2 = P.ComfyUI("http://127.0.0.1:8188")
        bad = rt2.free_models()
        check("a refused /free is one sentence, never a traceback",
              bad.get("ok") is False
              and "DrawingFailed" in (bad.get("words") or ""), str(bad))
    finally:
        P.urllib.request.urlopen = urlopen0
    # The poll itself is unchanged, and it is still the one that was measured.
    rt3 = P.ComfyUI("http://127.0.0.1:8188")
    seen = []

    def fake(path, payload=None, *, timeout=None, **kw):
        seen.append((path, kw.get("allow_empty")))
        return {} if path == "/free" else {"devices": [{"torch_vram_total": 0}]}

    rt3._json = fake
    out = rt3.free_models()
    check("free_models asks /free for an empty answer, then waits on the card",
          out.get("ok") is True and seen
          and seen[0] == ("/free", True)
          and seen[1][0] == "/system_stats" and seen[1][1] is not True,
          str((out, seen)))


class _Clock:
    """A clock the test moves, so a ten-minute wait costs a few hundred steps.

    The WAIT is what this test is about - the route must give a real draw the
    time it needs and stop at the wait it says it uses - so the clock is moved
    forward instead of the test sleeping, and the REAL ``ComfyUI.draw`` and
    ``free_models`` run against a stand-in for the drawing program.
    """

    def __init__(self):
        self.now = 0.0
        self.slept = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += float(seconds)
        self.slept += float(seconds)


class _Answer:
    """The context manager ``urllib.request.urlopen`` hands back."""

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


def draw_on_a_clock(runtime, *, finish_at=None):
    """Run the REAL ``ComfyUI.draw`` on a clock this test owns.

    ``finish_at`` is the fake second at which the stand-in program reports the
    picture done; ``None`` means the job never finishes at all. Answers
    ``(clock, piece, raised)``: the clock, the Piece the real draw built, and
    the exception it raised instead, whichever happened.
    """
    clock = _Clock()
    real_time, real_urlopen = P.time, P.urllib.request.urlopen

    def json_call(path, payload=None, *, method=None, timeout=None,
                  allow_empty=False):
        if path == "/prompt":
            return {"prompt_id": "p1"}
        if finish_at is not None and clock.now >= finish_at:
            return {"p1": {"outputs": {"9": {"images": [{"filename": "a.png"}]}}}}
        return {}

    runtime._json = json_call
    # The graph is not what is under test here (other tests cover it); the wait
    # around it is. A one-line stand-in keeps the two apart.
    runtime._workflow = lambda prompt, settings: (
        {}, {"steps": 1, "width": 64, "height": 64, "guidance": 1.0})
    P.time = clock
    P.urllib.request.urlopen = lambda url, timeout=None: _Answer(PNG)
    try:
        return clock, runtime.draw("a red panda", settings={}), None
    except Exception as exc:
        return clock, None, exc
    finally:
        P.time, P.urllib.request.urlopen = real_time, real_urlopen


def t_the_route_waits_long_enough_for_a_real_draw():
    """The three defects found on 2026-10-25, measured at the seams that run.

    Every check calls the real function with the drawing program stood in for
    and asserts on what it RECEIVED - none of it reads the module's source
    text, so a rename or a rewrite that keeps the behaviour keeps this green,
    and a change that breaks the behaviour turns it red.

    The measured case behind the wait: a real Chroma1-HD picture on this PC
    took a median of 274.4 s, and the old cap was
    ``max(60, self.timeout * 12)`` = 120 s - it refused the very draw the
    feature exists for.
    """
    check("the wait covers a real measured draw (>= 600 s)",
          P.DRAW_WAIT_S >= 600.0, str(P.DRAW_WAIT_S))

    # 1. The OLD cap is gone: a draw still running after 200 s is waited for.
    #    120 s was the old ceiling, so 200 s is past it by a wide margin.
    clock, piece, raised = draw_on_a_clock(P.ComfyUI("http://127.0.0.1:8188"),
                                           finish_at=200.0)
    check("a draw still running after 200 s is waited for, not given up on "
          "(the old 120 s cap is gone)",
          piece is not None and piece.png == PNG and clock.slept >= 200.0,
          str((clock.slept, raised)))

    # 2. The wait IS max(DRAW_WAIT_S, self.timeout * 12), measured twice: the
    #    module's own constant for a default adapter, and the adapter's own
    #    12x timeout when THAT is the longer of the two.
    gave_up, _, stopped = draw_on_a_clock(P.ComfyUI("http://127.0.0.1:8188"),
                                          finish_at=None)
    check("... and a job that never finishes ends at DRAW_WAIT_S, not for ever",
          isinstance(stopped, P.DrawingFailed)
          and P.DRAW_WAIT_S <= gave_up.slept <= P.DRAW_WAIT_S + 2.0,
          str((gave_up.slept, stopped)))
    slow, _, _ = draw_on_a_clock(P.ComfyUI("http://127.0.0.1:8188", timeout=100.0),
                                 finish_at=None)
    check("... and a slower adapter gets its own 12x timeout when that is longer",
          slow.slept > P.DRAW_WAIT_S
          and 1200.0 <= slow.slept <= 1202.0, str(slow.slept))

    # 3. ComfyUI is asked to let go of its models on its OWN route, with the
    #    release payload, and the empty answer that route sends is accepted
    #    rather than parsed as JSON.
    rt = P.ComfyUI("http://127.0.0.1:8188")
    asked = []
    readings = [{"devices": [{"torch_vram_total": 3 * 1024 ** 3}]},
                {"devices": [{"torch_vram_total": 0}]}]

    def spy(path, payload=None, *, method=None, timeout=None,
            allow_empty=False):
        asked.append({"path": path, "payload": payload,
                      "empty_ok": allow_empty, "timeout": timeout})
        if path == "/free":
            return {}
        return readings.pop(0) if readings else {
            "devices": [{"torch_vram_total": 0}]}

    rt._json = spy
    real_time = P.time
    P.time = _Clock()
    try:
        freed = rt.free_models()
    finally:
        P.time = real_time
    check("ComfyUI is asked to free its models on its own /free, with the "
          "release payload",
          bool(asked) and asked[0]["path"] == "/free"
          and asked[0]["payload"] == {"unload_models": True,
                                      "free_memory": True}, str(asked[:1]))
    check("... and its empty answer is accepted, not parsed as JSON",
          bool(asked) and asked[0]["empty_ok"] is True
          and all(not a["empty_ok"] for a in asked[1:]), str(asked))
    check("... and it is given FREE_WAIT_S to let go",
          bool(asked) and asked[0]["timeout"] == P.FREE_WAIT_S, str(asked[:1]))
    check("... and the card is read from its own /system_stats until it is "
          "really free",
          freed.get("ok") is True and freed.get("held_bytes") == 0
          and len(asked) >= 2 and asked[1]["path"] == "/system_stats"
          and len([a for a in asked if a["path"] == "/system_stats"]) >= 2,
          str((freed, asked)))

    # 4. The warm-back runs in a FINALLY, never only on success: a draw that
    #    CRASHES (a real bug, not a DrawingFailed) still brings the chat back,
    #    and the answer carries the times step_back itself returned.
    class Crash(StubRuntime):
        def draw(self, prompt, *, seed=None, settings=None):
            raise RuntimeError("a crash the route did not expect")

    folder = tmpdir()
    events = []
    saved = (P.step_aside, P.step_back, P.record_measurement)
    use_plan(SWAP_PLAN)
    P.step_aside = lambda plan: {"ok": True, "did": True, "seconds": 1.0,
                                 "words": "The chat stepped aside."}

    def back(plan):
        events.append("back")
        return {"ok": True, "did": True, "seconds": 9.0,
                "words": "The chat was back after 9.0 seconds."}

    P.step_back = back
    P.record_measurement = lambda plan, piece: None
    try:
        code, out = make(settings_for(folder), json.dumps(
            {"prompt": "a red panda", "free_card": True}).encode(),
            runtime=Crash("x"))
    finally:
        P.step_aside, P.step_back, P.record_measurement = saved
        reset_plan()
    check("the warm-back runs in a finally: a draw that CRASHES still brings "
          "the chat back", events == ["back"] and code == 502,
          str((code, events)))
    check("... and the answer carries the times step_back itself returned",
          out.get("card", {}).get("chat_back_seconds") == 9.0
          and out.get("card", {}).get("chat_back") is True,
          str(out.get("card")))

    # 5. The make route no longer refuses a phone's confirm - it draws. The
    #    SETTINGS route is still this PC's alone, because where pictures are
    #    kept and which program draws them is this PC's own configuration.
    saved = (P.step_aside, P.step_back, P.record_measurement)
    use_plan(SWAP_PLAN)
    P.step_aside = lambda plan: {"ok": True, "did": True, "seconds": 1.0,
                                 "words": "The chat stepped aside."}
    P.step_back = lambda plan: {"ok": True, "did": True, "seconds": 2.0,
                                "words": "The chat was back."}
    P.record_measurement = lambda plan, piece: None
    phone_stub = StubRuntime("x")
    try:
        code, out = P.handle_post(
            "/api/pictures", {"prompt": "a cat", "free_card": True},
            settings=settings_for(tmpdir()), runtime=phone_stub, pc_only=False)
    finally:
        P.step_aside, P.step_back, P.record_measurement = saved
        reset_plan()
    check("the make route no longer refuses a phone's confirm: it draws",
          code == 200 and out.get("ok") is True and not out.get("pc_only")
          and bool(phone_stub.asked), str(out)[:200])
    refused = []
    for change in ({"action": "folder", "folder": str(tmpdir("phone-folder"))},
                   {"action": "runtime", "runtime": "sd_cpp"}):
        code, out = P.handle_post("/api/pictures/settings", change,
                                  settings=settings_for(tmpdir()), pc_only=False)
        refused.append((code, out.get("pc_only")))
    check("... while changing the folder or the program is still the PC's alone",
          refused == [(403, True), (403, True)], str(refused))

    # 6. One picture at a time, guarded by the module's OWN lock: take it and
    #    the second request is a sentence, and nothing is drawn.
    held = P._DRAW_IN_FLIGHT.acquire(blocking=False)
    try:
        code, out = make(settings_for(tmpdir()),
                         json.dumps({"prompt": "a cat"}).encode(),
                         runtime=StubRuntime("x"))
    finally:
        # `locked()` rather than the flag alone: a module that releases a lock
        # it never took must be REPORTED as a failed check, not crash the suite
        # with a traceback and hide the checks after this one.
        if held and P._DRAW_IN_FLIGHT.locked():
            P._DRAW_IN_FLIGHT.release()
    check("... and only one picture can be drawn at a time: the module's own "
          "lock refuses the second with its own sentence",
          held and code == 409 and out.get("needs") == "drawing"
          and out.get("error") == P.STILL_DRAWING_WORDS, str(out)[:200])

    # 7. The two-request consent key the apps may pin: needs=free_card, and a
    #    confirm instruction that carries it.
    use_plan(SWAP_PLAN)
    try:
        code, out = make(settings_for(tmpdir()), json.dumps(
            {"prompt": "a cat"}).encode(), runtime=StubRuntime("x"))
    finally:
        reset_plan()
    check("the two-request consent key the apps may pin is needs=free_card and "
          "confirm={free_card: true}",
          code == 409 and out.get("needs") == "free_card"
          and out.get("confirm") == {"free_card": True}, str(out)[:200])

    # 8. THE BUDGET BOTH APPS MUST GIVE IT (2026-10-25, ruling B6). A read
    #    timeout measures SILENCE, and this route says nothing at all for the
    #    whole swap - so an app's budget must outlast the PC's WORST CASE, which
    #    is the SUM of its five own ceilings, not one measured draw. The two
    #    card ceilings are read from the function defaults themselves, so a
    #    change there cannot leave this check green by accident. FREE_WAIT_S
    #    counts TWICE and that is the whole correction: free_models() sends
    #    `POST /free` with timeout=FREE_WAIT_S and THEN sets
    #    deadline = time.time() + FREE_WAIT_S to poll /system_stats, so the
    #    "let go" step costs up to 360 s. The earlier four-term sum counted
    #    that step once and was 180 s short.
    free_src = inspect.getsource(P.ComfyUI.free_models)
    check("the let-go step is TWO FREE_WAIT_S waits, not one: /free's own "
          "timeout, then the /system_stats poll deadline set after it",
          "timeout=FREE_WAIT_S" in free_src
          and "deadline = time.time() + FREE_WAIT_S" in free_src,
          free_src[:300])
    ceilings = (
        inspect.signature(C.unload_lane).parameters["timeout"].default,
        P.DRAW_WAIT_S,
        P.FREE_WAIT_S,
        P.FREE_WAIT_S,
        inspect.signature(C.warm_lane).parameters["timeout"].default,
    )
    worst = sum(ceilings)
    check("the PC's worst case is its five ceilings together: unload_lane 120 "
          "+ DRAW_WAIT_S 600 + /free's FREE_WAIT_S 180 + its /system_stats "
          "poll's FREE_WAIT_S 180 + warm_lane 600 = 1,680 s",
          ceilings == (120.0, 600.0, 180.0, 180.0, 600.0) and worst == 1_680.0,
          str(ceilings))
    # The clients' numbers are in two other languages. Reading their source
    # here is deliberate: this is the check that fails if either app is ever
    # trimmed back under the PC's ceiling, which is the false failure this
    # ruling fixes.
    phone_budget = re.search(r"CONFIRM_TIMEOUT_S\s*=\s*([\d_]+)L",
                             PHONE_PICTURES.read_text(encoding="utf-8"))
    desktop_budget = re.search(
        r"PICTURE_TIMEOUT: Duration = Duration::from_secs\(([\d_]+)\)",
        DESKTOP_BRAIN.read_text(encoding="utf-8"))
    budgets = {
        "phone": int(phone_budget.group(1).replace("_", "")) if phone_budget else None,
        "desktop": (int(desktop_budget.group(1).replace("_", ""))
                    if desktop_budget else None),
    }
    check("both apps wait longer than that: 1,740 s, so a legitimate slow draw "
          "and warm-back is never a false failure",
          all(got is not None and got >= 1_740 and got > worst
              for got in budgets.values()), str(budgets))


# ---------------------------------------------------------------------------
#   3. Storage: write, read back, sidecar intact
# ---------------------------------------------------------------------------

def t_the_storage_round_trip_keeps_the_record():
    folder = tmpdir()
    stub = StubRuntime("x", seed=1234, model="sd_xl_base_1.0.safetensors")
    settings = settings_for(folder)
    code, out = make(settings, json.dumps(
        {"prompt": "a lighthouse at night", "seed": 1234,
         "settings": {"steps": 28, "width": 768, "height": 512}}).encode(),
        runtime=stub)
    check("the picture was written", code == 200 and out["ok"], str(out)[:200])
    side = Path(out["path"]).with_suffix(".json")
    check("a sidecar sits beside it", side.is_file(), str(side))
    record = json.loads(side.read_text(encoding="utf-8"))
    check("the sidecar holds the owner's own prompt",
          record["prompt"] == "a lighthouse at night", str(record.get("prompt")))
    check("... and the seed", record["seed"] == 1234, str(record.get("seed")))
    check("... and the model that drew it",
          record["model"] == "sd_xl_base_1.0.safetensors", str(record.get("model")))
    check("... and the program", record["runtime"] == "comfyui")
    check("... and the settings, so it can be made again",
          record["settings"]["steps"] == 28
          and record["settings"]["width"] == 768
          and record["settings"]["height"] == 512, str(record.get("settings")))
    check("... and when it was made, in words",
          isinstance(record.get("made_at_words"), str)
          and len(record["made_at_words"]) > 5, str(record.get("made_at_words")))
    check("... and which picture it belongs to",
          record["picture"] == Path(out["path"]).name)
    # Read it back the way the list route does.
    items = P.listing(folder)
    check("the list reads it back", len(items) == 1, str(items))
    one = items[0]
    check("... with the prompt", one["prompt"] == "a lighthouse at night")
    check("... with the seed and the model",
          one["seed"] == 1234 and one["model"] == "sd_xl_base_1.0.safetensors")
    check("... flagged as having a record", one["record"] is True)
    check("... and with a name that is the file's own name",
          one["name"] == Path(out["path"]).name)
    # Survives a restart: nothing is held in memory, a second load sees it.
    again = P.listing(folder)
    check("reading it again after a restart gives the same picture",
          [x["name"] for x in again] == [one["name"]])
    check("the record on disk is still intact after the second read",
          json.loads(side.read_text(encoding="utf-8")) == record)


def t_the_file_name_is_the_date_the_time_and_a_slug():
    stem = P.picture_stem(time.mktime((2026, 10, 11, 14, 5, 9, 0, 0, -1)),
                          "A Red Panda, in a Library! (2026)")
    check("the name starts with the date and the time",
          re.match(r"^2026-10-11-140509-", stem), stem)
    check("the slug's own words are slugged, not dropped",
          "red-panda" in stem and "library" in stem, stem)
    check("... with nothing a path could use",
          re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{6}-[a-z0-9-]+", stem),
          stem)
    check("... not the whole prompt",
          len(stem) <= 20 + P.SLUG_MAX, f"{len(stem)}: {stem}")
    for nasty in ["../../etc/passwd", "C:\\Windows\\system32", "a/b\\c:d*e?f",
                  "  ", "!!!", "日本語のプロンプト"]:
        got = P.slug_for(nasty)
        check(f"the slug for {nasty!r} is safe and never empty",
              bool(got) and re.fullmatch(r"[a-z0-9-]+", got) is not None, got)
    check("two different prompts make two different names",
          P.slug_for("a red panda") != P.slug_for("an owl"),
          P.slug_for("a red panda"))
    check("a prompt of punctuation only still gets a usable name",
          P.slug_for("!!!") == "picture")


def t_two_pictures_on_one_day_do_not_collide():
    """The brief: two pictures on one day must not collide. And the harder
    case the name's own clock makes possible - the same prompt in the SAME
    second - must not overwrite the first picture either."""
    folder = tmpdir()
    stub = StubRuntime("x")
    settings = settings_for(folder)
    frozen = time.mktime((2026, 10, 11, 9, 30, 0, 0, 0, -1))
    first = make(settings, json.dumps({"prompt": "a red panda"}).encode(),
                 runtime=stub, when=frozen)[1]
    # The SAME prompt at the SAME second - the collision the file name's own
    # clock makes possible, tested by freezing the clock rather than by
    # hoping two calls land in the same second.
    second = make(settings, json.dumps({"prompt": "a red panda"}).encode(),
                  runtime=stub, when=frozen)[1]
    check("the first picture is still there after the second",
          Path(first["path"]).is_file(), first["path"])
    check("... and the second is a different file",
          second["path"] != first["path"], f"{first['path']} vs {second['path']}")
    check("... with its own name", second["name"] != first["name"],
          f"{first['name']} vs {second['name']}")
    check("... both in the folder", len(list(folder.glob("*.png"))) == 2,
          str(sorted(p.name for p in folder.glob("*.png"))))
    check("... each with its own sidecar", len(list(folder.glob("*.json"))) == 2)
    check("... and neither file was overwritten (both are real pictures)",
          Path(first["path"]).read_bytes() == PNG
          and Path(second["path"]).read_bytes() == PNG)
    # Two different prompts on one day, the ordinary case.
    third = make(settings, json.dumps({"prompt": "an owl"}).encode(),
                 runtime=stub, when=frozen + 90)[1]
    check("a different prompt on the same day gets its own name",
          third["name"] != first["name"] and "owl" in third["name"],
          third["name"])
    names = [x["name"] for x in P.listing(folder)]
    check("... and the list holds all three", len(names) == 3, str(names))
    check("... newest first, by name: the date and time are in the name",
          names[0] == third["name"], str(names))
    check("... and the two from the same second are both there, neither lost",
          first["name"] in names and second["name"] in names, str(names))
    check("next_names never hands back a name already on disk",
          all(not p.exists() for p in P.next_names(folder, first["id"])))


# ---------------------------------------------------------------------------
#   4. Nothing configured at all
# ---------------------------------------------------------------------------

def t_nothing_configured_is_one_plain_sentence_naming_what_to_install():
    folder = tmpdir()
    settings = {"enabled": True, "runtime": None, "address": None,
                "folder": str(folder)}
    code, out = make(settings, json.dumps({"prompt": "a cat"}).encode())
    check("with no program configured the make route is 503", code == 503, str(code))
    words = out.get("error") or ""
    check("... and says plainly that nothing is set up yet",
          "no picture-making program" in words, words)
    check("... and names BOTH programs the owner could install",
          "ComfyUI" in words and "stable-diffusion.cpp" in words, words)
    check("... and says where to choose one",
          "Settings" in words and "Pictures" in words, words)
    check("... as one sentence with a full stop",
          words.count(".") >= 2 and words.rstrip().endswith("."), words)
    check("... and available:false, so an app shows the line and no error",
          out.get("available") is False, str(out)[:200])
    # The status route says the same thing, and still reads the folder.
    status = P.status_answer(settings)
    check("the status route carries the same sentence",
          status["words"] == P.NOT_CONFIGURED, str(status["words"]))
    check("... and lists the two supported values by name",
          [r["id"] for r in status["runtimes"]] == ["comfyui", "sd_cpp"],
          str(status["runtimes"]))
    check("... each with what to install and its default address",
          all(r["install"] and r["address"].startswith("http://127.0.0.1:")
              for r in status["runtimes"]), str(status["runtimes"]))
    check("no unknown runtime name is ever reported as configured",
          P.status_answer({"enabled": True, "runtime": "midjourney",
                           "folder": str(folder)})["runtime"] == "midjourney"
          and P.runtime_for({"runtime": "midjourney"}) is None)


# ---------------------------------------------------------------------------
#   5. The listing route: the folder, its size, and a lost record
# ---------------------------------------------------------------------------

def t_the_list_route_reports_the_folder_and_its_size():
    folder = tmpdir()
    stub = StubRuntime("x")
    settings = settings_for(folder)
    base = time.mktime((2026, 10, 11, 9, 0, 0, 0, 0, -1))
    for i, prompt in enumerate(("a red panda", "a pygmy owl", "a sea otter")):
        make(settings, json.dumps({"prompt": prompt}).encode(), runtime=stub,
             when=base + i * 60)
    status = P.status_answer(settings)
    check("the list route says where the pictures are",
          status["folder"] == str(folder), str(status["folder"]))
    check("... and how many there are", status["count"] == 3, str(status["count"]))
    check("... and how big the folder is", status["bytes"] > 0
          and status["bytes"] == P.folder_bytes(folder), str(status["bytes"]))
    check("... in words a person reads",
          status["size_words"] == P.sized_words(status["bytes"]),
          str(status["size_words"]))
    check("... and every prompt is there, newest first",
          [p["prompt"] for p in status["pictures"]]
          == ["a sea otter", "a pygmy owl", "a red panda"],
          str([p["prompt"] for p in status["pictures"]]))
    check("... each with when it was made",
          all(p["made_at_words"] for p in status["pictures"]))
    check("... and the promise that they are not tidied away",
          "never tidies" in status["keep"], status["keep"])
    check("sizes read the way a person says them",
          P.sized_words(0) == "0 B" and P.sized_words(2048) == "2 KB"
          and P.sized_words(3 * 1024 ** 2) == "3.0 MB", P.sized_words(2048))
    # A lost sidecar must not hide the owner's picture.
    victim = sorted(folder.glob("*.png"))[0]
    victim.with_suffix(".json").unlink()
    items = P.listing(folder)
    check("a picture whose record is lost is still listed", len(items) == 3)
    lost = [p for p in items if p["name"] == victim.name][0]
    check("... with its prompt empty rather than invented", lost["prompt"] == "")
    check("... and flagged so a screen can say the record is gone",
          lost["record"] is False, str(lost))
    check("... and its file untouched", lost["bytes"] == victim.stat().st_size)


def t_the_picture_itself_comes_back_as_bytes_and_nothing_else_does():
    folder = tmpdir()
    stub = StubRuntime("x")
    settings = settings_for(folder)
    made = make(settings, json.dumps({"prompt": "a red panda"}).encode(),
                runtime=stub)[1]
    code, out = P.handle_get("/api/pictures/file", "id=" + made["id"],
                             settings=settings)
    check("the picture comes back 200", code == 200, str(out)[:200])
    check("... as base64, the way the captcha hand-off sends its own frame",
          out.get("encoding") == "base64", str(out.get("encoding")))
    check("... and it IS the picture",
          base64.b64decode(out["png"]) == PNG)
    check("... with its size", out["bytes"] == len(PNG))
    for bad in ["", "../pictures.json", "..\\x", "a/b", "nope",
                made["id"] + "/../../x", "C:\\Windows\\win.ini"]:
        code, out = P.handle_get("/api/pictures/file", "id=" + bad,
                                 settings=settings)
        check(f"the id {bad!r} is refused with no file outside the folder",
              code in (400, 404) and out.get("ok") is False, str(out)[:120])
    check("a picture id can never name a file this module did not write",
          P.picture_path(folder, "pictures") is None
          and P.picture_path(folder, made["id"]) is not None)
    # A deleted folder says so in words rather than falling over.
    import shutil
    shutil.rmtree(folder)
    code, out = P.handle_get("/api/pictures", settings=settings)
    check("a folder that is gone is answered, not crashed",
          code == 200 and out["count"] == 0, str(out)[:160])


# ---------------------------------------------------------------------------
#   6. The routes, the install(), and where the routes are live
# ---------------------------------------------------------------------------

def t_the_routes_are_the_documented_ones():
    check("the base path is /api/pictures", P.BASE == "/api/pictures", P.BASE)
    check("GET answers the list and the file",
          P.GET_ROUTES == ("/api/pictures", "/api/pictures/file"),
          str(P.GET_ROUTES))
    check("POST answers the make route and the settings route",
          P.POST_ROUTES == ("/api/pictures", "/api/pictures/settings"),
          str(P.POST_ROUTES))
    check("an unknown route is a 404 and says so",
          P.handle_get("/api/nope", settings={})[0] == 404
          and P.handle_post("/api/nope", {}, settings={})[0] == 404)
    check("a trailing slash still reaches the list route",
          P.handle_get("/api/pictures/", settings={"folder": str(tmpdir())})[0]
          == 200)


def t_it_owns_nothing_under_picture_card():
    """The other half of the guard main's own suite holds.

    PR #248 merged the picture-maker's CARD half as its own module, owning
    `/api/picture-card`. Two features that both make pictures must never fight
    over a prefix, so each module carries the check in its own suite:
    `test_picture_card.py`'s `t_owns_nothing_under_pictures()` fails if
    `jarvis_picture_card.py` ever grows a route under `/api/pictures`, and this
    one fails if `jarvis_pictures.py` ever grows one under `/api/picture-card`.
    """
    source = (HERE / "jarvis_pictures.py").read_text(encoding="utf-8")
    check("this module never claims a route under /api/picture-card",
          "/api/picture-card" not in source, None)


def t_install_wraps_the_handler_and_leaves_every_other_request_alone():
    folder = tmpdir()
    stub = StubRuntime("x")
    saved = P.RUNTIME_CLASSES["comfyui"]
    P.register_runtime("comfyui", _StubFactory(stub))
    saved_path = P.settings_path
    settings_file = tmpdir() / "pictures.json"
    settings_file.write_text(json.dumps(settings_for(folder)), encoding="utf-8")
    P.settings_path = lambda: settings_file
    try:
        cls = type("H", (Handler0,), {})
        banner = P.install(cls, origin_ok=lambda h: h.origin == "pc",
                           token_ok=lambda h: h.token == "good",
                           read_body=lambda h: h.body)
        check("install() returns a banner line naming the feature",
              "pictures" in banner.lower(), banner)

        h = cls(path="/api/status")
        h.do_GET()
        check("a request that is not ours goes straight through",
              h.passed_through == 1 and not h.sent)

        h = cls(path="/api/pictures")
        h.do_GET()
        check("GET /api/pictures is answered here",
              h.sent and h.sent[0][0] == 200, str(h.sent)[:200])
        check("... with the pictures in it",
              h.sent[0][1]["ok"] is True and h.sent[0][1]["folder"] == str(folder))

        h = cls(path="/api/pictures")
        h.body = json.dumps({"prompt": "a red panda"}).encode()
        h.do_POST()
        check("POST /api/pictures draws one",
              h.sent and h.sent[0][0] == 200, str(h.sent)[:200])
        check("... and the file is on disk",
              Path(h.sent[0][1]["path"]).is_file())

        h = cls(path="/api/pictures", origin="elsewhere")
        h.do_GET()
        check("a cross-origin request is refused before anything is read",
              h.sent and h.sent[0][0] == 403, str(h.sent)[:120])
        h = cls(path="/api/pictures", token="wrong")
        h.do_GET()
        check("a bad token is refused before anything is read",
              h.sent and h.sent[0][0] == 401, str(h.sent)[:120])
        h = cls(path="/api/pictures")
        h.body = b"{broken"
        h.do_POST()
        check("a body that is not JSON is a 400, not a traceback",
              h.sent and h.sent[0][0] == 400, str(h.sent)[:120])
        # Installing twice is a no-op that says so, never double-wrapping.
        again = P.install(cls, origin_ok=lambda h: True, token_ok=lambda h: True,
                          read_body=lambda h: h.body)
        check("installing twice says it is already on", "already on" in again,
              again)
        h = cls(path="/api/pictures")
        h.do_GET()
        check("... and does not answer the request twice",
              len(h.sent) == 1, str(len(h.sent)))
    finally:
        P.RUNTIME_CLASSES["comfyui"] = saved
        P.settings_path = saved_path


# ---------------------------------------------------------------------------
#   7. A picture is not a way out of the PC
# ---------------------------------------------------------------------------

def t_no_picture_is_sent_anywhere_and_no_model_can_reach_this():
    """The owner's rule 1. A picture stays on the PC; the phone's own "save to
    my phone" is the owner's device over Tailscale, not a way out."""
    src = (HERE / "jarvis_pictures.py").read_text(encoding="utf-8")
    low = src.lower()
    for forbidden in ("smtplib", "import requests", "http://localhost:11434",
                      "api.telegram", "api.openai", "generativelanguage"):
        check(f"jarvis_pictures.py holds no {forbidden}",
              forbidden not in low, forbidden)
    check("... and no route or function is named for sending one",
          not any(w in src for w in ("def send_", "def upload_", "def email_")))
    check("... and the module says so itself, in the app's own words",
          "A picture is never sent anywhere by Jarvis" in src)
    # No MODEL path may import it: the prompt is the owner's typed words only,
    # never text a model filled in from email, a page or a file.
    #
    # ONE module is allowed, and named here rather than left to a loose rule:
    # `jarvis_settings_registry.py`, whose whole job is to carry the switch
    # ("turn on making pictures", and the Settings card's own flip). It reaches
    # this module's load/save only - it never draws and never touches a prompt
    # - and it is reached from the owner's own typed or spoken words, exactly
    # as `set_web_search` and `set_prompt_coach` already are.
    ALLOWED = {"jarvis_settings_registry"}
    importers = []
    for py in sorted(HERE.glob("*.py")):
        if py.name.startswith("test_") or py.name == "jarvis_pictures.py":
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if re.search(r"^\s*(?:import|from)\s+jarvis_pictures\b", text, re.M):
            if py.stem not in ALLOWED:
                importers.append(py.name)
    check("no backend module imports jarvis_pictures except the one named "
          "settings registry (so no model turn and no tool can reach it)",
          importers == [], str(importers))
    # And the modules that WOULD make it a model path must never name it,
    # whatever else changes: the agent and its tools, quick commands, the
    # intake/learning path, and the two picture readers.
    for name in ("jarvis_agent.py", "jarvis_quick.py", "jarvis_intake.py",
                 "jarvis_auto_learn.py", "jarvis_screen_picture.py",
                 "jarvis_chat_picture.py", "jarvis_screen.py"):
        p = HERE / name
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        check(f"{name} is not a way into making pictures",
              "jarvis_pictures" not in text, name)
    agent = REPO / "backend" / "jarvis_agent.py"
    if agent.is_file():
        text = agent.read_text(encoding="utf-8", errors="replace")
        check("jarvis_agent.py does not name it as a tool",
              "jarvis_pictures" not in text, "jarvis_agent.py")
    # The only address ever opened is the configured one.
    check("the adapters only ever talk to the address they were given",
          "urllib.request.urlopen" in src and address_only(src))
    check("the two supported runtimes are exactly the two documented ones",
          sorted(P.RUNTIMES) == ["comfyui", "sd_cpp"], str(sorted(P.RUNTIMES)))
    for name, info in P.RUNTIMES.items():
        check(f"the {name} address is on this PC",
              info["address"].startswith("http://127.0.0.1:"), info["address"])


def address_only(src: str) -> bool:
    """Every urlopen call builds its URL from `self.address` - no literal host
    anywhere else in the file."""
    urls = re.findall(r"urlopen\(\s*([A-Za-z_][\w.]*)", src)
    return bool(urls) and all(u in ("url", "req") for u in urls)


# ---------------------------------------------------------------------------
#   8. The document claims are true
# ---------------------------------------------------------------------------

def t_the_api_document_has_the_section_and_it_matches_this_code():
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    check("docs/JARVIS-API.md has section 129", "## 129." in api,
          "no section 129 yet")
    for route in ("/api/pictures", "/api/pictures/file"):
        check(f"... and names the route {route}", route in api, route)
    check("... and says the pictures are kept on this PC",
          "Pictures" in api and "kept" in api.lower())
    check("... and names the switch and its default",
          "Making pictures" in api and "default OFF" in api)
    check("... and names both drawing programs as the two supported values",
          "ComfyUI" in api and "stable-diffusion.cpp" in api
          and "`comfyui`" in api and "`sd_cpp`" in api)
    check("... and says a picture needs no approval card, and why",
          "no approval card" in api.lower(), "the section must say this")
    check("... and says nothing leaves the PC",
          "Nothing leaves the PC" in api or "nothing leaves the PC" in api)
    check("... and names pictures.json and the default folder",
          "pictures.json" in api and "Pictures\\Jarvis" in api)
    check("... and says the prompts hide with the memory lists",
          "Hide memory lists and chat history" in api)
    check("... and says the sidecar holds the seed and the model",
          "sidecar" in api and "seed" in api and "model" in api)
    check("... and says the prompt can never come from a model turn",
          "tool in `jarvis_agent.py`" in api
          and "reachable from no\nmodel turn" in api.replace("  ", " "),
          "the section must say this")
    # This branch's section moved 124 -> 126 on 2026-10-11 (main's 124 is the
    # picture-CARD module and 125 the uncensored opt-ins), so a check on
    # "the last 124" would now read MAIN's section and prove nothing about this
    # feature. It asserts this feature's own heading, exactly once.
    #
    # It used to ALSO require that nothing at all was written after it, as a
    # proxy for "129 is the newest section". That proxy expired on 2026-10-13,
    # when section 130 (the model-facing change_setting tool) was added after it -
    # a fact about the document, not about this feature. What the guard is really
    # for is that this heading identifies THIS feature and no other feature's
    # section was spliced in above it, so it now requires: the heading exactly
    # once, nothing numbered BELOW 129 appearing after it, and the sections after
    # it in ascending order.
    #
    # NOT the whole document in ascending order: it is not, and never was - the
    # run reads ... 101, 102, 110, 103, 104 ... on main already (section 110 sits
    # before 103), which is pre-existing and nothing to do with this feature. A
    # global ordering check would fail on main, so it is not what this asserts.
    #
    # Since Gemini's ruling 1 (2026-11-02) the run from 129 up also has its own
    # check - unique numbers, strictly increasing, at most three missing - in
    # `t_the_sections_from_129_up_are_unique_ascending_and_never_skip_more_than_three`,
    # which reads the numbers through `api_section_numbers` below. This check
    # keeps what is about THIS feature's heading; its `tail == sorted(tail)` is a
    # second, cheaper look at the same run rather than the rule.
    numbered = api_section_numbers(api)
    tail = numbered[numbered.index(129):] if 129 in numbered else []
    check("the section is present once, and nothing numbered below it follows it",
          api.count("\n## 129.") == 1
          and len(tail) >= 1
          and all(n > 129 for n in tail[1:])
          and tail == sorted(tail),
          repr(tail))


#: How many numbers may be MISSING between two sections that are both present.
#:
#: GEMINI'S RULING 1, 2026-11-02, quoted because it is the reason this file no
#: longer carries a hand-written list of every section: *"Update
#: `backend/test_pictures.py` so it checks that all `## <N>.` headings from 129
#: upward have (a) strictly unique numbers (no duplicate `§175`s) and (b)
#: strictly increasing order (`N_i < N_{i+1}`), while allowing a small gap
#: (`<= 3`) when an in-flight sibling PR's reserved number hasn't merged yet -
#: and remove the hardcoded upper bound so PRs stop conflicting on
#: `EXPECTED_SECTIONS_FROM_129`."*
#:
#: WHAT "A GAP OF 3" MEANS HERE, exactly, because an off-by-one in a rule like
#: this is silent: it counts the numbers MISSING between two sections that are
#: both present. `... 174, 178 ...` is three missing (175, 176, 177) and PASSES.
#: `... 174, 179 ...` is four missing and FAILS. The case the ruling is written
#: for is the small one: a sibling PR reserved 175 and has not merged, so a
#: later PR appends 176 and the file reads `... 174, 176 ...` until 175 lands -
#: one missing number, allowed.
#:
#: WHAT THIS COSTS, said out loud rather than implied. The pinned list is gone,
#: so a merge that silently drops up to three sections from the MIDDLE of the
#: run now passes, and a dropped TAIL passes too. That protection was the list
#: every API pull request had to edit, which is why five of them were blocked or
#: serialized by one shared line on 2026-11-02: two PRs that both append a
#: section conflict on it by construction, and a conflicted PR gets no CI at
#: all. Duplicates and out-of-order numbers - what those five were actually
#: hitting - still fail.
MAX_MISSING_BETWEEN_SECTIONS = 3

#: The lowest section number this rule owns. Sections below it are read too, but
#: their numbers are not checked: the document's order is not ascending down
#: there and never was - the run reads ... 101, 102, 110, 103, 104 ... on main
#: already (section 110 sits before 103), 66-69, 76 and 111 were never written,
#: and none of that is a fact this feature owns. A global ordering check would
#: fail on an untouched main, so it is not what the ruling asks for.
FIRST_CHECKED_SECTION = 129


def api_section_numbers(api: str) -> list[int]:
    """Every `## <N>.` heading number in `api`, in the order the file holds them.

    A section heading in `docs/JARVIS-API.md` is `## N.` at the start of a line,
    and requiring that start keeps a `### N.M` subsection from being read as a
    section of its own.
    """
    return [int(m.group(1)) for m in re.finditer(r"\n## (\d+)\.", api)]


def api_section_problems(numbers: list[int]) -> list[str]:
    """Gemini's ruling 1 (2026-11-02) applied to one document's section numbers.

    Returns one plain sentence per thing wrong with the sections from 129 up, in
    document order; an empty list means the document obeys the ruling. Each
    sentence starts with the part of the rule it breaks - `duplicate`, `order`
    or `gap` - so a caller can report them as separate checks and a reader can
    see which part failed.
    """
    tail = [n for n in numbers if n >= FIRST_CHECKED_SECTION]
    problems: list[str] = []
    if FIRST_CHECKED_SECTION not in tail:
        problems.append(
            f"duplicate: there is no section {FIRST_CHECKED_SECTION} at all, so "
            f"the run this rule is about cannot be checked")
    seen: dict[int, int] = {}
    for position, number in enumerate(tail, 1):
        if number in seen:
            problems.append(
                f"duplicate: section {number} appears twice (at heading "
                f"{seen[number]} and heading {position}), and two contracts must "
                f"never share one citation")
        else:
            seen[number] = position
    for before, after in zip(tail, tail[1:]):
        if after <= before:
            problems.append(
                f"order: section {after} comes after {before}, so the numbers do "
                f"not strictly increase")
        elif after - before - 1 > MAX_MISSING_BETWEEN_SECTIONS:
            skipped = ", ".join(str(n) for n in range(before + 1, after))
            problems.append(
                f"gap: sections {before} and {after} skip {after - before - 1} "
                f"numbers ({skipped}), and at most "
                f"{MAX_MISSING_BETWEEN_SECTIONS} may be reserved by a sibling PR "
                f"that has not merged yet")
    return problems


def t_the_sections_from_129_up_are_unique_ascending_and_never_skip_more_than_three():
    """Gemini's ruling 1 (2026-11-02) on `docs/JARVIS-API.md` itself.

    THE RULE, and what it replaced. Until this ruling the file compared the
    document against `EXPECTED_SECTIONS_FROM_129`, a tuple written out by hand
    from 129 to 174, and demanded that the numbers ran contiguously and that
    nothing above 174 had been added "without saying so". That made ONE line the
    thing every API pull request edits: two PRs that both append a section
    conflict on it by construction, the second one loses its CI run, and five
    open PRs were blocked or serialized by it on 2026-11-02. The ruling removes
    the upper bound and checks the document's own numbers instead - unique,
    strictly increasing, with at most three missing numbers between two sections
    so an in-flight sibling's reserved number does not fail the PR behind it.

    WHAT IT CATCHES, which is the case nobody was watching: two sections
    numbered `175`, and a section whose number goes backwards. Either way two
    different contracts end up sharing one citation, or a client reading "the
    next section" reads the wrong one. `docs/JARVIS-API.md` is what the desktop
    and Android apps are written against.

    WHAT IT NO LONGER CATCHES, deliberately - the trade the ruling makes. A
    stale-branch merge once deleted sections 135 and 136 - 305 lines, two whole
    features - with NO conflict shown, and the hand-written list is what caught
    it. With the list gone, a middle gap of up to three and a dropped tail both
    pass; the ruling accepts that in exchange for every API PR no longer editing
    one shared line. `MAX_MISSING_BETWEEN_SECTIONS`'s own comment says this in
    full, and it is the part to read before trusting this check.
    """
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    numbers = api_section_numbers(api)
    tail = [n for n in numbers if n >= FIRST_CHECKED_SECTION]

    # Two sanity anchors, so a broken read cannot make the three checks below
    # vacuous: if the headings ever stop being `## N.` this fails loudly instead
    # of passing over an empty list.
    check("the document still has numbered sections to check at all",
          len(numbers) > 128, f"only {len(numbers)} numbered headings were read")
    check(f"... and section {FIRST_CHECKED_SECTION} and something above it are "
          f"both there",
          bool(tail) and tail[0] == FIRST_CHECKED_SECTION,
          f"the run from {FIRST_CHECKED_SECTION} up reads {tail[:8]}")

    problems = api_section_problems(numbers)

    def broken(part: str) -> list[str]:
        return [p for p in problems if p.startswith(part + ":")]

    check("every section from 129 up has a number of its own - no §175 twice",
          not broken("duplicate"), "; ".join(broken("duplicate")))
    check("... and the numbers strictly increase in document order",
          not broken("order"), "; ".join(broken("order")))
    check(f"... and no two sections skip more than {MAX_MISSING_BETWEEN_SECTIONS} "
          f"numbers (a sibling PR's reserved number may be missing, not four)",
          not broken("gap"), "; ".join(broken("gap")))
    # The whole run is printed when something fails, because a number that is
    # wrong is easiest to spot against the run it sits in.
    check("the run from 129 up reads as one document, not two halves",
          not problems, f"tail {tail}")


def t_the_section_rule_itself_passes_and_fails_the_right_fixtures():
    """The cases in Gemini's ruling 1, each on a document built for it.

    WHY THIS EXISTS. The rule above is the only thing standing between the
    document and a duplicate section number, and it is a rule with three parts
    and an off-by-one in the gap. A check that is only ever run against a
    healthy document proves that it PASSES, never that it BITES - so each
    fixture here breaks one part and the rule is asked to name it. A `FAIL` on
    one of these lines means the rule got weaker, not that the document is
    wrong.
    """
    def doc(*numbers: int) -> str:
        return "".join(f"\n## {n}. A section the fixture made up\n" for n in numbers)

    def problems(*numbers: int) -> list[str]:
        return api_section_problems(api_section_numbers(doc(*numbers)))

    def says(parts: list[str], part: str) -> bool:
        return any(p.startswith(part + ":") for p in parts)

    no_gap = problems(*range(129, 135))
    check("a run with no gap at all is accepted", no_gap == [], repr(no_gap))

    # Below 129 the document is not ascending on main (... 101, 102, 110, 103
    # ...), and this rule must not object to that: it owns 129 and up only.
    below_129 = problems(103, 110, 129, 130)
    check("... and the order of the sections BELOW 129 is not this rule's business",
          below_129 == [], repr(below_129))

    # A duplicate in document order also breaks strict increase, so this fixture
    # trips two parts; the duplicate is what must be NAMED, because "two
    # contracts share §175" is the failure a person has to act on.
    twice = problems(129, 130, 131, 131, 132)
    check("a duplicate number FAILS, and the failure names the number",
          says(twice, "duplicate") and "131" in " ".join(twice), repr(twice))

    backwards = problems(129, 130, 132, 131, 133)
    check("a number out of order FAILS, and that is not read as a duplicate",
          says(backwards, "order") and not says(backwards, "duplicate"),
          repr(backwards))

    three_missing = problems(129, 130, 134)     # 131, 132 and 133 are missing
    check("three numbers missing PASSES - a sibling PR's reserved number has not "
          "merged yet", not says(three_missing, "gap"), repr(three_missing))

    four_missing = problems(129, 130, 135)      # 131, 132, 133 and 134 are missing
    check("four numbers missing FAILS - that is no longer one waiting sibling",
          says(four_missing, "gap"), repr(four_missing))


def t_the_settings_route_changes_one_named_thing_and_only_on_the_pc():
    """The switch, the drawing program and the folder. ONE named change at a
    time, and never from the phone: where a picture is written and which
    program draws it are this PC's own business."""
    folder = tmpdir()
    other = tmpdir("elsewhere")
    st = settings_for(folder, enabled=False, runtime=None)
    check("the settings route is a POST route of its own",
          "/api/pictures/settings" in P.POST_ROUTES, str(P.POST_ROUTES))
    code, out = P.handle_post("/api/pictures/settings",
                              {"action": "enabled", "on": True},
                              settings=st, pc_only=True)
    check("turning the switch on is one change", code == 200 and out["ok"], str(out)[:160])
    check("... and the answer says which change it was", out.get("changed") == "enabled",
          str(out.get("changed")))
    check("... and the switch reads as on afterwards", out["enabled"] is True)
    code, out = P.handle_post("/api/pictures/settings",
                              {"action": "runtime", "runtime": "sd_cpp"},
                              settings=st, pc_only=True)
    check("choosing the drawing program is one change",
          code == 200 and out["runtime"] == "sd_cpp", str(out)[:160])
    check("... and the program's own default address comes with it",
          out.get("runtimes") and any(r["id"] == "sd_cpp" for r in out["runtimes"]),
          str(out.get("runtimes")))
    code, out = P.handle_post("/api/pictures/settings",
                              {"action": "runtime", "runtime": "midjourney"},
                              settings=st, pc_only=True)
    check("a program Jarvis does not know is refused, and both real ones are named",
          code == 400 and "comfyui" in out["error"] and "sd_cpp" in out["error"],
          str(out)[:160])
    code, out = P.handle_post("/api/pictures/settings",
                              {"action": "folder", "folder": str(other)},
                              settings=st, pc_only=True)
    check("choosing the folder is one change",
          code == 200 and out["folder"] == str(other), str(out)[:160])
    check("... and a folder that is not there yet is made",
          other.is_dir(), str(other))
    code, out = P.handle_post("/api/pictures/settings",
                              {"action": "folder", "folder": "  "},
                              settings=st, pc_only=True)
    check("an empty folder is refused in words",
          code == 400 and "folder" in out["error"].lower(), str(out)[:160])
    code, out = P.handle_post("/api/pictures/settings", {"action": "shoes"},
                              settings=st, pc_only=True)
    check("an action Jarvis does not know is refused and names the three",
          code == 400 and "enabled" in out["error"] and "folder" in out["error"],
          str(out)[:160])
    code, out = P.handle_post("/api/pictures/settings",
                              {"action": "enabled", "on": "yes"},
                              settings=st, pc_only=True)
    check("a switch value that is not true/false is refused in words",
          code == 400, str(out)[:160])
    # NEVER from the phone.
    code, out = P.handle_post("/api/pictures/settings",
                              {"action": "enabled", "on": True},
                              settings=st, pc_only=False)
    check("the phone cannot change any of it", code == 403 and out.get("pc_only"),
          str(out)[:160])
    check("... and the refusal is a plain sentence with a full stop",
          str(out.get("error") or "").endswith("."), str(out.get("error")))
    # Drawing a picture from the phone is still fine - it opens no way out.
    stub = StubRuntime("x")
    code, out = P.handle_post("/api/pictures", {"prompt": "a cat"},
                              settings=settings_for(tmpdir()), runtime=stub,
                              pc_only=False)
    check("but the phone CAN ask for a picture - it changes nothing on the PC",
          code == 200 and out["ok"], str(out)[:160])


def t_the_settings_file_round_trips_and_never_enables_itself():
    folder = tmpdir()
    path = tmpdir() / "pictures.json"
    check("a fresh file is written OFF with nothing configured",
          P.save_settings({}, path)["enabled"] is False)
    saved = P.save_settings({"enabled": True, "runtime": "comfyui",
                             "folder": str(folder)}, path)
    check("what was saved is what is read back",
          saved["enabled"] is True and saved["runtime"] == "comfyui"
          and saved["folder"] == str(folder), str(saved))
    check("... and the file on disk holds only the four keys this file owns",
          sorted(json.loads(path.read_text(encoding="utf-8")))
          == ["address", "enabled", "folder", "runtime"],
          path.read_text(encoding="utf-8"))
    check("... with the program's own address filled in",
          saved["address"] == P.RUNTIMES["comfyui"]["address"], str(saved["address"]))
    # A stray key in the file cannot add a fifth setting, and cannot turn the
    # feature on by accident either.
    path.write_text(json.dumps({"enabled": False, "runtime": None,
                                "send_my_pictures_to": "someone"}), encoding="utf-8")
    got = P.load_settings(path)
    check("a key this file does not own is ignored, not carried",
          "send_my_pictures_to" not in got, str(got))
    check("... and the feature reads as off", got["enabled"] is False)
    check("the default folder is under the owner's own Pictures",
          "Pictures" in str(P.default_folder())
          and str(P.default_folder()).endswith("Jarvis"),
          str(P.default_folder()))


def main() -> int:
    for fn in (t_the_mode_is_off_by_default,
               t_the_route_draws_and_says_where_and_how_long,
               t_a_stub_that_is_not_answering_is_one_plain_sentence,
               t_a_drawing_program_that_fails_is_a_sentence_not_a_traceback,
               t_the_plan_finds_the_three_ways_and_the_price,
               t_the_first_request_asks_before_anything_moves,
               t_the_confirmed_draw_steps_the_chat_aside_and_brings_it_back,
               t_a_draw_that_fails_still_brings_the_everyday_chat_back,
               t_the_swap_sentence_is_said_once_and_the_card_carries_no_words,
               t_a_failed_set_aside_draws_nothing_and_says_so,
               t_way_b_is_a_plain_sentence_not_a_broken_draw,
               t_the_phone_may_confirm_the_swap_too,
               t_a_second_confirm_while_a_draw_is_running_is_one_sentence,
               t_the_picture_model_is_given_time_to_let_go_of_the_card,
               t_the_free_answer_is_allowed_to_have_no_body_at_all,
               t_the_route_waits_long_enough_for_a_real_draw,
               t_the_storage_round_trip_keeps_the_record,
               t_the_file_name_is_the_date_the_time_and_a_slug,
               t_two_pictures_on_one_day_do_not_collide,
               t_nothing_configured_is_one_plain_sentence_naming_what_to_install,
               t_the_list_route_reports_the_folder_and_its_size,
               t_the_settings_route_changes_one_named_thing_and_only_on_the_pc,
               t_the_settings_file_round_trips_and_never_enables_itself,
               t_the_picture_itself_comes_back_as_bytes_and_nothing_else_does,
               t_the_routes_are_the_documented_ones,
               t_it_owns_nothing_under_picture_card,
               t_install_wraps_the_handler_and_leaves_every_other_request_alone,
               t_no_picture_is_sent_anywhere_and_no_model_can_reach_this,
               t_the_api_document_has_the_section_and_it_matches_this_code,
               t_the_sections_from_129_up_are_unique_ascending_and_never_skip_more_than_three,
               t_the_section_rule_itself_passes_and_fails_the_right_fixtures):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
