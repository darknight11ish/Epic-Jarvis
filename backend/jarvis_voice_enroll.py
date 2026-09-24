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

_LOCK = threading.Lock()
_PENDING: Optional[dict] = None     # {"id", "clips", "count", "seconds", "since", "timeout"}
_LAST: Optional[dict] = None        # the last outcome, for the phone to show


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


def describe(count: int, seconds: float, mic: str = "") -> str:
    """The card's text. Every word from here - no audio, no transcript, no
    name. What refusing costs is on it, as docs/ARCHITECTURE.md §3 asks."""
    words = _MIC_WORDS.get(mic, _MIC_WORDS[""])
    where = _MIC_WHERE.get(mic, _MIC_WHERE[""])
    return (
        f"Replace the voice Jarvis listens for on {words} with the one just "
        f"recorded {where}? {count} clips, {seconds:.0f} seconds in all.\n\n"
        f"If you say yes: from now on only a voice that matches these clips "
        f"can talk to Jarvis through {words}. Any voice trained before for it "
        f"is replaced. The sentences that start with \"hey Jarvis\" also "
        f"teach it how you say that.\n\n"
        f"If you did not just do this {where}, say no - someone else may be "
        f"trying to make Jarvis obey their voice.\n\n"
        f"If you say no: nothing changes, and the recordings are deleted."
    )


def describe_threshold(mic: str, old: float, new: float) -> str:
    """The threshold card. Plain words: what the number does, both ways."""
    words = _MIC_WORDS.get(mic, _MIC_WORDS[""])
    stricter = new > old
    return (
        f"Make Jarvis {'stricter' if stricter else 'less strict'} about your voice "
        f"on {words}? From {old:.2f} to {new:.2f}.\n\n"
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


def _enroll(clips: list, mic: str = ""):
    """The same embedder choice jarvis_speech.hear() makes, so the profile
    this writes is one hear() can compare against - verify() refuses a
    profile made by a different embedder."""
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
    return jarvis_voice.enroll(clips, embedder=emb, **kw)


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


def _wake_verifier(clips: list, mic: str = "") -> str:
    """Builds the "hey Jarvis" verifier from the approved clips (16 kHz PCM
    bytes) and saves it beside the voice print. Returns one line for the
    outcome. Never raises: this must never undo an approved enrolment."""
    try:
        import numpy as np
        import jarvis_wakeword as W
    except Exception:
        return "not built: the wake-word module is not installed"
    p = None
    try:
        p = W.verifier_path(mic)
        if mic == "phone":
            # The phone's new print replaces the old single one (jarvis_voice
            # .enroll); the old verifier described that voice, so it goes too.
            _drop(W.verifier_path(""))
        samples = [np.frombuffer(bytes(c[: len(c) // 2 * 2]), dtype="<i2")
                   .astype(np.float32) / 32768.0 for c in clips]
        out = W.build_verifier(samples, SAMPLE_RATE, mic=mic)
        if not out.get("built"):
            _drop(p)
            return "not built: " + str(out.get("why", "no reason given"))[:160]
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(out["doc"]), encoding="utf-8")
        tmp.replace(p)
        return f"built from {out['clips']} \"hey Jarvis\" sentences"
    except Exception as exc:
        if p is not None:
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
    text = describe(count, seconds, mic)
    # Counts and lengths only. The gate stores `detail` on the approvals row
    # and an audit line; neither is a place for audio.
    detail = {"text": text, "clips": count, "seconds": seconds, "mic": mic,
              "what": "replace the enrolled owner voice print"}
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
            clips = list(_PENDING["clips"]) if (_PENDING and _PENDING["id"] == pid) else []
            mic = _PENDING.get("mic", "") if (_PENDING and _PENDING["id"] == pid) else ""
        if not clips:
            return _finish(pid, "failed", request_id=rid,
                           reason="the recordings were gone")
        try:
            try:
                prof = enroll(clips, mic) if _takes_mic(enroll) else enroll(clips)
            except Exception as exc:
                # ValueError from enroll() is its own plain sentence ("no
                # usable audio in those clips"); anything else is named, not
                # quoted.
                why = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                return _finish(pid, "failed", request_id=rid, reason=why[:200])
            # Enrolled: said at once, so the phone stops showing "waiting for
            # the card" while the "hey Jarvis" check is built - from the same
            # approved clips, under the same card, taking up to a minute.
            done = _finish(pid, "enrolled", request_id=rid,
                           samples=int(getattr(prof, "samples", 0) or 0),
                           embedder=str(getattr(prof, "embedder", "")),
                           wake_check="being built from the same sentences")
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
          wake_check: Optional[Callable] = None) -> tuple:
    """POST /api/voice/enroll. Returns (http_status, payload).

    Checks the clips, stores them in memory, raises ONE card on a background
    thread, and returns at once. Enrols nothing - see the module docstring.
    """
    global _PENDING
    gate = gate or _gate
    tier_of = tier_of or _tier_of
    enroll = enroll or _enroll
    wake_check = wake_check or _wake_verifier
    spawn = spawn or _spawn

    try:
        doc = _doc(body)
    except BadClip as exc:
        return 400, {"error": str(exc)}
    mode = str(doc.get("mode", "enroll") or "enroll").strip().lower()
    if mode == "calibrate":
        # Changes nothing, raises no card: allowed while a card waits.
        return calibrate(doc)
    if mode not in ("enroll", "threshold"):
        return 400, {"error": f"unknown mode {mode[:20]!r}"}

    with _LOCK:
        if _PENDING is not None:
            left = max(0, int(_PENDING["since"] + _PENDING["timeout"] - time.time()))
            return 409, {"error": ("a voice training is already waiting for "
                                   "approval - approve or deny that card first"),
                         "pending": True, "expires_in": left}

    if mode == "threshold":
        return stage_threshold(doc, gate=gate, tier_of=tier_of, spawn=spawn)
    mic = _mic(doc)
    try:
        clips = _parse(doc)
    except BadClip as exc:
        return 400, {"error": str(exc)}

    try:
        tier = tier_of(ACTION)
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        # Checked BEFORE a card is raised: a card that could not end in a
        # person deciding should not be raised at all.
        return 409, {"error": (f"{ACTION} is tier {tier!r} in "
                               f"jarvis-framework.toml; replacing your voice "
                               f"needs a person to say yes, so it must be "
                               f"'ask'"), "pending": False}

    pid = uuid.uuid4().hex
    count = len(clips)
    seconds = round(sum(s for _, s in clips), 1)
    with _LOCK:
        if _PENDING is not None:        # lost a race with another request
            return 409, {"error": ("a voice training is already waiting for "
                                   "approval - approve or deny that card first"),
                         "pending": True}
        _PENDING = {"id": pid, "clips": [pcm for pcm, _ in clips],
                    "count": len(clips), "seconds": seconds, "mic": mic,
                    "kind": "enroll", "since": time.time(), "timeout": _timeout()}
    clips.clear()
    _audit("voice.training.staged", {"clips": count, "seconds": seconds})

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
                 "seconds": seconds,
                 "message": ("Approve the card on your PC or phone to finish. "
                             "Nothing changes until you do.")}


def state() -> dict:
    """For /api/voice/status (gate.training). Counts and times only."""
    with _LOCK:
        p = _PENDING
        # `calibrate`: this PC understands mode calibrate/threshold. The
        # phone offers the "someone else" check only when it sees this - an
        # older PC would stage those clips as a training.
        out = {"available": True, "pending": p is not None, "calibrate": True}
        if p is not None:
            out["clips"] = p.get("count", 0)
            out["kind"] = p.get("kind", "enroll")
            out["expires_in"] = max(0, int(p["since"] + p["timeout"] - time.time()))
        if _LAST is not None:
            out["last"] = {k: _LAST[k] for k in ("outcome", "at", "samples", "reason",
                                                 "wake_check", "threshold", "mic")
                           if k in _LAST}
    out["limits"] = {"min_clips": MIN_CLIPS, "max_clips": MAX_CLIPS,
                     "min_seconds": MIN_SECONDS, "max_seconds": MAX_SECONDS,
                     "max_total_seconds": MAX_TOTAL_SECONDS}
    return out


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
            got = jarvis_voice.score_clips(pcm, _embedder(), SAMPLE_RATE, mic)
        else:
            got = score(pcm, mic)
    except Exception as exc:
        return 500, {"ok": False, "error": type(exc).__name__}
    finally:
        pcm.clear()
    if not got.get("ok"):
        return 409, {"ok": False, "error": str(got.get("why", "could not compare"))}
    theirs = [s for s in got["scores"] if isinstance(s, (int, float))]
    sug = jarvis_voice.suggest_threshold(got.get("owner_scores", []), theirs)
    current = float(got.get("threshold", 0.0))
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
                 "print": got.get("print", ""), "message": msg}


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
    new, old = round(float(raw), 2), float(prof.threshold)
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
                    "since": time.time(), "timeout": _timeout()}
    apply = apply or (lambda value, m: jarvis_voice.set_threshold(value, m))

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
    return 202, {"ok": True, "pending": True, "threshold": new,
                 "message": ("Approve the card on your PC or phone to use the new "
                             "setting. Nothing changes until you do.")}


def _decide_threshold(pid: str, *, gate: Callable, apply: Callable) -> dict:
    with _LOCK:
        p = _PENDING if (_PENDING and _PENDING["id"] == pid) else None
        if p is None:
            return {"outcome": "gone"}
        mic, new, old = p.get("mic", ""), p["threshold"], p["old"]
    text = describe_threshold(mic, old, new)
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
    return _finish(pid, "threshold_set", request_id=rid, threshold=new, mic=mic)


def _reset_for_tests() -> None:
    global _PENDING, _LAST
    with _LOCK:
        _PENDING = None
        _LAST = None
