"""One PC-wide voice: the setting both apps show is the voice that is heard.

    python3 backend/test_voice_one_state.py

THE OWNER'S REPORT (2026-10-28), in his words: *"when i change the jarvis voice
in the android app it still stays the same in jarvis live in the android app. it
needs to be consistent, including across gemini on desktop and android. if i
change voice on desktop jarvis it should change it on android jarvis and so
forth."*

WHAT WAS WRONG, measured in the code and in his own files rather than guessed.
His PC has `"personality": "classic_butler", "personality_explicit": true` in
`manner.json` and no `sync_voice_with_personality` key (so it is ON), and
`"speaker": "af_bella"` in `voices/state.json`. `jarvis_speech.tts_voice()` read
the personality FIRST - `if not plain: spec = _personality_voice()` - and
returned the preset's fallback voice (`bm_george`) and its pace, before ever
asking `jarvis_voices.spaker()`. So both apps' pickers, the `voices` event and
`voices/state.json` all said Bella, and every reply was spoken as George. A
voice change in either app changed the screen and nothing that was heard. Live
was not a second path: the phone's Live reply asks the same `/api/voice/say`
(`VoiceSession.speakStreamed` -> `api.say`), which is why it sounded unchanged
too.

WHAT THIS SUITE PROVES:

  - the voice both apps show (`GET /api/voice/voices`) is the voice
    `tts_voice()` speaks, with a personality chosen and its voice lock on -
    the reported bug, as a regression test;
  - a personality with the lock on APPLIES its voice to that one setting (one
    write, one audit line, one `voices` event), so the two can never disagree;
  - the lock off leaves the voice alone, and switching personality then
    changes no voice at all;
  - a preset voice this PC's pack does not offer changes nothing and does not
    fail the switch;
  - there is exactly ONE place that writes the speaker, and `jarvis_speech`
    no longer names a personality - the second source of truth cannot come
    back by accident. Those two are structural facts, so they are proven by
    walking each module's syntax tree (`ast`) and by driving a spy through
    both callers - never by matching the modules' source TEXT, which goes red
    when a name is spelled differently and stays green when the behaviour is
    wrong (`tools/check_no_source_pins.py`);
  - the speed is one setting too: a preset's own 0.94-1.1 pace is not applied;
  - a crisis answer keeps the plain voice (no card, no animal, no pitch);
  - nothing private reaches an audit line or an event: a voice name and a
    speed id at most, never a word the owner said.

Runs anywhere. No voices pack, no model, no graphics card: the picker's list is
whatever `jarvis_kokoro` says this PC offers, and every case is driven through
the real `jarvis_voices`, `jarvis_manner` and `jarvis_speech`.
"""
import ast
import gc
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, require_shipped  # noqa: E402

require_shipped("jarvis_voices.py", "jarvis_manner.py", "jarvis_speech.py")
import jarvis_kokoro as K  # noqa: E402
import jarvis_manner as M  # noqa: E402
import jarvis_speech as SP  # noqa: E402
import jarvis_voices as V  # noqa: E402

FAILED, PASSED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass (the BLOCKED-is-never-a-pass rule)."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def _cleanup(tmp) -> None:
    gc.collect()
    try:
        tmp.cleanup()
    except OSError:
        pass


_EVENTS: list = []
_AUDITS: list = []


def folder_events():
    """Every `voices` event rung inside the current `with Folder()`."""
    return _EVENTS


def folder_audits():
    """Every (event, detail) audit line written inside it."""
    return _AUDITS


class Folder:
    """A temporary config folder for BOTH modules that keep this setting:
    `voices/state.json` (jarvis_voices) and `manner.json` (jarvis_manner).
    It also records every event and audit line, so a test can prove one write
    and one doorbell - and that neither carries a private word."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = os.environ.get("OPENJARVIS_CONFIG_DIR")
        os.environ["OPENJARVIS_CONFIG_DIR"] = self.tmp.name
        self.real_v, self.real_m = V._config_dir, M._config_dir
        V._config_dir = lambda: Path(self.tmp.name)
        M._config_dir = lambda: Path(self.tmp.name)
        _EVENTS.clear()
        _AUDITS.clear()
        self.real_pub, self.real_audit = V._publish, V._audit
        V._publish = lambda data: _EVENTS.append(json.loads(json.dumps(data)))
        V._audit = lambda event, detail=None: _AUDITS.append(
            (event, json.loads(json.dumps(detail or {}))))
        return Path(self.tmp.name)

    def __exit__(self, *a):
        V._config_dir, M._config_dir = self.real_v, self.real_m
        V._publish, V._audit = self.real_pub, self.real_audit
        if self.saved is None:
            os.environ.pop("OPENJARVIS_CONFIG_DIR", None)
        else:
            os.environ["OPENJARVIS_CONFIG_DIR"] = self.saved
        _cleanup(self.tmp)


def spoken_sid():
    """The voice number a reply is really spoken in."""
    return int(SP.tts_voice(V)[0])


def shown_name():
    """The voice name both apps show (`GET /api/voice/voices`)."""
    return str(V.speaker_view()["choice"])


def sid_of(name):
    return K.sid_of(V.table_kind(), name)


def offered():
    return {r["id"] for r in V._speaker_rows(V.table_kind())}


def pick(*preferred):
    """The first of `preferred` this PC's voice pack really offers, so the
    suite runs on a PC with either pack (v0.19 has no af_heart, for one)."""
    have = offered()
    for name in preferred:
        if name in have:
            return name
    return sorted(have)[0]


# --------------------------------------------------------------------------
#   The reported bug, as a regression test
# --------------------------------------------------------------------------

def t_the_voice_both_apps_show_is_the_voice_that_is_heard():
    with Folder():
        first, second = pick("af_sarah", "af_bella"), pick("bm_lewis", "bm_george")
        code, _out = V.handle_post("/api/voice/voices/speaker", {"speaker": first})
        check("a picker's POST stores the voice and answers 200", code == 200, code)
        check("... and it is the voice a reply is spoken in",
              spoken_sid() == sid_of(first), (spoken_sid(), sid_of(first)))
        check("... and the same one both apps are shown",
              shown_name() == first, shown_name())
        code, _out = V.handle_post("/api/voice/voices/speaker", {"speaker": second})
        check("changing it again is heard at once, with no card",
              code == 200 and spoken_sid() == sid_of(second) and shown_name() == second,
              (code, spoken_sid(), sid_of(second), shown_name()))


def t_a_personality_cannot_silently_outvote_the_voice():
    # THE OWNER'S OWN MACHINE, case for case: a personality chosen, its voice
    # lock on (the default), and a built-in voice picked in the app. Before
    # 2026-10-28 the picker's voice was on screen and the preset's was spoken.
    with Folder():
        own, preset_voice = pick("af_sarah", "af_bella"), "bm_george"
        M.set_personality("classic_butler")
        check("a personality with the lock on applies its own voice",
              shown_name() == "bm_george" and spoken_sid() == sid_of(preset_voice),
              (shown_name(), spoken_sid()))
        code, _out = V.handle_post("/api/voice/voices/speaker", {"speaker": own})
        check("the owner's next pick is stored, at once, no card", code == 200, code)
        check("THE BUG: the voice on screen is the voice spoken - not the preset's",
              shown_name() == own and spoken_sid() == sid_of(own),
              (shown_name(), own, spoken_sid(), sid_of(own)))
        check("... the preset still says what voice it wants, and is not consulted for the sound",
              (M.voice_for_speech() or {}).get("fallback") == preset_voice
              and not hasattr(SP, "_personality_voice"),
              M.voice_for_speech())


# --------------------------------------------------------------------------
#   A personality applies its voice INTO the one setting
# --------------------------------------------------------------------------

def t_a_personality_switch_writes_the_one_setting_once():
    with Folder():
        ok, said = M.set_personality("classic_butler")
        check("the switch itself still works, and answers in character", ok and said, said)
        check("its voice is written into voices/state.json",
              V._read_state().get("speaker") == "bm_george", V._read_state())
        events = [e for e in folder_events() if e.get("what") == "speaker"]
        check("exactly ONE `voices` event - no second doorbell for the same change",
              len(events) == len(folder_events()), folder_events())
        check("... and it is the shape both apps already read: {what, outcome}",
              events == [{"what": "speaker", "outcome": "set"}], events)
        check("... so the voice heard is the one the event announced",
              spoken_sid() == sid_of("bm_george") == V.speaker(), (spoken_sid(), V.speaker()))


def t_the_switch_off_leaves_the_voice_alone():
    with Folder():
        own = pick("af_sarah", "af_bella")
        V.handle_post("/api/voice/voices/speaker", {"speaker": own})
        M.handle_set({"sync_voice_with_personality": False})
        M.set_personality("dry_wit")
        check("with the lock off, a personality switch changes no voice",
              shown_name() == own and spoken_sid() == sid_of(own),
              (shown_name(), spoken_sid()))
        check("... and it says so rather than pretending", M.voice_for_speech() is None,
              M.voice_for_speech())


def t_turning_the_lock_on_applies_the_voice_at_once():
    with Folder():
        own = pick("af_sarah", "af_bella")
        V.handle_post("/api/voice/voices/speaker", {"speaker": own})
        M.handle_set({"sync_voice_with_personality": False})
        M.set_personality("dry_wit")
        ok, said = M.handle_set({"sync_voice_with_personality": True})
        check("turning the switch on changes the voice there and then",
              ok and shown_name() != own and spoken_sid() == V.speaker(),
              (ok, shown_name(), spoken_sid()))
        check("... and the answer names the voice it is now, so nothing is silent",
              "British (male) - Lewis" in json.dumps(said), json.dumps(said)[:300])


def t_a_voice_this_pack_does_not_have_changes_nothing():
    with Folder():
        own = pick("af_sarah", "af_bella")
        V.handle_post("/api/voice/voices/speaker", {"speaker": own})
        M.set_personality("classic_butler")
        events_before = [e for e in folder_events() if e.get("what") == "speaker"]
        ok, why = V.set_speaker_name("this_voice_is_not_in_any_pack")
        check("a name no pack has is refused in plain words", not ok and why, (ok, why))
        check("... and nothing is written or announced",
              shown_name() == "bm_george"
              and [e for e in folder_events() if e.get("what") == "speaker"] == events_before,
              shown_name())
        check("a personality whose voice this pack lacks still switches, changing no voice",
              M._apply_personality_voice({"voice_fallback": "af_not_here"}) == ""
              and shown_name() == "bm_george", shown_name())


# --------------------------------------------------------------------------
#   One source of truth, structurally: it cannot come back by accident
# --------------------------------------------------------------------------

#: The two names that would be a second source of truth for the voice: the old
#: speech-time reader of a personality (`voice_for_speech`) and the preset's
#: own voice function (`_personality_voice`). `jarvis_speech` may name neither.
_SECOND_TRUTH = {"voice_for_speech", "_personality_voice"}


def _tree(module):
    """A shipped module's parsed syntax tree - what it DOES, not its words.

    `ast.parse` of the module's text is safe where a substring check is not:
    the answer is the code's structure, so a docstring or a comment (an
    `ast.Constant`, never an `ast.Call`) cannot answer for it, and renaming a
    local variable cannot turn a true fact false.
    """
    return ast.parse((BACKEND / module).read_text(encoding="utf-8"))


def _called(tree, name):
    """Every call of `name(...)`, or of `something.name(...)`, in a tree."""
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)
            and name in (getattr(n.func, "attr", None), getattr(n.func, "id", None))]


def _named(tree, name):
    """The one function definition called `name`, or None."""
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == name:
            return fn
    return None


def _holder(tree, node):
    """The name of the innermost function `node` sits in, "" at module level."""
    found = ""
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                n is node for n in ast.walk(fn)):
            found = fn.name
    return found


class FakeVoices:
    """A stand-in `jarvis_voices` that records every question it is asked.

    Driving the REAL `jarvis_speech.tts_voice` against this is the behavioural
    half of "the speech-time voice is read from jarvis_voices only": whatever
    this object answers is what the reply is spoken in, and `asked` proves
    nothing else was consulted on the way.
    """

    def __init__(self, sid, pace, semis=0.0):
        self.asked = []
        self.sid, self.pace, self.semis = int(sid), float(pace), float(semis)

    def builtin_voice(self):
        self.asked.append("builtin_voice")
        return (self.sid, self.pace, self.semis, "")

    def speaker(self):
        self.asked.append("speaker")
        return self.sid

    def speaker_speed(self):
        self.asked.append("speaker_speed")
        return self.pace

    def speed(self):
        self.asked.append("speed")
        return self.pace


def t_one_write_of_the_speaker_and_no_second_truth():
    voices = _tree("jarvis_voices.py")
    writes = [c for c in _called(voices, "_write_state")
              if any(k.arg == "speaker" for k in c.keywords)]
    check("jarvis_voices writes the speaker in exactly ONE place",
          len(writes) == 1, [c.lineno for c in writes])
    check("... and that place is the shared _store_speaker both callers use",
          len(writes) == 1 and _holder(voices, writes[0]) == "_store_speaker",
          _holder(voices, writes[0]) if writes else "no speaker write found")
    check("... which has exactly two call sites, so no third path exists",
          len(_called(voices, "_store_speaker")) == 2,
          [c.lineno for c in _called(voices, "_store_speaker")])

    # Both callers, driven for real, against a spy on the ONE shared function:
    # the picker's route and a personality switch must reach the same write.
    with Folder():
        first = pick("af_sarah", "af_bella")
        seen = []
        real = V._store_speaker

        def spy(name):
            seen.append(name)
            return real(name)

        V._store_speaker = spy
        try:
            V.handle_post("/api/voice/voices/speaker", {"speaker": first})
            M.set_personality("classic_butler")
        finally:
            V._store_speaker = real
        check("the picker's route and a personality switch both write it through there",
              seen == [first, "bm_george"], seen)
        check("... once each: one audit line and one `voices` event per change, no more",
              [a for a in folder_audits() if a[0] == "voices.speaker"]
              == [("voices.speaker", {"speaker": first}),
                  ("voices.speaker", {"speaker": "bm_george"})]
              and [e for e in folder_events() if e.get("what") == "speaker"]
              == [{"what": "speaker", "outcome": "set"}] * 2,
              (folder_audits(), folder_events()))


def t_jarvis_speech_never_asks_a_personality_for_a_voice():
    speech = _tree("jarvis_speech.py")
    named = {n.id for n in ast.walk(speech) if isinstance(n, ast.Name)}
    named |= {n.attr for n in ast.walk(speech) if isinstance(n, ast.Attribute)}
    check("jarvis_speech names no personality voice - not as a call, not as an attribute",
          not (named & _SECOND_TRUTH), sorted(named & _SECOND_TRUTH))

    tts = _named(speech, "tts_voice")
    check("its speech-time voice is read from jarvis_voices, resolved once and asked once",
          tts is not None and bool(_called(tts, "_voices_mod"))
          and bool(_called(tts, "builtin_voice")),
          (tts.name if tts else None,
           [c.lineno for c in _called(tts, "_voices_mod")] if tts else []))

    # What the voices module says is what is heard - one read, nothing else.
    fake = FakeVoices(77, 1.33)
    heard = SP.tts_voice(fake)
    check("the voice a reply is spoken in is the voices module's answer",
          heard == (77, 1.33, 0.0), heard)
    check("... and it was asked exactly once, and nothing else",
          fake.asked == ["builtin_voice"], fake.asked)

    with Folder():
        own = pick("af_sarah", "af_bella")
        M.set_personality("classic_butler")        # wants bm_george, at pace 1.02
        V.handle_post("/api/voice/voices/speaker", {"speaker": own})
        fake = FakeVoices(77, 1.33)
        heard = SP.tts_voice(fake)
        check("THE BUG, AT SPEECH TIME: a chosen preset's voice and pace are not spoken",
              heard == (77, 1.33, 0.0) and spoken_sid() == sid_of(own),
              (heard, spoken_sid(), sid_of(own)))
        check("... though the preset still says what it wants - this path just never asks",
              (M.voice_for_speech() or {}).get("fallback") == "bm_george"
              and not hasattr(SP, "_personality_voice"), M.voice_for_speech())
        plain = FakeVoices(78, 1.15)
        kept = SP.tts_voice(plain, plain=True)
        check("a crisis answer keeps the owner's own voice, with no pitch rise",
              kept == (78, 1.15, 0.0) and plain.asked == ["speaker", "speaker_speed"],
              (kept, plain.asked))


def t_a_personality_applies_its_voice_through_the_picker():
    with Folder():
        own = pick("af_sarah", "af_bella")
        V.handle_post("/api/voice/voices/speaker", {"speaker": own})
        M.handle_set({"sync_voice_with_personality": False})
        M.set_personality("dry_wit")
        check("with the lock off a personality switch applies no voice at all",
              shown_name() == own and M.voice_for_speech() is None,
              (shown_name(), M.voice_for_speech()))

        calls = []
        real = V.set_speaker_name

        def spy(name):
            calls.append(name)
            return real(name)

        V.set_speaker_name = spy
        try:
            M.handle_set({"sync_voice_with_personality": True})
            M.set_personality("classic_butler")
        finally:
            V.set_speaker_name = real
        check("the preset's voice is applied through the picker's own set_speaker_name",
              calls == ["bm_lewis", "bm_george"], calls)
        check("... from turning the lock ON and from a personality switch - both, not one",
              len(calls) == 2 and shown_name() == "bm_george"
              and spoken_sid() == sid_of("bm_george"),
              (len(calls), shown_name(), spoken_sid()))


def t_the_speed_is_one_setting_too():
    with Folder():
        V.handle_post("/api/voice/voices/speed", {"speed": "faster"})
        M.set_personality("classic_butler")   # its own voice_speed is 1.02
        sid, pace, semis = SP.tts_voice(V)
        check("the spoken pace is the owner's one speed setting, not the preset's 1.02",
              abs(pace - 1.15) < 1e-9, pace)
        check("... a personality never adds a pitch of its own", semis == 0.0, semis)
        check("... and the speed both apps show agrees with it",
              abs(float(V.speed_view()["value"]) - pace) < 1e-9,
              (V.speed_view()["value"], pace))


def t_a_crisis_answer_keeps_the_plain_voice():
    with Folder():
        M.set_personality("classic_butler")
        M.handle_set({"sync_voice_with_personality": False})
        V.handle_post("/api/voice/voices/speaker", {"speaker": pick("af_sarah", "af_bella")})
        plain = SP.tts_voice(V, plain=True)
        check("the plain voice is the owner's own choice, with no pitch rise",
              plain[0] == V.speaker() and plain[2] == 0.0, plain)


def t_nothing_private_reaches_an_audit_line_or_an_event():
    with Folder():
        M.set_personality("classic_butler")
        V.handle_post("/api/voice/voices/speaker", {"speaker": pick("af_sarah", "af_bella")})
        V.handle_post("/api/voice/voices/speed", {"speed": "slower"})
        events = folder_events()
        check("every `voices` event is a doorbell: {what, outcome} and nothing else",
              bool(events) and all(set(e) <= {"what", "outcome"} for e in events), events)
        details = [d for _e, d in folder_audits()]
        check("every audit line holds ids and names only",
              all(set(d) <= {"speaker", "speed"} for d in details), details)
        check("... none of which is a word the owner said",
              all(isinstance(v, str) and " " not in v for d in details for v in d.values()),
              details)


def main():
    # Each `with Folder()` starts from an empty settings folder, so nothing in
    # this suite touches the owner's own manner.json or voices/state.json.
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
