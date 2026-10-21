"""test_voice_parallel.py - the owner check and speech-to-text run BESIDE
each other, and the words of an unverified clip are still thrown away.

    python3 backend/test_voice_parallel.py

WHAT THIS PROVES (2026-10-20, the voice-latency work order's Opt 3.1). The
owner chose "parallel CAM++ and Parakeet": `jarvis_speech.hear()` used to run
the owner check (~140 ms) and then, only if it passed, the transcription
(~219 ms), one after the other on every spoken clip. They now run at the same
time on the same in-memory audio, so a verified clip costs the longer of the
two - about 140 ms less.

The privacy rule is the part that must not move, and it is tested here on
EVERY sink `hear()` has:

  1. AN UNVERIFIED CLIP NEVER ESCAPES. The transcript is made beside the
     check; when the check says no it is discarded (`text = ""`) and the
     words appear in NOTHING the caller can see - not the returned `Heard`,
     not its `as_dict()` (what `/api/voice/utterance` sends), not the reason,
     not the printed output, not `_note_for_history` (the one door to chat
     history), not `_flow` (the delay table). The worker is joined before
     `hear()` returns, so no thread is left holding the clip either.
  2. A FAILING OWNER CHECK disposes of the words the same way, and `hear()`
     then re-raises exactly as it did when the transcription was inline.
  3. A FAILING TRANSCRIPTION is reported as the same honest "transcription
     failed (NameError)" it was before, never raised into the route.
  4. WITH NO ENGINE INSTALLED no worker is started at all - the old "nothing
     is even attempted for a stranger" behaviour, kept where it applies.
  5. THE CHECK-ONLY PATH OF A LIVE VOICE PAUSE keeps its old serial
     behaviour: checked first, and a passing clip turned into words after.
  6. THE DELAY NUMBER is the transcription's own length, not the short wait
     for a worker that was already running.
  7. THE EARLY WINDOW (2026-10-21, the audit's V1-Path A): the owner check
     is asked on the clip's FIRST ~1.2 s rather than the whole clip. A clear
     answer decides on its own; a score inside the margin is re-checked on
     the FULL clip exactly as before (`_decide_owner`, `_early_decides`).
     The privacy rule does not move: the words are still made beside the
     check and thrown away unread when the answer is no, and a REFUSAL still
     costs the transcription (the worker is joined before `hear()` returns),
     so the caller cannot tell "verified" from "refused" by a short reply.
     `StreamingVerify` is the same rule for a caller that feeds chunks while
     the owner is still speaking: the check starts as soon as a window of
     voice has arrived, so end of speech is answered at once.

The parallelism assertion is a MECHANISM test, not a benchmark: the stand-ins
sleep, and the test checks that the transcription STARTED before the owner
check ENDED (a fact with a wide margin, not a micro-timing), and that the
whole call took clearly less than the two sleeps added together. A machine
under load cannot make it flaky the way a millisecond threshold would.

What CANNOT be tested here, and is not claimed: the real models' speeds. No
CAM++ weights, no Parakeet weights and no microphone exist in this
repository or this container - the ~140 ms saving is the work order's figure
for real hardware (docs/, "NOT-TESTABLE" in the pull request), and what is
proven here is the mechanism that produces it.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import threading
import time
import traceback
import types
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_speech.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-voice-parallel-"))
if "jarvis_framework" not in sys.modules:
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = _TMP
    fw.LOG_DIR = _TMP
    fw.load_framework = lambda: {}
    fw.audit_log = lambda event, detail=None, **k: None
    fw.action_tier = lambda action: "ask"
    sys.modules["jarvis_framework"] = fw

import jarvis_speech as S  # noqa: E402

PASSED, FAILED = [], []
WORKER_NAME = "jarvis-stt-beside-check"
VERIFY_WORKER = "jarvis-verify-beside-check"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def workers_alive():
    return [t for t in threading.enumerate()
            if t.name in (WORKER_NAME, VERIFY_WORKER) and t.is_alive()]


# ---------------------------------------------------------------------------
#   The stand-in world: every engine replaced, so only the ORDER runs
# ---------------------------------------------------------------------------

class Verdict:
    def __init__(self, owner=True, reason="", score=None, threshold=0.5):
        self.is_owner = owner
        self.reason = reason or ("" if owner else "that did not sound like you")
        self.score = (0.99 if owner else 0.1) if score is None else float(score)
        self.threshold = float(threshold)
        self.mode = "owner"
        self.voice_print = "desk"
        self.strictness = "very_strict"


class LiveEngine:
    """A Live session paused on other voices: clips are CHECKED only."""

    def __init__(self):
        self.refused = []

    def accepts(self, mic):
        return {"ok": False, "check": True}

    def status(self):
        return {"on": True, "device": "phone", "state": "on",
                "paused": "other_voices", "hint": ""}

    def trust_decision(self, mic, spoken):
        return {"action": "check", "words": ""}

    def note_refused(self, mic, near_miss=False):
        self.refused.append(bool(near_miss))

    def note_verified(self, mic): pass
    def carry_on_by_voice(self, mic): pass
    def abort_trust(self, why): pass
    def note_owner(self, mic): pass


class LiveModule:
    def __init__(self):
        self.ENGINE = LiveEngine()

    @staticmethod
    def phrase(text):
        return None


class FakeWakeword:
    @staticmethod
    def spot_stop(samples, rate=None):
        return types.SimpleNamespace(ran=False, heard=False, score=0.0)

    @staticmethod
    def split_wake(text):
        return False, text


class World:
    """`hear()` with every engine and every sink stood in for.

    `verify` / `transcribe` are the decisions under test; everything else is
    a spy or a fixed answer, so a check that fails says it failed about the
    real function and not about a model that is not installed.
    """

    def __init__(self, owner=True, verify_boom=False, transcribe_boom=False,
                 verify_seconds=0.0, transcribe_seconds=0.0,
                 transcribe_text="what time is my meeting", engine=True, live=None,
                 verify_script=None):
        self.owner = owner
        self.verify_boom = verify_boom
        self.transcribe_boom = transcribe_boom
        self.verify_seconds = verify_seconds
        self.transcribe_seconds = transcribe_seconds
        self.transcribe_text = transcribe_text
        self.engine = engine
        self.live = live
        #: Per-call answers for the owner check: [{"owner":bool, "score":float,
        #: "seconds":float, "boom":bool}, ...] - consumed in order. Empty:
        #: the plain `owner`/`verify_seconds` answer for every call.
        self.verify_script = list(verify_script or [])
        self.calls = []            # [("owner_check" | "stt", perf_counter)]
        self.times = {}            # "verify_start"/"verify_end"/"stt_start"/"stt_end"
        self.sample_counts = []    # how many samples each owner check was given
        self.noted = []            # (words, ...) _note_for_history was given
        self.flows = []            # every _flow() call
        self.verdicts = []

    # -- the two stand-ins ---------------------------------------------------

    def _verify(self, samples, embedder, **kw):
        self.calls.append(("owner_check", time.perf_counter()))
        self.sample_counts.append(len(samples))
        self.times["verify_start"] = time.perf_counter()
        spec = self.verify_script.pop(0) if self.verify_script else {}
        seconds = spec.get("seconds", self.verify_seconds)
        if seconds:
            time.sleep(seconds)
        self.times["verify_end"] = time.perf_counter()
        if spec.get("boom") or self.verify_boom:
            raise RuntimeError("the speaker model failed")
        v = Verdict(spec.get("owner", self.owner), score=spec.get("score"))
        self.verdicts.append(v)
        return v

    def _transcribe(self, samples, sample_rate):
        self.calls.append(("stt", time.perf_counter()))
        self.times["stt_start"] = time.perf_counter()
        if self.transcribe_seconds:
            time.sleep(self.transcribe_seconds)
        self.times["stt_end"] = time.perf_counter()
        if self.transcribe_boom:
            raise ValueError("the speech-to-text model failed")
        return self.transcribe_text

    # -- the world -----------------------------------------------------------

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        voice = types.SimpleNamespace(
            EcapaEmbedder=type("E", (), {}),
            Embedder=type("E", (), {}),
            verify=self._verify,
        )
        if self.live is None:
            live = None
        else:
            live = LiveModule()
        self.patches = [
            mock.patch.object(S, "_read_wav", lambda raw: ([0.1] * 40000, 16000)),
            mock.patch.object(S, "_speech_span", lambda *a, **k: "skip"),
            mock.patch.object(S, "_note_voice_attempt", lambda *a, **k: None),
            mock.patch.object(S, "_has_print", lambda mic: True),
            mock.patch.object(S, "_min_command_seconds", lambda: 0.0),
            mock.patch.object(S, "_private_aloud", lambda: False),
            mock.patch.object(S, "_memory_aloud", lambda: False),
            mock.patch.object(S, "_sensitive_aloud", lambda: False),
            mock.patch.object(S, "_screen_aloud", lambda *a, **k: False),
            mock.patch.object(S, "_really_checked", lambda v, very=False: True),
            mock.patch.object(S, "_source_trusted", lambda src: True),
            mock.patch.object(S, "_question_private", lambda text: False),
            mock.patch.object(S, "_note_for_history",
                              lambda words, *a, **k: self.noted.append((words, a, k))),
            mock.patch.object(S, "_flow", lambda *a, **k: self.flows.append((a, k))),
            mock.patch.object(S, "_stt_files", lambda: ("model.onnx",)),
            mock.patch.object(S, "_stt_engine",
                              (lambda: object()) if self.engine else (lambda: None)),
            mock.patch.object(S, "_transcribe", self._transcribe),
            mock.patch.object(S, "jarvis_voice", voice),
            mock.patch.object(S, "jarvis_wakeword", FakeWakeword),
            mock.patch.object(S, "jarvis_live", live),
        ]
        for p in self.patches:
            p.start()
        S._reset_speaking_for_tests()
        return self

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()
        S._reset_speaking_for_tests()
        self._tmp.cleanup()
        return False


def _clip(seconds=2.5):
    return b"RIFF" + b"\x00" * int(seconds * 32000)


def _hear(world, **kw):
    return S.hear(_clip(float(kw.pop("seconds", 2.5))), **kw)


# ---------------------------------------------------------------------------
#   1. The two steps run beside each other
# ---------------------------------------------------------------------------

def t_steps_four_and_five_run_beside_each_other():
    """MECHANISM, not a benchmark: the transcription starts before the owner
    check answers, and the call is shorter than the two sleeps added."""
    with World(owner=True, verify_seconds=0.5, transcribe_seconds=0.5) as w:
        t0 = time.perf_counter()
        heard = _hear(w, source="push_to_talk", mic="desktop")
        wall = time.perf_counter() - t0
    check("the owner's words still come back, with the check beside them",
          heard.is_owner and heard.text == "what time is my meeting", heard)
    check("BESIDE: the transcription started before the owner check ended",
          w.times.get("stt_start", 1e9) < w.times.get("verify_end", 0.0),
          (w.times, w.calls))
    check("BESIDE: both stand-ins really ran, once each",
          [c for c, _t in w.calls].count("owner_check") == 1
          and [c for c, _t in w.calls].count("stt") == 1, w.calls)
    check("...and the call was shorter than the two sleeps added (0.5 + 0.5)",
          wall < 0.85, f"wall {wall:.3f}s")
    check("...and not shorter than the longer one alone, so both did happen",
          wall >= 0.45, f"wall {wall:.3f}s")


def t_the_delay_number_is_the_transcriptions_own_length():
    """`steps["stt"]` must stay "what speech-to-text cost", not the short
    join - the delay table would otherwise claim it had become free."""
    with World(owner=True, verify_seconds=0.0, transcribe_seconds=0.4) as w:
        _hear(w, source="push_to_talk", mic="desktop")
    steps = w.flows[0][0][2] if w.flows else {}
    check("one delay-table row, for the words that came back", len(w.flows) == 1, w.flows)
    check("the row's stt_ms is the transcription's own length (~400 ms), not the join",
          isinstance(steps.get("stt"), (int, float)) and steps["stt"] >= 350, steps)
    check("...and the owner check is in it too",
          isinstance(steps.get("owner_check"), (int, float)), steps)


# ---------------------------------------------------------------------------
#   2. Nothing of an unverified clip escapes - every sink spied on
# ---------------------------------------------------------------------------

SECRET = "SECRET STRANGER SENTENCE THAT MUST NEVER ESCAPE"


def t_a_stranger_is_transcribed_beside_the_check_and_the_words_are_discarded():
    printed = io.StringIO()
    with World(owner=False, transcribe_seconds=0.3, transcribe_text=SECRET) as w:
        with contextlib.redirect_stdout(printed), contextlib.redirect_stderr(printed):
            t0 = time.perf_counter()
            heard = _hear(w, source="push_to_talk", mic="desktop")
            returned_at = time.perf_counter()
    wire = json.dumps(heard.as_dict(), sort_keys=True)
    check("a stranger is still refused, with no words",
          (not heard.is_owner) and heard.text == "", heard)
    check("the transcription really did run beside the check (or this proves nothing)",
          [c for c, _t in w.calls].count("stt") == 1, w.calls)
    check("NOT RETURNED: the returned Heard, its as_dict() and its reason hold no words",
          SECRET not in wire and SECRET not in str(heard)
          and SECRET not in heard.as_dict().get("reason", ""), wire[:300])
    check("NOT STORED OR LEARNED: _note_for_history was never called", w.noted == [], w.noted)
    check("NOT IN THE DELAY TABLE: _flow was never called", w.flows == [], w.flows)
    check("NOT LOGGED: nothing was printed", SECRET not in printed.getvalue(),
          printed.getvalue()[:300])
    check("JOINED: hear() returned after the worker's transcription ended",
          returned_at >= w.times.get("stt_end", 1e9),
          (returned_at, w.times))
    check("JOINED: no worker thread outlives the call", workers_alive() == [], workers_alive())
    check("...and the stranger's clip took at least the transcription's time (it ran)",
          returned_at - t0 >= 0.25, f"{returned_at - t0:.3f}s")


def t_a_failing_owner_check_discards_the_words_and_still_raises():
    printed = io.StringIO()
    raised = None
    with World(verify_boom=True, transcribe_seconds=0.2, transcribe_text=SECRET) as w:
        with contextlib.redirect_stdout(printed), contextlib.redirect_stderr(printed):
            try:
                _hear(w, source="push_to_talk", mic="desktop")
            except Exception as exc:      # noqa: BLE001 - the contract is "it raises"
                raised = exc
    check("a failing owner check still raises, as it did before the change",
          isinstance(raised, RuntimeError), raised)
    check("...and the words made beside it are gone", SECRET not in printed.getvalue()
          and w.noted == [] and w.flows == [], (w.noted, w.flows, printed.getvalue()[:200]))
    check("...and the worker was joined before the raise (no thread left holding audio)",
          workers_alive() == [], workers_alive())


def t_a_failing_transcriber_is_reported_not_raised():
    with World(owner=True, transcribe_boom=True) as w:
        heard = _hear(w, source="push_to_talk", mic="desktop")
    check("the owner was recognised, but there are no words to give",
          heard.is_owner and not heard.available and heard.text == "", heard)
    check("the failure is named exactly as before the change",
          "transcription failed (ValueError)" in heard.reason, heard.reason)
    check("...and no thread is left behind", workers_alive() == [], workers_alive())


# ---------------------------------------------------------------------------
#   3. Where the old serial rule still holds
# ---------------------------------------------------------------------------

def t_with_no_engine_nothing_is_started_for_a_stranger():
    """No speech-to-text model installed: there is nothing to run beside the
    check, and the old "not even attempted" behaviour is what happens."""
    with World(owner=False, engine=False) as w:
        heard = _hear(w, source="push_to_talk", mic="desktop")
    check("with no engine, a stranger is refused without a transcription",
          (not heard.is_owner) and heard.text == ""
          and [c for c, _t in w.calls].count("stt") == 0, w.calls)


def t_a_live_voice_pause_keeps_the_old_serial_path():
    """The check-only path of a Live voice pause spends as little as it can
    on a clip that may not be the owner: checked first, words after."""
    with World(owner=False, live="paused") as w:
        heard = _hear(w, source="live", mic="phone")
        stranger_calls = list(w.calls)
        w.calls.clear()
    check("a paused Live clip from a stranger is checked, and no words are made",
          not heard.is_owner and heard.text == "" and heard.live == "on", heard)
    check("...and speech-to-text never ran on it",
          [c for c, _t in stranger_calls] == ["owner_check"], stranger_calls)
    with World(owner=True, live="paused") as w:
        heard = _hear(w, source="live", mic="phone")
        owner_calls = [c for c, _t in w.calls]
    check("the owner's voice carries Live on and is heard",
          heard.is_owner and heard.text == "what time is my meeting", heard)
    check("...and on this exception path the old order still holds: check, then words",
          owner_calls == ["owner_check", "stt"], owner_calls)


# ---------------------------------------------------------------------------
#   4. The worker object on its own
# ---------------------------------------------------------------------------

def t_discard_clears_and_join_raises():
    with mock.patch.object(S, "_transcribe", lambda samples, rate: SECRET):
        early = S._EarlyStt([0.1] * 16000, 16000)
        early.discard()
    check("discard() drops the words and keeps nothing to read",
          early._text == "" and early._error is None, early._text)
    check("...and no worker is left", not any(t.name == WORKER_NAME for t in workers_alive()))
    with mock.patch.object(S, "_transcribe",
                           side_effect=RuntimeError("the model died")):
        early = S._EarlyStt([0.1] * 16000, 16000)
        got = None
        try:
            early.join()
        except Exception as exc:          # noqa: BLE001 - the contract is "it raises"
            got = exc
    check("join() re-raises the engine's own error unchanged",
          isinstance(got, RuntimeError) and str(got) == "the model died", got)
    with mock.patch.object(S, "_transcribe", lambda samples, rate: SECRET):
        early = S._EarlyStt([0.1] * 16000, 16000)
        check("join() gives the words of a verified clip", early.join() == SECRET)
        check("...and reports the transcription's own length",
              isinstance(early.ms, float) and early.ms >= 0.0, early.ms)


def t_the_audio_reference_is_released_after_the_worker():
    clip = [0.1] * 16000
    with mock.patch.object(S, "_transcribe", lambda samples, rate: "words"):
        early = S._EarlyStt(clip, 16000)
        early.join()
    check("a finished worker no longer holds the clip", early._samples is None)


# ---------------------------------------------------------------------------
#   5. The early window: the check starts on the first ~1.2 s, not the clip
# ---------------------------------------------------------------------------

def t_early_window_answer_is_used_at_end_of_speech():
    """A clear first-window answer decides; the full clip is not checked.

    TEST-MODE mechanism, not a benchmark: the stand-ins are what the numbers
    here describe. The window check is given ~1.2 s of the clip, and the call
    no longer waits for the full-clip check's sleep - which is what the real
    check's cost difference is made of. The real CAM++/Parakeet times are
    NOT-MEASURED here (no weights, no microphone) and are not claimed.
    """
    script = [{"owner": True, "score": 0.97, "seconds": 0.10},
              {"owner": True, "score": 0.99, "seconds": 0.80}]
    with World(owner=True, transcribe_seconds=0.05, verify_script=script) as w:
        t0 = time.perf_counter()
        heard = _hear(w, source="push_to_talk", mic="desktop")
        wall = time.perf_counter() - t0
    check("the owner's words come back", heard.is_owner and heard.text, heard)
    check("the window's answer was the one used",
          sorted(c for c, _t in w.calls) == ["owner_check", "stt"], w.calls)
    check("...and it was given ~1.2 s of the clip, not all of it",
          w.sample_counts and 18000 <= w.sample_counts[0] <= 19500, w.sample_counts)
    check("...the call did not wait for the full-clip check",
          wall < 0.6, f"wall {wall:.3f}s (window 0.10 s, full would have added 0.80 s)")
    steps = w.flows[0][0][2] if w.flows else {}
    check("the delay table says the early check answered",
          steps.get("owner_check_early") == 1.0, steps)
    print(f"  TEST-MODE numbers: window check 100 ms (stand-in), call {wall * 1000:.0f} ms, "
          "full-clip stand-in 800 ms not run - NOT hardware latency")


def t_a_borderline_window_is_rechecked_on_the_full_clip():
    """Inside the margin, the full clip decides exactly as it always did."""
    script = [{"owner": True, "score": 0.52, "seconds": 0.02},   # inside +0.06 band
              {"owner": True, "score": 0.99, "seconds": 0.02}]
    with World(owner=True, verify_script=script) as w:
        heard = _hear(w, source="push_to_talk", mic="desktop")
    counts = [c for c, _t in w.calls]
    check("the window was asked, then the full clip", counts == ["stt", "owner_check", "owner_check"]
          or counts == ["owner_check", "owner_check", "stt"], counts)
    check("...the full clip really got the whole clip",
          len(w.sample_counts) == 2 and w.sample_counts[1] == 40000, w.sample_counts)
    check("...the answer is the full clip's", heard.is_owner and heard.text, heard)
    steps = w.flows[0][0][2] if w.flows else {}
    check("...and the delay table does not claim the early path",
          steps.get("owner_check_early") == 0.0, steps)


def t_a_clear_refusal_on_the_window_still_costs_the_transcription():
    """Privacy + the stated cost: the words are made beside the check and
    thrown away, and the refusal waits for them, so it cannot be told apart
    from a verified clip by a suspiciously short answer."""
    script = [{"owner": False, "score": 0.05, "seconds": 0.02}]
    with World(owner=False, transcribe_seconds=0.30, verify_script=script) as w:
        t0 = time.perf_counter()
        heard = _hear(w, source="push_to_talk", mic="desktop")
        wall = time.perf_counter() - t0
    check("the stranger is refused", not heard.is_owner and heard.text == "", heard)
    check("...on the window alone", len(w.sample_counts) == 1 and
          18000 <= w.sample_counts[0] <= 19500, w.sample_counts)
    check("...the transcription still ran (and was discarded)",
          any(c == "stt" for c, _t in w.calls), w.calls)
    check("...the refusal took at least the transcription's length",
          wall >= 0.24, f"wall {wall:.3f}s vs transcription stand-in 0.30 s")
    check("NOT RETURNED / STORED / LOGGED: the existing sinks are empty",
          not any(SECRET in json.dumps(h.as_dict()) for h in [heard])
          and w.noted == [] and w.flows == [], (w.noted, w.flows))


def t_a_failing_window_worker_falls_back_to_the_full_clip():
    script = [{"boom": True}, {"owner": True, "score": 0.97}]
    with World(owner=True, verify_script=script) as w:
        heard = _hear(w, source="push_to_talk", mic="desktop")
    check("a worker that raises is not a refusal: the full clip is checked",
          heard.is_owner and len(w.sample_counts) == 2 and w.sample_counts[1] == 40000,
          (heard, w.sample_counts))
    check("...and no verify worker is left behind",
          not [t for t in threading.enumerate()
               if t.name == VERIFY_WORKER and t.is_alive()], threading.enumerate())


def t_early_window_can_be_switched_off_and_the_old_path_returns():
    with World(owner=True) as w, \
            mock.patch.object(S, "_early_verify_window", lambda: 0.0):
        heard = _hear(w, source="push_to_talk", mic="desktop")
    check("[voice] early_verify_window = 0: one full-clip check, exactly as before",
          heard.is_owner and w.sample_counts == [40000], w.sample_counts)
    steps = w.flows[0][0][2] if w.flows else {}
    check("...and the delay table says the early path did not run",
          steps.get("owner_check_early") == 0.0, steps)


def t_streaming_verify_answers_before_end_of_speech():
    """The chunk-fed path: the check starts once a window of voice has
    arrived, so end of speech waits only for the answer that is already there."""
    script = [{"owner": True, "score": 0.97, "seconds": 0.25}]
    with World(owner=True, verify_script=script) as w:
        streaming = S.StreamingVerify(16000, mic="desktop", window=1.2)
        state = {}
        chunk = (b"\x66\x06" * 512)          # 0.1 amplitude, 512 samples = 32 ms
        for _ in range(40):                    # 1.28 s of voiced audio
            state = streaming.feed(chunk)
            if state["started"]:
                break
        started_before_end = state["started"]
        time.sleep(0.30)                       # the window check finishes meanwhile
        t0 = time.perf_counter()
        verdict, _emb, used_early, _ms = streaming.verdict(samples=[0.1] * 40000)
        wait = time.perf_counter() - t0
    check("the check started while the audio was still arriving", started_before_end, state)
    check("...it was given the window, not the whole clip",
          w.sample_counts and w.sample_counts[0] <= 19500, w.sample_counts)
    check("...end of speech used that answer", used_early is True, used_early)
    check("...and the full clip was not checked", len(w.sample_counts) == 1, w.sample_counts)
    check("...so end-of-speech waited only milliseconds (stand-in check 250 ms)",
          wait < 0.05, f"wait {wait * 1000:.1f} ms")
    check("...and it produced no words at all",
          not hasattr(streaming, "text") and w.noted == [] and w.flows == [])
    print(f"  TEST-MODE numbers: window check stand-in 250 ms, end-of-speech wait "
          f"{wait * 1000:.1f} ms - mechanism only, NOT hardware latency")


# ---------------------------------------------------------------------------
#   6. Ruling 10.4: an early verdict belongs to ONE recording, never the next
# ---------------------------------------------------------------------------


def _voiced_pcm(seconds: float = 1.28) -> bytes:
    """Voiced 16 kHz mono int16 PCM: 0.1 amplitude, 512-sample chunks."""
    chunk = b"\x66\x06" * 512
    want = int(seconds * 16000) * 2
    return chunk * (want // len(chunk) + 1)


def _feed_until_started(streaming, seconds: float = 1.28):
    data = _voiced_pcm(seconds)
    state = {}
    for i in range(0, len(data), 1024):
        state = streaming.feed(data[i:i + 1024])
        if state["started"]:
            break
    return state


def t_streaming_verify_never_carries_a_verdict_to_the_next_utterance():
    """One instance, two sentences: the second must start its OWN window
    check and answer from it, never from the first sentence's verdict."""
    script = [{"owner": True, "score": 0.97, "seconds": 0.02},    # sentence 1
              {"owner": False, "score": 0.05, "seconds": 0.02}]   # sentence 2
    with World(owner=True, verify_script=script) as w:
        sv = S.StreamingVerify(16000, mic="desktop", window=1.2)
        st1 = _feed_until_started(sv)
        check("the first utterance started a window check", st1["started"], st1)
        time.sleep(0.05)
        v1, _e1, early1, _ms1 = sv.verdict(samples=[0.1] * 40000)
        first_counts = list(w.sample_counts)
        st2 = _feed_until_started(sv)
        check("a second utterance on the SAME instance starts a fresh check",
              st2["started"], st2)
        time.sleep(0.05)
        v2, _e2, early2, _ms2 = sv.verdict(samples=[0.1] * 40000)
        all_counts = list(w.sample_counts)
    check("sentence 1: the owner's window decided", v1.is_owner and early1 is True, v1)
    check("...on one window of audio, not the whole clip",
          first_counts and 18000 <= first_counts[0] <= 19500, first_counts)
    check("the second sentence's answer came from a NEW check",
          len(all_counts) == len(first_counts) + 1, (first_counts, all_counts))
    check("...and it is ITS refusal, not the first sentence's pass",
          (not v2.is_owner) and early2 is True, v2)
    print("  TEST-MODE numbers: two sentences, one StreamingVerify instance, "
          f"{len(all_counts)} window checks (2 expected) - no inherited verdict")


def t_an_aborted_recording_cannot_answer_the_next_one():
    """A recording abandoned before its verdict (stop/hang-up) leaves no audio
    and no answer behind, and the full-clip fallback of the next recording
    sees only the next recording's samples."""
    script = [{"owner": True, "score": 0.97, "seconds": 0.02},    # abandoned check
              {"owner": False, "score": 0.52, "seconds": 0.02},   # sentence 2: borderline
              {"owner": False, "score": 0.97, "seconds": 0.02}]   # full clip: still a stranger
    with World(owner=True, verify_script=script) as w:
        sv = S.StreamingVerify(16000, mic="desktop", window=1.2)
        _feed_until_started(sv)
        time.sleep(0.05)
        sv.abort()
        check("abort() keeps no audio and no worker from the abandoned recording",
              sv.voiced_seconds == 0.0 and not sv.started
              and not [t for t in threading.enumerate()
                       if t.name == VERIFY_WORKER and t.is_alive()],
              (sv.voiced_seconds, sv.started))
        _feed_until_started(sv)
        time.sleep(0.05)
        v, _e, early, _ms = sv.verdict()        # its own buffer; no caller samples
    check("the abandoned recording's 'owner' verdict never comes back",
          (not v.is_owner) and early is False, (v, early))
    check("...the fallback full check got the SECOND recording only (1.2 s, not 2.4 s)",
          w.sample_counts and 18000 <= w.sample_counts[-1] <= 19500, w.sample_counts)
    print("  TEST-MODE numbers: aborted recording then a stranger - "
          f"full-clip fallback saw {w.sample_counts[-1]} samples (one window)")


def t_each_hear_gets_its_own_early_verdict():
    """The single-shot path builds a new window worker per call; nothing is
    cached between utterances, so the second call cannot inherit the first's."""
    script = [{"owner": True, "score": 0.97},
              {"owner": False, "score": 0.05}]
    with World(owner=True, verify_script=script) as w:
        first = _hear(w, source="push_to_talk", mic="desktop")
        second = _hear(w, source="push_to_talk", mic="desktop")
        counts = list(w.sample_counts)
    check("each hear() asked the check on its own fresh window",
          counts == [19200, 19200], counts)
    check("the first recording passes", first.is_owner and first.text, first)
    check("the second is refused on ITS verdict, not the first's",
          (not second.is_owner) and second.text == "", second)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
