"""test_web_search_grant.py - "you have full approval to search the web in this
conversation" (the owner's ask, 2026-11-01).

    python3 backend/test_web_search_grant.py

THE OWNER'S WORDS, both messages:

  "if I ask jarvis and say you have full approval to search the web for
   anything during this conversation. give jarvis the approval to search the
   web for the entire conversation until I say it doesn't have authorization
   to do that. make sure a card comes up that I have to approve before this
   happens"
  "and if I ask anything further like book a flight for me online then it will
   have to have another card to approve further action beyond just searching
   the web."

WHAT IT PROVES, in the nine numbered cases the brief names - each check is
driven through the REAL turn loop (`jarvis_agent.run_local_turn`), the real
`jarvis_search` planning, and the real `jarvis_gate` audit writers from
`jarvis-backend/` (never a stub of them), against a throwaway config folder, a
throwaway log folder and a stand-in for the model:

  1. Without a card there is no grant: a search that would ask still asks, and
     a denied card sends nothing. (`t_no_card_then_no_grant`)
  2. Asking for the grant raises EXACTLY ONE card, and a denial leaves every
     search asking. (`t_one_card_and_a_denial_grants_nothing`)
  3. With an approved grant, a web_search in the same conversation runs with NO
     second card, and the gate's own log carries `gate.granted` with the grant
     id - read back out of the log file, not out of a stub.
     (`t_an_approved_grant_runs_the_search_and_logs_it`)
  4. The grant changes NO other action: six are named, two are driven on the
     real path with a grant live (each raises its own card and nothing runs),
     and the rest are read from the real gate's own tier table; and the grant is
     read in exactly ONE place in the whole module.
     (`t_the_grant_covers_no_other_action`)
  5. Conversation A's grant does not cover conversation B.
     (`t_conversation_a_does_not_cover_conversation_b`)
  6. Revocation is instant and idempotent: no card, the log says so, a second
     stop changes nothing, and the next search asks again.
     (`t_revocation_is_instant_and_idempotent`)
  7. The 8-hour cap and a restart end it, and a new chat starts clean.
     (`t_the_cap_a_restart_and_a_new_chat_end_it`)
  8. "Book a flight for me" still raises its own card while the grant is live.
     (`t_booking_a_flight_still_asks`)
  9. An open-ended "full approval to do anything" grants search only: the card
     says so in its own words, and nothing widens.
     (`t_open_ended_words_grant_search_only`)
 10. The field test of 2026-11-02: a natural request reaches the grant tool on
     the tools a real PC offers (the ask rides with web search), a natural
     request raises EXACTLY one card and the search after it asks no more, the
     prompt's "a grant is in force" line is a real store read, and an answer
     that claims an approval the store does not hold is corrected in plain
     words - while an honest denial or a conditional is never touched.
     (`t_a_natural_request_reaches_the_grant_tool`,
     `t_the_model_cannot_claim_a_grant_it_does_not_have`,
     `t_the_prompt_state_is_a_real_read`)

And the delivery itself: `backend/web-search-grant.patch` applies to
`jarvis-backend/jarvis_gate.py` and reverses byte for byte, both shipped
settings copies carry the two tier lines, and both `_RISK` rows are in the
published base. (`t_the_patch_and_the_tables`)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-wsgrant-"))
# Before anything imports jarvis_framework: its CONFIG_DIR is read once. The
# log folder is named explicitly so every audit line this suite reads back is
# one it wrote itself - never a line from the owner's real log.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")
_TMP.joinpath("config").mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_agent.py", "jarvis_search.py", "jarvis_card_words.py")

if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

# THE REAL SETTINGS FILE, so the tiers this suite drives are the ones that ship
# (grant "ask", revoke "auto") and not the unknown-action fallback. Without it
# every action would read "ask" in this throwaway config folder and the
# instant, card-free stop could not be tested at all.
shutil.copyfile(HERE / "rebuilt" / "jarvis-framework.toml",
                _TMP / "config" / "jarvis-framework.toml")

import jarvis_agent as AG  # noqa: E402
import jarvis_search as WS  # noqa: E402
import jarvis_framework as FW  # noqa: E402
import jarvis_asks_first as AF  # noqa: E402
import _base  # noqa: E402

# The two things a turn publishes that this suite has no use for, and that
# would otherwise write to the event bus.
AG._publish_step = lambda step: None
AG._record_chain = lambda steps: None

# The real gate: jarvis-backend/ holds the state the whole patch stack leaves,
# which is where this feature's audit writers and risk rows live.
GATE_FOLDER = _base.folder("jarvis_gate.py")
_base.put_on_path(GATE_FOLDER)
GATE = None
try:
    import jarvis_gate as GATE  # noqa: E402
except Exception as _exc:                                  # noqa: BLE001
    GATE = None
    print(f"  NOTE  jarvis_gate could not be imported ({type(_exc).__name__}: {_exc})")

# `control_computer` is driven on the REAL turn path in cases 4 and 8, only to
# prove it still raises its own card while a grant is live - not to read a real
# screen. Planning it reads a window through `jarvis_ui_control`'s injectable
# reader, whose default needs Windows + `uiautomation`; on the CI runner that
# module is absent, so the tool refused BEFORE any card
# ("no UI reader was given and 'uiautomation' is not installed") and the Linux
# run failed for a reason that had nothing to do with grants. The reader is
# replaced with the two windows those cases name. No other check here reads a
# screen, and the app's own behaviour is unchanged.
try:
    import jarvis_ui_control as _UIC  # noqa: E402

    _UIC._default_read = lambda window: {
        "Notepad": [{"name": "Save", "automation_id": "save", "enabled": True}],
        "Booking - Chrome": [{"name": "Pay now", "automation_id": "pay", "enabled": True}],
    }.get(window, [])
except Exception as _exc:                                  # noqa: BLE001
    print(f"  NOTE  jarvis_ui_control could not be imported ({type(_exc).__name__}: {_exc})")

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass (BLOCKED is never a pass, CLAUDE.md)."""
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   The stand-ins: the model, the gate, and the one thing a search sends
# --------------------------------------------------------------------------

class Verdict:
    """The shape jarvis_gate.check() returns, and nothing more: the turn reads
    `.allowed`, `.outcome`, `.tier`, `.reason`, `.request_id` and `.action`
    (gate-outcome.patch's fields) and nothing else."""

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


class Gate:
    """A stand-in for jarvis_gate.check(), and it models the TIER - which is
    the part that decides whether a person is asked at all.

    `answers` maps an action name to the verdict it gets when it asks; anything
    else gets `default`. A tier of "auto" or "notify" answers allowed with
    nobody asked (exactly as the real gate does), and "never" refuses. So
    `gate.cards` is every question that really reached a person, and
    `gate.calls` is every question asked of the gate - and a test that says
    "no card" is saying something about `cards`, not about a string.
    """

    def __init__(self, answers=None, default=APPROVED):
        self.answers = dict(answers or {})
        self.default = default
        self.calls = []          # every question, card or not
        self.cards = []          # the ones put in front of a person

    def __call__(self, action, detail, prompt=""):
        row = {"action": action, "detail": detail, "prompt": prompt}
        self.calls.append(row)
        tier = AG._tier_of(action)
        if tier == "never":
            return Verdict(False, "refused", "never",
                           "this action is set to 'never'")
        if tier in ("auto", "notify"):
            return Verdict(True, tier, tier, f"tier is {tier}")
        self.cards.append(row)
        return self.answers.get(action, self.default)

    def actions(self):
        """The actions a PERSON was asked about, in order."""
        return [c["action"] for c in self.cards]


class Model:
    """The model, as a list of rounds: each round is the tool calls to ask for,
    and the last round is the answer. `post` answers them in order."""

    def __init__(self, rounds, answer="done"):
        self.rounds = [r for r in rounds]
        self.answer = answer
        self.sent = []
        self.index = 0

    def post(self, url, payload):
        self.sent.append(payload)
        if self.index < len(self.rounds):
            calls = self.rounds[self.index]
            self.index += 1
            if calls:
                return {"choices": [{"message": {
                    "role": "assistant", "tool_calls": [
                        {"id": f"c{i}", "function": {"name": n,
                                                     "arguments": json.dumps(a)}}
                        for i, (n, a) in enumerate(calls)]}}]}
        return {"choices": [{"message": {"role": "assistant", "content": self.answer}}]}

    def told(self):
        """Every tool result the model was handed, newest round last."""
        out = []
        for payload in self.sent[-1:]:
            out += [m for m in payload.get("messages") or [] if m.get("role") == "tool"]
        return out

    def all_told(self):
        out = []
        for payload in self.sent:
            out += [m for m in payload.get("messages") or [] if m.get("role") == "tool"]
        return out


def reset(*, ask_every_time=False):
    """No grants, a fresh search setting, a fresh log folder, no fakes left."""
    AG._reset_web_search_grants()
    AG._conversation_tainted = _real_tainted
    try:
        WS.settings_path().unlink()
    except OSError:
        pass
    WS._save(provider="searxng", searxng_url="http://127.0.0.1:8888",
             ask_every_time=ask_every_time)
    WS.run = _real_run
    runs = []
    shutil.rmtree(_TMP / "logs", ignore_errors=True)
    return runs


_real_run = WS.run
_real_tainted = AG._conversation_tainted


def _fake_run(seen):
    """A search that "ran": records its words and answers like a real one."""
    def run(p, approved=False):
        seen.append(getattr(p, "query", ""))
        return {"ok": True, "query": getattr(p, "query", ""),
                "results": [{"title": "A result", "url": "https://example.test/1",
                             "snippet": "words"}]}
    return run


def _turn(*, cid="c1", tool_calls, gate, runs, tainted=False, enabled=None,
          answer="done", words="please", strict=False):
    """One real turn: the model asks for `tool_calls`, then answers.

    `enabled` is the tools the turn is OFFERED. By default the tool it calls is
    added to that set (the older tests are about the gate, not about the offer);
    `strict=True` offers exactly `enabled` and nothing else, which is what a
    real turn does - it is how the field-test case is driven below.

    Returns (the model, its tool results for the last round, the turn summary).
    """
    AG._conversation_tainted = (lambda c, messages=None: True) if tainted \
        else (lambda c, messages=None: False)
    WS.run = _fake_run(runs)
    model = Model([tool_calls, []], answer=answer)
    req = [{"role": "user", "content": words, "provenance": "typed"}]
    messages = [{"role": "user", "content": words}]
    names = set(enabled or ())
    if not strict:
        names |= {n for n, _a in tool_calls}
    summary = AG.run_local_turn(
        messages, "m", ollama_url="http://127.0.0.1:11434",
        stream_out=lambda b: None, post=model.post, gate_check=gate,
        enabled_tools=names, record_chain=lambda s: None, context_length=8192,
        request={"messages": req, "conversation_id": cid})
    return model, model.told(), summary or {}


def _grant_now(cid="c1", gate=None, runs=None):
    """The one card, approved, in one real turn. Returns the gate it used."""
    gate = gate or Gate()
    runs = runs if runs is not None else []
    _turn(cid=cid, tool_calls=[(AG.GRANT_TOOL, {})], gate=gate, runs=runs)
    return gate


def _search_in(*, cid="c1", gate, runs, tainted=True, query="walking boots"):
    """One real turn in which the model searches the web. Returns the model's
    tool results."""
    model, told, _summary = _turn(cid=cid, gate=gate, runs=runs, tainted=tainted,
                                  tool_calls=[("web_search", {"query": query})])
    return told


def audit_lines():
    """Every audit line this suite's own process wrote, newest last."""
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


def _said(told):
    """The tool result the model was handed, as text."""
    return " ".join(str(m.get("content") or "") for m in told)


# --------------------------------------------------------------------------
#   1. Without a card there is no grant
# --------------------------------------------------------------------------

def t_no_card_then_no_grant():
    if GATE is None:
        skip("jarvis_gate.py is not here, so the grant cannot be created at all")
        return
    runs = reset()
    check("a fresh process holds no grant for any chat",
          AG.web_search_grant("c1") is None and AG.web_search_grant("c2") is None)
    # The owner's own typed question: no card, and that is unchanged (the
    # ordinary web-search rule, not this feature).
    gate = Gate()
    _search_in(gate=gate, runs=runs, tainted=False)
    check("a plain search with no grant: the ordinary path still runs it, no card",
          gate.calls == [] and runs == ["walking boots"], (gate.actions(), runs))
    # A search that WOULD ask: with no grant it asks, and a denial sends nothing.
    runs = reset()
    gate = Gate(default=DENIED)
    told = _search_in(gate=gate, runs=runs, tainted=True)
    check("no grant, and a search that would ask: exactly ONE card for search_the_web",
          gate.actions() == [WS.ACTION_SEARCH], gate.actions())
    check("... denied: nothing was sent", runs == [], runs)
    check("... and the model is told it was refused, not that it searched",
          "refused" in _said(told) and "Nothing was searched" in _said(told), _said(told))
    check("... and no grant exists afterwards",
          AG.web_search_grant("c1") is None)


# --------------------------------------------------------------------------
#   2. One card for the grant, and a denial grants nothing
# --------------------------------------------------------------------------

def t_one_card_and_a_denial_grants_nothing():
    if GATE is None:
        skip("jarvis_gate.py is not here, so the grant cannot be created at all")
        return
    runs = reset()
    gate = Gate(default=DENIED)
    model, told, summary = _turn(tool_calls=[(AG.GRANT_TOOL, {})], gate=gate,
                                 runs=runs, enabled={AG.GRANT_TOOL})
    check("asking for the grant raises EXACTLY one card, under its own action",
          gate.actions() == [AG.GRANT_ACTION], gate.actions())
    check("... and the card's words are the feature's own (not a generic line)",
          "without a card each time" in gate.calls[0]["detail"]["text"]
          and "Nothing else is covered" in gate.calls[0]["detail"]["text"],
          gate.calls[0]["detail"]["text"][:200])
    check("... and what the model is told is a refusal, and says nothing changed",
          "refused" in _said(told).lower() or "nothing changed" in _said(told).lower(),
          _said(told)[:300])
    check("a DENIED grant card grants nothing at all",
          AG.web_search_grant("c1") is None)
    check("... and no `gate.grant_made` line was written",
          audit_events("gate.grant_made") == [])
    # And the next search in that chat still asks.
    gate2 = Gate(default=DENIED)
    _search_in(gate=gate2, runs=runs, tainted=True)
    check("... so the next search in that chat still asks",
          gate2.actions() == [WS.ACTION_SEARCH], gate2.actions())
    # A card nobody answered, and one the gate let through with nobody asked,
    # must also grant nothing (a grant is a person's yes or it is nothing).
    runs = reset()
    gate3 = Gate(default=Verdict(False, "timed_out", "ask", "nobody answered"))
    _turn(tool_calls=[(AG.GRANT_TOOL, {})], gate=gate3, runs=runs,
          enabled={AG.GRANT_TOOL})
    check("a card nobody answered grants nothing",
          AG.web_search_grant("c1") is None)
    runs = reset()
    gate4 = Gate(default=Verdict(True, "auto", "auto", "tier is auto"))
    _turn(tool_calls=[(AG.GRANT_TOOL, {})], gate=gate4, runs=runs,
          enabled={AG.GRANT_TOOL})
    check("a verdict with nobody asked (outcome `auto`) grants nothing either",
          AG.web_search_grant("c1") is None)
    check("... because the grant tool is one a PERSON must answer, whatever the "
          "tier says (NEEDS_A_PERSON) - the belt for a loosened settings file",
          AG.GRANT_TOOL in AG.NEEDS_A_PERSON)
    check("... while the stop is NOT: it takes permission away, runs at tier "
          "`auto`, and must never wait for a card",
          AG.REVOKE_TOOL not in AG.NEEDS_A_PERSON
          and AG._tier_of(AG.REVOKE_ACTION) == "auto")


# --------------------------------------------------------------------------
#   3. An approved grant: no second card, and the log says so
# --------------------------------------------------------------------------

def t_an_approved_grant_runs_the_search_and_logs_it():
    if GATE is None:
        skip("jarvis_gate.py is not here, so no grant and no audit line")
        return
    runs = reset()
    gate = Gate()
    _turn(cid="c1", tool_calls=[(AG.GRANT_TOOL, {})], gate=gate, runs=runs,
          enabled={AG.GRANT_TOOL})
    check("the grant card was asked once and approved",
          gate.actions() == [AG.GRANT_ACTION], gate.actions())
    grant = AG.web_search_grant("c1")
    check("an approved card stores ONE grant for this conversation, with an id "
          "and a cap", bool(grant) and bool(grant.get("grant_id"))
          and grant.get("expires_at", 0) > grant.get("issued_at", 1)
          and 0 < grant["expires_at"] - grant["issued_at"] <= AG.GRANT_TTL_SECONDS,
          grant)
    made = audit_events("gate.grant_made")
    check("... the gate's own log has `gate.grant_made` with that id",
          len(made) == 1 and made[0]["detail"].get("grant") == (grant or {}).get("grant_id"),
          made)
    # The search that used to ask: no second card, and it really ran.
    gate2 = Gate()
    told = _search_in(gate=gate2, runs=runs, tainted=True)
    check("with the grant live, a search that would ask raises NO card at all",
          gate2.actions() == [], gate2.actions())
    check("... and the search really ran (the words were sent)",
          runs == ["walking boots"], runs)
    used = audit_events("gate.granted")
    check("... and the gate's log carries `gate.granted search_the_web` with the "
          "grant's id - read back out of the log file itself",
          len(used) == 1
          and used[0]["detail"].get("action") == WS.ACTION_SEARCH
          and used[0]["detail"].get("grant") == grant["grant_id"], used)
    check("... the grant id is in the log as an id, not redacted away",
          isinstance(used[0]["detail"].get("grant"), str)
          and len(used[0]["detail"]["grant"]) == 12, used[0]["detail"])
    # A second search under the same grant: still no card, and logged again.
    gate3 = Gate()
    _search_in(gate=gate3, runs=runs, tainted=True, query="second search")
    check("a second search in the same chat: no card, logged again",
          gate3.actions() == [] and runs[-1] == "second search"
          and len(audit_events("gate.granted")) == 2,
          (gate3.actions(), runs, len(audit_events("gate.granted"))))
    check("... and the conversation itself is NEVER written down in the log "
          "(only the grant's own random id)",
          not _holds(audit_lines(), "c1"))


def _holds(rows, needle):
    """True when `needle` is a WHOLE value anywhere in these audit rows.

    A substring search would match a grant id that happens to contain "c1"
    (they are hex), which is a false alarm about a leak that has not happened.
    """
    def walk(value):
        if isinstance(value, str):
            return value == needle
        if isinstance(value, dict):
            return any(walk(k) or walk(v) for k, v in value.items())
        if isinstance(value, (list, tuple)):
            return any(walk(v) for v in value)
        return False
    return any(walk(row) for row in rows)
    _ = told


# --------------------------------------------------------------------------
#   4. The grant covers NO other action
# --------------------------------------------------------------------------

#: The actions the owner's own sentence ("book a flight for me", and everything
#: that is not a search) must still be asked about. The first two are driven on
#: the real path below; all six are read from the real gate's own tier table.
OTHER_ACTIONS = (
    ("send_email", "send an email"),
    ("control_browser", "work a web page in a browser"),
    ("spend_money", "spend money"),
    ("delete_file", "delete a file"),
    ("run_shell_on_host", "run a command on this PC"),
    ("change_own_config", "change one of Jarvis's own settings"),
)


def t_the_grant_covers_no_other_action():
    if GATE is None:
        skip("jarvis_gate.py is not here, so the real tier table cannot be read")
        return
    # (a) ONE reader in the whole module. If a second place ever read a grant,
    # the search's card could be skipped somewhere else - and that is the one
    # way this feature could widen.
    src = (HERE / "jarvis_agent.py").read_text(encoding="utf-8")
    reader_fns, current = set(), ""
    pattern = re.compile(r"(?<![\w])web_search_grant\(")
    for line in src.splitlines():
        if line.startswith("def ") or line.startswith("class "):
            current = line.split("(")[0].replace("def ", "").replace("class ", "").strip()
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("def web_search_grant"):
            continue
        if pattern.search(line):
            reader_fns.add(current)
    check("a grant is READ in exactly four places, all named, and only the FIRST "
          "can skip a card: the search itself. The other three only REPORT the "
          "same store - the 'already on' refusal, the prompt's state line and the "
          "false-claim correction - so none of them can widen what a grant covers",
          reader_fns == {"_web_search_call", "_prepare_web_search_grant",
                         "_grant_prompt_line", "_grant_claim_line"},
          sorted(reader_fns))
    check("... and the grant store is one plain dict in this process's memory "
          "(no file, no database)",
          isinstance(AG._GRANTS, dict)
          and not (HERE / "rebuilt" / "web_search_grant.json").exists())
    # (b) The real gate's own table: every one of them still asks.
    tiers = {}
    try:
        tiers = dict(GATE._tiers())
    except Exception as exc:                              # noqa: BLE001
        skip(f"the gate's tier table could not be read ({type(exc).__name__})")
    if tiers:
        for action, what in OTHER_ACTIONS:
            tier = tiers.get(action, "ask (no line: unknown_action_tier)")
            check(f"{action} ({what}) still asks: its tier is {tier!r}",
                  tier not in ("auto", "notify", "never"), tier)
        check("... and the grant's own action is the only one this feature added",
              tiers.get(AG.GRANT_ACTION) == "ask"
              and tiers.get(AG.REVOKE_ACTION) == "auto",
              (tiers.get(AG.GRANT_ACTION), tiers.get(AG.REVOKE_ACTION)))
    # (c) On the real path, with a grant LIVE, two of them raise their own card
    # and nothing runs. Both are offline-safe on purpose: `read_web_page`
    # resolves its host (and refuses a private address, so it cannot be driven
    # hermetically - its card is covered by the tier check above instead), and
    # `browser_control` is not offered at all without the second-card lane.
    for tool, args, want in (("shell_exec", {"command": "echo hi"}, "run_shell_on_host"),
                             ("control_computer",
                              {"goal": "book a flight", "window": "Notepad",
                               "requests": [{"control": "Save", "action": "click"}]},
                              "control_computer")):
        runs = reset()
        _grant_now(runs=runs)
        check(f"CONTROL: the grant is live before {tool} runs",
              AG.web_search_grant("c1") is not None)
        gate = Gate(default=DENIED)
        model = Model([[ (tool, args) ], []])
        AG._conversation_tainted = lambda c, messages=None: False
        WS.run = _fake_run(runs)
        AG.run_local_turn(
            [{"role": "user", "content": "book me a flight"}], "m",
            ollama_url="http://127.0.0.1:11434", stream_out=lambda b: None,
            post=model.post, gate_check=gate, enabled_tools={tool},
            record_chain=lambda s: None, context_length=8192,
            request={"messages": [{"role": "user", "content": "book me a flight",
                                   "provenance": "typed"}],
                     "conversation_id": "c1"})
        check(f"with a grant live, {tool} still raises its OWN card ({want})",
              gate.actions() == [want], gate.actions())
        check(f"... and {tool} did not run", runs == [], runs)


# --------------------------------------------------------------------------
#   5. Conversation A's grant does not cover conversation B
# --------------------------------------------------------------------------

def t_conversation_a_does_not_cover_conversation_b():
    if GATE is None:
        skip("jarvis_gate.py is not here, so no grant can be created")
        return
    runs = reset()
    _grant_now(cid="chat-a", runs=runs)
    check("CONTROL: chat-a's grant is live",
          AG.web_search_grant("chat-a") is not None)
    gate = Gate(default=DENIED)
    told = _search_in(cid="chat-b", gate=gate, runs=runs, tainted=True)
    check("a search in chat-b still asks: chat-a's grant does not reach it",
          gate.actions() == [WS.ACTION_SEARCH], gate.actions())
    check("... and nothing was sent from chat-b", runs == [], runs)
    check("... and chat-b has no grant of its own",
          AG.web_search_grant("chat-b") is None)
    check("... while chat-a's is still there, untouched",
          AG.web_search_grant("chat-a") is not None)
    # A request with NO conversation id can neither give nor use one.
    runs = reset()
    gate = Gate()
    AG._conversation_tainted = lambda c, messages=None: False
    WS.run = _fake_run(runs)
    model = Model([[(AG.GRANT_TOOL, {})], []])
    AG.run_local_turn(
        [{"role": "user", "content": "full approval to search"}], "m",
        ollama_url="http://127.0.0.1:11434", stream_out=lambda b: None,
        post=model.post, gate_check=gate, enabled_tools={AG.GRANT_TOOL},
        record_chain=lambda s: None, context_length=8192,
        request={"messages": [{"role": "user", "content": "full approval to search",
                               "provenance": "typed"}]})
    check("a chat with NO conversation id: refused with no card at all "
          "(a grant that cannot be limited to one chat is not granted)",
          gate.actions() == [] and "conversation id" in _said(model.told()),
          (gate.actions(), _said(model.told())[:200]))
    check("... and no grant was stored anywhere",
          all(AG.web_search_grant(cid) is None
              for cid in ("", None, "None", "chat-a")))
    _ = told


# --------------------------------------------------------------------------
#   6. Revocation: instant, logged, idempotent
# --------------------------------------------------------------------------

def t_revocation_is_instant_and_idempotent():
    if GATE is None:
        skip("jarvis_gate.py is not here, so no grant can be created")
        return
    runs = reset()
    _grant_now(runs=runs)
    grant = AG.web_search_grant("c1")
    check("CONTROL: the grant is live", bool(grant))
    # The owner says "you don't have approval to search any more". The model
    # calls the stop tool: tier "auto", so NO card is raised.
    gate = Gate()
    model, told, _summary = _turn(tool_calls=[(AG.REVOKE_TOOL, {})], gate=gate,
                                  runs=runs, enabled={AG.REVOKE_TOOL})
    check("saying stop raises NO card (tier `auto`, instant)",
          gate.actions() == [], gate.actions())
    check("... the grant is gone at once", AG.web_search_grant("c1") is None)
    ended = audit_events("gate.grant_ended")
    check("... and the log says it ended, with the id and why",
          len(ended) == 1 and ended[0]["detail"].get("grant") == grant["grant_id"]
          and ended[0]["detail"].get("state") == "revoked", ended)
    check("... and the model is told searches will ask again",
          "ask" in _said(told).lower() and "Approval stopped" in _said(told),
          _said(told)[:300])
    # The very next search asks again.
    gate2 = Gate(default=DENIED)
    _search_in(gate=gate2, runs=runs, tainted=True)
    check("the next search in that chat asks again",
          gate2.actions() == [WS.ACTION_SEARCH], gate2.actions())
    # Stopping again is harmless, and does not pretend it stopped something.
    gate3 = Gate()
    model3, told3, _s = _turn(tool_calls=[(AG.REVOKE_TOOL, {})], gate=gate3,
                              runs=runs, enabled={AG.REVOKE_TOOL})
    check("stopping again raises no card and says there was nothing to stop",
          gate3.actions() == [] and "nothing changed" in _said(told3).lower(),
          (gate3.actions(), _said(told3)[:200]))
    check("... and it wrote no second `gate.grant_ended` line",
          len(audit_events("gate.grant_ended")) == 1,
          audit_events("gate.grant_ended"))


# --------------------------------------------------------------------------
#   7. The cap, a restart, and a new chat
# --------------------------------------------------------------------------

def t_the_cap_a_restart_and_a_new_chat_end_it():
    if GATE is None:
        skip("jarvis_gate.py is not here, so no grant can be created")
        return
    runs = reset()
    _grant_now(runs=runs)
    grant = AG.web_search_grant("c1")
    check("CONTROL: the grant is live, and its cap is 8 hours",
          bool(grant) and AG.GRANT_TTL_SECONDS == 8 * 60 * 60,
          AG.GRANT_TTL_SECONDS)
    # The cap: push the stored expiry into the past and look again - exactly
    # what eight hours of a long conversation does.
    AG._GRANTS["c1"]["expires_at"] = 1.0
    check("past its cap the grant is gone the moment it is looked at",
          AG.web_search_grant("c1") is None)
    expired = [row for row in audit_events("gate.grant_ended")
               if row["detail"].get("state") == "expired"]
    check("... and the log says `expired`, with the id",
          len(expired) == 1 and expired[0]["detail"].get("grant") == grant["grant_id"],
          expired)
    gate = Gate(default=DENIED)
    _search_in(gate=gate, runs=runs, tainted=True)
    check("... and the next search asks again", gate.actions() == [WS.ACTION_SEARCH],
          gate.actions())
    # A restart: the store starts empty in a new process. `_GRANTS.clear()` is
    # what that looks like from inside one, and nothing else is needed because
    # nothing was ever written to disk.
    runs = reset()
    _grant_now(runs=runs)
    check("CONTROL: a fresh grant, live", AG.web_search_grant("c1") is not None)
    AG._GRANTS.clear()
    check("a restart forgets it: the grant lives only in this process's memory",
          AG.web_search_grant("c1") is None)
    gate = Gate(default=DENIED)
    _search_in(gate=gate, runs=runs, tainted=True)
    check("... and after a restart the search asks again",
          gate.actions() == [WS.ACTION_SEARCH], gate.actions())
    # A new chat is clean: no grant, and no cap leftover from another chat.
    check("a new chat starts clean (no grant is invented for it)",
          AG.web_search_grant("brand-new-chat") is None)


# --------------------------------------------------------------------------
#   8. "Book a flight for me" still raises its own card
# --------------------------------------------------------------------------

def t_booking_a_flight_still_asks():
    if GATE is None:
        skip("jarvis_gate.py is not here, so no grant can be created")
        return
    runs = reset()
    _grant_now(runs=runs)
    check("CONTROL: the grant is live",
          AG.web_search_grant("c1") is not None)
    # "Book a flight for me online" is not a search: it is clicking and typing
    # in a program (control_computer) or working a web page (browser_control),
    # and it sends/commits something that cannot be taken back.
    gate = Gate(default=DENIED)
    model = Model([[("control_computer",
                     {"goal": "book a flight",
                      "window": "Booking - Chrome",
                      "requests": [{"control": "Pay now", "action": "click",
                                    "irreversible": True, "leaves_machine": True}]})], []])
    AG._conversation_tainted = lambda c, messages=None: False
    WS.run = _fake_run(runs)
    summary = AG.run_local_turn(
        [{"role": "user", "content": "book me a flight online"}], "m",
        ollama_url="http://127.0.0.1:11434", stream_out=lambda b: None,
        post=model.post, gate_check=gate, enabled_tools={"control_computer"},
        record_chain=lambda s: None, context_length=8192,
        request={"messages": [{"role": "user", "content": "book me a flight online",
                               "provenance": "typed"}], "conversation_id": "c1"})
    check("with a grant live, 'book a flight' raises its OWN card (control_computer)",
          gate.actions() == ["control_computer"], (gate.actions(), _said(model.told())[:200]))
    check("... denied: nothing was clicked, and the model is told it was refused",
          "refused" in _said(model.told()) and summary.get("tools_ran") == [],
          (_said(model.told())[:300], summary.get("tools_ran")))
    check("... and the browser tool, the other way to book something, still asks "
          "too: its tier is 'ask' in the real table (it is not offered here at all "
          "without the second-card lane, so its card is proved by the table)",
          GATE._tiers().get("control_browser") == "ask",
          GATE._tiers().get("control_browser"))
    check("... and the grant is untouched by any of it",
          AG.web_search_grant("c1") is not None)


# --------------------------------------------------------------------------
#   9. Open-ended words grant search only
# --------------------------------------------------------------------------

def t_open_ended_words_grant_search_only():
    if GATE is None:
        skip("jarvis_gate.py is not here, so no grant can be created")
        return
    runs = reset()
    gate = Gate()
    model = Model([[(AG.GRANT_TOOL, {})], []])
    AG._conversation_tainted = lambda c, messages=None: False
    WS.run = _fake_run(runs)
    AG.run_local_turn(
        [{"role": "user", "content": "you have full approval to do anything you "
                                     "need in this conversation, including "
                                     "searching the web"}],
        "m", ollama_url="http://127.0.0.1:11434", stream_out=lambda b: None,
        post=model.post, gate_check=gate, enabled_tools={AG.GRANT_TOOL},
        record_chain=lambda s: None, context_length=8192,
        request={"messages": [{"role": "user", "content":
                               "you have full approval to do anything you need "
                               "in this conversation, including searching the web",
                               "provenance": "typed"}],
                 "conversation_id": "c1"})
    text = gate.calls[0]["detail"]["text"] if gate.calls else ""
    check("an open-ended 'full approval to do anything' asks for ONE card, and it "
          "is the web-search one", gate.actions() == [AG.GRANT_ACTION], gate.actions())
    check("... the card says search only: it names web searches as what is allowed",
          "web search" in text.lower(), text[:300])
    check("... and says plainly that nothing else is covered, naming the things "
          "the owner might mean",
          "Nothing else is covered" in text
          and all(word in text for word in
                  ("email", "buying", "spending", "deleting", "command",
                   "setting", "browser", "accounts", "phone")), text[:600])
    check("... and says it can never widen to them, whatever the words were",
          "never widen" in text, text[:600])
    check("... and says exactly how to stop it",
          "stop searching without asking" in text and "revoke that" in text,
          text[:600])
    check("... and how long it lasts, and that it is capped",
          "when this chat ends" in text and "after 8 hours" in text, text[:600])
    check("... and that Lockdown still asks", "Lockdown still asks" in text,
          text[:600])
    # The scope is fixed by the ACTION, not by the words: nothing but
    # `search_the_web` is ever handed a grant, whatever was said.
    grant = AG.web_search_grant("c1")
    check("CONTROL: the open-ended words produced a grant", bool(grant))
    gate2 = Gate(default=DENIED)
    model2 = Model([[("shell_exec", {"command": "echo hi"})], []])
    AG.run_local_turn(
        [{"role": "user", "content": "and do anything else too"}], "m",
        ollama_url="http://127.0.0.1:11434", stream_out=lambda b: None,
        post=model2.post, gate_check=gate2, enabled_tools={"shell_exec"},
        record_chain=lambda s: None, context_length=8192,
        request={"messages": [{"role": "user", "content": "and do anything else too",
                               "provenance": "typed"}], "conversation_id": "c1"})
    check("... and under those same open-ended words, a shell command still asks",
          gate2.actions() == ["run_shell_on_host"], gate2.actions())
    # A second request while one is live never becomes a second card.
    gate3 = Gate()
    model3 = Model([[(AG.GRANT_TOOL, {})], []])
    AG.run_local_turn(
        [{"role": "user", "content": "yes, full approval"}], "m",
        ollama_url="http://127.0.0.1:11434", stream_out=lambda b: None,
        post=model3.post, gate_check=gate3, enabled_tools={AG.GRANT_TOOL},
        record_chain=lambda s: None, context_length=8192,
        request={"messages": [{"role": "user", "content": "yes, full approval",
                               "provenance": "typed"}],
                 "conversation_id": "c1"})
    check("asking again while one is live raises no second card, and changes "
          "nothing", gate3.calls == [] and AG.web_search_grant("c1") == grant,
          (gate3.actions(), AG.web_search_grant("c1") == grant))


# --------------------------------------------------------------------------
#   10. The field test of 2026-11-02: a natural request reaches the tool, and a
#       grant the store does not hold can never be claimed
# --------------------------------------------------------------------------
#
# THE FAILURE THIS SECTION FIXES, measured on the owner's PC after #1074:
#
#   "Give me full approval to search the web for this conversation." and
#   "Approve web search for this conversation, so you can search without asking
#   me each time in this chat." both produced NO grant card at all, and the
#   model answered "Understood. Search is approved for this conversation.
#   Ready to check the web whenever needed." The next search raised an ordinary
#   search_the_web card, so nothing had been granted.
#
# Cause, measured in this tree: the grant tool was not in the live
# `[tools].enabled` (it was never a fresh-install default), and `offered_tools`
# offers only names in that set - so the model had no tool to call, no card
# could ever be raised, and nothing in the prompt said whether an approval was
# in force. The fixes these checks pin: the two tools ride with web search, the
# prompt carries a real store read when a grant IS in force, and an answer that
# claims one the store does not hold is corrected in plain words.

#: The field test's own answer, word for word, from the failing turn.
FIELD_TEST_ANSWER = ("Understood. Search is approved for this conversation. "
                     "Ready to check the web whenever needed.")


def t_a_natural_request_reaches_the_grant_tool():
    """The offer is the fix: the two tools are offered on the tools a real PC
    has, even though `[tools].enabled` never names them."""
    if GATE is None:
        skip("jarvis_gate.py is not here, so no grant card can be raised")
        return
    reset()
    enabled = AG.enabled_tools_for_turn()
    check("the settings list really does NOT name the grant tools (the old cause: "
          "they were never a default)",
          AG.GRANT_TOOL not in enabled and AG.REVOKE_TOOL not in enabled, sorted(enabled))
    offered = AG.offered_tools(enabled)
    check("... and yet a real turn OFFERS the grant tool, because the ask rides with "
          "web search", AG.GRANT_TOOL in offered, offered)
    check("... and its instant stop with it", AG.REVOKE_TOOL in offered, offered)
    check("... and web search itself is offered (the one condition)",
          "web_search" in offered, offered)
    check("... with web search NOT offered, neither is the ask",
          not (set(AG.GRANT_ASK_TOOLS) & set(AG.offered_tools(
              set(enabled) - {"web_search"}))))
    check("... and the Settings page no longer offers a switch for them (a switch "
          "the turn ignored would be a lie)",
          not (set(AG.GRANT_ASK_TOOLS) & set(AF.TOOLS_SWITCHABLE)),
          sorted(set(AG.GRANT_ASK_TOOLS) & set(AF.TOOLS_SWITCHABLE)))
    check("... and the two modules name the same pair, so they cannot drift",
          tuple(AF.GRANT_ASK_TOOLS) == tuple(AG.GRANT_ASK_TOOLS),
          (AF.GRANT_ASK_TOOLS, AG.GRANT_ASK_TOOLS))
    # The field test's own two sentences, on the offer a real turn has.
    for words in ("Give me full approval to search the web for this conversation.",
                  "Approve web search for this conversation, so you can search without "
                  "asking me each time in this chat."):
        runs = reset()
        gate = Gate()
        _turn(tool_calls=[(AG.GRANT_TOOL, {})], gate=gate, runs=runs,
              enabled=offered, strict=True, words=words)
        check(f"natural words raise EXACTLY ONE grant card: {words[:38]!r}...",
              gate.actions() == [AG.GRANT_ACTION], (gate.actions(), words))
        check("... and the card was approved into a real grant",
              AG.web_search_grant("c1") is not None)
        gate2 = Gate()
        _search_in(gate=gate2, runs=runs, tainted=True)
        check("... and a search in that conversation then runs with NO card",
              gate2.actions() == [] and runs == ["walking boots"],
              (gate2.actions(), runs))
    reset()


def t_the_model_cannot_claim_a_grant_it_does_not_have():
    """The field test's false "Search is approved": corrected from a real store
    read, and NOT corrected when a real grant makes it true."""
    if GATE is None:
        skip("jarvis_gate.py is not here, so no grant can be checked")
        return
    runs = reset()
    gate = Gate()
    _model, _told, summary = _turn(
        tool_calls=[], gate=gate, runs=runs, answer=FIELD_TEST_ANSWER,
        words="Give me full approval to search the web for this conversation.")
    answer = str(summary.get("answer") or "")
    check("CONTROL: the field test's answer was really sent", FIELD_TEST_ANSWER in answer,
          answer[:200])
    check("... with no card raised and NO grant created",
          gate.calls == [] and AG.web_search_grant("c1") is None,
          (gate.actions(), AG.web_search_grant("c1")))
    check("... and the answer is CORRECTED in plain words: no approval is in force",
          "no web-search approval is in force" in answer.lower(), answer[-400:])
    check("... and the correction says how to get one",
          "give me full approval to search the web for this conversation" in answer.lower(),
          answer[-400:])
    # CONTROL: a real grant makes the same words true, so nothing is added.
    runs = reset()
    _grant_now(runs=runs)
    check("CONTROL: a real grant is live", AG.web_search_grant("c1") is not None)
    _m2, _t2, summary2 = _turn(tool_calls=[], gate=Gate(), runs=runs,
                               answer=FIELD_TEST_ANSWER)
    check("... the same words are true now and are NOT corrected",
          "no web-search approval is in force" not in str(summary2.get("answer") or "").lower(),
          str(summary2.get("answer") or "")[-300:])
    # An honest denial, a conditional, a reported-speech echo and a promise are
    # sentences this must never touch.
    for honest in (
            "There is no web-search approval in force in this chat, so every search asks.",
            "If you approve the card, search is approved for this chat.",
            "You said you have full approval to search the web, so searches still ask.",
            "I don't have approval to search yet - just the card waiting for you."):
        reset()
        _m3, _t3, s3 = _turn(tool_calls=[], gate=Gate(), runs=[], answer=honest)
        check(f"an honest sentence is NOT corrected: {honest[:34]!r}...",
              "Correction" not in str(s3.get("answer") or ""),
              str(s3.get("answer") or "")[-300:])
    reset()


def t_the_prompt_state_is_a_real_read():
    """The only signal that tells the model a grant is in force is the store."""
    if GATE is None:
        skip("jarvis_gate.py is not here, so no grant can be checked")
        return
    runs = reset()
    check("no grant: the prompt carries NO state line at all (0 tokens)",
          AG._grant_prompt_line("c1") == "")
    _grant_now(runs=runs)
    line = AG._grant_prompt_line("c1")
    check("a grant: the prompt line says so, and it is this feature's own sentence",
          line == AG.WEB_SEARCH_GRANT_IN_FORCE and "IS in force" in line, line)
    check("... another chat gets nothing (the read is per conversation)",
          AG._grant_prompt_line("c2") == "")
    _m, _told, _s = _turn(tool_calls=[], gate=Gate(), runs=runs)
    sent = [m.get("content") for m in (_m.sent[-1].get("messages") or [])
            if isinstance(m, dict) and m.get("role") == "system"]
    check("... and a real turn SENDS it to the model as a system message",
          AG.WEB_SEARCH_GRANT_IN_FORCE in sent, sent)
    check("... and the rules are still the first message",
          bool(_m.sent[-1].get("messages")) and
          _m.sent[-1]["messages"][0].get("content") == AG.LANE_SYSTEM)
    # After the owner says stop, the line is gone on the next turn.
    _turn(tool_calls=[(AG.REVOKE_TOOL, {})], gate=Gate(), runs=runs,
          enabled={AG.REVOKE_TOOL})
    check("... and after a stop the prompt line is gone at once",
          AG.web_search_grant("c1") is None and AG._grant_prompt_line("c1") == "")
    _m2, _t2, _s2 = _turn(tool_calls=[], gate=Gate(), runs=runs)
    sent2 = [m.get("content") for m in (_m2.sent[-1].get("messages") or [])
             if isinstance(m, dict) and m.get("role") == "system"]
    check("... and the next turn carries no state line again",
          AG.WEB_SEARCH_GRANT_IN_FORCE not in sent2)
    # The rules paragraph is in the shipped prompt, so the model is told plainly
    # not to claim an approval before one happens.
    check("the rules say an approval is not the model's to give or assume",
          "An approval is not yours to give or to assume" in AG.LANE_SYSTEM)
    check("... and that only a tool result can say one is in place",
          "unless a tool result in this conversation told you so" in AG.LANE_SYSTEM)
    check("the grant tool's own text says it too",
          "Never say it is on before a person answers the card" in AG._grant_tool_text())
    reset()


# --------------------------------------------------------------------------
#   The delivery: the patch, the two settings copies, the base's rows
# --------------------------------------------------------------------------

def t_the_patch_and_the_tables():
    import subprocess

    patch = REPO / "backend" / "web-search-grant.patch"
    base = REPO / "jarvis-backend" / "jarvis_gate.py"
    if not patch.is_file() or not base.is_file():
        skip("the patch or the published base is not in this checkout")
        return
    text = patch.read_text(encoding="utf-8")
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    entry = "'web-search-grant.patch'"
    tail = ps1.split(entry, 1)[1] if entry in ps1 else ""
    after = [ln.strip() for ln in tail.splitlines() if ln.strip().startswith("'")]
    check("the patch is in the stack BEFORE unknown-risk-approvable.patch "
          "(whose guard requires that patch to stay the LAST writer of "
          "jarvis_gate.py, so this one may not sit after it), with only "
          "github-tools.patch between them - it anchors on this patch's own "
          "trailing block, which is why it must follow it)",
          after[:2] == ["'github-tools.patch'", "'unknown-risk-approvable.patch'"],
          f"not found in apply-patches.ps1, or the entries after it are {after[:2]!r}")
    check("its header is the bare `a/`/`b/` form every patch here uses",
          text.startswith("--- a/jarvis_gate.py\n+++ b/jarvis_gate.py\n@@"), text[:80])
    work = Path(tempfile.mkdtemp(prefix="jarvis-wsgrant-patch-"))
    try:
        copy = work / "jarvis_gate.py"
        copy.write_bytes(base.read_bytes())
        arg = ["git", "-c", "core.autocrlf=false", "apply"]
        back = subprocess.run(arg + ["-R", str(patch)], cwd=work,
                              capture_output=True, text=True)
        check("the patch REVERSES out of the published base cleanly",
              back.returncode == 0, (back.returncode, back.stderr[:300]))
        pre = copy.read_bytes()
        check("... and the result is not the base any more (it really removed "
              "something)", pre != base.read_bytes())
        fwd = subprocess.run(arg + [str(patch)], cwd=work,
                             capture_output=True, text=True)
        check("... and applies forwards again, byte for byte",
              fwd.returncode == 0 and copy.read_bytes() == base.read_bytes(),
              (fwd.returncode, fwd.stderr[:300]))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    check("the published base has both `_RISK` rows this patch adds",
          '"grant_web_search_conversation": ("yes", "outbound"' in base.read_text(encoding="utf-8")
          and '"revoke_web_search_grant": ("yes", "local"' in base.read_text(encoding="utf-8"))
    check("... and the three audit writers, as ordinary functions",
          all(f"\ndef {n}(" in base.read_text(encoding="utf-8")
              for n in ("grant_made", "granted", "grant_ended")))
    # Both shipped settings copies, both tier lines, and the values that make
    # the feature work: "ask" for the card, "auto" for the instant stop.
    for path in (REPO / "backend" / "rebuilt" / "jarvis-framework.toml",
                 REPO / "jarvis-backend" / "jarvis-framework.toml"):
        if not path.is_file():
            skip(f"{path} is not in this checkout")
            continue
        body = path.read_text(encoding="utf-8")
        check(f"{path.parent.name}/{path.name}: grant tier is 'ask'",
              'grant_web_search_conversation             = "ask"' in body)
        check(f"{path.parent.name}/{path.name}: revoke tier is 'auto' (no card "
              f"to stop)", 'revoke_web_search_grant                   = "auto"' in body)
    check("both settings copies are the same file (the two-file rule)",
          (REPO / "backend" / "rebuilt" / "jarvis-framework.toml").read_bytes()
          == (REPO / "jarvis-backend" / "jarvis-framework.toml").read_bytes())
    # The card's words are in the one place both apps word a card from.
    if GATE is not None:
        try:
            import jarvis_card_words as W
            check("both new actions have a plain title",
                  W.title_for(AG.GRANT_ACTION).startswith("Jarvis wants to")
                  and "_" not in W.title_for(AG.GRANT_ACTION)
                  and W.title_for(AG.REVOKE_ACTION).startswith("Jarvis wants to"),
                  (W.title_for(AG.GRANT_ACTION), W.title_for(AG.REVOKE_ACTION)))
            check("... and a short summary of its own (the owner's one-line card: "
                  "the written row, inside the word cap)",
                  bool(W.SUMMARY.get(AG.GRANT_ACTION))
                  and len(W.SUMMARY[AG.GRANT_ACTION].split()) <= W.SUMMARY_MAX_WORDS
                  and bool(W.SUMMARY.get(AG.REVOKE_ACTION))
                  and len(W.SUMMARY[AG.REVOKE_ACTION].split()) <= W.SUMMARY_MAX_WORDS
                  and W.summary_for(AG.GRANT_ACTION) ==
                  "Jarvis wants to " + W.SUMMARY[AG.GRANT_ACTION] + ".",
                  (W.SUMMARY.get(AG.GRANT_ACTION), W.summary_for(AG.GRANT_ACTION)))
        except Exception as exc:                          # noqa: BLE001
            skip(f"jarvis_card_words could not be read ({type(exc).__name__})")
    if GATE is not None:
        risky = GATE.risk_for(AG.GRANT_ACTION)
        check("the grant's card is a risky one: outbound, so a lock screen "
              "cannot swipe it through",
              risky["reach"] == "outbound" and risky["swipe_ok"] is False, risky)
        check("... and it is reversible: saying stop undoes it at once",
              risky["reversible"] == "yes", risky)
        stop = GATE.risk_for(AG.REVOKE_ACTION)
        check("the stop's own row says it stays on this PC and asks for nothing",
              stop["reach"] == "local" and stop["classified"] is True, stop)


if __name__ == "__main__":
    print(f"  file  {_base.which(HERE, 'jarvis_agent.py')}")
    if GATE is not None:
        print(f"  file  {_base.which(GATE_FOLDER, 'jarvis_gate.py')}")
    print(f"  logs  {FW.log_dir()}")
    for fn in (t_no_card_then_no_grant,
               t_one_card_and_a_denial_grants_nothing,
               t_an_approved_grant_runs_the_search_and_logs_it,
               t_the_grant_covers_no_other_action,
               t_conversation_a_does_not_cover_conversation_b,
               t_revocation_is_instant_and_idempotent,
               t_the_cap_a_restart_and_a_new_chat_end_it,
               t_booking_a_flight_still_asks,
               t_open_ended_words_grant_search_only,
               t_a_natural_request_reaches_the_grant_tool,
               t_the_model_cannot_claim_a_grant_it_does_not_have,
               t_the_prompt_state_is_a_real_read,
               t_the_patch_and_the_tables):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
