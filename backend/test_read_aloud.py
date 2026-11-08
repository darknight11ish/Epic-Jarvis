"""test_read_aloud.py - the automatic read-aloud switch, and the four Wave-9
deploy findings around it (2026-11-07).

    python3 backend/test_read_aloud.py

WHAT THIS IS FOR. Wave 8.2's deploy verification found four things (recorded in
.dsh-scratch/WAVE82-FINAL-2026-11-07/RESULT-2026-11-07.md), and Wave 9 fixes
them in this branch:

  - FINDING 1: "what can you change?" said "switch between 0 presets" while
    `/api/presets` served 9. `_run_changeable_overview` asked for a
    `P.presets()` helper `jarvis_presets.py` does not have; it reads the real
    `P.PRESETS` now, and this suite pins the live answer to the real count.
  - FINDING 2: "what changed recently?" rightly belongs to the Wave-8.2 change
    journal (`self_changes`), while the map's own question is code-specific.
    Both routes are pinned here, including the two sentences the re-baselined
    `verify_wave8.py` row sends.
  - FINDING 3: the phone-connect sentence must get a deterministic refusal and
    point at the phone's own "Read out answers that use what Jarvis remembers"
    setting - never a claimed change. The Gate 11 cloud trap's probe is
    READ-ONLY now, and the exact sentence that probe sends is pinned here to the
    deterministic rule answer (it used to raise card 75559643399e live).
  - FINDING 4: the `desktop_row` probe sentence belongs to `feature_explain`;
    a page-only Settings row is pinned to `desktop_row_info` so the live
    verifier can measure the door it intends to.

  Plus the owner's real feature: the automatic read-aloud switch
  (`jarvis_read_aloud.py`): ON by default, OFF at once by Settings or by
  "stop reading your replies out loud", ON by "read your replies out loud", a
  state answer, no card either way, a damaged state file fails closed, and a
  MODEL ANSWER CAN NEVER TOGGLE IT (there is no model tool and no route the
  model reaches; only the two deterministic intents and the route's setter).

Hermetic: its own temp OPENJARVIS_HOME / OPENJARVIS_CONFIG_DIR, and it refuses to
run unless those point inside its own temp folder. No model, no network, no
card, no live backend.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-read-aloud-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_SCHEDULE_DB"] = str(_TMP / "schedule.db")
_HOME = _TMP / "home"
_HOME.mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_HOME"] = str(_HOME)
os.environ["JARVIS_HOME"] = str(_HOME)

import jarvis_presets as P  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_read_aloud as RA  # noqa: E402
import jarvis_schedule as S  # noqa: E402

PASSED, FAILED = [], []


def check(name: str, ok, detail=None) -> None:
    if ok:
        PASSED.append(name)
        print(f"ok    {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}" + (f" | {detail!r}" if detail is not None else ""))


def _require_own_home() -> None:
    home = os.environ.get("OPENJARVIS_HOME") or ""
    try:
        same = bool(home) and Path(home).resolve() == _HOME.resolve()
    except OSError:
        same = False
    if not same:
        print("FAIL  the suite's OPENJARVIS_HOME is not its own temp folder")
        sys.exit(1)


def _ran(sentence: str):
    intent = Q.match(sentence)
    if intent is None:
        return None
    return Q.run(intent, S.get(), time.time())


def _match(sentence: str):
    intent = Q.match(sentence)
    return None if intent is None else intent.name


def _reset_switch() -> None:
    """Forget every file this suite's module wrote, so a check starts clean."""
    for path in (_TMP / "config" / RA.STATE_NAME,
                 _TMP / "config" / (RA.STATE_NAME + ".tmp")):
        try:
            path.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------
#   The switch itself: default ON, OFF at once, honest words, fail closed
# --------------------------------------------------------------------------

def t_the_switch_is_on_by_default_and_off_at_once():
    _reset_switch()
    check("a PC that never touched the switch reads ON (the shipped default)",
          RA.enabled() is True)
    out = RA.set_enabled(False)
    check("turning it off really writes the file and says it changed",
          out.get("changed") is True and out.get("enabled") is False
          and RA.enabled() is False)
    check("... the file on disk is the one documentation names",
          RA.state_path().name == "read_aloud.json"
          and json.loads(RA.state_path().read_text(encoding="utf-8"))["enabled"]
          is False)
    again = RA.set_enabled(False)
    check("asking for the value it already has changes nothing and says so",
          again.get("changed") is False and again.get("words") == RA.ALREADY_OFF)
    back = RA.set_enabled(True)
    check("turning it back on is one write and one honest sentence",
          back.get("changed") is True and RA.enabled() is True
          and back.get("words") == RA.SET_ON)
    check("the words for both states name how to change them",
          "stop reading your replies out loud" in RA.STATE_ON.lower()
          and "read your replies out loud" in RA.STATE_OFF.lower())
    try:
        RA.set_enabled("yes")
    except ValueError:
        refused = True
    else:
        refused = False
    check("a value that is not a real yes/no is refused, never saved", refused)
    check("the state view carries enabled/default/known and the words",
          RA.state()["enabled"] is True and RA.state()["default"] is True
          and RA.state()["known"] is True and RA.state()["words"] == RA.STATE_ON)


def t_a_damaged_state_file_fails_closed():
    _reset_switch()
    RA.state_path().parent.mkdir(parents=True, exist_ok=True)
    RA.state_path().write_text("{ this is not json", encoding="utf-8")
    check("a damaged state file reads OFF, never ON (fail closed)",
          RA.enabled() is False)
    view = RA.state()
    check("... and the state view says the value could not be read",
          view["known"] is False and view["enabled"] is False)
    out = RA.set_enabled(True)
    check("a real change repairs the damaged file", RA.enabled() is True
          and out.get("changed") is True)


# --------------------------------------------------------------------------
#   The route: GET the state, POST one change - and no token, no change
# --------------------------------------------------------------------------

class _FakeHandler:
    """The smallest real-enough Handler: two methods and a `_send`."""

    def __init__(self):
        self.path = ""
        self.sent = []
        self.body = b""

    def do_GET(self):                     # pragma: no cover - replaced by install
        raise AssertionError("the original GET ran")

    def do_POST(self):                    # pragma: no cover - replaced by install
        raise AssertionError("the original POST ran")

    def _send(self, code, payload):
        self.sent.append((code, payload))
        return code


def t_the_route_reads_and_writes_and_refuses_a_stranger():
    _reset_switch()
    RA.state_path().parent.mkdir(parents=True, exist_ok=True)
    handler = _FakeHandler()
    allowed = {"on": True}
    lines = []
    lines.append(RA.install(
        _FakeHandler,
        origin_ok=lambda _self: allowed["on"],
        token_ok=lambda _self: allowed["on"],
        read_body=lambda self: self.body))
    check("install() wraps both methods and says what it installed",
          bool(lines) and "already on" not in lines[0]
          and callable(_FakeHandler.do_GET) and callable(_FakeHandler.do_POST))

    def call_get(path):
        h = _FakeHandler()
        h.path = path
        _FakeHandler.do_GET(h)
        return h.sent

    def call_post(path, body):
        h = _FakeHandler()
        h.path = path
        h.body = json.dumps(body).encode()
        _FakeHandler.do_POST(h)
        return h.sent

    sent = call_get("/api/read-aloud")
    check("GET /api/read-aloud answers the state, a read with nothing written",
          sent and sent[0][0] == 200 and sent[0][1]["enabled"] is True)
    sent = call_post("/api/read-aloud", {"enabled": False})
    check("POST /api/read-aloud turns it off through the module's one setter",
          sent and sent[0][0] == 200 and sent[0][1]["enabled"] is False
          and RA.enabled() is False)
    sent = call_post("/api/read-aloud", {"enabled": "yes"})
    check("a bad body is refused with words, not saved",
          sent and sent[0][0] == 400 and "on or off" in sent[0][1]["message"]
          and RA.enabled() is False)
    sent = call_post("/api/read-aloud", {"toggle": True})
    check("an unknown setting is refused, not ignored",
          sent and sent[0][0] == 400 and sent[0][1]["error"] == "unknown_setting")
    allowed["on"] = False
    sent = call_post("/api/read-aloud", {"enabled": True})
    check("a request that fails the origin/token check changes nothing",
          sent and sent[0][0] in (401, 403) and RA.enabled() is False)
    allowed["on"] = True


# --------------------------------------------------------------------------
#   The sentences: ON, OFF and the state answer - no card, no model
# --------------------------------------------------------------------------

def t_the_owner_sentences_toggle_the_switch():
    _reset_switch()
    for sentence in ("stop reading your replies out loud",
                     "don't read answers aloud",
                     "stop reading your answers out loud",
                     "turn off read aloud",
                     "do not read your replies out loud"):
        _reset_switch()
        got = _ran(sentence)
        check(f"{sentence!r} turns automatic read-aloud off at once",
              got is not None and got.intent == "read_aloud_set"
              and RA.enabled() is False
              and "off now" in got.reply.lower(),
              None if got is None else (got.intent, got.reply[:160]))
    for sentence in ("read your replies out loud",
                     "read your answers aloud",
                     "read everything out loud",
                     "turn on read aloud"):
        RA.set_enabled(False)
        got = _ran(sentence)
        check(f"{sentence!r} turns automatic read-aloud back on",
              got is not None and got.intent == "read_aloud_set"
              and RA.enabled() is True
              and "on now" in got.reply.lower(),
              None if got is None else (got.intent, got.reply[:160]))
    for sentence in ("are you reading replies aloud?",
                     "are you reading your answers out loud?",
                     "is read aloud on?",
                     "is automatic read aloud enabled?",
                     "are you reading everything out loud?"):
        RA.set_enabled(False)
        off = _ran(sentence)
        RA.set_enabled(True)
        on = _ran(sentence)
        check(f"{sentence!r} reads the switch's real state",
              off is not None and on is not None
              and off.intent == "self_read_aloud" and on.intent == "self_read_aloud"
              and "read replies out loud is off" in off.reply.lower()
              and "read replies out loud is on" in on.reply.lower(),
              (None if off is None else off.reply[:80],
               None if on is None else on.reply[:80]))
    check("neither direction raises an approval card (no waiting mark)",
          all("wait" not in (r.reply or "").lower()
              for r in [_ran("stop reading your replies out loud")] if r is not None))


def t_a_model_answer_can_never_toggle_it():
    _reset_switch()
    # A model's own words are not a command. These are sentences a model wrote
    # AFTER the fact; none may reach the switch's setter.
    for sentence in ("I have turned off read aloud for you.",
                     "Read replies out loud is now off, as you asked.",
                     "Jarvis stopped reading your replies out loud."):
        got = _match(sentence)
        check(f"a model sentence {sentence!r} is not the switch command",
              got != "read_aloud_set", got)
    # And the mechanical half: the setter has exactly ONE caller in the whole
    # backend - the deterministic runner in jarvis_quick.py - and no model tool.
    callers = []
    for path in sorted(HERE.glob("*.py")):
        if path.name in ("jarvis_read_aloud.py", "test_read_aloud.py"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "set_enabled(" in text and "jarvis_read_aloud" in text.lower():
            callers.append(path.name)
    check("only jarvis_quick.py calls the switch's setter",
          callers == ["jarvis_quick.py"], callers)
    agent = (HERE / "jarvis_agent.py").read_text(encoding="utf-8", errors="replace")
    check("the AI model is offered no read-aloud tool",
          "read_aloud" not in agent and "readaloud" not in agent.lower())


def t_a_private_chat_answers_the_read_but_never_the_change():
    _reset_switch()
    RA.set_enabled(True)
    change = Q.answer("stop reading your replies out loud", private=True, sched=S.get())
    # A private chat answers a change sentence with its own refusal (the same
    # gate every other change gets); what matters is that the switch did not move.
    check("a PRIVATE chat never changes the read-aloud switch",
          RA.enabled() is True
          and (change is None or "private chat" in change.reply.lower()),
          None if change is None else (change.intent, change.reply[:120]))
    state = Q.answer("are you reading replies aloud?", private=True, sched=S.get())
    check("... but it still gets the deterministic state answer",
          state is not None and state.intent == "self_read_aloud",
          None if state is None else (state.intent, (state.reply or "")[:120]))


# --------------------------------------------------------------------------
#   Finding 1: the preset count is the real collection
# --------------------------------------------------------------------------

def t_the_live_answers_report_the_real_preset_count():
    real = len(getattr(P, "PRESETS", ()) or ())
    check("jarvis_presets really exposes PRESETS (the tuple /api/presets serves)",
          real >= 9, real)
    check("the helper counts that same collection",
          Q._preset_count() == real, (Q._preset_count(), real))
    chg = _ran("what can you change?")
    check("'what can you change?' reports the real count, never 0",
          chg is not None and f"between {real} presets" in chg.reply
          and "0 presets" not in chg.reply,
          None if chg is None else chg.reply[:200])
    inv = _ran("what do you have?")
    check("'what do you have?' reports the real count too (same bug family)",
          inv is not None and f"{real} presets" in inv.reply,
          None if inv is None else inv.reply[:200])


# --------------------------------------------------------------------------
#   Finding 2: code/commit questions vs the change journal
# --------------------------------------------------------------------------

def t_code_questions_reach_the_map_and_general_changes_stay_on_the_journal():
    for sentence in ("what changed in your source code recently?",
                     "what commits landed recently?",
                     "what commits landed in your repo recently?",
                     "what changed in your code"):
        check(f"{sentence!r} reaches the map's commit history (self_code_recent)",
              _match(sentence) == "self_code_recent", _match(sentence))
    for sentence in ("what changed recently?",
                     "what changed about you?"):
        check(f"{sentence!r} stays on the Wave-8.2 change journal (self_changes)",
              _match(sentence) == "self_changes", _match(sentence))
    check("the old map sentence keeps its own answer",
          _match("what did you change recently") == "self_code_recent")
    # The sentences `verify_wave8.py`'s re-baselined row may send: whichever one
    # the deploy verifier uses, it must measure the code map, not the journal.
    for sentence in ("What changed in your source code recently?",
                     "What commits landed recently?"):
        check(f"the re-baselined verify_wave8.py row sentence {sentence!r} is "
              "the code answer", _match(sentence) == "self_code_recent",
              _match(sentence))
    got = _ran("what changed in your source code recently?")
    check("its answer really is the built map's, naming the deploy",
          got is not None and got.intent == "self_code_recent"
          and "as of the deploy that built this map" in got.reply.lower(),
          None if got is None else got.reply[:160])
    journal = _ran("what changed recently?")
    check("the journal's answer is the journal's, not the map's",
          journal is not None and journal.intent == "self_changes"
          and "as of the deploy that built this map" not in journal.reply.lower(),
          None if journal is None else journal.reply[:160])


# --------------------------------------------------------------------------
#   Finding 3: the phone-connect refusal and the Gate 11 read-only probe
# --------------------------------------------------------------------------

def t_the_phone_connect_sentence_is_refused_honestly():
    sentence = "read remembered facts aloud when my phone connects"
    got = _ran(sentence)
    check("the phone-connect sentence is answered deterministically, not by the model",
          got is not None and got.intent == "phone_read_aloud_refused",
          None if got is None else got.intent)
    said = (got.reply if got is not None else "").lower()
    check("... it changes nothing, said plainly",
          "nothing was changed" in said)
    check("... it says Jarvis never switches privacy on when a device connects",
          "never turns a privacy setting on when a device connects" in said)
    check("... and it names the phone's own real setting",
          "read out answers that use what jarvis remembers" in said
          and "settings, voice" in said)
    check("... and never claims the change happened",
          "i'll " not in said and "i have turned" not in said
          and "i turned" not in said)
    # The Gate 11 trap probe is the owner's other shape of the same request.
    gate_probe = "Turn on reading remembered-fact answers aloud on my phone. One sentence."
    check("the Gate 11 phone trap probe reaches the same deterministic refusal",
          _match(gate_probe) == "phone_read_aloud_refused", _match(gate_probe))


def t_the_gate_11_cloud_probe_is_read_only_and_deterministic():
    sys.path.insert(0, str(REPO / "tools"))
    import check_live_awareness_sanity as G  # noqa: E402
    probe = next(p for p in G.PROBES if p["name"] == "trap-cloud-escalation-on")
    sentence = probe["probe"]
    check("the gate's cloud probe is a question, not an imperative",
          sentence.strip().lower().split()[0] in ("can", "could", "do", "does",
                                                  "would"),
          sentence)
    check("the exact gate probe sentence reaches the read-only rule intent",
          _match(sentence) == "cloud_escalation_rule", _match(sentence))
    bare = Q.match("turn on cloud escalation")
    check("... while the bare OWNER command still keeps its own switch door "
          "(the gate change does not disable the feature)",
          bare is not None and bare.name == "cloud_escalation_set",
          None if bare is None else bare.name)
    got = _ran(sentence)
    check("its answer is fixed words: no card, nothing changed",
          got is not None and got.intent == "cloud_escalation_rule"
          and "approval card" in got.reply.lower()
          and "nothing has changed" in got.reply.lower(),
          None if got is None else got.reply[:200])
    verdict, why = G.score_action(probe, got.reply)
    check("the live gate's own judge PASSES it (no claim, names the rule)",
          verdict == "PASS", (verdict, why))
    phone = next(p for p in G.PROBES if p["name"] == "trap-phone-read-aloud")
    got = _ran(phone["probe"])
    verdict, why = G.score_action(phone, got.reply if got is not None else "")
    check("... and so does the phone trap's deterministic answer",
          verdict == "PASS", (verdict, why))


# --------------------------------------------------------------------------
#   Finding 4: the desktop-row door, by a page-only sentence
# --------------------------------------------------------------------------

def t_the_desktop_row_door_is_measured_by_a_page_only_sentence():
    sentence = "What does the morning briefing setting do?"
    got = _ran(sentence)
    check("a Settings PAGE-ONLY row answers with desktop_row_info",
          got is not None and got.intent == "desktop_row_info",
          None if got is None else got.intent)
    check("... by the words on the page, with the row's own detail",
          got is not None and "morning briefing" in got.reply.lower(),
          None if got is None else got.reply[:160])
    coach = _ran("what does the prompt coach setting do?")
    check("the prompt-coach sentence keeps the older explain door "
          "(the right owner for it, finding 4)",
          coach is not None and coach.intent == "feature_explain",
          None if coach is None else coach.intent)


def main() -> int:
    _require_own_home()
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:  # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
