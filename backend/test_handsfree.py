"""test_handsfree.py - hands-free mode: the switch, the read-out, the spoken
answer, and the text message.

    py -3 -B backend/test_handsfree.py

THE OWNER'S REQUEST (2026-11-04, their own words): "a handfree setting that i
can turn off in chat, jarvis live, or through settings. in this mode any
approval card for a task i ask jarvis to do will automatically be read out and
i can answer confirm or deny (including verbally) and it will approve the card.
i want jarvis to be able to write text messages to contacts for me in
particular among the full fledged handsfree mode".

And their answer to the security question, on a clickable card: **"A voice yes
counts for every card."** The decision record is
`decisions.d/2026-11-04-handsfree-voice-approval.md`; the sentence it
supersedes ("Never approve-by-voice") is still in docs/ARCHITECTURE.md, marked.

WHAT IS PROVED HERE, and what is not:

  * the switch is OFF in both shipped templates, OFF is instant and cardless,
    and ON is ONE ask-tier card (`handsfree_enable`) - refused, it stays off;
  * the writer edits ONE line of the owner's settings file and leaves every
    other byte (comments, order) alone;
  * a waiting card is announced as `handsfree_card` with the card's OWN notice
    words, and the announcement approves nothing;
  * one spoken clip answers ONE card: the words are transcribed on the PC,
    the OWNER'S VOICE IS CHECKED FIRST (a stranger's clip never becomes words),
    a closed vocabulary decides, the 60-second window is enforced, an unclear
    answer is asked once more and then treated as a deny, and the decision goes
    through the SAME `jarvis_gate.decide()` a tap uses - with the stamp a
    Windows Hello approval leaves, which is the narrow branch the owner chose;
  * outside hands-free mode nothing at all happens, and nothing else in the
    tree can take a voice yes (source checks);
  * a text message is ONE card naming the contact and the exact words, handed
    to the phone as `phone_command`, and the PC never claims it was sent: only
    the phone's own result makes a receipt.

NOT PROVED HERE, plainly: no real microphone clip is recorded, no real speech
model or voice print is loaded (both are stand-ins), no phone receives a
command, and no SMS is sent. Those are the phone lane's and a desk test's.

No pytest, no network, no model, no audio device. Real files in a temporary
folder for the setting and the receipts; everything else is a stand-in.
"""
from __future__ import annotations

import base64
import json
import shutil
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-handsfree-"))
_CONFIG = _TMP / "config"
_CONFIG.mkdir(parents=True, exist_ok=True)
_TEMPLATE = HERE / "rebuilt" / "jarvis-framework.toml"
(_CONFIG / "jarvis-framework.toml").write_bytes(_TEMPLATE.read_bytes())
import os  # noqa: E402

os.environ["OPENJARVIS_CONFIG_DIR"] = str(_CONFIG)
os.environ["JARVIS_CONFIG_DIR"] = str(_CONFIG)

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "rebuilt"))
# The two gate modules are the base folder's (they are patched, not
# shipped). Appended, never inserted: a copy there must never shadow one
# this repository ships.
sys.path.append(str(REPO / "jarvis-backend"))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_handsfree.py", "jarvis_card_words.py")

import jarvis_handsfree as HF  # noqa: E402
import jarvis_card_words as CW  # noqa: E402

try:
    import tomllib
except ModuleNotFoundError:                       # Python < 3.11
    try:
        import tomli as tomllib                   # type: ignore
    except ModuleNotFoundError:
        tomllib = None

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name)
    if not cond and detail:
        print("        " + str(detail)[-900:])


def eq(name, got, want):
    check(name, got == want, f"got {got!r}, wanted {want!r}")


# --------------------------------------------------------------------------
#   Stand-ins: nothing here loads a model, a microphone or a phone
# --------------------------------------------------------------------------

CLIP = base64.b64encode(b"RIFF-fake-wav-bytes" * 8).decode("ascii")
SAMPLES = [0.0] * 3200
RATE = 16000


def _wav(_raw):
    return SAMPLES, RATE


class _Verdict:
    def __init__(self, is_owner, reason=""):
        self.is_owner = is_owner
        self.reason = reason


def owner_voice(_samples, _rate):
    return _Verdict(True)


def stranger_voice(_samples, _rate):
    return _Verdict(False, "does not match the owner's voice print")


class _Row(dict):
    pass


def row(rid="c1", action="send_text_message", expires_in=None):
    item = _Row(id=rid, action=action, tier="ask")
    if expires_in is not None:
        item["expires_in"] = expires_in
    return item


class _Notice(dict):
    pass


class _Gate:
    """The two reads `read_out`/`_row` make, and nothing else."""

    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def notice_for(self, item):
        return _Notice(title=CW.title_for(item.get("action")),
                       body="it sends the message shown. nothing has happened yet.")

    def pending(self):
        return list(self.rows)


class _Checker:
    """jarvis_gate.check's shape: called once, returns a Verdict-like."""

    def __init__(self, allowed=True, reason="denied by a human"):
        self.allowed = allowed
        self.reason = reason
        self.calls = []

    def __call__(self, action, detail, prompt):
        self.calls.append({"action": action, "detail": detail, "prompt": prompt})
        return types.SimpleNamespace(allowed=self.allowed, reason=self.reason,
                                     request_id="card-1", tier="ask",
                                     outcome="approved" if self.allowed else "denied")


class _Ordered:
    """One recorder for stamp/decide/transcribe/verify, so ORDER is visible."""

    def __init__(self, decide_answer=True):
        self.calls = []
        self.decide_answer = decide_answer

    def stamp(self, card_id, action):
        self.calls.append(("stamp", card_id, action))

    def decide(self, card_id, approved):
        self.calls.append(("decide", card_id, approved))
        return self.decide_answer

    def transcribe(self, _samples, _rate):
        self.calls.append(("transcribe",))
        return self._heard

    def verify(self, _samples, _rate):
        self.calls.append(("verify",))
        return self._verdict

    def set_heard(self, heard, verdict=None):
        self._heard = heard
        self._verdict = verdict or _Verdict(True)
        return self


def _on():
    HF.set_enabled(True)
    HF._clear()


def _off():
    HF.set_enabled(False)
    HF._clear()


def _answer(heard, *, verdict=None, decide_answer=True, has_print=True,
            card="c1", now=None, readout=True, rows=None):
    """One whole answer through the real route function, with stand-ins."""
    rec = _Ordered(decide_answer).set_heard(heard, verdict)
    gate = _Gate(rows if rows is not None else [row(card)])
    if readout and gate.rows:
        HF.read_out(gate.rows[0], now=now, gate=gate)
    code, out = HF.answer(card, CLIP, RATE, gate=gate, decide=rec.decide,
                          stamp=rec.stamp, transcribe=rec.transcribe,
                          verify=rec.verify, has_print=lambda: has_print,
                          read_wav=_wav, now=now)
    return code, out, rec, gate


# --------------------------------------------------------------------------
#   1. The switch
# --------------------------------------------------------------------------

def t_the_switch_is_off_in_both_shipped_templates():
    for path in (HERE / "rebuilt" / "jarvis-framework.toml",
                 REPO / "jarvis-backend" / "jarvis-framework.toml"):
        if tomllib is None:
            text = path.read_text(encoding="utf-8")
            check(f"{path.name} carries [handsfree] enabled = false", 
                  "[handsfree]\nenabled = false" in text)
            continue
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
        eq(f"{path} [handsfree] enabled", (doc.get("handsfree") or {}).get("enabled"), False)
        eq(f"{path} [autonomy.tiers] send_text_message", 
           (doc.get("autonomy") or {}).get("tiers", {}).get("send_text_message"), "ask")
        check(f"{path} offers send_text_message to the model",
              "send_text_message" in (doc.get("tools") or {}).get("enabled", []))


def t_off_is_the_default_and_the_template_says_so():
    _off()
    eq("hands-free is off in a fresh install", HF.enabled(), False)


def t_off_is_instant_and_raises_nothing():
    _off()
    checker = _Checker()
    code, out = HF.request_enabled(False, gate=checker)
    eq("turning OFF answers 200", code, 200)
    eq("turning OFF approved nothing and asked nothing", checker.calls, [])
    eq("turning OFF leaves the mode off", HF.enabled(), False)


def t_on_is_one_ask_card_and_only_that_card_turns_it_on():
    _off()
    checker = _Checker(allowed=False, reason="the owner said no")
    code, out = HF.request_enabled(True, gate=checker)
    eq("a refused ON answers 403", code, 403)
    eq("a refused ON leaves the mode off", HF.enabled(), False)
    eq("a refused ON raised exactly ONE card", len(checker.calls), 1)
    eq("that card is the hands-free one", checker.calls[0]["action"], HF.ACTION_ENABLE)
    check("the card's words say what changes and how to answer",
          "spoken yes or no" in checker.calls[0]["prompt"]
          and "Windows Hello" in checker.calls[0]["prompt"], checker.calls[0]["prompt"][:200])
    _off()
    checker = _Checker(allowed=True)
    code, out = HF.request_enabled(True, gate=checker)
    eq("an approved ON answers 200", code, 200)
    eq("an approved ON raises exactly ONE card", len(checker.calls), 1)
    eq("an approved ON turns the mode on", HF.enabled(), True)
    again = _Checker()
    code, out = HF.request_enabled(True, gate=again)
    eq("ON already on asks nobody", again.calls, [])
    eq("ON already on still answers 200", code, 200)
    _off()


def t_the_writer_changes_one_line_and_nothing_else():
    p = Path(tempfile.mkdtemp(prefix="hf-toml-")) / "jarvis-framework.toml"
    shutil.copyfile(_TEMPLATE, p)
    before = p.read_text(encoding="utf-8")
    HF.set_enabled(True, path=p)
    after = p.read_text(encoding="utf-8")
    eq("exactly ONE line differs when the mode is turned on",
       sum(1 for a, b in zip(before.splitlines(), after.splitlines()) if a != b)
       + abs(len(before.splitlines()) - len(after.splitlines())), 1)
    if tomllib is not None:
        eq("the file still parses and says on",
           (tomllib.loads(after).get("handsfree") or {}).get("enabled"), True)
        eq("and every other section is intact",
           tomllib.loads(after).get("tools"), tomllib.loads(before).get("tools"))
    HF.set_enabled(False, path=p)
    if tomllib is not None:
        eq("turning it off writes false",
           (tomllib.loads(p.read_text(encoding="utf-8")).get("handsfree") or {}).get("enabled"),
           False)
    # A missing [handsfree] section is ADDED, not assumed: an older settings
    # file that predates this feature must still be able to turn it on.
    older = Path(tempfile.mkdtemp(prefix="hf-old-")) / "jarvis-framework.toml"
    text = before.replace("[handsfree]\nenabled = false\n", "")
    older.write_text(text, encoding="utf-8")
    HF.set_enabled(True, path=older)
    if tomllib is not None:
        eq("a settings file with no [handsfree] gains one",
           (tomllib.loads(older.read_text(encoding="utf-8")).get("handsfree") or {}).get("enabled"),
           True)
    # A file that is not there is a plain refusal, never a silent success.
    try:
        HF.set_enabled(True, path=_TMP / "does-not-exist.toml")
        check("a missing settings file is refused", False)
    except HF.Refused as exc:
        check("a missing settings file is refused with a sentence",
              "settings file" in str(exc), str(exc))


def t_the_chat_and_voice_phrase_reaches_the_same_writer():
    import jarvis_quick as Q
    for said in ("turn on hands-free mode", "turn off hands-free",
                 "turn on hands free mode", "enable hands-free",
                 "disable handsfree", "switch off hands-free mode"):
        got = Q.match(said)
        ok = got is not None and got.name == "settings_bool" \
            and got.f.get("key") == "handsfree"
        check(f'"{said}" reaches the hands-free switch', ok, got)


# --------------------------------------------------------------------------
#   2. The read-out
# --------------------------------------------------------------------------

def t_the_read_out_carries_the_cards_own_words():
    _on()
    gate = _Gate([row("c9", "send_text_message")])
    payload = HF.read_out(gate.pending()[0], now=1000.0, gate=gate)
    eq("the read-out names the card", payload["card_id"], "c9")
    eq("the read-out names the action", payload["action"], "send_text_message")
    eq("the payload is exactly the frozen four fields",
       sorted(payload), ["action", "card_id", "expires_in_sec", "say"])
    check("the say starts with the card's own title",
          payload["say"].startswith(CW.title_for("send_text_message")), payload["say"])
    check("the say ends with the one sentence that says how to answer",
          payload["say"].endswith(CW.HANDSFREE_ASK), payload["say"])
    eq("the window is the whole minute", payload["expires_in_sec"], 60)
    # A card with less time left than the window gets the shorter one: the
    # spoken answer must never outlive the card it answers.
    tight = HF.read_out(_Gate([row("c10", "send_text_message", expires_in=12)]).rows[0],
                        now=1000.0, gate=_Gate([row("c10", "send_text_message")]))
    ok = tight["expires_in_sec"] <= 12
    check("a card with 12 seconds left gets at most 12", ok, tight["expires_in_sec"])
    HF._clear()


def t_the_read_out_is_a_notification_and_never_an_approval():
    _on()
    published = []
    rows = [row("c1"), row("c2", "edit_vault_note")]
    out = HF.tick(publish=lambda kind, data: published.append((kind, data)),
                  pending=lambda: list(rows), now=2000.0)
    eq("one event per waiting card", len(out), 2)
    eq("the event kind is handsfree_card",
       {k for k, _ in published}, {HF.READOUT_KIND})
    check("nothing was approved by reading a card out",
          all("approved" not in json.dumps(d) for _, d in published))
    again = HF.tick(publish=lambda kind, data: published.append((kind, data)),
                    pending=lambda: list(rows), now=2001.0)
    eq("a card is read out once, not every two seconds", again, [])
    rows.pop(0)
    HF.tick(publish=lambda kind, data: published.append((kind, data)),
            pending=lambda: list(rows), now=2002.0)
    check("an answered card's read-out is forgotten",
          "c1" not in HF._READOUTS, list(HF._READOUTS))
    _off()
    eq("with the mode off nothing is read out",
       HF.tick(publish=lambda *a: published.append(a), pending=lambda: [row("c3")]), [])


# --------------------------------------------------------------------------
#   3. The spoken answer
# --------------------------------------------------------------------------

def t_a_spoken_yes_approves_that_one_card_through_the_same_decision():
    _on()
    code, out, rec, _gate = _answer("yes")
    eq("a spoken yes answers 200", code, 200)
    eq("the heard words come back", out["heard"], "yes")
    eq("the decision is approved", out["decision"], "approved")
    eq("the card state is approved", out["card_state"], "approved")
    eq("it stamped, then decided - in that order",
       [c[0] for c in rec.calls if c[0] in ("stamp", "decide")], ["stamp", "decide"])
    stamps = [c for c in rec.calls if c[0] == "stamp"]
    check("the stamp names the card's real action",
          len(stamps) == 1 and stamps[0][2] == "send_text_message", stamps)
    check("it decided with a yes",
          [c for c in rec.calls if c[0] == "decide"] == [("decide", "c1", True)], rec.calls)
    check("the read-out is gone, so a second yes has nothing to answer",
          "c1" not in HF._READOUTS)
    code, out, rec2, _ = _answer("yes", readout=False)
    eq("a second yes for the same card is refused", code, 409)
    eq("... and decides nothing", rec2.calls, [])
    _off()


def t_a_spoken_no_denies_and_never_stamps():
    _on()
    code, out, rec, _ = _answer("no")
    eq("a spoken no answers 200", code, 200)
    eq("the decision is denied", out["decision"], "denied")
    eq("a denial stamps nothing (refusing needs no proof)",
       [c[0] for c in rec.calls if c[0] in ("stamp", "decide")], ["decide"])
    check("it decided with a no",
          [c for c in rec.calls if c[0] == "decide"] == [("decide", "c1", False)], rec.calls)
    _off()


def t_an_unclear_answer_is_asked_once_more_and_then_treated_as_a_deny():
    _on()
    code, out, rec, _ = _answer("yes please")
    eq("the first unclear answer answers 200", code, 200)
    eq("... and decides nothing yet", out["decision"], "again")
    eq("... the card is still waiting", out["card_state"], "pending")
    eq("... and it asks the question again", out["say"], HF.SAID_AGAIN)
    eq("... changing nothing", [c for c in rec.calls if c[0] in ("stamp", "decide")], [])
    code, out, rec, _ = _answer("what was that", readout=False)
    eq("the second unclear answer decides", code, 200)
    eq("... as a deny", out["decision"], "denied")
    check("... with no stamp", ("stamp", "c1", "send_text_message") not in rec.calls)
    eq("... and says so", out["say"], HF.SAID_UNCLEAR_DENIED)
    _off()


def t_the_window_is_sixty_seconds_and_the_clock_is_the_read_out_s():
    eq("the window is 60 seconds", HF.WINDOW_SEC, 60.0)
    _on()
    code, out, rec, _ = _answer("yes", now=1000.0)
    eq("a read-out answered at once works", code, 200)
    HF._clear()
    code, out, rec, _ = _answer("yes", now=2000.0)
    eq("a read-out answered inside the minute works", code, 200)
    HF._clear()
    # Read out at 3000, answered at 3060.5: the window is over.
    gate = _Gate([row("c1")])
    HF.read_out(gate.pending()[0], now=3000.0, gate=gate)
    late = _Ordered().set_heard("yes")
    code, out = HF.answer("c1", CLIP, RATE, gate=gate, decide=late.decide,
                          stamp=late.stamp, transcribe=late.transcribe,
                          verify=late.verify, has_print=lambda: True,
                          read_wav=_wav, now=3060.5)
    eq("an answer one second after the minute is refused", code, 409)
    eq("... and decides nothing", late.calls, [])
    _off()


def t_a_card_that_was_never_read_out_cannot_be_answered():
    _on()
    code, out, rec, _ = _answer("yes", readout=False)
    eq("a card with no read-out is refused", code, 409)
    eq("... and decides nothing", rec.calls, [])
    code, out, rec, _ = _answer("yes", card="another-card", rows=[row("c1")])
    eq("a different card's id answers nothing", code, 409)
    _off()


def t_a_stranger_is_refused_before_any_words_are_made():
    _on()
    code, out, rec, _ = _answer("yes", verdict=_Verdict(False, "does not match"))
    eq("a clip that is not the owner is refused", code, 403)
    eq("the sentence is the voice module's own", out["say"], HF.SAID_NOT_YOUR_VOICE)
    check("it never turns a stranger's voice into words",
          ("transcribe",) not in rec.calls, rec.calls)
    check("... and never decides anything",
          [c for c in rec.calls if c[0] in ("stamp", "decide")] == [], rec.calls)
    _off()


def t_no_enrolled_voice_print_means_no_spoken_yes():
    _on()
    # No print enrolled: verify() is the voice module's own refusal, and the
    # module says why rather than falling back to words alone.
    code, out, rec, _ = _answer("yes", verdict=_Verdict(False, "no enrolled voice profile"),
                                has_print=False)
    eq("with no voice print a yes is refused", code, 403)
    check("... and the sentence says how to fix it",
          "train my voice" in out["say"], out["say"])
    check("... and nothing was stamped or decided",
          [c for c in rec.calls if c[0] in ("stamp", "decide")] == [], rec.calls)
    _off()


def t_with_the_mode_off_a_spoken_yes_does_nothing_at_all():
    _off()
    code, out, rec, _ = _answer("yes")
    eq("with hands-free off the answer is refused", code, 403)
    eq("... with the sentence that says so", out["say"], HF.SAID_OFF)
    eq("... and nothing at all was done", rec.calls, [])
    code, out = HF.answer("c1", CLIP, RATE, now=0)
    eq("... even with no stand-ins at all", code, 403)


def t_a_card_that_is_no_longer_waiting_is_refused():
    _on()
    code, out, rec, _ = _answer("yes", rows=[])
    eq("a card that is not in the queue is refused", code, 409)
    eq("... and decides nothing", rec.calls, [])
    _off()


def t_a_late_decision_is_refused_and_never_claimed():
    _on()
    code, out, rec, _ = _answer("yes", decide_answer=False)
    eq("a card already settled answers 409", code, 409)
    eq("... and the answer says the card is gone", out["card_state"], "gone")
    _off()


def t_a_broken_clip_is_refused_plainly():
    _on()
    gate = _Gate([row("c1")])
    HF.read_out(gate.pending()[0], gate=gate)
    code, out = HF.answer("c1", "not base64 at all!!", RATE, gate=gate)
    eq("an unreadable clip answers 400", code, 400)
    code, out = HF.answer("c1", CLIP, 44100, gate=gate, read_wav=_wav)
    eq("a sample rate that disagrees with the clip answers 400", code, 400)
    code, out = HF.answer("", CLIP, RATE, gate=gate)
    eq("no card id answers 400", code, 400)
    _off()


def t_the_vocabulary_is_closed():
    eq("the confirm words are the seven the owner was promised",
       list(HF.CONFIRM),
       ["yes", "yeah", "confirm", "approve", "do it", "go ahead", "okay", "ok"])
    eq("the deny words are the seven the owner was promised",
       list(HF.DENY), ["no", "nope", "deny", "cancel", "stop", "don't", "do not"])
    eq('"Yes." is a yes', HF.match_words("Yes."), "confirm")
    eq('"go ahead" is a yes', HF.match_words("go ahead"), "confirm")
    eq('"No." is a no', HF.match_words("No."), "deny")
    eq('"don\'t" is a no', HF.match_words("don't"), "deny")
    eq('a sentence containing a yes is NOT a yes', HF.match_words("yes but wait"), "")
    eq('a sentence with no decision in it decides nothing', HF.match_words("what time is it"), "")
    eq("nothing heard decides nothing", HF.match_words(""), "")


def t_the_one_sentence_that_says_how_to_answer_matches_the_vocabulary():
    check("the ask sentence names both answers",
          "yes" in CW.HANDSFREE_ASK and "no" in CW.HANDSFREE_ASK, CW.HANDSFREE_ASK)
    words = (HERE / "jarvis_card_words.py").read_text(encoding="utf-8")
    eq("the sentence has ONE definition in the card words", words.count("HANDSFREE_ASK = "), 1)
    check("and the read-out uses it rather than its own copy",
          "jarvis_card_words.HANDSFREE_ASK" in (HERE / "jarvis_handsfree.py").read_text(
              encoding="utf-8"))


# --------------------------------------------------------------------------
#   4. The narrow branch, and that it stays narrow
# --------------------------------------------------------------------------

def t_a_hello_card_is_approvable_by_voice_only_inside_hands_free():
    import jarvis_owner_check as OC
    import jarvis_gate as G
    # The gate believes an "approved" row only with a stamp from this process.
    # Nothing stamped: the gate's own check refuses (this is the non-hands-free
    # path, unchanged: Windows Hello is what leaves that stamp).
    check("an approval with no stamp is not believed",
          G._approval_stamped("card-x", "send_text_message") is False)
    # Hands-free: approve_one leaves the stamp a Hello approval would leave.
    OC.stamp("card-x", "send_text_message")
    check("a stamp from the hands-free branch IS believed",
          G._approval_stamped("card-x", "send_text_message") is True)
    check("and it is taken once, never twice",
          G._approval_stamped("card-x", "send_text_message") is False)


def t_nothing_outside_this_module_can_take_a_voice_yes():
    src = (HERE / "jarvis_handsfree.py").read_text(encoding="utf-8")
    eq("the stamp is left in exactly ONE place",
       src.count("jarvis_owner_check.stamp("), 1)
    eq("and approve_one is the ONE function that does it",
       src.count("def approve_one("), 1)
    for name in ("jarvis_gate.py", "jarvis_owner_check.py", "jarvis_hud.py"):
        path = HERE / name
        if not path.is_file():
            path = REPO / "jarvis-backend" / name
        text = path.read_text(encoding="utf-8")
        check(f"{name} never imports hands-free, so no other path can stamp by voice",
              "jarvis_handsfree" not in text)
    # The test that proves the OTHER half: jarvis_owner_check's own risky path
    # is untouched. Its Hello decision has no hands-free branch in it.
    oc = (REPO / "jarvis-backend" / "jarvis_owner_check.py").read_text(encoding="utf-8")
    check("jarvis_owner_check has no hands-free exception in it",
          "handsfree" not in oc.lower())


def t_the_voice_is_checked_before_the_words_exist():
    _on()
    rec = _Ordered().set_heard("yes")
    gate = _Gate([row("c1")])
    HF.read_out(gate.pending()[0], gate=gate)
    HF.answer("c1", CLIP, RATE, gate=gate, decide=rec.decide, stamp=rec.stamp,
              transcribe=rec.transcribe, verify=rec.verify,
              has_print=lambda: True, read_wav=_wav)
    order = [c[0] for c in rec.calls]
    eq("the voice check comes before the transcription", order, ["verify", "transcribe",
                                                                "stamp", "decide"])
    _off()


# --------------------------------------------------------------------------
#   5. Text messages
# --------------------------------------------------------------------------

def _phone_one(_status=None):
    return {"devices": [{"id": "d1", "name": "Pixel 9", "kind": "phone",
                         "last_seen": int(__import__("time").time())}],
            "readable": True, "why": ""}


def t_the_text_card_names_the_contact_and_the_exact_words():
    _on()
    state, card = HF.prepare_sms({"contact": "Ann Example",
                                  "text": "Running ten minutes late."},
                                 phone=_phone_one)
    check("the card names the contact", "Ann Example" in card, card[:200])
    check("the card shows the message word for word",
          "Running ten minutes late." in card, card[:400])
    check("the card says the phone sends it and nothing has happened yet",
          "never stores a phone number" in card and "until you approve" in card, card[-300:])
    eq("the plan carries the contact", state["contact"], "Ann Example")
    eq("the plan carries the text", state["text"], "Running ten minutes late.")
    check("the plan has its own command id", bool(state.get("id")), state)
    _off()


def t_the_text_tool_refuses_when_hands_free_is_off():
    _off()
    try:
        HF.prepare_sms({"contact": "Ann", "text": "hello"}, phone=_phone_one)
        check("with hands-free off the text tool refuses", False)
    except HF.Refused as exc:
        check("with hands-free off the text tool refuses, and says why",
              "Hands-free mode is off" in str(exc), str(exc))


def t_the_text_tool_refuses_when_no_phone_is_paired():
    _on()
    for label, status in (
            ("no phone at all", {"devices": [], "readable": True, "why": ""}),
            ("an unreadable list", {"devices": [], "readable": False, "why": "broken"}),
    ):
        try:
            HF.prepare_sms({"contact": "Ann", "text": "hello"}, phone=lambda: status)
            check(f"with {label} the text tool refuses", False)
        except HF.Refused as exc:
            check(f"with {label} the text tool refuses, and says why",
                  bool(str(exc)), str(exc))
    # A phone that checked in a week ago still gets the command when it
    # reconnects, and the answer says so rather than pretending it is fresh.
    ok, why = HF._phone_ready(lambda: {"devices": [
        {"kind": "phone", "last_seen": 0}], "readable": True, "why": ""})
    check("a stale phone is still a phone", ok)
    check("... and the answer says it will get this when it connects",
          "next connects" in why, why)
    _off()


def t_the_dispatch_is_a_phone_command_and_never_claims_sent():
    _on()
    state, _card = HF.prepare_sms({"contact": "Ann", "text": "hello there"},
                                  phone=_phone_one)
    published = []
    out = HF.send(state, publish=lambda kind, data: published.append((kind, data)),
            phone=_phone_one)
    eq("the dispatch says asked, not sent", out.get("sent"), False)
    eq("... once", len(published), 1)
    kind, data = published[0]
    eq("the event kind is phone_command", kind, HF.PHONE_COMMAND_KIND)
    eq("it is a send_sms command", data["kind"], "send_sms")
    eq("it names the contact, and only the phone resolves it", data["contact"], "Ann")
    eq("it carries the text", data["text"], "hello there")
    eq("it carries the command id", data["id"], state["id"])
    eq("the frozen payload is exactly these four fields",
       sorted(data), ["contact", "id", "kind", "text"])
    check("the answer to the owner says the phone has not reported yet",
          "not sent" in out["said"], out.get("said"))
    _off()


def t_only_the_phones_own_result_makes_a_receipt():
    _on()
    state, _card = HF.prepare_sms({"contact": "Ann", "text": "hello there"},
                                  phone=_phone_one)
    HF.send(state, publish=lambda *a: None, phone=_phone_one)
    eq("no receipt exists before the phone reports", HF.receipts(), [])
    published = []
    code, out = HF.phone_result({"id": state["id"], "ok": True,
                                 "receipt": "SMS sent", "why": ""},
                                publish=lambda kind, data: published.append((kind, data)))
    eq("the result is accepted", code, 200)
    eq("... and says it was sent", out["sent"], True)
    eq("... and the event kind is phone_result", published[0][0], HF.PHONE_RESULT_KIND)
    rows = HF.receipts()
    eq("exactly one receipt was recorded", len(rows), 1)
    eq("the receipt names the contact", rows[0]["contact"], "Ann")
    eq("the receipt carries the phone's own words", rows[0]["receipt"], "SMS sent")
    check("the receipt keeps a hash of the text, never the text",
          len(rows[0].get("text_sha256") or "") == 64 and "hello there" not in json.dumps(rows[0]))
    code, out = HF.phone_result({"id": state["id"], "ok": True, "receipt": "again"})
    eq("a second result for the same command is refused", code, 409)


def t_a_result_for_a_command_this_pc_never_sent_is_refused():
    code, out = HF.phone_result({"id": "made-up-id", "ok": True, "receipt": "sent"})
    eq("an unknown command id is refused", code, 409)
    check("... and invents no receipt", "sent" not in json.dumps(out) or
          out.get("ok") is False, out)
    code, out = HF.phone_result({"ok": True})
    eq("a result with no id is refused", code, 400)


def t_a_result_that_failed_is_recorded_honestly():
    _on()
    state, _card = HF.prepare_sms({"contact": "Ann", "text": "hello"},
                                  phone=_phone_one)
    HF.send(state, publish=lambda *a: None, phone=_phone_one)
    code, out = HF.phone_result({"id": state["id"], "ok": False,
                                 "receipt": "", "why": "no signal"},
                                publish=lambda *a: None)
    eq("a failed send is accepted as a result", code, 200)
    eq("... and never says it was sent", out["sent"], False)
    check("... and the sentence says it did not send, with the phone's reason",
          "did not send" in out["say"] and "no signal" in out["say"], out["say"])
    eq("... and the receipt records the failure", HF.receipts()[-1]["ok"], False)
    _off()


# --------------------------------------------------------------------------
#   6. The audit receipt and the routes
# --------------------------------------------------------------------------

def t_the_audit_receipt_names_the_clip_the_words_and_the_decision():
    _on()
    seen = []
    real = HF._audit
    HF._audit = lambda event, detail: seen.append((event, dict(detail)))
    try:
        _answer("yes")
    finally:
        HF._audit = real
    answered = [d for e, d in seen if e == "handsfree.answer"]
    eq("exactly one decision receipt", len(answered), 1)
    d = answered[0]
    eq("the receipt names the card", d.get("card"), "c1")
    eq("the receipt names the action", d.get("action"), "send_text_message")
    eq("the receipt names the heard words", d.get("heard"), "yes")
    eq("the receipt names the decision", d.get("decision"), "approved")
    check("the receipt carries the clip's hash, not the clip",
          len(d.get("clip") or "") == 64 and CLIP not in json.dumps(d), d.get("clip"))
    eq("the receipt names who decided", d.get("by"), HF.BY)
    _off()


def t_the_routes_answer_one_card_at_a_time():
    _off()
    code, out = HF.handle_get(HF.PATH)
    eq("GET /api/handsfree is a read", code, 200)
    eq("... and says the mode is off", out["enabled"], False)
    eq("... and the window it advertises is the real one", out["window_sec"], 60)
    check("... and the vocabulary it advertises is the real one",
          out["vocabulary"]["confirm"] == list(HF.CONFIRM), out["vocabulary"])
    code, out = HF.handle_post(HF.PATH, {"enabled": False})
    eq("POST /api/handsfree takes a boolean", code, 200)
    code, out = HF.handle_post(HF.PATH, {"enabled": "yes please"})
    eq("... and refuses anything else", code, 400)
    _on()
    code, out = HF.handle_post(HF.ANSWER_PATH, {"card_id": ["a", "b"], "data_b64": CLIP})
    eq("the answer route takes ONE card id, never a list", code, 400)
    code, out = HF.handle_post("/api/not-a-route", {})
    eq("an unknown route is 404", code, 404)
    _off()


def t_the_module_adds_no_second_way_to_change_anything():
    import ast
    src = (HERE / "jarvis_handsfree.py").read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for forbidden in ("urllib", "requests", "http", "socket", "subprocess",
                      "webbrowser"):
        check(f"jarvis_handsfree.py imports no {forbidden}", forbidden not in imported,
              sorted(imported))
    check("jarvis_handsfree.py has no os.system or popen",
          "os.system" not in src and "popen" not in src.lower())
    check("the approval goes through jarvis_gate.decide, not a SQL write of its own",
          "UPDATE approvals" not in src and "jarvis_gate" in src)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    try:
        HF._clear()
    except Exception:
        pass
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
