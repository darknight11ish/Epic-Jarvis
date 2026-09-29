"""Kokoro v1.0: the voice pack, voices BY NAME, "Hear it", the carry-over of the
owner's old choice, and the pinned download (the owner's decision of
2026-09-28, built 2026-09-29; docs/JARVIS-API.md section 94).

    python3 test_kokoro.py

Runs anywhere; no model downloads, no network. A stand-in `voices.bin` of each
pack's REAL size is all the PC looks at to tell the packs apart. With
JARVIS_KOKORO_V1_DIR pointing at an unpacked kokoro-multi-lang-v1_0 folder and
sherpa-onnx installed, it also speaks in every offered voice with the real
model (the run in the build notes, docs/CRITTERS.md). With /opt/pwsh/pwsh
present it runs the real install line against a local web server.

What it proves:

  - the two packs' voice tables (11 and 54, and where each voice sits) and
    that a voices.bin is told apart by its size alone;
  - the owner's old NUMBER means the name it meant, once, and the choice never
    changes (the built-in voice, the animals, `[voice] tts_speaker_id`);
  - the picker offers the pack's own voices, best rated first, never Sky or
    Adam to anyone who has not already chosen one, and no animal may use them;
  - a voice this pack does not have is not spoken by the wrong number;
  - British voices are asked for British English (only on v1.0), American ones
    for the engine's own language, and a sherpa-onnx that cannot be asked
    speaks as before;
  - "Hear it": a fixed line, in the named voice only, never a recording, never
    the face's pitch, one at a time, kept in memory only, and NOTHING about
    the PC changes - no state written, no card, no event, no audit line;
  - the pinned download: one constant, the install line is written from it
    and README.md holds the same line, and it is never offered without a
    checksum.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, require_shipped  # noqa: E402

for p in (HERE / "rebuilt",):
    if str(p) not in sys.path:
        sys.path.append(str(p))

require_shipped("jarvis_kokoro.py", "jarvis_voices.py", "jarvis_speech.py")

import numpy as np  # noqa: E402
import jarvis_kokoro as K  # noqa: E402
import jarvis_voices as V  # noqa: E402
import jarvis_speech as S  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


TMP = Path(tempfile.mkdtemp(prefix="jarvis-kokoro-"))
CFG, AUDIT, EVENTS, CARDS = {}, [], [], []
_ORIG = {n: getattr(V, n) for n in ("_config_dir", "_cfg", "_audit", "_publish", "_gate",
                                    "_voices_file")}
_S_CFG = S._cfg
_S_SHERPA = S.sherpa_onnx
PACK = {"path": None}


class FakeKokoro:
    """sherpa-onnx's OfflineTts for Kokoro, as far as Jarvis calls it."""

    def __init__(self):
        self.calls = []       # (sid, speed, lang) per sentence
        self.fail_config = False

    def generate(self, text, *args, **kwargs):
        if args and hasattr(args[0], "sid"):          # generate(text, GenerationConfig)
            cfg = args[0]
            if self.fail_config:
                raise RuntimeError("this sherpa-onnx cannot be asked for a language")
            self.calls.append((cfg.sid, cfg.speed, (cfg.extra or {}).get("lang")))
        else:                                         # generate(text, sid=, speed=)
            sid = kwargs.get("sid", args[0] if args else 0)
            speed = kwargs.get("speed", args[1] if len(args) > 1 else 1.0)
            self.calls.append((sid, speed, None))
        return types.SimpleNamespace(samples=(0.05 * np.ones(12000)).astype(np.float32),
                                     sample_rate=24000)


class FakeGenerationConfig:
    def __init__(self):
        self.sid = 0
        self.speed = 1.0
        self.extra = {}


def reset(pack=None, face_voice=None):
    """A fresh config folder. `pack`: "v1", "v019" or None (no pack files)."""
    V._reset_for_tests()
    d = Path(tempfile.mkdtemp(prefix="cfg-", dir=TMP))
    CFG.clear()
    AUDIT.clear()
    EVENTS.clear()
    CARDS.clear()
    V._config_dir = lambda: d
    V._cfg = lambda k, default=None: CFG.get(k, default)
    V._audit = lambda e, det: AUDIT.append((e, dict(det)))
    V._publish = lambda data: EVENTS.append(dict(data))

    def no_card(*a, **k):
        CARDS.append(a)
        raise AssertionError("a built-in voice choice or a sample must never raise a card")
    V._gate = no_card
    vf = d / "tts" / "voices.bin"
    vf.parent.mkdir(parents=True, exist_ok=True)
    if pack:
        with open(vf, "wb") as f:
            f.truncate(K.voices_file_size(pack))
    V._voices_file = lambda: str(vf)
    PACK["path"] = vf
    S._cfg = lambda k, default=None: CFG.get(k, default)
    S._tts_cache = FakeKokoro()
    S.sherpa_onnx = types.SimpleNamespace(GenerationConfig=FakeGenerationConfig)
    if face_voice is not None:
        V._write_state(face_voice=face_voice, face_answers={f: "use" for f in V.FACE_VOICES})
        AUDIT.clear()
        EVENTS.clear()
    return d


def show_face(d: Path, face):
    (d / "appearance.json").write_text(json.dumps({"face": face}), encoding="utf-8")


def state_text() -> str:
    p = V._state_path()
    return p.read_text(encoding="utf-8") if p.is_file() else ""


# ------------------------------------------------------------------ the tables --

def t_the_two_packs_are_the_real_ones():
    check("v0.19 has 11 voices, v1.0 has 54, every name once",
          len(K.V019_NAMES) == 11 and len(K.V1_NAMES) == 54
          and len(set(K.V019_NAMES)) == 11 and len(set(K.V1_NAMES)) == 54)
    check("v0.19's order is the one the repo's own toml comment confirms (0 = af, 9 = bm_george)",
          K.V019_NAMES[0] == "af" and K.V019_NAMES[9] == "bm_george"
          and K.V019_NAMES[4] == "af_sky" and K.V019_NAMES[10] == "bm_lewis")
    check("v1.0's English voices are the first 28, alphabetical; em_santa is last (index 53)",
          K.V1_NAMES[:28] == tuple(sorted(K.V1_NAMES[:28]))
          and K.V1_NAMES[3] == "af_heart" and K.V1_NAMES[9] == "af_sarah"
          and K.V1_NAMES[26] == "bm_george" and K.V1_NAMES[53] == "em_santa"
          and K.V1_NAMES.index("em_alex") == 29)
    check("number 9 is George on the old pack and Sarah on v1.0 - the reason for saving names",
          K.V019_NAMES[9] == "bm_george" and K.V1_NAMES[9] == "af_sarah")
    check("the old numbers map to the names they meant, in order",
          K.LEGACY_NAME == {str(i): n for i, n in enumerate(K.V019_NAMES)}
          and K.LEGACY_NAME["9"] == "bm_george" and K.LEGACY_NAME["4"] == "af_sky")
    sizes = {"v1": 28_200_960, "v019": 5_755_904}
    check("a voices.bin's size is what tells the packs apart (the real files' sizes)",
          K.voices_file_size("v1") == sizes["v1"] and K.voices_file_size("v019") == sizes["v019"])
    d = Path(tempfile.mkdtemp(dir=TMP))
    kinds = {}
    for name, size in (("a", sizes["v1"]), ("b", sizes["v019"]), ("c", 12345),
                       ("d", K.voices_file_size("v1") + 4), ("e", 103 * 510 * 256 * 4)):
        with open(d / name, "wb") as f:
            f.truncate(size)
        kinds[name] = K.kind_of_file(d / name)
    check("v1.0, v0.19 - and a wrong size, a damaged file and a v1.1 pack are neither",
          kinds == {"a": "v1", "b": "v019", "c": "", "d": "", "e": ""}, kinds)
    check("a missing file, and things that are not paths, are no pack",
          K.kind_of_file(d / "nope") == "" and K.kind_of_file(None) == ""
          and K.kind_of_file("") == "")


def t_names_carry_over_and_stand_in():
    check("an old number is read as its name; a name as itself; nothing else",
          K.normalise("9") == "bm_george" and K.normalise("0") == "af"
          and K.normalise("bm_george") == "bm_george" and K.normalise("zf_xiaobei") == "zf_xiaobei"
          and K.normalise("11") is None and K.normalise("warp") is None
          and K.normalise(9) is None and K.normalise(None) is None and K.normalise(True) is None
          and K.normalise(["9"]) is None)
    check("the old default 'af' is af_heart on v1.0 (and back)",
          K.resolve("v1", "af") == "af_heart" and K.resolve("v019", "af_heart") == "af"
          and K.sid_of("v1", "af") == 3 and K.sid_of("v019", "af") == 0)
    check("a v1.0-only voice is not in the old pack, and is never spoken by another's number",
          K.resolve("v019", "am_fenrir") is None and K.sid_of("v019", "am_fenrir") is None
          and K.sid_of("v1", "am_fenrir") == 14)
    check("every offered voice exists in its pack",
          all(n in K.names("v1") for n in K.V1_PICK) and all(n in K.names("v019") for n in K.V019_PICK))
    check("nobody is offered Sky or Adam, and no animal ever may use them",
          not {"af_sky", "am_adam"} & set(K.V1_PICK + K.V019_PICK)
          and not {"af_sky", "am_adam"} & set(K.pickable_for_animals()))
    check("names that match OpenAI's voices, and the low-graded ones, are not offered either",
          not {"af_alloy", "am_echo", "am_onyx", "af_nova", "bm_fable"} & set(K.V1_PICK))
    check("the best rated (Heart) is first on v1.0; the pack's own default on the old one",
          K.V1_PICK[0] == "af_heart" and K.V019_PICK[0] == "af"
          and K.default_name("v1") == "af_heart" and K.default_name("v019") == "af"
          and K.default_sid("v1") == 3 and K.default_sid("v019") == 0)
    rows = K.offered("v1", "af_sky")
    check("the owner's current choice is listed once at the end, in words, if it is not offered",
          [r["id"] for r in rows][-1] == "af_sky" and len(rows) == len(K.V1_PICK) + 1
          and rows[-1]["label"] == "American (female) - Sky (your current choice)")
    check("... and not twice if it is offered",
          len(K.offered("v1", "af_bella")) == len(K.V1_PICK))
    check("labels are plain words",
          K.label_of("af") == "American (female)" and K.label_of("af_heart") == "American (female) - Heart"
          and K.label_of("bm_george") == "British (male) - George"
          and K.label_of("am_michael") == "American (male) - Michael"
          and K.label_of("zf_xiaobei") == "Voice zf_xiaobei" and K.label_of("") == "")
    check("British voices are asked for British English - on v1.0 only",
          K.accent_lang("v1", "bf_emma") == K.BRITISH_LANG == "en-gb-x-rp"
          and K.accent_lang("v1", "bm_lewis") == "en-gb-x-rp"
          and K.accent_lang("v1", "am_michael") is None and K.accent_lang("v1", "af_heart") is None
          and K.accent_lang("v019", "bf_emma") is None and K.accent_lang("", "bf_emma") is None
          and K.accent_lang("v1", "bf_emma", "en-gb-scotland") == "en-gb-scotland"
          and K.accent_lang("v1", None) is None)
    check("sids go both ways",
          all(K.name_of("v1", K.sid_of("v1", n)) == n for n in K.V1_NAMES)
          and K.name_of("v1", 54) is None and K.name_of("v1", -1) is None
          and K.name_of("v1", True) is None and K.name_of("v1", "3") is None)


# ------------------------------------------------------------ the pinned download --

def t_the_pin_is_one_constant_and_the_line_is_written_from_it():
    pin = K.V1_PACK
    check("the pin is a real GitHub release URL, a size and a SHA-256 (64 hex)",
          pin["url"].startswith("https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/")
          and pin["url"].endswith(".tar.bz2") and pin["folder"] == "kokoro-multi-lang-v1_0"
          and re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]) and pin["bytes"] == 349_906_910)
    line = K.install_line()
    check("the install line is ONE line", "\n" not in line and "\r" not in line and len(line) > 300)
    check("it holds the URL, the checksum (as PowerShell prints it) and the folder",
          pin["url"] in line and pin["sha256"].upper() in line and pin["folder"] in line
          and "350 MB" in line)
    check("it checks the file before it unpacks anything, and installs nothing if it differs",
          line.index("Get-FileHash") < line.index("tar -xjf")
          and "-ne '" + pin["sha256"].upper() + "'" in line
          and "so nothing was installed" in line and "Remove-Item $f" in line)
    check("it keeps the old pack beside the new one (tts-old-<time>), so going back is a rename",
          "'tts-old-'" in line and "Rename-Item $d" in line)
    check("it uses the same config-folder rule as the v0.19 line (OPENJARVIS_CONFIG_DIR, then JARVIS_CONFIG_DIR)",
          "$env:OPENJARVIS_CONFIG_DIR" in line and "$env:JARVIS_CONFIG_DIR" in line
          and "\\.openjarvis" in line)
    saved = dict(K.V1_PACK)
    try:
        K.V1_PACK["sha256"] = ""
        check("with no checksum there is NO line, and no upgrade note pointing at one",
              K.install_line() == "" and K.upgrade_note() == "")
    finally:
        K.V1_PACK.update(saved)
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    check("backend/README.md holds exactly this line, under its own heading",
          "Upgrade the voice pack to Kokoro v1.0" in readme and line in readme)
    check("the upgrade note points at that heading and says what it costs",
          "Upgrade the voice pack to Kokoro v1.0" in K.upgrade_note() and "350 MB" in K.upgrade_note()
          and "carries over" in K.upgrade_note())


def t_the_real_line_runs_on_powershell():
    pwsh = "/opt/pwsh/pwsh"
    tar = shutil.which("tar")
    if not (os.path.isfile(pwsh) and tar):
        print("skip  no PowerShell 7 at /opt/pwsh/pwsh: the real line was run by hand instead")
        return
    import hashlib
    import http.server
    import functools
    root = Path(tempfile.mkdtemp(prefix="ps-", dir=TMP))
    pack = root / "kokoro-multi-lang-v1_0"
    pack.mkdir()
    for n in ("model.onnx", "voices.bin", "tokens.txt"):
        (pack / n).write_bytes(b"fake " + n.encode())
    served = root / "www"
    served.mkdir()
    subprocess.run([tar, "-cjf", str(served / "pack.tar.bz2"), "-C", str(root),
                    "kokoro-multi-lang-v1_0"], check=True)
    good = hashlib.sha256((served / "pack.tar.bz2").read_bytes()).hexdigest()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(served))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/pack.tar.bz2"
    base_line = K.install_line().replace(K.V1_PACK["url"], url)

    def run(line, cfg):
        env = dict(os.environ, OPENJARVIS_CONFIG_DIR=str(cfg), TEMP=str(root))
        env.pop("JARVIS_CONFIG_DIR", None)
        return subprocess.run([pwsh, "-NoProfile", "-Command", line], capture_output=True,
                              text=True, env=env, timeout=180)

    try:
        # Right file, an old pack already there: installed, old one kept.
        cfg = root / "cfg-ok"
        (cfg / "voice-models" / "tts").mkdir(parents=True)
        (cfg / "voice-models" / "tts" / "voices.bin").write_bytes(b"old")
        r = run(base_line.replace(K.V1_PACK["sha256"].upper(), good.upper()), cfg)
        tts = cfg / "voice-models" / "tts"
        olds = [p for p in (cfg / "voice-models").iterdir() if p.name.startswith("tts-old-")]
        check("the line installs the pack and keeps the old one as tts-old-<time>",
              r.returncode == 0 and (tts / "model.onnx").is_file() and (tts / "voices.bin").is_file()
              and len(olds) == 1 and (olds[0] / "voices.bin").read_bytes() == b"old"
              and "OK - the new voices are in" in r.stdout, (r.returncode, r.stdout, r.stderr))
        # A file that is not the pinned one: nothing installed, the old pack untouched.
        cfg2 = root / "cfg-bad"
        (cfg2 / "voice-models" / "tts").mkdir(parents=True)
        (cfg2 / "voice-models" / "tts" / "voices.bin").write_bytes(b"old")
        r2 = run(base_line, cfg2)  # the real pin against the fake file: a different hash
        check("a file that is not the pinned one installs NOTHING and leaves the old pack alone",
              "so nothing was installed" in r2.stdout
              and (cfg2 / "voice-models" / "tts" / "voices.bin").read_bytes() == b"old"
              and not [p for p in (cfg2 / "voice-models").iterdir() if p.name.startswith("tts-old-")]
              and not (root / "jarvis-tts-v1.tar.bz2").exists(), (r2.returncode, r2.stdout, r2.stderr))
    finally:
        srv.shutdown()


# ------------------------------------------------------------- the picker, by name --

def t_the_choices_come_from_the_pack_that_is_installed():
    reset("v1")
    view = V.speaker_view()
    check("Kokoro v1.0: eleven voices by name, Heart first and chosen, and the way to make "
          "Ashby and Clara in its note (they are not made yet)",
          [c["id"] for c in view["choices"]] == list(K.V1_PICK) and view["choice"] == "af_heart"
          and view["default"] == "af_heart" and view["note"] == K.BLENDS_TO_MAKE
          and view["pack"] == {"kind": "v1", "name": "Kokoro v1.0", "voices": 54}, view)
    check("and speaker() is Heart's number in that pack (3), not 0",
          V.speaker() == 3 and V.speaker_name() == "af_heart")
    reset("v019")
    view = V.speaker_view()
    check("the old pack: nine voices, no Sky or Adam, the way to the new pack in its note",
          [c["id"] for c in view["choices"]] == list(K.V019_PICK) and view["choice"] == "af"
          and view["note"] == K.upgrade_note() + " " + K.BLENDS_NEED_V1
          and view["pack"]["kind"] == "v019"
          and V.speaker() == 0, view)
    reset(None)
    view = V.speaker_view()
    check("no pack files: the old list, no note (there is no voice to upgrade)",
          [c["id"] for c in view["choices"]] == list(K.V019_PICK) and view["note"] == ""
          and view["pack"] == {"kind": "", "name": "", "voices": 0})
    check("GET /api/voice/voices carries it", V.status()["speaker"] == V.speaker_view())


def t_a_choice_is_saved_by_name_and_followed():
    reset("v1")
    code, out = V.handle_post("/api/voice/voices/speaker", {"speaker": "bm_george"})
    check("POST speaker with a name: 200, at once, no card",
          code == 200 and out["ok"] is True and not CARDS, (code, out))
    check("it is kept BY NAME, and speaker() is that voice's number in THIS pack (26, not 9)",
          json.loads(state_text())["speaker"] == "bm_george" and V.speaker() == 26
          and V.speaker_name() == "bm_george")
    check("the answer names the voice, and the audit line and event carry the name only",
          out["message"] == "Jarvis's built-in voice is now British (male) - George."
          and AUDIT == [("voices.speaker", {"speaker": "bm_george"})]
          and EVENTS == [{"what": "speaker", "outcome": "set"}], (AUDIT, EVENTS))
    check("jarvis_speech reads the same, from the one source",
          S.tts_speaker() == 26 and S.tts_voice()[0] == 26 and S.tts_voice(plain=True)[0] == 26)
    for bad in ({"speaker": "9"}, {"speaker": 26}, {"speaker": "af_sky"}, {"speaker": "am_adam"},
                {"speaker": "zf_xiaobei"}, {"speaker": "bm_george", "x": 1}, {}, None, "bm_george",
                {"speaker": None}, {"speaker": ["bm_george"]}, {"speaker": "grandpa"}):
        c, o = V.set_speaker(bad)
        check(f"refused: {bad!r}", c == 400 and o["ok"] is False
              and o["error"] == "choose one of the listed voices", (c, o))
    check("and nothing changed", json.loads(state_text())["speaker"] == "bm_george")
    V.set_speaker({"speaker": "am_fenrir"})
    reset("v019")
    c, o = V.set_speaker({"speaker": "am_fenrir"})
    check("a v1.0 voice cannot be chosen on the old pack", c == 400, (c, o))


def t_a_voice_the_pack_does_not_have_is_never_spoken_by_a_wrong_number():
    reset("v019")
    V._write_state(speaker="am_fenrir")            # chosen while v1.0 was installed
    view = V.speaker_view()
    check("the old pack speaks its default, and says so in words",
          V.speaker() == 0 and view["choice"] == "af"
          and "American (male) - Fenrir" in view["note"] and "newer voice pack" in view["note"], view)
    reset("v1")
    V._write_state(speaker="af")                    # the old default, saved before the upgrade
    view = V.speaker_view()
    check("the old default is Heart on v1.0: same choice, its new name",
          view["choice"] == "af_heart" and V.speaker() == 3 and "note" in view
          and view["note"] == K.BLENDS_TO_MAKE)
    V._write_state(speaker="af_sky")                # chosen before Sky was taken off the list
    view = V.speaker_view()
    check("a voice that is no longer offered still works for the owner who chose it, "
          "and stays listed as their current choice",
          V.speaker() == 9 + 1 and view["choice"] == "af_sky"
          and view["choices"][-1] == {"id": "af_sky",
                                      "label": "American (female) - Sky (your current choice)"}, view)
    c, o = V.set_speaker({"speaker": "af_sky"})
    check("... and choosing it again is allowed (it is what they have)", c == 200, (c, o))


def t_the_settings_file_number_keeps_its_old_meaning():
    reset("v1")
    CFG["tts_speaker_id"] = 9
    check("[voice] tts_speaker_id = 9 is still George (the old numbering), on v1.0 too",
          V.speaker_name() == "bm_george" and V.speaker() == 26
          and V.speaker_view()["choice"] == "bm_george"
          and V.speaker_view()["note"] == K.BLENDS_TO_MAKE)
    CFG["tts_speaker_id"] = 0
    check("0 is the default American voice", V.speaker_name() == "af_heart" and V.speaker() == 3)
    CFG["tts_speaker_id"] = 40
    view = V.speaker_view()
    check("a number beyond the old list is used as it is, and shown as custom, said plainly",
          V.speaker() == 40 and view["choice"] == "custom" and "40" in view["note"]
          and "tts_speaker_id" in view["note"], view)
    CFG["tts_speaker_id"] = -1
    check("an impossible value is ignored", V.speaker() == 3)
    CFG["tts_speaker_id"] = 9
    V.set_speaker({"speaker": "af_bella"})
    check("the owner's choice wins over the file", V.speaker() == 2 and V.speaker_name() == "af_bella")


# ------------------------------------------------------- the one-time carry-over --

def t_an_old_saved_number_becomes_its_name_once():
    reset("v019")
    V._state_path().parent.mkdir(parents=True, exist_ok=True)
    V._state_path().write_text(json.dumps({
        "active": "builtin", "speaker": "9", "speed": "faster",
        "face_animals": {
            "seaotter": {"speaker": "4", "semitones": 3.0, "pace": "normal"},
            "redpanda": {"speaker": "3", "semitones": 1.5, "pace": "slower"},
            "monkey": {"speaker": "7", "semitones": 1.0, "pace": "normal"},
            "pygmyowl": {"speaker": "5", "semitones": 0.0, "pace": "normal"}}}))
    check("read at once as what it meant, before anything is written",
          V._read_state()["speaker"] == "bm_george" and V.speaker() == 9)
    check("the animals' numbers are names too; Sky and Adam are no animal's choice",
          V._read_state()["face_animals"] == {
              "redpanda": {"speaker": "af_sarah", "semitones": 1.5, "pace": "slower"},
              "monkey": {"speaker": "bf_emma", "semitones": 1.0, "pace": "normal"}},
          V._read_state()["face_animals"])
    moved = V.migrate_saved_choices()
    raw = json.loads(state_text())
    check("the migration writes the names back, once, and keeps everything else",
          raw["speaker"] == "bm_george" and raw["speed"] == "faster"
          and raw["face_animals"]["redpanda"]["speaker"] == "af_sarah"
          and "seaotter" not in raw["face_animals"] and "pygmyowl" not in raw["face_animals"]
          and raw["face_animals"]["monkey"]["speaker"] == "bf_emma", raw)
    check("it says what moved: the built-in voice, and each animal ('None' = back to its own)",
          moved == [("built-in voice", "9", "bm_george"), ("seaotter", "4", None),
                    ("redpanda", "3", "af_sarah"), ("monkey", "7", "bf_emma"),
                    ("pygmyowl", "5", None)], moved)
    check("the audit lines have numbers and names only",
          AUDIT == [("voices.speaker_migrated", {"what": w, "from": a, "to": b})
                    for w, a, b in moved], AUDIT)
    AUDIT.clear()
    check("a second time there is nothing to do, nothing is written, nothing is logged",
          V.migrate_saved_choices() == [] and not AUDIT and json.loads(state_text()) == raw)
    check("the owner's choice never changed: still George, same number",
          V.speaker_name() == "bm_george" and V.speaker() == 9)


def t_status_does_the_carry_over_and_survives_damage():
    reset("v019")
    V._state_path().parent.mkdir(parents=True, exist_ok=True)
    V._state_path().write_text(json.dumps({"active": "builtin", "speaker": "10"}))
    st = V.status()
    check("GET /api/voice/voices carries the choice over (Lewis) and rewrites the file",
          st["speaker"]["choice"] == "bm_lewis"
          and json.loads(state_text())["speaker"] == "bm_lewis")
    for junk in ("", "not json", "[]", '{"speaker": 7}', '{"speaker": "warp"}',
                 '{"face_animals": "x"}', '{"face_animals": {"redpanda": "x"}}'):
        V._state_path().write_text(junk)
        try:
            ok = V.migrate_saved_choices() == [] and V.status()["available"] is True
        except Exception as exc:  # never a crash
            ok = False
            print("        ", type(exc).__name__, exc)
        check(f"a damaged state file is never a crash: {junk!r}", ok)
    reset("v019")
    check("no state file at all: nothing to carry over", V.migrate_saved_choices() == []
          and not V._state_path().exists())


# ------------------------------------------------------------------ the animals --

def t_the_animals_keep_their_voices_by_name_and_never_sky():
    d = reset("v1", face_voice=True)
    want = {"redpanda": ("af_bella", 2), "pygmyowl": ("af_nicole", 6),
            "seaotter": ("af_sarah", 9), "monkey": ("am_michael", 16),
            "robot": ("bf_emma", 21)}
    for face, (name, sid) in want.items():
        show_face(d, face)
        check(f"{face}: {name}, number {sid} on v1.0",
              V.FACE_VOICES[face]["speaker"] == name and V.builtin_voice()[0] == sid
              and S.tts_speaker() == sid, V.builtin_voice())
    check("no animal's own voice is Sky or Adam (the owner's 2026-09-28 rule for the otter)",
          all(r["speaker"] not in ("af_sky", "am_adam") for r in V.FACE_VOICES.values()))
    reset("v019", face_voice=True)
    show_face(V._config_dir(), "seaotter")
    check("on the old pack the same names are the old numbers (3, 6, 1, 2, 7 as before)",
          [K.sid_of("v019", r["speaker"]) for r in V.FACE_VOICES.values()] == [1, 2, 3, 6, 7])
    d = reset("v1", face_voice=True)
    code, out = V.set_face_animal({"face": "redpanda", "speaker": "am_fenrir", "semitones": 1.0,
                                   "pace": "normal"})
    show_face(d, "redpanda")
    check("an animal may pick a v1.0 voice", code == 200 and V.builtin_voice()[0] == 14, (code, out))
    check("its row and the choices are names, without Sky or Adam",
          out["face_voice"]["animals"][0]["speaker"] == "am_fenrir"
          and out["face_voice"]["animals"][0]["voice"] == "Fenrir"
          and [v["id"] for v in out["face_voice"]["animal_choices"]["voices"]] == list(K.V1_PICK))
    for bad in ("af_sky", "am_adam", "4", "5", "zf_xiaobei", ""):
        c, _o = V.set_face_animal({"face": "seaotter", "speaker": bad, "semitones": 0,
                                   "pace": "normal"})
        check(f"the otter (or any animal) cannot pick {bad!r}", c == 400)
    reset("v019", face_voice=True)
    V._write_state(face_animals={"redpanda": {"speaker": "am_fenrir", "semitones": 1.0,
                                              "pace": "normal"}})
    show_face(V._config_dir(), "redpanda")
    check("a v1.0 voice an animal picked, with the old pack back: its own voice speaks (never a wrong number)",
          V.builtin_voice()[0] == 1, V.builtin_voice())


def t_an_animal_saved_with_the_old_default_shows_the_name_the_pack_lists():
    d = reset("v1", face_voice=True)
    V._write_state(face_animals={"redpanda": {"speaker": "af", "semitones": 2.0, "pace": "slower"}})
    show_face(d, "redpanda")
    row = V.face_voice_view()["animals"][0]
    listed = [v["id"] for v in V.face_voice_view()["animal_choices"]["voices"]]
    check("the panda saved as the old pack's plain 'af' shows as af_heart on v1.0 - a name the "
          "picker lists (else the row would show nothing chosen)",
          row["speaker"] == "af_heart" and row["speaker"] in listed and row["voice"] == "Heart", row)
    check("and it speaks as Heart (number 3)", V.builtin_voice()[0] == 3)
    code, out = V.set_face_animal({"face": "redpanda", "speaker": row["speaker"], "semitones": 3.0,
                                   "pace": row["pace"]})
    check("the app can send the row back as it is shown (a new pitch, the same voice): accepted",
          code == 200, (code, out))
    reset("v019", face_voice=True)
    V._write_state(face_animals={"redpanda": {"speaker": "am_fenrir", "semitones": 2.0,
                                              "pace": "normal"}})
    row = V.face_voice_view()["animals"][0]
    check("a v1.0 voice on the old pack shows as the panda's own voice, which is what speaks",
          row["speaker"] == "af_bella" and row["changed"] is True, row)


# ------------------------------------------------------------------- the accent --

def t_british_voices_are_asked_for_british_english():
    reset("v1")
    check("accent_lang by number: Emma (21) and George (26) British, Michael (16) not",
          V.accent_lang(21) == "en-gb-x-rp" and V.accent_lang(26) == "en-gb-x-rp"
          and V.accent_lang(16) is None and V.accent_lang(3) is None)
    CFG["tts_lang_british"] = "en-gb-scotland"
    check("[voice] tts_lang_british changes which British voice of espeak-ng",
          V.accent_lang(21) == "en-gb-scotland")
    CFG.clear()
    reset("v019")
    check("the old pack never asks (its speech is American only)",
          V.accent_lang(7) is None and V.accent_lang(9) is None)
    reset(None)
    check("no pack: never", V.accent_lang(7) is None and V.accent_lang("x") is None)

    reset("v1")
    V.set_speaker({"speaker": "bf_emma"})
    S.say("Of course. I have added the dentist to Tuesday at ten.")
    calls = S._tts_cache.calls
    check("a British voice: one config-based call carrying its language",
          calls == [(21, 1.0, "en-gb-x-rp")], calls)
    V.set_speaker({"speaker": "am_michael"})
    S._tts_cache.calls.clear()
    S.say("Of course. I have added the dentist to Tuesday at ten.")
    check("an American voice: the plain call, the engine's own language, exactly as before",
          S._tts_cache.calls == [(16, 1.0, None)], S._tts_cache.calls)
    reset("v019")
    V.set_speaker({"speaker": "bf_emma"})
    S.say("Of course. I have added the dentist to Tuesday at ten.")
    check("the old pack: plain call even for a British voice",
          S._tts_cache.calls == [(7, 1.0, None)], S._tts_cache.calls)
    reset("v1")
    V.set_speaker({"speaker": "bf_emma"})
    S._tts_cache.fail_config = True
    S.say("Of course. I have added the dentist to Tuesday at ten.")
    check("a sherpa-onnx that cannot be asked for a language speaks as before (never silence)",
          S._tts_cache.calls == [(21, 1.0, None)], S._tts_cache.calls)
    reset("v1")
    S.sherpa_onnx = types.SimpleNamespace()           # no GenerationConfig at all
    V.set_speaker({"speaker": "bf_emma"})
    S.say("Of course. I have added the dentist to Tuesday at ten.")
    check("... including one with no GenerationConfig at all",
          S._tts_cache.calls == [(21, 1.0, None)], S._tts_cache.calls)


def t_the_mouth_timing_is_asked_on_both_packs():
    """2026-09-29: Kokoro v1.0 has its own exact mouth timing now (jarvis_mouth.py
    reads the pack it finds and refuses a copy made for another one), so
    kokoro_speak asks for it on either pack - handing a British voice's own
    language on. If jarvis_mouth cannot, the sound is made as it always was."""
    for kind in ("v1", "v019"):
        reset(kind)
        seen = []
        fake = types.ModuleType("jarvis_mouth")
        fake.speak = lambda *a, **k: seen.append(k) or False
        saved = sys.modules.get("jarvis_mouth")
        sys.modules["jarvis_mouth"] = fake
        try:
            out = []
            got = S.kokoro_speak(S._tts_cache, "Hello there.", 3, 1.0, 0.0, mouth=out)
            check(f"on {kind} jarvis_mouth is asked, and when it declines the sound is made "
                  "the ordinary way with no mouth", got is not None and len(seen) == 1
                  and out == [], (seen, out))
            check(f"... an American voice on {kind}: no per-call language",
                  seen[0].get("extra_lang") is None and seen[0].get("lang") == "en-us", seen[0])
            got = S.kokoro_speak(S._tts_cache, "Hello there.", 21, 1.0, 0.0, mouth=[])
            want = "en-gb-x-rp" if kind == "v1" else None
            check(f"... Emma (21) on {kind}: "
                  + ("British English handed on, as the sound's own call asks"
                     if kind == "v1" else "no accent (that pack speaks American only)"),
                  seen[1].get("extra_lang") == want
                  and seen[1].get("lang") == (want or "en-us"), seen[1])
        finally:
            if saved is None:
                sys.modules.pop("jarvis_mouth", None)
            else:
                sys.modules["jarvis_mouth"] = saved


# ---------------------------------------------------------------------- Hear it --

def t_hear_it_speaks_a_fixed_line_in_the_named_voice():
    d = reset("v1", face_voice=True)
    show_face(d, "seaotter")                        # a pitch-raised animal is showing
    V.set_speed({"speed": "faster"})
    AUDIT.clear()
    EVENTS.clear()
    before = state_text()
    code, out = V.handle_post("/api/voice/voices/sample", {"voice": "bf_isabella"})
    check("200 and a WAV (RIFF/WAVE)", code == 200 and isinstance(out, (bytes, bytearray))
          and out[:4] == b"RIFF" and out[8:12] == b"WAVE", (code, str(out)[:80]))
    check("the fixed line, in that voice's number (bf_isabella = 22), at the owner's speed, "
          "with no animal pitch even though the otter is showing",
          S._tts_cache.calls == [(22, V.SPEED_VALUE["faster"], "en-gb-x-rp")], S._tts_cache.calls)
    check("nothing about the PC changed: no state written, no card, no event, no audit line",
          state_text() == before and not CARDS and not EVENTS and not AUDIT)
    check("the voice Jarvis uses is untouched (Heart), and the otter still speaks as the otter",
          V.speaker_name() == "af_heart" and V.builtin_voice()[3] == "seaotter")
    check("the words are fixed here and hold nothing private",
          V.SAMPLE_LINE == "Hello, I'm Jarvis. This is how I sound."
          and "{" not in V.SAMPLE_LINE)


def t_hear_it_only_takes_a_name_from_the_list():
    reset("v1")
    for bad in ({"voice": "af_sky"}, {"voice": "am_adam"}, {"voice": "9"}, {"voice": 9},
                {"voice": "zf_xiaobei"}, {"voice": "grandpa"}, {"voice": "builtin"},
                {"voice": ""}, {"voice": None}, {"voice": ["af_bella"]}, {}, None,
                {"voice": "af_bella", "text": "say something else"}, "af_bella", []):
        c, o = V.sample_voice(bad)
        check(f"refused: {bad!r}", c == 400 and o["ok"] is False
              and o["error"] == "choose one of the listed voices", (c, o))
    check("the engine was never asked for any of them", S._tts_cache.calls == [])
    V._write_state(speaker="af_sky")
    c, _o = V.sample_voice({"voice": "af_sky"})
    check("the owner's current choice (Sky) can be heard - it is on their list", c == 200)


def t_hear_it_is_never_a_recorded_voice():
    reset("v1")
    folder = V.voices_dir() / "grandpa"
    folder.mkdir(parents=True)
    (folder / "voice.json").write_text(json.dumps({"id": "grandpa", "name": "Grandpa"}))
    V._write_state(active="grandpa")                  # a custom voice is what speaks now
    c, o = V.sample_voice({"voice": "grandpa"})
    check("a recorded voice's id is refused", c == 400, (c, o))
    c, o = V.sample_voice({"voice": "af_heart"})
    check("and a custom voice being active does not make Hear it use it: it is Kokoro's, by name",
          c == 200 and S._tts_cache.calls[-1][0] == 3, S._tts_cache.calls)
    src = (HERE / "jarvis_voices.py").read_text(encoding="utf-8")
    body = src[src.index("def _sample_voice("):src.index("def handle_audio(")]
    check("the code path never touches a recording, a print or the second card",
          not re.search(r"load_voice|clip\.wav|(?<!\w)speak\(|processor_generate|_F5|owner_check|PROFILE", body))


def t_hear_it_is_one_at_a_time_and_kept_in_memory_only():
    reset("v1")
    V.sample_voice({"voice": "af_bella"})
    n = len(S._tts_cache.calls)
    c, wav2 = V.sample_voice({"voice": "af_bella"})
    check("the same voice twice is instant: the second comes from memory",
          c == 200 and len(S._tts_cache.calls) == n)
    V.set_speed({"speed": "slower"})
    V.sample_voice({"voice": "af_bella"})
    check("another speaking speed is another sample (the cache key has it)",
          len(S._tts_cache.calls) == n + 1 and S._tts_cache.calls[-1][1] == V.SPEED_VALUE["slower"])
    check("nothing was written to disk for it",
          sorted(p.name for p in V.voices_dir().iterdir()) == ["state.json"])
    reset("v019")
    V.sample_voice({"voice": "af_bella"})
    m = len(S._tts_cache.calls)
    with open(PACK["path"], "wb") as f:
        f.truncate(K.voices_file_size("v1"))          # the new pack arrives
    V.sample_voice({"voice": "af_bella"})
    check("a new pack is a new sound: the cache key has the pack's size",
          len(S._tts_cache.calls) == m + 1)
    for i in range(30):
        V._SAMPLE_CACHE[("x", i, "x", 1.0)] = b"RIFF"
    V.sample_voice({"voice": "af_nicole"})
    check("the memory is small and never grows without end",
          len(V._SAMPLE_CACHE) <= V._SAMPLE_CACHE_MAX)
    V._SAMPLE_CACHE.clear()
    with V._TRY_LOCK:
        c, o = V.sample_voice({"voice": "af_bella"})
    check("a second one while the first is being made is refused at once, in words (429)",
          c == 429 and o["error"] == V.SAMPLE_BUSY
          and o["error"] == "the PC is still making the sound for the last Hear it. Try again in a moment", (c, o))
    with V._TRY_LOCK:
        c2, _o2 = V.try_face_animal({"face": "redpanda"})
    check("it shares 'Try it's lock: they are never made at the same time", c2 == 429)


def t_hear_it_says_so_when_it_cannot():
    reset("v1")
    S._tts_cache = None
    fake_engine_missing = types.SimpleNamespace(_tts_engine=lambda: None)
    c, o = V.sample_voice({"voice": "af_bella"}, speech_module=fake_engine_missing)
    check("no built-in voice on this PC: 503 in words",
          c == 503 and o["error"] == "this PC has no built-in voice to play it with", (c, o))

    class Boom:
        def generate(self, *a, **k):
            raise RuntimeError("secret detail that must not be shown")
    fake = types.SimpleNamespace(_tts_engine=lambda: Boom(), kokoro_speak=S.kokoro_speak,
                                 _write_wav=S._write_wav)
    S._tts_cache = Boom()
    c, o = V.sample_voice({"voice": "af_bella"})
    check("a voice that fails: 503 naming the exception, never its message",
          c == 503 and "RuntimeError" in o["error"] and "secret" not in o["error"], (c, o))
    reset("v1")

    class Silent:
        def generate(self, *a, **k):
            return types.SimpleNamespace(samples=np.zeros(0, dtype=np.float32), sample_rate=24000)
    S._tts_cache = Silent()
    c, o = V.sample_voice({"voice": "af_bella"})
    check("a voice that makes no sound: 503 in words",
          c == 503 and o["error"] == "the built-in voice made no sound", (c, o))
    check("and the lock is free again afterwards", V._TRY_LOCK.acquire(blocking=False)
          and (V._TRY_LOCK.release() or True))


def t_the_audio_routes_are_wired():
    reset("v1")
    c, wav = V.handle_audio("/api/voice/voices/sample", {"voice": "af_bella"})
    check("handle_audio serves Hear it", c == 200 and wav[:4] == b"RIFF")
    c, wav = V.handle_audio("/api/voice/voices/face_animal/try", {"face": "redpanda"})
    check("... and Try it, as before", c == 200 and wav[:4] == b"RIFF")
    check("... and knows no other route",
          V.handle_audio("/api/voice/voices/speaker", {})[0] == 404)
    check("handle_post finds Hear it too", "/api/voice/voices/sample" in V.ROUTES)
    patch = (HERE / "voices.patch").read_text(encoding="utf-8")
    check("voices.patch sends the WAV for both routes, through handle_audio",
          '"/api/voice/voices/face_animal/try", "/api/voice/voices/sample"' in patch
          and "jarvis_voices.handle_audio(route, body)" in patch
          and 'ctype="audio/wav"' in patch)
    check("the route block is token- and origin-checked like every write",
          patch.index("handle_audio(route, body)") > patch.index('"/api/voice/voices/sample"')
          and patch.count("_token_ok(self)") >= 3)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    import _where
    check("apply-patches.ps1 and _where.SHIPPED copy jarvis_kokoro.py in",
          "'jarvis_kokoro.py'" in ps1 and "jarvis_kokoro.py" in _where.SHIPPED)


def t_no_network_and_no_way_to_hear_the_owner():
    for name in ("jarvis_kokoro.py",):
        src = (HERE / name).read_text(encoding="utf-8")
        bad = re.findall(r"^\s*(?:import|from)\s+(urllib|requests|socket|http|ssl|ftplib|smtplib|"
                         r"subprocess|ctypes)\b", src, re.M)
        check(f"{name} imports nothing that can reach a network or run a program", not bad, bad)
    src = (HERE / "jarvis_voices.py").read_text(encoding="utf-8")
    body = src[src.index("def sample_voice("):src.index("def handle_audio(")]
    check("Hear it has no network call and reads no file but the size of voices.bin",
          not re.search(r"urllib|requests|socket|http\.|open\(|read_bytes|read_text", body), body[:200])


def t_real_model_if_it_is_here():
    d = os.environ.get("JARVIS_KOKORO_V1_DIR")
    try:
        import sherpa_onnx
    except Exception:
        sherpa_onnx = None
    if not d or sherpa_onnx is None:
        print("skip  set JARVIS_KOKORO_V1_DIR to an unpacked kokoro-multi-lang-v1_0 folder (and "
              "install sherpa-onnx) to speak in every offered voice with the real model")
        return
    d = Path(d)
    check("the real voices.bin is Kokoro v1.0 by its size",
          K.kind_of_file(d / "voices.bin") == "v1")
    k = sherpa_onnx.OfflineTtsKokoroModelConfig(
        model=str(d / "model.onnx"), voices=str(d / "voices.bin"), tokens=str(d / "tokens.txt"),
        lexicon="", data_dir=str(d / "espeak-ng-data"), dict_dir="", lang="en-us")
    engine = sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(kokoro=k, num_threads=4)))
    check("54 speakers, as the table says", engine.num_speakers == len(K.V1_NAMES))
    reset("v1")
    V._voices_file = lambda: str(d / "voices.bin")
    S._tts_cache = engine
    S.sherpa_onnx = sherpa_onnx
    lengths = {}
    for n in K.V1_PICK:
        c, wav = V.sample_voice({"voice": n})
        lengths[n] = len(wav) if c == 200 else c
    check("every offered voice speaks the sample with the real model",
          all(isinstance(v, int) and v > 20000 for v in lengths.values()), lengths)
    a = S.kokoro_speak(engine, "Schedule the tomato water and the laboratory.", 26, 1.0)
    engine_plain = engine.generate("Schedule the tomato water and the laboratory.", sid=26, speed=1.0)
    check("a British voice really sounds different from asking for American English for it",
          a is not None and abs(len(a[0]) - len(engine_plain.samples)) > 100,
          (len(a[0]), len(engine_plain.samples)))


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("t_") and callable(v)]

if __name__ == "__main__":
    import traceback
    try:
        for t in TESTS:
            print(f"\n--- {t.__name__} ---")
            try:
                t()
            except Exception:
                FAILED.append(t.__name__)
                traceback.print_exc()
    finally:
        V._config_dir, V._cfg = _ORIG["_config_dir"], _ORIG["_cfg"]
        V._audit, V._publish, V._gate = _ORIG["_audit"], _ORIG["_publish"], _ORIG["_gate"]
        V._voices_file = _ORIG["_voices_file"]
        S._cfg = _S_CFG
        S.sherpa_onnx = _S_SHERPA
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed:", ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
