"""test_cloud_escalate_setting.py - the "escalate to the cloud when the work is
too complex" switch: ONE card to turn it on, instant to turn it off, and the
PC - never a client - decides (the owner's decision, 2026-10-27).

    python3 backend/test_cloud_escalate_setting.py

WHY THIS SUITE EXISTS, IN ONE PARAGRAPH

`jarvis_router.choose()` said, in its own words, that cloud use is "per use,
with permission ... and asks. **No standing grant.**" (2026-09-24). The owner
changed that rule on 2026-10-27 and asked for a checkbox. A standing yes is the
one loosening this feature adds, so every part of it has to be proved rather
than described:

  1. the switch READS as off from an absent file, a corrupt file, a wrong-shaped
     file, and a missing `jarvis_presets.py` - a privacy switch fails closed;
  2. turning it ON raises ONE `change_own_config` card, and a refused card
     writes NOTHING; turning it OFF is instant and asks nothing;
  3. ON with no cloud provider chosen refuses before a card, because a standing
     yes to a service nobody picked cannot do anything;
  4. the STANDING GRANT comes from THIS PC's file and from nowhere else - no
     request body, no header, no client flag is consulted for it;
  5. the HUD page's own `cloud_yes` counts only while that file says on
     (cloud-escalate.patch's first hunk), so a stale page cannot turn a switch
     that has been turned off into a yes for one question;
  6. the in-chat phrase ("escalate this", "send this to the cloud") is a yes for
     THAT TURN ONLY - nothing is stored - and it can only ever move gate 6,
     after every privacy gate has already had its chance to answer local;
  7. an AUTOMATIC turn - standing switch or phrase - whose cloud reply has no
     usable answer is answered on this PC under one honest line, and the
     model's private working-out is never shown as its answer.

WHAT IS REAL AND WHAT IS INJECTED. `jarvis_router.choose()` (the shipped
`backend/rebuilt/jarvis_router.py`), `jarvis_presets`, `jarvis_chatbot_api` and
the real `CloudAnswer` reader are driven. The approval gate, the app's own
`cloud_yes` body and the local fallback are stood in by the test - this suite
must never post a card, never read the owner's key store and never call a model.
A fresh `OPENJARVIS_CONFIG_DIR` is used, so nothing on this PC is touched.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASE = REPO / "jarvis-backend"
REBUILT = HERE / "rebuilt"
PATCH = HERE / "cloud-escalate.patch"

#: A scratch home BEFORE anything reads a settings file.
SCRATCH = Path(tempfile.mkdtemp(prefix="jarvis-cloud-escalate-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_SUITE_RUNNING"] = "1"
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""
os.environ.setdefault("JARVIS_APPROVAL_TIMEOUT", "2.0")

sys.dont_write_bytecode = True
sys.path.insert(0, str(REBUILT))
sys.path.insert(0, str(HERE))

import jarvis_chatbot_api as API  # noqa: E402
import jarvis_presets as P  # noqa: E402
import jarvis_router as RT  # noqa: E402

FAILED, PASSED = [], []
LOCAL = "qwen3.5:9b"
#: Long and clause-heavy: the complexity gate alone lets it out, so a refusal
#: below can only come from the gate named in that check.
HARD = ("Explain in detail how the three-body problem differs from the two-body "
        "problem, and why the difference matters for predicting orbits.")
PRIVATE = "What is my password for the bank?"
REVIEW = "Review this: explain, step by step, the trade-offs in the design."


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class _Verdict:
    def __init__(self, allowed: bool, outcome: str = "") -> None:
        self.allowed = bool(allowed)
        self.outcome = outcome or ("approved" if allowed else "denied")
        self.reason = ""


def gate_yes(action, detail, prompt=""):
    gate_yes.seen.append((action, dict(detail or {}), prompt))
    return _Verdict(True)


def gate_no(action, detail, prompt=""):
    gate_no.seen.append((action, dict(detail or {}), prompt))
    return _Verdict(False, "denied")


gate_yes.seen = []
gate_no.seen = []


def _paths():
    return (SCRATCH / P.CLOUD_ESCALATE_FILE, SCRATCH / P.CLOUD_CHOICE_FILE,
            SCRATCH / P.CHOICE_FILE)


def clean(*, provider="deepseek_api"):
    """A fresh scratch home, and (by default) a cloud provider already chosen."""
    for child in SCRATCH.iterdir():
        if child.is_file():
            child.unlink()
        else:
            shutil.rmtree(child, ignore_errors=True)
    API._reset_models_for_tests()
    if provider:
        (SCRATCH / P.CLOUD_CHOICE_FILE).write_text(
            json.dumps({"provider": provider}) + "\n", encoding="utf-8")


def _escalate_file() -> Path:
    return SCRATCH / P.CLOUD_ESCALATE_FILE


# ==========================================================================
#  1. the switch reads as OFF unless the file plainly says ON
# ==========================================================================

def t_the_switch_fails_closed():
    clean()
    check("absent file: off", P.escalate_on() is False)
    check("... and the sentence says it was never turned on",
          P.escalate_why() == "not turned on for this PC", P.escalate_why())
    (_escalate_file()).write_text("{not json", encoding="utf-8")
    check("corrupt file: off (a switch that cannot be read is not a yes)",
          P.escalate_on() is False)
    check("... and the sentence says the setting cannot be read",
          "cannot be read" in P.escalate_why(), P.escalate_why())
    (_escalate_file()).write_text(json.dumps({"on": "true"}) + "\n", encoding="utf-8")
    check("a name that looks like true but is not the boolean: still off",
          P.escalate_on() is False)
    (_escalate_file()).write_text(json.dumps([1, 2]) + "\n", encoding="utf-8")
    check("a list where an object belongs: off", P.escalate_on() is False)
    (_escalate_file()).write_text(json.dumps({"on": True}) + "\n", encoding="utf-8")
    check("the boolean true, and only that, is on", P.escalate_on() is True)
    check("... and `why` is empty once it is on", P.escalate_why() == "", P.escalate_why())


# ==========================================================================
#  2. one card to turn it on, instant to turn it off
# ==========================================================================

def t_on_is_one_card_and_off_is_instant():
    clean()
    gate_yes.seen.clear()
    code, out = P.cloud_escalate(on=True, gate_check=gate_yes)
    check("ON raises exactly ONE card, as change_own_config",
          len(gate_yes.seen) == 1 and gate_yes.seen[0][0] == P.CLOUD_ACTION,
          gate_yes.seen)
    words = gate_yes.seen[0][1]["text"]
    check("... whose text says it may send a hard question without asking first",
          "without asking you first" in words, words)
    check("... and says what STILL never leaves this PC, and that the money limit "
          "still applies",
          "private" in words and "picture" in words and "screen" in words
          and "money limit" in words, words)
    check("... and names the provider it is about", "DeepSeek" in words, words)
    check("a yes writes the switch and says so",
          code == 200 and out["ok"] is True and out["changed"] is True
          and out["on"] is True and P.escalate_on() is True, (code, out))
    check("... and `card` is True, so an app can say what it waited for", out["card"] is True)

    # Already on: no second card.
    gate_yes.seen.clear()
    code, out = P.cloud_escalate(on=True, gate_check=gate_yes)
    check("asking for ON when it is already on raises no card at all",
          gate_yes.seen == [] and out["changed"] is False and out["card"] is False,
          (gate_yes.seen, out))

    # OFF: instant, and the gate is never consulted.
    gate_no.seen.clear()
    code, out = P.cloud_escalate(on=False, gate_check=gate_no)
    check("OFF is INSTANT - no card, nothing asked",
          gate_no.seen == [] and code == 200 and out["ok"] is True
          and out["changed"] is True and out["card"] is False, (code, out))
    check("... and it is really off afterwards", P.escalate_on() is False)


def t_a_refused_card_writes_nothing():
    clean()
    code, out = P.cloud_escalate(on=True, gate_check=gate_no)
    check("a NO leaves it off: 200, ok false, changed false, card true",
          code == 200 and out["ok"] is False and out["changed"] is False
          and out["card"] is True and out["on"] is False, (code, out))
    check("... nothing was written at all", not _escalate_file().exists(),
          sorted(p.name for p in SCRATCH.iterdir()))
    check("... and it still reads as off", P.escalate_on() is False)


def t_on_with_no_provider_refuses_before_a_card():
    clean(provider="")
    gate_yes.seen.clear()
    code, out = P.cloud_escalate(on=True, gate_check=gate_yes)
    check("ON with no cloud provider chosen: 409, and a sentence saying to pick one "
          "first",
          code == 409 and out["changed"] is False and "Presets menu" in out["error"],
          (code, out))
    check("... and NO card was raised for a setting that could not work",
          gate_yes.seen == [], gate_yes.seen)


def t_the_route_body_is_checked_before_it_is_acted_on():
    clean()
    real_gate = P._gate
    P._gate = gate_yes
    try:
        code, out = P.escalate_from_body({"on": True})
        check('POST {"on": true} turns it on through the route\'s own entry point',
              code == 200 and out.get("changed") is True and P.escalate_on() is True,
              (code, out))
        code, out = P.escalate_from_body({"on": False})
        check('POST {"on": false} turns it off, with no card at all',
              code == 200 and out.get("changed") is True and P.escalate_on() is False,
              (code, out))
    finally:
        P._gate = real_gate
    code, out = P.escalate_from_body({})
    check('a body with no "on" is a 400 rather than a guess', code == 400, (code, out))
    code, out = P.escalate_from_body({"on": "yes"})
    check("a non-boolean `on` is a 400 - no truthiness shortcut on a privacy switch",
          code == 400, (code, out))
    code, out = P.escalate_from_body(["on"])
    check("a body that is not an object is a 400", code == 400, (code, out))


# ==========================================================================
#  3. who may say yes: the PC's file, the phrase, or the per-question click
# ==========================================================================

def _choose(query, *, owner_said_yes=False, lanes=None, tainted=False,
            has_image=False, has_screen=False, local=LOCAL):
    """`choose()` driven the way the HUD route drives it.

    The lane list is `jarvis_presets.cloud_lanes()` - the SAME call
    `_lane_names()` makes on the owner's PC after cloud-escalate.patch - so the
    chain is real end to end: a provider chosen is one lane, no provider chosen
    is NO lane at all, which `choose()` answers as gate "unavailable".
    """
    got = P.cloud_lanes() if lanes is None else list(lanes)
    return RT.choose(query, local_model=local, lanes=got,
                     has_image=has_image, conversation_tainted=tainted,
                     budget=RT.Budget(path=None), owner_said_yes=owner_said_yes,
                     has_screen=has_screen)


def t_the_standing_switch_is_the_only_source_of_a_standing_yes():
    clean()
    d = _choose(HARD)
    check("switch off, no click: the cloud is offered, never taken",
          d.gate == "offer" and d.lane == LOCAL and d.offer == RT.CLOUD_LANE
          and d.auto is False, d.as_dict())
    (_escalate_file()).write_text(json.dumps({"on": True}) + "\n", encoding="utf-8")
    d = _choose(HARD)
    check("switch ON: the turn escalates with NO click",
          d.gate == "escalate" and d.lane == RT.CLOUD_LANE, d.as_dict())
    check("... and the decision says it was automatic, so a blank cloud answer is "
          "never dressed up as one", d.auto is True, d.as_dict())
    check("... and the reason names the switch, not the owner's click",
          "Presets menu" in d.reason and "said yes for this question" not in d.reason,
          d.reason)
    # A click for THIS question is the owner's own yes, and is not "automatic".
    d = _choose(HARD, owner_said_yes=True)
    check("switch ON and the owner ALSO clicked: it is still his click that is named",
          d.gate == "escalate" and d.auto is False
          and "said yes for this question" in d.reason, d.as_dict())


def t_no_client_flag_can_turn_the_switch_on():
    """The standing switch is a FILE. `owner_said_yes` is the per-question click
    and nothing else - it cannot make a standing grant, and it is not consulted
    for one. (cloud-escalate.patch's first hunk is what bounds the HUD page's
    own flag; that half is proved by t_the_patch_bounds_the_hud_flag below.)"""
    clean()
    check("the module reads the file, and has no other input at all",
          "escalate_on" in Path(P.__file__).read_text(encoding="utf-8")
          and P.escalate_on() is False)
    d = _choose(HARD, owner_said_yes=False)
    check("a request with no yes and the switch off stays here",
          d.gate == "offer" and d.auto is False, d.as_dict())


def t_the_phrase_is_a_yes_for_that_turn_only():
    clean()
    check("the phrase list is fixed and narrow, and names the cloud or the escalation",
          isinstance(RT.ESCALATE_PHRASES, tuple) and 3 <= len(RT.ESCALATE_PHRASES) <= 12
          and any("escalate" in p for p in RT.ESCALATE_PHRASES)
          and any("cloud" in p for p in RT.ESCALATE_PHRASES), RT.ESCALATE_PHRASES)
    for phrase in ("escalate this", "send this to the cloud", "ask the cloud",
                   "use the bigger model for this"):
        d = _choose(f"{HARD} {phrase}")
        check(f'"{phrase}" escalates with no click and no stored setting',
              d.gate == "escalate" and d.auto is True and P.escalate_on() is False,
              d.as_dict())
    d = _choose(HARD)
    check("... and the NEXT turn does not remember it",
          d.gate == "offer" and d.auto is False, d.as_dict())
    d = _choose("Hello there.")
    check("an ordinary short message is not a phrase match and nothing escalates",
          d.gate == "complexity" and d.auto is False, d.as_dict())


def t_the_phrase_can_never_lift_a_privacy_gate():
    """Every gate still runs FIRST, in the same order, with the phrase present
    and the standing switch on. Each of these must answer local, and name the
    gate that said so."""
    clean()
    (_escalate_file()).write_text(json.dumps({"on": True}) + "\n", encoding="utf-8")
    asked = f"{HARD} escalate this"
    cases = [
        ("private words", dict(query=PRIVATE + " escalate this"), "private"),
        ("a tainted conversation", dict(query=asked, tainted=True), "taint"),
        ("a picture", dict(query=asked, has_image=True), "image"),
        ("words read off the screen", dict(query=asked, has_screen=True), "screen"),
    ]
    for name, kwargs, gate in cases:
        d = _choose(**kwargs)
        check(f"{name}: still local, on gate {gate!r}, even with the switch on and "
              f"the phrase present",
              d.gate == gate and d.lane == LOCAL and d.offer == "", d.as_dict())
    # A pasted secret is gate 3, after private words and before complexity.
    d = _choose(asked + "\nsk-live-0123456789abcdef0123456789abcdef")
    check("a pasted secret: still local, on gate 'secret'",
          d.gate == "secret" and d.lane == LOCAL, d.as_dict())
    # The short-circuit: a question that is not complex enough never gets there.
    d = _choose("hi escalate this")
    check("under the complexity threshold: still local, on gate 'complexity'",
          d.gate == "complexity" and d.auto is False, d.as_dict())
    # And with no lane offered at all (no provider chosen) the switch does nothing.
    clean(provider="")
    d = _choose(HARD)
    check("no cloud provider chosen: gate 'unavailable', whatever the switch says",
          d.gate == "unavailable" and d.lane == LOCAL, d.as_dict())


def t_the_lane_list_is_normalised_to_the_one_lane():
    check("an old config that still lists three lanes is ONE lane to choose()",
          RT.cloud_lanes(["jarvis-escalate", "jarvis-critic", "jarvis-bulk"])
          == ["jarvis-escalate"])
    check("a list with only the dead names is NO lane at all",
          RT.cloud_lanes(["jarvis-critic", "jarvis-bulk"]) == [])
    check("an unknown name is never substituted for the cloud",
          RT.cloud_lanes(["jarvis-cloud"]) == [] and RT.cloud_lanes([]) == [])
    check("... and the one lane that is kept is the module's own constant",
          RT.CLOUD_LANE == "jarvis-escalate" == P.CLOUD_LANE
          and "jarvis-escalate" in API.CLOUD_LANES, RT.CLOUD_LANE)


# ==========================================================================
#  4. the patch: the HUD half, proved the way this repository proves one
# ==========================================================================

def t_the_patch_bounds_the_hud_flag():
    """The page's `cloud_yes` is honoured only while THIS PC's file says on.

    The owner's HUD file is not in this repository, so the expression is read
    out of `backend/cloud-escalate.patch` (the same evidence
    `test_cloud_lane_taint.py` uses for cloud-say-yes.patch) and then the SAME
    expression is evaluated here against both states of the file. That is not
    a proof about the owner's file - nothing in a clone can be - it is a proof
    that the rule the patch installs behaves as the decision says.
    """
    text = PATCH.read_text(encoding="utf-8")
    check("the patch exists and changes jarvis_hud.py",
          PATCH.is_file() and "+++ b/jarvis_hud.py" in text)
    added = [ln[1:].strip() for ln in text.splitlines() if ln.startswith("+")
             and not ln.startswith("+++")]
    joined = "\n".join(added)
    check("it passes the HUD's cloud_yes through the PC's own escalation setting",
          "escalate_on()" in joined and 'X-Jarvis-Client' in joined.lower().replace(
              "x-jarvis-client", "X-Jarvis-Client"), joined[:400])
    check("... and it reads the setting from jarvis_presets, not from the body",
          'jarvis_presets' in joined, joined[:400])
    check("it tells the cloud reader when a turn was escalated with no click",
          "auto=" in joined and "answer_here" in joined, joined[:400])
    check("it stops reading litellm-proxy.yaml for the lane list",
          "litellm" in text and "cloud_lanes()" in joined
          and "model_name" not in joined, joined[-400:])


def t_the_patch_applies_and_reverses_on_the_published_base():
    """`git apply` -> the file parses -> `git apply --reverse` -> byte for byte.

    `jarvis-backend/jarvis_hud.py` is the published base: the owner's file at
    the moment it was taken, which is the state the patch's context has to
    match. apply-patches.ps1 is the only thing that proves the same on a live
    install; this is the check a clone can make, and it is the one
    backend/_stack.py's RATCHET docstring asks for when a hunk's context is
    text only the owner's PC holds.
    """
    import subprocess
    base = BASE / "jarvis_hud.py"
    if not base.is_file():
        check("the published base jarvis_hud.py is here", False, base)
        return
    work = Path(tempfile.mkdtemp(prefix="jarvis-escalate-patch-"))
    try:
        target = work / "jarvis_hud.py"
        shutil.copyfile(base, target)
        env = dict(os.environ)
        env["GIT_CEILING_DIRECTORIES"] = str(work.parent)

        def git(*args):
            return subprocess.run(["git"] + list(args), cwd=str(work), env=env,
                                  capture_output=True, text=True, timeout=180)
        git("init", "-q")
        git("config", "core.autocrlf", "false")
        git("config", "core.eol", "lf")
        before = target.read_bytes()
        applied = git("apply", str(PATCH))
        check("the patch applies to the published base", applied.returncode == 0,
              (applied.stdout + applied.stderr)[-600:])
        if applied.returncode != 0:
            return
        patched = target.read_bytes()
        check("... and it changed the file", patched != before)
        try:
            compile(patched.decode("utf-8"), "<jarvis_hud.py>", "exec")
            ok, why = True, ""
        except SyntaxError as exc:
            ok, why = False, f"{exc.msg} (line {exc.lineno})"
        check("... the patched file still compiles", ok, why)
        reversed_ = git("apply", "--reverse", str(PATCH))
        check("... and reversing it gives the base back, byte for byte",
              reversed_.returncode == 0 and target.read_bytes() == before,
              (reversed_.stdout + reversed_.stderr)[-600:])
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ==========================================================================
#  5. a cloud answer nobody asked for
# ==========================================================================

WORKING_OUT = ("The three-body problem has no closed-form solution, so one "
               "integrates numerically and the errors grow because ...")


def _stream(*, reasoning=WORKING_OUT, content="", finish="length"):
    """The measured shape of an escalated reply: all cap, no answer."""
    out = []
    if reasoning:
        out.append(b"data: " + json.dumps({"choices": [{
            "index": 0, "delta": {"reasoning_content": reasoning},
            "finish_reason": None}]}).encode() + b"\n\n")
    final = {"delta": {}}
    if content:
        final = {"delta": {"content": content}}
    out.append(b"data: " + json.dumps({"choices": [{
        "index": 0, "delta": final["delta"], "finish_reason": finish}]}).encode() + b"\n\n")
    return out


def _read(chunks, **kw):
    says = API.CloudAnswer(True, **kw)
    body = b"".join(says.feed(c) for c in chunks) + says.close()
    return says, body.decode("utf-8", "replace")


def t_an_automatic_turn_is_answered_here_and_the_working_out_is_not_shown():
    says, body = _read(_stream(), auto=True, fallback=lambda: "It is chaotic.")
    check("an automatic turn with no usable answer shows the LOCAL answer, under one "
          "honest line",
          "this PC answered it instead" in body and "It is chaotic." in body, body)
    check("... and NOT the model's private working-out",
          WORKING_OUT not in body, body)
    check("... and it is never reported as 'the working-out was shown'",
          says.used_reasoning is False and says.answered_here is True,
          (says.used_reasoning, says.answered_here))
    says, body = _read(_stream(), auto=True)
    check("with no local answer available, it says so plainly and invents nothing",
          "did not answer this one" in body and WORKING_OUT not in body, body)
    says, body = _read(_stream(), auto=True, fallback=lambda: (_ for _ in ()).throw(
        RuntimeError("the local model is down")))
    check("a local turn that RAISES is no answer, not a crash and not the working-out",
          "did not answer this one" in body and WORKING_OUT not in body, body)


def t_a_clicked_turn_keeps_the_2026_10_14_rule():
    says, body = _read(_stream(), auto=False)
    check("a turn the owner clicked for still shows the working-out, marked",
          "ran out of room before it wrote an answer" in body
          and WORKING_OUT in body, body)
    check("... and says so on the answer", says.used_reasoning is True)
    says, body = _read(_stream(reasoning="", content=""), auto=False)
    check("a clicked turn with nothing at all gets the plain 'did not send an answer'",
          "did not send an answer this time" in body, body)
    says, body = _read(_stream(reasoning="", content="A real answer.", finish="stop"),
                       auto=True, fallback=lambda: "unused")
    check("an automatic turn with a REAL answer is passed through, byte for byte",
          "A real answer." in body and "this PC answered it" not in body
          and says.answered_here is False, body)


def t_a_whole_body_reply_obeys_the_same_rule():
    raw = json.dumps({"choices": [{"index": 0, "message": {
        "content": "", "reasoning_content": WORKING_OUT}, "finish_reason": "length"}]}
    ).encode()
    says = API.CloudAnswer(False, auto=True, fallback=lambda: "It is chaotic.")
    body = (says.feed(raw) + says.close()).decode("utf-8", "replace")
    got = json.loads(body)["choices"][0]["message"]["content"]
    check("a one-shot reply (not streamed) obeys the same rule",
          "this PC answered it instead" in got and "It is chaotic." in got
          and WORKING_OUT not in got, got)
    says = API.CloudAnswer(False)
    body = (says.feed(raw) + says.close()).decode("utf-8", "replace")
    got = json.loads(body)["choices"][0]["message"]["content"]
    check("... and a clicked one-shot reply still shows the working-out, marked",
          "ran out of room" in got and WORKING_OUT in got, got)


# ==========================================================================

TESTS = [
    t_the_switch_fails_closed,
    t_on_is_one_card_and_off_is_instant,
    t_a_refused_card_writes_nothing,
    t_on_with_no_provider_refuses_before_a_card,
    t_the_route_body_is_checked_before_it_is_acted_on,
    t_the_standing_switch_is_the_only_source_of_a_standing_yes,
    t_no_client_flag_can_turn_the_switch_on,
    t_the_phrase_is_a_yes_for_that_turn_only,
    t_the_phrase_can_never_lift_a_privacy_gate,
    t_the_lane_list_is_normalised_to_the_one_lane,
    t_the_patch_bounds_the_hud_flag,
    t_the_patch_applies_and_reverses_on_the_published_base,
    t_an_automatic_turn_is_answered_here_and_the_working_out_is_not_shown,
    t_a_clicked_turn_keeps_the_2026_10_14_rule,
    t_a_whole_body_reply_obeys_the_same_rule,
]


def main() -> int:
    for fn in TESTS:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(f"{fn.__name__} raised")
            print(f"FAIL  {fn.__name__} raised")
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  failed: {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
