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
  - the whole tail of `docs/JARVIS-API.md` is still there: every section from
    129 up is checked against a list kept OUTSIDE the document, so a merge that
    silently drops the end of the file fails here and names the missing number;
  - install() wraps a handler, passes every other request through, and refuses
    a request that fails the server's own origin or token check.
"""
from __future__ import annotations

import base64
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

    def available(self):
        return self.ready

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
    numbered = [int(m.group(1)) for m in re.finditer(r"\n## (\d+)\.", api)]
    tail = numbered[numbered.index(129):] if 129 in numbered else []
    check("the section is present once, and nothing numbered below it follows it",
          api.count("\n## 129.") == 1
          and len(tail) >= 1
          and all(n > 129 for n in tail[1:])
          and tail == sorted(tail),
          repr(tail))


#: EVERY numbered section of `docs/JARVIS-API.md` from 129 up, written out by
#: hand so the check below has something INDEPENDENT to compare against.
#:
#: WHY A HAND-WRITTEN LIST AND NOT A DERIVED ONE. Any rule that derives its
#: expectation from the document itself - "the numbers are contiguous", "each
#: number is one more than the last" - has to derive its END from the document
#: too, and that end is the very thing a lost tail changes. The intact document
#: reads 129..136 and a tail-deleted one reads 129..134: contiguous both times,
#: so the derived rule agrees with the deletion. That is the check that CANNOT
#: FAIL, and it is exactly how 135 and 136 went missing. The expectation has to
#: live outside the file being watched, and this list is that outside.
#:
#: WHAT IT COSTS. Adding a section, or deliberately removing one, means editing
#: this list in the same commit - one visible line, and the person doing it
#: writes down that they meant to. That is the price of a check that bites, and
#: it is why the failure message below spells out the difference instead of
#: saying "the document changed".
EXPECTED_SECTIONS_FROM_129 = tuple(range(129, 153))   # 129 ..= 152 (146 app control; 147 setup questionnaire; 148 REA reverse-engineering tool; 149 searchable recordings, F5 S2; 150 the blind-approval guards, 2026-10-21; 151 the Obsidian vault organizer, 2026-10-21; 152 the Notion export -> Obsidian vault routes, 2026-10-21)
#: 137 is a REAL section, not a gap: `## 137. Starting the local model when
#: it is not running`; 138 is `skills.lock` (PR #455). The tail reads
#: 129 ..= 138 with no hole.
#:
#: EVERY SECTION ABOVE 138 IS ITS OWN PR FAMILY, merged in this order:
#: 139 self-improve's diagnostic routes (PR #549); 140 the guardian's history
#: and restore routes (#568/#569/#571); 141 the selection chip (#562); 142
#: the data-and-maths sandbox's own switch (LM-1C, #583); 143 the person
#: dossier click door (LM-4); 144 the media read slice (F5 S1); 145 the preset
#: GET route (2026-10-19); 146 app control on the phone (2026-10-20); 147 the
#: setup questionnaire (2026-10-20, #643); 148 the reverse-engineering tool REA
#: (2026-10-20); 149 the searchable recordings index (F5 S2, 2026-10-20, #641);
#: 150 the two mechanical guards against blind / stacked approvals (review
#: ruling 8.2, 2026-10-20, #680); 151 the Obsidian vault organizer (#681,
#: 2026-10-21); 152 the Notion export -> Obsidian vault routes (#683,
#: 2026-10-21). A section added above 138 gets its row here in
#: the same commit.
#:
#: This list names the RELEASED tail, so a dropped section anywhere in it is
#: caught, and a section above it is reported rather than silently accepted.


def t_every_section_from_129_up_is_still_in_the_document():
    """The whole tail of `docs/JARVIS-API.md`, not just its order.

    THE FAILURE THIS CATCHES. A stale-branch merge once deleted sections 135 and
    136 - 305 lines, two whole features - with NO conflict shown. The check above
    stayed green, and correctly so: what survived was still present exactly once,
    still above 129, still in ascending order. Order among the survivors says
    nothing about a section that is simply gone. This one compares the document
    against a list kept outside it, so a missing section fails the suite and the
    output NAMES the missing number.

    It deliberately does NOT assert that 129 is the highest section, or that the
    document holds no other gaps. The run reads ... 101, 102, 110, 103 ... on
    main already (section 110 sits before 103), 66-69, 76 and 111 were never
    written, and new sections are added above 136 all the time. Each of those is
    a fact about the document that this feature does not own, and a check that
    failed on them would be turned off within a week.
    """
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    # `\n## N.` is the same shape the check above reads, so a number with a
    # `### N.M` subsection is not misread as a section of its own.
    present = {int(m.group(1)) for m in re.finditer(r"\n## (\d+)\.", api)}

    # A sanity anchor, so a broken read cannot make the check below vacuous: if
    # the headings ever stop being `## N.` this fails loudly rather than passing
    # over an empty set.
    check("the document still has numbered sections to check at all",
          len(present) > 128,
          f"only {len(present)} numbered headings were read")

    missing = [n for n in EXPECTED_SECTIONS_FROM_129 if n not in present]
    extra = sorted(n for n in present if n > EXPECTED_SECTIONS_FROM_129[-1])
    check("every section from 129 up is still in docs/JARVIS-API.md",
          not missing,
          f"missing section(s): {missing}. The document jumps "
          f"{sorted(n for n in present if n >= 129)} - a merge that dropped the "
          f"tail of the file leaves no other trace. If 129-up really did change "
          f"on purpose, update EXPECTED_SECTIONS_FROM_129 to the new set in the "
          f"same commit, so the change is visible to a reader.")
    check("... and no section above the list has been added without saying so",
          not extra,
          f"the document has {extra}, which EXPECTED_SECTIONS_FROM_129 does not "
          f"know about; add them to that list in this commit")


def t_the_sections_after_129_run_without_a_gap_or_a_repeat():
    """Every number from 129 to the highest is present exactly once.

    Ported from the branch `test/jarvis-api-section-completeness`, whose own
    docstring records why it was written: *"On 2026-10-15, merging main into a
    stale branch deleted section 135 and 136 (305 lines) with NO conflict shown,
    and this file's order check stayed green."*

    Two checks above already look at this document and neither closes this hole:

    * `t_every_section_from_129_up_is_still_in_the_document` catches a GAP,
      because it demands every number in `EXPECTED_SECTIONS_FROM_129` is present
      - but it can only speak for the numbers that list names, so a section
      added above it reports as `extra` until a person edits the list.
    * the order check catches a section that appears BELOW 129 and asserts the
      tail ascends. `tail == sorted(tail)` is true of a tail holding a repeated
      number, and `api.count("\\n## 129.") == 1` guards only 129 itself.

    So this asserts the RUN, independent of any pinned list: every number from
    129 to the highest present, none missing, **none twice**. Adding a section
    does not need this edited; deleting one fails it; numbering two sections the
    same fails it - which is the case nobody was watching.

    Why it matters beyond tidiness: `docs/JARVIS-API.md` is what the desktop and
    Android apps are written against. A missing section is a route with no
    contract written down; a duplicate number is worse, because two different
    contracts then share one citation.
    """
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    numbered = [int(m.group(1)) for m in re.finditer(r"\n## (\d+)\.", api)]
    if 129 not in numbered:
        check("the sections after 129 run without a gap or a repeat", False,
              "there is no section 129, so the run cannot be checked")
        return
    tail = numbered[numbered.index(129):]
    expected = list(range(129, max(tail) + 1))
    missing = [n for n in expected if n not in tail]
    repeated = sorted({n for n in tail if tail.count(n) > 1})
    check("the sections after 129 run without a gap or a repeat",
          not missing and not repeated,
          f"missing {missing}, repeated {repeated}, tail {tail}")


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
               t_the_sections_after_129_run_without_a_gap_or_a_repeat,
               t_every_section_from_129_up_is_still_in_the_document):
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
