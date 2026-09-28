"""The animals' mouths on a large, deliberately awkward set of sentences.

    python3 test_mouth_corpus.py                  (CI: no voice model needed)
    python3 test_mouth_corpus.py --make-fixtures  (with JARVIS_KOKORO_DIR set)

The owner asked for the animals' mouths to be tested "with a large amount of
verbs, words, sentences and more". A test engineer's corpus of 3,286 lines
(every English speech sound at the start, middle and end of a word, minimal
pairs, consonant clusters, about 300 verbs in all their forms, contractions,
numbers, times, dates, money, units, abbreviations, web addresses, names,
words spelt the same but said differently, punctuation of every kind, emoji,
other alphabets, control characters, one-letter and very long answers, the
720 Harvard sentences, tongue twisters and Jarvis's own replies) was run
through jarvis_mouth.py in all four voices (13,144 mouth tracks), and 671 of
them were also spoken by the real Kokoro voice through kokoro_speak(...,
mouth=[]) as say() does it (2,631 clips; 646 lines in all four voices). The
corpus and the scripts that ran it live in the dev container's scratch
space, not here.

This file keeps a compact, broad slice of that corpus as a regression test.
fixtures/mouth_corpus/corpus.json holds, for every line: the text, the
speech sounds espeak-ng gives for it (as sherpa-onnx makes them for Kokoro),
and the length Kokoro's own timing model gives every sound in each of the
four voices - worked out once with the real model. So without the model
this still checks, on real timings:

  - every speech sound the sentences use has a mouth shape (none silently
    ignored), and every sound in Kokoro's vocabulary has one;
  - Kokoro's token pieces (pads, the space after ".", the split at 510);
  - how a clause ended (_clause_end) on the exact text espeak-ng read, in
    cases checked against piper-phonemize - including the three it used to
    get wrong: a clause with no letter or digit ("!", an emoji and "."),
    a NUL character, and U+FFFD;
  - the mouth track for every line in every voice, on a stand-in sound
    (louder on vowels, silent in pauses) put through the real pause
    shortening, pitch rise and finish(): m, b, p shut for their whole
    sound; f, v a lip-bite; "oo"/"w" rounded (and rounding early, except
    straight after a silence); "ee" spread; ah > eh > ee; pauses and the
    clip's ends shut; no NaN, nothing outside 0..1; no jump over 0.35 in
    10 ms; wide and round never both over 0.5; the packed track the same as
    the committed one (within 2/255) for a sample of lines.

With espeakng-loader installed it also reads the corpus's awkward texts with
espeak-ng's own bundled data and checks that each is split into the same
sentences with the same endings as piper-phonemize. With JARVIS_KOKORO_DIR
pointing at a kokoro-en-v0_19 folder it runs the real thing: espeak-ng
with Kokoro's data must give the stored sounds for every line, the timing
model the stored lengths in every voice, and sherpa-onnx must speak the
awkward lines with a mouth that matches it to the sample.
"""
import hashlib
import json
import math
import os
import sys
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_mouth.py", "jarvis_speech.py")

import numpy as np  # noqa: E402
import jarvis_mouth as J  # noqa: E402
import jarvis_speech as S  # noqa: E402

FIX = HERE / "fixtures" / "mouth_corpus" / "corpus.json"
FAILED, PASSED = [], []
VOICES = {"default": (0, 1.0, 0.0), "panda": (1, 1.0, 2.0), "owl": (2, 0.85, 1.0),
          "otter": (4, 1.15, 3.0)}
RATE = 24000


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))


def load():
    return json.loads(FIX.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
#   The stand-in sound and the track, the way say() builds it
# ---------------------------------------------------------------------------

_AMP = {"V": 0.30, "R": 0.14, "W": 0.12, "J": 0.14, "ALV": 0.10, "VEL": 0.08,
        "BIL": 0.06, "LAB": 0.06, "DEN": 0.05, "SIB": 0.07, "PAL": 0.07, "T": 0.04}
_STOPS = set("pbtdkɡg")


def standin(labels, frames, rng):
    """Kokoro's raw sound for one piece, stood in by noise at a loudness per
    kind of sound: vowels loudest, a stop silent for its first 60 % (the
    closure) then a burst, pauses and pads exactly 0 (so the pause shortening
    really shortens them) - and, like Kokoro's own, SOUND_LEAD ahead of the
    plan."""
    out = []
    for lab, fr in zip(labels, frames):
        ns = int(fr) * J.KOKORO_FRAME
        if ns == 0:
            continue
        if lab == "" or lab in J._REST:
            out.append(np.zeros(ns, np.float32))
            continue
        kind = "V" if lab in J._V else J._C.get(lab, "T")
        env = np.full(ns, _AMP.get(kind, 0.04), np.float32)
        if lab in _STOPS:
            env[: int(ns * 0.6)] = 0.0
        ramp = min(ns // 2, 120)
        if ramp > 0:
            env[:ramp] *= np.linspace(0.2, 1, ramp)
            env[-ramp:] *= np.linspace(1, 0.2, ramp)
        out.append((rng.standard_normal(ns).astype(np.float32) * env).clip(-1, 1))
    if not out:
        return np.zeros(0, np.float32)
    x = np.concatenate(out)
    # Kokoro's real sound runs SOUND_LEAD ahead of its plan (jarvis_mouth.py);
    # so does the stand-in, same length
    lead = min(len(x), int(getattr(J, "SOUND_LEAD", 0)))
    return np.concatenate((x[lead:], np.zeros(lead, np.float32)))


class _Job:
    def __init__(self, pieces):
        self.pieces, self.why, self.ms = pieces, "", 0.0
        self.done = threading.Event()
        self.done.set()


def make_track(line, voice):
    """(track, timed sounds, final samples, payload) for one fixture line in
    one voice - through scale_silence, pitch_up and finish(), as say() does."""
    sid, _speed, semis = VOICES[voice]
    f = 2.0 ** (semis / 12.0)
    pieces = [(labels, np.asarray(fr, np.int64))
              for labels, fr in zip(line["labels"], line["frames"][voice])]
    seed = int(hashlib.md5((line["text"] + voice).encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    raws = [standin(l, fr, rng) for l, fr in pieces]
    if sum(len(r) for r in raws) == 0:
        return None, [], None, None
    shortened, remaps = [], []
    for r in raws:
        y, rm = J.scale_silence(r, RATE, 0.2)
        shortened.append(y)
        remaps.append(rm)
    final = S.pitch_up(np.concatenate(shortened), semis)
    # finish() builds the track; keep the one it built (and the timed sounds
    # it built it from) instead of building it twice.
    seen = {}
    build = J.build_track

    def keep(segs, samples, rate):
        seen["segs"], seen["track"] = list(segs), build(segs, samples, rate)
        return seen["track"]
    J.build_track = keep
    try:
        payload = J.finish(_Job(pieces), raws, remaps, final, RATE, f, wait=0)
    finally:
        J.build_track = build
    if "track" not in seen:
        return None, [], final, payload
    return seen["track"], seen["segs"], final, payload


def _frames_in(t0, t1, n):
    a = max(0, int(math.ceil(t0 * J.FPS)))
    b = min(n - 1, int(math.floor(t1 * J.FPS)))
    return range(a, b + 1)


# ---------------------------------------------------------------------------
#   Without the model
# ---------------------------------------------------------------------------

def t_fixture_is_broad(data):
    lines = data["lines"]
    cats = {l["cat"] for l in lines}
    want = {"phoneme", "minimal_pair", "cluster", "verb_irregular", "verb_regular",
            "verb_sentence", "function_words", "contraction", "number", "time", "date",
            "currency", "percent_unit", "abbrev", "url_email", "name", "homograph",
            "punctuation", "emoji_nonascii", "very_short", "letters", "long", "harvard",
            "tongue_twister", "jarvis", "probe"}
    check(f"the fixture covers every kind of line ({len(lines)} lines, {len(cats)} kinds)",
          want <= cats, str(sorted(want - cats)))
    sounds = set("".join(s for l in lines for s in l["sents"]))
    english = set("pbtdkɡfvθðszʃʒhmnŋlɹwjiɪeɛæɑɔoʊuʌəɚɜaɐᵻɾʔ")
    check("every English speech sound espeak-ng uses is in it", english <= sounds,
          "".join(sorted(english - sounds)))


def t_every_sound_has_a_shape(data):
    tokens = data["tokens"]
    known = lambda c: (c in J._V or c in J._C or c in J._STRESS or c in J._TO_PREVIOUS
                       or c in J._TRANSPARENT or c in J._REST)
    used = set("".join(s for l in data["lines"] for s in l["sents"]))
    check("every sound in the corpus has a mouth shape (none silently ignored)",
          all(known(c) for c in used), "".join(sorted(c for c in used if not known(c))))
    # Kokoro's whole vocabulary: everything except the capital letters and the
    # tone arrows, which espeak-ng's phoneme output never contains.
    vocab = [c for c in tokens if not ("A" <= c <= "Z" or c in "↓↑→↗↘")]
    check(f"every sound in Kokoro's vocabulary has a mouth shape ({len(vocab)})",
          all(known(c) for c in vocab), "".join(c for c in vocab if not known(c)))
    check("Scottish 'oo' (ʉ, espeak-ng's en-gb-scotland) is rounded",
          J._V.get("ʉ", (0, 0, 0))[2] >= 0.75)


def t_token_pieces(data):
    tokens = data["tokens"]
    bad = []
    for l in data["lines"]:
        got = [lab for _ids, lab in J.token_pieces(l["sents"], tokens, 511)]
        if got != l["labels"]:
            bad.append(l["text"][:40])
    check(f"Kokoro's token pieces are the stored ones for every line ({len(data['lines'])})",
          not bad, str(bad[:3]))
    long_ = [l for l in data["lines"] if len(l["labels"]) > len(l["sents"])]
    check("a sentence longer than 510 sounds is split, every piece at most 512 tokens with "
          "a pad at each end (the longest measured exact against sherpa-onnx)",
          long_ and all(len(p) <= 512 and p[0] == "" and p[-1] == "" for l in long_
                        for p in l["labels"]),
          str([[len(p) for p in l["labels"]] for l in long_]))


def t_clause_end(data):
    cases = data["clause_cases"]
    wrong = [c for c in cases if J._clause_end(c[0], c[1], c[2]) != c[3]]
    check(f"how a clause ended: every case espeak-ng really read, as piper-phonemize (or, where "
          f"its wheel differs, sherpa-onnx itself) has it ({len(cases)})", not wrong, str(wrong[:3]))
    # the corpus's three finds, spelt out
    check("a clause with no letter or digit ends nothing ('!', thumbs-up '.', '© ®.')",
          J._clause_end("!", False) == "" and J._clause_end("\U0001F44D.", False) == ""
          and J._clause_end("© ®.", False) == "")
    check("... unless a line break follows the mark",
          J._clause_end("©.\nH", True) == ".")
    check("... and the character read past the last clause counts as this one's",
          J._clause_end("!", False, lead="X") == "!" and J._clause_end("5.", False) == ".")
    check("'½' and '²' are not digits to the espeak-ng inside sherpa-onnx (measured by "
          "speaking '½.': no full stop)", J._clause_end("½.", False) == ""
          and J._clause_end("²!", False) == "")


def t_tracks(data):
    t0 = time.monotonic()
    fails = {k: [] for k in ("made", "range", "frames", "bil", "lab", "pause", "ends",
                              "both", "jump", "golden")}
    rounders = anticip = anticip_ok = 0
    round_ok = spread = spread_ok = 0
    groups = {v: {"ah": [], "eh": [], "ee": []} for v in VOICES}
    max_jump = 0.0
    golden = data.get("golden", {})
    built = 0
    for line in data["lines"]:
        for voice in VOICES:
            track, segs, final, payload = make_track(line, voice)
            if final is None:
                continue  # nothing to say (no sound at all)
            built += 1
            name = f"{voice}: {line['text'][:40]!r}"
            if payload is None or track is None:
                fails["made"].append(name + " " + J.status()["last_skip_why"])
                continue
            n = track["n"]
            o, w, r = (np.asarray(track[k], np.float64) for k in ("open", "wide", "round"))
            if any(not np.all(np.isfinite(x)) or x.min() < 0 or x.max() > 1
                   for x in (o, w, r, np.asarray(track["level"]))):
                fails["range"].append(name)
            if n != J.frame_count(len(final), RATE) or len(o) != n:
                fails["frames"].append(name)
            db, ref, gate, _ = J.loudness(final, RATE)
            silent = db <= gate if ref > gate else np.ones(n, bool)
            sl = J.segments(segs)
            last_vowel_end = None
            for s in sl:
                fr = list(_frames_in(s[2], s[3], n))
                if s[1] == "BIL" and fr and max(o[i] for i in fr) > 1e-6:
                    fails["bil"].append(f"{name} {s[0]}@{s[2]:.2f}")
                if s[1] == "LAB" and fr and max(o[i] for i in fr) > J.K["lab_open"] + 1e-6:
                    fails["lab"].append(f"{name} {s[0]}@{s[2]:.2f}")
                if s[1] == "REST" and s[3] - s[2] >= 0.15 and s[2] > 0.05:
                    if o[min(n - 1, int((s[2] + s[3]) / 2 * J.FPS))] >= 0.05:
                        fails["pause"].append(f"{name} @{s[2]:.2f}")
                if s[1] == "V" and s[3] - s[2] >= 0.05 and fr:
                    g = ("ah" if s[0] in "ɑaæ" else "eh" if s[0] in "ɛe" else
                         "ee" if s[0] in "iɪ" else None)
                    if g:
                        groups[voice][g].append(max(o[i] for i in fr))
                if s[3] - s[2] >= 0.04 and fr and (
                        s[1] == "W" or (s[1] == "V" and J._V[s[0]][2] >= 0.75)):
                    rounders += 1
                    round_ok += max(r[i] for i in fr) >= 0.45
                    i = int(round((s[2] - 0.08) * J.FPS))
                    if (last_vowel_end is None or s[2] - last_vowel_end >= 0.1) and 0 <= i < n \
                            and not silent[max(0, i - 2):i + 3].any():
                        anticip += 1
                        anticip_ok += r[i] >= 0.15
                if s[1] == "V" and s[0] == "i" and s[3] - s[2] >= 0.04 and fr:
                    spread += 1
                    spread_ok += max(w[i] for i in fr) >= 0.4
                if s[1] == "V":
                    last_vowel_end = s[3]
            if o[0] >= 0.05 or o[-1] >= 0.05:
                fails["ends"].append(name)
            if np.any((w > 0.5) & (r > 0.5)):
                fails["both"].append(name)
            jump = max(float(np.max(np.abs(np.diff(x)))) if n > 1 else 0.0 for x in (o, w, r))
            max_jump = max(max_jump, jump)
            if jump > 0.35:
                fails["jump"].append(f"{name} {jump:.3f}")
            key = f"{line['id']}|{voice}"
            if key in golden:
                want = J.unpack(golden[key])
                have = J.unpack(payload[len(J.PAYLOAD_HEAD):]) if payload else None
                if not have or want["n"] != have["n"] or max(
                        float(np.max(np.abs(have[k] - want[k]))) for k in
                        ("open", "wide", "round")) > 2 / 255 + 1e-9:
                    fails["golden"].append(name)
    secs = time.monotonic() - t0
    total = built
    check(f"a mouth for every line in every voice ({total} tracks, {secs:.1f} s)",
          not fails["made"] and total >= 4 * len(data["lines"]) - 8, str(fails["made"][:3]))
    check("no NaN, nothing outside 0..1, one frame per 10 ms of the clip",
          not fails["range"] and not fails["frames"], str((fails["range"] + fails["frames"])[:3]))
    check("m, b, p shut for their whole sound, in every line and voice",
          not fails["bil"], f"{len(fails['bil'])}: {fails['bil'][:3]}")
    check("f, v a lip-bite (open at most 0.1) for their whole sound", not fails["lab"],
          f"{len(fails['lab'])}: {fails['lab'][:3]}")
    check("pauses shut, and the clip starts and ends shut",
          not fails["pause"] and not fails["ends"], str((fails["pause"] + fails["ends"])[:3]))
    check("wide and round never both over 0.5", not fails["both"], str(fails["both"][:3]))
    check(f"no jump over 0.35 between two frames (largest: {max_jump:.3f})", not fails["jump"],
          str(fails["jump"][:3]))
    check(f"'oo', 'oh', 'w' round (at least 0.45) in 95 % or more ({round_ok}/{rounders})",
          rounders > 200 and round_ok >= 0.95 * rounders)
    check(f"... and already rounding 80 ms before, when there is sound before them "
          f"({anticip_ok}/{anticip})", anticip > 100 and anticip_ok >= 0.9 * anticip)
    check(f"'ee' spreads the lips (at least 0.4) in 97 % or more ({spread_ok}/{spread})",
          spread > 100 and spread_ok >= 0.97 * spread)
    med = {v: {g: float(np.median(x)) if x else None for g, x in gs.items()}
           for v, gs in groups.items()}
    check("vowels open by how open they are, in every voice: ah > eh > ee (median peak)",
          all(None not in m.values() and m["ah"] > m["eh"] > m["ee"] for m in med.values()),
          json.dumps(med))
    check(f"the packed track is the committed one, within 2/255 ({len(golden)} tracks)",
          golden and not fails["golden"], str(fails["golden"][:3]))


def _marks(sents):
    """A sentence list reduced to what does not depend on the dictionary:
    how many sentences, and how each ends."""
    return [s[-1:] if s[-1:] in ".?!" else ("," if s.endswith(", ") else "") for s in sents]


def t_loader_phonemize(data):
    try:
        import espeakng_loader
        d = espeakng_loader.get_data_path()
    except Exception:
        print("skip: espeakng-loader is not installed (the clause cases above cover it)")
        return
    wrong = []
    for t in data["texts"]:
        got = J.phonemize(t["text"], d)
        if got is None or _marks(got) != _marks(t["want"]):
            wrong.append((t["text"], got, t["want"]))
    check(f"espeak-ng (espeakng-loader's own data) splits and ends every awkward text as "
          f"sherpa-onnx does ({len(data['texts'])})", not wrong, repr(wrong[:2]))


# ---------------------------------------------------------------------------
#   The real model (only with JARVIS_KOKORO_DIR)
# ---------------------------------------------------------------------------

def _real_paths():
    d = os.environ.get("JARVIS_KOKORO_DIR")
    if not d:
        return None
    d = Path(d)
    p = {"model": str(d / "model.onnx"), "voices": str(d / "voices.bin"),
         "tokens": str(d / "tokens.txt"), "data_dir": str(d / "espeak-ng-data"),
         "lexicon": "", "dict_dir": ""}
    return p if all(Path(p[k]).exists() for k in ("model", "voices", "tokens", "data_dir")) else None


def _real_model(p):
    J.prepare(p, say=lambda s: None)
    m = J._model(p)
    assert m is not None, J._MODEL["why"]
    return m


def t_real_model(data):
    p = _real_paths()
    if p is None:
        print("skip the real model: set JARVIS_KOKORO_DIR to a kokoro-en-v0_19 folder to run it")
        return
    m = _real_model(p)
    bad_s, bad_f = [], []
    for line in data["lines"]:
        sents = J.phonemize(line["text"], p["data_dir"])
        if sents != line["sents"]:
            bad_s.append(line["text"][:40])
            continue
        for voice, (sid, speed, semis) in VOICES.items():
            f = 2.0 ** (semis / 12.0)
            got = [m.durations(ids, sid, speed / f).tolist()
                   for ids, _l in J.token_pieces(sents, m.tokens, m.max_len)]
            if got != line["frames"][voice]:
                bad_f.append(f"{voice} {line['text'][:30]}")
    check(f"real model: espeak-ng gives the stored sounds for every line ({len(data['lines'])})",
          not bad_s, str(bad_s[:3]))
    check("real model: the timing model gives the stored lengths in every voice", not bad_f,
          str(bad_f[:3]))
    try:
        import sherpa_onnx
    except ImportError:
        print("skip speaking the awkward lines: sherpa-onnx is not installed")
        return
    k = sherpa_onnx.OfflineTtsKokoroModelConfig(model=p["model"], voices=p["voices"],
                                                tokens=p["tokens"], data_dir=p["data_dir"],
                                                lang="en-us")
    cfg = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(kokoro=k, num_threads=2))
    eng = sherpa_onnx.OfflineTts(cfg)
    missed = []
    for text in data["speak"]:
        got = J.speak(eng, text, 0, 1.0, 0.0, pitch_up=S.pitch_up, silence_scale=cfg.silence_scale,
                      paths=p, wait=30.0)
        if got is not None and got[2] is None:
            missed.append((text, J.status()["last_skip_why"]))
    check(f"real model: sherpa-onnx speaks the awkward lines with a mouth that matches it to "
          f"the sample ({len(data['speak']) - len(missed)}/{len(data['speak'])})", not missed,
          repr(missed[:3]))


def make_fixtures():
    """Recompute the sounds, lengths and golden tracks of the fixture's lines
    with the real model (keeps the lines themselves)."""
    p = _real_paths()
    if p is None:
        print("set JARVIS_KOKORO_DIR first")
        return 1
    m = _real_model(p)
    data = load()
    data["tokens"] = J.read_tokens(p["tokens"])
    for line in data["lines"]:
        line["sents"] = J.phonemize(line["text"], p["data_dir"])
        line["labels"] = [lab for _i, lab in J.token_pieces(line["sents"], m.tokens, m.max_len)]
        line["frames"] = {}
        for voice, (sid, speed, semis) in VOICES.items():
            f = 2.0 ** (semis / 12.0)
            line["frames"][voice] = [m.durations(ids, sid, speed / f).tolist()
                                     for ids, _l in J.token_pieces(line["sents"], m.tokens, m.max_len)]
    golden = {}
    for line in data["lines"]:
        if line.get("golden"):
            for voice in VOICES:
                _t, _s, _f, payload = make_track(line, voice)
                if payload:
                    golden[f"{line['id']}|{voice}"] = payload[len(J.PAYLOAD_HEAD):]
    data["golden"] = golden
    FIX.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("wrote", FIX, len(data["lines"]), "lines,", len(golden), "golden tracks")
    return 0


if __name__ == "__main__":
    if "--make-fixtures" in sys.argv:
        sys.exit(make_fixtures())
    data = load()
    tests = [v for k, v in list(globals().items()) if k.startswith("t_") and callable(v)]
    for fn in tests:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn(data)
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc(file=sys.stdout)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
