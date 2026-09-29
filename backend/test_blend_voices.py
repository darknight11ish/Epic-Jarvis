"""Ashby and Clara: two blended Kokoro voices made for Jarvis (the owner's
decision of 2026-09-29; docs/JARVIS-API.md section 94.7).

    python3 test_blend_voices.py

Runs anywhere; no model downloads, no network. With JARVIS_KOKORO_V1_DIR
pointing at an unpacked kokoro-multi-lang-v1_0 folder and sherpa-onnx installed
it also builds the REAL blend file from the real pack, checks it against both
pins, speaks a real sentence with each blend and shows the sound differs from
both parents.

What it proves:

  - a blend is the weighted sum of two voices' whole tables, done the same
    way on every machine (so its file can be pinned), written over two unused
    slots of a COPY of the pack's voices.bin - the pack's own file is never
    written, an unexpected pack or result writes nothing;
  - the copy is only believed when it is exactly the pinned file;
  - Ashby and Clara are offered first, each with one plain line, only when
    the copy is what the speech engine loaded; the old pack, "not made yet",
    "bad file", "restart" and "refused" each say so in words;
  - they speak with the right number, British English, and Ashby's own pace
    (0.95) on top of the owner's speed - in an answer, in the crisis-plain
    voice, and in Hear it;
  - the "not the owner's voice" check runs when one is chosen, when it is
    heard and when the voice prints change, and a voice that fails is not
    listed, not chosen and not spoken with; not being able to check is not a
    pass;
  - no animal can use either, ever.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

for p in (HERE / "rebuilt",):
    if str(p) not in sys.path:
        sys.path.append(str(p))

require_shipped("jarvis_kokoro.py", "jarvis_voices.py", "jarvis_speech.py")

import numpy as np  # noqa: E402
import jarvis_kokoro as K  # noqa: E402
import jarvis_voices as V  # noqa: E402
import jarvis_speech as S  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


TMP = Path(tempfile.mkdtemp(prefix="jarvis-blend-"))
CFG, AUDIT, EVENTS, CARDS, SPAWNED = {}, [], [], [], []
FP = {"v": "prints-1"}
CHECKED = []          # what the (stand-in) owner check was asked, in order
OWNER = {"ok": True}  # what the stand-in owner check answers
_ORIG = {n: getattr(V, n) for n in ("_config_dir", "_cfg", "_audit", "_publish", "_gate",
                                    "_voices_file", "owner_check", "prints_fingerprint",
                                    "_spawn")}
_S_CFG = S._cfg
_S_SHERPA = S.sherpa_onnx
_K_PINS = (K.BLEND_SHA256, K.V1_VOICES_SHA256)
V1_SIZE = K.voices_file_size(K.V1)


class FakeKokoro:
    def __init__(self):
        self.calls = []       # (sid, speed, lang) per sentence

    def generate(self, text, *args, **kwargs):
        if args and hasattr(args[0], "sid"):
            cfg = args[0]
            self.calls.append((cfg.sid, cfg.speed, (cfg.extra or {}).get("lang")))
        else:
            sid = kwargs.get("sid", args[0] if args else 0)
            speed = kwargs.get("speed", args[1] if len(args) > 1 else 1.0)
            self.calls.append((sid, speed, None))
        return types.SimpleNamespace(samples=(0.05 * np.ones(24000)).astype(np.float32),
                                     sample_rate=24000)


class FakeGenerationConfig:
    def __init__(self):
        self.sid = 0
        self.speed = 1.0
        self.extra = {}


def stand_in_table(seed=7) -> np.ndarray:
    """A whole v1.0 voices table of random numbers (54 voices x 510 rows x 256)."""
    return np.random.default_rng(seed).standard_normal((54, 510, 256)).astype(np.float32)


_STAND = {}


def stand_in():
    """The stand-in pack's bytes, the blend file the real code makes from it, and
    both hashes - made once (each is 28 MB)."""
    if not _STAND:
        pack = stand_in_table().tobytes()
        (TMP / "stand-in.bin").write_bytes(pack)
        made = K.make_blend_table(K._read_table(TMP / "stand-in.bin")).tobytes()
        _STAND.update(pack=pack, pack_sha=hashlib.sha256(pack).hexdigest(), blend=made,
                      blend_sha=hashlib.sha256(made).hexdigest())
    return _STAND


def write_pack(dir_: Path, table=None) -> Path:
    """A stand-in v1.0 pack: voices.bin of the real size."""
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / "voices.bin").write_bytes(stand_in()["pack"] if table is None else table.tobytes())
    return dir_ / "voices.bin"


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin_to(pack_dir: Path):
    """Point the pins at the stand-in pack and the file made from it."""
    K.V1_VOICES_SHA256 = stand_in()["pack_sha"]
    K.BLEND_SHA256 = stand_in()["blend_sha"]


def reset(pack="v1", blends="none", engine_loaded="path"):
    """A fresh config folder with a stand-in pack. `pack`: "v1", "v019" or None.
    `blends`: "none" (not made), "ready" (the pinned file beside the pack),
    "bad" (a file of the right name that is not the pinned one). `engine_loaded`:
    "path" (jarvis_voices asks where the engine would load from) or "plain" (the
    engine was built on the pack's own voices.bin - a restart is needed)."""
    V._reset_for_tests()
    K._BLEND_OK.clear()
    K.BLEND_SHA256, K.V1_VOICES_SHA256 = _K_PINS
    V._BLEND_CHECKS.clear()
    V._RECHECKING.clear()
    d = Path(tempfile.mkdtemp(prefix="cfg-", dir=TMP))
    CFG.clear()
    AUDIT.clear()
    EVENTS.clear()
    CARDS.clear()
    CHECKED.clear()
    SPAWNED.clear()
    FP["v"] = "prints-1"
    OWNER.clear()
    OWNER["ok"] = True
    V._config_dir = lambda: d
    V._cfg = lambda k, default=None: CFG.get(k, default)
    V._audit = lambda e, det: AUDIT.append((e, dict(det)))
    V._publish = lambda data: EVENTS.append(dict(data))
    V.prints_fingerprint = lambda: FP["v"]
    V._spawn = lambda fn: SPAWNED.append(fn)

    def no_card(*a, **k):
        CARDS.append(a)
        raise AssertionError("a built-in voice choice or a sample must never raise a card")
    V._gate = no_card

    def owner_check(samples, margin=None):
        CHECKED.append(len(samples))
        if OWNER["ok"]:
            return {"ok": True, "checked": 1, "why": "it does not sound like your voice",
                    "fingerprint": FP["v"], "score": 0.1, "bar": 0.5}
        return {"ok": False, "refused": "owner_voice", "fingerprint": FP["v"],
                "why": "this recording sounds too much like YOUR voice", "score": 0.9, "bar": 0.5}
    V.owner_check = owner_check

    tts = d / "voice-models" / "tts"
    plain = tts / "voices.bin"
    tts.mkdir(parents=True, exist_ok=True)
    if pack == "v1":
        write_pack(tts)
        pin_to(tts)
        if blends == "ready":
            (tts / K.BLEND_FILE).write_bytes(stand_in()["blend"])
        elif blends == "bad":
            (tts / K.BLEND_FILE).write_bytes(b"\0" * V1_SIZE)
    elif pack == "v019":
        with open(plain, "wb") as f:
            f.truncate(K.voices_file_size(K.V019))
    CFG["tts_voices"] = ""
    S._cfg = lambda k, default=None: CFG.get(k, default)
    S._models_dir = lambda: d / "voice-models"
    # What jarvis_voices reads as "the voices file": the engine's own answer.
    S._TTS_VOICES = str(plain) if engine_loaded == "plain" else ""
    V._voices_file = _ORIG["_voices_file"]
    S._tts_cache = FakeKokoro()
    S.sherpa_onnx = types.SimpleNamespace(GenerationConfig=FakeGenerationConfig)
    return d


# ------------------------------------------------------------- the tables and the sum --

def t_the_two_voices_are_defined_plainly():
    check("two blends, Ashby first, weights add up to 1",
          K.MIX_IDS == ("mix_ashby", "mix_clara")
          and all(abs(sum(w for _n, w in K.MIX[v]["parts"]) - 1.0) < 1e-12 for v in K.MIX))
    check("Ashby: 70% bm_george, 30% am_michael, British, 0.95",
          K.MIX["mix_ashby"]["parts"] == (("bm_george", 0.7), ("am_michael", 0.3))
          and K.MIX["mix_ashby"]["pace"] == 0.95 and K.MIX["mix_ashby"]["accent"] == "british")
    check("Clara: 60% bf_emma, 40% af_heart, British-leaning, normal pace",
          K.MIX["mix_clara"]["parts"] == (("bf_emma", 0.6), ("af_heart", 0.4))
          and K.MIX["mix_clara"]["pace"] == 1.0 and K.MIX["mix_clara"]["accent"] == "british")
    check("every part is a voice of the pack, and none is Sky or Adam",
          all(n in K.V1_NAMES and n not in K.NEVER_FOR_ANIMALS
              for v in K.MIX for n, _w in K.MIX[v]["parts"]))
    check("the parts are Jarvis's own sources (Kokoro voices) - none is a recorded voice",
          all(K.MIX[v]["parts"][0][0] in K.V1_NAMES for v in K.MIX))
    same = [i for i, (a, b) in enumerate(zip(K.V1_NAMES, K.V1MIX_NAMES)) if a != b]
    check("the copy's table differs from the pack's in exactly the two slots, and nothing moved",
          len(K.V1MIX_NAMES) == 54 and [K.V1_NAMES[i] for i in same] == ["pm_santa", "em_santa"]
          and K.V1MIX_NAMES[K.V1_NAMES.index("em_santa")] == "mix_ashby"
          and K.V1MIX_NAMES[K.V1_NAMES.index("pm_santa")] == "mix_clara")
    check("the two slots are voices Jarvis never speaks with (not offered, not an animal's, not "
          "a part of a blend, not in the old numbering)",
          all(n not in K.V1_PICK + K.V019_PICK and n not in K.LEGACY_NAME.values()
              and all(n != p for v in K.MIX for p, _w in K.MIX[v]["parts"])
              for n in K.MIX_SLOTS.values()))
    check("labels and a plain line for each, and the family of the copy is the pack",
          K.label_of("mix_ashby") == "Ashby (made for Jarvis)"
          and K.label_of("mix_clara") == "Clara (made for Jarvis)"
          and K.family(K.V1MIX) == K.V1 and K.family(K.V019) == K.V019
          and all(K.MIX[v]["detail"].endswith("not modelled on anyone.") for v in K.MIX))
    check("known() and normalise() take them; the animals' list does not",
          K.known("mix_ashby") and K.normalise("mix_clara") == "mix_clara"
          and not any(v in K.pickable_for_animals() for v in K.MIX))
    rows = K.offered(K.V1MIX)
    check("the copy offers them first with their line; the pack alone does not; the old pack never",
          [r["id"] for r in rows[:2]] == ["mix_ashby", "mix_clara"]
          and all("detail" in r for r in rows[:2]) and all("detail" not in r for r in rows[2:])
          and [r["id"] for r in rows[2:]] == list(K.V1_PICK)
          and not any(r["id"] in K.MIX for r in K.offered(K.V1) + K.offered(K.V019)))
    check("British English for both (and for the British voices as before), none for American",
          K.accent_lang(K.V1MIX, "mix_ashby") == K.BRITISH_LANG
          and K.accent_lang(K.V1MIX, "mix_clara") == K.BRITISH_LANG
          and K.accent_lang(K.V1MIX, "bm_george") == K.BRITISH_LANG
          and K.accent_lang(K.V1MIX, "af_heart") is None
          and K.accent_lang(K.V019, "mix_ashby") is None
          and K.accent_lang(K.V1, "mix_ashby") == K.BRITISH_LANG)
    check("Ashby's pace is 0.95, everyone else's 1.0",
          K.voice_pace("mix_ashby") == 0.95 and K.voice_pace("mix_clara") == 1.0
          and K.voice_pace("af_heart") == 1.0 and K.voice_pace(None) == 1.0)
    check("pack_words says Kokoro v1.0 with 54 voices for the copy too",
          K.pack_words(K.V1MIX) == K.pack_words(K.V1) == {"kind": "v1", "name": "Kokoro v1.0",
                                                          "voices": 54})


def t_the_sum_is_the_weighted_sum_of_whole_tables():
    t = stand_in_table(3)
    from array import array
    flat = array("f")
    flat.frombytes(t.tobytes())
    made = np.frombuffer(K.make_blend_table(flat).tobytes(),
                         dtype=np.float32).reshape(54, 510, 256)
    ia, ib, isl = (K.V1_NAMES.index("bm_george"), K.V1_NAMES.index("am_michael"),
                   K.V1_NAMES.index("em_santa"))
    ref = (t[ia].astype(np.float64) * 0.7 + t[ib].astype(np.float64) * 0.3).astype(np.float32)
    check("Ashby's slot holds 0.7 x George + 0.3 x Michael, number for number, exactly as numpy "
          "does it in double precision (so the pin can be exact)", np.array_equal(made[isl], ref))
    ic, id_, isc = (K.V1_NAMES.index("bf_emma"), K.V1_NAMES.index("af_heart"),
                    K.V1_NAMES.index("pm_santa"))
    ref = (t[ic].astype(np.float64) * 0.6 + t[id_].astype(np.float64) * 0.4).astype(np.float32)
    check("Clara's slot holds 0.6 x Emma + 0.4 x Heart", np.array_equal(made[isc], ref))
    others = [i for i in range(54) if i not in (isl, isc)]
    check("every other voice is byte for byte the pack's", np.array_equal(made[others], t[others]))
    check("a blend is neither of its parents",
          not np.array_equal(made[isl], t[ia]) and not np.array_equal(made[isl], t[ib])
          and not np.array_equal(made[isc], t[ic]) and not np.array_equal(made[isc], t[id_]))


# ------------------------------------------------------------- making the file --

def t_building_writes_only_the_pinned_file_beside_the_pack():
    reset("v1")
    tts = Path(V._models_dir()) / "tts"
    before = ((tts / "voices.bin").read_bytes(), (tts / "voices.bin").stat().st_mtime_ns)
    ok, words = K.build_blends(str(tts))
    made = tts / K.BLEND_FILE
    check("the file is made, is the pinned one, and says where it is and to restart",
          ok and made.is_file() and made.stat().st_size == V1_SIZE and sha(made) == K.BLEND_SHA256
          and str(made) in words and "Restart Jarvis" in words, words)
    check("the pack's own voices.bin was not touched (bytes and time)",
          (tts / "voices.bin").read_bytes() == before[0]
          and (tts / "voices.bin").stat().st_mtime_ns == before[1])
    check("no half-written file is left behind", not (tts / (K.BLEND_FILE + ".tmp")).exists())
    check("blend_ok() believes it; table_kind_of_file says v1mix; the pack's own file stays v1",
          K.blend_ok(made) and K.table_kind_of_file(made) == K.V1MIX
          and K.kind_of_file(made) == K.V1 and K.table_kind_of_file(tts / "voices.bin") == K.V1
          and K.blend_state(tts / "voices.bin") == "ready")
    ok2, words2 = K.build_blends(str(tts))
    check("running it again does nothing and says so", ok2 and words2.startswith("Already done"),
          words2)
    made.write_bytes(b"\1" * V1_SIZE)
    check("a file of the right size that is not the pinned one is not believed",
          not K.blend_ok(made) and K.blend_state(tts / "voices.bin") == "bad"
          and K.table_kind_of_file(made) == K.V1)
    ok3, _w = K.build_blends(str(tts))
    check("... and running the line again puts the right one back", ok3 and K.blend_ok(made))


def t_building_refuses_what_it_does_not_expect():
    reset("v1")
    tts = Path(V._models_dir()) / "tts"
    K.V1_VOICES_SHA256 = "0" * 64
    ok, words = K.build_blends(str(tts))
    check("a pack that is not the pinned v1.0 voices.bin: nothing is made",
          not ok and not (tts / K.BLEND_FILE).exists() and "not the one" in words, words)
    reset("v1")
    K.BLEND_SHA256 = "0" * 64
    ok, words = K.build_blends(str(tts := Path(V._models_dir()) / "tts"))
    check("a result that is not the pinned file: nothing is kept, not even a .tmp",
          not ok and not (tts / K.BLEND_FILE).exists()
          and not (tts / (K.BLEND_FILE + ".tmp")).exists() and "nothing was kept" in words, words)
    reset("v019")
    ok, words = K.build_blends(str(Path(V._models_dir()) / "tts"))
    check("the old pack: refused in words, nothing made",
          not ok and "newer voice pack" in words
          and not (Path(V._models_dir()) / "tts" / K.BLEND_FILE).exists(), words)
    reset(None)
    ok, words = K.build_blends(str(Path(V._models_dir()) / "tts"))
    check("no pack at all: says to install it first", not ok and "install it first" in words, words)
    reset("v1")
    K.BLEND_SHA256 = ""
    ok, words = K.build_blends(str(Path(V._models_dir()) / "tts"))
    check("an empty pin: nothing is made, and the pin is what says so",
          not ok and "not pinned" in words, words)
    check("blend_ok() with an empty pin trusts nothing", not K.blend_ok(
        Path(V._models_dir()) / "tts" / "voices.bin"))
    check("main(): no flag is a usage line, --make-blends runs it",
          K.main([]) == 2 and K.main(["--make-blends", "--pack", str(TMP / "nowhere")]) == 1)


def t_the_owner_step_is_one_line_and_in_the_readme():
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    check("the one line is in backend/README.md, under its own heading",
          K.MAKE_LINE in readme and "Make Ashby and Clara" in readme)
    check("it is ONE line (no newline), says where the file lands in the README, and names the "
          "tool that makes it",
          "\n" not in K.MAKE_LINE and "--make-blends" in K.MAKE_LINE
          and "voices-jarvis.bin" in readme)
    check("the pins in the README are the ones in the code",
          _K_PINS[0] in readme and _K_PINS[1] in readme)
    check("jarvis_kokoro.py is copied by the patch script, and only imports the standard library",
          "jarvis_kokoro.py" in (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8"))


# ------------------------------------------------------------- what the engine loads --

def t_the_engine_loads_the_pinned_copy_only():
    d = reset("v1", "ready")
    tts = d / "voice-models" / "tts"
    check("the pinned copy beside the pack is what jarvis_speech loads",
          S._sherpa_tts_paths()["voices"] == str(tts / K.BLEND_FILE))
    CFG["tts_voices"] = str(tts / "voices.bin")
    check("a voices file the owner named in [voice] tts_voices always wins",
          S._sherpa_tts_paths()["voices"] == str(tts / "voices.bin"))
    d = reset("v1", "bad")
    check("a copy that is not the pinned one is never loaded",
          S._sherpa_tts_paths()["voices"] == str(d / "voice-models" / "tts" / "voices.bin"))
    d = reset("v1", "none")
    check("no copy: the pack's own voices.bin, as before",
          S._sherpa_tts_paths()["voices"] == str(d / "voice-models" / "tts" / "voices.bin"))
    d = reset("v019")
    check("the old pack is untouched by any of this",
          S._sherpa_tts_paths()["voices"] == str(d / "voice-models" / "tts" / "voices.bin"))
    d = reset("v1", "ready", engine_loaded="path")
    S._TTS_VOICES = ""
    seen = {}

    class Cfg:
        def __init__(self, **kw):
            seen.update(kw)

    class Model:
        def __init__(self, **kw):
            pass

    class Tts:
        def __init__(self, config):
            self.num_speakers = 54
            self.sample_rate = 24000

    class FullCfg:
        def __init__(self, **kw):
            self.silence_scale = 0.2
    S.sherpa_onnx = types.SimpleNamespace(
        OfflineTtsKokoroModelConfig=Cfg, OfflineTtsModelConfig=Model,
        OfflineTtsConfig=FullCfg, OfflineTts=Tts, GenerationConfig=FakeGenerationConfig)
    CFG["tts_engine"] = "sherpa-onnx"
    S._mouth = lambda *a, **k: None
    eng = S._build_tts_engine()
    check("the engine is built with the copy and remembers which file it loaded",
          eng is not None and seen.get("voices") == str(d / "voice-models" / "tts" / K.BLEND_FILE)
          and S._TTS_VOICES == seen["voices"], (seen, S._TTS_VOICES))
    check("jarvis_voices reads the engine's own answer, not the disk's",
          V._voices_file() == S._TTS_VOICES and V.table_kind() == K.V1MIX
          and V.pack_kind() == K.V1)
    S.reload_engines()
    check("reloading the engines forgets it", S._TTS_VOICES == "")


# ------------------------------------------------------------- the picker, in words --

def choose(vid):
    return V.set_speaker({"speaker": vid})


def t_the_picker_says_where_each_case_stands():
    reset("v1", "ready")
    view = V.speaker_view()
    ids = [c["id"] for c in view["choices"]]
    check("made and loaded: Ashby and Clara first, then the eleven, no note",
          ids == list(K.MIX_IDS) + list(K.V1_PICK) and view["note"] == ""
          and view["choices"][0]["label"] == "Ashby (made for Jarvis)"
          and view["choices"][0]["detail"] == K.MIX["mix_ashby"]["detail"]
          and view["pack"] == {"kind": "v1", "name": "Kokoro v1.0", "voices": 54}
          and view["choice"] == "af_heart" and view["default"] == "af_heart", view)
    check("GET /api/voice/voices carries it", V.status()["speaker"] == V.speaker_view())
    reset("v1", "none")
    view = V.speaker_view()
    check("the new pack, not made yet: not listed, and the note says how",
          [c["id"] for c in view["choices"]] == list(K.V1_PICK)
          and view["note"] == K.BLENDS_TO_MAKE
          and "Make Ashby and Clara" in view["note"] and "restart" in view["note"].lower(), view)
    reset("v1", "bad")
    check("a file that is not the pinned one: not listed, the note says so",
          V.speaker_view()["note"] == K.BLENDS_BAD
          and not any(c["id"] in K.MIX for c in V.speaker_view()["choices"]))
    reset("v1", "ready", engine_loaded="plain")
    view = V.speaker_view()
    check("made while Jarvis runs (the engine loaded the pack's own file): not listed yet, and "
          "the note says to restart",
          view["note"] == K.BLENDS_RESTART
          and not any(c["id"] in K.MIX for c in view["choices"]), view)
    reset("v019")
    view = V.speaker_view()
    check("the old pack: not listed; the note says they need the newer voice pack",
          view["note"].endswith(K.BLENDS_NEED_V1) and "newer voice pack" in view["note"]
          and not any(c["id"] in K.MIX for c in view["choices"]), view)
    c, o = choose("mix_ashby")
    check("... and choosing one there is refused like any unlisted name",
          c == 400 and o["error"] == "choose one of the listed voices", (c, o))
    reset(None)
    check("no pack: no note about them", V.speaker_view()["note"] == "")


def t_choosing_one_runs_the_owner_check_first():
    reset("v1", "ready")
    c, o = choose("mix_ashby")
    check("Ashby: 200, saved by name, and the voice check ran once on a real-length sample",
          c == 200 and o["ok"] and json.loads((V._state_path()).read_text())["speaker"]
          == "mix_ashby" and len(CHECKED) == 1 and CHECKED[0] >= 12000
          and o["message"] == "Jarvis's built-in voice is now Ashby (made for Jarvis).", (c, o))
    check("the answer's speaker block is the new choice, Ashby listed and chosen",
          o["speaker"]["choice"] == "mix_ashby" and o["speaker"]["value"] == 53)
    check("no card, and the audit line carries a name and yes/no only",
          not CARDS and ("voices.blend_check", {"voice": "mix_ashby", "ok": True}) in AUDIT
          and ("voices.speaker", {"speaker": "mix_ashby"}) in AUDIT
          and all("text" not in d for _e, d in AUDIT))
    c, o = choose("mix_clara")
    check("Clara is checked too (the check is per voice)", c == 200 and len(CHECKED) == 2)
    check("the sample was spoken in the voice being checked, in British English, at its own pace",
          (53, 0.95, "en-gb-x-rp") in S._tts_cache.calls
          and (44, 1.0, "en-gb-x-rp") in S._tts_cache.calls, S._tts_cache.calls)
    choose("mix_ashby")
    check("choosing again does not check again (kept for these voice prints)", len(CHECKED) == 2)
    FP["v"] = "prints-2"
    choose("mix_ashby")
    check("new voice prints, new check", len(CHECKED) == 3)


def t_a_voice_that_sounds_like_the_owner_is_never_used():
    reset("v1", "ready")
    OWNER["ok"] = False
    c, o = choose("mix_ashby")
    check("refused in plain words about a built-in voice (not the recording wording), and "
          "nothing was saved",
          c == 400 and o["error"] == "Ashby sounds too much like your own voice, so Jarvis "
          "will not use it." and not V._state_path().exists(), (c, o))
    view = V.speaker_view()
    check("it is not listed any more, and the note says why",
          not any(r["id"] == "mix_ashby" for r in view["choices"])
          and any(r["id"] == "mix_clara" for r in view["choices"])
          and "Ashby sounds too much like your own voice, so Jarvis will not use it."
          in view["note"],
          view)
    c, o = V.sample_voice({"voice": "mix_ashby"})
    check("Hear it refuses it like any unlisted voice", c == 400
          and o["error"] == "choose one of the listed voices", (c, o))
    # the owner already had it chosen when the prints changed
    reset("v1", "ready")
    choose("mix_clara")
    check("chosen and checked: it speaks", V.speaker() == 44 and V.speaker_name() == "mix_clara")
    CHECKED.clear()
    FP["v"] = "prints-2"
    OWNER["ok"] = False
    view = V.speaker_view()
    check("new prints: the saved voice is re-checked in the background, once, not on the GET "
          "itself - until then it still speaks",
          len(SPAWNED) == 1 and not CHECKED and V.speaker() == 44
          and view["choice"] == "mix_clara")
    V.speaker_view()
    check("asking again while it is queued does not queue another", len(SPAWNED) == 1)
    SPAWNED.pop()()
    check("the background check ran one sample", len(CHECKED) == 1)
    view = V.speaker_view()
    check("it failed: the pack's default speaks instead, the choice shows that, and the note "
          "says so in words",
          V.speaker() == 3 and V.speaker_name() == "af_heart" and view["choice"] == "af_heart"
          and view["note"].startswith("Clara sounds too much like your own voice, so Jarvis "
                                      "will not use it. American (female) - Heart speaks instead.")
          and not any(r["id"] == "mix_clara" for r in view["choices"]), view)
    check("the saved choice itself is kept as the owner made it (a new print may pass it again)",
          json.loads(V._state_path().read_text())["speaker"] == "mix_clara")
    FP["v"] = "prints-3"
    OWNER["ok"] = True
    V.speaker_view()
    SPAWNED.pop()()
    check("with the prints changed again and a pass, it speaks again",
          V.speaker() == 44 and V.speaker_name() == "mix_clara")


def t_not_being_able_to_check_is_not_a_pass():
    reset("v1", "ready")
    S._tts_cache = None
    c, o = choose("mix_ashby")
    check("no engine to make the sample: 503 in words, nothing saved, not kept as a verdict",
          c == 503 and "no built-in voice" in o["error"] and not V._state_path().exists()
          and not V._BLEND_CHECKS and not CHECKED, (c, o))
    reset("v1", "ready")

    def boom(samples, margin=None):
        raise RuntimeError("secret detail")
    V.owner_check = boom
    c, o = choose("mix_ashby")
    check("the check itself failing: 503, the exception's name and never its message",
          c == 503 and "RuntimeError" in o["error"] and "secret" not in o["error"]
          and not V._state_path().exists(), (c, o))
    reset("v1", "ready")
    V.owner_check = lambda samples, margin=None: {
        "ok": False, "refused": "no_voice_check",
        "why": "the voice check (jarvis_voice.py) is not installed on this PC"}
    c, o = choose("mix_clara")
    check("no voice check to compare with: refused, in words about the blend - not a pass",
          c == 400 and o["error"] == "Clara could not be checked against your voice print, "
          "so Jarvis will not use it yet." and not V._state_path().exists(), (c, o))
    reset("v1", "ready")
    with V._TRY_LOCK:
        c, o = choose("mix_ashby")
    check("one sound at a time: a second is refused at once, in words", c == 429
          and o["ok"] is False and not CHECKED, (c, o))
    reset("v1", "ready")
    src = (HERE / "jarvis_voices.py").read_text(encoding="utf-8")
    body = src[src.index("def blend_check("):src.index("def _recheck_saved_blend(")]
    check("the check reads no file, sends nothing anywhere and writes nothing to disk",
          "open(" not in body and "write" not in body and "urllib" not in body
          and "socket" not in body)


# ------------------------------------------------------------- speaking with them --

def t_they_speak_with_their_number_accent_and_pace():
    reset("v1", "ready")
    choose("mix_ashby")
    S._tts_cache.calls.clear()
    sid, speed, semis = S.tts_voice()
    check("Ashby: number 53, the owner's normal speed times 0.95, no pitch change",
          (sid, speed, semis) == (53, 0.95, 0.0), (sid, speed, semis))
    check("the same numbers through the three other doors jarvis_speech has",
          S.tts_speaker() == 53 and abs(S.tts_speed() - 0.95) < 1e-9 and S.tts_pitch() == 0.0)
    got = S.kokoro_speak(S._tts_cache, "Good evening.", sid, speed, semis)
    check("spoken as British English at that pace with that number",
          got is not None and S._tts_cache.calls[-1] == (53, 0.95, "en-gb-x-rp"),
          S._tts_cache.calls)
    check("the crisis-plain voice (no face) is Ashby at his pace too",
          S.tts_voice(plain=True) == (53, 0.95, 0.0), S.tts_voice(plain=True))
    V.set_speed({"speed": "faster"})
    check("the owner's own speed still applies on top: faster x 0.95",
          abs(S.tts_voice()[1] - 1.15 * 0.95) < 1e-9 and abs(V.speaker_speed() - 1.15 * 0.95) < 1e-9)
    V.set_speed({"speed": "slower"})
    check("... and slower x 0.95", abs(S.tts_voice()[1] - 0.85 * 0.95) < 1e-9)
    check("the one-moment clip's key changes with the voice (it is built from these numbers)",
          S.tts_voice()[:2] == (53, 0.85 * 0.95))
    choose("mix_clara")
    V.set_speed({"speed": "normal"})
    check("Clara: number 44, normal pace, British English",
          S.tts_voice() == (44, 1.0, 0.0) and V.accent_lang(44) == K.BRITISH_LANG
          and V.accent_lang(53) == K.BRITISH_LANG and V.accent_lang(3) is None)
    V.set_speaker({"speaker": "af_heart"})
    check("and back to Heart: number 3, normal pace, American English",
          S.tts_voice() == (3, 1.0, 0.0) and V.accent_lang(3) is None)
    V.set_speed({"speed": "slower"})
    check("a pace of 0.85 is still just the owner's for every other voice",
          abs(S.tts_voice()[1] - 0.85) < 1e-9)


def t_hear_it_works_on_them():
    reset("v1", "ready")
    c, wav = V.sample_voice({"voice": "mix_ashby"})
    check("Hear it: a WAV", c == 200 and wav[:4] == b"RIFF", (c, wav if c != 200 else ""))
    check("it was checked first (once) and then spoken - both at Ashby's pace, British",
          len(CHECKED) == 1
          and S._tts_cache.calls == [(53, 0.95, "en-gb-x-rp"), (53, 0.95, "en-gb-x-rp")],
          S._tts_cache.calls)
    check("it changed nothing: no state file, no card, no event",
          not V._state_path().exists() and not CARDS and not EVENTS)
    n = len(S._tts_cache.calls)
    c2, wav2 = V.sample_voice({"voice": "mix_ashby"})
    check("the second time is instant (kept in memory) and is not checked again",
          c2 == 200 and wav2 == wav and len(S._tts_cache.calls) == n and len(CHECKED) == 1)
    V.set_speed({"speed": "faster"})
    S._tts_cache.calls.clear()
    V.sample_voice({"voice": "mix_ashby"})
    check("another speaking speed is another sample: faster x 0.95",
          abs(S._tts_cache.calls[-1][1] - 1.15 * 0.95) < 1e-9, S._tts_cache.calls)
    S._tts_cache.calls.clear()
    c, wav = V.sample_voice({"voice": "mix_clara"})
    check("Clara: 44, normal pace, British", c == 200
          and S._tts_cache.calls[-1] == (44, 1.15, "en-gb-x-rp"), S._tts_cache.calls)
    src = (HERE / "jarvis_voices.py").read_text(encoding="utf-8")
    body = src[src.index("def _sample_voice("):src.index("def handle_audio(")]
    import re
    check("the sample's own code still never touches a recording, a print or the second card",
          not re.search(r"load_voice|clip\.wav|(?<!\w)speak\(|processor_generate|_F5|owner_check|"
                        r"PROFILE", body))


# ------------------------------------------------------------- the animals --

def t_no_animal_can_use_either():
    reset("v1", "ready")
    fv = V.face_voice_view()
    check("the animals' voice list has neither",
          not any(r["id"] in K.MIX for r in fv["animal_choices"]["voices"])
          and [r["id"] for r in fv["animal_choices"]["voices"]] == list(K.V1_PICK))
    for vid in K.MIX_IDS:
        c, o = V.set_face_animal({"face": "redpanda", "speaker": vid, "semitones": 0.0,
                                  "pace": "normal"})
        check(f"an animal cannot be given {vid}: 400", c == 400
              and o["error"] == "choose one of the listed voices", (c, o))
    V._write_state(face_animals={"redpanda": {"speaker": "mix_ashby", "semitones": 1.0,
                                              "pace": "normal"}})
    check("a saved animal choice of one is no choice at all (the animal keeps its own voice)",
          V.animal_voice("redpanda")["speaker"] == "af_bella"
          and V._read_state()["face_animals"] == {})
    V._write_state(face_voice=True, face_answers={"redpanda": "use"})
    (Path(V._config_dir()) / "appearance.json").write_text(json.dumps({"face": "redpanda"}))
    check("the panda speaks as Bella (number 1) whatever the copy holds; Ashby is not its voice",
          V.builtin_voice()[0] == K.V1_NAMES.index("af_bella"))
    check("an animal's saved voice is read against the pack's own table, never the copy's",
          all(K.sid_of(K.V1, f["speaker"]) == K.sid_of(K.V1MIX, f["speaker"])
              for f in V.FACE_VOICES.values()))


def t_a_saved_choice_that_cannot_be_spoken_is_never_a_wrong_voice():
    reset("v1", "none")
    V._write_state(speaker="mix_ashby")
    view = V.speaker_view()
    check("chose Ashby, not made yet: the default speaks, and the note says it is not made yet",
          V.speaker() == 3 and view["choice"] == "af_heart"
          and "You chose Ashby (made for Jarvis), which is not made yet" in view["note"]
          and view["note"].endswith(K.BLENDS_TO_MAKE), view)
    check("... it does NOT speak the pack's own slot 53 (Spanish Santa)",
          S.tts_voice()[0] == 3)
    reset("v1", "ready", engine_loaded="plain")
    V._write_state(speaker="mix_ashby")
    view = V.speaker_view()
    check("chose Ashby, made while Jarvis runs: the default speaks until the restart, and the "
          "note says Jarvis has not loaded it yet (not that it is not made)",
          V.speaker() == 3 and "which Jarvis has not loaded yet" in view["note"]
          and view["note"].endswith(K.BLENDS_RESTART), view)
    reset("v019")
    V._write_state(speaker="mix_clara")
    view = V.speaker_view()
    check("chose Clara, the old pack: the default speaks and the note says newer voice pack",
          V.speaker() == 0 and "needs the newer voice pack" in view["note"], view)
    reset("v1", "ready")
    V._write_state(speaker="mix_ashby")
    check("made and loaded: it is Ashby, and the saved name is the one in the file",
          V.speaker() == 53 and json.loads(V._state_path().read_text())["speaker"] == "mix_ashby")
    reset("v1", "ready")
    V._write_state(speaker="em_santa")
    check("the pack's own slot name is not a voice in the copy (nobody can pick Spanish Santa)",
          V.speaker_name() == "af_heart" and V.speaker() == 3)


def t_the_migration_and_old_numbers_are_untouched():
    reset("v1", "ready")
    V._write_state(speaker="9")
    moved = V.migrate_saved_choices()
    check("an old number still becomes its old name (George), on the copy too",
          moved == [("built-in voice", "9", "bm_george")] and V.speaker() == 26)
    CFG["tts_speaker_id"] = 9
    V._write_state(speaker=None)
    check("[voice] tts_speaker_id = 9 is still George on the copy",
          V.speaker_name() == "bm_george" and V.speaker() == 26)


# ------------------------------------------------------------- the real pack --

def t_the_real_pack_if_it_is_here():
    d = os.environ.get("JARVIS_KOKORO_V1_DIR")
    try:
        import sherpa_onnx
    except Exception:
        sherpa_onnx = None
    if not d or sherpa_onnx is None:
        print("skip  set JARVIS_KOKORO_V1_DIR to an unpacked kokoro-multi-lang-v1_0 folder (and "
              "install sherpa-onnx) to build the real blend file and speak with both blends")
        return
    d = Path(d)
    K.BLEND_SHA256, K.V1_VOICES_SHA256 = _K_PINS
    check("the real pack's voices.bin is the pinned one", sha(d / "voices.bin") == _K_PINS[1])
    work = Path(tempfile.mkdtemp(prefix="real-", dir=TMP))
    os.symlink(d / "voices.bin", work / "voices.bin")
    ok, words = K.build_blends(str(work))
    check("built from the real pack: the result is the pinned file, byte for byte",
          ok and sha(work / K.BLEND_FILE) == _K_PINS[0], words)
    check("the real pack's file is untouched", sha(d / "voices.bin") == _K_PINS[1])

    def make(voices):
        k = sherpa_onnx.OfflineTtsKokoroModelConfig(
            model=str(d / "model.onnx"), voices=str(voices), tokens=str(d / "tokens.txt"),
            lexicon="", data_dir=str(d / "espeak-ng-data"), dict_dir="", lang="en-us")
        return sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(kokoro=k, num_threads=4)))
    eng = make(work / K.BLEND_FILE)
    check("sherpa-onnx loads the copy: still 54 speakers", eng.num_speakers == 54)
    text = "Good evening. I have looked over your calendar, and the afternoon is quite clear."

    def say(name, speed=1.0):
        sid = K.sid_of(K.V1MIX, name)
        cfg = sherpa_onnx.GenerationConfig()
        cfg.sid, cfg.speed = sid, speed
        cfg.extra = {"lang": K.BRITISH_LANG}
        a = eng.generate(text, cfg)
        return np.asarray(a.samples, dtype=np.float32)

    def ltas(x, n=1024):
        w = np.hanning(n)
        fr = np.array([np.abs(np.fft.rfft(x[i:i + n] * w)) for i in range(0, len(x) - n, n // 2)])
        db = 10 * np.log10(np.mean(fr ** 2, axis=0) + 1e-12)
        f = np.fft.rfftfreq(n, 1 / 24000)
        return db[(f > 100) & (f < 8000)]

    def gap(a, b):
        return float(np.sqrt(np.mean((ltas(a) - ltas(b)) ** 2)))
    out = {n: say(n) for n in ("mix_ashby", "mix_clara", "bm_george", "am_michael", "bf_emma",
                               "af_heart")}
    check("each blend speaks real sound (more than a second, not silence)",
          all(len(out[n]) > 24000 and np.abs(out[n]).max() > 0.05 for n in K.MIX))
    again = say("mix_ashby")
    noise = gap(again, out["mix_ashby"])
    check("speaking the same blend twice gives almost the same sound (the model is not bit for "
          "bit repeatable: the length differs by a few dozen samples, and the average spectrum "
          "by a third of a decibel or so) - that is the noise every difference below is "
          "measured against",
          abs(len(again) - len(out["mix_ashby"])) < 400 and noise < 0.6,
          (len(again), len(out["mix_ashby"]), noise))
    for blend, parents in (("mix_ashby", ("bm_george", "am_michael")),
                           ("mix_clara", ("bf_emma", "af_heart"))):
        for parent in parents:
            check(f"{blend} is not {parent}: different samples, and its average spectrum is more "
                  f"than a decibel away - at least twice the run-to-run noise",
                  not np.allclose(out[blend][:min(len(out[blend]), len(out[parent]))],
                                  out[parent][:min(len(out[blend]), len(out[parent]))], atol=1e-4)
                  and gap(out[blend], out[parent]) > max(1.0, 2 * noise),
                  (gap(out[blend], out[parent]), noise))
        gaps = [gap(out[blend], out[p]) for p in parents]
        check(f"{blend} sits between its parents, not beyond them (each parent is nearer than "
              f"the parents are to each other, plus a little)",
              all(g < gap(out[parents[0]], out[parents[1]]) + 1.0 for g in gaps), gaps)
    slow, norm = say("mix_ashby", 0.95), say("mix_ashby", 1.0)
    check("Ashby at 0.95 is a little longer than at 1.0 (about 5%)",
          1.02 < len(slow) / len(norm) < 1.10, len(slow) / len(norm))
    pack = make(d / "voices.bin")
    santa = np.asarray(pack.generate(text, sid=K.V1_NAMES.index("em_santa")).samples)
    check("the pack's own voices.bin still has Santa in that slot (the blend is only in the copy)",
          not np.array_equal(santa[:len(out['mix_ashby'])], out["mix_ashby"][:len(santa)]))


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
        V._voices_file, V.owner_check = _ORIG["_voices_file"], _ORIG["owner_check"]
        V.prints_fingerprint, V._spawn = _ORIG["prints_fingerprint"], _ORIG["_spawn"]
        K.BLEND_SHA256, K.V1_VOICES_SHA256 = _K_PINS
        S._cfg = _S_CFG
        S.sherpa_onnx = _S_SHERPA
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed:", ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
