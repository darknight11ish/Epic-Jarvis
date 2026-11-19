"""test_project_chat.py - a chat can belong to a project (2026-11-19).

    python -B backend/test_project_chat.py

WHAT THIS SUITE EXISTS FOR. docs/PROJECTS-DESIGN.md's build notes say the
other half of step 4 - "a fact learned in a project chat being labelled by
itself ... waits for /api/chat to carry a project id". `docs/JARVIS-API.md`
section 88 says the same, twice. This suite covers the lane that carries it:

  * the request body may name a project (`project`: its id, or its own name,
    resolved by the store's own lookup - never guessed);
  * a turn with NO project is every caller that existed before it: the same
    answer, the same route header, byte for byte - the CONTROL checks below
    prove nothing leaked into an ordinary turn;
  * a project-scoped turn gets that project's own context (instructions,
    pinned notes, work list, open goal steps, non-private benchmark numbers)
    and none of another project's;
  * the remembered facts a scoped turn may use are the unlabelled personal
    ones plus THIS project's own labelled facts - a fact labelled to another
    project is dropped, and a turn that may leave the PC gets none at all
    (rule 1: its own pinned-notes-and-context slice is read-only);
  * "what's next on this project" is a READ that names the stores and the date
    it read, then the real work-list items, open goals, steps and due
    benchmarks; "log N against <benchmark>" is ONE card and writes nothing
    until a person says yes, and a benchmark of another project never gets it;
  * a goal step's existing `measure` (budget 2026-09-30, JARVIS-API section
    101) is what the project read reports - NO schema change, NO new route,
    because that item was already built when section 88 still said otherwise.

Every fixture is a temporary folder (`JARVIS_PROJECTS_DB`, `JARVIS_GOALS_DB`,
`JARVIS_SCHEDULE_DB`, the config dir), no model runs, no socket opens, and
nothing in the owner's ~/.openjarvis is read or written. The approval gate,
its tier and its spawn are fakes: an answer that raises a real card fails.
"""
from __future__ import annotations

import ast
import functools
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

# The live install's copy is older than this branch until the deploy pass, and
# `_where` would put it on sys.path first. This suite is about the repository's
# own code, so the ambient install is ignored (CI never sets it).
os.environ.pop("JARVIS_BACKEND", None)
os.environ.pop("OLLAMA_URL", None)

_TMP = Path(tempfile.gettempdir()) / ("jarvis-project-chat-" + secrets.token_hex(6))
_CFG = _TMP / "config"
_CFG.mkdir(parents=True, exist_ok=True)
for _n in ("JARVIS_CONFIG_DIR", "OPENJARVIS_CONFIG_DIR"):
    os.environ[_n] = str(_CFG)
os.environ["JARVIS_PROJECTS_DB"] = str(_CFG / "projects.db")
os.environ["JARVIS_GOALS_DB"] = str(_CFG / "goals.db")
os.environ["JARVIS_SCHEDULE_DB"] = str(_CFG / "schedule.db")
os.environ["JARVIS_MEMORY_K"] = "5"

import jarvis_goals as G  # noqa: E402
import jarvis_projects as P  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_schedule as S  # noqa: E402

FAILED, PASSED = [], []


@functools.lru_cache(maxsize=1)
def _hud() -> tuple:
    """The HUD as an AST plus a parent map - never as source text to pin.

    `tools/check_no_source_pins.py` is the ratchet against a test comparing a
    literal with a module's source text; it cannot go red because a comment
    changed, but it can also be answered faster. Structural questions ("is
    this call inside that if?", "does this dict say role=system?") are walked
    on the tree instead, which is what that checker's own docstring asks for.
    """
    tree = ast.parse((REPO / "jarvis-backend" / "jarvis_hud.py")
                     .read_text(encoding="utf-8"))
    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    return tree, parent


def _call_name(call: ast.Call) -> str:
    try:
        return ast.unparse(call.func)
    except Exception:                               # noqa: BLE001 - not a name
        return ""


def _calls(name: str) -> list:
    tree, _ = _hud()
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and _call_name(n).endswith(name)]


def _parents(node) -> list:
    _, parent = _hud()
    out = []
    while node in parent:
        node = parent[node]
        out.append(node)
    return out


def _enclosed_by(node, *words) -> bool:
    """Is `node` inside an ast.If whose test mentions every one of `words`?"""
    for p in _parents(node):
        if isinstance(p, ast.If):
            test = ast.unparse(p.test)
            if all(w in test for w in words):
                return True
    return False


def _guarded_by(node, *words) -> bool:
    """Is `node` inside ast.If tests that mention every word, in any nesting?"""
    seen = set()
    for p in _parents(node):
        if isinstance(p, ast.If):
            test = ast.unparse(p.test)
            seen.update(w for w in words if w in test)
    return seen == set(words)


def _route_header_assigns(key: str) -> list:
    tree, _ = _hud()
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Assign):
            continue
        for target in n.targets:
            if (isinstance(target, ast.Subscript)
                    and ast.unparse(target.value) == "route_header"
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value == key):
                out.append(n)
    return out

#: Fixed so the read-date half of "what's next" is checked exactly.
NOW = datetime(2026, 11, 19, 12, 0).timestamp()
DATE = "2026-11-19"


def check(label: str, ok: bool, detail="") -> None:
    if ok:
        PASSED.append(label)
        print("  ok    " + label)
    else:
        FAILED.append(label)
        print("  FAIL  " + label)
        if detail:
            print("          " + str(detail)[:500])


class Sched:
    """A made-up scheduler: a card or a write from a read-only answer fails."""

    def __init__(self):
        self.commands = []

    def mark_command(self, text):
        self.commands.append(text)

    def note_set(self, *a, **k):
        return None

    def forget_set(self, *a, **k):
        return None

    def act(self, *a, **k):
        raise AssertionError("a card was raised by a read-only answer")


class Verdict:
    def __init__(self, allowed=True, outcome="approved", tier="ask"):
        self.allowed = allowed
        self.outcome = outcome
        self.tier = tier
        self.reason = ""
        self.request_id = None


def _fresh():
    """One empty project/goal/schedule store, and no singleton keeps an old one."""
    for name in ("projects.db", "goals.db", "schedule.db"):
        for suffix in ("", "-wal", "-shm"):
            p = _CFG / (name + suffix)
            if p.exists():
                p.unlink()
    P._reset_for_tests()
    G._reset_for_tests()
    S._SCHED = None


def _body(text, project=None, provenance="typed"):
    msg = {"role": "user", "content": text}
    if provenance:
        msg["provenance"] = provenance
    body = {"messages": [msg]}
    if project is not None:
        body["project"] = project
    return body


def _ask(text, project=None, now=NOW, provenance="typed"):
    return Q.answer_turn(_body(text, project, provenance), sched=Sched(), now=now)


def _make_project(name="Kestrel Trip", notes=None, instructions="", kind="life"):
    return P.get().create({"name": name, "kind": kind,
                           "notes": notes or [], "instructions": instructions},
                          here=True)


def _add_bench(pid, name, *, unit="", better="higher", target=None):
    return P.get().add_benchmark(pid, {"name": name, "kind": "number", "unit": unit,
                                       "better": better, "target": target}, here=True)


# --------------------------------------------------------------------------
#   1. A scoped turn answers with THAT project's own context, and only it
# --------------------------------------------------------------------------

def t_scoped_turn_uses_the_projects_own_notes_and_headers():
    _fresh()
    a = _make_project("Kestrel Trip", notes=["the server uses port 8080",
                                             "bring the blue folder"],
                      instructions="always check the weather before the drive")
    b = _make_project("Falcon Trip", notes=["bills due on the first"])
    _add_bench(a["id"], "launch checklist")
    _add_bench(b["id"], "budget review")

    pa = Q.project_prompt(P.chat_scope({"project": a["id"]}))
    pb = Q.project_prompt(P.chat_scope({"project": b["id"]}))
    check("the prompt carries the project's own instructions",
          "always check the weather" in pa, pa[:300])
    check("the prompt carries the project's own pinned notes",
          "port 8080" in pa and "blue folder" in pa)
    check("the prompt does NOT carry the other project's pinned note",
          "bills due on the first" not in pa)
    check("the other project's prompt carries its own note only",
          "bills due on the first" in pb and "port 8080" not in pb)

    got = _ask("what's next on this project", project=a["id"])
    check("a scoped 'what's next' is answered here, not by the model",
          got is not None and got.intent == "project_next", repr(got))
    if got is None:
        return
    fields = Q.route_fields(got)
    check("the route header says which project the answer was scoped to",
          fields.get("project") == {"id": a["id"], "name": "Kestrel Trip"}, repr(fields))
    check("the answer names this project's own due benchmark",
          "launch checklist" in got.reply, got.reply[:400])
    check("... and never the other project's benchmark",
          "budget review" not in got.reply)

    # Resolved by the project's NAME too - the store's own lookup, the same
    # answer, and a name in any case: never a prefix, never a guess.
    by_name = P.chat_scope({"project": "Kestrel Trip"})
    by_case = P.chat_scope({"project": "kestrel trip"})
    check("a project resolves by its own name",
          by_name["ok"] and by_name["id"] == a["id"], repr(by_name))
    check("... case and spacing ignored, like the store's own uniqueness rule",
          by_case["ok"] and by_case["id"] == a["id"], repr(by_case))
    named = _ask("what's next on this project", project="Kestrel Trip")
    check("a name on the chat body answers exactly as the id does",
          named is not None and named.intent == "project_next")


# --------------------------------------------------------------------------
#   2. A project that does not exist is refused BY NAME, and nothing is written
# --------------------------------------------------------------------------

class FakeStore:
    """Two projects with ONE name: the store itself refuses that, but an edited
    database could hold it - and resolve_ref must refuse, never pick one."""

    def __init__(self, rows):
        self.rows = rows

    def list(self):
        return [{"id": pid, "name": name} for pid, name in self.rows]

    def get(self, pid):
        return {"id": pid, "name": dict(self.rows)[pid]}


def t_unknown_project_refused_by_name_and_nothing_written():
    _fresh()
    a = _make_project("Kestrel Trip")
    _add_bench(a["id"], "launch checklist")
    before = {"projects": len(P.get().list()),
              "benchmarks": len(P.get().get(a["id"])["benchmark_list"]),
              "results": len(P.get().results(a["id"],
                                            P.get().get(a["id"])["benchmark_list"][0]["id"])
                            ["points"])}

    got = _ask("what's next on this project", project="Ghost Project")
    check("an unknown project is refused, not answered",
          got is not None and got.intent == "project_unknown", repr(got))
    if got is not None:
        check("the refusal names the project that was asked for",
              "Ghost Project" in got.reply, got.reply)
        check("... and says nothing was changed",
              "nothing was changed" in got.reply.lower(), got.reply)
    after = {"projects": len(P.get().list()),
             "benchmarks": len(P.get().get(a["id"])["benchmark_list"]),
             "results": len(P.get().results(a["id"],
                                           P.get().get(a["id"])["benchmark_list"][0]["id"])
                           ["points"])}
    check("nothing was written by the refusal", before == after, (before, after))

    bad_type = P.chat_scope({"project": 7})
    check("a project reference that is not text is refused in words",
          bad_type["given"] and not bad_type["ok"] and
          "id or its name" in bad_type["error"], repr(bad_type))

    two = FakeStore([("a" * 32, "Trip"), ("b" * 32, "Trip")])
    try:
        P.resolve_ref("Trip", store=two)
        refused = None
    except ValueError as exc:
        refused = str(exc)
    check("two projects with one name are refused, never one picked",
          refused is not None and "Trip" in refused and "b" * 32 in refused, refused)
    check("... and that refusal says nothing was changed",
          refused is not None and "nothing was changed" in refused.lower())

    # The HUD reads the same answer: a reference given but not resolved is a
    # 400 before the quick answer, the model or any write. Structural (ast),
    # not a source-text pin - see `_hud`'s docstring.
    tree, _ = _hud()
    send400 = [n for n in ast.walk(tree)
               if isinstance(n, ast.Return) and isinstance(n.value, ast.Call)
               and _call_name(n.value).endswith("self._send")
               and n.value.args and isinstance(n.value.args[0], ast.Constant)
               and n.value.args[0].value == 400]
    refused_here = [n for n in send400 if _enclosed_by(n, "_project.get", "given")]
    check("the HUD refuses a bad project with a 400 before the turn",
          bool(refused_here),
          [ast.unparse(n)[:120] for n in send400[:3]])

    # The project-scope resolver is called before the quick answer is even
    # tried: the HUD's own `_project = ...chat_scope(body)` line number is
    # smaller than the quick call's (both are real Calls in the tree).
    scope_calls = _calls("chat_scope")
    quick_calls = _calls("answer_turn")
    check("the HUD resolves the project before it asks the fast path",
          bool(scope_calls) and bool(quick_calls)
          and scope_calls[0].lineno < quick_calls[0].lineno,
          ([c.lineno for c in scope_calls], [c.lineno for c in quick_calls]))


# --------------------------------------------------------------------------
#   3. "log N against <benchmark>": ONE card, and another project never gets it
# --------------------------------------------------------------------------

def t_named_benchmark_log_is_carded_and_scoped():
    _fresh()
    a = _make_project("Kestrel Trip")
    b = _make_project("Falcon Trip")
    a_bench = _add_bench(a["id"], "tests", target=45)
    b_bench = _add_bench(b["id"], "tests", target=45)

    cards, spawned = [], []

    def gate(action, detail, prompt=""):
        cards.append({"action": action, "detail": detail, "prompt": prompt})
        return Verdict()

    def boom(*a, **k):
        raise AssertionError("a log card claim must not happen here")

    out = P.log_by_words(a["id"], "tests", 41, now=NOW, gate=gate,
                         tier_of=lambda action: "ask",
                         spawn=lambda fn: spawned.append(fn))
    check("a number said against a benchmark raises ONE card",
          out["ok"] is True and out["waiting"] is True, repr(out))
    check("... and the chat answer says nothing is logged until the yes",
          "Nothing is logged until you approve" in out["said"], out["said"])
    check("nothing is logged before the person answers",
          P.get().results(a["id"], a_bench["id"])["points"] == [] and
          P.get().results(b["id"], b_bench["id"])["points"] == [])
    check("the card has not been raised yet (it is the spawned thread's job)",
          cards == [] and len(spawned) == 1)
    if spawned:
        spawned[0]()
    check("the card names the project, the benchmark and the number",
          len(cards) == 1 and "Kestrel Trip" in cards[0]["prompt"] and
          "tests" in cards[0]["prompt"] and "41" in cards[0]["prompt"],
          repr(cards))
    a_points = P.get().results(a["id"], a_bench["id"])["points"]
    b_points = P.get().results(b["id"], b_bench["id"])["points"]
    check("an approved card writes the number, through the store's log",
          len(a_points) == 1 and a_points[0]["value"] == 41, repr(a_points))
    check("... and the OTHER project's identical benchmark never receives it",
          b_points == [], repr(b_points))

    # A benchmark that does not exist: refused in words, no card, no write.
    cards.clear()
    bad = P.log_by_words(a["id"], "no such benchmark", 3, now=NOW, gate=gate,
                         tier_of=lambda action: "ask",
                         spawn=lambda fn: spawned.append(fn))
    check("a benchmark that does not exist is refused, not guessed",
          bad["ok"] is False and "no such benchmark" in bad["said"].lower(),
          bad["said"])
    check("... and no card was raised and nothing was written",
          cards == [] and len(P.get().results(a["id"], a_bench["id"])["points"]) == 1)

    # Two benchmarks could match the words: refused, naming both.
    _add_bench(a["id"], "5k time", unit="min")
    _add_bench(a["id"], "5k pace", unit="min")
    amb = P.log_by_words(a["id"], "5k", 22, now=NOW, gate=gate,
                         tier_of=lambda action: "ask",
                         spawn=lambda fn: spawned.append(fn))
    check("two benchmarks matching the words are refused, not picked",
          amb["ok"] is False and "5k time" in amb["said"] and "5k pace" in amb["said"],
          amb["said"])

    # No card, no write: the tier rule. A "hard" tier is not a person's yes.
    never = P.log_by_words(a["id"], "tests", 42, now=NOW, gate=gate,
                           tier_of=lambda action: "auto",
                           spawn=lambda fn: spawned.append(fn))
    check("a tier that cannot be a person's yes refuses the write",
          never["ok"] is False and "nothing was logged" in never["said"].lower(),
          never["said"])
    check("... and nothing was written for it",
          len(P.get().results(a["id"], a_bench["id"])["points"]) == 1)

    # The chat path itself: the quick answer carries the card and stays private
    # for a health benchmark (kept on screen, never read aloud).
    _fresh()
    c = _make_project("Health")
    _add_bench(c["id"], "weight", unit="kg", better="lower", target=80)
    orig_gate, orig_tier, orig_spawn = P._gate, P._tier, P._spawn
    held = []
    try:
        P._gate = gate
        P._tier = lambda action: "ask"
        P._spawn = lambda fn: held.append(fn)
        got = _ask("log 72 against weight", project=c["id"])
    finally:
        P._gate, P._tier, P._spawn = orig_gate, orig_tier, orig_spawn
    check("the chat lane raises the card for a named benchmark",
          got is not None and got.intent == "project_benchmark_log", repr(got))
    check("a health number's answer is private: kept on screen, not read aloud",
          got is not None and got.private is True)
    check("the chat answer says the card is waiting",
          got is not None and "Nothing is logged until you approve" in got.reply,
          got.reply if got else "")
    if held:
        held[0]()


# --------------------------------------------------------------------------
#   4. "what's next on this project": names its stores and its date, and the
#      REAL work-list items, open goals, steps and due benchmarks
# --------------------------------------------------------------------------

def t_whats_next_names_its_stores_and_its_real_items():
    _fresh()
    proj = _make_project("garage")
    check("the project's default work list is its own name",
          proj["work_list"] == {"name": "garage", "title": "Garage list"},
          repr(proj["work_list"]))
    bench = _add_bench(proj["id"], "paint cans")
    sched = S.get()
    sched.add_todo("borrow sander", list_name="garage")
    sched.add_todo("already done", list_name="garage")
    goal = G.get().create("get the garage painted",
                          plan=[{"step": "sand the door"},
                                {"step": "buy the paint"}])
    P.get().update(proj["id"], {"goals": [goal["id"]]}, here=True)
    # A private benchmark must never be named in this answer.
    _add_bench(proj["id"], "weight", unit="kg", better="lower", target=80)

    got = _ask("what's next on this project", project=proj["id"])
    check("the project read is answered on this PC", got is not None, repr(got))
    if got is None:
        return
    reply = got.reply
    check("it names projects.db, the store it read", "projects.db" in reply, reply[:400])
    check("it names goals.db, the store it read", "goals.db" in reply)
    check("it names schedule.db, the store it read", "schedule.db" in reply)
    check("it names the date it read", DATE in reply)
    check("it lists the real open work-list item", "borrow sander" in reply)
    check("it lists the real open goal and its next step",
          "get the garage painted" in reply and "sand the door" in reply, reply)
    check("it lists the benchmark that is due a new number", "paint cans" in reply)
    check("a private (health or money) benchmark is not named",
          "weight" not in reply.lower(), reply)
    check("... and the answer says a private one was left out",
          "private" in reply.lower(), reply)
    check("the answer is read-only: nothing was ticked or written",
          P.get().get(proj["id"])["benchmark_list"][0]["results"] == 0 and
          G.get().get(goal["id"])["status"] == "draft")
    check("the read-only answer makes nothing for 'cancel that' to undo",
          got.made == [] and got.intent in Q.READ_ONLY_INTENTS)


# --------------------------------------------------------------------------
#   5. Two projects never share their pinned notes or their remembered facts
# --------------------------------------------------------------------------

def t_two_projects_do_not_share_notes_or_facts():
    _fresh()
    a = _make_project("Kestrel Trip", notes=["kestrel note: port 8080"])
    b = _make_project("Falcon Trip", notes=["falcon note: hangar code"])
    pa = Q.project_prompt(P.chat_scope({"project": a["id"]}))
    pb = Q.project_prompt(P.chat_scope({"project": b["id"]}))
    check("project A's pinned note is not in project B's prompt",
          "port 8080" in pa and "port 8080" not in pb, (pa[:200], pb[:200]))
    check("project B's pinned note is not in project A's prompt",
          "hangar code" in pb and "hangar code" not in pa)

    chosen = [{"id": 1, "text": "the owner is vegetarian"},
              {"id": 2, "text": "project A secret"},
              {"id": 3, "text": "project B secret"}]
    own_a = [{"id": 2, "text": "project A secret", "current": True, "created": 1.0}]
    own_b = [{"id": 3, "text": "project B secret", "current": True, "created": 1.0}]
    scope_a = P.chat_scope({"project": a["id"]})
    scope_b = P.chat_scope({"project": b["id"]})
    ka = Q.recall_for_project(chosen, scope_a, own_ids=[2], other_ids=[3],
                              own_rows=own_a, limit=5)
    kb = Q.recall_for_project(chosen, scope_b, own_ids=[3], other_ids=[2],
                              own_rows=own_b, limit=5)
    ids_a = {f["id"] for f in ka["facts"]}
    ids_b = {f["id"] for f in kb["facts"]}
    check("a project-scoped turn never sees another project's labelled fact",
          3 not in ids_a and 2 not in ids_b, (ids_a, ids_b))
    check("both keep the unlabelled personal fact, exactly as before",
          ids_a == {1, 2} and ids_b == {1, 3}, (ids_a, ids_b))
    check("a project's own labelled fact is added when the search missed it",
          2 in {f["id"] for f in Q.recall_for_project(
              [{"id": 1, "text": "x"}], scope_a, own_ids=[2], other_ids=[3],
              own_rows=own_a, limit=5)["facts"]})
    check("when the labels cannot be proved, NO fact is used (fail closed)",
          Q.recall_for_project(chosen, scope_a, own_ids=None, other_ids=None,
                               own_rows=own_a)["facts"] == [])
    check("a fact with no id cannot be proved unlabelled, so it is dropped",
          Q.recall_for_project([{"text": "no id"}], scope_a, own_ids=[], other_ids=[],
                               own_rows=[])["facts"] == [])


# --------------------------------------------------------------------------
#   6. RULE 1: a scoped chat that escalates to the cloud still strips memory
# --------------------------------------------------------------------------

def t_rule_1_a_cloud_turn_gets_no_project_memory():
    _fresh()
    a = _make_project("Kestrel Trip")
    scope = P.chat_scope({"project": a["id"]})
    chosen = [{"id": 1, "text": "personal fact"}]
    own = [{"id": 2, "text": "project fact", "current": True, "created": 1.0}]
    cloud = Q.recall_for_project(chosen, scope, own_ids=[2], other_ids=[],
                                 own_rows=own, local=False)
    check("a turn that may leave this PC is given NO remembered fact",
          cloud["facts"] == [], repr(cloud))
    check("... and it says why", "leave this PC" in cloud["why"], cloud["why"])

    # The static half, walked as an AST (never pinned as source text).
    prompt_calls = _calls("_jq.project_prompt")
    check("the HUD builds the project context block only on a local turn",
          bool(prompt_calls) and
          all(_guarded_by(c, "decision.inject_memory", "_project") for c in prompt_calls),
          [ast.unparse(c)[:120] for c in prompt_calls])
    blocks = [n for n in ast.walk(_hud()[0]) if isinstance(n, ast.Assign)
              and any(ast.unparse(t) == "_proj_msg" for t in n.targets)
              and isinstance(n.value, ast.Dict)
              and any(ast.unparse(k) == "'role'" for k in n.value.keys)]
    system_msg = [n for n in blocks
                  if any(isinstance(v, ast.Constant) and v.value == "system"
                         for v in n.value.values)]
    check("the project block IS a system message", bool(system_msg),
          [ast.unparse(n)[:120] for n in blocks])
    recall_calls = _calls("_jq.recall_for_project")
    check("the scoped facts are filtered by a shipped, tested function",
          bool(recall_calls))
    check("the fact scoping sits INSIDE the local-memory condition",
          all(_guarded_by(c, "decision.inject_memory", "jarvis_side_memory")
              for c in recall_calls),
          [ast.unparse(c)[:120] for c in recall_calls])
    # The cloud cuts (the relay's own and the degrade loop's) rebuild
    # `messages` from user-role turns only - every system message goes,
    # project block and recalled facts alike. The LAST of them runs AFTER the
    # block is inserted, so a hop that starts local and lands on a cloud lane
    # cannot carry it.
    cuts = []
    for n in ast.walk(_hud()[0]):
        if (isinstance(n, ast.Assign)
                and any(ast.unparse(t) == "messages" for t in n.targets)
                and isinstance(n.value, ast.ListComp)):
            text = ast.unparse(n.value)
            if "role" in text and "user" in text:
                cuts.append(n.lineno)
    check("the cloud cut that strips system messages comes after the block",
          bool(cuts) and bool(system_msg)
          and max(cuts) > min(n.lineno for n in system_msg),
          (cuts, [n.lineno for n in system_msg]))
    check("the route header says the scope only on a turn that named a project",
          bool(_route_header_assigns("project")) and
          all(_enclosed_by(a, "_project.get", "given")
              for a in _route_header_assigns("project")),
          [ast.unparse(a)[:120] for a in _route_header_assigns("project")])
    # private-chat.patch adds `private=_private` to THIS call - so the base
    # must keep it as `(body, peer=..., local=...)`, one call, exactly.
    quick_calls = _calls("answer_turn")
    check("the HUD's quick call is unchanged (private-chat.patch's own line)",
          len(quick_calls) == 1
          and [k.arg for k in quick_calls[0].keywords] == ["peer", "local"],
          [(k.arg, ast.unparse(k.value)) for c in quick_calls
           for k in c.keywords])


# --------------------------------------------------------------------------
#   7. THE CONTROL: a request with no project is every caller it was before
# --------------------------------------------------------------------------

def t_every_existing_caller_is_unchanged():
    _fresh()
    check("an ordinary turn's scope is 'no project'",
          P.chat_scope({}) == {"given": False, "ok": True, "project": None,
                               "id": None, "name": "", "error": "",
                               "why": "No project was named, so this turn is an "
                                      "ordinary one."}, repr(P.chat_scope({})))
    check("'what's next on this project' with no project still reaches the model",
          _ask("what's next on this project") is None)
    check("'log 41 against tests' with no project still reaches the model",
          _ask("log 41 against tests") is None)
    check("the route header has no 'project' key when no project was named",
          "project" not in Q.route_fields(Q.Result("x", "time_now")),
          repr(Q.route_fields(Q.Result("x", "time_now"))))

    # The OLD cardless life-benchmark lane is untouched: no project on the
    # body, and the owner's own sentence still logs without a card.
    _fresh()
    a = _make_project("Kestrel Trip")
    bench = _add_bench(a["id"], "run", unit="km")
    got = _ask("I ran 5 km")
    check("the old 'I ran 5 km' lane still answers without a project",
          got is not None and got.intent == "project_log", repr(got))
    if got is not None:
        pts = P.get().results(a["id"], bench["id"])["points"]
        check("... and still logs at once, cardless, as it shipped",
              len(pts) == 1 and pts[0]["value"] == 5, repr(pts))
        check("... and its route header is the old shape",
              "project" not in Q.route_fields(got))
    # A scoped chat matches inside ITS project only: the same sentence must not
    # land in another project's benchmark.
    b = _make_project("Falcon Trip")
    b_bench = _add_bench(b["id"], "run", unit="km")
    scoped = _ask("I ran 5 km", project=b["id"])
    check("a scoped 'I ran 5 km' logs inside the project the chat belongs to",
          scoped is not None and
          len(P.get().results(b["id"], b_bench["id"])["points"]) == 1, repr(scoped))
    check("... and NOT in the other project's identical benchmark",
          len(P.get().results(a["id"], bench["id"])["points"]) == 1)
    check("an untagged request is still not the owner's own words",
          Q.newest_own_words({"messages": [
              {"role": "user", "content": "what's next on this project"}]}) is None)
    check("a read-only project answer may be untagged (the purity gate)",
          "project_next" in Q.UNTAGGED_RECORD_READS and
          "project_benchmark_log" not in Q.UNTAGGED_RECORD_READS)


# --------------------------------------------------------------------------
#   8. A goal step's measure is what the project read reports (NO new schema)
# --------------------------------------------------------------------------

def t_a_goal_steps_measure_is_what_the_project_reads():
    _fresh()
    proj = _make_project("Kestrel Trip")
    bench = _add_bench(proj["id"], "tests", target=45)
    P.get().log(proj["id"], bench["id"], 41, source="app")
    goal = G.get().create("ship it",
                          plan=[{"step": "pass the tests",
                                 "measure": {"project": proj["id"], "bench": bench["id"]}}])
    P.get().update(proj["id"], {"goals": [goal["id"]]}, here=True)
    nxt = P.next_on_project(proj["id"], now=NOW)
    steps = (nxt["goals"][0]["steps"] if nxt["goals"] else [])
    check("the project read follows the goal's existing measure",
          bool(steps) and steps[0].get("measure_name") == "tests", repr(nxt["goals"]))
    check("41 of 45 is open, not met",
          bool(steps) and steps[0].get("state") == "open", repr(steps))
    P.get().log(proj["id"], bench["id"], 46, source="app")
    nxt2 = P.next_on_project(proj["id"], now=NOW)
    steps2 = (nxt2["goals"][0]["steps"] if nxt2["goals"] else [])
    check("the number reaching its target is reported as met, never ticked",
          bool(steps2) and steps2[0].get("state") == "met_by_number",
          repr(steps2))
    check("... with the reached words the goal module already builds",
          bool(steps2) and "reached" in (steps2[0].get("reached_words") or "").lower(),
          repr(steps2))
    got = _ask("what's next on this project", project=proj["id"])
    check("the chat answer says the step's number reached its target",
          got is not None and "reached its target" in got.reply,
          got.reply if got else "")
    check("no goal schema change was needed: the step still carries its measure",
          "measure" in json.dumps(G.get().get(goal["id"])["plan"]))


# --------------------------------------------------------------------------
#   9. The published twin, and the lane's own classification
# --------------------------------------------------------------------------

def t_the_published_twin_is_byte_identical():
    for name in ("jarvis_quick.py", "jarvis_projects.py"):
        here = (HERE / name).read_bytes()
        there = (REPO / "jarvis-backend" / name).read_bytes()
        check(f"{name} and its published jarvis-backend twin are identical",
              here == there, f"{len(here)} vs {len(there)} bytes")

    check("'what's next' is classified read-only",
          "project_next" in Q.READ_ONLY_INTENTS)
    check("the carded write is NOT classified read-only",
          "project_benchmark_log" not in Q.READ_ONLY_INTENTS)
    check("the write intent is not answered from a private chat's fast path",
          "project_benchmark_log" not in Q._PRIVATE_DETERMINISTIC_READS)


def main():
    print("=" * 74)
    print("jarvis_quick - a chat can belong to a project (2026-11-19)")
    print("=" * 74)
    tests = [
        ("a scoped turn uses that project's own context",
         t_scoped_turn_uses_the_projects_own_notes_and_headers),
        ("an unknown project is refused by name and writes nothing",
         t_unknown_project_refused_by_name_and_nothing_written),
        ("a named benchmark log is carded and scoped",
         t_named_benchmark_log_is_carded_and_scoped),
        ("what's next names its stores and its real items",
         t_whats_next_names_its_stores_and_its_real_items),
        ("two projects share no notes or facts",
         t_two_projects_do_not_share_notes_or_facts),
        ("rule 1: a cloud turn gets no project memory",
         t_rule_1_a_cloud_turn_gets_no_project_memory),
        ("the control: no project means no change",
         t_every_existing_caller_is_unchanged),
        ("a goal step's measure is what the project read reports",
         t_a_goal_steps_measure_is_what_the_project_reads),
        ("the published twin", t_the_published_twin_is_byte_identical),
    ]
    for name, fn in tests:
        print()
        print("--", name, "-" * max(0, 66 - len(name)))
        try:
            fn()
        except Exception as exc:                        # noqa: BLE001
            FAILED.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
            import traceback
            traceback.print_exc()
    print()
    print("=" * 74)
    print(f"{len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print("  FAIL:", name)
    shutil.rmtree(_TMP, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
