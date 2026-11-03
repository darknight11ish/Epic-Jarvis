"""test_quick_mic.py - the phone's mic press does not check the voice print.

    python3 backend/test_quick_mic.py

THE OWNER'S REQUEST (2026-11-02), in their words: "also, when i do the mic
press to make a short verbal message to jarvis, dont have it confirm my voice
through the voice id". So ONE surface stops running the owner check: a clip
with `?source=push_to_talk` AND `?mic=phone` - the phone's own talk button.
Everything else still runs it, and this suite holds both halves.

What it proves, with the rebuilt jarvis_voice (test_voice_strict.py's Table
stand-in: a loud tone is the owner, a quiet one a stranger), a speech-to-text
that says only what the test tells it, and a Live session that is on:

  1. THE PHONE'S MIC PRESS: `jarvis_voice.verify()` is never called - not
     once - and the words are used just the same. A SHORT message (0.9 s,
     under the 2.0 s command minimum) is transcribed instead of refused as
     "say a little more", which is the whole point of the owner's request.
     The reply is honest about what did not happen: `mode: "quick_message"`,
     `strictness: ""`, `voice_print: ""`, `threshold: 0`, `score: 0`.
  2. WHAT IT DID NOT BUY. With the read-aloud settings at their loosest
     ("voice check is enough", sensitive facts allowed aloud), none of
     `private_aloud`, `memory_aloud`, `sensitive_aloud` becomes true on an
     unchecked clip: a private, memory or sensitive answer stays on the
     phone's screen. `screen_aloud` is unchanged, because that rule never
     rested on the voice check. Automatic learning refuses the reply's voice
     facts too (GUARDS L8: mode must be `owner` and strictness `very_strict`).
  3. THE HONEST COST, said plainly: a voice the check WOULD refuse is still
     answered on this one surface, because the press is the act now (like
     typing a message). This is pinned so nobody discovers it by surprise.
  4. EVERY OTHER SURFACE STILL CHECKS EVERY CLIP: the desktop's talk button
     (`mic=desktop`), a clip that names no microphone (fail closed), the
     phone's "hey Jarvis" (`source=wake_word`), and Jarvis Live
     (`source=live`) - where a short clip is still put to the check and never
     transcribed, and a stranger is still refused with no words. The desktop
     button also still refuses a clip shorter than the command minimum, before
     the check.
  5. The gate itself is untouched: the button's readiness rule
     (`_push_to_talk`: owner mode, a voice print, the voice-ID model, and
     speech-to-text) still answers exactly as before - this suite changes no
     enrolment and no threshold. And a quick message cannot open Jarvis Live:
     "let's talk" from the phone's press is an ordinary message, because the
     owner's "NO LIVE WITHOUT A REAL VOICE CHECK" rule is not loosened by the
     one surface that skips the check (the desktop's checked button still does
     open it).

No network, no model, no microphone.
"""
import sys
import traceback
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
require_shipped("jarvis_speech.py", "jarvis_live.py", "rebuilt/jarvis_voice.py")

import jarvis_live as L  # noqa: E402
import jarvis_speech as S  # noqa: E402
import jarvis_voice as V  # noqa: E402
import jarvis_wakeword as W  # noqa: E402
import test_voice_strict as T  # noqa: E402  (its Table stand-in, clips, Temp)

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" +
          (f"\n        {detail}" if detail and not cond else ""))


class LiveSession:
    """Jarvis Live, on for the phone, every clip to be checked.

    Only the answers `hear()` reads: the session is on, so the clip is looked
    at; the session's trust rule says "check" (a fresh session's first
    sentence), which is exactly the branch a short or stranger clip reaches
    the speaker model through. Nothing here decides anything itself.
    """

    def __init__(self):
        self.refused = []
        self.verified = []
        self.owner_turns = 0
        self.starts = []

    def start(self, device, minutes=None, by="button", conversation_id=None):
        self.starts.append((S._norm_mic(device), str(by)))
        return {"ok": True, "say": "I'm listening."}

    def accepts(self, mic):
        if S._norm_mic(mic) == "phone":
            return {"ok": True}
        return {"ok": False, "words": "Jarvis Live is not on for that device"}

    def trust_decision(self, mic, seconds):
        return {"action": "check", "words": "", "strictness": ""}

    def trust_source(self, mic):
        return "live"

    def status(self):
        return {"on": True, "device": "phone", "state": "on",
                "paused": "", "hint": ""}

    def note_verified(self, mic, strictness="", label=""):
        self.verified.append((str(strictness), str(label)))

    def note_refused(self, mic, near_miss=False):
        self.refused.append(bool(near_miss))

    def abort_trust(self, why=""):
        pass

    def note_owner(self, mic):
        self.owner_turns += 1

    def carry_on_by_voice(self, mic):
        pass

    def short_line_due(self):
        return False


class World:
    """The stand-ins, held for the whole test body (a wake-word clip needs the
    same world as a push-to-talk one, so they are patches, not a wrapper round
    one call)."""

    def __init__(self):
        self.small = T.Table("sherpa-onnx:357a834f702b",
                             {"loud": T.OWNER, "quiet": T.STRANGER})
        V.enroll(["a", "b", "c"], embedder=T.Table(
            self.small.name, {"a": T.OWNER, "b": T.OWNER, "c": T.OWNER}))
        self.checks = []
        self.words = "what is the weather"
        self.live = LiveSession()

    def __enter__(self):
        real_verify = V.verify

        def verify(*a, **k):
            self.checks.append(1)
            return real_verify(*a, **k)

        self._patchers = [
            mock.patch.object(V, "EcapaEmbedder", lambda: self.small),
            mock.patch.object(V, "strong_embedder", lambda *a: None),
            mock.patch.object(V, "verify", verify),
            mock.patch.object(S, "_speech_span", return_value="skip"),
            mock.patch.object(S, "_stt_engine", return_value=object()),
            mock.patch.object(S, "_transcribe", lambda *a, **k: self.words),
            mock.patch.object(W, "spot_stop",
                              return_value=W.Spot(True, heard=False, score=0.0)),
            mock.patch.object(L, "ENGINE", self.live),
        ]
        for p in self._patchers:
            p.start()
        return self

    def __exit__(self, *a):
        for p in reversed(self._patchers):
            p.stop()

    def hear(self, who="owner", seconds=2.5, words=None,
             source="push_to_talk", mic="phone"):
        if words is not None:
            self.words = words
        return S.hear(T._clip(who, seconds), source=source, mic=mic).as_dict()


# ------------------------------------------------------- 1. the one surface --

def t_the_phone_mic_press_is_not_checked():
    with T.Temp():
        with World() as w:
            h = w.hear(who="owner", seconds=2.5, words="remind me to call mum at five")
            check("the phone's mic press: the voice check is NOT run, not even once",
                  w.checks == [], w.checks)
            check("...and the words are used: ok, owner, the transcript",
                  h["ok"] and h["owner"] and h["text"] == "remind me to call mum at five", h)
            check("...the reply says no real check happened: mode quick_message, "
                  "strictness '', voice_print '', threshold 0, score 0",
                  h["mode"] == "quick_message" and h["strictness"] == ""
                  and h["voice_print"] == "" and h["threshold"] == 0
                  and h["score"] == 0, h)
            check("...and it is still marked as the talk button's clip",
                  h["source"] == "push_to_talk", h["source"])

            # A SHORT verbal message: the owner's words are "a short verbal
            # message", and the 2.0 s command minimum exists only to feed the
            # voice check. With no check there is nothing to feed.
            w.checks.clear()
            h = w.hear(who="owner", seconds=0.9, words="lights off")
            check("a 0.9 s message (under the 2.0 s minimum) is transcribed, "
                  "not refused as 'say a little more'",
                  h["ok"] and h["text"] == "lights off" and not h["too_short"], h)
            check("...with no check for it either", w.checks == [], w.checks)

            # The honest cost, pinned rather than discovered later: the press
            # is the act now, so whose voice it is does not decide.
            w.checks.clear()
            h = w.hear(who="stranger", seconds=2.5, words="lights off")
            check("a voice the check would refuse is still answered here - the "
                  "press on the paired phone is the act, like typing",
                  h["ok"] and h["text"] == "lights off" and w.checks == [], h)


# --------------------------------------------- 2. what the exception did NOT buy --

def t_nothing_private_is_read_aloud():
    with T.Temp():
        with World() as w:
            # The loosest read-aloud settings there are: each of these makes
            # the field true for a clip that passed a real check.
            V.set_setting("privacy", "voice_is_enough", approved=True)
            V.set_setting("sensitive_memory", "sensitive_aloud", approved=True)
            h = w.hear(who="owner", seconds=2.5, words="read me my last email")
            check("with 'voice check is enough' AND sensitive facts allowed aloud, "
                  "an unchecked clip still reads NOTHING aloud privately",
                  h["private_aloud"] is False and h["memory_aloud"] is False
                  and h["sensitive_aloud"] is False, h)
            check("...and the words are still answered (on the phone's screen)",
                  h["ok"] and h["text"] == "read me my last email", h)
            check("...while the same clip on the desktop's button DOES read them "
                  "aloud (the settings are real, only the check is missing)",
                  _desktop_aloud(T.Temp) is True, "see t_desktop_is_unchanged")

        # Automatic learning (GUARDS L8) reads the same facts, and refuses.
        import jarvis_auto_learn as A
        with T.Temp():
            with World() as w:
                h = w.hear(who="owner", seconds=2.5,
                           words="my sister's birthday is in June")
        why = A.check_voice({"provenance": "voice", "voice_check": {
            "strictness": h["strictness"], "mode": h["mode"],
            "model": "", "source": h["source"]}})
        check("automatic learning refuses the unchecked clip: a fact it mentions "
              "waits for a card", bool(why) and "not at its strictest" in why, why)


def _desktop_aloud(temp):
    """Control for the check above: the SAME settings, the SAME words, on the
    desktop's talk button, and the private field becomes true - so the false
    above is the missing check, not a setting that never worked."""
    with temp():
        with World() as w:
            V.set_setting("privacy", "voice_is_enough", approved=True)
            V.set_setting("sensitive_memory", "sensitive_aloud", approved=True)
            h = w.hear(who="owner", seconds=2.5, mic="desktop",
                       words="read me my last email")
            return bool(h["ok"] and h["private_aloud"] and h["memory_aloud"]
                        and h["sensitive_aloud"])


# ------------------------------------- 3. every other surface still checks --

def t_the_desktop_button_is_unchanged():
    with T.Temp():
        with World() as w:
            h = w.hear(who="owner", seconds=2.5, mic="desktop")
            check("the desktop's talk button (mic=desktop) still runs the check, "
                  "at its own strictness",
                  len(w.checks) >= 1 and h["ok"] and h["strictness"] == "very_strict", h)
            w.checks.clear()
            h = w.hear(who="stranger", seconds=2.5, mic="desktop")
            check("...and a stranger is still refused there, with no words",
                  not h["ok"] and h["text"] == "" and len(w.checks) >= 1, h)
            w.checks.clear()
            h = w.hear(who="owner", seconds=1.2, mic="desktop")
            check("a short desktop clip is still refused BEFORE the check "
                  "(the 2.0 s command minimum is untouched)",
                  h["too_short"] and w.checks == [] and h["threshold"] == 0, (h, w.checks))
            w.checks.clear()
            h = w.hear(who="owner", seconds=2.5, mic="")
            check("a clip that names no microphone is still checked - fail closed",
                  len(w.checks) >= 1 and h["strictness"] == "very_strict", h)
            w.checks.clear()
            h = w.hear(who="owner", seconds=2.5, mic="tablet")
            check("an unknown microphone counts as none named, and is still checked",
                  len(w.checks) >= 1, h)


def t_live_still_checks_every_clip():
    with T.Temp():
        with World() as w:
            h = w.hear(who="owner", seconds=2.5, source="live", mic="phone")
            check("a Live clip: the owner check still runs, and the words are used",
                  len(w.checks) >= 1 and h["ok"] and h["live"] == "on", h)
            w.checks.clear()
            h = w.hear(who="owner", seconds=1.0, source="live", mic="phone",
                       words="yes please")
            check("a SHORT Live clip is still put to the check and never "
                  "transcribed (the owner's 2026-09-28 'no Balanced for Live')",
                  len(w.checks) >= 1 and h["too_short"] and h["text"] == ""
                  and h["live_short"] == "owner", h)
            w.checks.clear()
            h = w.hear(who="stranger", seconds=2.5, source="live", mic="phone",
                       words="NEVER TRANSCRIBED")
            check("a stranger on Live is still refused, with no words",
                  not h["ok"] and h["text"] == "" and len(w.checks) >= 1, h)


def t_the_phone_wake_word_is_still_checked():
    with T.Temp():
        with World() as w:
            with mock.patch.object(S, "_wake_enabled", return_value=True), \
                    mock.patch.object(S, "_take_awake", return_value=False), \
                    mock.patch.object(S, "_question_open", return_value=False), \
                    mock.patch.object(W, "spot",
                                      return_value=W.Spot(True, heard=True, score=0.9)):
                w.words = "Hey Jarvis, what time is it"
                h = S.hear(T._clip("owner", 2.5), source="wake_word",
                           mic="phone").as_dict()
            check("the phone's 'hey Jarvis' clip is still checked",
                  len(w.checks) >= 1 and h["ok"] and h["wake_heard"], h)


# ------------------------------------------- 4. the rule is exactly one surface --

def t_the_quick_press_does_not_open_live():
    """The one clip without a check may not open Jarvis Live either: the
    owner's 2026-09-28 rule is "NO LIVE WITHOUT A REAL VOICE CHECK", and a
    route that skips the check must not become a way in. The words are an
    ordinary message, and the app's own Start control is still there."""
    with T.Temp():
        with World() as w:
            h = w.hear(who="owner", seconds=1.2, words="let's talk")
            check("the phone's mic press saying 'let's talk' does NOT open Live - "
                  "it is an ordinary message",
                  w.live.starts == [] and h["live"] == "" and h["text"] == "let's talk",
                  (h, w.live.starts))
            h = w.hear(who="owner", seconds=2.5, mic="desktop", words="let's talk")
            check("...while the desktop's CHECKED talk button still opens it",
                  w.live.starts == [("desktop", "voice")] and h["live"] == "started"
                  and h["live_say"] == "I'm listening.", (h, w.live.starts))


def t_the_rule_is_one_surface():
    check("the exception is push_to_talk AND mic=phone, nothing else",
          S._is_quick_message("push_to_talk", "phone") is True
          and S._is_quick_message("push_to_talk", "desktop") is False
          and S._is_quick_message("wake_word", "phone") is False
          and S._is_quick_message("live", "phone") is False
          and S._is_quick_message("push_to_talk", "") is False
          and S._is_quick_message("", "phone") is False,
          [S._is_quick_message(a, b) for a, b in
           (("push_to_talk", "phone"), ("push_to_talk", "desktop"),
            ("wake_word", "phone"), ("live", "phone"), ("push_to_talk", ""))])
    check("...and the verdict it gets is not a passed check",
          S._really_checked(S._QuickMessage()) is False
          and S._really_checked(S._QuickMessage(), very=True) is False)


def t_the_button_gate_is_untouched():
    """The enrolment/readiness gate the phone reads is the same rule as before:
    owner mode, a print, the voice-ID model, speech-to-text. The request
    removed the per-clip confirmation, not the enrolment."""
    voice = {"enabled": True, "mode": "owner", "enrolled": True,
             "speaker_model": True, "needs_retraining": False}
    check("enrolled + model + STT: the button is offered",
          S._push_to_talk(voice, True, True) == (True, ""), S._push_to_talk(voice, True, True))
    not_enrolled = dict(voice, enrolled=False)
    ok, why = S._push_to_talk(not_enrolled, True, True)
    check("...not enrolled is still refused, in words that point at training",
          ok is False and "Train my voice" in why, (ok, why))
    no_model = dict(voice, speaker_model=False)
    ok, why = S._push_to_talk(no_model, True, True)
    check("...no voice-ID model is still refused, in words that say which",
          ok is False and "voice-ID model" in why, (ok, why))
    ok, why = S._push_to_talk(voice, False, True)
    check("...no speech-to-text is still refused", ok is False and "speech-to-text" in why,
          (ok, why))


if __name__ == "__main__":
    for fn in (t_the_phone_mic_press_is_not_checked,
               t_nothing_private_is_read_aloud,
               t_the_desktop_button_is_unchanged,
               t_live_still_checks_every_clip,
               t_the_phone_wake_word_is_still_checked,
               t_the_quick_press_does_not_open_live,
               t_the_rule_is_one_surface,
               t_the_button_gate_is_untouched):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
