#!/usr/bin/env python3
"""test_github_mode.py - full GitHub mode, slice 1: ONE PC-only card that turns
the mode on, ONE instant off, and the state every screen reads.

    py -3 -B backend/test_github_mode.py

THE OWNER'S ASK, verbatim (2026-11-25):

    "also add a full github mode that gives full parity with less restrictions
     and less cards, full parity with deepseek harness. it can be enabled in
     chat or settings and forwards anything necessary to the cloud api";
    "activating github mode needs a card";
    "in github mode i still want the local ai model to do as much work as
     possible though".

WHAT THIS SUITE PINS, each one a separate way the feature can regress:

  1. THE MODE HAS ONE STATE AND IT FAILS CLOSED: `<settings>/github-mode.json`
     is the mode AND the second standing yes gate 6 reads. Absent, corrupt,
     wrong-shaped or holding anything but `"on": true` reads as OFF.
  2. ON IS ONE CARD and NOTHING is written before a person says yes: a denied,
     timed-out or nobody-asked verdict writes no file, no tool line and no
     per-file approval.
  3. THE CARD SAYS WHAT THE OWNER MUST KNOW: the twenty tools, the cloud
     forwarding, the per-file approval and exactly how it ends, the ten writes
     that keep their own cards, what still never leaves the PC, that OFF is
     instant, and what a no costs.
  4. THE TIER MUST BE "ask": a looser line switches the mode off rather than
     making it cardless, and the card is never raised when the line is not ask.
  5. AN APPROVED CARD WRITES BOTH HALVES - the twenty names and the mode file -
     and records the per-file approval for the ONE chat that asked.
  6. OFF IS INSTANT AND CARDLESS, from either app: the file goes off, the
     twenty names go, every live per-file approval is dropped, and a settings
     file that refuses the last step says so instead of pretending.
  7. THE SETTINGS ROUTE IS PC-ONLY FOR ON (403 `pc_only`) and instant for OFF,
     and it raises the SAME card the chat tool does.
  8. THE PAYLOAD IS THE LEAD'S CONTRACT: exactly `on`, `can_enable`, `effect`,
     `where`, beside `github_group`, and the page row says "always asks".
  9. THE PUBLISHED ROWS ARE WHAT THE GATE BUILDS: the `_RISK` and
     `_TOOL_ACTIONS` rows are found by the `<table>.update({...})` fold, the
     action is PC-only, and NO patch carries the rows (the owner's 2026-11-14
     ruling: base + repair tool).
 10. THE LIVE-INSTALL REPAIR carries both rows, in one write, and is a no-op on
     a gate that already has them.
 11. IT LOOSENS NO OTHER TIER: the ten GitHub writes keep "ask" and stay in
     NEEDS_A_PERSON.

No network, no model, no Windows, no card and no file this PC owns: the gate,
the spawn, the armed check and the settings writer are all stubs here, and the
settings folder is a temporary one.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-ghmode-"))
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

require_shipped("jarvis_asks_first.py", "jarvis_presets.py",
                "jarvis_owner_check.py", "jarvis_card_words.py",
                "jarvis_tool_profiles.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_asks_first as AF  # noqa: E402
import jarvis_card_words as W  # noqa: E402
import jarvis_owner_check as OC  # noqa: E402
import jarvis_presets as P  # noqa: E402
import jarvis_router as RT  # noqa: E402

# The REAL gate, built the way an install builds it (the published base, where
# the end-of-file `_RISK.update` / `_TOOL_ACTIONS.update` rows live).
import _base  # noqa: E402

GATE_FOLDER = _base.folder("jarvis_gate.py")
if GATE_FOLDER is not None:
    _base.put_on_path(GATE_FOLDER)
GATE = None
try:
    import jarvis_gate as GATE  # noqa: E402
except Exception as _exc:                                  # noqa: BLE001
    print(f"  NOTE  jarvis_gate could not be imported ({type(_exc).__name__}: {_exc})")

import jarvis_agent as AG  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


class Verdict:
    """The shape jarvis_gate.check() returns: the four fields the turn reads."""

    def __init__(self, allowed=False, outcome="denied", tier="ask",
                 reason="denied by a person", action="github_mode",
                 request_id=None):
        self.allowed = allowed
        self.outcome = outcome
        self.tier = tier
        self.reason = reason
        self.action = action
        self.request_id = request_id


APPROVED = Verdict(True, "approved", "ask", "approved by a human")
DENIED = Verdict(False, "denied", "ask")
TIMED_OUT = Verdict(False, "timed_out", "ask", "nobody answered")
NOBODY_ASKED = Verdict(True, "auto", "auto", "tier is auto")


class Gate:
    """A stand-in for jarvis_gate.check() that records every question.

    It models the tier the way the real gate does: "auto" and "notify" answer
    allowed with nobody asked, "never" refuses. `cards` is therefore every
    question that really reached a person.
    """

    def __init__(self, verdict=APPROVED):
        self.verdict = verdict
        self.calls = []
        self.cards = []

    def __call__(self, action, detail, prompt=""):
        self.calls.append({"action": action, "detail": dict(detail or {}),
                           "prompt": prompt})
        tier = AF._tier(action)
        if tier == "never":
            return Verdict(False, "refused", "never", "never")
        if tier in ("auto", "notify"):
            return Verdict(True, tier, tier, f"tier is {tier}")
        self.cards.append(self.calls[-1])
        return self.verdict

    def actions(self):
        return [c["action"] for c in self.cards]


def fresh():
    """No mode, no grants, no waiting card: the state every test starts from."""
    try:
        P._github_mode_path().unlink()
    except OSError:
        pass
    AG._reset_github_mode_grants()
    with AF._T_LOCK:
        AF._T_STATE["pending"].clear()
        AF._T_STATE["withdrawn"].clear()
        AF._T_STATE["latest"].clear()
        AF._T_STATE["last"].clear()
        AF._T_STATE["off_rows"].clear()


def _on(verdict=APPROVED, *, cid="chat-1", tier="ask", write=None):
    """One `set_github_mode(True)` with the given verdict. -> (code, body, gate, writes)."""
    gate = Gate(verdict)
    writes = []
    write = write or (lambda t, on: writes.append((t, on)))
    code, body = AF.set_github_mode(
        True, gate_check=gate, tier_of=lambda a: tier, conversation_id=cid,
        write=write)
    return code, body, gate, writes


# --------------------------------------------------------------------------
#   1. The mode file is the only state, and it fails closed
# --------------------------------------------------------------------------

def t_the_mode_file_is_the_only_state_and_it_fails_closed():
    fresh()
    check("absent file: off", P.github_mode_on() is False)
    check("... and the router's reader agrees",
          RT.github_mode_escalation() is False)
    check("... and the page says why, in words",
          P.github_mode_why() == "not turned on for this PC", P.github_mode_why())
    P._github_mode_path().write_text("not json at all", encoding="utf-8")
    check("unreadable file: off", P.github_mode_on() is False)
    P._github_mode_path().write_text("[]", encoding="utf-8")
    check("a list where an object belongs: off", P.github_mode_on() is False)
    P._github_mode_path().write_text('{"on": 1}', encoding="utf-8")
    check("the number 1 is not true: off", P.github_mode_on() is False)
    P._github_mode_path().write_text('{"on": "yes"}', encoding="utf-8")
    check("the word yes is not true: off", P.github_mode_on() is False)
    check("an unreadable file says so", "cannot be read" in P.github_mode_why(),
          P.github_mode_why())
    P._github_mode_path().write_text('{"on": true}', encoding="utf-8")
    check("the boolean true, and only that, is on", P.github_mode_on() is True)
    check("... and the router's reader reads the same file",
          RT.github_mode_escalation() is True)
    check("... and the page has nothing to explain",
          P.github_mode_why() == "", P.github_mode_why())
    fresh()
    check("write_github_mode(True) writes the one file",
          P.write_github_mode(True) is True and P.github_mode_on() is True)
    check("... and write_github_mode(False) really turns it off",
          P.write_github_mode(False) is True and P.github_mode_on() is False)


# --------------------------------------------------------------------------
#   2. ON is ONE card, and nothing is written before the yes
# --------------------------------------------------------------------------

def t_on_is_one_card_and_writes_nothing_before_the_verdict():
    for label, verdict in (("denied", DENIED), ("timed out", TIMED_OUT),
                           ("nobody asked (outcome auto)", NOBODY_ASKED)):
        fresh()
        code, body, gate, writes = _on(verdict)
        check(f"{label}: the card was raised ONCE, under github_mode",
              gate.calls and gate.actions() == ["github_mode"], gate.actions())
        check(f"{label}: nothing was written - no mode file, no tool line, no grant",
              writes == [] and P.github_mode_on() is False
              and AG.github_mode_grant("chat-1") is None,
              (writes, P.github_mode_on(), AG.github_mode_grant("chat-1")))
        check(f"{label}: the answer says it is NOT on and nothing changed",
              body.get("ok") is False and body.get("changed") is False
              and body.get("on") is False, body)
    fresh()
    code, body, gate, writes = _on(tier="auto")
    check("a tier line of auto refuses BEFORE any card is raised",
          code == 503 and gate.calls == [] and writes == [],
          (code, gate.calls, writes))
    check("... and the answer names the setting and the needed word",
          "must be 'ask'" in str(body.get("error")), body.get("error"))


# --------------------------------------------------------------------------
#   3. The card's words carry every fact the owner must read
# --------------------------------------------------------------------------

#: Each (needle, why it must be there). One check per needle.
CARD_FACTS = (
    ("only be approved on this PC, with Windows Hello",
     "the card says it is PC-only"),
    ("all twenty GitHub and review tools",
     "the twenty tools are offered"),
    ("the eighteen GitHub tools and both local review gates",
     "the twenty are named, not just counted"),
    ("may then go to the cloud service you chose in the Presets menu",
     "the cloud forwarding is said"),
    ("Only a GitHub-shaped one", "the forwarding is limited to GitHub work"),
    ("stops asking you for each file", "the per-file card is replaced"),
    ("this chat ends, 8 hours pass, or Jarvis restarts",
     "the per-file approval's four endings are said"),
    ("Merge, push, open a pull request, comment, re-run a workflow, create a "
     "repository, use a workflow, change labels, edit a pull request and post a "
     "review each keep their own card",
     "the ten writes that keep their cards are each named"),
    ("Email, your files, credentials and stored memory still never leave this PC",
     "rule 1 is restated"),
    ("Turning full GitHub mode off is instant, from either app, with no card",
     "OFF is instant and cardless"),
    ("If you say no: nothing changes", "what a no costs is said"),
)


def t_the_card_says_every_fact_in_plain_words():
    words = AF._github_mode_card(True)
    for needle, why in CARD_FACTS:
        check(f"the card's words: {why}", needle in words, needle)
    check("the chat card promises the per-file approval for THIS chat",
          "In THIS chat" in words)
    settings = AF._github_mode_card(False)
    check("the Settings card does NOT promise a per-file approval it cannot give",
          "NOT part of this" in settings
          and "In THIS chat" not in settings, settings[:300])
    check("... and it still says every other fact",
          all(needle in settings for needle, _why in CARD_FACTS[:5] + CARD_FACTS[7:]),
          [needle for needle, _w in CARD_FACTS[:5] + CARD_FACTS[7:]
           if needle not in settings])


# --------------------------------------------------------------------------
#   4. An approved card writes both halves and records the chat's approval
# --------------------------------------------------------------------------

def t_an_approved_card_turns_on_both_halves_and_gives_the_chat_approval():
    fresh()
    code, body, gate, writes = _on(APPROVED)
    check("ONE card was asked, under the mode's own action",
          gate.actions() == ["github_mode"], gate.actions())
    check("the card's detail carries the words, not a bare action name",
          bool(gate.calls[0]["detail"].get("text"))
          and "full github mode" in gate.calls[0]["detail"]["text"].lower(),
          gate.calls[0]["detail"])
    check("the mode file is ON", P.github_mode_on() is True)
    check("... and the twenty tool names were written in ONE group step",
          writes == [("github_tools_group", True)], writes)
    check("... the answer says both happened, and that the chat got its approval",
          body.get("ok") is True and body.get("changed") is True
          and body.get("granted") is True and body.get("chat") is True, body)
    check("... and the words it returns say the per-file approval is in force",
          "In THIS chat" in str(body.get("message")), body.get("message"))
    grant = AG.github_mode_grant("chat-1")
    check("the per-file approval really exists for THAT chat",
          isinstance(grant, dict) and bool(grant.get("grant_id")), grant)
    check(f"... and is capped at the shared 8-hour grant TTL",
          grant is not None
          and 0 < grant["expires_at"] - grant["issued_at"] <= AG.GRANT_TTL_SECONDS,
          grant)
    check("a DIFFERENT chat got no approval of its own",
          AG.github_mode_grant("chat-2") is None)
    check("the mode's last-answer line records the approval",
          AF.github_mode_view(here=True).get("on") is True)


def t_the_settings_door_gives_no_per_file_approval_and_says_so():
    fresh()
    code, body, gate, writes = _on(APPROVED, cid="")
    check("from Settings the mode still turns on", P.github_mode_on() is True
          and body.get("changed") is True)
    check("... with no per-file approval, because there is no chat to scope it to",
          body.get("granted") is False and not AG._GITHUB_MODE_GRANTS)
    check("... and the answer says plainly the per-file approval was not given",
          "NOT given" in str(body.get("message")), body.get("message"))


# --------------------------------------------------------------------------
#   5. OFF is instant, cardless, and ends every live per-file approval
# --------------------------------------------------------------------------

def t_off_is_instant_cardless_and_clears_every_grant():
    fresh()
    _on(APPROVED)
    AG.remember_github_mode_grant("chat-2")
    check("CONTROL: the mode is on and two chats hold approvals",
          P.github_mode_on() is True
          and AG.github_mode_grant("chat-1") and AG.github_mode_grant("chat-2"))
    gate = Gate(DENIED)
    writes = []
    code, body = AF.set_github_mode(
        False, gate_check=gate, tier_of=lambda a: "ask", write=lambda t, on: writes.append((t, on)))
    check("OFF asks NOBODY: no card, no gate call", gate.calls == [], gate.calls)
    check("... it happened at once, and the file is off",
          code == 200 and body.get("changed") is True and body.get("card") is False
          and P.github_mode_on() is False, body)
    check("... the twenty names were removed", writes == [("github_tools_group", False)],
          writes)
    check("... and EVERY live per-file approval is gone",
          AG.github_mode_grant("chat-1") is None
          and AG.github_mode_grant("chat-2") is None)
    code, body = AF.set_github_mode(False, gate_check=gate, tier_of=lambda a: "ask",
                                    write=lambda t, on: writes.append((t, on)))
    check("an OFF on an already-off mode changes nothing and still asks nobody",
          code == 200 and body.get("changed") is False and gate.calls == []
          and writes == [("github_tools_group", False)], (body, writes))


def t_off_reports_a_settings_file_that_refuses_to_lose_the_tools():
    fresh()
    _on(APPROVED)

    def refuse(_tool, _on):
        raise AF.TierFileError("Your settings file cannot be written")

    code, body = AF.set_github_mode(False, gate_check=Gate(DENIED),
                                    tier_of=lambda a: "ask", write=refuse)
    check("the permission half still went off even when the file write failed",
          code == 200 and P.github_mode_on() is False and body.get("ok") is True,
          body)
    check("... and the answer says the tools are still offered and how to hide them",
          "could not be removed" in str(body.get("message"))
          and "Switch the group off" in str(body.get("message")),
          body.get("message"))


# --------------------------------------------------------------------------
#   6. The Settings route: ON only from the PC, OFF instant from either app
# --------------------------------------------------------------------------

def _route(body, *, here, gate=None, tier="ask", armed=True):
    spawned = []

    def spawn(fn):
        spawned.append(fn)
        fn()                       # run the card's thread inline, so the test waits

    gate = gate or Gate(APPROVED)
    writes = []
    code, out = AF.request_tool_enable(
        body, here=here, gate=gate, tier_of=lambda a: tier, spawn=spawn,
        write=lambda t, on: writes.append((t, on)), armed=lambda: armed)
    return code, out, gate, writes, spawned


def t_the_settings_route_is_pc_only_for_on_and_instant_for_off():
    fresh()
    code, out, gate, writes, _spawned = _route(
        {"tool": "github_mode", "enabled": True}, here=False)
    check("ON from anywhere but the PC: 403 pc_only, no card, nothing written",
          code == 403 and out.get("pc_only") is True and gate.calls == []
          and writes == [] and P.github_mode_on() is False,
          (code, out, gate.calls, writes))
    fresh()
    code, out, gate, writes, spawned = _route(
        {"tool": "github_mode", "enabled": True, "conversation_id": "chat-9"},
        here=True)
    check("ON from the PC: the route answers 'waiting' and raises ONE card",
          code == 202 and out.get("waiting") is True
          and gate.actions() == ["github_mode"] and len(spawned) == 1,
          (code, out, gate.actions()))
    check("... and that card's approval turned the mode on and wrote both halves",
          P.github_mode_on() is True and writes == [("github_tools_group", True)])
    check("... and the body's conversation id got the per-file approval",
          AG.github_mode_grant("chat-9") is not None)
    check("... and the last-answer line says it is on",
          (AF._T_STATE["last"] or {}).get("outcome") == "enabled",
          AF._T_STATE["last"])
    gate = Gate(DENIED)
    writes = []
    code, out = AF.set_github_mode(False, write=lambda t, on: writes.append((t, on)))
    check("OFF from the route - even off the PC - is instant and cardless",
          code == 200 and out.get("changed") is True and gate.calls == [],
          (code, out, gate.calls))
    fresh()
    code, out, gate, writes, _ = _route(
        {"tool": "github_mode", "enabled": True}, here=True, armed=False)
    check("a PC with no owner check armed refuses ON before a card",
          code == 503 and gate.calls == [] and writes == [], (code, out))
    fresh()
    code, out, gate, writes, _ = _route(
        {"tool": "github_mode", "enabled": True}, here=True, tier="auto")
    check("a tier line of auto refuses ON before a card",
          code == 503 and gate.calls == [] and writes == [], (code, out))


# --------------------------------------------------------------------------
#   7. The payload is the lead's contract, beside github_group
# --------------------------------------------------------------------------

#: The desktop row, the phone row and the API page are built against these two
#: sentences (the lead's contract, 2026-11-25). A change here is a cross-lane
#: change, which is why the suite pins the words.
CONTRACT_EFFECT = (
    "Offers all twenty GitHub tools, and lets a GitHub question go to the cloud "
    "without asking again. Asked in chat, turning it on also makes the fix loop ask "
    "once for that chat, not once per file. Merge, push, open PR, comment, re-run, "
    "create a repo, labels, edit and review each keep their own card.")
CONTRACT_WHERE = ("Settings, What asks first, on this PC - turning it on needs "
                  "Windows Hello. Either app can turn it off.")


def t_the_payload_is_the_leads_contract_beside_github_group():
    fresh()
    tools = AF.tools_status(here=True)
    mode = tools.get("github_mode")
    check("the payload carries a github_mode object", isinstance(mode, dict), mode)
    check("... with EXACTLY the four contract keys, in order",
          list(mode or {}) == ["on", "can_enable", "effect", "where"], list(mode or {}))
    check("... reading off", (mode or {}).get("on") is False)
    check("... enabled from this PC", (mode or {}).get("can_enable") is True)
    check("... the effect is the contract's sentence",
          (mode or {}).get("effect") == CONTRACT_EFFECT, (mode or {}).get("effect"))
    check("... and so is where it changes",
          (mode or {}).get("where") == CONTRACT_WHERE, (mode or {}).get("where"))
    away = AF.tools_status(here=False)["github_mode"]
    check("away from the PC can_enable is False and the state is still the real one",
          away.get("can_enable") is False and away.get("on") is False, away)
    P.write_github_mode(True)
    check("the mode's real state reaches the payload with no restart",
          AF.tools_status(here=False)["github_mode"]["on"] is True)
    check("... and the group switch is still the separate object beside it",
          "github_group" in tools and "github_mode" in tools
          and (tools.get("github_group") or {}).get("id") == AF.GITHUB_TOOLS_GROUP)
    check("... the mode is not a per-tool switch row",
          AF.GITHUB_MODE_ID not in AF.TOOLS_SWITCHABLE
          and AF.GITHUB_MODE_ID not in [i["id"] for i in tools["items"]])
    view = AF.view(here=True)
    check("the page's own payload carries it too",
          (view.get("tools") or {}).get("github_mode") == AF.tools_status(here=True)["github_mode"])


# --------------------------------------------------------------------------
#   8. The published rows, the page row and the tier
# --------------------------------------------------------------------------

def t_the_published_rows_are_what_the_gate_builds():
    if GATE is None:
        skip("jarvis_gate.py is not here, so the published rows cannot be read")
        return
    risk = GATE.risk_for("github_mode")
    check("the gate classifies github_mode (found by the <table>.update fold)",
          risk.get("classified") is True, risk)
    check("... reversible 'yes' and reach 'outbound' - off is instant, the words may leave",
          (risk.get("reversible"), risk.get("reach")) == ("yes", "outbound"), risk)
    check("... so it is a risky card: Windows Hello on the PC, never a swipe",
          risk.get("swipe_ok") is False, risk)
    check("... and its words say the ten writes keep their own cards",
          "merge, push, open a pull request" in risk.get("why", ""), risk.get("why"))
    check("action_for_tool('github_mode') is the mode's own action, not unclassified",
          GATE.action_for_tool("github_mode") == ("github_mode", True),
          GATE.action_for_tool("github_mode"))
    check("the shipped tier line is 'ask'",
          GATE._tiers().get("github_mode") == "ask", GATE._tiers().get("github_mode"))
    check("the action is PC-only, so the phone can never approve its card",
          "github_mode" in OC.PC_ONLY_ACTIONS, sorted(OC.PC_ONLY_ACTIONS))
    check("its card has written words (a Windows Hello prompt must name it)",
          W.has_written_title("github_mode") is True)
    check("... and a short row like every other action",
          "github_mode" in W.SUMMARY and "github_mode" in W.TITLES)
    ids = [a for _title, rows in AF.GROUPS for a in rows]
    check("the page lists it", "github_mode" in ids)
    check("... as a row that always asks and cannot be loosened from an app",
          "github_mode" in AF.MUST_ASK and "github_mode" in AF.HARD_LIMITS
          and "github_mode" not in AF.SWITCHABLE)
    row = AF._row("github_mode", here=True)
    check("... with the page's own 'always asks' words and no switch",
          row.get("says") == AF.SAYS["ask"] and row.get("note") == AF.NOTE_ALWAYS
          and "switch" not in row, row)
    import tomllib
    cfg = tomllib.loads((HERE / "rebuilt" / "jarvis-framework.toml")
                        .read_text(encoding="utf-8"))
    check("the shipped settings copy carries github_mode = \"ask\"",
          cfg.get("autonomy", {}).get("tiers", {}).get("github_mode") == "ask",
          cfg.get("autonomy", {}).get("tiers", {}).get("github_mode"))


def t_the_rows_ride_the_base_and_the_repair_tool_not_a_patch():
    patches = [(p.name, p.read_text(encoding="utf-8"))
               for p in sorted(HERE.glob("*.patch"))]
    carriers = [name for name, text in patches if "github_mode" in text]
    check("NO patch carries the mode's rows (the owner's 2026-11-14 ruling)",
          carriers == [], carriers)
    base = (REPO / "jarvis-backend" / "jarvis_gate.py").read_text(encoding="utf-8")
    check("the published base carries the risk row in an end-of-file update",
          '"github_mode": ("yes", "outbound",' in base)
    check("... and the tool mapping beside it",
          '"github_mode": "github_mode",' in base)
    check("... AFTER the scheduling batch's own end-of-file block (both kept)",
          base.index('"cancel_scheduled": "auto",')
          < base.index('"github_mode": ("yes", "outbound",'))
    check("the base still ends without a trailing newline, as it did",
          not base.endswith("\n"), repr(base[-3:]))
    check("the mode's own row text is the one the repair tool carries",
          '"github_mode": ("yes", "outbound", "turns GitHub mode on for this PC'
          in base)


# --------------------------------------------------------------------------
#   9. The live-install repair
# --------------------------------------------------------------------------

def _repair_tool():
    spec = importlib.util.spec_from_file_location(
        "repair_tool_for_github_mode_test",
        REPO / "tools" / "repair_live_backend_gaps.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["repair_tool_for_github_mode_test"] = mod
    spec.loader.exec_module(mod)
    return mod


LIVE_GATE = (
    "_RISK: dict[str, tuple[str, str, str]] = {\n"
    '    "web_research": ("yes", "outbound", "a public query leaves the machine"),\n'
    "}\n"
    "\n"
    "_TOOL_ACTIONS: dict[str, str] = {\n"
    '    "calculator": "auto",\n'
    "}\n"
)


def _live_folder():
    d = _TMP / "live-gate"
    d.mkdir(parents=True, exist_ok=True)
    for p in d.glob("*"):
        p.unlink()
    (d / "jarvis_gate.py").write_text(LIVE_GATE, encoding="utf-8", newline="\n")
    return d


def t_the_repair_tool_carries_both_rows_to_a_live_install():
    if GATE is None:
        skip("jarvis_gate.py is not here, so there is no base row to compare")
        return
    mod = _repair_tool()
    repair = mod.REPAIRS.get("github-mode")
    check("the repair tool has an entry for the mode", repair is not None)
    if repair is None:
        return
    live = _live_folder()
    check("a live gate without the rows is reported missing",
          mod.check_one(live, repair) == "missing")
    check("... and ONE apply writes them",
          mod.apply_one(live, repair, stamp="test") == "applied")
    text = (live / "jarvis_gate.py").read_text(encoding="utf-8")
    why = GATE._RISK["github_mode"][2]
    check("the repaired file carries the base's own risk row, byte for byte",
          ('"github_mode": ("yes", "outbound", ' + json.dumps(why) + "),") in text,
          text[:400])
    check("... and the tool mapping", '"github_mode": "github_mode",' in text)
    check("... exactly once each", text.count('"github_mode": ("yes", "outbound"') == 1
          and text.count('"github_mode": "github_mode"') == 1)
    check("... a second apply is the idempotent no-op",
          mod.apply_one(live, repair, stamp="test-2") == "already")
    check("... and one backup was left for the one write",
          len(list(live.glob("jarvis_gate.py.before-repair-*"))) == 1)


# --------------------------------------------------------------------------
#  10. It loosens no other tier and no other card
# --------------------------------------------------------------------------

#: Every GitHub write the owner said keeps its own card, and the two reads whose
#: card-free state must not change either.
KEPT_CARDED = (
    "github_merge_pr", "github_fix_and_push", "github_open_pr", "github_comment",
    "github_open_issue", "github_rerun_workflow", "github_create_repo",
    "github_workflow", "github_issue_labels", "github_edit_pr", "github_pr_review",
    "github_issue_state", "github_fix_write",
)


def t_the_mode_loosens_no_other_tier_and_no_other_card():
    if GATE is None:
        skip("jarvis_gate.py is not here, so the tier table cannot be read")
        return
    fresh()
    _on(APPROVED)
    tiers = GATE._tiers()
    for action in KEPT_CARDED:
        check(f"{action} still asks, with the mode on", tiers.get(action) == "ask",
              tiers.get(action))
        check(f"... and is still in NEEDS_A_PERSON (the belt)",
              action in AG.NEEDS_A_PERSON, action)
    check("the mode adds no 'auto' line for any GitHub write",
          not [a for a in KEPT_CARDED if tiers.get(a) in ("auto", "notify")],
          [a for a in KEPT_CARDED if tiers.get(a) in ("auto", "notify")])
    check("... and it is the mode, not the action, that is new: no GitHub tool's "
          "own action name resolves to github_mode",
          [t for t in ("github_merge_pr", "github_fix_write", "github_fix_and_push",
                       "github_open_pr")
           if GATE.action_for_tool(t)[0] == "github_mode"] == [])


def main():
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
