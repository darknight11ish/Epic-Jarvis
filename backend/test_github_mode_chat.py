#!/usr/bin/env python3
"""test_github_mode_chat.py - full GitHub mode from chat, and the ONE card it
removes: the fix loop's per-file approval, in one conversation.

    py -3 -B backend/test_github_mode_chat.py

THE OWNER'S ASK, verbatim (2026-11-25): "also add a full github mode that gives
full parity with less restrictions and less cards ... it can be enabled in chat
or settings"; "activating github mode needs a card"; "in github mode i still
want the local ai model to do as much work as possible though".

WHAT THIS SUITE PINS, each one a separate way it can regress:

  1. THE CHAT DOOR EXISTS AND RIDES WITH change_setting: one model tool,
     `github_mode`, resolving to its own gate action, offered wherever
     "Change one of Jarvis's own settings" is, never a plan step, never a read.
  2. ON IS ONE CARD and nothing is written before the yes; a chat with no
     conversation id is refused BEFORE the card (the per-file approval could not
     be limited to one chat), and so is a turn shaped by outside text.
  3. THE CARD LIMIT IS HONOURED before the ONE card that asks - and an instant
     OFF is never refused by it.
  4. THE PER-FILE APPROVAL COVERS `github_fix_write` IN ONE CHAT AND NOTHING
     ELSE: with it live, a fix write raises no card and is logged as `granted`;
     a second chat still asks; the PUSH stage and `github_merge_pr` still ask.
  5. THE BELT STILL BITES: with the mode on and NO grant, `github_merge_pr` and
     `github_fix_and_push` are refused when their verdict came with nobody asked
     (tier "auto"), whatever the settings file says.
  6. EVERY ENDING: Lockdown outranks the grant, 8 hours expires it, a restart
     forgets it, turning the mode off drops it, a new chat cannot use it.
  7. OFF IS INSTANT AND CARDLESS, even in an answer that has already used every
     card its limit allows.
  8. A STANDING GRANT IS A PERSON'S EARLIER YES, not a self-approval: only the
     marker-carrying verdict counts, and only a live grant can produce one.
  9. THE GRANT'S ID IS LOGGED and the conversation id never is.

WHAT IS REAL AND WHAT IS INJECTED. The real `jarvis_agent._one_call` turn path,
the real `jarvis_asks_first.set_github_mode`, the real gate tables and the real
grant store are driven. The model is not: a tool call is handed straight to
`_one_call`, and the GitHub tools' own prepare/execute are replaced with short
plans so nothing reads a token, a network or a scratch folder. The gate is a
stand-in that models the tier exactly as `jarvis_gate.check()` does. A fresh
settings folder is used, so nothing on this PC is touched.
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
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-ghmode-chat-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")
os.environ["JARVIS_SUITE_RUNNING"] = "1"
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""
os.environ["JARVIS_APPROVAL_TIMEOUT"] = "2.0"
os.environ["JARVIS_FRAMEWORK_TOML"] = str(_TMP / "jarvis-framework.toml")
(_TMP / "config").mkdir(parents=True, exist_ok=True)
(_TMP / "jarvis-framework.toml").write_bytes(
    (HERE / "rebuilt" / "jarvis-framework.toml").read_bytes())

sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_agent.py", "jarvis_asks_first.py",
                "jarvis_presets.py", "jarvis_card_words.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import _base  # noqa: E402

GATE_FOLDER = _base.folder("jarvis_gate.py")
if GATE_FOLDER is not None:
    _base.put_on_path(GATE_FOLDER)

import jarvis_agent as AG  # noqa: E402
import jarvis_asks_first as AF  # noqa: E402
import jarvis_framework as FW  # noqa: E402
import jarvis_presets as P  # noqa: E402

GATE = None
try:
    import jarvis_gate as GATE  # noqa: E402
except Exception as _exc:                                  # noqa: BLE001
    print(f"  NOTE  jarvis_gate could not be imported ({type(_exc).__name__}: {_exc})")

# The two things a turn publishes that this suite has no use for.
AG._publish_step = lambda step: None
AG._record_chain = lambda steps: None

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   The stand-ins
# --------------------------------------------------------------------------

class Verdict:
    def __init__(self, allowed=False, outcome="denied", tier="ask",
                 reason="denied by a person", action="", request_id=None):
        self.allowed = allowed
        self.outcome = outcome
        self.tier = tier
        self.reason = reason
        self.action = action
        self.request_id = request_id


APPROVED = Verdict(True, "approved", "ask", "approved by a human")
DENIED = Verdict(False, "denied", "ask")
NOBODY_ASKED = Verdict(True, "auto", "auto", "tier is auto")


class Gate:
    """The real gate's tier behaviour, and a record of every card it asked."""

    def __init__(self, verdict=APPROVED):
        self.verdict = verdict
        self.calls = []
        self.cards = []

    def __call__(self, action, detail, prompt=""):
        self.calls.append({"action": action, "detail": dict(detail or {}),
                           "prompt": prompt})
        tier = AG._tier_of(action)
        if tier == "never":
            return Verdict(False, "refused", "never", "never")
        if tier in ("auto", "notify"):
            return Verdict(True, tier, tier, f"tier is {tier}")
        self.cards.append(self.calls[-1])
        return self.verdict

    def actions(self):
        return [c["action"] for c in self.cards]


class Out:
    def __init__(self):
        self.statuses = []
        self.answers = []
        # `_one_call` reads `out.gone` to know the app's stream ended; on this
        # suite's stand-in it never has.
        self.gone = False

    def set_status(self, status):
        self.statuses.append(status)

    def card_answered(self, verdict):
        self.answers.append(verdict)


def watch(cid="chat-1", provenance="typed", cards=0):
    messages = [{"role": "user", "content": "please do that", "provenance": provenance}]
    w = AG._TurnWatch(request={"messages": messages, "conversation_id": cid})
    w.cards = cards
    return w


def call(name, args, *, gate, w=None, out=None):
    """One tool call down the REAL `_one_call`, and its result as a dict."""
    w = w if w is not None else watch()
    out = out if out is not None else Out()
    convo, steps = [], []
    AG._one_call({"id": "call-1",
                  "function": {"name": name, "arguments": json.dumps(args)}},
                 [name], convo, steps, gate, lambda *a, **k: None, out,
                 lambda *a, **k: None, watch=w)
    result = {}
    for message in convo:
        if message.get("role") == "tool":
            try:
                result = json.loads(message.get("content") or "{}")
            except ValueError:
                result = {"raw": message.get("content")}
    return result, steps, out


def _json(result):
    return json.dumps(result)


#: The GitHub tools' own plan/run halves are replaced: this suite is about the
#: gate path, not about a token, a network or a scratch folder.
EXECUTED = []


def _patch_github_tools():
    fix = AG.TOOLS["github_fix_and_push"]
    merge = AG.TOOLS["github_merge_pr"]

    def fix_prepare(args):
        return (None, "Write ONE file inside the fix copy: "
                      + str((args or {}).get("path") or ""))

    def fix_execute(args, state, **kw):
        EXECUTED.append(("fix", dict(args or {})))
        return {"ok": True, "wrote": (args or {}).get("path")}

    def merge_prepare(args):
        return (None, "Merge pull request " + str((args or {}).get("number") or ""))

    def merge_execute(args, state, **kw):
        EXECUTED.append(("merge", dict(args or {})))
        return {"ok": True, "merged": True}

    fix.prepare, fix.execute = fix_prepare, fix_execute
    merge.prepare, merge.execute = merge_prepare, merge_execute


def fresh():
    """No mode, no grants, no waiting card, and the shipped settings file back."""
    for path in (P._github_mode_path(),):
        try:
            path.unlink()
        except OSError:
            pass
    AG._reset_github_mode_grants()
    with AF._T_LOCK:
        AF._T_STATE["pending"].clear()
        AF._T_STATE["withdrawn"].clear()
        AF._T_STATE["latest"].clear()
        AF._T_STATE["last"].clear()
    (_TMP / "jarvis-framework.toml").write_bytes(
        (HERE / "rebuilt" / "jarvis-framework.toml").read_bytes())
    AF._reload()
    EXECUTED.clear()


def _mode_on(cid="chat-1", gate=None):
    """Turn the mode on through the chat door, the way a real turn does."""
    result, steps, out = call(AG.GITHUB_MODE_TOOL, {"action": "on"},
                              gate=gate or Gate(APPROVED), w=watch(cid=cid))
    return result, steps, out


def _fix_write(cid="chat-1", *, gate=None, w=None):
    args = {"stage": "write", "repo": "owner/repo", "number": "7",
            "worktree": str(_TMP / "fix"), "path": "backend/app.py",
            "content": "print('hi')\n", "message": "fix: one line"}
    return call("github_fix_and_push", args, gate=gate or Gate(DENIED),
                w=w if w is not None else watch(cid=cid))


def audit_lines():
    out = []
    where = FW.log_dir()
    if not where.is_dir():
        return out
    for path in sorted(where.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def audit_events(name):
    return [row for row in audit_lines() if row.get("event") == name]


# --------------------------------------------------------------------------
#   1. The chat door: one tool, its own action, riding with the settings tool
# --------------------------------------------------------------------------

def t_the_chat_door_is_one_tool_with_its_own_action():
    check("the model has a github_mode tool", AG.GITHUB_MODE_TOOL in AG.TOOLS)
    tool = AG.TOOLS.get(AG.GITHUB_MODE_TOOL)
    check("... whose model-facing name is its own gate key (no gate_lookup_name)",
          tool is not None and tool.gate_lookup_name is None)
    if GATE is not None:
        check("... resolving to the mode's own action, never unclassified",
              GATE.action_for_tool(AG.GITHUB_MODE_TOOL) == ("github_mode", True),
              GATE.action_for_tool(AG.GITHUB_MODE_TOOL))
        check("... at tier ask, so its card is a person's yes",
              AG._tier_of("github_mode") == "ask")
    check("it rides with change_setting, the same rule cloud_escalation follows",
          AG.RIDES_WITH_SETTINGS == (AG.ESCALATION_TOOL, AG.GITHUB_MODE_TOOL),
          AG.RIDES_WITH_SETTINGS)
    check("a plan step may never name it", AG.GITHUB_MODE_TOOL in AG._PLAN_EXCLUDED_STEPS)
    check("its result is NOT outside text (it reads no page, file or mail)",
          AG.GITHUB_MODE_TOOL in AG._NOT_READING)
    text = str(getattr(tool, "description", ""))
    check("the tool text says when to call it and never to promise a result",
          "Call this tool" in text and "Never say the mode is on" in text, text[:200])
    check("... and names the writes that keep their own cards",
          "merge" in text.lower() and "still raise their own card" in text.lower(),
          text[:300])


# --------------------------------------------------------------------------
#   2. ON is one card; nothing is written before it
# --------------------------------------------------------------------------

def t_on_is_one_card_and_nothing_before_the_yes():
    fresh()
    result, steps, out = _mode_on(gate=Gate(DENIED))
    check("a DENIED card turned nothing on",
          P.github_mode_on() is False and AG.github_mode_grant("chat-1") is None)
    check("... the model is told it is not on", result.get("ok") is False
          and result.get("changed") is False, result)
    check("... and the step says it was refused, not done",
          steps and steps[0].get("outcome") in ("denied", "refused"), steps)
    # The card's action and words, from a fresh run.
    fresh()
    gate = Gate(APPROVED)
    result, steps, out = call(AG.GITHUB_MODE_TOOL, {"action": "on"}, gate=gate)
    check("one card was asked, under github_mode",
          gate.actions() == ["github_mode"], gate.actions())
    check("... the detail carries the card's own words",
          "Turn on full GitHub mode?" in str((gate.calls[0]["detail"] or {}).get("text")),
          gate.calls[0]["detail"])
    check("... and the approved card turned the mode on and gave this chat its approval",
          P.github_mode_on() is True and result.get("changed") is True
          and result.get("granted") is True, result)
    check("... the app was told approval was being waited for, then that it finished",
          out.statuses[:1] == ["approval"] and out.statuses[-1] == "thinking",
          out.statuses)
    check("... the step says approved", steps and steps[0].get("outcome") == "approved",
          steps)


def t_a_chat_with_no_conversation_id_is_refused_before_the_card():
    fresh()
    gate = Gate(APPROVED)
    result, steps, out = call(AG.GITHUB_MODE_TOOL, {"action": "on"},
                              gate=gate, w=watch(cid=""))
    check("no conversation id: NO card and nothing written",
          gate.calls == [] and P.github_mode_on() is False, (gate.calls, P.github_mode_on()))
    check("... and the model is told why, in words",
          "conversation id" in str(result.get("error")), result.get("error"))
    check("... with no per-file approval invented", not AG._GITHUB_MODE_GRANTS)


def t_a_turn_shaped_by_outside_text_changes_nothing():
    fresh()
    gate = Gate(APPROVED)
    result, steps, out = call(AG.GITHUB_MODE_TOOL, {"action": "on"},
                              gate=gate, w=watch(provenance="page"))
    check("a page-shaped turn: NO card, no mode, no grant",
          gate.calls == [] and P.github_mode_on() is False
          and not AG._GITHUB_MODE_GRANTS, (gate.calls, P.github_mode_on()))
    check("... and the refusal is the settings tool's own sentence",
          result.get("error") == AG.SETTINGS_AFTER_OUTSIDE, result.get("error"))


# --------------------------------------------------------------------------
#   3. The card limit, and the instant OFF that must never meet it
# --------------------------------------------------------------------------

def t_the_card_limit_is_honoured_before_the_card_but_never_blocks_off():
    fresh()
    gate = Gate(APPROVED)
    result, steps, out = call(AG.GITHUB_MODE_TOOL, {"action": "on"}, gate=gate,
                              w=watch(cards=AG.CARDS_PER_TURN))
    check("an answer that has used every card cannot ask for the mode's",
          gate.calls == [] and P.github_mode_on() is False)
    check("... and the model is told to ask again in a new message",
          "already asked" in str(result.get("error")), result.get("error"))
    fresh()
    P.write_github_mode(True)
    gate = Gate(APPROVED)
    result, steps, out = call(AG.GITHUB_MODE_TOOL, {"action": "off"}, gate=gate,
                              w=watch(cards=AG.CARDS_PER_TURN))
    check("OFF in that same full answer is instant and asks nobody",
          gate.calls == [] and P.github_mode_on() is False
          and result.get("changed") is True, (gate.calls, result))


# --------------------------------------------------------------------------
#   4. The grant covers one action in one chat, and nothing else
# --------------------------------------------------------------------------

def t_the_per_file_approval_covers_the_fix_write_in_one_chat():
    fresh()
    _mode_on()
    check("CONTROL: the mode is on and this chat holds the approval",
          P.github_mode_on() is True and AG.github_mode_grant("chat-1") is not None)
    gate = Gate(DENIED)
    result, steps, out = _fix_write(gate=gate)
    check("with the approval live, a fix write raises NO card",
          gate.actions() == [], gate.actions())
    check("... it really ran (the tool's own execute was reached)",
          any(kind == "fix" for kind, _a in EXECUTED), EXECUTED)
    check("... and the result is a success, not a refusal",
          result.get("ok") is True, result)
    check("... and the step records it as `granted`",
          steps and steps[0].get("outcome") == "granted", steps)
    grant = AG.github_mode_grant("chat-1")
    used = [row for row in audit_events("gate.granted")
            if row["detail"].get("grant") == (grant or {}).get("grant_id")]
    check("... the gate's own log carries `gate.granted github_fix_write` with the id",
          len(used) >= 1
          and used[-1]["detail"].get("action") == "github_fix_write", used)
    # A SECOND chat, same mode: the card is back.
    gate2 = Gate(DENIED)
    result2, steps2, _out = _fix_write(cid="chat-2", gate=gate2)
    check("a different chat still asks: ONE github_fix_write card",
          gate2.actions() == ["github_fix_write"], gate2.actions())
    check("... and is refused when that card is denied",
          result2.get("ok") is False and steps2[0].get("outcome") == "denied",
          (result2, steps2))
    # The PUSH stage and a merge are NOT covered, in the chat that HAS the grant.
    gate3 = Gate(DENIED)
    EXECUTED.clear()
    call("github_fix_and_push",
         {"stage": "push", "repo": "owner/repo", "number": "7"},
         gate=gate3, w=watch(cid="chat-1"))
    check("the PUSH stage still raises its own card in the approved chat",
          gate3.actions() == ["github_fix_and_push"], gate3.actions())
    gate4 = Gate(DENIED)
    call("github_merge_pr", {"repo": "owner/repo", "number": "7"},
         gate=gate4, w=watch(cid="chat-1"))
    check("a merge still raises its own card in the approved chat",
          gate4.actions() == ["github_merge_pr"], gate4.actions())
    check("... and neither of them ran", EXECUTED == [], EXECUTED)


# --------------------------------------------------------------------------
#   5. The belt: a verdict with nobody asked is still refused
# --------------------------------------------------------------------------

def t_with_no_grant_a_loosened_tier_still_cannot_run_a_github_write():
    fresh()
    _mode_on(cid="chat-9")
    check("CONTROL: the mode is on and chat-1 has no approval",
          P.github_mode_on() is True and AG.github_mode_grant("chat-1") is None)
    result, steps, out = _fix_write(gate=Gate(NOBODY_ASKED))
    check("github_fix_and_push write: allowed at tier auto, still REFUSED",
          result.get("ok") is False
          and "nobody" in str(result.get("error")).lower(), result.get("error"))
    check("... and it did not run", EXECUTED == [], EXECUTED)
    result, steps, out = call("github_merge_pr",
                              {"repo": "owner/repo", "number": "7"},
                              gate=Gate(NOBODY_ASKED), w=watch())
    check("github_merge_pr: allowed at tier auto, still REFUSED",
          result.get("ok") is False
          and "nobody" in str(result.get("error")).lower(), result.get("error"))
    check("... and it did not run", EXECUTED == [], EXECUTED)


# --------------------------------------------------------------------------
#   6. Every ending of the per-file approval
# --------------------------------------------------------------------------

def t_every_ending_of_the_per_file_approval():
    # LOCKDOWN outranks it.
    fresh()
    _mode_on()
    real_lockdown = AF.lockdown_on
    AF.lockdown_on = lambda: True
    try:
        gate = Gate(DENIED)
        result, steps, _out = _fix_write(gate=gate)
        check("Lockdown outranks the approval: the card is back",
              gate.actions() == ["github_fix_write"]
              and result.get("ok") is False, (gate.actions(), result))
    finally:
        AF.lockdown_on = real_lockdown
    # THE 8-HOUR CAP.
    fresh()
    _mode_on()
    grant = AG._GITHUB_MODE_GRANTS.get("chat-1") or {}
    grant["expires_at"] = time.time() - 1
    gate = Gate(DENIED)
    result, steps, _out = _fix_write(gate=gate)
    expired = [row for row in audit_events("gate.grant_ended")
               if row["detail"].get("state") == "expired"]
    check("8 hours: the approval is dropped and the card is back",
          gate.actions() == ["github_fix_write"] and result.get("ok") is False,
          (gate.actions(), result))
    check("... and the log says `expired`, with the id",
          len(expired) == 1
          and expired[0]["detail"].get("grant") == grant.get("grant_id"), expired)
    # A RESTART.
    fresh()
    _mode_on()
    AG._reset_github_mode_grants()          # what a restart does, exactly
    gate = Gate(DENIED)
    result, steps, _out = _fix_write(gate=gate)
    check("a restart forgets it: the card is back",
          gate.actions() == ["github_fix_write"], gate.actions())
    # TURNING THE MODE OFF.
    fresh()
    _mode_on()
    result, steps, out = call(AG.GITHUB_MODE_TOOL, {"action": "off"},
                              gate=Gate(DENIED), w=watch(cid="chat-1"))
    check("turning the mode off is instant and gives every card back",
          P.github_mode_on() is False and result.get("changed") is True
          and AG.github_mode_grant("chat-1") is None, result)
    gate = Gate(DENIED)
    result, steps, _out = _fix_write(gate=gate)
    check("... so the next fix write asks again",
          gate.actions() == ["github_fix_write"], gate.actions())


# --------------------------------------------------------------------------
#   7. A standing grant is a person's earlier yes, and only that
# --------------------------------------------------------------------------

def t_a_standing_grant_is_a_persons_earlier_yes_only():
    granted = AG._GrantedByStanding()
    check("the grant verdict is allowed, at tier ask, with outcome `granted`",
          granted.allowed is True and granted.tier == "ask"
          and granted.outcome == "granted", vars(granted) if hasattr(granted, "__dict__") else "")
    check("... and `_a_person_said_yes` reads it as a person's yes",
          AG._a_person_said_yes(granted) is True)
    check("a verdict with the same outcome but no marker is NOT a person's yes",
          AG._a_person_said_yes(Verdict(True, "granted", "ask")) is False)
    check("... nor is one that says granted but is not allowed",
          AG._a_person_said_yes(Verdict(False, "granted", "ask")) is False)
    check("... and an ordinary approved verdict is still a yes",
          AG._a_person_said_yes(APPROVED) is True)
    check("only a live grant can produce the marker: the class is built in ONE "
          "place, the grant branch",
          "_GrantedByStanding()" in (HERE / "jarvis_agent.py").read_text(encoding="utf-8")
          and (HERE / "jarvis_agent.py").read_text(encoding="utf-8").count(
              "_GrantedByStanding()") <= 3)


# --------------------------------------------------------------------------
#   8. The grant's id is logged; the chat's id never is
# --------------------------------------------------------------------------

def _holds(rows, needle):
    def walk(value):
        if isinstance(value, str):
            return value == needle
        if isinstance(value, dict):
            return any(walk(k) or walk(v) for k, v in value.items())
        if isinstance(value, (list, tuple)):
            return any(walk(v) for v in value)
        return False
    return any(walk(row) for row in rows)


def t_the_grant_is_logged_and_the_chat_never_is():
    fresh()
    _mode_on()
    grant = AG.github_mode_grant("chat-1") or {}
    made = [row for row in audit_events("gate.grant_made")
            if row["detail"].get("grant") == grant.get("grant_id")]
    check("the gate's own log has `gate.grant_made` with the approval's id",
          len(made) >= 1, made)
    _fix_write(gate=Gate(DENIED))
    used = [row for row in audit_events("gate.granted")
            if row["detail"].get("grant") == grant.get("grant_id")]
    check("... and one `gate.granted github_fix_write` per covered write",
          len(used) == 1 and used[0]["detail"].get("action") == "github_fix_write",
          used)
    check("the conversation id is NEVER written down in the log",
          not _holds(audit_lines(), "chat-1"))


def main():
    _patch_github_tools()
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("t_") and callable(v)]
    for t in tests:
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as exc:                            # noqa: BLE001
            traceback.print_exc()
            check(f"{t.__name__} ran to the end", False, repr(exc))
    fresh()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed checks:")
        for name in FAILED:
            print(f"  {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
