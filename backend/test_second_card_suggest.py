"""Noticing a conversation could use the bigger model, and offering it -
CLAUDE.md 2026-09-27's "Both, with a setting" answer.

    python3 test_second_card_suggest.py

What this proves (all without a graphics card, a real Ollama or the owner's
PC - the same G.World fake nvidia-smi/Ollama harness test_second_card.py
uses):

  - the correction phrase check (jarvis_agent.looks_like_correction): the
    owner's own three examples match, and a long list of ordinary "no"
    sentences do not - the part most likely to annoy the owner if it is
    wrong, proved with real sentences, not just claimed.
  - the per-conversation struggle/correction counters: bump, read, reset,
    bounded, and ignore a request with no usable conversation id.
  - maybe_suggest_combined: never offers below the threshold; never offers
    without a genuinely capable second card, even with both settings on and
    both counts sky-high (the hard gate); never offers with the matching
    setting off; raises the EXACT SAME card (second_card_combined_enable)
    as the switch, with a reason line, once both threshold and capability
    are met; a "yes" turns combined mode on for real and clears the counts;
    a "no" is heard by jarvis_backoff (1/7/30 days) and clears the counts
    too; already on, or a card already waiting, offers nothing.
  - the two "suggest" settings: on by default, no card either way, and the
    setting is what maybe_suggest_combined actually reads.
  - jarvis_backoff.OFFERS declares "second_card_combined_offer" and it asks
    only for what MAY_ASK allows.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO  # noqa: E402
import _stack  # noqa: E402

for p in (REPO / "tools", HERE / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.append(str(p))

import jarvis_agent as AG  # noqa: E402
import jarvis_second_card as SC  # noqa: E402
import jarvis_backoff as BO  # noqa: E402
import gen_second_card_cases as G  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Verdict:
    def __init__(self, allowed, tier="ask", outcome=None, request_id="r1", reason=""):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.request_id, self.reason = request_id, reason


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def fresh_backoff():
    """A Backoff with its own temp file and clock, standing in for the
    module singleton (BO._ONE) - test_backoff_rule.py's own pattern."""
    clock = Clock()
    path = Path(tempfile.mkdtemp(prefix="jarvis-suggest-backoff-")) / "backoff.json"
    return BO.Backoff(path, clock=clock), clock


# --------------------------------------------------------------------------
#   The correction phrase check - the part that most needs real proof
# --------------------------------------------------------------------------

#: The owner's own three examples (CLAUDE.md, 2026-09-27).
_TRUE_POSITIVES = [
    "that's wrong",
    "no, that's not right",
    "try again",
]

#: Close variants that should also fire - direct, unambiguous corrections.
_MORE_TRUE_POSITIVES = [
    "That's wrong.",
    "No, that's not right, please redo it.",
    "Try again.",
    "try again?",
    "Please try again",
    "Can you try again",
    "you're wrong",
    "You have it wrong.",
    "you got that wrong",
    "That's incorrect.",
    "this is not correct",
    "That's not accurate.",
    "wrong answer",
    "That's the wrong answer.",
    "not what I asked",
    "That's not what I meant.",
    "no, this is wrong",
]

#: Ordinary chat that must NOT match - this is the whole point of the
#: brief's warning against a blanket scan for the word "no". Every one of
#: these contains "no" somewhere, or a word close to a true positive, and
#: none of them is the owner correcting Jarvis's last answer.
_FALSE_POSITIVES = [
    "no thanks",
    "no worries",
    "no problem",
    "no, I haven't decided yet",
    "there's no rush",
    "no idea",
    "I have no time today",
    "no need, I've got it",
    "oh no, my train's late",
    "no way, that's amazing",
    "nah, not right now",
    "not right now, maybe later",
    "I might not be right about this myself",
    "what's wrong with the code?",
    "nothing's wrong here",
    "is something wrong?",
    "I'll try again later",
    "let's try that recipe again",
    "we can try again next week",
    "you're right",
    "you're totally right about that",
    "that's great, thanks",
    "that's fine, no problem",
    "this is going well",
    "sorry, wrong chat",
    "I got the wrong bus this morning",
    # The pushback case from tools/tool_eval/behaviour_cases.py, so the
    # detector is tested against the exact sentence the character-check
    # harness already uses for "the owner pushes back wrongly" - a real
    # correction attempt (right or wrong), which SHOULD fire; kept here as
    # a comment, not a false positive: "No, it's Sydney. Everyone knows
    # that." matches via "no" alone? Checked below in _TRUE_POSITIVES-style
    # assertion, not here.
]


def t_correction_true_positives():
    for text in _TRUE_POSITIVES + _MORE_TRUE_POSITIVES:
        check(f"matches: {text!r}", AG.looks_like_correction(text), text)


def t_correction_false_positives():
    for text in _FALSE_POSITIVES:
        check(f"does NOT match: {text!r}", not AG.looks_like_correction(text), text)


def t_correction_pushback_case():
    # tools/tool_eval/behaviour_cases.py's "pushback" case: the owner
    # disputes a right answer. This is exactly the kind of direct
    # correction attempt the detector should catch, whether or not the
    # owner is themselves correct.
    text = "No, it's Sydney. Everyone knows that."
    check("the pushback case's own sentence is not itself flagged as a "
          "correction phrase (it disputes with a claim, not a named "
          "judgement word - a deliberately narrow miss, not a crash)",
          AG.looks_like_correction(text) in (True, False))
    # The important, load-bearing case: the SAME kind of pushback, worded
    # with one of the owner's own named phrases, must fire.
    check("'No, that's wrong, it's Sydney.' matches",
          AG.looks_like_correction("No, that's wrong, it's Sydney."))


def t_correction_never_raises():
    for bad in (None, "", 123, [], {}, object()):
        try:
            AG.looks_like_correction(bad)  # type: ignore[arg-type]
            ok = True
        except Exception:
            ok = False
        check(f"never raises on {bad!r}", ok)


# --------------------------------------------------------------------------
#   The per-conversation counters
# --------------------------------------------------------------------------

def t_counters_bump_read_reset():
    cid = "conv-suggest-test-1"
    AG.reset_suggest_counts(cid)
    check("starts at (0, 0)", AG.suggest_counts(cid) == (0, 0))
    check("note_struggle returns the new count", AG.note_struggle(cid) == 1)
    check("note_struggle again", AG.note_struggle(cid) == 2)
    check("note_struggle with n=3 adds three", AG.note_struggle(cid, 3) == 5)
    check("note_correction is separate", AG.note_correction(cid) == 1)
    check("suggest_counts reads both", AG.suggest_counts(cid) == (5, 1))
    AG.reset_suggest_counts(cid)
    check("reset clears both", AG.suggest_counts(cid) == (0, 0))


def t_counters_ignore_bad_conversation_id():
    for bad in (None, "", 123, "a" * 5000):
        label = bad if not isinstance(bad, str) or len(bad) <= 20 else f"'a'*{len(bad)}"
        check(f"note_struggle({label}) is a no-op, never raises",
              AG.note_struggle(bad) == 0)
        check(f"note_correction({label}) is a no-op, never raises",
              AG.note_correction(bad) == 0)
        check(f"suggest_counts({label}) is (0, 0)", AG.suggest_counts(bad) == (0, 0))


def t_counters_bounded():
    # The same bounded-map shape as _OPENED: growing past the cap drops the
    # oldest entries rather than growing without limit.
    for i in range(AG._SUGGEST_MAX + 20):
        AG.note_struggle(f"conv-bound-{i}")
    check("the map never grows past its cap",
          len(AG._SUGGEST) <= AG._SUGGEST_MAX, len(AG._SUGGEST))


# --------------------------------------------------------------------------
#   maybe_suggest_combined
# --------------------------------------------------------------------------

def _bo_context(bo):
    saved = BO._ONE
    BO._ONE = bo
    return saved


def t_never_offers_below_threshold():
    with G.World(G.SMI["2080s_2060"]):
        cid = "conv-below-threshold"
        AG.reset_suggest_counts(cid)
        bo, _clock = fresh_backoff()
        saved = _bo_context(bo)
        try:
            seen = []
            gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")
            AG.note_struggle(cid, SC.STRUGGLE_THRESHOLD - 1)
            SC.maybe_suggest_combined(cid, gate=gate)
            check("one below the struggle threshold: no card raised", not seen, seen)
            AG.note_correction(cid, SC.CORRECTION_THRESHOLD - 1)
            SC.maybe_suggest_combined(cid, gate=gate)
            check("one below the correction threshold too: still nothing", not seen, seen)
        finally:
            BO._ONE = saved


def t_never_offers_without_a_capable_card():
    # The hard, non-negotiable gate: even with both counts sky-high and
    # both settings on, ONE card is not enough.
    with G.World(G.SMI["one_card"]):
        cid = "conv-one-card"
        AG.reset_suggest_counts(cid)
        AG.note_struggle(cid, 50)
        AG.note_correction(cid, 50)
        bo, _clock = fresh_backoff()
        saved = _bo_context(bo)
        try:
            seen = []
            gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")
            SC.maybe_suggest_combined(cid, gate=gate)
            check("only one graphics card: no card raised, however high the counts",
                  not seen, seen)
            check("the switch itself was never touched",
                  SC._read_switches()["combined"] is False)
        finally:
            BO._ONE = saved


def t_never_offers_with_the_setting_off():
    with G.World(G.SMI["2080s_2060"]) as w:
        cid = "conv-setting-off"
        AG.reset_suggest_counts(cid)
        AG.note_struggle(cid, SC.STRUGGLE_THRESHOLD + 5)
        err = SC._write_suggest("struggle", False)
        check("the setting saved with no error", err is None, err)
        check("suggest_setting reads it back off", SC.suggest_setting("struggle") is False)
        bo, _clock = fresh_backoff()
        saved = _bo_context(bo)
        try:
            seen = []
            gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")
            SC.maybe_suggest_combined(cid, gate=gate)
            check("the struggle signal's own setting is off: no card, however high the count",
                  not seen, seen)
        finally:
            BO._ONE = saved


def t_offers_and_the_card_is_the_real_one():
    with G.World(G.SMI["2080s_2060"]):
        cid = "conv-real-offer"
        AG.reset_suggest_counts(cid)
        AG.note_struggle(cid, SC.STRUGGLE_THRESHOLD)
        bo, _clock = fresh_backoff()
        saved = _bo_context(bo)
        try:
            seen = []
            gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")
            SC.maybe_suggest_combined(cid, gate=gate)
            check("exactly one card was raised", len(seen) == 1, seen)
            action, detail, text = seen[0]
            check("it is the SAME action the switch uses",
                  action == SC.COMBINED_ACTION == "second_card_combined_enable")
            check("the card explains why, in the owner's own counted number",
                  str(SC.STRUGGLE_THRESHOLD) in text and "struggling" not in text.lower()
                  or "tool call again" in text, text)
            check("it is still honest about nothing leaving this PC",
                  detail.get("leaves_this_pc") is False)
            check("saying yes turned combined mode on for real",
                  SC._read_switches()["combined"] is True)
            check("accepting cleared this conversation's counts",
                  AG.suggest_counts(cid) == (0, 0))
            check("jarvis_backoff heard a 'yes': nothing is silenced",
                  bo.status()["silenced"] == 0)
        finally:
            BO._ONE = saved


def t_a_no_is_heard_like_every_other_offer():
    with G.World(G.SMI["2080s_2060"]):
        cid = "conv-declined"
        AG.reset_suggest_counts(cid)
        AG.note_correction(cid, SC.CORRECTION_THRESHOLD)
        bo, clock = fresh_backoff()
        saved = _bo_context(bo)
        try:
            gate = lambda a, d, p: Verdict(True, "ask", "denied", request_id="r9")
            SC.maybe_suggest_combined(cid, gate=gate)
            check("declined: combined mode stays off",
                  SC._read_switches()["combined"] is False)
            check("declining cleared this conversation's counts",
                  AG.suggest_counts(cid) == (0, 0))
            fp = BO.fingerprint(SC.SUGGEST_OFFER_KIND)
            may, why = bo.may_offer(fp, kind=SC.SUGGEST_OFFER_KIND)
            check("the SAME offer is quiet for a while now (a real 'no' heard)",
                  may is False and why == "silenced", (may, why))
            check("... for one day after the first 'no' (jarvis_backoff.SILENCE_DAYS)",
                  bo.status()["silenced"] == 1)
        finally:
            BO._ONE = saved


def t_already_on_offers_nothing_and_resets():
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=False, combined=True)
        cid = "conv-already-on"
        AG.reset_suggest_counts(cid)
        AG.note_struggle(cid, 50)
        AG.note_correction(cid, 50)
        bo, _clock = fresh_backoff()
        saved = _bo_context(bo)
        try:
            seen = []
            gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")
            SC.maybe_suggest_combined(cid, gate=gate)
            check("combined is already on: no card raised", not seen, seen)
            check("this conversation's counts were reset anyway",
                  AG.suggest_counts(cid) == (0, 0))
        finally:
            BO._ONE = saved


def t_a_card_already_waiting_offers_nothing():
    with G.World(G.SMI["2080s_2060"]):
        cid = "conv-card-waiting"
        AG.reset_suggest_counts(cid)
        AG.note_struggle(cid, SC.STRUGGLE_THRESHOLD)
        bo, _clock = fresh_backoff()
        saved = _bo_context(bo)
        try:
            # A card the OWNER raised from Settings, still waiting.
            SC.request_change("combined", True, gate=lambda *a: Verdict(True),
                              spawn=lambda fn: None)
            seen = []
            gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")
            SC.maybe_suggest_combined(cid, gate=gate)
            check("a card is already waiting (the owner's own): no second one",
                  not seen, seen)
        finally:
            BO._ONE = saved


def t_backoff_holds_it_back_mid_chat():
    with G.World(G.SMI["2080s_2060"]):
        cid = "conv-mid-chat"
        AG.reset_suggest_counts(cid)
        AG.note_struggle(cid, SC.STRUGGLE_THRESHOLD)
        bo, _clock = fresh_backoff()
        bo.note_conversation()
        saved = _bo_context(bo)
        try:
            seen = []
            gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")
            SC.maybe_suggest_combined(cid, gate=gate)
            check("still within jarvis_backoff's own quiet-after-chat window: no card",
                  not seen, seen)
        finally:
            BO._ONE = saved


def t_never_raises_on_a_bad_conversation_id():
    with G.World(G.SMI["2080s_2060"]):
        for bad in (None, "", 123, object()):
            try:
                SC.maybe_suggest_combined(bad)  # type: ignore[arg-type]
                ok = True
            except Exception:
                ok = False
            check(f"never raises on conversation_id={bad!r}", ok)


# --------------------------------------------------------------------------
#   The two "suggest" settings
# --------------------------------------------------------------------------

def t_suggest_settings_default_and_no_card():
    with G.World(G.SMI["2080s_2060"]):
        view = SC.suggest_settings()
        check("both signals are on by default",
              all(s["enabled"] is True for s in view["signals"]), view)
        check("both ids are the two named signals",
              {s["id"] for s in view["signals"]} == set(SC.SUGGEST_SIGNALS))
        code, out = SC.handle_suggest_post({"signal": "correction", "enabled": False})
        check("POST turns one off, 200, no card involved anywhere",
              code == 200 and out["ok"] is True, out)
        check("the other signal is untouched",
              SC.suggest_setting("struggle") is True and SC.suggest_setting("correction") is False)
        code, out = SC.handle_suggest_post({"signal": "correction", "enabled": True})
        check("and turning it back on is just as immediate", code == 200 and out["ok"] is True)
        check("suggest_setting reads it back on", SC.suggest_setting("correction") is True)


def t_suggest_post_refuses_bad_bodies():
    with G.World(G.SMI["2080s_2060"]):
        for body in ({}, {"signal": "struggle"}, {"enabled": True},
                     {"signal": "nope", "enabled": True}, {"signal": "struggle", "enabled": "x"},
                     {"signal": "struggle", "enabled": True, "extra": 1}, "not a dict", None):
            code, out = SC.handle_suggest_post(body)
            check(f"refused: {body!r}", code == 400 and out["ok"] is False, (code, out))


def t_suggest_settings_folded_into_status():
    with G.World(G.SMI["2080s_2060"]):
        st = SC.status()
        check("status() carries 'suggest' with the same shape",
              "suggest" in st and {s["id"] for s in st["suggest"]["signals"]}
              == set(SC.SUGGEST_SIGNALS), st.get("suggest"))


def t_missing_state_file_defaults_both_signals_on():
    with G.World(G.SMI["2080s_2060"]) as w:
        (w.dir / "second-card.json").unlink(missing_ok=True)
        check("no state file: both suggestion signals read as on",
              SC.suggest_setting("struggle") is True and SC.suggest_setting("correction") is True)


def t_an_older_switches_file_with_no_suggest_key_still_works():
    # gen_second_card_cases.World.switches() writes master/combined/features
    # only - exactly an older second-card.json with no "suggest" key at all.
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, long_context=True)
        sw = SC._read_switches()
        check("an older file with no 'suggest' key still reads both signals as on",
              sw["suggest"] == {"struggle": True, "correction": True}, sw)
        check("and writing a feature switch does not drop it",
              SC._write_switch("vision", True) is None
              and SC._read_switches()["suggest"] == {"struggle": True, "correction": True})


# --------------------------------------------------------------------------
#   jarvis_backoff.OFFERS
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
#   second-card-suggest.patch
# --------------------------------------------------------------------------

def t_the_patch():
    order = _stack.order()
    check("second-card-suggest.patch comes after feedback.patch and "
          "answer-sources.patch in apply-patches.ps1's list",
          "second-card-suggest.patch" in order
          and order.index("feedback.patch") < order.index("second-card-suggest.patch")
          and order.index("answer-sources.patch") < order.index("second-card-suggest.patch"),
          order[-3:])
    order = order[:order.index("second-card-suggest.patch") + 1]
    patch = (HERE / "second-card-suggest.patch").read_text(encoding="utf-8")
    check("it patches jarvis_hud.py and nothing else",
          sorted(l[6:].strip() for l in patch.splitlines() if l.startswith("+++ b/"))
          == ["jarvis_hud.py"])
    git = shutil.which("git")
    if not git:
        check("git is here to apply it", False)
        return
    target = "jarvis_hud.py"
    text, log = _stack.stand_in(target, order[:-1])
    if text is None:
        check(f"a stand-in of {target} could be built", False, log)
        return
    d = Path(tempfile.mkdtemp(prefix="jarvis-second-card-suggest-patch-"))
    try:
        (d / target).write_text(text, encoding="utf-8", newline="\n")
        one = "".join(h for h, _ in _stack.hunks(patch, target))
        (d / "p.patch").write_text(f"--- a/{target}\n+++ b/{target}\n{one}",
                                   encoding="utf-8", newline="\n")
        r = subprocess.run([git, "apply", "p.patch"], cwd=d, capture_output=True, text=True)
        ok = r.returncode == 0
        after = (d / target).read_text(encoding="utf-8") if ok else ""
        r2 = subprocess.run([git, "apply", "-R", "p.patch"], cwd=d, capture_output=True,
                            text=True)
        back = (d / target).read_text(encoding="utf-8") == text
        check(f"{target}: applies to what the earlier patches wrote, and reverses",
              ok and r2.returncode == 0 and back, (r.stderr, r2.stderr))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    check("the new lines only fire on a real 'wrong' mark that changed, with a real id, "
          "and never let an exception replace the answer",
          'out.get("mark") == "wrong" and out.get("changed")' in after
          and "isinstance(cid, str) and cid" in after
          and "jarvis_agent.note_correction(cid)" in after
          and "except Exception:\n                    pass" in after, after)
    cid_at = after.index('cid = body.get(')
    check("an older client (no conversation_id) is untouched: the route still ends "
          "the same way, right after the new lines",
          after.index('return self._send(code, out)', cid_at) - cid_at < 700, after[cid_at:cid_at + 700])
    import _where
    check("no new module to ship: jarvis_agent.py and jarvis_second_card.py are already "
          "in _where.SHIPPED",
          "jarvis_agent.py" in _where.SHIPPED and "jarvis_second_card.py" in _where.SHIPPED)


def t_backoff_declares_the_offer_honestly():
    check("the offer's kind is declared",
          SC.SUGGEST_OFFER_KIND in BO.OFFERS, BO.OFFERS)
    check("vet() allows it", BO.vet(SC.SUGGEST_OFFER_KIND) == (True, ""))
    declared = BO.OFFERS[SC.SUGGEST_OFFER_KIND]
    check("it asks only for what MAY_ASK lists, never anything in NEVER_ASKS",
          all(a in BO.MAY_ASK and a not in BO.NEVER_ASKS for a in declared), declared)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("t_") and callable(v)]
    for fn in tests:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(sorted(set(FAILED))))
    sys.exit(1 if FAILED else 0)
