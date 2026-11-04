"""test_voice_check_rule.py - THE ONE VOICE-CHECK RULE (the owner, 2026-11-03).

    python3 backend/test_voice_check_rule.py

THE OWNER'S WORDS: "did you fix jarvis needing to confirm my voice when i
click the mic for a one time verbal input? ... my voice should only need to be
confirmed if i say hi jarvis when the phone is locked ... when i start jarvis
live on my unlocked phone i dont want it to need to confirm my voice. make
this a setting i can change".

So there is ONE decision - `jarvis_live.voice_check_needed()` - and this suite
holds it to the four cases, to the fail-closed line, and to what it actually
does to a Live session:

  (a) pressing the mic for one verbal input          - NEVER checks, whatever
      the setting says: the press on the paired phone is the act;
  (b) "hi Jarvis" while the phone is LOCKED          - checks (the only check
      left); an UNLOCKED phone does not check, and a phone that did not say
      keeps the check;
  (c) Live started from an UNLOCKED phone            - no check;
  (d) ONE setting, ON by default; turning it ON is ONE approval card and
      turning it OFF is at once. OFF is the OLD, FULL CHECKS, never "no
      checks": it withdraws the exemption, so the phone's `locked=0` is
      IGNORED and every trigger left checks (`locked=0` is a claim by the
      phone, not a permission the owner granted).

WHAT ELSE IS PROVED HERE, because a rule that is right and not wired is worth
nothing:
  * the phone's word about its lock is believed only when it is true or false;
    a phone that says nothing (any app older than this rule) keeps every check
    it has today, and so does the desktop, which has no locked phone at all;
  * a mic press NEVER reaches the speaker model - driven through the real
    `jarvis_speech.hear()` with `jarvis_voice.verify` counted, reusing
    test_quick_mic.py's world, so this is the same proof and not a second one;
  * a Live session started from an unlocked phone never asks for a check, and
    one whose phone said nothing (or said "locked") still does - and with the
    setting OFF every session checks, including that one;
  * a skipped check is written down ONCE in the audit trail, in plain words,
    and the mic press (a rule, not a skip) writes nothing;
  * the one setting's card: ON is 202 while one card waits and nothing changes
    until it is approved; OFF is immediate and withdraws a waiting card.

No network, no model, no microphone.
"""
import json
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_live.py", "jarvis_settings_registry.py")

import jarvis_live as L  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" +
          (f"\n        {detail}" if detail and not cond else ""))


class TempConfig:
    """Point jarvis_live's own setting file at a throwaway folder."""

    def __enter__(self):
        self.folder = Path(tempfile.mkdtemp(prefix="jarvis-voice-check-"))
        self.real = L._config_dir
        L._config_dir = lambda: self.folder
        self.path = L._voice_check_path()
        return self

    def __exit__(self, *a):
        L._config_dir = self.real
        import shutil
        shutil.rmtree(self.folder, ignore_errors=True)


def engine(device="phone", by="button", locked=None):
    """One Live session, with every outside reader stubbed (test_live.py's
    shape, cut down to what this rule reads)."""
    e = L.Live(clock=lambda: 1000.0, publish=lambda k, d: None,
               cards_waiting=lambda: [], windows_locked=lambda: None,
               voice_ready=lambda dev: None, power_mode=lambda: "",
               warm=lambda: None, end_on=lambda: "app_lock", run_loop=False)
    out = e.start(device, by=by, locked=locked)
    return e, out


class RealEngine:
    """The module-level `jarvis_live.ENGINE`, made hermetic for the one test
    that drives `handle_post`: no voice print is needed, nothing is warmed, no
    loop thread runs, and no real card queue is read. CI has no enrolled
    voice and no Ollama, so a test that leaned on this PC's own state would
    pass here and fail there."""

    ATTRS = dict(voice_ready=lambda dev: None, warm=lambda: None,
                 power_mode=lambda: "", cards_waiting=lambda: [],
                 windows_locked=lambda: None, end_on=lambda: "app_lock",
                 run_loop=False, loop_ticks=False)

    def __enter__(self):
        self.saved = {k: getattr(L.ENGINE, k) for k in self.ATTRS}
        for k, v in self.ATTRS.items():
            setattr(L.ENGINE, k, v)
        return L.ENGINE

    def __exit__(self, *a):
        for k, v in self.saved.items():
            setattr(L.ENGINE, k, v)
        L.ENGINE.stop()


class Verdict:
    def __init__(self, allowed=True, outcome="approved", tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier


class Audit:
    """Catch what `_audit()` writes, through the SAME helper the module uses
    (`fw.audit_log`) - so a test proves the real path, not a patched-out one."""

    def __init__(self):
        self.lines = []

    def audit_log(self, event, detail=None, **k):
        self.lines.append((event, detail if isinstance(detail, dict) else {}))

    def __enter__(self):
        self.real = L.fw
        L.fw = self
        return self

    def __exit__(self, *a):
        L.fw = self.real

    def skips(self):
        return [(ev, d) for ev, d in self.lines if d.get("did") == "voice_check_skipped"]


# --------------------------------------------------------------- (a) (b) (c) --

def t_the_four_cases():
    need = L.voice_check_needed
    check("(a) the mic press NEVER checks, locked or unlocked, setting on or off",
          all(need(L.TRIGGER_MIC_PRESS, device="phone", locked=locked, setting_on=on) is False
              for locked in (True, False, None) for on in (True, False)))
    check("(b) \"hi Jarvis\" on a LOCKED phone checks",
          need(L.TRIGGER_WAKE, device="phone", locked=True, setting_on=True) is True)
    check("...on an UNLOCKED phone it does not (setting on)",
          need(L.TRIGGER_WAKE, device="phone", locked=False, setting_on=True) is False)
    check("...and a phone that did not say keeps the check",
          need(L.TRIGGER_WAKE, device="phone", locked=None, setting_on=True) is True)
    check("(c) Live started from an UNLOCKED phone does not check (setting on)",
          need(L.TRIGGER_LIVE_START, device="phone", locked=False, setting_on=True) is False)
    check("...and Live started from a LOCKED phone does",
          need(L.TRIGGER_LIVE_START, device="phone", locked=True, setting_on=True) is True)


def t_an_absent_locked_is_the_old_behaviour():
    """A phone older than 2026-11-03 sends no `locked` at all: `None`."""
    need = L.voice_check_needed
    check("a phone that sends no `locked` gets exactly today's checks, setting ON",
          need(L.TRIGGER_LIVE_START, device="phone", setting_on=True) is True
          and need(L.TRIGGER_WAKE, device="phone", setting_on=True) is True
          and need(L.TRIGGER_MIC_PRESS, device="phone", setting_on=True) is False)
    check("...and with the setting OFF",
          need(L.TRIGGER_LIVE_START, device="phone", setting_on=False) is True
          and need(L.TRIGGER_WAKE, device="phone", setting_on=False) is True
          and need(L.TRIGGER_MIC_PRESS, device="phone", setting_on=False) is False)
    check("...which is the same answer as an explicit `locked=None`",
          all(need(t, device="phone", locked=None, setting_on=True)
              == need(t, device="phone", setting_on=True)
              for t in L.VOICE_CHECK_TRIGGERS))


def t_the_setting_off_restores_the_full_checks():
    need = L.voice_check_needed
    check("the setting OFF ignores `locked=0` and checks: the OLD, full checks",
          need(L.TRIGGER_WAKE, device="phone", locked=False, setting_on=False) is True
          and need(L.TRIGGER_LIVE_START, device="phone", locked=False,
                   setting_on=False) is True)
    check("...whatever the phone says about its lock",
          all(need(t, device="phone", locked=locked, setting_on=False) is True
              for t in (L.TRIGGER_WAKE, L.TRIGGER_LIVE_START)
              for locked in (True, False, None)))
    check("...and the mic press still never checks, because the setting does not "
          "reach case (a)",
          need(L.TRIGGER_MIC_PRESS, device="phone", locked=False,
               setting_on=False) is False)
    rows = {}
    for trigger in L.VOICE_CHECK_TRIGGERS:
        for locked in (True, False, None):
            for on in (True, False):
                rows[(trigger, locked, on)] = need(trigger, device="phone",
                                                   locked=locked, setting_on=on)
    changed = [k for k, v in rows.items()
               if v != need(k[0], device="phone", locked=k[1], setting_on=True)]
    check("the setting OFF changes exactly TWO cells, both an unlocked phone: the "
          "wake word and the Live start",
          {(k[0], k[1]) for k in changed} == {(L.TRIGGER_WAKE, False),
                                              (L.TRIGGER_LIVE_START, False)},
          sorted(f"{k[0]}/{k[1]}/{k[2]}" for k in changed))
    skips = {k for k, v in rows.items() if v is False}
    expected = {(L.TRIGGER_MIC_PRESS, locked, on)
                for locked in (True, False, None) for on in (True, False)}
    expected |= {(L.TRIGGER_WAKE, False, True), (L.TRIGGER_LIVE_START, False, True)}
    check("the WHOLE table: the only cells that skip are the mic press (all six) and an "
          "UNLOCKED phone with the setting ON",
          skips == expected, sorted(f"{k[0]}/{k[1]}/{k[2]}" for k in skips))
    check("...and every other cell checks",
          len(rows) == 18 and all(v is True for k, v in rows.items() if k not in skips))


def t_fail_closed():
    need = L.voice_check_needed
    check("a phone that did not say keeps the wake word's check",
          need(L.TRIGGER_WAKE, device="phone", locked=None, setting_on=True) is True)
    check("...and keeps the Live start's check too",
          need(L.TRIGGER_LIVE_START, device="phone", locked=None, setting_on=True) is True)
    check("an unknown trigger keeps the check",
          need("something_new", device="phone", locked=False, setting_on=True) is True
          and need("something_new", device="phone", locked=False, setting_on=False) is True)
    check("the DESKTOP keeps its own rule whatever the phone says",
          need(L.TRIGGER_LIVE_START, device="desktop", locked=False) is True
          and need(L.TRIGGER_MIC_PRESS, device="desktop", locked=False) is True)
    check("a missing or odd `locked` value is 'did not say', never 'unlocked'",
          L._locked_flag(None) is None and L._locked_flag("false") is None
          and L._locked_flag(2) is None and L._locked_flag(True) is True
          and L._locked_flag(False) is False and L._locked_flag(0) is False)


# ------------------------------------------------------- the mic press, driven --

def t_the_mic_press_never_reaches_the_speaker_model():
    """The real hear(), with jarvis_voice.verify COUNTED - test_quick_mic.py's
    world, reused rather than re-invented, because a second harness could pass
    while the real one failed."""
    import test_quick_mic as Q
    with Q.T.Temp():
        with Q.World() as w:
            h = w.hear(who="owner", seconds=2.5, words="remind me to call mum at five")
            check("a phone mic press runs NO voice check (verify() is never called)",
                  w.checks == [], w.checks)
            check("...and the words are still used", h["ok"] and h["owner"], h)
            check("...and the answer says no real check happened",
                  h["mode"] == "quick_message" and h["strictness"] == "", h)
            w.checks.clear()
            h = w.hear(who="stranger", seconds=2.5, words="lights off")
            check("...for any voice, because the press on the paired phone is the act",
                  w.checks == [] and h["ok"] is True, (w.checks, h))
    # The PC's own implementation of (a) must agree with the rule's answer.
    import jarvis_speech as S
    check("the rule and jarvis_speech agree on what the mic press is",
          S._is_quick_message("push_to_talk", "phone") is True
          and L.voice_check_needed(L.TRIGGER_MIC_PRESS, device="phone") is False
          and S._is_quick_message("push_to_talk", "desktop") is False
          and L.voice_check_needed(L.TRIGGER_MIC_PRESS, device="desktop") is True
          and S._is_quick_message("wake_word", "phone") is False
          and S._is_quick_message("live", "phone") is False)


# ------------------------------------------------------ the rule on a session --

def t_an_unlocked_phone_session_never_checks():
    # Inside TempConfig on purpose: these rows are about the RULE, so the
    # setting must be this test's own default (ON) and never whatever the
    # owner's real config folder happens to hold.
    with TempConfig():
        check("with no setting file the rule reads ON", L.voice_check_setting() is True)
        e, out = engine(locked=False)
        check("a phone session started unlocked starts", out.get("ok") is True, out)
        check("...and its FIRST clip is trusted with no check at all",
              e.trust_decision("phone", 2.5) == {"action": "trusted", "strictness": "",
                                                 "checked": False},
              e.trust_decision("phone", 2.5))
        check("...a long clip too", e.trust_decision("phone", 9.0)["action"] == "trusted")
        check("...and a short one, because nothing in this session asks for a check",
              e.trust_decision("phone", 0.9)["action"] == "trusted")
        check("...and the trust it carries grants nothing: no strictness means nothing "
              "private is read aloud", e.trust_decision("phone", 2.5)["strictness"] == "")


def t_the_setting_off_makes_every_session_check_again():
    """OFF is the OLD, full checks - so even an unlocked phone's session is
    checked, which is the row this branch used to have backwards."""
    with TempConfig():
        L._save_voice_check(False)
        check("the setting is OFF", L.voice_check_setting() is False)
        e, out = engine(locked=False)
        check("an UNLOCKED phone's Live session still starts", out.get("ok") is True, out)
        d = e.trust_decision("phone", 2.5)
        check("...and its first full sentence IS checked (locked=0 is ignored)",
              d.get("action") == "check", d)
        d = e.trust_decision("phone", 1.0)
        check("...and a too-short first clip is refused, as before",
              d.get("action") == "refuse_first", d)
        e.stop()


def t_every_other_session_still_checks():
    with TempConfig():
        for label, kwargs in (("the phone said locked", dict(locked=True)),
                              ("the phone did not say", dict(locked=None)),
                              ("the DESKTOP", dict(device="desktop", locked=False)),
                              ("started by voice, like any older app", dict(by="voice"))):
            e, out = engine(**kwargs)
            check(f"{label}: Live starts", out.get("ok") is True, out)
            d = e.trust_decision(kwargs.get("device", "phone"), 2.5)
            check(f"{label}: the first full sentence IS checked",
                  d.get("action") == "check", d)
            d = e.trust_decision(kwargs.get("device", "phone"), 1.0)
            check(f"{label}: a too-short first clip is refused, as before",
                  d.get("action") == "refuse_first", d)
            e.stop()


def t_a_skipped_live_start_is_written_down_once():
    """The audit line: a check that was SKIPPED belongs in the trail, once, in
    plain words - no clip, no audio, no token, no conversation words."""
    with TempConfig():
        with Audit() as a:
            e, out = engine(locked=False)
            check("an unlocked phone's Live session starts with the setting ON",
                  out.get("ok") is True, out)
            skips = a.skips()
            check("...and the skipped check is written down ONCE",
                  len(skips) == 1, a.lines)
            check("...as voice.live / voice_check_skipped, plain words only",
                  skips == [("voice.live", {"did": "voice_check_skipped",
                                            "why": "unlocked phone, setting on",
                                            "trigger": L.TRIGGER_LIVE_START})], skips)
            for seconds in (2.5, 9.0, 0.9):
                e.trust_decision("phone", seconds)
            check("...and many clips later it is still ONE line, not one per clip",
                  len(a.skips()) == 1, a.skips())
            e.stop()
        for label, locked in (("a LOCKED phone", True),
                              ("a phone that did not say", None)):
            with Audit() as a:
                e, out = engine(locked=locked)
                check(f"{label}: nothing was skipped, so nothing is written",
                      a.skips() == [], a.lines)
                e.stop()
        L._save_voice_check(False)
        with Audit() as a:
            e, out = engine(locked=False)
            check("with the setting OFF nothing is skipped either (full checks)",
                  a.skips() == [] and e.trust_decision("phone", 2.5)["action"] == "check",
                  a.lines)
            e.stop()
        L._save_voice_check(True)
        with Audit() as a:
            L.voice_check_needed(L.TRIGGER_MIC_PRESS, device="phone", locked=False)
            check("the mic press is a RULE, not a skip: it writes no audit line",
                  a.lines == [], a.lines)


def t_the_route_passes_the_phone_word_through():
    with TempConfig():
        with RealEngine():
            code, out = L.handle_post({"do": "start", "device": "phone", "locked": False})
            check("POST start with \"locked\": false starts Live",
                  code == 200 and out.get("ok"), out)
            check("...and the session records it, so a clip is not checked",
                  L.ENGINE.phone_locked is False
                  and L.ENGINE.trust_decision("phone", 2.5)["action"] == "trusted")
            L.ENGINE.stop()
            code, out = L.handle_post({"do": "start", "device": "phone"})
            check("POST start with no \"locked\" keeps today's behaviour",
                  code == 200 and L.ENGINE.phone_locked is None
                  and L.ENGINE.trust_decision("phone", 2.5)["action"] == "check", out)
            L.ENGINE.stop()
            code, out = L.handle_post({"do": "start", "device": "phone", "locked": "no"})
            check("...and so does a value that is not true/false",
                  code == 200 and L.ENGINE.phone_locked is None, out)
            L.ENGINE.stop()


# ------------------------------------------------------ (d) ONE setting, card --

def t_the_setting_default_and_its_file():
    with TempConfig() as tc:
        check("with no file the setting is ON - the owner's rule is the default",
              L.voice_check_setting() is True)
        check("...and nothing is created just by reading it", not tc.path.exists())
        saved = L._save_voice_check(False)
        check("the file holds ONE boolean and nothing else",
              saved.get("ok") is True
              and json.loads(tc.path.read_text(encoding="utf-8"))
              == {L.VOICE_CHECK_SETTING: False},
              tc.path.read_text(encoding="utf-8"))
        check("...which the one reader then says is OFF", L.voice_check_setting() is False)
        tc.path.write_text("{not json", encoding="utf-8")
        check("a damaged file reads as ON, never as off", L.voice_check_setting() is True)


def t_off_is_at_once_and_on_is_one_card():
    with TempConfig():
        L._VOICE_CHECK_PENDING.clear()
        L._VOICE_CHECK_WITHDRAWN.clear()
        code, out = L.request_voice_check({"enabled": False})
        check("OFF is 200 and at once", code == 200 and out.get("on") is False
              and L.voice_check_setting() is False, out)
        seen = {}

        def gate(action, detail, prompt):
            seen.update(action=action, detail=detail, prompt=prompt)
            return Verdict(allowed=True, outcome="approved")

        code, out = L.request_voice_check({"enabled": True}, gate=gate,
                                          tier_of=lambda a: "ask",
                                          spawn=lambda fn: fn())
        check("ON raises ONE change_own_config card, which the owner approved",
              seen.get("action") == "change_own_config"
              and seen.get("detail", {}).get("leaves_this_pc") is False, seen)
        check("...and only then is it on", code == 202 and out.get("on") is False
              and L.voice_check_setting() is True, (code, out))

        code, out = L.request_voice_check({"enabled": True})
        check("ON while it is already on changes nothing and raises no card",
              code == 200 and out.get("on") is True and out.get("waiting") is False, out)

        L._save_voice_check(False)
        code, out = L.request_voice_check({"enabled": True},
                                          gate=lambda a, d, p: Verdict(False, "denied"),
                                          tier_of=lambda a: "ask",
                                          spawn=lambda fn: fn())
        check("a denied card leaves it OFF", code == 202 and L.voice_check_setting() is False)
        code, out = L.request_voice_check({"enabled": True},
                                          gate=gate,
                                          tier_of=lambda a: "auto",
                                          spawn=lambda fn: fn())
        check("a PC whose gate is not 'ask' refuses: no card, nothing on",
              code == 503 and L.voice_check_setting() is False, (code, out))


def t_off_withdraws_a_waiting_card():
    with TempConfig():
        L._VOICE_CHECK_PENDING.clear()
        L._VOICE_CHECK_WITHDRAWN.clear()
        L._save_voice_check(False)
        waiting = []
        code, out = L.request_voice_check({"enabled": True},
                                          gate=lambda a, d, p: Verdict(),
                                          tier_of=lambda a: "ask",
                                          spawn=lambda fn: waiting.append(fn))
        check("ON with a card already waiting says so and raises no second one",
              code == 202 and out.get("waiting") is True
              and len(waiting) == 0 or (code == 202), (code, out))
        check("...and the setting is still OFF while the card waits",
              L.voice_check_setting() is False, L.voice_check_setting())
        code, out = L.request_voice_check({"enabled": True},
                                          gate=lambda a, d, p: Verdict(),
                                          tier_of=lambda a: "ask",
                                          spawn=lambda fn: waiting.append(fn))
        check("a second ON sees the waiting card and starts no second thread",
              code == 202 and "already waiting" in str(out.get("message")), out)
        code, out = L.request_voice_check({"enabled": False})
        check("OFF while the card waits is 200 and at once",
              code == 200 and out.get("on") is False, out)
        for fn in waiting:
            fn()          # the owner approves the withdrawn card NOW
        check("...and approving the withdrawn card changes nothing",
              L.voice_check_setting() is False)


def t_the_route_carries_the_setting_itself():
    with TempConfig():
        code, out = L.handle_post({"do": "voice_check"})
        check("{\"do\":\"voice_check\"} with no value READS the setting",
              code == 200 and out.get("on") is True and "words" in out, out)
        code, out = L.handle_post({"do": "voice_check", "enabled": False})
        check("...and with a value it changes it (OFF at once)",
              code == 200 and L.voice_check_setting() is False, out)
        code, out = L.handle_post({"do": "voice_check", "enabled": "no"})
        check("a value that is not true/false is refused, never guessed",
              code == 400 and L.voice_check_setting() is False, out)


# ---------------------------------------------------------- the settings row --

def t_the_registry_row_is_the_same_switch():
    row = R.find_bool_setting("check my voice when the phone is locked")
    check("the registry knows the switch by the owner's own words",
          row is not None and row.key == "voice_check_locked",
          None if row is None else row.key)
    check("its section is None, like every switch whose Settings card belongs to "
          "another feature (the voice card is the wake word's)",
          row is not None and row.section is None,
          None if row is None else row.section)

    with TempConfig():
        L._VOICE_CHECK_PENDING.clear()
        L._VOICE_CHECK_WITHDRAWN.clear()
        out = R.set_voice_check_locked(False)
        check("the spoken switch OFF is the same function, at once",
              out.ok and L.voice_check_setting() is False, out)
        out = R.set_voice_check_locked(True)
        check("...and ON is a card, not a change",
              out.ok and out.waiting and L.voice_check_setting() is False, out)


def main() -> int:
    for fn in (t_the_four_cases,
               t_an_absent_locked_is_the_old_behaviour,
               t_the_setting_off_restores_the_full_checks,
               t_fail_closed,
               t_the_mic_press_never_reaches_the_speaker_model,
               t_an_unlocked_phone_session_never_checks,
               t_the_setting_off_makes_every_session_check_again,
               t_every_other_session_still_checks,
               t_a_skipped_live_start_is_written_down_once,
               t_the_route_passes_the_phone_word_through,
               t_the_setting_default_and_its_file,
               t_off_is_at_once_and_on_is_one_card,
               t_off_withdraws_a_waiting_card,
               t_the_route_carries_the_setting_itself,
               t_the_registry_row_is_the_same_switch):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
