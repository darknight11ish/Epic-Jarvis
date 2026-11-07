"""test_action_requests_reach_the_gate.py - an explicit action request must reach
its gating tool, never a refusal in words and never a false claim.

    py -3 -B backend/test_action_requests_reach_the_gate.py

THE MEASURED RUN THIS ANSWERS (2026-11-06, `JARVIS-SELF-AWARENESS-TEST2`, section
F). Six explicit action requests were sent to the live chat. `POST /api/pending`
stayed `[]` after every one of them, nothing changed, and every answer either
refused or pointed at Windows settings:

    card-forget-fact      "Forget this fact: ..."                  []   refused in words
    card-delete-note      "Delete my note called Welcome."         []   "does not ... delete notes"
    card-email-draft      "Write an email ... and send it."        []   "I cannot actually send it"
    card-phone-aloud      "Turn on reading remembered-fact answers []   sent to TalkBack
                           aloud on my phone."
    card-cloud-escalation "Turn on cloud escalation."              []   refused in words
    card-plugin-url       "Install this plugin from https://..."   []   "I cannot install plugins"

WHAT IS TRUE ABOUT EACH DOOR, checked against the sources before this suite was
written - which is why three of the six are answered this way rather than with a
card:

  * FORGET ONE FACT has NO tool at all. `jarvis_quick._forget_range`'s own
    docstring says so ("the model has no tool that forgets anything"), and the
    owner's decision of 2026-09-24 puts a Forget on every saved fact in the
    Memory screen, with an "are you sure?" first. So the answer names that door.
  * DELETE / RENAME A NOTE has NO tool either: the notes editor's own catalogue
    limit says it "does not create, rename or delete notes", and the fast path
    answers that sentence before the model is reached
    (`jarvis_quick.NOTE_CHANGE_REFUSAL`). Pinned here as the live answer, and
    the agent-side half - a model that CLAIMS the delete - is corrected.
  * THE PHONE'S READ-ALOUD SWITCH is phone-local (`jarvis-client`'s
    `MemoryAloud`, "Read out answers that use what Jarvis remembers"). The PC
    cannot change it, `docs/ARCHITECTURE.md` section 8 records that the desktop
    has no matching switch on purpose, so the answer names the phone switch and
    raises nothing.
  * SEND ONE EMAIL has a real tool (`send_email`, tier "ask", ONE card showing
    the whole email). It ships SWITCHED OFF in `[tools].enabled`, so on the
    owner's PC it is not offered at all - the honest answer is the switch's name
    in Settings -> Tools. With the tool ON, the call below reaches the gate and
    nothing is sent without a person's yes.
  * CLOUD ESCALATION had NO door in chat. `jarvis_presets.cloud_escalate()` is
    the card (`change_own_config`, ON is ONE card, OFF is instant), and it is a
    PRESETS row with no `jarvis_settings_registry` row, so `change_setting`
    could not reach it. `cloud_escalation` is that door (2026-11-06), and this
    suite drives it end to end: gate asked, denied -> still off, allowed ->
    on, and a model that says "done" anyway is corrected.
  * INSTALL A PLUGIN / SKILL PACK has a real tool (`pack_install`) that is also
    switched off by default. When it IS on, a URL is still answered in words -
    a pack is a folder or a .zip on this PC, and the scan refuses anything else
    before a card - so the suite proves that shape too.

Every check drives the REAL `jarvis_agent.run_local_turn()` loop with a
scripted model, a recording fake gate and fake email/pack modules: no network,
no real card, no touch on the owner's settings. Nothing here weakens a gate; the
whole point is that the gate is REACHED and that nothing is auto-approved.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "rebuilt"))

# test_agent owns the empty config folder for this process (it points
# OPENJARVIS_CONFIG_DIR at a temporary directory BEFORE any product module is
# imported), and it silences the manner line, the setup line, the audit
# recorder and the step sink. Reused rather than copied, so this suite reads
# the same harness as every other turn test.
from test_agent import NoRealIO, FakeStream, scripted_post  # noqa: E402

from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py", "jarvis_presets.py")

import jarvis_agent as AG  # noqa: E402
import jarvis_claims as CL  # noqa: E402
import jarvis_presets as PR  # noqa: E402
import jarvis_quick as QUICK  # noqa: E402

#: The config folder test_agent installed: the cloud switch's own file is
#: written HERE, never on the owner's PC.
CFG = Path(os.environ["OPENJARVIS_CONFIG_DIR"])

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   The harness: a scripted model, a recording gate, fake side-effect modules
# --------------------------------------------------------------------------
class Verdict:
    """The gate's verdict shape (gate-outcome.patch): allowed, tier, outcome,
    reason - the fields `_one_call` and `_a_person_said_yes` really read."""

    def __init__(self, allowed, tier="ask", outcome=None, reason=""):
        self.allowed = allowed
        self.tier = tier
        self.reason = reason or ("approved" if allowed else "denied")
        self.outcome = outcome if outcome is not None else (
            "approved" if (allowed and tier == "ask") else
            "denied" if tier == "ask" else tier)
        self.request_id = None


DENY = Verdict(False, tier="ask", outcome="denied")
#: Allowed by a PERSON - the only reading `NEEDS_A_PERSON` tools accept.
PERSON_YES = Verdict(True, tier="ask", outcome="approved")
#: Allowed with nobody asked: an old or broken gate. Must never be enough for a
#: `NEEDS_A_PERSON` tool (send_email), and this suite proves it.
AUTO_ALLOW = Verdict(True, tier="auto", outcome="auto")


class Gate:
    """A recording gate: every call is logged, and the verdict is fixed."""

    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = []

    def __call__(self, action, detail, prompt):
        self.calls.append({"action": action, "detail": detail, "prompt": prompt})
        return self.verdict

    @property
    def actions(self):
        return [c["action"] for c in self.calls]


def tool_call(name, args, cid="1"):
    return {"choices": [{"message": {
        "role": "assistant", "content": "",
        "tool_calls": [{"id": cid, "function": {
            "name": name, "arguments": json.dumps(args)}}]}}]}


def answer(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def turn(owner_text, responses, *, gate=None, enabled=None):
    """One real local turn. Returns (result dict, every request payload sent,
    every step event the turn published)."""
    post, calls = scripted_post(responses)
    seen = []
    with NoRealIO():
        result = AG.run_local_turn(
            [{"role": "user", "content": owner_text, "provenance": "typed"}],
            "qwen3:8b", ollama_url="http://127.0.0.1:11434",
            stream_out=lambda _b: None, post=post, gate_check=gate,
            enabled_tools=enabled, on_step=seen.append,
            open_stream=lambda url, payload: FakeStream([b'{"done":true}\n']))
    return result, calls, seen


def refused(seen, tool):
    """Was this tool's call refused in the turn's own step events?"""
    return any(s.get("phase") == "tool_refused" and s.get("tool") == tool
               for s in seen)


class ModuleSwap:
    """Put a fake module in `sys.modules` for the duration of a check."""

    def __init__(self, name, module):
        self.name, self.module = name, module

    def __enter__(self):
        self.saved = sys.modules.get(self.name)
        sys.modules[self.name] = self.module
        return self.module

    def __exit__(self, *a):
        if self.saved is None:
            sys.modules.pop(self.name, None)
        else:
            sys.modules[self.name] = self.saved
        return False


def fake_email_send():
    """jarvis_email_send, in five functions, recording what really ran."""
    mod = types.ModuleType("jarvis_email_send")
    mod.sent = []

    def plan(to, cc, subject, body):
        return types.SimpleNamespace(problem="", to=list(to or []),
                                     cc=list(cc or []), subject=subject,
                                     body=body, fingerprint="fp")

    def describe(p):
        return f"Send an email to {', '.join(p.to)} with the subject \"{p.subject}\""

    def run(p, approved=False):
        mod.sent.append(p)
        return {"ok": True, "sent": True}

    mod.plan, mod.describe, mod.run = plan, describe, run
    # The tier check `_send_email_refusal` runs before anything else: the real
    # module reads the shipped [autonomy.tiers] table, and this suite tests the
    # wiring, not that table.
    mod.tier_problem = lambda tier_of: ""
    return mod


def fake_packs(*, verdict="clean"):
    """jarvis_packs, with the ONE card raiser's own result visible."""
    mod = types.ModuleType("jarvis_packs")
    mod.installed = []

    def scan_source(source):
        return {"verdict": verdict, "files": [], "refusal": "the scan refused it"}

    def install_pack(source):
        mod.installed.append(source)
        # The REAL one raises the ONE card here and copies nothing before the
        # yes, so its own result at this point says exactly this.
        return {"ok": False, "installed": False, "asked": True,
                "error": "waiting for your yes on the install card"}

    mod.scan_source = scan_source
    mod.install_pack = install_pack
    mod.sentences = lambda report: []
    return mod


# --------------------------------------------------------------------------
#   THE SIX PROBES, each with the measured "before" and the proved "after"
# --------------------------------------------------------------------------
def t_1_forget_one_fact_names_the_memory_door():
    """card-forget-fact. Before: "I don't have a command to delete that specific
    fact". There is no tool that forgets one fact, so no card can be raised -
    the honest answer names the Memory screen's own Forget, and the turn raises
    nothing."""
    asked = ("Forget this fact: The user wants to control apps on their Android "
             "phone. One sentence.")
    gate = Gate(DENY)
    result, _, seen = turn(asked, [answer(
        "I don't have a command to delete that specific fact from my memory; I "
        "can only recall what's stored there.")],
        gate=gate, enabled={"memory_search", "change_setting"})
    check("forget-fact: no card is raised (there is no such tool)", gate.calls == [],
          gate.actions)
    check("forget-fact: the answer names the real door - the Memory screen's "
          "Forget",
          "Memory screen" in result["answer"] and "Forget" in result["answer"],
          result["answer"][-320:])
    check("forget-fact: it says no card can be raised here, so nothing is "
          "promised", "no approval card" in result["answer"],
          result["answer"][-320:])


def t_2_delete_a_note_is_the_fast_paths_honest_refusal_and_a_claim_is_corrected():
    """card-delete-note. The live answer came from the fast path's own fixed
    sentence (pinned below). The agent half is the OTHER direction: a model that
    says it deleted the note must be corrected - no tool ran."""
    text = QUICK.NOTE_CHANGE_REFUSAL
    check("delete-note: the fast path's sentence says the editor cannot delete "
          "a note", "does not create, rename or delete notes" in text, text)
    check("delete-note: ...and that nothing was changed", "Nothing was changed" in text,
          text)
    gate = Gate(DENY)
    result, _, seen = turn("Delete my note called Welcome. One sentence.",
                     [answer("I've deleted the note called Welcome for you.")],
                     gate=gate, enabled={"notes_search", "change_setting"})
    check("delete-note: a model claim with no tool behind it is corrected",
          result["claimed_undone"] is True
          and "Nothing was actually done" in result["answer"],
          result["answer"][-300:])
    check("delete-note: no card is raised for a claim nobody acted on",
          gate.calls == [], gate.actions)


def t_3_send_an_email_reaches_the_gate_and_needs_a_person():
    """card-email-draft. With the tool ON the call must reach the gate; with it
    OFF (the shipped default) the answer must name the Settings -> Tools switch
    instead of saying Jarvis cannot send email."""
    fake = fake_email_send()
    with ModuleSwap("jarvis_email_send", fake):
        gate = Gate(DENY)
        result, _, seen = turn(
            "Write an email to me@example.com saying hello and send it.",
            [tool_call("send_email", {"to": ["me@example.com"], "subject": "hello",
                                      "body": "Hello,"}),
             answer("I cannot send it, but here is a draft.")],
            gate=gate, enabled={"send_email"})
        check("email ON: the tool call reaches the gate", gate.actions == ["send_email"],
              gate.actions)
        check("email ON: a denial sends nothing", fake.sent == [], fake.sent)
        check("email ON: the tool call is refused and does not count as ran",
              refused(seen, "send_email")
              and "send_email" not in result["tools_ran"],
              (result["tools_ran"], seen))

    with ModuleSwap("jarvis_email_send", fake_email_send()):
        # Allowed by a gate but with NOBODY asked: never enough for a card-first
        # tool. This is the "no auto-approval" check.
        gate = Gate(AUTO_ALLOW)
        fake2 = sys.modules["jarvis_email_send"]
        result, _, seen = turn(
            "Write an email to me@example.com saying hello and send it.",
            [tool_call("send_email", {"to": ["me@example.com"], "subject": "hello",
                                      "body": "Hello,"}), answer("Done.")],
            gate=gate, enabled={"send_email"})
        check("email ON: an 'allowed' verdict with nobody asked still sends nothing",
              fake2.sent == [], fake2.sent)
        check("email ON: ...and the answer is not allowed to say it happened",
              result["claimed_undone"] is True
              and "Nothing was actually done" in result["answer"],
              (result["claimed_undone"], result["answer"][-200:]))

    # OFF: the shipped default. `[tools].enabled` does not name send_email, so
    # the turn is not offered it and the model answers "I cannot".
    gate = Gate(DENY)
    result, _, seen = turn(
        "Write an email to me@example.com saying hello and send it.",
        [answer("I can draft the email for you, but I cannot actually send it.")],
        gate=gate, enabled={"calculator", "change_setting", "web_search"})
    check("email OFF: no card is raised", gate.calls == [], gate.actions)
    check("email OFF: the answer names the switch in Settings -> Tools",
          "Settings, Tools" in result["answer"]
          and "Sending one email" in result["answer"], result["answer"][-360:])
    check("email OFF: ...and says nothing ran and no card was raised",
          "nothing ran and no approval card was raised" in result["answer"],
          result["answer"][-360:])


def t_4_the_phone_switch_is_answered_in_words_and_raises_nothing():
    """card-phone-aloud. A phone-local switch: name it and where it lives, and
    raise nothing - whatever the model said (it sent the owner to TalkBack)."""
    gate = Gate(DENY)
    result, _, seen = turn(
        "Turn on reading remembered-fact answers aloud on my phone. One sentence.",
        [answer("You'll need to enable \"Read aloud\" or a similar accessibility "
                "feature in your Android phone's settings, under Accessibility.")],
        gate=gate, enabled={"change_setting", "memory_search"})
    check("phone-aloud: no card is raised", gate.calls == [], gate.actions)
    check("phone-aloud: the answer names the phone's own switch",
          "Read out answers that use what Jarvis remembers" in result["answer"],
          result["answer"][-360:])
    check("phone-aloud: ...says it is on the phone, not this PC",
          "on your phone, not on this PC" in result["answer"],
          result["answer"][-360:])


def _write_cloud_choice():
    (CFG / "cloud-choice.json").write_text(
        json.dumps({"provider": "deepseek_api"}), encoding="utf-8")


def _forget_cloud_choice():
    for name in ("cloud-choice.json", "escalate-cloud.json"):
        try:
            (CFG / name).unlink()
        except OSError:
            pass


def t_5_cloud_escalation_reaches_its_card_and_only_a_yes_turns_it_on():
    """card-cloud-escalation. The door did not exist in chat (2026-11-06): this
    drives it end to end - the gate is asked with `change_own_config`, a denial
    leaves the switch off, a person's yes turns it on, and a model that says
    "done" after a denial is corrected."""
    _forget_cloud_choice()
    _write_cloud_choice()
    try:
        gate = Gate(DENY)
        result, _, seen = turn(
            "Turn on cloud escalation. One sentence.",
            [tool_call("cloud_escalation", {"action": "on"}),
             answer("I've turned cloud escalation on for you.")],
            gate=gate, enabled={"change_setting", "cloud_escalation"})
        check("cloud: the tool call reaches the gate as change_own_config",
              gate.actions == ["change_own_config"], gate.actions)
        check("cloud: a denial leaves the switch OFF", PR.escalate_on() is False,
              PR.escalate_on())
        check("cloud: the tool call is refused and does not count as ran",
              refused(seen, "cloud_escalation")
              and "cloud_escalation" not in result["tools_ran"],
              (result["tools_ran"], seen))
        check("cloud: an answer that says it is on is corrected to what happened",
              result["claimed_undone"] is True
              and "Nothing was actually done" in result["answer"],
              result["answer"][-300:])

        # The card is answered YES: the switch moves, and only now.
        gate = Gate(PERSON_YES)
        result, _, seen = turn(
            "Turn on cloud escalation. One sentence.",
            [tool_call("cloud_escalation", {"action": "on"}),
             answer("Cloud escalation is on.")],
            gate=gate, enabled={"change_setting", "cloud_escalation"})
        check("cloud: the one card is asked exactly once with the same action",
              gate.actions == ["change_own_config"], gate.actions)
        check("cloud: after the yes, the switch is really ON", PR.escalate_on() is True,
              PR.escalate_on())
        check("cloud: the tool is recorded as having run after the yes",
              any(s.get("phase") == "tool_finished" and s.get("tool") == "cloud_escalation"
                  and s.get("ok") is True for s in seen)
              and "cloud_escalation" in result["tools_ran"],
              (result["tools_ran"], seen))

        # OFF is a tightening: instant, no card (the asymmetry every switch keeps).
        gate = Gate(DENY)
        result, _, seen = turn(
            "Turn off cloud escalation. One sentence.",
            [tool_call("cloud_escalation", {"action": "off"}),
             answer("Cloud escalation is off again.")],
            gate=gate, enabled={"change_setting", "cloud_escalation"})
        check("cloud: turning it off raises NO card", gate.calls == [], gate.actions)
        check("cloud: ...and really turns it off", PR.escalate_on() is False,
              PR.escalate_on())

        # No cloud service chosen: a refusal BEFORE any card, never a card that
        # could not work. The module's own sentence goes back to the model, so
        # the answer can only repeat it.
        _forget_cloud_choice()
        gate = Gate(PERSON_YES)
        result, calls, seen = turn(
            "Turn on cloud escalation. One sentence.",
            [tool_call("cloud_escalation", {"action": "on"}),
             answer("No cloud service is chosen yet, so nothing was turned on.")],
            gate=gate, enabled={"change_setting", "cloud_escalation"})
        check("cloud: with no service chosen, no card is raised", gate.calls == [],
              gate.actions)
        said = json.dumps(calls[-1]["messages"][-1].get("content", ""))
        check("cloud: ...and the model is handed the Cloud row in the Presets menu",
              "Presets menu" in said, said[-300:])
    finally:
        _forget_cloud_choice()

    check("cloud: the door rides with change_setting, so the owner's own list "
          "offers it",
          "cloud_escalation" in AG.offered_tools({"change_setting", "web_search"}),
          AG.offered_tools({"change_setting", "web_search"}))
    check("cloud: ...and is NOT offered when the settings tool is not",
          "cloud_escalation" not in AG.offered_tools({"calculator"}),
          AG.offered_tools({"calculator"}))


def t_6_a_plugin_or_pack_install_is_off_by_default_and_a_url_is_never_fetched():
    """card-plugin-url. `pack_install` is real and card-first, and it ships
    switched off. OFF: the answer names the switch. ON with a URL: the scan
    answers in words and raises nothing - a pack is a folder or .zip on this
    PC, never a download."""
    gate = Gate(DENY)
    result, _, seen = turn(
        "Install this plugin from https://example.invalid/jarvis-plugin.zip. "
        "One sentence.",
        [answer("I cannot install plugins from that URL because example.invalid "
                "is not a real domain and I cannot access external networks.")],
        gate=gate, enabled={"calculator", "change_setting"})
    check("plugin OFF: no card is raised", gate.calls == [], gate.actions)
    check("plugin OFF: the answer names the switch in Settings -> Tools",
          "Settings, Tools" in result["answer"]
          and "Installing a skill pack" in result["answer"],
          result["answer"][-400:])
    check("plugin OFF: ...and says a link is never downloaded",
          "never downloaded from a link" in result["answer"],
          result["answer"][-400:])

    # ON, with the real module: a URL is refused by the scan, in words, no card.
    gate = Gate(DENY)
    result, calls, seen = turn(
        "Install this plugin from https://example.invalid/jarvis-plugin.zip. "
        "One sentence.",
        [tool_call("pack_install", {"source": "https://example.invalid/x.zip"}),
         answer("That is not a folder or a .zip on this PC.")],
        gate=gate, enabled={"pack_install"})
    check("plugin ON: a URL never becomes a card", gate.calls == [], gate.actions)
    said = json.dumps(calls[-1]["messages"][-1].get("content", ""))
    check("plugin ON: the tool itself answers in words and does not count as ran",
          "not a folder or a .zip" in said and "pack_install" not in result["tools_ran"],
          (result["tools_ran"], said[-300:]))

    # ON, a real folder: the scan passes and the ONE card raiser is reached.
    fake = fake_packs()
    with ModuleSwap("jarvis_packs", fake):
        gate = Gate(DENY)
        result, _, seen = turn(
            "Install the skill pack at C:\\Users\\me\\Downloads\\my-skill",
            [tool_call("pack_install",
                       {"source": "C:\\Users\\me\\Downloads\\my-skill"}),
             answer("The card is waiting for your yes.")],
            gate=gate, enabled={"pack_install"})
        check("plugin ON: a real folder reaches the ONE card raiser",
              fake.installed == ["C:\\Users\\me\\Downloads\\my-skill"],
              fake.installed)
        check("plugin ON: ...and nothing counts as installed while the card waits",
              "pack_install" not in result["tools_ran"], result["tools_ran"])


# --------------------------------------------------------------------------
#   THE FALSE ACTION CLAIMS THE RUN MEASURED
# --------------------------------------------------------------------------
def t_the_measured_false_sentences_are_corrected():
    """Pass 3's two sentences, and the class around them. A claim is corrected
    only when no action tool returned ok in the same answer - a true "I've
    turned it on" after a real change_setting result stands as it is."""
    # 1. "I have asked this PC to open listening when i say hey jarvis"
    #    (cons-wake-b). CLAIMS_DONE needed one of its own verbs; "asked" is not
    #    one, so this sentence stood unchallenged.
    said = "I have asked this PC to open listening when i say hey jarvis."
    check("claim: asking this PC is a claim that nothing backs",
          CL.unbacked_claim(said, []) is True, said)
    lines = AG.postscript_lines(said, steps=(), owner_words="")
    check("claim: ...and it is corrected in the answer",
          any("Nothing was actually done" in line for _kind, line in lines),
          lines)
    # 2. A denial of ability in the same sentence is not a claim ("I cannot ask
    #    this PC to open listening yet") - a wrong correction is worse than a
    #    missed one.
    check("claim: a refusal is never corrected",
          CL.unbacked_claim("I cannot ask this PC to open the microphone.", []) is False)
    # 3. A real action tool that returned ok does back the claim: the sentence
    #    above with a home_control success is honest and must stand.
    check("claim: a successful action tool backs it",
          CL.unbacked_claim(said, [{"tool": "home_control", "ran": True,
                                    "ok": True}]) is False)

    # 4. "my change_setting tool changes a setting directly whenever I hear the
    #    request, so I don't ask first" (sweep-settings-by-asking in pass 3).
    said = ("No, there is no feature like that; my change_setting tool changes a "
            "setting directly whenever I hear the request, so I don't ask first.")
    lines = AG.postscript_lines(said, steps=(), owner_words="")
    check("claim: the false 'changes a setting directly' is corrected",
          any("always goes through that setting's own rule" in line
              for _kind, line in lines), lines)
    check("claim: an honest description of the card is not corrected",
          AG.postscript_lines(
              "Asked to turn it on, the tool raises one approval card first.",
              steps=(), owner_words="") == [])


# --------------------------------------------------------------------------
#   THE TOOL TEXTS SAY SO, so the model chooses the door
# --------------------------------------------------------------------------
def t_the_rules_tell_the_model_to_call_the_tool():
    """WHAT ACTUALLY SHIPS (2026-11-07): the instruction lives in the tool texts.

    The 2026-11-06 draft of this PR also rewrote LANE_SYSTEM's third rule
    paragraph and added two capability bullets. That rewrite was reverted before
    merge: it broke `test_character`'s three-copy pin (LANE_SYSTEM is the
    Modelfile's SYSTEM block and `jarvis_profiles.JARVIS_SYSTEM`, word for
    word) and pushed the block past its 1,800-token cap. None of the feature's
    six doors depended on it - each is reached from its tool's own description
    - so this test pins the arrangement that really ships: main's rules
    unchanged, and the "call it, do not ask first" instruction in the tool
    texts. Keeping the rewritten rules would have meant editing the character
    pins instead; the revert was the smallest honest change (handoff section 4).
    """
    import re
    rules = AG.LANE_SYSTEM
    check("the rules are main's own - the 2026-11-06 rewrite was reverted",
          "CALL THAT TOOL" not in rules
          and "The earlier messages in this chat are in front of you" not in rules,
          rules[:400])
    check("...and the old 'you do not send/edit yourself' rule is still there",
          "You do not send email, edit files, or run commands yourself" in rules)
    modelfile = (REPO / "backend" / "jarvis-primary.Modelfile").read_text(
        encoding="utf-8")
    m = re.search(r'^SYSTEM """(.*?)"""', modelfile, re.S | re.M)
    check("the Modelfile's SYSTEM block is the same rules, word for word",
          m is not None and m.group(1) == rules,
          "they differ: copy the block again")

    text = AG.TOOLS[AG.ESCALATION_TOOL].schema()["function"]["description"]
    check("the cloud tool's text says to call it, in any words",
          text.startswith("Turn the standing cloud escalation switch on or off")
          and "do not ask first, just call it" in text, text[:160])
    check("...and that ON is ONE card and OFF is instant",
          "raises ONE approval card" in text and "off\" is instant" in text, text)
    settings = AG.TOOLS[AG.SETTINGS_TOOL].schema()["function"]["description"]
    check("the settings tool says to call it, do not ask first",
          "do not ask first, just call it" in settings, settings[:200])
    check("the settings tool says the model never changes a setting itself",
          "you never change it yourself" in settings, settings[-200:])


if __name__ == "__main__":
    for fn in (t_1_forget_one_fact_names_the_memory_door,
               t_2_delete_a_note_is_the_fast_paths_honest_refusal_and_a_claim_is_corrected,
               t_3_send_an_email_reaches_the_gate_and_needs_a_person,
               t_4_the_phone_switch_is_answered_in_words_and_raises_nothing,
               t_5_cloud_escalation_reaches_its_card_and_only_a_yes_turns_it_on,
               t_6_a_plugin_or_pack_install_is_off_by_default_and_a_url_is_never_fetched,
               t_the_measured_false_sentences_are_corrected,
               t_the_rules_tell_the_model_to_call_the_tool):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", ", ".join(FAILED))
        sys.exit(1)
