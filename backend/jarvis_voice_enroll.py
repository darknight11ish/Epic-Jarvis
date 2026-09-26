"""jarvis_voice_enroll.py - "Train my voice": clips from the phone, one card, then enrol.

NEW MODULE, shipped whole beside jarvis_hud.py (apply-patches.ps1 copies it).
`voice-enroll.patch` adds the one route that calls it:

    POST /api/voice/enroll   {"clips": ["<base64 WAV>", ...], "mic": "phone"}
        -> stage(body)       202 {"ok": true, "pending": true, ...}   a card is up
                             400 {"error": "clip 2 ..."}              bad input
                             409 {"error": ..., "pending": true}      one is already waiting
    GET /api/voice/status    gate.training = state()                  (jarvis_speech)

Since 2026-09-24 the same route (no new route, so no new patch) also takes:

    {"mode": "calibrate", "mic": "phone", "clips": [...]}   "someone else" -
        another person's clips, scored against the owner's print and
        dropped. 200 with the scores and, only when the owner's own
        training clips all beat theirs, a suggested stricter bar. No card:
        it changes nothing.
    {"mode": "threshold", "mic": "phone", "threshold": 0.52}   raises ONE
        card to use that bar for that microphone's print. Nothing changes
        until it is approved.

`mic` says which microphone's voice print the clips train (one print per
microphone - jarvis_voice.py, "ONE VOICE PRINT PER MICROPHONE"). Missing
means none named; an older phone sends none.

WHY THERE IS A CARD AT ALL. The voice print decides who may talk to Jarvis.
Replacing it is a change to who Jarvis obeys, which is `change_own_config`
(tier "ask" in jarvis-framework.toml) - the same action the wake-word
comment in jarvis_hud.py names for widening where Jarvis listens. So the
phone's clips are STAGED here and nothing is enrolled until a person says yes
on an approval card. That also closes the obvious attack: someone holding
the unlocked phone could otherwise record their own voice and become "the
owner" in one tap.

THE CARD. Raised through jarvis_gate.check() on a background thread, the
same way jarvis_skill_discovery.offer() raises its "make this a skill?"
card: check() blocks until a person answers or the gate's own timeout
(`approval_timeout_seconds`, 180 s in the shipped config) passes, so it must
not run on the request thread. The tier is checked BEFORE a card is raised
and AGAIN on the verdict, because `allowed` is True on tiers auto and notify
with nobody asked (docs/ARCHITECTURE.md §3) - a voice print must not be
replaced on that.

WHAT HAPPENS TO THE AUDIO. The clips live in this process's memory only -
never written to disk, never logged, never put on the card (the card says
how many clips and how long, nothing else). Approved: they are turned into a
voice print by jarvis_voice.enroll() and dropped. Denied, timed out, refused,
or the enrolment failed: dropped. Either way the list is cleared in a
`finally`, so no path keeps them.

THE "HEY JARVIS" CHECK, FROM THE SAME CLIPS (added 2026-09-24). When the
card is approved and the voice print is made, the same clips also build the
owner's wake-word verifier (jarvis_wakeword.build_verifier: the moments
"hey Jarvis" is heard in the sentences that start with it, against the
rest and a bank of other voices), saved beside the voice print. No second
card: it is part of the change the owner just approved - "this is my
voice". If it cannot be built (too few "hey Jarvis" sentences heard, no
wake-word model), the enrolment still stands and any OLD verifier is
deleted, because it described the voice that was just replaced. The
outcome says which (`wake_check`).

ONE AT A TIME. While a card is waiting, a second training is refused with a
409 rather than replacing the first. Replacing sounds friendlier and is
worse: the first card would still be on screen (the gate has no call to take
a card back), approving it would then do nothing or - worse - enrol the
wrong clips, and "which card is the real one" is not a question an approval
screen should ever pose. The 409 says how long until the waiting one expires.

THE STRICTER CHECK (added 2026-09-24) - still no new route; five more modes
on this one (docs/JARVIS-API.md, "The stricter voice check", has the JSON):

    {"mode": "train", "round": 1|2|3, "mic", "clips": [...], "add": false,
     "finish": false}
        Training in ROUNDS, each up to 12 clips in its own conditions (1:
        normal, close; 2: further away or quieter; 3: another time or
        room). Each round is checked and HELD HERE, in memory - no card,
        nothing changed - for up to SESSION_SECONDS after the last one.
        `"finish": true` (with a round, or alone) raises ONE card for
        everything held. Deny, a timeout, `"cancel": true`, or the time
        running out: every held clip is dropped. `"add": true` adds the
        recordings to the print already there instead of replacing it.
        Each round becomes its own sub-print (jarvis_voice, "sub-prints").
    {"mode": "strictness", "value": "very_strict"|"balanced"}
    {"mode": "privacy", "value": "private_on_screen"|"voice_is_enough"}
    {"mode": "memory", "value": "memory_aloud"|"memory_on_screen"}
    {"mode": "sensitive_memory", "value": "sensitive_on_screen"|"sensitive_aloud"}
    {"mode": "hands_free", "value": "same_as_button"|"button_only"}
        Tightening applies at once. Loosening raises ONE card
        (change_own_config), and changes nothing until it is approved.
        `voice_is_enough` is refused unless the check is very strict;
        choosing `balanced` puts private answers back on screen.
    {"mode": "measure", "mic", "clips": [up to 20]}
        The guided "how often would I have to repeat myself?" test: the
        owner's own sentences, each judged at both settings. Scored and
        dropped; no card.

Every held or staged clip is in this process's memory only, as before, and
the training no longer happens at all without a voice-ID model: with only
the basic check installed, a training is refused (409) before any card,
because the basic check refuses every voice anyway.
"""
from __future__ import annotations

import base64
import binascii
import io
import json
import math
import threading
import time
import uuid
import wave
from typing import Callable, Optional

#: The gate action. See the module docstring for why this one.
ACTION = "change_own_config"

#: Limits. Three is the fewest that says anything about how consistent the
#: owner's voice is (enroll() lowers the bar to fit the loosest clip, so one
#: clip would give it nothing to measure). Twelve since 2026-09-24 (the
#: phone asks for twelve short sentences, four of them "hey Jarvis"). Twelve
#: at ten seconds would not fit jarvis_hud's 4 MB MAX_BODY, so the TOTAL is
#: capped too: 80 s is ~2.6 MB of audio, ~3.4 MB as base64.
MIN_CLIPS = 3
MAX_CLIPS = 12
MIN_SECONDS = 1.0
MAX_SECONDS = 10.0
MAX_TOTAL_SECONDS = 80.0
#: The "someone else" check: a few clips of another person.
MIN_OTHER_CLIPS = 1
MAX_OTHER_CLIPS = 5
SAMPLE_RATE = 16000
#: Per clip, after base64: the audio at MAX_SECONDS plus room for a header
#: and a small extra chunk. Checked before the WAV is even parsed.
MAX_CLIP_BYTES = int(MAX_SECONDS * SAMPLE_RATE * 2) + 4096
#: Quieter than this at its loudest is a microphone that recorded nothing.
#: (About -40 dB below full scale; ordinary speech peaks far above it.)
MIN_PEAK = 0.01

#: Training rounds: number -> (the sub-print's condition, what the app
#: should ask for). The phone asks for each in turn; any may be redone.
ROUNDS = {1: ("close", "normal, close to the microphone"),
          2: ("far", "further away from the microphone, or quieter"),
          3: ("room", "at another time of day, or in another room")}
#: Held rounds are dropped this long after the last one arrived.
SESSION_SECONDS = 900.0
#: The guided repeat test: up to this many of the owner's own sentences.
MEASURE_MAX_CLIPS = 20

_LOCK = threading.Lock()
_PENDING: Optional[dict] = None     # {"id", "clips", "count", "seconds", "since", "timeout"}
_LAST: Optional[dict] = None        # the last outcome, for the phone to show
_SESSION: Optional[dict] = None     # rounds held before the card: {"id", "mic", "add", "rounds", "touched"}
_LAST_MEASURE: Optional[dict] = None  # the last guided test's counts (no audio, no scores per clip)


# --------------------------------------------------------------------------
#   Reading the clips - bytes from the network, before any card, so every
#   branch returns a sentence and none of them echoes what it was given.
# --------------------------------------------------------------------------

class BadClip(ValueError):
    """A clip the owner has to re-record. The message is shown on the phone."""


def _read_clip(n: int, raw: bytes) -> tuple:
    """(16-bit PCM bytes, seconds) for clip number `n` (1-based), or BadClip."""
    if not raw:
        raise BadClip(f"clip {n} is empty - record it again")
    if len(raw) > MAX_CLIP_BYTES:
        raise BadClip(f"clip {n} is longer than {MAX_SECONDS:g} seconds - "
                      f"record it again, a little shorter")
    try:
        with wave.open(io.BytesIO(raw), "rb") as w:
            rate, width, chans = w.getframerate(), w.getsampwidth(), w.getnchannels()
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError, ValueError, OSError):
        raise BadClip(f"clip {n} is not a WAV recording") from None
    if width != 2 or chans != 1 or rate != SAMPLE_RATE:
        raise BadClip(f"clip {n} must be 16 kHz, 16-bit, mono - it is "
                      f"{rate} Hz, {width * 8}-bit, {chans} channel(s)")
    seconds = len(frames) / 2 / SAMPLE_RATE
    if seconds < MIN_SECONDS:
        raise BadClip(f"clip {n} is too short ({seconds:.1f} s) - read the "
                      f"whole sentence")
    if seconds > MAX_SECONDS:
        raise BadClip(f"clip {n} is longer than {MAX_SECONDS:g} seconds - "
                      f"record it again, a little shorter")
    peak = 0
    for i in range(0, len(frames) - 1, 2):
        v = abs(int.from_bytes(frames[i:i + 2], "little", signed=True))
        if v > peak:
            peak = v
    if peak / 32768.0 < MIN_PEAK:
        raise BadClip(f"clip {n} is silent - check the microphone and record "
                      f"it again")
    return frames, round(seconds, 2)


def _doc(body) -> dict:
    """The request body as a JSON object, or BadClip."""
    try:
        doc = json.loads(body.decode("utf-8") if isinstance(body, (bytes, bytearray))
                         else body or "")
    except (UnicodeDecodeError, ValueError):
        raise BadClip('send {"clips": ["<base64 WAV>", ...]}') from None
    if not isinstance(doc, dict):
        raise BadClip('send {"clips": ["<base64 WAV>", ...]}')
    return doc


def _mic(doc: dict) -> str:
    """The microphone named in the body, as jarvis_voice spells it, or ""."""
    try:
        import jarvis_voice
        return jarvis_voice.clean_mic(doc.get("mic", ""))
    except Exception:
        return ""


def _parse(body, lo: int = MIN_CLIPS, hi: int = MAX_CLIPS) -> list:
    """The request body -> [(pcm, seconds)], or BadClip with the reason."""
    doc = body if isinstance(body, dict) else _doc(body)
    clips = doc.get("clips")
    if not isinstance(clips, list):
        raise BadClip('send {"clips": ["<base64 WAV>", ...]}')
    if not lo <= len(clips) <= hi:
        raise BadClip(f"send between {lo} and {hi} clips, not "
                      f"{len(clips)}")
    out = []
    for n, c in enumerate(clips, 1):
        if not isinstance(c, str):
            raise BadClip(f"clip {n} is not base64 text")
        # Checked on the TEXT first, so an oversized clip is refused before
        # it is decoded into a second, larger copy.
        if len(c) > (MAX_CLIP_BYTES * 4) // 3 + 8:
            raise BadClip(f"clip {n} is longer than {MAX_SECONDS:g} seconds - "
                          f"record it again, a little shorter")
        try:
            raw = base64.b64decode(c, validate=True)
        except (binascii.Error, ValueError):
            raise BadClip(f"clip {n} is not valid base64") from None
        out.append(_read_clip(n, raw))
    total = sum(s for _, s in out)
    if total > MAX_TOTAL_SECONDS:
        raise BadClip(f"the recordings are {total:.0f} seconds in all; the most is "
                      f"{MAX_TOTAL_SECONDS:.0f} - redo the longest ones a little quicker")
    return out


# --------------------------------------------------------------------------
#   The card
# --------------------------------------------------------------------------

_MIC_WORDS = {"phone": "your phone's microphone", "desktop": "this PC's microphone",
              "": "your microphones"}
_MIC_WHERE = {"phone": "on your phone", "desktop": "on this PC", "": "on your phone"}


def describe(count: int, seconds: float, mic: str = "", rounds: int = 1,
             add: bool = False) -> str:
    """The card's text. Every word from here - no audio, no transcript, no
    name. What refusing costs is on it, as docs/ARCHITECTURE.md §3 asks."""
    words = _MIC_WORDS.get(mic, _MIC_WORDS[""])
    where = _MIC_WHERE.get(mic, _MIC_WHERE[""])
    parts = f"{count} clips in {rounds} rounds" if rounds > 1 else f"{count} clips"
    if add:
        return (
            f"Add the recordings just made {where} to the voice Jarvis listens for on "
            f"{words}? {parts}, {seconds:.0f} seconds in all.\n\n"
            f"If you say yes: Jarvis learns more about how you sound on {words}, from "
            f"these recordings as well as the ones it already had. Nothing it had is "
            f"deleted. A voice that matches these clips can talk to Jarvis.\n\n"
            f"If you did not just do this {where}, say no - someone else may be "
            f"trying to make Jarvis obey their voice.\n\n"
            f"If you say no: nothing changes, and the recordings are deleted."
        )
    return (
        f"Replace the voice Jarvis listens for on {words} with the one just "
        f"recorded {where}? {parts}, {seconds:.0f} seconds in all.\n\n"
        f"If you say yes: from now on only a voice that matches these clips "
        f"can talk to Jarvis through {words}. Any voice trained before for it "
        f"is replaced. The sentences that start with \"hey Jarvis\" also "
        f"teach it how you say that.\n\n"
        f"If you did not just do this {where}, say no - someone else may be "
        f"trying to make Jarvis obey their voice.\n\n"
        f"If you say no: nothing changes, and the recordings are deleted."
    )


def describe_threshold(mic: str, old: float, new: float, which: str = "small") -> str:
    """The threshold card. Plain words: what the number does, both ways."""
    words = _MIC_WORDS.get(mic, _MIC_WORDS[""])
    stricter = new > old
    model = " (on the stronger voice-ID model)" if which == "strong" else ""
    return (
        f"Make Jarvis {'stricter' if stricter else 'less strict'} about your voice "
        f"on {words}? From {old:.2f} to {new:.2f}{model}.\n\n"
        f"This is how closely a voice must match yours to be obeyed. "
        + ("Higher turns other people away more often, and may sometimes "
           "ask you to repeat yourself. " if stricter else
           "Lower lets you through more easily, and lets other voices through "
           "more easily too. ")
        + "It was suggested by the \"someone else\" check.\n\n"
        f"If you did not just do this, say no.\n\n"
        f"If you say no: nothing changes."
    )


def _fw():
    import jarvis_framework
    return jarvis_framework


def _tier_of(action: str) -> str:
    return str(_fw().action_tier(action))


def _audit(event: str, detail: dict) -> None:
    try:
        _fw().audit_log(event, detail)
    except Exception:
        pass


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _timeout() -> float:
    try:
        return float(_fw().load_framework().get("autonomy", {})
                     .get("approval_timeout_seconds", 180))
    except Exception:
        return 180.0


def _embedder():
    import jarvis_voice
    try:
        return jarvis_voice.EcapaEmbedder()
    except Exception:
        return jarvis_voice.Embedder()


def _strong(primary):
    """The stronger model, or None - from a jarvis_voice.py new enough to
    have one."""
    import jarvis_voice
    fn = getattr(jarvis_voice, "strong_embedder", None)
    return fn(primary) if fn is not None else None


def _model_missing() -> str:
    """Why a training cannot be useful on this PC, or "". With only the basic
    check, every voice is refused (jarvis_voice, hole 1), so a card to
    train it would ask the owner to approve something that cannot work."""
    emb = _embedder()
    if getattr(emb, "semantic", False):
        return ""
    import jarvis_voice
    return getattr(jarvis_voice, "NO_MODEL_REASON",
                   "no voice-ID model is installed on this PC")


def _enroll(clips: list, mic: str = "", conditions: Optional[list] = None,
            add: bool = False):
    """The same embedder choice jarvis_speech.hear() makes, so the profile
    this writes is one hear() can compare against - verify() refuses a
    profile made by a different embedder. The stronger model too, when it
    is installed, so very strict has a print to compare it with."""
    import inspect
    import jarvis_voice
    emb = _embedder()
    # `sample_rate` and `mic` only for a jarvis_voice.py new enough to take
    # them: an older copy on the PC would otherwise turn an approved card
    # into a TypeError.
    params = inspect.signature(jarvis_voice.enroll).parameters
    kw = {}
    if "sample_rate" in params:
        kw["sample_rate"] = SAMPLE_RATE
    if "mic" in params:
        kw["mic"] = mic
    if "conditions" in params:
        kw["conditions"] = conditions
        kw["add"] = bool(add)
        kw["strong"] = _strong(emb)
    return jarvis_voice.enroll(clips, embedder=emb, **kw)


def _takes(fn, name: str) -> bool:
    import inspect
    try:
        return name in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def _takes_mic(fn) -> bool:
    """Whether a callable takes (clips, mic) - the real ones do; a test's
    one-argument stand-in does not, and is called the old way."""
    import inspect
    try:
        inspect.signature(fn).bind(None, "")
        return True
    except (TypeError, ValueError):
        return False


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-voice-enroll", daemon=True).start()


def _wake_verifier(clips: list, mic: str = "", keep_old: bool = False) -> str:
    """Builds the "hey Jarvis" verifier from the approved clips (16 kHz PCM
    bytes) and saves it beside the voice print. Returns one line for the
    outcome. Never raises: this must never undo an approved enrolment.

    `keep_old` ("train more", which ADDS to a print): an old verifier still
    describes the same voice, so when these clips cannot build a new one,
    the old one stays."""
    try:
        import numpy as np
        import jarvis_wakeword as W
    except Exception:
        return "not built: the wake-word module is not installed"
    p = None
    try:
        p = W.verifier_path(mic)
        if mic == "phone" and not keep_old:
            # The phone's new print replaces the old single one (jarvis_voice
            # .enroll); the old verifier described that voice, so it goes too.
            _drop(W.verifier_path(""))
        samples = [np.frombuffer(bytes(c[: len(c) // 2 * 2]), dtype="<i2")
                   .astype(np.float32) / 32768.0 for c in clips]
        out = W.build_verifier(samples, SAMPLE_RATE, mic=mic)
        if not out.get("built"):
            if keep_old and p.is_file():
                return ("kept the one you had: " + str(out.get("why", "no reason given"))[:140])
            _drop(p)
            return "not built: " + str(out.get("why", "no reason given"))[:160]
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(out["doc"]), encoding="utf-8")
        tmp.replace(p)
        return f"built from {out['clips']} \"hey Jarvis\" sentences"
    except Exception as exc:
        if p is not None and not keep_old:
            _drop(p)
        return f"not built ({type(exc).__name__})"


def _drop(p) -> None:
    """Removes a verifier that no longer matches the voice print."""
    try:
        p.unlink()
    except (FileNotFoundError, OSError):
        pass


def _finish(pid: str, outcome: str, **extra) -> dict:
    """Records the outcome and DROPS THE CLIPS. Every path ends here."""
    global _PENDING, _LAST
    with _LOCK:
        if _PENDING is not None and _PENDING["id"] == pid:
            _PENDING["clips"].clear()
            _PENDING = None
        _LAST = {"outcome": outcome, "at": time.time(), **extra}
        last = dict(_LAST)
    _audit("voice.training.decided", {"outcome": outcome,
                                      **{k: v for k, v in extra.items()
                                         if k in ("samples", "request_id")}})
    return last


def _note_last(pid_outcome: str, **extra) -> None:
    """Adds to the last outcome, if it is still the one named."""
    with _LOCK:
        if _LAST is not None and _LAST.get("outcome") == pid_outcome:
            _LAST.update(extra)


def _where_clips(outliers: list, index: list) -> list:
    """Enrolment's left-out clips (0-based, in staged order) as the app
    numbers them: [{"round": 2, "clip": 5}] - clip counted from 1 within
    its round - so it can ask for exactly those to be recorded again."""
    out = []
    for i in outliers or []:
        if isinstance(i, int) and 0 <= i < len(index):
            r, n = index[i]
            out.append({"round": int(r), "clip": int(n)})
        elif isinstance(i, int) and not index:
            out.append({"round": 1, "clip": i + 1})
    return out


def _decide(pid: str, *, gate: Callable, enroll: Callable,
            wake_check: Callable = _wake_verifier) -> dict:
    """Raise the card for staged set `pid`, wait for the answer, act on it.
    Blocks - runs on its own thread (see stage)."""
    global _PENDING
    with _LOCK:
        p = _PENDING if (_PENDING and _PENDING["id"] == pid) else None
        if p is None:
            return {"outcome": "gone"}
        count, seconds, mic = p["count"], p["seconds"], p.get("mic", "")
        rounds, add = len(p.get("rounds") or [1]), bool(p.get("add"))
    text = describe(count, seconds, mic, rounds=rounds, add=add)
    # Counts and lengths only. The gate stores `detail` on the approvals row
    # and an audit line; neither is a place for audio.
    detail = {"text": text, "clips": count, "seconds": seconds, "mic": mic,
              "rounds": rounds, "add": add,
              "what": ("add to the enrolled owner voice print" if add else
                       "replace the enrolled owner voice print")}
    try:
        try:
            v = gate(ACTION, detail, text)
        except Exception as exc:
            return _finish(pid, "refused",
                           reason=f"the approval gate failed ({type(exc).__name__})")
        vtier = getattr(v, "tier", "unknown")
        allowed = getattr(v, "allowed", False) is True
        outcome = getattr(v, "outcome", None)
        if outcome is None:
            # A gate from before gate-outcome.patch: only allowed-on-ask can
            # be read as a person saying yes.
            outcome = "approved" if (allowed and vtier == "ask") else "refused"
        rid = getattr(v, "request_id", None)
        if vtier != "ask":
            return _finish(pid, "refused", request_id=rid,
                           reason=f"the gate answered at tier {vtier!r}, which "
                                  f"is not a person saying yes")
        if not (allowed and outcome == "approved"):
            if outcome in ("denied", "timed_out"):
                return _finish(pid, outcome, request_id=rid)
            return _finish(pid, "refused", request_id=rid,
                           reason=str(getattr(v, "reason", "refused"))[:200])
        with _LOCK:
            mine = _PENDING if (_PENDING and _PENDING["id"] == pid) else {}
            clips = list(mine.get("clips", []))
            mic = mine.get("mic", "")
            conditions = list(mine.get("conditions") or [])
            index = list(mine.get("index") or [])
        if not clips:
            return _finish(pid, "failed", request_id=rid,
                           reason="the recordings were gone")
        try:
            try:
                if _takes(enroll, "conditions"):
                    prof = enroll(clips, mic, conditions=conditions or None, add=add)
                else:
                    prof = enroll(clips, mic) if _takes_mic(enroll) else enroll(clips)
            except Exception as exc:
                # ValueError from enroll() is its own plain sentence ("no
                # usable audio in those clips"); anything else is named, not
                # quoted.
                why = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                bad = _where_clips(getattr(exc, "outliers", []), index)
                return _finish(pid, "failed", request_id=rid, reason=why[:200],
                               **({"outliers": bad} if bad else {}))
            # Enrolled: said at once, so the phone stops showing "waiting for
            # the card" while the "hey Jarvis" check is built - from the same
            # approved clips, under the same card, taking up to a minute.
            bad = _where_clips(getattr(prof, "outliers", []) or [], index)
            subs = getattr(prof, "subprints", None)
            done = _finish(pid, "enrolled", request_id=rid,
                           samples=int(getattr(prof, "samples", 0) or 0),
                           embedder=str(getattr(prof, "embedder", "")),
                           added=add, outliers=bad,
                           subprints=([sp["condition"] for sp in
                                       subs(str(getattr(prof, "embedder", "")))]
                                      if callable(subs) else []),
                           wake_check="being built from the same sentences")
            if _takes(wake_check, "keep_old"):
                wake = str(wake_check(clips, mic, keep_old=add))
            else:
                wake = str(wake_check(clips, mic) if _takes_mic(wake_check) else wake_check(clips))
            _note_last(pid_outcome="enrolled", wake_check=wake)
            return {**done, "wake_check": wake}
        finally:
            clips.clear()
    finally:
        # Belt and braces: whatever happened above, the staged audio is gone.
        with _LOCK:
            if _PENDING is not None and _PENDING["id"] == pid:
                _PENDING["clips"].clear()
                _PENDING = None


def stage(body: bytes, *, gate: Optional[Callable] = None,
          tier_of: Optional[Callable[[str], str]] = None,
          enroll: Optional[Callable] = None,
          spawn: Optional[Callable] = None,
          wake_check: Optional[Callable] = None,
          ready: Optional[Callable[[], str]] = None,
          measure_fn: Optional[Callable] = None) -> tuple:
    """POST /api/voice/enroll. Returns (http_status, payload).

    Checks the clips, stores them in memory, raises ONE card on a background
    thread, and returns at once. Enrols nothing - see the module docstring.

    `ready` says why a training cannot be useful here ("" when it can). By
    default that is "no voice-ID model installed" - but only on the real
    path: a caller that brings its own `enroll` brings its own embedder.
    """
    global _PENDING
    real = enroll is None
    gate = gate or _gate
    tier_of = tier_of or _tier_of
    enroll = enroll or _enroll
    wake_check = wake_check or _wake_verifier
    spawn = spawn or _spawn
    ready = ready or (_model_missing if real else (lambda: ""))

    try:
        doc = _doc(body)
    except BadClip as exc:
        return 400, {"error": str(exc)}
    mode = str(doc.get("mode", "enroll") or "enroll").strip().lower()
    if mode == "calibrate":
        # Changes nothing, raises no card: allowed while a card waits.
        return calibrate(doc)
    if mode == "measure":
        # The same: scores, no card.
        return measure(doc, measure_fn=measure_fn)
    if mode in ("strictness", "privacy", "memory", "sensitive_memory", "hands_free"):
        # Tightening is allowed while a card waits; loosening checks itself.
        return stage_setting(doc, mode, gate=gate, tier_of=tier_of, spawn=spawn)
    if mode not in ("enroll", "threshold", "train"):
        return 400, {"error": f"unknown mode {mode[:20]!r}"}
    if mode == "train" and doc.get("cancel") is True:
        return cancel_session()

    with _LOCK:
        if _PENDING is not None:
            left = max(0, int(_PENDING["since"] + _PENDING["timeout"] - time.time()))
            return 409, {"error": ("a voice training is already waiting for "
                                   "approval - approve or deny that card first"),
                         "pending": True, "expires_in": left}

    if mode == "threshold":
        return stage_threshold(doc, gate=gate, tier_of=tier_of, spawn=spawn)
    try:
        why = ready()
    except Exception as exc:
        why = f"the voice check could not be loaded ({type(exc).__name__})"
    if why:
        # Before any card, and before the clips are even read: with only the
        # basic check every voice is refused, so training it would ask the
        # owner to approve something that cannot work.
        return 409, {"error": why, "pending": False, "needs_model": True}
    if mode == "train":
        return stage_round(doc, gate=gate, tier_of=tier_of, enroll=enroll,
                           spawn=spawn, wake_check=wake_check)
    mic = _mic(doc)
    try:
        clips = _parse(doc)
    except BadClip as exc:
        return 400, {"error": str(exc)}
    # The one-shot training (every phone before rounds): one round, in
    # normal conditions.
    return _start_card(mic, doc.get("add") is True, {1: clips}, gate=gate,
                       tier_of=tier_of, enroll=enroll, spawn=spawn,
                       wake_check=wake_check)


def _start_card(mic: str, add: bool, rounds: dict, *, gate, tier_of, enroll, spawn,
                wake_check) -> tuple:
    """Stages the clips of `rounds` ({round: [(pcm, seconds)]}) and raises
    ONE card for all of them. Enrols nothing."""
    global _PENDING
    try:
        tier = tier_of(ACTION)
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        # Checked BEFORE a card is raised: a card that could not end in a
        # person deciding should not be raised at all.
        for got in rounds.values():
            got.clear()
        return 409, {"error": (f"{ACTION} is tier {tier!r} in "
                               f"jarvis-framework.toml; replacing your voice "
                               f"needs a person to say yes, so it must be "
                               f"'ask'. The recordings were deleted."), "pending": False}

    pid = uuid.uuid4().hex
    flat, conditions, index = [], [], []
    for r in sorted(rounds):
        for n, (pcm, _secs) in enumerate(rounds[r], 1):
            flat.append(pcm)
            conditions.append(ROUNDS.get(r, ROUNDS[1])[0])
            index.append((r, n))
    count = len(flat)
    seconds = round(sum(s for got in rounds.values() for _, s in got), 1)
    with _LOCK:
        if _PENDING is not None:        # lost a race with another request
            return 409, {"error": ("a voice training is already waiting for "
                                   "approval - approve or deny that card first"),
                         "pending": True}
        _PENDING = {"id": pid, "clips": flat, "conditions": conditions, "index": index,
                    "rounds": sorted(rounds), "add": bool(add),
                    "count": count, "seconds": seconds, "mic": mic,
                    "kind": "enroll", "since": time.time(), "timeout": _timeout()}
    for got in rounds.values():
        got.clear()
    _audit("voice.training.staged", {"clips": count, "seconds": seconds,
                                     "rounds": len(rounds), "add": bool(add)})

    def work():
        try:
            _decide(pid, gate=gate, enroll=enroll, wake_check=wake_check)
        except Exception:
            _finish(pid, "failed", reason="unexpected error")

    try:
        spawn(work)
    except Exception as exc:
        _finish(pid, "failed", reason=f"could not start ({type(exc).__name__})")
        return 500, {"error": "could not raise the approval card"}
    with _LOCK:
        waiting = _PENDING is not None and _PENDING["id"] == pid
    return 202, {"ok": True, "pending": waiting, "clips": count,
                 "seconds": seconds, "rounds": len(rounds),
                 "message": ("Approve the card on your PC or phone to finish. "
                             "Nothing changes until you do.")}


# --------------------------------------------------------------------------
#   Training in rounds: held in memory until "finish", then ONE card
# --------------------------------------------------------------------------

def _session_view(sess: Optional[dict], now: Optional[float] = None) -> Optional[dict]:
    """Counts and times only - never the clips."""
    if sess is None:
        return None
    now = time.time() if now is None else now
    rounds = [{"round": r, "condition": ROUNDS[r][0],
               "clips": len(sess["rounds"][r]),
               "seconds": round(sum(s for _, s in sess["rounds"][r]), 1)}
              for r in sorted(sess["rounds"])]
    return {"mic": sess["mic"], "add": sess["add"], "rounds": rounds,
            "clips": sum(x["clips"] for x in rounds),
            "seconds": round(sum(x["seconds"] for x in rounds), 1),
            "expires_in": max(0, int(sess["touched"] + SESSION_SECONDS - now))}


def _drop_session_locked(outcome: str = "") -> None:
    """Deletes every held clip. Called with _LOCK held."""
    global _SESSION, _LAST
    if _SESSION is None:
        return
    for got in _SESSION["rounds"].values():
        got.clear()
    _SESSION["rounds"].clear()
    _SESSION = None
    if outcome:
        _LAST = {"outcome": outcome, "at": time.time()}


def expire_sessions(now: Optional[float] = None) -> bool:
    """Drops held rounds that are older than SESSION_SECONDS. True if it
    dropped some. Run by a timer after each round, and on every call."""
    now = time.time() if now is None else now
    with _LOCK:
        if _SESSION is not None and now - _SESSION["touched"] > SESSION_SECONDS:
            _drop_session_locked("expired")
            gone = True
        else:
            gone = False
    if gone:
        _audit("voice.training.expired", {})
    return gone


def _arm_expiry() -> None:
    t = threading.Timer(SESSION_SECONDS + 1.0, expire_sessions)
    t.daemon = True
    t.start()


def cancel_session() -> tuple:
    """{"mode": "train", "cancel": true}: every held clip is deleted."""
    with _LOCK:
        had = _SESSION is not None
        _drop_session_locked("cancelled" if had else "")
    if had:
        _audit("voice.training.cancelled", {})
    return 200, {"ok": True, "cancelled": had,
                 "message": ("The recordings were deleted." if had else
                             "There was nothing held to delete.")}


def stage_round(doc: dict, *, gate, tier_of, enroll, spawn, wake_check,
                arm: Optional[Callable[[], None]] = None) -> tuple:
    """{"mode": "train", "round": n, "clips": [...], "finish": bool}. Holds
    the round (replacing an earlier take of the same round); with `finish`,
    raises ONE card for every held round."""
    global _SESSION
    mic = _mic(doc)
    add = doc.get("add") is True
    finish = doc.get("finish") is True
    r = doc.get("round", 1)
    if isinstance(r, bool) or not isinstance(r, int) or r not in ROUNDS:
        return 400, {"error": f"round must be one of {', '.join(str(k) for k in ROUNDS)}"}
    has = doc.get("clips") is not None
    clips = []
    if has:
        try:
            clips = _parse(doc)
        except BadClip as exc:
            return 400, {"error": str(exc), "round": r}
    expire_sessions()
    now = time.time()
    with _LOCK:
        sess = _SESSION
        if sess is not None and (sess["mic"] != mic or sess["add"] != add):
            view = _session_view(sess, now)
            clips.clear()
            return 409, {"error": ("another training is being recorded (for "
                                   f"{_MIC_WORDS.get(sess['mic'], 'your microphones')}"
                                   f"{', adding' if sess['add'] else ''}) - finish it or "
                                   "cancel it first"), "session": view}
        if not has and not finish:
            return 400, {"error": 'send {"mode": "train", "round": 1, "clips": [...]}'}
        if not has and (sess is None or not sess["rounds"]):
            return 400, {"error": "nothing has been recorded yet to finish"}
        if sess is None:
            sess = {"id": uuid.uuid4().hex, "mic": mic, "add": add, "rounds": {},
                    "touched": now}
        if has:
            old = sess["rounds"].pop(r, None)
            if old:
                old.clear()
            sess["rounds"][r] = clips
        sess["touched"] = now
        if finish:
            _SESSION = None
            take = sess
        else:
            _SESSION = sess
            view = _session_view(sess, now)
            # Worked out here, under the lock: once it is released another
            # request (a cancel, say) may change the held rounds.
            nxt = next((k for k in sorted(ROUNDS) if k not in sess["rounds"]), None)
    if not finish:
        (arm or _arm_expiry)()
        _audit("voice.training.round", {"round": r, "held": view["clips"]})
        return 200, {"ok": True, "pending": False, "held": view, "round": r,
                     "next_round": nxt,
                     "next_ask": ROUNDS[nxt][1] if nxt else "",
                     "message": (f"Round {r} is kept on your PC, in memory only. "
                                 + (f"Next: round {nxt}, {ROUNDS[nxt][1]}. " if nxt else "")
                                 + "Nothing changes until you finish and approve the card.")}
    rounds = dict(take["rounds"])
    return _start_card(take["mic"], take["add"], rounds, gate=gate, tier_of=tier_of,
                       enroll=enroll, spawn=spawn, wake_check=wake_check)


def state() -> dict:
    """For /api/voice/status (gate.training). Counts and times only."""
    expire_sessions()
    with _LOCK:
        p = _PENDING
        # `calibrate`: this PC understands mode calibrate/threshold. The
        # phone offers the "someone else" check only when it sees this - an
        # older PC would stage those clips as a training. The same for the
        # modes added 2026-09-24: `rounds` (mode train), `settings` (modes
        # strictness and privacy), `measure`.
        out = {"available": True, "pending": p is not None, "calibrate": True,
               "rounds": True, "settings": True, "measure": True}
        if p is not None:
            out["clips"] = p.get("count", 0)
            out["kind"] = p.get("kind", "enroll")
            out["expires_in"] = max(0, int(p["since"] + p["timeout"] - time.time()))
            if p.get("kind") == "setting":
                out["setting"] = {"name": p.get("key"), "value": p.get("value")}
        if _LAST is not None:
            out["last"] = {k: _LAST[k] for k in ("outcome", "at", "samples", "reason",
                                                 "wake_check", "threshold", "mic",
                                                 "outliers", "added", "subprints",
                                                 "setting", "value", "model")
                           if k in _LAST}
        out["session"] = _session_view(_SESSION)
        if _LAST_MEASURE is not None:
            out["measure_last"] = dict(_LAST_MEASURE)
    out["limits"] = {"min_clips": MIN_CLIPS, "max_clips": MAX_CLIPS,
                     "min_seconds": MIN_SECONDS, "max_seconds": MAX_SECONDS,
                     "max_total_seconds": MAX_TOTAL_SECONDS,
                     "rounds": len(ROUNDS), "session_seconds": SESSION_SECONDS,
                     "measure_max_clips": MEASURE_MAX_CLIPS}
    out["round_asks"] = {str(k): v[1] for k, v in ROUNDS.items()}
    return out


# --------------------------------------------------------------------------
#   Strictness and private answers: tighten at once, loosen with a card
# --------------------------------------------------------------------------

_SETTING_WORDS = {
    ("strictness", "balanced"): (
        "Make Jarvis's voice check less strict? From \"very strict\" to \"balanced\".\n\n"
        "Balanced checks your voice at a lower bar, and takes shorter sentences. You "
        "will be asked to repeat yourself less often - and someone whose voice is close "
        "to yours gets through more easily too. Private answers (email, calendar, "
        "notes) will be shown on screen only, never read aloud: that goes with "
        "balanced.\n\n"
        "If you did not just do this, say no.\n\n"
        "If you say no: nothing changes, and it stays very strict."),
    ("privacy", "voice_is_enough"): (
        "Let Jarvis read private answers aloud when you ask by voice?\n\n"
        "Email, your calendar, your notes and what Jarvis remembers about you would be "
        "spoken out loud whenever your voice passes the very strict check. Anyone near "
        "the speaker will hear them. This is only allowed while the check is very "
        "strict; making it less strict later turns this off again.\n\n"
        "If you did not just do this, say no.\n\n"
        "If you say no: nothing changes - private answers stay on your screen."),
    ("memory", "memory_aloud"): (
        "Let Jarvis read answers that use what it remembers about you aloud, when you "
        "ask by voice?\n\n"
        "Anyone near the speaker will hear them. Questions about email, your calendar, "
        "your notes, health or money still stay on your screen.\n\n"
        "If you did not just do this, say no.\n\n"
        "If you say no: nothing changes - those answers stay on your screen."),
    # The owner's decision, 2026-09-24: answers that use a sensitive saved
    # fact stay on screen unless this card is approved.
    ("sensitive_memory", "sensitive_aloud"): (
        "Let Jarvis read answers that use a saved fact about your health, money, "
        "passwords or other people's private details aloud, when you ask by voice?\n\n"
        "Anyone near the speaker will hear them.\n\n"
        "If you did not just do this, say no.\n\n"
        "If you say no: nothing changes - those answers stay on your screen."),
    # The owner's decision, 2026-09-24: hands-free voice is as trusted as the
    # talk button by default; "only trust the talk button" is the stricter
    # choice, and going back to the default is this card.
    ("hands_free", "same_as_button"): (
        "Let a question started with \"Hey Jarvis\" count the same as pressing the "
        "talk button?\n\n"
        "Then a recording or a copy of your voice played near the microphone could "
        "have Jarvis remember things, or read memory and private answers aloud.\n\n"
        "If you did not just do this, say no.\n\n"
        "If you say no: nothing changes - \"Hey Jarvis\" questions stay on the "
        "stricter setting."),
}


def _voice():
    import jarvis_voice
    if not hasattr(jarvis_voice, "set_setting"):
        raise ImportError("jarvis_voice.py is older than the strictness settings")
    return jarvis_voice


def settings_view() -> dict:
    try:
        v = _voice()
    except Exception:
        return {}
    s = v.settings()
    return {"strictness": s["strictness"], "privacy": s["privacy"],
            "memory": s.get("memory", ""),
            # "" from a jarvis_voice.py older than this setting.
            "sensitive_memory": s.get("sensitive_memory", ""),
            "hands_free": s.get("hands_free", ""),
            "voice_is_enough_allowed": s["strictness"] == v.VERY_STRICT}


def _withdraw(key: str) -> None:
    """A waiting card that would loosen `key` will do nothing if approved:
    the owner has just asked for the strict value. (The card stays on
    screen - the gate has no call to take one back - and says so when
    answered: outcome "withdrawn".)"""
    with _LOCK:
        if (_PENDING is not None and _PENDING.get("kind") == "setting"
                and _PENDING.get("key") == key):
            _PENDING["withdrawn"] = True


def stage_setting(doc: dict, key: str, *, gate: Callable, tier_of: Callable,
                  spawn: Callable) -> tuple:
    """{"mode": "strictness"|"privacy"|"memory"|"sensitive_memory"|"hands_free",
    "value": ...}.
    Tightening applies at once; loosening raises ONE card and changes nothing
    itself. A jarvis_voice.py older than the setting: 503, in words."""
    global _PENDING
    try:
        V = _voice()
    except Exception:
        return 503, {"error": "the voice check on this PC is too old for this setting "
                              "(run the patch script)"}
    if key not in V._CHOICES:
        return 503, {"error": "the voice check on this PC is too old for this setting "
                              "(run the patch script)"}
    value = doc.get("value")
    if not isinstance(value, str) or value not in V._CHOICES[key]:
        return 400, {"error": f"send {{\"mode\": \"{key}\", \"value\": "
                              + " or ".join(f'\"{c}\"' for c in V._CHOICES[key]) + "}"}
    cur = V.settings()
    if cur[key] == value:
        if value != V.LOOSER[key]:
            # Already strict - and saying so again still withdraws a waiting
            # card that would loosen it (see below).
            _withdraw(key)
        return 200, {"ok": True, "changed": False, "pending": False,
                     "settings": settings_view()}
    if not V.is_loosening(key, value):
        # Tightening: at once, no card - it only narrows who Jarvis obeys or
        # what it says aloud. It also withdraws a waiting card that would
        # loosen the same setting: approving that card later does nothing.
        try:
            V.set_setting(key, value)
        except (OSError, ValueError) as exc:
            return 500, {"error": f"could not save the setting ({type(exc).__name__})"}
        _withdraw(key)
        _audit("voice.setting.tightened", {"setting": key, "value": value})
        return 200, {"ok": True, "changed": True, "pending": False,
                     "settings": settings_view(),
                     "message": "Done - that applies now."}
    if key == "privacy" and cur["strictness"] != V.VERY_STRICT:
        return 409, {"error": ("private answers can only be read aloud while the voice "
                               "check is very strict - make it very strict first"),
                     "pending": False}
    with _LOCK:
        if _PENDING is not None:
            left = max(0, int(_PENDING["since"] + _PENDING["timeout"] - time.time()))
            return 409, {"error": ("a voice card is already waiting for approval - "
                                   "approve or deny that one first"),
                         "pending": True, "expires_in": left}
    try:
        tier = tier_of(ACTION)
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        return 409, {"error": (f"{ACTION} is tier {tier!r} in jarvis-framework.toml; "
                               f"making the voice check looser needs a person to say "
                               f"yes, so it must be 'ask'"), "pending": False}
    pid = uuid.uuid4().hex
    with _LOCK:
        if _PENDING is not None:
            return 409, {"error": ("a voice card is already waiting for approval - "
                                   "approve or deny that one first"), "pending": True}
        _PENDING = {"id": pid, "clips": [], "count": 0, "seconds": 0.0, "mic": "",
                    "kind": "setting", "key": key, "value": value,
                    "since": time.time(), "timeout": _timeout()}

    def work():
        try:
            _decide_setting(pid, gate=gate)
        except Exception:
            _finish(pid, "failed", reason="unexpected error")

    try:
        spawn(work)
    except Exception as exc:
        _finish(pid, "failed", reason=f"could not start ({type(exc).__name__})")
        return 500, {"error": "could not raise the approval card"}
    return 202, {"ok": True, "pending": True, "setting": key, "value": value,
                 "message": ("Approve the card on your PC or phone to use the new "
                             "setting. Nothing changes until you do.")}


def _decide_setting(pid: str, *, gate: Callable) -> dict:
    with _LOCK:
        p = _PENDING if (_PENDING and _PENDING["id"] == pid) else None
        if p is None:
            return {"outcome": "gone"}
        key, value = p["key"], p["value"]
    text = _SETTING_WORDS[(key, value)]
    detail = {"text": text, "setting": key, "to": value,
              "what": "make the owner voice check looser"}
    try:
        v = gate(ACTION, detail, text)
    except Exception as exc:
        return _finish(pid, "refused", reason=f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    rid = getattr(v, "request_id", None)
    if vtier != "ask":
        return _finish(pid, "refused", request_id=rid, setting=key, value=value,
                       reason=f"the gate answered at tier {vtier!r}, which is not a person saying yes")
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, outcome, request_id=rid, setting=key, value=value)
        return _finish(pid, "refused", request_id=rid, setting=key, value=value,
                       reason=str(getattr(v, "reason", "refused"))[:200])
    with _LOCK:
        withdrawn = bool(_PENDING and _PENDING["id"] == pid and _PENDING.get("withdrawn"))
    if withdrawn:
        return _finish(pid, "withdrawn", request_id=rid, setting=key, value=value,
                       reason="you made it stricter again while the card waited")
    try:
        _voice().set_setting(key, value, approved=True)
    except Exception as exc:
        why = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        return _finish(pid, "failed", request_id=rid, setting=key, value=value,
                       reason=why[:200])
    return _finish(pid, "setting_changed", request_id=rid, setting=key, value=value)


# --------------------------------------------------------------------------
#   The guided repeat test
# --------------------------------------------------------------------------

def _speech_seconds(pcm: bytes) -> float:
    """How much of a clip is speech, the way hear() measures it (the VAD's
    span), or the whole clip when the VAD is not installed."""
    whole = len(pcm) / 2 / SAMPLE_RATE
    try:
        import numpy as np
        import jarvis_speech
        x = np.frombuffer(bytes(pcm[: len(pcm) // 2 * 2]), dtype="<i2").astype(np.float32) / 32768.0
        span = jarvis_speech._speech_span(x, SAMPLE_RATE)
    except Exception:
        return whole
    if span is None:
        return 0.0
    if span == "skip":
        return whole
    return (span[1] - span[0]) / float(SAMPLE_RATE)


def measure(doc: dict, *, measure_fn: Optional[Callable] = None) -> tuple:
    """mode "measure": up to MEASURE_MAX_CLIPS of the owner's own sentences,
    each judged at both strictness settings. Scored and dropped; no card;
    nothing counted as real use."""
    global _LAST_MEASURE
    mic = _mic(doc)
    try:
        clips = _parse(doc, 1, MEASURE_MAX_CLIPS)
    except BadClip as exc:
        return 400, {"ok": False, "error": str(exc)}
    pcm = [c for c, _ in clips]
    clips.clear()
    try:
        if measure_fn is not None:
            got = measure_fn(pcm, mic)
        else:
            try:
                V = _voice()
            except Exception:
                return 503, {"ok": False, "error": "the voice check on this PC is too old "
                                                   "for this test (run the patch script)"}
            got = V.measure(pcm, _embedder(), SAMPLE_RATE, mic,
                            seconds=[_speech_seconds(c) for c in pcm])
    except Exception as exc:
        return 500, {"ok": False, "error": type(exc).__name__}
    finally:
        pcm.clear()
    if not got.get("ok"):
        return 409, {"ok": False, "error": str(got.get("why", "could not check"))}
    keep = {"at": time.time(), "clips": got["clips"],
            "strong_model": bool(got.get("strong_model"))}
    for s in ("very_strict", "balanced"):
        keep[s] = {k: got[s][k] for k in ("passed", "of", "too_short", "repeat_rate")}
    with _LOCK:
        _LAST_MEASURE = keep
    _audit("voice.training.measured", {"clips": got["clips"],
                                       "very_strict": got["very_strict"]["passed"],
                                       "balanced": got["balanced"]["passed"]})
    vs, ba, n = got["very_strict"]["passed"], got["balanced"]["passed"], got["clips"]
    return 200, {**got, "message": (f"Very strict let {vs} of {n} through; balanced "
                                    f"{ba} of {n}.")}


# --------------------------------------------------------------------------
#   "Someone else": scores only, and the card that uses them
# --------------------------------------------------------------------------

def calibrate(doc: dict, *, score=None) -> tuple:
    """mode "calibrate": another person's clips against the owner's print.
    Scored, answered, dropped - nothing stored, nothing changed, no card."""
    mic = _mic(doc)
    try:
        clips = _parse(doc, MIN_OTHER_CLIPS, MAX_OTHER_CLIPS)
    except BadClip as exc:
        return 400, {"ok": False, "error": str(exc)}
    try:
        import jarvis_voice
    except Exception:
        return 503, {"ok": False, "error": "the voice check is not installed on this PC"}
    pcm = [c for c, _ in clips]
    clips.clear()
    try:
        if score is None:
            emb = _embedder()
            if not getattr(emb, "semantic", False) and hasattr(jarvis_voice, "NO_MODEL_REASON"):
                return 409, {"ok": False, "error": jarvis_voice.NO_MODEL_REASON}
            got = jarvis_voice.score_clips(pcm, emb, SAMPLE_RATE, mic)
        else:
            got = score(pcm, mic)
    except Exception as exc:
        return 500, {"ok": False, "error": type(exc).__name__}
    finally:
        pcm.clear()
    if not got.get("ok"):
        return 409, {"ok": False, "error": str(got.get("why", "could not compare"))}
    theirs = [s for s in got["scores"] if isinstance(s, (int, float))]
    try:
        floor = float(got.get("floor", jarvis_voice.MIN_THRESHOLD))
        sug = jarvis_voice.suggest_threshold(got.get("owner_scores", []), theirs, floor=floor)
    except TypeError:       # a jarvis_voice.py from before the floor
        sug = jarvis_voice.suggest_threshold(got.get("owner_scores", []), theirs)
    current = float(got.get("threshold", 0.0))
    # With the stricter check a clip can clear the bar and still be refused
    # (the stronger model, or the comparison voices): `passed` is what the
    # check itself said, when it says it.
    verdicts = got.get("passed")
    if isinstance(verdicts, list) and len(verdicts) == len(got["scores"]):
        passed = sum(1 for x in verdicts if x is True)
    else:
        verdicts = None
        passed = sum(1 for s in theirs if s >= current)
    if sug["separated"]:
        msg = (f"Your own training clips all scored {sug['owner_low']:.2f} or more; "
               f"theirs {sug['others_high']:.2f} at most.")
    else:
        msg = sug["why"][:1].upper() + sug["why"][1:] + "."
    _audit("voice.training.checked", {"clips": len(got["scores"]), "passed": passed})
    return 200, {"ok": True, "scores": got["scores"], "threshold": current,
                 "owner_low": sug.get("owner_low", 0.0),
                 "others_high": sug.get("others_high", 0.0),
                 "separated": bool(sug["separated"]), "suggested": sug["suggested"],
                 "print": got.get("print", ""), "message": msg,
                 "passed": verdicts, "passed_count": passed,
                 "strictness": str(got.get("strictness", "")),
                 # Which model `scores` and `suggested` are for - send it back
                 # with mode "threshold" so the card sets that model's bar.
                 "model": str(got.get("model", "small"))}


def stage_threshold(doc: dict, *, gate: Callable, tier_of: Callable,
                    spawn: Callable, apply: Optional[Callable] = None) -> tuple:
    """mode "threshold": ONE card to use a new bar for `mic`'s print."""
    global _PENDING
    mic = _mic(doc)
    raw = doc.get("threshold")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
        return 400, {"error": "send {\"mode\": \"threshold\", \"threshold\": 0.5}"}
    try:
        import jarvis_voice
    except Exception:
        return 503, {"error": "the voice check is not installed on this PC"}
    lo, hi = jarvis_voice.MIN_THRESHOLD, jarvis_voice.MAX_SUGGESTED
    if not lo <= float(raw) <= hi:
        return 400, {"error": f"the setting must be between {lo:g} and {hi:g}"}
    prof, _label = jarvis_voice.find_profile(mic)
    if prof is None:
        return 409, {"error": "no voice has been trained yet", "pending": False}
    # Which model's bar (2026-09-24): "small" or "strong", as the "someone
    # else" check named it (`model` in its reply); by default the one that
    # decides - the stronger model when it is installed and in the print.
    name, which = prof.embedder, "small"
    if hasattr(jarvis_voice, "strong_embedder"):
        strong = _strong(_embedder())
        wanted = str(doc.get("model") or "").strip().lower()
        has_strong = strong is not None and bool(prof.subprints(strong.name))
        if wanted == "strong" and not has_strong:
            return 409, {"error": ("the stronger voice-ID model is not installed, or your "
                                   "voice print has nothing from it yet"), "pending": False}
        if has_strong and wanted != "small":
            name, which = strong.name, "strong"
    floor_for = getattr(jarvis_voice, "floor_for", None)
    if floor_for is not None:
        # Hole 2 (2026-09-24): no bar below the model's own floor - not by
        # enrolment, and not by a card either.
        lowest = floor_for(name, "balanced")
        if float(raw) < lowest:
            return 400, {"error": (f"the lowest this voice check allows is {lowest:.2f} - "
                                   f"below that it would let other people through")}
    new = round(float(raw), 2)
    if which == "strong":
        old = float(prof.thresholds.get(name) or floor_for(name, "balanced"))
    else:
        old = float(prof.threshold)
    try:
        tier = tier_of(ACTION)
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        return 409, {"error": (f"{ACTION} is tier {tier!r} in jarvis-framework.toml; "
                               f"changing how strict Jarvis is about your voice needs "
                               f"a person to say yes, so it must be 'ask'"),
                     "pending": False}
    pid = uuid.uuid4().hex
    with _LOCK:
        if _PENDING is not None:
            return 409, {"error": ("a voice card is already waiting for approval - "
                                   "approve or deny that one first"), "pending": True}
        _PENDING = {"id": pid, "clips": [], "count": 0, "seconds": 0.0, "mic": mic,
                    "kind": "threshold", "threshold": new, "old": old,
                    "model": which, "since": time.time(), "timeout": _timeout()}
    if apply is None:
        if _takes(jarvis_voice.set_threshold, "model"):
            apply = (lambda value, m: jarvis_voice.set_threshold(value, m, model=name))
        else:
            apply = (lambda value, m: jarvis_voice.set_threshold(value, m))

    def work():
        try:
            _decide_threshold(pid, gate=gate, apply=apply)
        except Exception:
            _finish(pid, "failed", reason="unexpected error")

    try:
        spawn(work)
    except Exception as exc:
        _finish(pid, "failed", reason=f"could not start ({type(exc).__name__})")
        return 500, {"error": "could not raise the approval card"}
    return 202, {"ok": True, "pending": True, "threshold": new, "model": which,
                 "message": ("Approve the card on your PC or phone to use the new "
                             "setting. Nothing changes until you do.")}


def _decide_threshold(pid: str, *, gate: Callable, apply: Callable) -> dict:
    with _LOCK:
        p = _PENDING if (_PENDING and _PENDING["id"] == pid) else None
        if p is None:
            return {"outcome": "gone"}
        mic, new, old = p.get("mic", ""), p["threshold"], p["old"]
        which = p.get("model", "small")
    text = describe_threshold(mic, old, new, which)
    detail = {"text": text, "mic": mic, "from": old, "to": new,
              "what": "change how closely a voice must match the owner's"}
    try:
        v = gate(ACTION, detail, text)
    except Exception as exc:
        return _finish(pid, "refused", reason=f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    rid = getattr(v, "request_id", None)
    if vtier != "ask":
        return _finish(pid, "refused", request_id=rid,
                       reason=f"the gate answered at tier {vtier!r}, which is not a person saying yes")
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, outcome, request_id=rid)
        return _finish(pid, "refused", request_id=rid,
                       reason=str(getattr(v, "reason", "refused"))[:200])
    try:
        apply(new, mic)
    except Exception as exc:
        why = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        return _finish(pid, "failed", request_id=rid, reason=why[:200])
    return _finish(pid, "threshold_set", request_id=rid, threshold=new, mic=mic,
                   model=which)


def _reset_for_tests() -> None:
    global _PENDING, _LAST, _LAST_MEASURE
    with _LOCK:
        _PENDING = None
        _LAST = None
        _LAST_MEASURE = None
        _drop_session_locked()
