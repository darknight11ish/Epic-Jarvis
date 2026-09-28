"""Talk-to-type on the PC (the owner's decision, 2026-09-27; JARVIS-API.md
section 72).

    python3 test_talk_type.py

No pytest, no network, no microphone. The same stand-ins as
test_voice_strict.py (a speaker model that returns chosen vectors, a gate
that answers what the test says); the switch, the card and hear() are the
REAL jarvis_voice / jarvis_voice_enroll / jarvis_speech code, writing into a
temporary folder.

What it proves:
  1. The switch is OFF by default, and a damaged settings file reads as off.
  2. ON raises ONE card (change_own_config) and changes nothing until it is
     approved; deny, a timeout and a wrong tier change nothing.
  3. OFF is immediate, raises no card, and withdraws a waiting ON card.
  4. While off, a talk-to-type clip is refused before ANYTHING runs - not
     read, not checked, not transcribed.
  5. While on: the owner check still runs first (a stranger is refused and
     never transcribed), the words come back cleaned of "um"/"uh", nothing
     is noted for chat history or the delay table, and nothing is marked to
     be read aloud.
  6. The status the apps read carries the switch.
  7. clean_dictation() on its own (the lists adapted from Handy, MIT).
"""
import json
import sys
import traceback
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))

import test_voice_strict as T  # noqa: E402  (its helpers; its own suite runs only as __main__)
from test_voice_strict import (V, E, S, Gate, HeldGate, OWNER, STRANGER, Table,  # noqa: E402
                               Temp, Verdict, _clip, check)


def _setting(value, verdict=None, tier="ask", gate=None, spawn=T.run_sync):
    gate = gate or Gate(verdict or Verdict(True, outcome="approved"))
    code, out = E.stage(json.dumps({"mode": "talk_to_type", "value": value}).encode(),
                        gate=gate, tier_of=lambda a: tier, spawn=spawn)
    return code, out, gate


def t_off_by_default():
    with Temp():
        check("off by default", V.settings()["talk_to_type"] == "off"
              and not V.talk_to_type_on())
        V.settings_path().write_text("{not json", encoding="utf-8")
        check("an unreadable settings file: off", not V.talk_to_type_on())
        V.settings_path().write_text(json.dumps({"talk_to_type": "yes please"}))
        check("an unknown value: off", not V.talk_to_type_on())
        V.settings_path().unlink()
        try:
            V.set_setting("talk_to_type", "on")
            check("turning it on without a card is refused", False)
        except ValueError:
            check("turning it on without a card is refused", not V.talk_to_type_on())


def t_on_is_one_card():
    with Temp():
        for outcome, verdict, tier in (("denied", Verdict(False, outcome="denied"), "ask"),
                                       ("timed_out", Verdict(False, outcome="timed_out"), "ask"),
                                       ("refused", Verdict(True, tier="auto", outcome="approved"),
                                        "ask")):
            E._reset_for_tests()
            code, out, gate = _setting("on", verdict, tier)
            check(f"ON raises ONE card; {outcome}: it stays off",
                  code == 202 and len(gate.calls) == 1
                  and gate.calls[0][0] == "change_own_config"
                  and not V.talk_to_type_on()
                  and E.state()["last"]["outcome"] == outcome, (code, out, E.state().get("last")))
        E._reset_for_tests()
        code, out, gate = _setting("on", tier="notify")
        check("a wrong tier: refused before any card", code == 409 and not gate.calls
              and not V.talk_to_type_on(), (code, out))
        E._reset_for_tests()
        code, out, gate = _setting("on")
        action, detail, prompt = gate.calls[0]
        check("approved: it is on", code == 202 and V.talk_to_type_on()
              and E.state()["last"]["outcome"] == "setting_changed", E.state().get("last"))
        check("the card says what it is, in plain words",
              detail["what"] == "turn on talk-to-type on this PC"
              and detail["setting"] == "talk_to_type" and detail["to"] == "on"
              and "password box" in prompt and "not kept in chat history" in prompt
              and "If you say no" in prompt, detail)
        code, out, gate = _setting("on")
        check("already on: nothing asked", code == 200 and not gate.calls
              and out["changed"] is False, (code, out))
        check("the other voice settings are untouched",
              V.settings()["strictness"] == "very_strict"
              and V.settings()["hands_free"] == "same_as_button")


def t_off_is_immediate_and_withdraws():
    with Temp():
        V.set_setting("talk_to_type", "on", approved=True)
        code, out, gate = _setting("off")
        check("OFF: at once, no card", code == 200 and not gate.calls
              and not V.talk_to_type_on() and out["settings"]["talk_to_type"] == "off",
              (code, out))

        held = HeldGate(Verdict(True, outcome="approved"))
        threads = []

        def spawn(fn):
            th = T.threading.Thread(target=fn)
            threads.append(th)
            th.start()

        code, out, _ = _setting("on", gate=held, spawn=spawn)
        held.asked.wait(5)
        code2, out2, gate2 = _setting("off")
        held.release.set()
        for th in threads:
            th.join(5)
        check("OFF while the ON card waits: approving it later changes nothing",
              code == 202 and code2 == 200 and not gate2.calls and not V.talk_to_type_on()
              and E.state()["last"]["outcome"] == "withdrawn", E.state().get("last"))


def _owner_setup():
    small = Table("sherpa-onnx:357a834f702b", {"loud": OWNER, "quiet": STRANGER})
    V.enroll(["a", "b", "c"], embedder=Table(small.name, {"a": OWNER, "b": OWNER,
                                                           "c": OWNER}))
    return small


def t_hear_refuses_while_off():
    with Temp():
        small = _owner_setup()
        boom = mock.Mock(side_effect=AssertionError("something ran"))
        with mock.patch.object(V, "EcapaEmbedder", lambda: small), \
                mock.patch.object(S, "_read_wav", boom), \
                mock.patch.object(S, "_speech_span", boom), \
                mock.patch.object(V, "verify", boom), \
                mock.patch.object(S, "_transcribe", boom):
            h = S.hear(_clip("owner", 2.5), source="talk_to_type", mic="desktop")
        check("off: refused before the clip is even read",
              not h.is_owner and h.available is False and h.text == ""
              and "switched off" in h.reason and "Settings, Voice" in h.reason, h)
        with mock.patch.object(V, "talk_to_type_on", side_effect=RuntimeError):
            check("a voice module that cannot answer: off", S._talk_type_on() is False)
        with mock.patch.object(S, "jarvis_voice", None):
            check("no voice module at all: off", S._talk_type_on() is False)


def t_hear_while_on():
    # _note_for_history is the ONE door to chat history from hear() (it calls
    # jarvis_chat_log.note_transcript); watching it here keeps this suite
    # free of the encryption library that module needs.
    with Temp():
        small = _owner_setup()
        V.set_setting("talk_to_type", "on", approved=True)
        V.set_setting("privacy", "voice_is_enough", approved=True)
        noted, flowed = [], []
        with mock.patch.object(V, "EcapaEmbedder", lambda: small), \
                mock.patch.object(V, "strong_embedder", lambda *a: None), \
                mock.patch.object(S, "_speech_span", return_value="skip"), \
                mock.patch.object(S, "_stt_engine", return_value=object()), \
                mock.patch.object(S, "_note_for_history",
                                  lambda words, *a, **kw: noted.append(words)), \
                mock.patch.object(S, "_flow", lambda *a, **kw: flowed.append(a[:1])):
            with mock.patch.object(S, "_transcribe",
                                   return_value="Um, send the report to Sam uh tomorrow"):
                h = S.hear(_clip("owner", 2.5), source="talk_to_type", mic="desktop")
            check("the owner: the words, cleaned of um and uh",
                  h.is_owner and h.text == "Send the report to Sam tomorrow"
                  and h.source == "talk_to_type", h)
            check("nothing noted for chat history, nothing in the delay table",
                  noted == [] and flowed == [], (noted, flowed))
            check("nothing marked to be read aloud",
                  not (h.private_aloud or h.memory_aloud or h.sensitive_aloud), h)

            boom = mock.Mock(side_effect=AssertionError("a stranger was transcribed"))
            with mock.patch.object(S, "_transcribe", boom):
                h = S.hear(_clip("stranger", 2.5), source="talk_to_type", mic="desktop")
            check("a stranger: refused by the owner check, never transcribed",
                  not h.is_owner and h.text == "", h)

            with mock.patch.object(S, "_transcribe", boom):
                h = S.hear(_clip("owner", 1.0), source="talk_to_type", mic="desktop")
            check("too short: 'say a little more', before the check, never transcribed",
                  not h.is_owner and h.too_short and "say a little more" in h.reason, h)

            with mock.patch.object(S, "_transcribe", return_value="what is the time"):
                S.hear(_clip("owner", 2.5), source="push_to_talk", mic="desktop")
            check("the talk button still notes its words for chat history, as before",
                  noted == ["what is the time"], noted)


def t_status_carries_the_switch():
    with Temp():
        st = S.status()
        check("gate.talk_to_type is off by default",
              st["gate"]["talk_to_type"] == "off"
              and st["gate"]["settings"]["talk_to_type"] == "off"
              and st["gate"]["settings"]["choices"]["talk_to_type"] == ["off", "on"]
              and st["gate"]["settings"]["defaults"]["talk_to_type"] == "off",
              st["gate"].get("settings"))
        V.set_setting("talk_to_type", "on", approved=True)
        check("...and on once approved", S.status()["gate"]["talk_to_type"] == "on")
        check("the enroll route's own view says so too",
              E.settings_view()["talk_to_type"] == "on", E.settings_view())
        check("an older voice module (no key): \"\", so the app does not offer it",
              S._strict_state({})["talk_to_type"] == "")


def t_clean_dictation():
    cases = [
        ("Um, so I think we should go.", "So I think we should go."),
        ("I I I think uh this is fine", "I think this is fine"),
        ("hmm. OK then", "OK then"),
        ("The drum is umm loud", "The drum is loud"),
        ("Mum said hi", "Mum said hi"),
        ("Uhm. Yes.", "Yes."),
        ("the umbrella is here", "the umbrella is here"),
        ("I I think so", "I I think so"),
        ("  lots   of   space  ", "lots of space"),
        ("", ""),
        ("uh", ""),
    ]
    for said, typed in cases:
        got = S.clean_dictation(said)
        check(f"clean_dictation({said!r}) == {typed!r}", got == typed, got)


if __name__ == "__main__":
    for fn in (t_off_by_default, t_on_is_one_card, t_off_is_immediate_and_withdraws,
               t_hear_refuses_while_off, t_hear_while_on, t_status_carries_the_switch,
               t_clean_dictation):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            T.FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(T.PASSED)} passed, {len(T.FAILED)} failed, {len(T.SKIPPED)} skipped")
    if T.FAILED:
        print("failed: " + ", ".join(T.FAILED))
    sys.exit(1 if T.FAILED else 0)
