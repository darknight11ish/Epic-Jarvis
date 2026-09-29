"""jarvis_mouth.py - the animals' mouths, timed by Jarvis's own voice engine.

NEW MODULE, shipped whole (like jarvis_speech.py). The owner's choice of
2026-09-28: "Build it" - take the timing of each speech sound from Kokoro,
the voice that speaks, instead of guessing it from the sound afterwards.

IN PLAIN WORDS. Kokoro, before it makes any sound, decides how long each
speech sound ("m", "oo", a pause) will last. sherpa-onnx, the program that
runs Kokoro here, never hands those numbers out. So this file keeps a small
copy of just the part of Kokoro's model that decides the lengths
(`model.durations.onnx`, made once on the PC by `--prepare`; the voice model
itself is never changed), asks it the same question sherpa-onnx asks, and
turns the answer into mouth shapes: shut for m, b and p, lip-bite for f and
v, rounded for "oo" and "w" (starting a little early, as real lips do),
spread for "ee", open wide for "ah". Those shapes travel inside the WAV that
/api/voice/say already returns, as one extra labelled block after the sound
(a RIFF chunk called "jmth"); both apps read it. A player that does not
know it plays the sound exactly as before.

NOTHING LEAVES THE PC (rule 1): the text is already here to be spoken, the
timing is worked out here, and the shapes go only in the reply to the app
that asked for the sound.

IT CAN ONLY EVER ADD. Any doubt - the durations file missing, the words
worked out differently from sherpa-onnx's (checked on every sentence: the
predicted length must equal the real sound's length to the sample), too slow,
any error at all - and the WAV has no "jmth" block, and the apps work the
mouth out from the sound, exactly as they did before this file existed.
Nothing here can stop Jarvis speaking or make it speak later than a small,
measured wait (MOUTH_WAIT_S).

KOKORO v1.0 TOO (owner, 2026-09-29: "Build exact timing"). Kokoro v1.0's
model hands out the same numbers as a second output of its own graph (the
lengths, after the same Round -> Clip -> Cast, then a Squeeze) - so the one-time
step slices that out exactly as it does for v0.19, from the ONE pinned model
file (jarvis_kokoro.V1_MODEL) and no other. What differs is the words -> sounds
step: sherpa-onnx reads v1.0 text with its own front end (KokoroMultiLangLexicon),
which changes ":" to ",", folds white space, and joins short sentences into the
one before - copied below (multilang_pieces()) and, like everything here,
proved on every sentence by the length check.

HOW IT FITS (docs/LIPSYNC.md, "Mouths from Kokoro's own timing"):

  1. words -> speech sounds: espeak-ng, called the way piper-phonemize (the
     code inside sherpa-onnx) calls it, through the espeak-ng library that
     the espeakng-loader package ships (it has Windows builds; piper-phonemize
     has none). That library lacks piper's one extra call (which says how a
     clause ended), so the clause ending is read from the text itself -
     _clause_end(); checked equal to piper-phonemize on 48,416 of 48,424
     lines (the 8 are odd code fragments, which the length check catches).
  2. sounds -> Kokoro's own token numbers (tokens.txt), split and padded the
     way sherpa-onnx does (max 510 per piece, a space after every ".").
  3. the durations model (onnxruntime) -> frames per sound; 1 frame = 600
     samples = 25 ms at 24 kHz.
  4. sherpa-onnx is asked for the sound with its pause-shortening switched
     off, one piece per sentence, and this file shortens the pauses itself
     with an exact copy of sherpa-onnx's own ScaleSilence (scale_silence()),
     so it knows where every sample went. The sound is byte-for-byte what
     sherpa-onnx would have made on its own (measured: docs/LIPSYNC.md).
  5. times / the animal's pitch factor f = 2^(semitones/12) (jarvis_speech.
     pitch_up plays the sound faster, or for a deeper voice slower, by f) ->
     seconds in the final clip.
  6. sounds -> mouth shapes at 100 frames a second (build_track()).
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import math
import os
import re
import struct
import sys
import threading
import time
import unicodedata
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

try:
    import numpy as np
except Exception:  # pragma: no cover - numpy is a requirement
    np = None  # type: ignore

# --------------------------------------------------------------------------
#   The numbers
# --------------------------------------------------------------------------

FPS = 100                     #: frames a second - lipsync.js's FPS
KOKORO_FRAME = 600            #: samples per Kokoro duration frame (25 ms at 24 kHz)
#: Kokoro's sound runs AHEAD of its own plan: each speech sound is heard
#: about 50-60 ms before the frames its durations give it (measured on the
#: raw sound, before any pause shortening or pitch change, and the same at
#: speed 1.0 and 0.8 - so a fixed number of Kokoro frames, not a share of
#: each sound's length: hiss of s/sh/f/th a median 60 ms early, speech
#: edges 25-50 ms, onsets after a pause 40 ms, stop releases 70 ms; the
#: mouth corpus, 2026-09-28, independently of the fallback tester's -60 ms
#: over 220 fricatives). So every planned time moves this much earlier,
#: two Kokoro frames - slightly under the measured lead, so the mouth is
#: never pulled ahead of the sound by this correction. The clip's length,
#: and the sample-exact check, are untouched.
SOUND_LEAD = 2 * KOKORO_FRAME  #: samples of the raw sound (50 ms at 24 kHz)
DURATION_NODE = "/Cast_output_0"  #: Kokoro v0.19's per-sound durations (after Round -> Clip)
DURATIONS_FILE = "model.durations.onnx"
#: Kokoro v1.0 declares its lengths as a graph output of its own (its second,
#: int64: Squeeze <- Cast <- Clip <- Round) instead of an inner node with a
#: fixed name; prepare() finds it by that shape, never by its auto-made name.
SHAPE_ONLY_OPS = ("Squeeze", "Reshape", "Identity", "Flatten")
CHUNK_ID = b"jmth"
PAYLOAD_HEAD = "v1;src=kokoro;"
#: How long say() may wait, after the sound is ready, for the timing still
#: being worked out on its own thread. Measured: the timing takes about a
#: twentieth of the time the sound takes, so this is almost never reached;
#: when it is, that sentence simply has no "jmth" block.
MOUTH_WAIT_S = 0.25
#: The timing model's own threads. One is plenty (about 0.1 s a sentence
#: here) and leaves the processor to the voice itself.
ORT_THREADS = 1

#: How the mouth moves - every tuning number in one table. Seconds for
#: times. "Reach" numbers are how far before (ant, anticipation) and after
#: (car, carry-over) a sound's own stretch its shape still pulls on the
#: mouth: a smooth blend of neighbouring shapes (Cohen & Massaro's
#: "dominance" model of coarticulation), not a jump from one to the next.
K = {
    # Dominance: weight inside a sound's stretch (alpha), reach before/after.
    "vowel_alpha": 4.0, "vowel_open_reach": 0.035, "vowel_lip_reach": 0.06,
    "round_alpha": 8.0, "round_ant": 0.075, "round_car": 0.05,   # oo, oh, w, sh
    "spread_ant": 0.05, "spread_car": 0.045,
    "cons_alpha": 2.0, "cons_reach": 0.025,
    "rest_alpha": 12.0, "rest_reach": 0.03,
    # A weak pull towards a neutral mouth everywhere (open 0, lips relaxed),
    # so nothing is held for long once the sounds pulling on it are gone.
    "prior_open": 0.05, "prior_lips": 0.35,
    # m, b, p: shut for the whole sound, closing from bil_in before it and
    # opening again over bil_out after. A sound the model gave no time at
    # all still shuts for bil_min.
    "bil_in": 0.05, "bil_out": 0.05, "bil_min": 0.03,
    # f, v: the lower lip tucked under the top teeth - barely open, spread.
    "lab_open": 0.1, "lab_in": 0.04, "lab_out": 0.05,
    # Stress: how far a vowel opens with no stress / secondary / primary.
    "stress": (0.82, 0.92, 1.0),
    # Loudness (the clip's own sound, per frame): the quietest speech opens
    # loud_min of the shape's opening, the loudest all of it.
    "loud_min": 0.5, "loud_pow": 0.7, "loud_range_db": 30.0, "loud_ms": 20.0,
    # Silence in the clip (as lipsync.js: >= 80 ms below its gate) closes
    # the mouth, fully from 40 ms in, starting to open 30 ms before speech.
    "gap_frames": 8, "gap_close_frames": 4,
    # Final light smoothing (forward-backward one-pole), and the output gain.
    "smooth_ms": 12.0, "open_gain": 1.0,
}

# Mouth shapes: (open, wide, round). Vowels by openness: "ah" > "eh" > "ee".
_V = {
    "ɑ": (0.95, 0.10, 0.0), "a": (0.90, 0.15, 0.0), "æ": (0.80, 0.45, 0.0),
    "ʌ": (0.65, 0.10, 0.0), "ɐ": (0.55, 0.10, 0.0), "ɒ": (0.80, 0.0, 0.45),
    "ɔ": (0.70, 0.0, 0.60), "o": (0.55, 0.0, 0.85), "ɛ": (0.62, 0.45, 0.0),
    "e": (0.50, 0.55, 0.0), "ɜ": (0.40, 0.05, 0.30), "ɚ": (0.30, 0.0, 0.35),
    "ə": (0.35, 0.10, 0.0), "ɪ": (0.30, 0.60, 0.0), "ᵻ": (0.28, 0.45, 0.0),
    "i": (0.22, 0.90, 0.0), "ʊ": (0.30, 0.0, 0.75), "u": (0.22, 0.0, 1.0),
    "ɵ": (0.35, 0.0, 0.5), "ø": (0.3, 0.0, 0.7), "y": (0.22, 0.2, 0.8),
    "ɯ": (0.25, 0.3, 0.0), "ɨ": (0.25, 0.4, 0.0), "œ": (0.5, 0.0, 0.5),
    # Kokoro's other vowels. en-us never emits them, but espeak-ng's other
    # English voices do if [voice] tts_lang is changed: en-gb-scotland says
    # every "oo" as ʉ, which used to get no rounding at all (the mouth
    # corpus, backend/test_mouth_corpus.py).
    "ʉ": (0.22, 0.0, 0.9), "ɝ": (0.40, 0.05, 0.30), "ɘ": (0.35, 0.15, 0.0),
    "ɞ": (0.50, 0.0, 0.50), "ɤ": (0.40, 0.2, 0.0), "ʏ": (0.25, 0.1, 0.7),
    "ɶ": (0.80, 0.0, 0.45),
}
# Consonants: class, and the shape its class pulls towards. None = this
# sound does not pull that channel at all (the lips borrow the neighbours').
#   BIL m b p         lips shut (open forced to 0 for the whole sound)
#   LAB f v           lip-bite
#   DEN θ ð           tongue between the teeth
#   SIB s z           teeth together, lips spread a little
#   PAL ʃ ʒ (and the second half of tʃ, dʒ)  lips pushed out, rounded
#   ALV t d n l ɾ     tongue behind the teeth: jaw a little closed
#   VEL k ɡ ŋ         back of the tongue
#   R   ɹ             American r: slightly rounded
#   W   w             rounded, nearly shut
#   J   j             "y": spread
_C = {
    "m": "BIL", "b": "BIL", "p": "BIL", "ɓ": "BIL", "ʙ": "BIL", "ɸ": "LAB",
    "β": "LAB", "f": "LAB", "v": "LAB", "ʋ": "LAB", "ɱ": "BIL",
    "θ": "DEN", "ð": "DEN",
    "s": "SIB", "z": "SIB", "ɕ": "SIB", "ʑ": "SIB", "ç": "SIB", "x": "VEL",
    "ʃ": "PAL", "ʒ": "PAL", "ʂ": "PAL", "ʐ": "PAL", "ʧ": "PAL", "ʤ": "PAL",
    "t": "ALV", "d": "ALV", "n": "ALV", "l": "ALV", "ɾ": "ALV", "ɫ": "ALV",
    "ʈ": "ALV", "ɖ": "ALV", "ɳ": "ALV", "ɭ": "ALV", "ɬ": "ALV", "ɲ": "ALV",
    "ʎ": "ALV", "c": "VEL", "ɟ": "VEL",
    "k": "VEL", "ɡ": "VEL", "g": "VEL", "ŋ": "VEL", "q": "VEL", "ɢ": "VEL",
    "ɴ": "VEL", "χ": "VEL", "ɣ": "VEL", "ʁ": "R", "ʀ": "R",
    "ɹ": "R", "r": "R", "ɻ": "R", "ɽ": "R",
    "w": "W", "ʍ": "W", "ɥ": "W", "ɰ": "W",
    "j": "J", "ʝ": "J",
    # the rest of Kokoro's consonants (implosives, clicks, ...), by place
    "ʘ": "BIL", "ⱱ": "LAB", "ɗ": "ALV", "ɮ": "ALV", "ɺ": "ALV", "ǀ": "ALV",
    "ǁ": "ALV", "ǂ": "ALV", "ǃ": "ALV", "ʄ": "VEL", "ɠ": "VEL", "ʛ": "VEL",
    "ʟ": "VEL", "ɧ": "PAL",
}
_CLASS = {
    #      open  wide  round   (None: does not pull that channel)
    "BIL": (0.0, None, None),
    "LAB": (0.10, 0.50, 0.0),
    "DEN": (0.20, 0.35, 0.0),
    "SIB": (0.12, 0.50, None),
    "PAL": (0.18, 0.0, 0.65),
    "ALV": (0.22, None, None),
    "VEL": (0.28, None, None),
    "R":   (0.22, 0.0, 0.45),
    "W":   (0.10, 0.0, 1.0),
    "J":   (0.20, 0.70, 0.0),
    "REST": (0.0, 0.0, 0.0),
}
#: Marks that are not sounds: stress goes to the vowel after it, length and
#: the syllabic mark to the sound before. "h" and the glottal stop take the
#: shape of what is around them (no pull of their own).
_STRESS = {"ˈ": 2, "ˌ": 1}
_TO_PREVIOUS = {"ː", "ˑ", "\u0329", "ʰ", "ʲ", "ʷ", "ˠ", "ˤ", "˞", "ʼ", "ʴ", "ʱ"}
_TRANSPARENT = {" ", "h", "ɦ", "ʔ", "ħ", "ʕ", "ʡ", "ʢ", "ʜ", "'", "-"}
_REST = set(";:,.!?¡¿—…\"«»“”()$")  # pads and punctuation: a pause


# --------------------------------------------------------------------------
#   Where things are
# --------------------------------------------------------------------------

def _speech():
    try:
        import jarvis_speech
        return jarvis_speech
    except Exception:
        return None


def tts_paths() -> dict:
    """The Kokoro files jarvis_speech uses (its [voice] settings), or the
    default place under the config folder."""
    S = _speech()
    if S is not None and hasattr(S, "_sherpa_tts_paths"):
        try:
            return dict(S._sherpa_tts_paths())
        except Exception:
            pass
    base = Path(os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
                or (Path.home() / ".openjarvis")) / "voice-models" / "tts"
    return {"model": str(base / "model.onnx"), "voices": str(base / "voices.bin"),
            "tokens": str(base / "tokens.txt"), "data_dir": str(base / "espeak-ng-data"),
            "lexicon": "", "dict_dir": ""}


def durations_path(paths: Optional[dict] = None) -> Path:
    """model.durations.onnx, beside the voice model it was made from."""
    paths = paths or tts_paths()
    return Path(paths["model"]).with_name(DURATIONS_FILE)


PREPARE_LINE = ('Push-Location "C:\\Users\\pcadmin\\Documents\\Claude\\Open jarvis files\\'
                'Desktop program"; py -3 -m pip install onnx espeakng-loader; '
                'py -3 .\\jarvis_mouth.py --prepare; Pop-Location')
HOW_TO_PREPARE = ("One-time step not done yet: backend\\README.md, \"Mouths that match "
                  "the words\", has the one PowerShell line. It makes a small copy of the "
                  "timing part of the voice model (model.durations.onnx, next to model.onnx); "
                  "the voice itself is not changed. Until then the apps work the mouth out "
                  "from the sound, as before.")


# --------------------------------------------------------------------------
#   prepare(): the one-time step on the owner's PC
# --------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _duration_chain(g, producer, name: str, onnx_mod) -> bool:
    """`name` holds Kokoro's sound lengths: it is the output of Cast(int64)
    <- Clip <- Round, optionally seen through shape-only nodes (a Squeeze).
    Never raises."""
    hops = 0
    while name in producer and g.node[producer[name]].op_type in SHAPE_ONLY_OPS and hops < 4:
        n = g.node[producer[name]]
        if not n.input:
            return False
        name, hops = n.input[0], hops + 1
    cast = g.node[producer[name]] if name in producer else None
    if cast is None or cast.op_type != "Cast" or not cast.input or cast.input[0] not in producer:
        return False
    clip = g.node[producer[cast.input[0]]]
    if clip.op_type != "Clip" or not clip.input or clip.input[0] not in producer:
        return False
    rnd = g.node[producer[clip.input[0]]]
    to = next((a.i for a in cast.attribute if a.name == "to"), None)
    return rnd.op_type == "Round" and to == onnx_mod.TensorProto.INT64


def _duration_output(g, producer, onnx_mod) -> str:
    """The tensor that carries the sound lengths: v0.19's inner node
    DURATION_NODE, or - Kokoro v1.0 - a declared int64 graph output. Both
    are known by what computes them (Round -> Clip -> Cast(int64)), so a
    node that only happens to share v0.19's name (v1.0 has an unrelated
    "/Cast_output_0") is never taken. Raises ValueError, in plain words."""
    candidates = [DURATION_NODE] if DURATION_NODE in producer else []
    candidates += [o.name for o in g.output
                   if o.type.tensor_type.elem_type == onnx_mod.TensorProto.INT64]
    for name in candidates:
        if _duration_chain(g, producer, name, onnx_mod):
            return name
    raise ValueError("this voice model has no sound-lengths output computed as Round -> Clip -> "
                     "Cast(int64), so it is not the Kokoro v0.19 (kokoro-en-v0_19) or Kokoro "
                     "v1.0 (kokoro-multi-lang-v1_0) model this was made for; nothing was written")


def _duration_slice(model, onnx_mod):
    """The part of Kokoro's graph that computes the sound lengths, as a new
    model: every node the lengths depend on (walked backwards, including
    names used inside sub-graphs), the weights those nodes read, and the
    three inputs. Nothing is changed in the nodes themselves. Raises
    ValueError, in plain words, when this is not the model it expects."""
    helper = onnx_mod.helper
    g = model.graph
    producer = {}
    for i, n in enumerate(g.node):
        for o in n.output:
            producer[o] = i
    out_name = _duration_output(g, producer, onnx_mod)

    def outer_names(node) -> set:
        out = set()
        for a in node.attribute:
            graphs = [a.g] if a.type == onnx_mod.AttributeProto.GRAPH else (
                list(a.graphs) if a.type == onnx_mod.AttributeProto.GRAPHS else [])
            for sg in graphs:
                local = {x.name for x in sg.input} | {x.name for x in sg.initializer}
                for sn in sg.node:
                    local |= set(sn.output)
                for sn in sg.node:
                    out |= {x for x in sn.input if x and x not in local}
                    out |= outer_names(sn)
        return out

    keep, need, todo = set(), set(), [out_name]
    while todo:
        name = todo.pop()
        if name in need:
            continue
        need.add(name)
        i = producer.get(name)
        if i is None or i in keep:
            continue
        keep.add(i)
        node = g.node[i]
        todo.extend(x for x in node.input if x)
        todo.extend(outer_names(node))
    inputs = [x for x in g.input if x.name in need]
    if sorted(x.name for x in inputs) != ["speed", "style", "tokens"]:
        raise ValueError("the sound lengths do not depend on exactly tokens, style and "
                         f"speed here ({[x.name for x in inputs]}); nothing was written")
    graph = helper.make_graph([g.node[i] for i in sorted(keep)], "kokoro_durations", inputs,
                              [helper.make_tensor_value_info(out_name,
                                                             onnx_mod.TensorProto.INT64, None)],
                              initializer=[x for x in g.initializer if x.name in need])
    out = helper.make_model(graph, opset_imports=list(model.opset_import),
                            ir_version=model.ir_version)
    out.producer_name = "jarvis_mouth"
    for p in model.metadata_props:
        out.metadata_props.add(key=p.key, value=p.value)
    return out


def _v1_pin() -> Optional[dict]:
    """jarvis_kokoro.V1_MODEL (the one place the v1.0 model file is pinned),
    or None when jarvis_kokoro.py is not beside this file."""
    try:
        import jarvis_kokoro
        pin = dict(jarvis_kokoro.V1_MODEL)
        return pin if pin.get("sha256") and pin.get("bytes") else None
    except Exception:
        return None


def _model_version(meta: dict) -> int:
    """Kokoro's own `version` note: absent in v0.19 (so 1), "2" in v1.0."""
    try:
        return int(str(meta.get("version", "1")).strip() or 1)
    except ValueError:
        return 1


def prepare(paths: Optional[dict] = None, force: bool = False,
            say: Callable[[str], None] = print) -> dict:
    """Make model.durations.onnx beside the Kokoro model, once. Idempotent:
    a copy already made from this same model is left alone. The model
    sherpa-onnx speaks with is only READ. Returns {"ok", "did", "path",
    "why"} and says what it did in plain words through `say`. Kokoro v1.0
    is made only from the one pinned file (jarvis_kokoro.V1_MODEL): any
    other model.onnx in a v1.0 folder gets no copy, and the apps keep
    working the mouth out from the sound."""
    paths = paths or tts_paths()
    src, dst = Path(paths["model"]), durations_path(paths)
    out = {"ok": False, "did": "nothing", "path": str(dst), "why": ""}
    if not src.is_file():
        out["why"] = (f"There is no Kokoro voice model at {src} yet. Install the voice first "
                      "(backend\\README.md, \"Install the voice models\"), then run this again.")
        say(out["why"])
        return out
    try:
        import onnx
    except Exception:
        out["why"] = ("The onnx package is not installed, and this one-time step needs it: "
                      "py -3 -m pip install onnx")
        say(out["why"])
        return out
    size = src.stat().st_size
    if dst.is_file() and not force:
        meta = _meta_of(dst)
        if meta.get("jarvis_source_size") == str(size):
            out.update(ok=True, did="already done",
                       why=f"Already done: {dst} was made from this voice model. Nothing changed.")
            say(out["why"])
            return out
    t0 = time.monotonic()
    say(f"Reading {src} (about {size / 1e6:.0f} MB; it is not changed)...")
    try:
        model = onnx.load(str(src))
        sha = _sha256(src)
        v1 = _model_version({p.key: p.value for p in model.metadata_props}) >= 2
        if v1:
            pin = _v1_pin()
            if pin is None:
                raise ValueError("jarvis_kokoro.py (which pins the Kokoro v1.0 model) is not in "
                                 "the backend folder, so this cannot check the model is the "
                                 "right one - run the apply-patches step first")
            if size != int(pin["bytes"]) or sha != str(pin["sha256"]).lower():
                raise ValueError(
                    "this is not the Kokoro v1.0 model file Jarvis's install line puts there "
                    f"(its fingerprint starts {sha[:12]}, the expected one starts "
                    f"{str(pin['sha256'])[:12]}), so no timing was made from it. Run the "
                    "\"Upgrade the voice pack to Kokoro v1.0\" line in backend\\README.md "
                    "again, then this step")
        sub = _duration_slice(model, onnx)
        out_name = sub.graph.output[0].name
        sub.metadata_props.add(key="jarvis_source_size", value=str(size))
        sub.metadata_props.add(key="jarvis_source_sha256", value=sha)
        tmp = dst.with_name(dst.name + ".part")
        onnx.save(sub, str(tmp))
        del model
        _check_durations_model(tmp, paths)
        if v1:
            _check_against_model(tmp, src, out_name, paths)
        os.replace(tmp, dst)
    except Exception as exc:
        try:
            dst.with_name(dst.name + ".part").unlink()
        except OSError:
            pass
        out["why"] = f"Could not make it: {exc}. Nothing was changed."
        say(out["why"])
        return out
    reset()
    out.update(ok=True, did="made",
               why=(f"Done in {time.monotonic() - t0:.1f} s: wrote {dst} "
                    f"({dst.stat().st_size / 1e6:.0f} MB). The voice model itself was not "
                    "changed. Restart Jarvis and the animals' mouths follow Kokoro's own timing."))
    say(out["why"])
    return out


def _meta_of(path: Path) -> dict:
    """The durations model's own notes (metadata), read without loading it
    into onnxruntime when onnx is there; {} on any trouble."""
    try:
        import onnx
        m = onnx.load(str(path), load_external_data=False)
        return {p.key: p.value for p in m.metadata_props}
    except Exception:
        pass
    try:
        import onnxruntime as ort
        s = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        return dict(s.get_modelmeta().custom_metadata_map)
    except Exception:
        return {}


def _check_durations_model(path: Path, paths: dict) -> None:
    """Runs the new file once on "hello" so a broken copy is never kept."""
    import onnxruntime as ort
    s = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    style = _load_voices(paths["voices"], dict(s.get_modelmeta().custom_metadata_map))
    ids = [0, 50, 83, 54, 156, 57, 135, 0]
    d = s.run(None, {"tokens": np.array([ids], np.int64),
                     "style": style[0][len(ids) - 2][None, :],
                     "speed": np.array([1.0], np.float32)})[0]
    if np.asarray(d).reshape(-1).shape[0] != len(ids) or int(np.asarray(d).sum()) <= 0:
        raise ValueError("the copy did not give one length per sound")


def _check_against_model(copy: Path, source: Path, out_name: str, paths: dict) -> None:
    """Kokoro v1.0 only: the copy must give, for three real inputs, exactly
    what the voice model itself gives at the output the copy was cut at -
    the proof that the slice is the model's own sound lengths."""
    import onnxruntime as ort
    c = ort.InferenceSession(str(copy), providers=["CPUExecutionProvider"])
    f = ort.InferenceSession(str(source), providers=["CPUExecutionProvider"])
    style = _load_voices(paths["voices"], dict(c.get_modelmeta().custom_metadata_map))
    for ids, sid, speed in (([0, 50, 83, 54, 156, 57, 135, 0], 0, 1.0),
                            ([0, 50, 83, 54, 156, 57, 135, 4, 16, 50, 83, 0], 3, 0.85),
                            ([0] + [83, 54, 156, 57, 135] * 9 + [0], 26, 1.3)):
        feed = {"tokens": np.array([ids], np.int64),
                "style": style[min(sid, style.shape[0] - 1)][len(ids) - 2][None, :],
                "speed": np.array([speed], np.float32)}
        a = np.asarray(c.run(None, feed)[0]).reshape(-1)
        b = np.asarray(f.run([out_name], feed)[0]).reshape(-1)
        if a.shape != b.shape or not np.array_equal(a, b):
            raise ValueError("the copy does not give the voice model's own sound lengths")


# --------------------------------------------------------------------------
#   espeak-ng, the way piper-phonemize (inside sherpa-onnx) calls it
# --------------------------------------------------------------------------

_ESPEAK_LOCK = threading.Lock()
_ESPEAK = {"lib": None, "data": None, "voice": None, "why": ""}
ESPEAK_IPA = 0x02
ESPEAK_CHARS_UTF8 = 1
#: What piper-phonemize (inside sherpa-onnx) passes (espeakCHARS_AUTO):
#: UTF-8, with any invalid byte read as 8-bit Latin-1 instead.
ESPEAK_CHARS_AUTO = 0
#: The espeak-ng inside sherpa-onnx (and the piper-phonemize wheel) also
#: takes U+FFFD (the "unknown character" mark) for invalid and re-reads its
#: three bytes as Latin-1 - "i-umlaut, inverted question mark, one half" -
#: where the espeak-ng 1.52 that espeakng-loader ships reads nothing at all.
#: So it is spelled out that way before espeak-ng sees it. Found by the
#: mouth corpus (backend/test_mouth_corpus.py): those sentences came out
#: shorter than the sound and lost their mouth; measured since, sherpa-onnx
#: speaks "hello \ufffd." exactly as long as this predicts (a mark straight
#: after the U+FFFD still differs, and that sentence simply has no mouth).
_FFFD_AS_PIPER = "\u00ef\u00bf\u00bd"
AUDIO_OUTPUT_SYNCHRONOUS = 2
#: Without this, espeak-ng calls exit() when its data cannot be read - which
#: would end the whole Jarvis backend. With it, it returns an error instead.
ESPEAK_INIT_DONT_EXIT = 0x8000


def _espeak_lib():
    """(the espeak-ng library from espeakng-loader, or None, why)."""
    try:
        import espeakng_loader
    except Exception:
        return None, "the espeakng-loader package is not installed (py -3 -m pip install espeakng-loader)"
    try:
        path = espeakng_loader.get_library_path()
        if sys.platform == "win32":
            try:
                os.add_dll_directory(str(Path(path).parent))
            except Exception:
                pass
        lib = ctypes.CDLL(path)
        lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        lib.espeak_Initialize.restype = ctypes.c_int
        lib.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
        lib.espeak_SetVoiceByName.restype = ctypes.c_int
        lib.espeak_TextToPhonemes.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int,
                                              ctypes.c_int]
        lib.espeak_TextToPhonemes.restype = ctypes.c_char_p
        return lib, ""
    except Exception as exc:
        return None, f"the espeak-ng library could not be loaded ({type(exc).__name__})"


def _path_bytes(p: str) -> bytes:
    if sys.platform == "win32":
        try:
            return p.encode("mbcs")
        except Exception:
            pass
    return os.fsencode(p)


def _espeak_ready(data_dir: str, voice: str):
    """Initialised espeak-ng for (data_dir, voice), or None. Caller holds
    _ESPEAK_LOCK."""
    E = _ESPEAK
    if E["lib"] is None:
        lib, why = _espeak_lib()
        if lib is None:
            E["why"] = why
            return None
        E["lib"] = lib
    lib = E["lib"]
    if E["data"] != data_dir:
        if lib.espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 0, _path_bytes(data_dir),
                                 ESPEAK_INIT_DONT_EXIT) <= 0:
            E["why"] = f"espeak-ng could not read its data in {data_dir}"
            E["data"] = None
            return None
        E["data"], E["voice"] = data_dir, None
    if E["voice"] != voice:
        if lib.espeak_SetVoiceByName(voice.encode("ascii", "replace")) != 0:
            E["why"] = f"espeak-ng has no voice {voice!r}"
            return None
        E["voice"] = voice
    return lib


_CLOSERS = "\"'()[]{}`\u201c\u201d\u2018\u2019\u00ab\u00bb"
_ENDS = ".?!,:;\u2026\u2014\u2013"


def _alnum(ch: str) -> bool:
    """"A letter or digit" as the espeak-ng inside sherpa-onnx has it
    (ucd-tools: a letter, a letter-like number such as a Roman numeral,
    or 0-9). NOT other numbers: sherpa-onnx reads "\u00bd." and "\u00b2!" as
    clauses with no letter or digit, although newer espeak-ng (and the
    piper-phonemize wheel) count them - measured by speaking them. Symbols
    count only when Unicode calls them "Other_Alphabetic", which Python
    cannot ask: the circled and squared Latin letters are listed."""
    cat = unicodedata.category(ch)
    if cat[0] == "L" or cat == "Nl" or "0" <= ch <= "9":
        return True
    o = ord(ch)
    return cat == "So" and (0x24B6 <= o <= 0x24E9 or 0x1F130 <= o <= 0x1F149
                            or 0x1F150 <= o <= 0x1F169 or 0x1F170 <= o <= 0x1F189)


def _clause_end(chunk: str, more: bool, lead: str = "") -> str:
    """How espeak-ng ended the clause it just read, from the text it read
    (`chunk`; `more`: text follows; `lead`: the one character the previous
    call read past its own clause, which belongs to this one). piper-phonemize
    gets this from its own espeak-ng build (espeak_TextToPhonemesWithTerminator),
    which the standard library lacks. Returns ".", "?", "!", ",", ":", ";",
    "P" (a paragraph: a sentence ends, nothing is added) or "". Rules measured
    against piper-phonemize (docs/LIPSYNC.md): espeak reads one character
    past the clause; blank lines end a sentence with nothing added; closing
    quotes and brackets after the mark do not count; of a run of marks the
    first decides ("?!" is a question); two or more dots, or "\u2026", add
    nothing and do not end the sentence; a dash between spaces is ";"; and a
    mark in a clause with no letter or digit in it at all ("!", a thumbs-up
    emoji and ".", "\u00a9 \u00ae.") ends nothing unless a line break follows it
    (espeak-ng readclause.c, `any_alnum`: "no letters or digits yet, so
    probably not a sentence terminator") - found by the mouth corpus
    (backend/test_mouth_corpus.py)."""
    s = chunk[:-1] if (more and chunk) else chunk
    body = s.rstrip()
    after = s[len(body):].replace("\r", "")
    if after.count("\n") >= 2:
        return "P"
    t = body.rstrip(_CLOSERS + " \t")
    i = len(t)
    while i > 0 and t[i - 1] in _ENDS:
        i -= 1
    run = t[i:]
    if not run or run.startswith("..") or run[0] == "\u2026":
        return ""
    if "\n" not in after and not any(_alnum(c) for c in lead + t[:i]):
        return ""
    if run[0] in "\u2014\u2013":
        return ";"
    return run[0]


def phonemize(text: str, data_dir: str, voice: str = "en-us") -> Optional[List[str]]:
    """Speech sounds for `text`, one string per sentence, exactly as
    sherpa-onnx's piper-phonemize makes them for Kokoro v0.19 - or None.
    (Kokoro v1.0's front end calls the same routine on the text fixed by
    multilang_text(); see multilang_pieces().)"""
    # espeak-ng reads a C string: nothing after a NUL character exists for
    # it (or for sherpa-onnx), so nothing after one may count here either.
    raw = text.replace("\ufffd", _FFFD_AS_PIPER).encode("utf-8", "replace").split(b"\0", 1)[0]
    with _ESPEAK_LOCK:
        lib = _espeak_ready(data_dir, voice)
        if lib is None:
            return None
        buf = ctypes.create_string_buffer(raw)
        base = ctypes.addressof(buf)
        ptr = ctypes.c_void_p(base)
        sentences: List[List[str]] = []
        cur: Optional[List[str]] = None
        guard = 0
        lead = ""
        while ptr.value is not None:
            guard += 1
            if guard > len(raw) + 8:
                return None
            start = ptr.value
            ph = lib.espeak_TextToPhonemes(ctypes.byref(ptr), ESPEAK_CHARS_AUTO, ESPEAK_IPA)
            end = ptr.value
            if end is not None and not (start <= end <= base + len(raw)):
                return None
            chunk = raw[start - base:(end - base) if end is not None else len(raw)]
            phon = unicodedata.normalize("NFD", (ph or b"").decode("utf-8", "replace"))
            phon = re.sub(r"\([^)]*\)", "", phon)  # (lang) switch flags
            if cur is None:
                cur = []
                sentences.append(cur)
            cur.extend(phon)
            said = chunk.decode("utf-8", "replace")
            if phon:
                mark = _clause_end(said, end is not None, lead)
            else:
                mark = "P" if end is None else ""
            if mark in (".", "?", "!"):
                cur.append(mark)
                cur = None
            elif mark in (",", ":", ";"):
                cur.extend([mark, " "])
            elif mark == "P" or end is None:
                cur = None
            # the character read past this clause starts the next one
            lead = said[-1:] if end is not None else ""
    return ["".join(s) for s in sentences]


# --------------------------------------------------------------------------
#   Kokoro's tokens and the durations model
# --------------------------------------------------------------------------

def read_tokens(path: str) -> dict:
    """tokens.txt -> {sound: number}, read as sherpa-onnx reads it (a line
    with only a number is the space)."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) == 1:
                out[" "] = int(parts[0])
            elif len(parts) == 2 and len(parts[0]) == 1:
                out[parts[0]] = int(parts[1])
    return out


def token_pieces(sentences: Sequence[str], tokens: dict, max_len: int = 511):
    """[(ids, sounds)] per piece sherpa-onnx will speak: 0 at each end, a
    space token after every ".", unknown sounds dropped, and a sentence
    longer than max_len - 1 split (PiperPhonemesToIdsKokoroOrKitten)."""
    out = []
    space = tokens.get(" ")
    for s in sentences:
        ids, labels = [0], [""]
        for p in s:
            if p not in tokens:
                continue
            if len(ids) > max_len - 1:
                ids.append(0)
                labels.append("")
                out.append((ids, labels))
                ids, labels = [0], [""]
            ids.append(tokens[p])
            labels.append(p)
            if p == "." and space is not None:
                ids.append(space)
                labels.append(" ")
        ids.append(0)
        labels.append("")
        out.append((ids, labels))
    return out


#: KokoroMultiLangLexicon::ConvertTextToTokenIds, step one (sherpa-onnx
#: kokoro-multi-lang-lexicon.cc): these replacements, in this order, on the
#: text before anything else. A plain ":" becomes ",", and every run of
#: white space (std::regex's "\s": space, tab, line feeds, form feed) one
#: space - so a blank line no longer ends a sentence on v1.0.
_ML_REPLACE = (("\uff0c", ","), (":", ","), ("\u3001", ","), ("\uff1b", ";"), ("\uff1a", ":"),
               ("\u3002", "."), ("\uff1f", "?"), ("\uff01", "!"))
_ML_SPACES = re.compile(r"[ \t\n\v\f\r]+")
#: A run of Chinese characters is read from the pack's Chinese lexicon,
#: which is not copied here: such a sentence gets no timing.
_ML_CHINESE = re.compile("[\u4e00-\u9fff]")
#: What sherpa-onnx takes as a bare punctuation "sentence" (IsPunctuation):
#: text that is exactly one of these is spoken as [0, that sound, 0].
_ML_PUNCT = {";", ":", ",", ".", "!", "?", "\u2014", "\u2026", "\"", "(", ")", "\u201c", "\u201d"}


def multilang_text(text: str) -> str:
    """The text as Kokoro v1.0's front end (KokoroMultiLangLexicon) hands it
    to espeak-ng: see _ML_REPLACE."""
    for old, new in _ML_REPLACE:
        text = text.replace(old, new)
    return _ML_SPACES.sub(" ", text)


def join_short_pieces(pieces):
    """sherpa-onnx's Kokoro v1.0 front end joins a short sentence (at most
    10 sounds between the two 0 pads) onto the one before it when the two
    together stay under 50 tokens - or whatever the length when it is under
    3 sounds: the earlier piece's closing 0 becomes the short one's first
    sound and the rest follows, so they are spoken (and timed) as ONE piece.
    A longer sentence is a piece of its own. [(ids, sounds)] in and out."""
    out = []
    for ids, labels in pieces:
        ids, labels = list(ids), list(labels)
        if len(ids) > 10 + 2 or not out:
            out.append((ids, labels))
            continue
        back_ids, back_labels = out[-1]
        if len(back_ids) + len(ids) < 50 or len(ids) < 5:
            back_ids[-1], back_labels[-1] = ids[1], labels[1]
            back_ids.extend(ids[2:])
            back_labels.extend(labels[2:])
        else:
            out.append((ids, labels))
    return out


def multilang_pieces(text: str, tokens: dict, max_len: int, data_dir: str,
                     voice: str = "en-us"):
    """[(ids, sounds)] per piece Kokoro v1.0's sherpa-onnx will speak for
    `text` in espeak voice `voice` - or None (espeak-ng unavailable, or the
    text has Chinese in it). The same steps, in the same order, as
    KokoroMultiLangLexicon with the pack's lexicon left out (Jarvis passes
    `lang`, not a lexicon): fix the text (multilang_text), a bare
    punctuation mark stands alone, else espeak-ng's sentences as tokens
    (token_pieces), then the short ones joined on (join_short_pieces)."""
    fixed = multilang_text(text)
    if _ML_CHINESE.search(fixed):
        return None
    if fixed == "":
        return []
    if fixed in _ML_PUNCT:
        if fixed not in tokens:
            return None
        return [([0, tokens[fixed], 0], ["", fixed, ""])]
    sents = phonemize(fixed, data_dir, voice)
    if sents is None:
        return None
    return join_short_pieces(token_pieces(sents, tokens, max_len))


def _load_voices(path: str, meta: dict):
    dims = [int(x) for x in str(meta.get("style_dim", "511,1,256")).split(",")]
    per = dims[0] * dims[2]
    v = np.fromfile(path, dtype=np.float32)
    if per <= 0 or v.size % per:
        raise ValueError("voices.bin does not match the model")
    return v.reshape(-1, dims[0], dims[2])


class _Model:
    """The durations model, tokens and voice styles - loaded once."""

    def __init__(self, paths: dict):
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = ORT_THREADS
        so.inter_op_num_threads = 1
        self.path = durations_path(paths)
        self.session = ort.InferenceSession(str(self.path), so,
                                            providers=["CPUExecutionProvider"])
        meta = dict(self.session.get_modelmeta().custom_metadata_map)
        want = meta.get("jarvis_source_size")
        have = str(Path(paths["model"]).stat().st_size)
        if want is not None and want != have:
            raise ValueError("model.durations.onnx was made from a different voice model; "
                             "run the one-time step again")
        #: "piper": Kokoro v0.19's front end; "multilang": Kokoro v1.0's.
        self.frontend = "multilang" if _model_version(meta) >= 2 else "piper"
        if self.frontend == "multilang":
            # v1.0 timing is only ever paired with the one pinned model file:
            # made from it (its recorded fingerprint) and still the same size.
            pin = _v1_pin()
            if pin is None:
                raise ValueError("jarvis_kokoro.py (which pins the Kokoro v1.0 model) is missing")
            if (meta.get("jarvis_source_sha256") != str(pin["sha256"]).lower()
                    or meta.get("jarvis_source_size") != str(pin["bytes"])
                    or have != str(pin["bytes"])):
                raise ValueError("model.durations.onnx was not made from the pinned Kokoro v1.0 "
                                 "model; run the one-time step again")
        self.meta = meta
        self.sample_rate = int(meta.get("sample_rate", 24000))
        self.tokens = read_tokens(paths["tokens"])
        self.styles = _load_voices(paths["voices"], meta)
        self.max_len = self.styles.shape[1]
        self.data_dir = paths["data_dir"]

    def durations(self, ids: Sequence[int], sid: int, speed: float):
        sid = sid if 0 <= sid < self.styles.shape[0] else 0
        d = self.session.run(None, {
            "tokens": np.array([list(ids)], dtype=np.int64),
            "style": self.styles[sid][len(ids) - 2][None, :],
            "speed": np.array([speed], dtype=np.float32)})[0]
        return np.asarray(d, dtype=np.int64).reshape(-1)


_MODEL_LOCK = threading.Lock()
_MODEL = {"key": None, "model": None, "why": ""}


def _model(paths: dict) -> Optional[_Model]:
    key = (paths.get("model"), paths.get("voices"), paths.get("tokens"), paths.get("data_dir"))
    with _MODEL_LOCK:
        if _MODEL["key"] == key:
            return _MODEL["model"]
        _MODEL.update(key=key, model=None, why="")
        try:
            _MODEL["model"] = _Model(paths)
        except Exception as exc:
            _MODEL["why"] = f"{type(exc).__name__}: {exc}"[:300]
        return _MODEL["model"]


def reset() -> None:
    """Forget the loaded model (a new voice model, or a new copy)."""
    with _MODEL_LOCK:
        _MODEL.update(key=None, model=None, why="")


# --------------------------------------------------------------------------
#   sherpa-onnx's pause shortening, exactly (GeneratedAudio::ScaleSilence)
# --------------------------------------------------------------------------

class Remap:
    """Where a sample of the unshortened sound ended up after
    scale_silence(): pieces (start, end, removed_before, kept) per pause."""

    def __init__(self, cuts: Sequence[Tuple[int, int, int]] = ()):
        # (cut_start, cut_end, delta): samples [cut_start, cut_end) of the
        # original were dropped (delta > 0) or `-delta` zeros were added at
        # cut_start (delta < 0).
        self.cuts = list(cuts)

    def __call__(self, pos: float) -> float:
        shift = 0.0
        for a, b, delta in self.cuts:
            if delta >= 0:
                if pos >= b:
                    shift += delta
                elif pos > a:
                    shift += pos - a
            elif pos >= a:
                shift += delta
        return pos - shift


def scale_silence(samples, sample_rate: int, scale: float):
    """(shortened samples, Remap): a line-for-line copy of sherpa-onnx's
    GeneratedAudio::ScaleSilence (offline-tts.cc) - a stretch of at least
    0.2 s where every sample is within +-0.01 keeps only `scale` of its
    length (its start). float32 arithmetic where sherpa-onnx uses float."""
    x = np.asarray(samples, dtype=np.float32)
    n = len(x)
    if scale == 1:
        return x, Remap()
    s32 = np.float32(scale)
    if not (np.float32(0.01) <= s32 <= np.float32(10.0)):
        return x, Remap()
    threshold = int(sample_rate * 0.2)
    silent = np.abs(x.astype(np.float64)) <= 0.01
    if n == 0 or not silent.any():
        return x, Remap()
    edges = np.flatnonzero(np.diff(np.concatenate(([0], silent.view(np.int8), [0]))))
    starts, ends = edges[0::2], edges[1::2]
    intervals = []
    for a, b in zip(starts.tolist(), ends.tolist()):
        if b == n:
            if n - a > threshold:
                intervals.append((a, b))
        elif b - a >= threshold:
            intervals.append((a, b))
    if not intervals:
        return x, Remap()
    parts, cuts, i = [], [], 0
    for a, b in intervals:
        parts.append(x[i:a])
        i = b
        length = b - a
        keep = int(np.float32(length) * s32)
        if keep <= length:
            parts.append(x[a:a + keep])
            cuts.append((a + keep, b, length - keep))
        else:
            parts.append(x[a:b])
            parts.append(np.zeros(keep - length, dtype=np.float32))
            cuts.append((b, b, -(keep - length)))
    if i < n:
        parts.append(x[i:])
    return np.concatenate(parts), Remap(cuts)


def looks_raw(chunk) -> bool:
    """Kokoro's own output is whole 25 ms frames; a piece sherpa-onnx has
    already shortened almost never is. Used so a sherpa-onnx that ignored
    "do not shorten" is never shortened twice."""
    return len(chunk) % KOKORO_FRAME == 0


# --------------------------------------------------------------------------
#   The timing job (its own thread, while sherpa-onnx makes the sound)
# --------------------------------------------------------------------------

_STATS_LOCK = threading.Lock()
_STATS = {"made": 0, "skipped": 0, "last_why": "", "last_ms": None}


def _note(made: bool, why: str = "", ms: Optional[float] = None) -> None:
    with _STATS_LOCK:
        _STATS["made" if made else "skipped"] += 1
        _STATS["last_why"] = "" if made else str(why)[:200]
        if ms is not None:
            _STATS["last_ms"] = round(ms, 1)


class Job:
    """Works out one sentence's sounds and their lengths on a thread of its
    own. `.pieces`: [(labels, frames)] per piece, once done and fine."""

    def __init__(self, text: str, sid: int, speed: float, lang: str, paths: dict):
        self.text, self.sid, self.speed, self.lang, self.paths = text, sid, speed, lang, paths
        self.pieces = None
        self.why = ""
        self.ms = None
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, name="jarvis-mouth", daemon=True)

    def _run(self) -> None:
        t0 = time.monotonic()
        try:
            m = _model(self.paths)
            if m is None:
                self.why = "the timing model could not be loaded: " + (_MODEL["why"] or "?")
                return
            if m.frontend == "multilang":
                todo = multilang_pieces(self.text, m.tokens, m.max_len, m.data_dir, self.lang)
                if todo is None:
                    self.why = ("espeak-ng: " + _ESPEAK["why"]) if _ESPEAK["why"] else \
                        "this text has Chinese characters or could not be read"
                    return
            else:
                sents = phonemize(self.text, m.data_dir, self.lang)
                if sents is None:
                    self.why = "espeak-ng: " + (_ESPEAK["why"] or "could not read the text")
                    return
                todo = token_pieces(sents, m.tokens, m.max_len)
            pieces = []
            for ids, labels in todo:
                frames = m.durations(ids, self.sid, self.speed)
                if len(frames) != len(ids):
                    self.why = "the timing model gave the wrong number of lengths"
                    return
                pieces.append((labels, frames))
            self.pieces = pieces
        except Exception as exc:
            self.why = f"timing failed ({type(exc).__name__})"
        finally:
            self.ms = (time.monotonic() - t0) * 1000.0
            self.done.set()


STALE_COPY = ("The timing copy (model.durations.onnx) was made from a different voice model "
              "than the one installed now. Run the one-time step again (backend\\README.md, "
              "\"Mouths that match the words\"). Until then the apps work the mouth out from "
              "the sound, as before.")
_STALE_CACHE: dict = {}


def _stale_copy(paths: dict) -> str:
    """STALE_COPY when the copy's own notes say it came from a model of
    another size than the one installed (an old copy beside a new pack, or
    the other way round) - or, for Kokoro v1.0, from anything but the pinned
    model file; "" when it fits or cannot be told. The notes are read once
    per file version, not on every status poll."""
    try:
        dst = durations_path(paths)
        st = dst.stat()
        key = (str(dst), st.st_mtime_ns, st.st_size)
        meta = _STALE_CACHE.get(key)
        if meta is None:
            meta = _meta_of(dst)
            _STALE_CACHE.clear()
            _STALE_CACHE[key] = meta
        if not meta:
            return ""
        have = str(Path(paths["model"]).stat().st_size)
        if meta.get("jarvis_source_size") not in (None, have):
            return STALE_COPY
        if _model_version(meta) >= 2:
            pin = _v1_pin()
            if pin is not None and (meta.get("jarvis_source_sha256") != str(pin["sha256"]).lower()
                                    or have != str(pin["bytes"])):
                return STALE_COPY
        return ""
    except Exception:
        return ""


def ready(paths: Optional[dict] = None) -> Tuple[bool, str]:
    """(can mouths be made here, why not) - file and package checks only.
    The voice's files first, then the one-time step, then the packages -
    so the answer does not depend on what happens to be installed when
    there is no voice at all."""
    if np is None:
        return False, "numpy is not installed"
    paths = paths or tts_paths()
    for key in ("model", "voices", "tokens"):
        if not Path(paths.get(key) or "").is_file():
            return False, "the Kokoro voice is not installed"
    if not Path(paths.get("data_dir") or "").is_dir():
        return False, "the Kokoro voice's espeak-ng-data folder is missing"
    if not durations_path(paths).is_file():
        return False, HOW_TO_PREPARE
    stale = _stale_copy(paths)
    if stale:
        return False, stale
    try:
        import onnxruntime  # noqa: F401
    except Exception:
        return False, "onnxruntime is not installed (py -3 -m pip install onnxruntime)"
    try:
        import espeakng_loader  # noqa: F401
    except Exception:
        return False, ("the espeakng-loader package is not installed "
                       "(py -3 -m pip install espeakng-loader)")
    return True, ""


def begin(text: str, sid: int, speed: float, lang: str = "en-us",
          paths: Optional[dict] = None) -> Optional[Job]:
    """Start the timing of `text` for Kokoro voice `sid` at `speed` (the
    speed Kokoro itself is asked for), or None when mouths cannot be made
    here - then nothing about the sound changes. Never raises."""
    try:
        paths = paths or tts_paths()
        ok, why = ready(paths)
        if not ok:
            return None  # not set up: status() says why; nothing was tried
        job = Job(text, int(sid), float(speed), lang or "en-us", paths)
        job.thread.start()
        return job
    except Exception as exc:
        _note(False, f"could not start ({type(exc).__name__})")
        return None


def warm(paths: Optional[dict] = None) -> None:
    """Load the timing model and espeak-ng on a thread of their own, so the
    first sentence is not the one that waits for them. Never raises."""
    def run():
        try:
            p = paths or tts_paths()
            if ready(p)[0]:
                m = _model(p)
                if m is not None:
                    phonemize("Ready.", m.data_dir, "en-us")
        except Exception:
            pass
    threading.Thread(target=run, name="jarvis-mouth-warm", daemon=True).start()


# --------------------------------------------------------------------------
#   Speaking with a mouth: what jarvis_speech.kokoro_speak calls
# --------------------------------------------------------------------------

class NotHere(Exception):
    """This sherpa-onnx cannot be asked the way this needs; speak as before."""


def speak(engine, text: str, sid: int, speed: float, semitones: float, *,
          pitch_up: Callable, silence_scale: float = 0.2, lang: str = "en-us",
          paths: Optional[dict] = None, wait: float = MOUTH_WAIT_S,
          extra_lang: Optional[str] = None):
    """(samples, sample_rate, payload or None) for the built-in voice,
    with the mouth shapes when they can be made - or raises NotHere before
    any sound was made (the caller then speaks exactly as before). `speed`
    is the pace asked for; Kokoro is asked for speed / f and the sound is
    then raised - or, below 0, lowered - by `semitones` (pitch_up), as
    kokoro_speak does. `lang` is the espeak voice the text is read with;
    `extra_lang` is the same voice when it must also be handed to sherpa-onnx
    as the per-call language (Kokoro v1.0's British voices - the call
    jarvis_speech._kokoro_generate makes), else None and sherpa-onnx uses
    its own."""
    try:
        import sherpa_onnx
        make_config = sherpa_onnx.GenerationConfig
    except Exception:
        raise NotHere("sherpa-onnx has no GenerationConfig")
    # The same f pitch_up plays the sound at: above 1 higher and shorter,
    # below 1 (a deeper animal voice) lower and longer - either way every
    # time below is divided by it (finish()).
    f = 2.0 ** (float(semitones or 0.0) / 12.0)
    model_speed = float(speed) / f
    job = begin(text, sid, model_speed, lang, paths)
    if job is None:
        raise NotHere("no mouth here")
    try:
        cfg = make_config()
        cfg.sid = int(sid)
        cfg.speed = model_speed
        cfg.silence_scale = 1.0
        if extra_lang:
            cfg.extra = {"lang": str(extra_lang)}
    except Exception:
        raise NotHere("GenerationConfig is not the expected shape")
    pieces: list = []

    def keep(chunk, _progress) -> int:
        pieces.append(np.array(chunk, dtype=np.float32, copy=True))
        return 1  # sherpa-onnx carries on while this is non-zero

    try:
        audio = engine.generate(text, cfg, keep)
    except TypeError:
        raise NotHere("this sherpa-onnx has no generate(text, config, callback)")
    except Exception:
        if extra_lang:
            # what _kokoro_generate does when the accent cannot be asked for
            raise NotHere("sherpa-onnx would not take the accent")
        raise
    if audio is None or len(audio.samples) == 0:
        if extra_lang:
            raise NotHere("no sound for the accent")  # the caller's own fallback speaks
        return None
    rate = int(audio.sample_rate)
    whole = np.asarray(audio.samples, dtype=np.float32)
    if sum(len(p) for p in pieces) != len(whole) or not pieces:
        pieces, consistent = [whole], False
    else:
        consistent = True
    shortened, remaps = [], []
    for p in pieces:
        if looks_raw(p):
            y, rm = scale_silence(p, rate, silence_scale)
        else:
            y, rm = p, None
        shortened.append(y)
        remaps.append(rm)
    samples = pitch_up(np.concatenate(shortened) if len(shortened) > 1 else shortened[0],
                       semitones)
    payload = None
    try:
        if not consistent:
            _note(False, "sherpa-onnx's pieces did not add up to the sound")
        else:
            payload = finish(job, pieces, remaps, samples, rate, f, wait)
    except Exception as exc:
        _note(False, f"mouth failed ({type(exc).__name__})")
        payload = None
    return samples, rate, payload


def finish(job: Job, pieces, remaps, final_samples, rate: int, f: float,
           wait: float = MOUTH_WAIT_S) -> Optional[str]:
    """The "jmth" payload for one spoken sentence, or None (and why is kept
    in status()). Checks that every piece of sound is exactly as long as
    the timing says - the proof that the sounds were worked out the same
    way sherpa-onnx worked them out."""
    if not job.done.wait(max(0.0, wait)):
        _note(False, "the timing was not ready in time")
        return None
    if job.pieces is None:
        _note(False, job.why or "no timing", job.ms)
        return None
    if len(job.pieces) != len(pieces):
        _note(False, f"{len(job.pieces)} sentences worked out, sherpa-onnx spoke {len(pieces)}",
              job.ms)
        return None
    segs = []
    offset = 0.0
    for (labels, frames), raw, rm in zip(job.pieces, pieces, remaps):
        want = int(np.sum(frames)) * KOKORO_FRAME
        if want != len(raw) or rm is None:
            _note(False, f"a sentence is {len(raw)} samples, the timing says {want}", job.ms)
            return None
        edges = np.concatenate(([0], np.cumsum(frames))) * KOKORO_FRAME
        # the sound comes SOUND_LEAD before the plan (see SOUND_LEAD); the
        # piece still starts at 0 and ends at its last sample
        edges = np.concatenate((np.clip(edges[:-1] - SOUND_LEAD, 0, None), edges[-1:]))
        shortened = rm(float(len(raw)))
        for lab, a, b in zip(labels, edges[:-1], edges[1:]):
            segs.append((lab, (offset + rm(float(a))) / f / rate,
                         (offset + rm(float(b))) / f / rate))
        offset += shortened
    total = len(final_samples) / float(rate)
    if abs(offset / f / rate - total) > 1.5 / FPS:
        _note(False, "the timing and the final sound differ in length", job.ms)
        return None
    track = build_track(segs, final_samples, rate)
    if track is None:
        _note(False, "no mouth track", job.ms)
        return None
    _note(True, "", job.ms)
    return PAYLOAD_HEAD + pack(track)


# --------------------------------------------------------------------------
#   Sounds -> mouth shapes
# --------------------------------------------------------------------------

def segments(segs):
    """Timed sounds -> [(label, kind, t0, t1, stress)] with the marks folded
    in: stress onto the next sound, length/syllabic marks onto the one
    before. kind: "V" vowel, a consonant class, "REST" (pause, pad,
    punctuation) or "T" (no pull of its own: space, h, glottal stop)."""
    out: List[list] = []
    pending_stress, pending_t0 = 0, None
    for lab, t0, t1 in segs:
        if lab in _STRESS:
            # Its time goes to the next sound; its stress to the next vowel.
            pending_stress = max(pending_stress, _STRESS[lab])
            pending_t0 = t0 if pending_t0 is None else pending_t0
            continue
        if lab in _TO_PREVIOUS:
            if out:
                out[-1][3] = max(out[-1][3], t1)
            continue
        if lab == "" or lab in _REST:
            kind = "REST"
        elif lab in _V:
            kind = "V"
        elif lab in _C:
            kind = _C[lab]
        else:
            kind = "T"  # _TRANSPARENT, and any sound this table does not know
        if pending_t0 is not None and kind != "REST":
            start, pending_t0 = pending_t0, None
        else:
            start = t0
        out.append([lab, kind, start, t1, pending_stress if kind == "V" else 0])
        if kind in ("V", "REST"):
            pending_stress, pending_t0 = 0, None
    return [tuple(s) for s in out]


def _dominance(times, t0, t1, alpha, ant, car):
    d = np.full(times.shape, float(alpha))
    before = times < t0
    after = times > t1
    d[before] = alpha * np.exp(-((t0 - times[before]) / max(ant, 1e-4)) ** 2)
    d[after] = alpha * np.exp(-((times[after] - t1) / max(car, 1e-4)) ** 2)
    return d


def _targets(seg):
    """((open, alpha, ant, car) | None, (wide, ...) | None, (round, ...) | None)."""
    lab, kind, _t0, _t1, stress = seg
    k = K
    if kind == "T":
        return None, None, None
    if kind == "REST":
        return ((0.0, k["rest_alpha"], k["rest_reach"], k["rest_reach"]),
                (0.0, 1.0, k["rest_reach"], k["rest_reach"]),
                (0.0, 1.0, k["rest_reach"], k["rest_reach"]))
    if kind == "V":
        o, w, r = _V[lab]
        o *= k["stress"][max(0, min(2, stress))]
        vo = (o, k["vowel_alpha"], k["vowel_open_reach"], k["vowel_open_reach"])
        if r >= 0.3:
            vr = (r, k["round_alpha"], k["round_ant"], k["round_car"])
        else:
            vr = (r, k["vowel_alpha"], k["vowel_lip_reach"], k["vowel_lip_reach"])
        if w >= 0.4:
            vw = (w, k["round_alpha"], k["spread_ant"], k["spread_car"])
        else:
            vw = (w, k["vowel_alpha"], k["vowel_lip_reach"], k["vowel_lip_reach"])
        return vo, vw, vr
    o, w, r = _CLASS[kind]
    reach = k["cons_reach"]
    to = (o, k["cons_alpha"], reach, reach) if o is not None else None
    if kind in ("W", "PAL"):
        tr = (r, k["round_alpha"], k["round_ant"], k["round_car"])
    else:
        tr = (r, k["cons_alpha"], reach, reach) if r is not None else None
    if kind in ("LAB", "J"):
        tw = (w, k["round_alpha"], reach, reach)
    else:
        tw = (w, k["cons_alpha"], reach, reach) if w is not None else None
    return to, tw, tr


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _coef(ms: float) -> float:
    return 1.0 - math.exp(-1000.0 / FPS / ms)


def _smooth_fb(x, ms: float):
    a = _coef(ms)
    y = np.array(x, dtype=np.float64)
    if len(y) == 0:
        return y
    v = y[0]
    for i in range(len(y)):
        v += (y[i] - v) * a
        y[i] = v
    v = y[-1]
    for i in range(len(y) - 1, -1, -1):
        v += (y[i] - v) * a
        y[i] = v
    return y


def frame_count(num_samples: int, rate: int) -> int:
    """lipsync.js features(): n = ceil(len * FPS / rate)."""
    return (num_samples * FPS + rate - 1) // rate if num_samples > 0 and rate > 0 else 0


def loudness(samples, rate: int):
    """(dB per frame, ref, gate, level 0..1) - a port of lipsync.js
    features()'s broadband level and its `level` channel (Hann window,
    ~25 ms, centred on each frame's time; 95th-percentile reference)."""
    x = np.asarray(samples, dtype=np.float64)
    n = frame_count(len(x), rate)
    N = 128
    target = 0.025 * rate
    while N < 2048 and N * 1.4142 < target:
        N *= 2
    half = N >> 1
    w = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N) / N)
    wsum = float(np.sum(w * w))
    pad = np.concatenate((np.zeros(half), x, np.zeros(N)))
    centres = (np.arange(n) * rate) // FPS
    # A block of frames at a time: all n windows at once is n x N numbers
    # (float64), which for a clip minutes long was gigabytes (the mouth
    # corpus: a 25-minute answer took over 3 GB here). Same numbers.
    e = np.zeros(n)
    offs = np.arange(N)[None, :]
    for a in range(0, n, 2048):
        frames = pad[centres[a:a + 2048, None] + offs]
        e[a:a + 2048] = np.sum((frames * w[None, :]) ** 2, axis=1)
    db = 10.0 * np.log10(e / wsum + 1e-12)
    level = np.zeros(n)
    live = np.sort(db[db > -80])
    if len(live) == 0:
        return db, 0.0, 0.0, level

    def pct(q):
        return float(live[int(math.floor(q * (len(live) - 1)))])
    ref, floor = pct(0.95), pct(0.10)
    gate = min(ref - 30, max(ref - 50, floor + 8))
    att, rel, env = _coef(20), _coef(75), 0.0
    for i in range(n):
        v = min(1.0, max(0.0, (db[i] - gate) / (ref - gate)))
        env += (v - env) * (att if v > env else rel)
        level[i] = env
    return db, ref, gate, level


def build_track(segs, final_samples, rate: int) -> Optional[dict]:
    """The mouth track (lipsync.js's shape: fps, n, level, open, wide,
    round) for timed sounds `segs` [(label, t0, t1)] in seconds of the
    final clip, whose samples are `final_samples`."""
    n = frame_count(len(final_samples), rate)
    if n <= 0:
        return None
    k = K
    times = np.arange(n) / float(FPS)
    segl = segments(segs)
    num = [np.zeros(n) for _ in range(3)]
    den = [np.zeros(n) for _ in range(3)]
    prior = (k["prior_open"], k["prior_lips"], k["prior_lips"])
    for c in range(3):
        den[c] += prior[c]
    for seg in segl:
        _lab, _kind, t0, t1, _st = seg
        for c, tgt in enumerate(_targets(seg)):
            if tgt is None:
                continue
            value, alpha, ant, car = tgt
            lo = int(max(0, math.floor((t0 - 4 * ant) * FPS)))
            hi = int(min(n, math.ceil((t1 + 4 * car) * FPS) + 1))
            if hi <= lo:
                continue
            d = _dominance(times[lo:hi], t0, t1, alpha, ant, car)
            num[c][lo:hi] += d * value
            den[c][lo:hi] += d
    opn, wide, rnd = (num[c] / den[c] for c in range(3))

    # m, b, p shut for their whole sound; f, v barely open.
    env_bil = np.ones(n)
    cap_lab = np.ones(n)
    for lab, kind, t0, t1, _st in segl:
        if kind == "BIL":
            if t1 - t0 < k["bil_min"]:
                mid = (t0 + t1) / 2
                t0, t1 = mid - k["bil_min"] / 2, mid + k["bil_min"] / 2
            e = np.where(times < t0, _smoothstep((t0 - times) / k["bil_in"]),
                         np.where(times > t1, _smoothstep((times - t1) / k["bil_out"]), 0.0))
            env_bil = np.minimum(env_bil, e)
        elif kind == "LAB":
            e = np.where(times < t0, _smoothstep((t0 - times) / k["lab_in"]),
                         np.where(times > t1, _smoothstep((times - t1) / k["lab_out"]), 0.0))
            cap_lab = np.minimum(cap_lab, k["lab_open"] + (1 - k["lab_open"]) * e)

    # The clip's own loudness: louder (stressed) opens more; silence shuts.
    db, ref, gate, level = loudness(final_samples, rate)
    if ref > gate:
        u = np.clip((db - (ref - k["loud_range_db"])) / k["loud_range_db"], 0.0, 1.0)
        u = np.clip(_smooth_fb(u, k["loud_ms"]), 0.0, 1.0)
        gain = k["loud_min"] + (1 - k["loud_min"]) * u ** k["loud_pow"]
        speech = db > gate
    else:
        gain = np.full(n, k["loud_min"])
        speech = np.zeros(n, dtype=bool)
    pm = np.ones(n)
    i = 0
    while i < n:
        if speech[i]:
            i += 1
            continue
        j = i
        while j < n and not speech[j]:
            j += 1
        if j - i >= k["gap_frames"]:
            g = float(k["gap_close_frames"])
            for q in range(i, j):
                dl = q - i + 1 if i > 0 else 99
                dr = j - q if j < n else 99
                pm[q] = max(min(1.0, max(0.0, 1 - dl / g)), min(1.0, max(0.0, 1 - dr / g)))
        i = j

    opn = opn * gain * k["open_gain"]
    opn = _smooth_fb(opn, k["smooth_ms"])
    opn = np.minimum(opn, cap_lab) * env_bil * pm
    wide = _smooth_fb(wide, k["smooth_ms"]) * pm
    rnd = _smooth_fb(rnd, k["smooth_ms"]) * pm
    w2 = np.clip(wide * (1 - rnd), 0, 1)
    r2 = np.clip(rnd * (1 - wide), 0, 1)
    return {"fps": FPS, "n": n, "level": np.clip(level, 0, 1), "open": np.clip(opn, 0, 1),
            "wide": w2, "round": r2, "_segments": segl}


# --------------------------------------------------------------------------
#   The track in the WAV
# --------------------------------------------------------------------------

def _byte(x) -> np.ndarray:
    """lipsync.js pack(): Math.round(clamp01(x) * 255) - halves round up."""
    return np.floor(np.clip(np.asarray(x, dtype=np.float64), 0, 1) * 255 + 0.5).astype(np.uint8)


def pack(track: dict) -> str:
    """lipsync.js pack(), byte for byte: "<fps>:" + base64 of 4 bytes a
    frame (level, open, wide, round)."""
    n = int(track["n"])
    b = np.empty(n * 4, dtype=np.uint8)
    for j, key in enumerate(("level", "open", "wide", "round")):
        b[j::4] = _byte(np.asarray(track[key])[:n])
    return f"{int(track['fps'])}:" + base64.b64encode(b.tobytes()).decode("ascii")


def unpack(s: str) -> Optional[dict]:
    """The other way (tests, and anyone reading a chunk back)."""
    try:
        fps, body = s.split(":", 1)
        b = np.frombuffer(base64.b64decode(body, validate=True), dtype=np.uint8)
        n = len(b) // 4
        return {"fps": int(fps), "n": n, "level": b[0::4][:n] / 255.0,
                "open": b[1::4][:n] / 255.0, "wide": b[2::4][:n] / 255.0,
                "round": b[3::4][:n] / 255.0}
    except Exception:
        return None


def add_chunk(wav: bytes, payload: Optional[str]) -> bytes:
    """`wav` with a "jmth" chunk carrying `payload` appended after its
    `data` chunk, RIFF size fixed and the RIFF pad byte added - or `wav`
    unchanged if anything about it is unexpected. Never raises."""
    try:
        if not payload or len(wav) < 12 or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
            return wav
        p, seen_data = 12, False
        while p + 8 <= len(wav):
            cid = wav[p:p + 4]
            size = struct.unpack("<I", wav[p + 4:p + 8])[0]
            if cid == b"data":
                if size == 0 or p + 8 + size > len(wav):
                    return wav  # a data chunk that does not say its size: leave it be
                seen_data = True
            p += 8 + size + (size & 1)
        if not seen_data or p != len(wav):
            return wav
        body = payload.encode("ascii")
        chunk = CHUNK_ID + struct.pack("<I", len(body)) + body + (b"\0" if len(body) & 1 else b"")
        out = bytearray(wav + chunk)
        out[4:8] = struct.pack("<I", len(out) - 8)
        return bytes(out)
    except Exception:
        return wav


def read_chunk(wav: bytes) -> Optional[str]:
    """The first "jmth" payload after `data`, or None."""
    try:
        p, after = 12, False
        while p + 8 <= len(wav):
            cid = wav[p:p + 4]
            size = struct.unpack("<I", wav[p + 4:p + 8])[0]
            if after and cid == CHUNK_ID:
                return wav[p + 8:p + 8 + size].decode("ascii")
            if cid == b"data":
                after = True
            p += 8 + size + (size & 1)
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------
#   status and the command line
# --------------------------------------------------------------------------

def status(paths: Optional[dict] = None) -> dict:
    """GET /api/voice/status tts.mouth: can the mouths follow Kokoro's own
    timing here, and why not. File checks only; nothing is loaded."""
    try:
        ok, why = ready(paths)
    except Exception as exc:
        ok, why = False, f"could not check ({type(exc).__name__})"
    with _STATS_LOCK:
        stats = dict(_STATS)
    return {"available": ok,
            "status": ("ready: the mouths follow Kokoro's own timing" if ok else why),
            "made": stats["made"], "skipped": stats["skipped"],
            "last_skip_why": stats["last_why"], "last_ms": stats["last_ms"]}


def _main(argv: Sequence[str]) -> int:
    if "--prepare" in argv:
        got = prepare(force="--force" in argv)
        return 0 if got["ok"] else 1
    st = status()
    for key, value in st.items():
        print(f"  {key:<14} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
