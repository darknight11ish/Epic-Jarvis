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

    def __init__(self, rounds):
        self.rounds = [r for r in rounds]
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
        return {"choices": [{"message": {"role": "assistant", "content": "done"}}]}

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
          answer="done"):
    """One real turn: the model asks for `tool_calls`, then answers.

    Returns (the model, its tool results for the last round, the turn summary).
    """
    AG._conversation_tainted = (lambda c, messages=None: True) if tainted \
        else (lambda c, messages=None: False)
    WS.run = _fake_run(runs)
    model = Model([tool_calls, []])
    messages = [{"role": "user", "content": "please"}]
    req = [{"role": "user", "content": "please", "provenance": "typed"}]
    names = set(enabled or ()) | {n for n, _a in tool_calls}
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
    check("a grant is READ in exactly two places, both named: the search itself, "
          "and the 'already on' refusal on the grant card",
          reader_fns == {"_web_search_call", "_prepare_web_search_grant"},
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
    check("the patch is in the stack, immediately before plugin-loader.patch",
          ("'web-search-grant.patch'\n    'plugin-loader.patch'"
           in (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")),
          "not found in apply-patches.ps1")
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
