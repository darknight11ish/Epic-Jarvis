"""jarvis_voice_enroll.py - "Train my voice": clips from the phone, one card, then enrol.

NEW MODULE, shipped whole beside jarvis_hud.py (apply-patches.ps1 copies it).
`voice-enroll.patch` adds the one route that calls it:

    POST /api/voice/enroll   {"clips": ["<base64 WAV>", ...]}
        -> stage(body)       202 {"ok": true, "pending": true, ...}   a card is up
                             400 {"error": "clip 2 ..."}              bad input
                             409 {"error": ..., "pending": true}      one is already waiting
    GET /api/voice/status    gate.training = state()                  (jarvis_speech)

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
#: clip would give it nothing to measure); eight at ten seconds is ~2.6 MB of
#: audio, ~3.4 MB as base64, inside jarvis_hud's 4 MB MAX_BODY.
MIN_CLIPS = 3
MAX_CLIPS = 8
MIN_SECONDS = 1.0
MAX_SECONDS = 10.0
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


def _parse(body: bytes) -> list:
    """The request body -> [(pcm, seconds)], or BadClip with the reason."""
    try:
        doc = json.loads(body.decode("utf-8") if isinstance(body, (bytes, bytearray))
                         else body or "")
    except (UnicodeDecodeError, ValueError):
        raise BadClip('send {"clips": ["<base64 WAV>", ...]}') from None
    clips = doc.get("clips") if isinstance(doc, dict) else None
    if not isinstance(clips, list):
        raise BadClip('send {"clips": ["<base64 WAV>", ...]}')
    if not MIN_CLIPS <= len(clips) <= MAX_CLIPS:
        raise BadClip(f"send between {MIN_CLIPS} and {MAX_CLIPS} clips, not "
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
    return out


# --------------------------------------------------------------------------
#   The card
# --------------------------------------------------------------------------

def describe(count: int, seconds: float) -> str:
    """The card's text. Every word from here - no audio, no transcript, no
    name. What refusing costs is on it, as docs/ARCHITECTURE.md §3 asks."""
    return (
        f"Replace the voice Jarvis listens for with the one just recorded on "
        f"your phone? {count} clips, {seconds:.0f} seconds in all.\n\n"
        f"If you say yes: from now on only a voice that matches these clips "
        f"can talk to Jarvis. Any voice trained before is replaced.\n\n"
        f"If you did not just do this on your phone, say no - someone else "
        f"may be trying to make Jarvis obey their voice.\n\n"
        f"If you say no: nothing changes, and the recordings are deleted."
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


def _enroll(clips: list):
    """The same embedder choice jarvis_speech.hear() makes, so the profile
    this writes is one hear() can compare against - verify() refuses a
    profile made by a different embedder."""
    import inspect
    import jarvis_voice
    try:
        emb = jarvis_voice.EcapaEmbedder()
    except Exception:
        emb = jarvis_voice.Embedder()
    # `sample_rate` only for a jarvis_voice.py new enough to take it: an older
    # copy on the PC would otherwise turn an approved card into a TypeError.
    if "sample_rate" in inspect.signature(jarvis_voice.enroll).parameters:
        return jarvis_voice.enroll(clips, embedder=emb, sample_rate=SAMPLE_RATE)
    return jarvis_voice.enroll(clips, embedder=emb)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-voice-enroll", daemon=True).start()


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


def _decide(pid: str, *, gate: Callable, enroll: Callable) -> dict:
    """Raise the card for staged set `pid`, wait for the answer, act on it.
    Blocks - runs on its own thread (see stage)."""
    global _PENDING
    with _LOCK:
        p = _PENDING if (_PENDING and _PENDING["id"] == pid) else None
        if p is None:
            return {"outcome": "gone"}
        count, seconds = p["count"], p["seconds"]
    text = describe(count, seconds)
    # Counts and lengths only. The gate stores `detail` on the approvals row
    # and an audit line; neither is a place for audio.
    detail = {"text": text, "clips": count, "seconds": seconds,
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
        if not clips:
            return _finish(pid, "failed", request_id=rid,
                           reason="the recordings were gone")
        try:
            prof = enroll(clips)
        except Exception as exc:
            # ValueError from enroll() is its own plain sentence ("no usable
            # audio in those clips"); anything else is named, not quoted.
            why = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            return _finish(pid, "failed", request_id=rid, reason=why[:200])
        finally:
            clips.clear()
        return _finish(pid, "enrolled", request_id=rid,
                       samples=int(getattr(prof, "samples", 0) or 0),
                       embedder=str(getattr(prof, "embedder", "")))
    finally:
        # Belt and braces: whatever happened above, the staged audio is gone.
        with _LOCK:
            if _PENDING is not None and _PENDING["id"] == pid:
                _PENDING["clips"].clear()
                _PENDING = None


def stage(body: bytes, *, gate: Optional[Callable] = None,
          tier_of: Optional[Callable[[str], str]] = None,
          enroll: Optional[Callable] = None,
          spawn: Optional[Callable] = None) -> tuple:
    """POST /api/voice/enroll. Returns (http_status, payload).

    Checks the clips, stores them in memory, raises ONE card on a background
    thread, and returns at once. Enrols nothing - see the module docstring.
    """
    global _PENDING
    gate = gate or _gate
    tier_of = tier_of or _tier_of
    enroll = enroll or _enroll
    spawn = spawn or _spawn

    with _LOCK:
        if _PENDING is not None:
            left = max(0, int(_PENDING["since"] + _PENDING["timeout"] - time.time()))
            return 409, {"error": ("a voice training is already waiting for "
                                   "approval - approve or deny that card first"),
                         "pending": True, "expires_in": left}

    try:
        clips = _parse(body)
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
                    "count": len(clips), "seconds": seconds,
                    "since": time.time(), "timeout": _timeout()}
    clips.clear()
    _audit("voice.training.staged", {"clips": count, "seconds": seconds})

    def work():
        try:
            _decide(pid, gate=gate, enroll=enroll)
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
        out = {"available": True, "pending": p is not None}
        if p is not None:
            out["clips"] = p["count"]
            out["expires_in"] = max(0, int(p["since"] + p["timeout"] - time.time()))
        if _LAST is not None:
            out["last"] = {k: _LAST[k] for k in ("outcome", "at", "samples", "reason")
                           if k in _LAST}
    out["limits"] = {"min_clips": MIN_CLIPS, "max_clips": MAX_CLIPS,
                     "min_seconds": MIN_SECONDS, "max_seconds": MAX_SECONDS}
    return out


def _reset_for_tests() -> None:
    global _PENDING, _LAST
    with _LOCK:
        _PENDING = None
        _LAST = None
