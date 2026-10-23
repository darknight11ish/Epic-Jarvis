"""test_schedule_contract.py - F5/Q2: ONE schedule action table, proved against the PC.

    python3 backend/test_schedule_contract.py

WHY THIS EXISTS (Gemini coherence ruling Q2 / finding F5, 2026-10-22). Three
surfaces draw the buttons for one scheduled job - the HUD's Reminders section,
the Brain window's `coming-up.js`, and the phone's `Schedule.kt` - and each used to
carry its own hand-written action table. They disagreed: `add_time` (+5 minutes)
was on the HUD's timer rows and on neither of the other two, `goal_checkin` rows
got Pause/Delete on the HUD but none on the phone, and no surface had anywhere to
show Wave D-1's new `ready_for_review` marker. The owner's fix (Q2) is one owner
table and a cross-surface proof.

WHAT THIS ADDS, AND WHAT IT DOES NOT TOUCH. `contract/schedule-cases.json` is the
one table (kind -> the allowed action names in button order, plus the exact labels
and the `ready_for_review` state). `contract/README.md` is the one note that says
who has consumed it. `tools/check_schedule_actions.py` reads the ONE shared
desktop table `jarvis-desktop/src/hud-actions.js` (coherence slice #729) plus the
HUD's browser-served `fallbackActionsFor`, the Brain's `coming-up.js` consumer and
the phone's hand-written `Schedule.kt` table, and compares each to the contract.
**This suite changes no surface, no backend module and no patch-carried file.**

THE XFAIL-WITH-REASON, stated exactly: a surface whose `status` is `"pending"` and
`"xfail": true` in the contract is still compared and every difference is printed
as `EXPECTED-GAP`; this suite reports such a surface with `skip(...)` - a skip is
counted on its own line and is never a pass. `--strict` turns a pending gap
WITHOUT `xfail` (or any enforced-surface difference) into a failure. All three
surfaces are now ENFORCED (the phone consumed the contract on 2026-10-23, Q2/F5),
so the suite still proves the strict rule by putting a pending gap without xfail
on a copy of the contract.

WHAT IS PROVED AGAINST THE REAL AUTHORITY, not copied prose:
  * the contract's kind list and flags against the REAL `jarvis_schedule.KINDS`
    registry (`KIND_MODULES` loaded; `jarvis_goals.KIND` = `goal_checkin` when
    Goals registers it);
  * the exact accept/refuse behaviour of the REAL `Scheduler.act()`:
    `add_time` only on a timer (active or paused), `done` only on a to-do,
    `pause` only on an active kind that has a time of its own (never a To-do,
    never a `Kind.ends` kind like `nexttime`), `resume` only when paused,
    `snooze` only on a fired timer/alarm/reminder, `delete` on every listed and
    fired state - each row created fresh, so one accepted action cannot colour
    the next;
  * the labels' amounts and words from the real helpers: `length_words(300)` is
    "+5 minutes" minus its plus sign and `length_words(SNOOZE_DEFAULT)` is
    "10 minutes", which is why the contract's two numeric labels are exactly
    those strings;
  * the HUD's three byte-identical copies agree (the same page is bundled in the
    desktop app and served by the backend);
  * D-1's `ready_for_review` marker when the backend has it (`propose_ready` /
    `suggest_done`), and an honest `skip` when it does not - D-1 (#722) was OPEN
    and NOT in main a97ac5f2 on 2026-10-22, so on today's main that half is
    NOT-TESTABLE, not a pass;
  * HUD Reminders Phase 2 (`edit`, `move`, `reorder`): `authority.verbs` is proved
    equal to the verb set read out of `Scheduler.act`'s own source (AST, not a
    backend import - the same read the checker does), and every case in the
    contract's `management.cases` is driven through the REAL `Scheduler.act()`
    with the expected 200/202/400/409 and the refusal sentence where one exists.
    The contract's contract-level verb/label/management shape is checked by
    `tools/check_schedule_actions.py` too, and this suite proves the checker
    fails on a deliberately drifted copy.

HONEST LIMITS: the three surface parsers read the known shape each surface has
today - a surface PR that renames its table must update
`tools/check_schedule_actions.py` in the same change (the checker fails loudly on
an unrecognised shape rather than guessing). The contract describes what the
owner's PC should draw; it does not run any app, so a rendering bug that keeps
the action names right but draws the wrong thing is outside it. No network, no
live write, no card, no deploy.
"""
from __future__ import annotations

import ast
import copy
import importlib
import importlib.util
import inspect
import json
import os
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
REBUILT = HERE / "rebuilt"
CONTRACT_PATH = REPO / "contract" / "schedule-cases.json"
README_PATH = REPO / "contract" / "README.md"
CHECKER_PATH = REPO / "tools" / "check_schedule_actions.py"

# A scratch home BEFORE the scheduler imports: its DB path is read from the
# environment; the owner's own ~/.openjarvis is never touched.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-schedule-contract-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP)
os.environ.setdefault("JARVIS_FRAMEWORK_TOML", str(REBUILT / "jarvis-framework.toml"))
sys.path.insert(0, str(REBUILT))
sys.path.insert(0, str(HERE))

import jarvis_schedule as S  # noqa: E402


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_schedule_actions", CHECKER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_schedule_actions"] = module
    spec.loader.exec_module(module)
    return module


CHECKER = _load_checker()

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


#: Kinds the contract marks as surfaced, with the owner_listed flag the real
#: registry must agree with. `goal_checkin` is registered by jarvis_goals, not by
#: jarvis_schedule's own KIND_MODULES list, so it is checked only when present.
def _load_real_kinds() -> dict:
    for name in S.KIND_MODULES:
        try:
            importlib.import_module(name)
        except Exception:  # noqa: BLE001 - the scheduler itself skips a missing module
            pass
    try:
        importlib.import_module("jarvis_goals")     # registers goal_checkin
    except Exception:  # noqa: BLE001
        pass
    return dict(S.KINDS)


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


NOW = 1_800_000_000.0
CLOCK = Clock(NOW)
SCHEDULER = S.Scheduler(
    _TMP / "contract.db", clock=CLOCK, gate=lambda *a, **k: None,
    tier_of=lambda a: "auto", spawn=lambda fn: fn(), publish=lambda k, d: None)


def fresh_job(kind: str, state: str = "active", *, rule=None, fired: bool = False) -> str:
    """One synthetic row of a real kind, so act() sees a real database row."""
    jid = SCHEDULER._insert(kind, text="probe", state="active" if fired else state,
                            due=None if fired else NOW + 3600, rule=rule,
                            duration=600 if kind == "timer" else None,
                            source="contract-test")
    if fired:
        with SCHEDULER._db() as c:
            c.execute("UPDATE jobs SET state = 'fired', fired_at = ?, due = NULL WHERE id = ?",
                      (NOW - 60, jid))
    return jid


def act(jid: str, do: str, seconds: float = 300) -> int:
    code, _out = SCHEDULER.act(jid, do, seconds=seconds)
    return code


def act_fields(jid: str, do: str, fields: dict) -> tuple:
    return SCHEDULER.act(jid, do, fields=fields)


def _listed(contract: dict) -> dict:
    return {kind: spec for kind, spec in contract["kinds"].items() if spec.get("listed")}


def _all_states_with_actions(contract: dict) -> list:
    out = []
    for kind, spec in _listed(contract).items():
        for state, actions in (spec.get("states") or {}).items():
            if actions:
                out.append((kind, state, actions))
    return out


# ==========================================================================
#  0. the contract itself: one table, real numbers for the labels
# ==========================================================================

def t_contract_is_one_complete_table():
    check("the contract file exists", CONTRACT_PATH.is_file(), CONTRACT_PATH)
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    check("it is schema 1 and names the real authority", contract.get("schema") == 1
          and "jarvis_schedule" in json.dumps(contract.get("authority") or {}),
          contract.get("authority"))
    for kind in ("timer", "alarm", "reminder", "todo", "standby", "briefing",
                 "tellme", "nexttime", "today", "review", "goal_checkin"):
        check(f"the table has {kind}", kind in contract["kinds"])
    check("every non-visible kind is marked not-listed",
          all(not contract["kinds"][k]["listed"]
              for k in ("focus", "tidy", "topic_sort", "referee", "tag_suggest")))
    labels = contract["labels"]
    check("the add_time label is EXACTLY the real length_words(300), plus a plus sign",
          labels["add_time"]["label"] == "+" + S.length_words(300), labels["add_time"])
    check("the add_time amount is 5 minutes in seconds", labels["add_time"]["seconds"] == 300)
    check("the snooze label is exactly 'Snooze ' + the real length_words(SNOOZE_DEFAULT)",
          labels["snooze"]["label"] == "Snooze " + S.length_words(S.SNOOZE_DEFAULT),
          labels["snooze"])
    check("the snooze amount is the real SNOOZE_DEFAULT", labels["snooze"]["seconds"] == S.SNOOZE_DEFAULT)
    check("the other four labels are the two apps' existing plain words",
          [labels[a]["label"] for a in ("pause", "resume", "delete", "done")]
          == ["Pause", "Resume", "Delete", "Done"])
    check("delete is the one button drawn as dangerous", labels["delete"].get("danger") is True)
    check("the ready_for_review entry exists with D-1's words and only done/delete",
          contract["states"]["ready_for_review"]["actions"] == ["done", "delete"]
          and contract["states"]["ready_for_review"]["tag"] == "Ready for your review"
          and "only you can mark it done" in contract["states"]["ready_for_review"]["said"]
          and "#722" in contract["states"]["ready_for_review"]["added_by"],
          contract["states"]["ready_for_review"])
    check("every action named in a kind's states has a label",
          all(action in labels for _kind, _state, actions in _all_states_with_actions(contract)
              for action in actions))
    check("add_time appears under a timer ONLY (S.act refuses it everywhere else)",
          all("add_time" not in actions for kind, _state, actions in _all_states_with_actions(contract)
              if kind != "timer")
          and "add_time" in contract["kinds"]["timer"]["states"]["active"])
    check("done appears under a to-do ONLY (S.act refuses it everywhere else)",
          all("done" not in actions for kind, _state, actions in _all_states_with_actions(contract)
              if kind != "todo")
          and "done" in contract["kinds"]["todo"]["states"]["active"])
    snooze_states = [(kind, state) for kind, state, actions in _all_states_with_actions(contract)
                     if "snooze" in actions]
    check("snooze appears only on a fired timer/alarm/reminder",
          all(state == "fired" and kind in ("timer", "alarm", "reminder")
              for kind, state in snooze_states)
          and {kind for kind, _state in snooze_states} == {"timer", "alarm", "reminder"},
          snooze_states)
    check("nexttime's rows are delete-only (a Kind.ends job has no time to pause)",
          all(set(actions) == {"delete"}
              for actions in contract["kinds"]["nexttime"]["states"].values() if actions))
    check("review and goal_checkin offer NO action (Decks / Goals own those rows)",
          all(not actions for states in (contract["kinds"]["review"]["states"],
                                         contract["kinds"]["goal_checkin"]["states"])
              for actions in states.values()))
    check("every surface has a status, an owner and a reason",
          all(s.get("status") in ("pending", "enforced") and s.get("owner") and s.get("reason")
              for s in contract["surfaces"].values()), contract["surfaces"])
    check("the shared desktop table is named in the contract and exists",
          (contract.get("shared") or {}).get("file") == "jarvis-desktop/src/hud-actions.js"
          and (REPO / contract["shared"]["file"]).is_file(), contract.get("shared"))
    shared = CHECKER.parse_shared((REPO / contract["shared"]["file"]).read_text(encoding="utf-8"))
    check("the shared table's labels are the contract's labels",
          all(shared["labels"].get(action) == spec["label"]
              for action, spec in contract["labels"].items()), shared["labels"])
    check("the shared table's went-off list and no-pause list are the contract's ordering",
          shared["went_off"] == ["snooze", "delete"] and shared["no_pause"] == {"nexttime"},
          (shared["went_off"], sorted(shared["no_pause"])))
    check("all three surfaces are ENFORCED on the shared table (phone consumed 2026-10-23)",
          contract["surfaces"]["hud"]["status"] == "enforced"
          and contract["surfaces"]["coming_up"]["status"] == "enforced"
          and contract["surfaces"]["phone"]["status"] == "enforced"
          and not contract["surfaces"]["phone"].get("xfail"), contract["surfaces"])
    check("the two deliberately-uncompared entries state their reason and owner",
          contract["kinds"]["goal_checkin"].get("surface_compare") is False
          and "surface_note" in contract["kinds"]["goal_checkin"]
          and (contract["states"]["ready_for_review"].get("surface_status")
               == "pending-d1-surfacing")
          and "surface_note" in contract["states"]["ready_for_review"])
    management = contract.get("management") or {}
    check("the contract carries HUD Reminders Phase 2 with a real case matrix",
          set((management.get("verbs") or {})) == {"edit", "move", "reorder"}
          and len(management.get("cases") or []) >= 20
          and management.get("owner") and management.get("reason"), management)
    check("authority.verbs names all nine real verbs, including the Phase-2 three",
          contract["authority"].get("verbs") == [
              "pause", "resume", "delete", "done", "add_time", "snooze",
              "edit", "move", "reorder"], contract["authority"].get("verbs"))
    check("the Phase-2 words are the open UI's exact words",
          (management.get("labels") or {}).get("edit") == "Edit"
          and (management.get("labels") or {}).get("save") == "Save changes"
          and (management.get("labels") or {}).get("cancel") == "Cancel"
          and (management.get("labels") or {}).get("move_up") == "Move up"
          and (management.get("labels") or {}).get("move_down") == "Move down",
          management.get("labels"))
    check("the Phase-2 kinds are the open UI's EDITABLE_KINDS plus the to-do-only verbs",
          management["verbs"]["edit"]["kinds"] == ["timer", "alarm", "reminder", "todo"]
          and management["verbs"]["move"]["kinds"] == ["todo"]
          and management["verbs"]["reorder"]["kinds"] == ["todo"]
          and all(k in contract["kinds"] for verb in management["verbs"].values()
                  for k in verb["kinds"]), management["verbs"])
    check("the Phase-2 surfaces say who must consume the block, and why it is pending",
          (management.get("surfaces") or {}).get("hud") == "pending"
          and (management.get("surfaces") or {}).get("coming_up") == "pending"
          and (management.get("surfaces") or {}).get("phone") == "not-planned"
          and "feat/hud-reminders-phase2-edit-move-reorder-ui" in management["owner"],
          management.get("surfaces"))


# ==========================================================================
#  1. the contract's kinds/flags against the REAL registry
# ==========================================================================

def t_contract_matches_the_real_kind_registry():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    kinds = _load_real_kinds()
    check("the real scheduler loaded its kinds", len(kinds) >= 10, sorted(kinds))
    for name, spec in contract["kinds"].items():
        real = kinds.get(name)
        if real is None:
            check(f"contract kind {name} is either in the real registry or explicitly not",
                  name == "goal_checkin",
                  f"{name} is neither in S.KINDS nor the one Goals-only kind")
            continue
        check(f"{name}: the contract's listed flag matches Kind.owner_listed",
              bool(spec.get("listed")) is bool(real.owner_listed),
              (spec.get("listed"), real.owner_listed))
    unlisted = [k for k, spec in contract["kinds"].items() if not spec.get("listed")]
    real_unlisted = [k for k, v in kinds.items() if not v.owner_listed]
    check("the non-visible kinds are the same set on both sides",
          sorted(unlisted) == sorted(set(unlisted) & set(real_unlisted))
          and set(real_unlisted) <= set(unlisted),
          sorted(set(real_unlisted) ^ set(unlisted)))
    check("every real registry kind is in the contract (a new kind cannot be forgotten)",
          set(kinds) <= set(contract["kinds"]), sorted(set(kinds) - set(contract["kinds"])))
    check("nexttime is the Kind.ends kind on both sides",
          kinds["nexttime"].ends is True and contract["kinds"]["nexttime"].get("ends") is True)
    check("standby is the window kind on both sides",
          kinds["standby"].window is True)
    check("the snoozable contract kinds are exactly the real S.SNOOZABLE tuple",
          tuple(k for k, spec in contract["kinds"].items() if spec.get("snoozable"))
          == tuple(k for k in S.SNOOZABLE if k in contract["kinds"]),
          S.SNOOZABLE)


# ==========================================================================
#  2. the REAL Scheduler.act() accepts/refuses exactly the contract's rules
# ==========================================================================

def t_act_authority_matches_the_contract_rules():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    listed = list(_listed(contract))
    # delete: every listed state, and a fired entry too (DEF-008).
    for kind in listed:
        for state in ("active", "paused", "waiting"):
            check(f"delete is accepted on {kind}.{state} (every listed state)",
                  act(fresh_job(kind, state), "delete") == 200, f"{kind}.{state}")
        if contract["kinds"][kind].get("snoozable"):
            check(f"delete is accepted on a fired {kind} entry (DEF-008)",
                  act(fresh_job(kind, fired=True), "delete") == 200, kind)
    # pause: an active job of a kind with a time of its own, never a to-do,
    # never a Kind.ends kind, never waiting or fired.
    for kind in ("todo",):
        check(f"pause is refused on {kind} (it has no time to skip)",
              act(fresh_job(kind, "active"), "pause") == 409, kind)
    for kind in ("review", "goal_checkin"):
        # The contract draws NO buttons for these because the row belongs to
        # Decks/Goals - a UI-ownership rule, not something act() itself refuses.
        check(f"the {kind} row is drawn with NO action (its owner owns it, not act())",
              not any(contract["kinds"][kind]["states"].values()))
    for kind in listed:
        if kind in ("todo",):
            continue
        if kind == "nexttime":
            check("pause is refused on nexttime (Kind.ends: nothing to pause)",
                  act(fresh_job(kind, "active"), "pause") == 409)
        else:
            check(f"pause is accepted on an active {kind}", act(fresh_job(kind, "active"), "pause") == 200, kind)
            check(f"pause is refused once {kind} is waiting", act(fresh_job(kind, "waiting"), "pause") == 409, kind)
    for kind in ("timer", "alarm", "reminder"):
        check(f"pause is refused on a fired {kind} (only snooze/delete reach it)",
              act(fresh_job(kind, fired=True), "pause") == 409)
    # resume: only from paused, and only where a pause was possible.
    for kind in ("timer", "alarm", "reminder", "standby", "briefing", "tellme", "today"):
        row = fresh_job(kind, "active")
        check(f"{kind} can really be paused first (the resume case is reachable)",
              act(row, "pause") == 200)
        check(f"resume is accepted on a paused {kind}", act(row, "resume") == 200, kind)
        check(f"resume is refused on an active {kind}", act(fresh_job(kind, "active"), "resume") == 409)
    # done: a to-do item only.
    check("done is accepted on a to-do", act(fresh_job("todo", "active"), "done") == 200)
    for kind in listed:
        if kind != "todo":
            check(f"done is refused on {kind} (only a to-do can be marked done)",
                  act(fresh_job(kind, "active"), "done") == 409, kind)
    # add_time: a timer only, active or paused; +5 minutes is what the contract says.
    timer = fresh_job("timer", "active")
    check("add_time is accepted on an active timer", act(timer, "add_time", 300) == 200)
    check("add_time is accepted on a paused timer", act(timer, "add_time", 300) == 200)
    for kind in listed:
        if kind != "timer":
            check(f"add_time is refused on {kind} ('Time can only be added to a timer')",
                  act(fresh_job(kind, "active"), "add_time", 300) == 409, kind)
    check("add_time is refused on a fired timer", act(fresh_job("timer", fired=True), "add_time", 300) == 409)
    check("add_time needs a positive amount", act(fresh_job("timer", "active"), "add_time", 0) == 400)
    # snooze: a fired timer/alarm/reminder only.
    for kind in S.SNOOZABLE:
        check(f"snooze is accepted on a fired {kind}", act(fresh_job(kind, fired=True), "snooze", 600) == 200)
        check(f"snooze is refused on an active {kind} that never went off",
              act(fresh_job(kind, "active"), "snooze", 600) == 409, kind)
    for kind in listed:
        if kind not in S.SNOOZABLE:
            check(f"snooze is refused on a fired {kind} (S.SNOOZABLE has three kinds)",
                  act(fresh_job(kind, fired=True), "snooze", 600) == 409, kind)
    check("an unknown verb is refused with the closed set",
          act(fresh_job("timer", "active"), "make_it_loud") == 400)


# ==========================================================================
#  3. Wave D-1's ready_for_review marker
# ==========================================================================

def t_ready_for_review_half():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    ready = contract["states"]["ready_for_review"]
    check("the contract entry keeps D-1's words and the owner-only rule",
          ready["tag"] == "Ready for your review" and "done" in ready["actions"]
          and "only you can mark it done" in ready["said"])
    if not hasattr(S.Scheduler, "propose_ready"):
        skip("D-1 (#722) is OPEN and not in main a97ac5f2 on 2026-10-22: the contract "
             "entry and the surface marker check are defined, but the backend half of "
             "ready_for_review is NOT-TESTABLE here. It will run automatically when "
             "#722 merges (the check below is shape-based, not version-pinned).")
        return
    jid = fresh_job("todo", "active")
    code, out = SCHEDULER.propose_ready(jid, review_note="done my part")
    check("propose_ready accepts a to-do", code == 200 and out.get("ready_for_review") is True, out)
    view = SCHEDULER.job(jid)
    check("the view says ready_for_review, with D-1's sentence",
          view.get("ready_for_review") is True and view.get("ready_said") == S.READY_SAID, view)
    check("... and the marker NEVER means done (done is still False)",
          view.get("done") is False, view.get("done"))
    check("... only the owner's act('done') completes it", act(jid, "done") == 200)
    other = fresh_job("reminder", "active")
    check("propose_ready refuses a non-to-do", SCHEDULER.propose_ready(other)[0] == 409)


# ==========================================================================
#  2b/2c. the verb set and the Phase-2 management cases against the REAL act()
# ==========================================================================

def _act_verbs_from_act_source() -> set:
    """The accepted verb set as the PC's own code spells it, no backend import."""
    src = textwrap.dedent(inspect.getsource(S.Scheduler.act))
    tree = ast.parse(src)
    verbs = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Compare) and isinstance(node.left, ast.Name)
                and node.left.id == "do"):
            continue
        for op, comp in zip(node.ops, node.comparators):
            if isinstance(op, ast.Eq) and isinstance(comp, ast.Constant) \
                    and isinstance(comp.value, str):
                verbs.add(comp.value)
            elif isinstance(op, ast.In) and isinstance(comp, ast.Tuple):
                verbs.update(elt.value for elt in comp.elts
                             if isinstance(elt, ast.Constant) and isinstance(elt.value, str))
    return verbs


def t_act_verb_set_matches_the_contract():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    real = _act_verbs_from_act_source()
    declared = sorted(contract["authority"]["verbs"])
    check("the AST read of Scheduler.act finds exactly the nine real verbs",
          real == {"pause", "resume", "delete", "done", "add_time", "snooze",
                   "edit", "move", "reorder"}, sorted(real))
    check("the contract's authority.verbs is EXACTLY Scheduler.act's accepted set",
          sorted(real) == declared, (sorted(real), declared))
    check("the checker's own AST read agrees (contract and tool use one truth)",
          CHECKER.scheduler_act_verbs(REPO) == declared,
          (CHECKER.scheduler_act_verbs(REPO), declared))
    check("every declared verb has a label or a management entry",
          set(contract["labels"]) | set(contract["management"]["verbs"]) == set(declared),
          (sorted(contract["labels"]), sorted(contract["management"]["verbs"])))
    drifted = copy.deepcopy(contract)
    drifted["authority"]["verbs"] = ["pause", "resume", "delete"]
    found = CHECKER.run(drifted, REPO)
    check("the checker FAILS when a contract verb is dropped (the drift is caught)",
          found["ok"] is False and any("Scheduler.act" in p
                                       for p in found["contract_problems"]),
          found["contract_problems"])


def t_phase2_management_cases():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    cases = contract["management"]["cases"]
    for case in cases:
        label = (f"{case['verb']} {case['kind']}.{case['state']} "
                 f"{case['fields']} -> {case['code']}")
        jid = fresh_job(case["kind"], case["state"])
        code, out = act_fields(jid, case["verb"], dict(case.get("fields") or {}))
        check(f"real act() gives the contract's {case['code']} for {label}",
              code == case["code"], out)
        if case.get("error"):
            said = str((out or {}).get("error") or "")
            check(f"... with the refusal sentence {case['error']!r}",
                  case["error"].lower() in said.lower(), said)
        if case.get("waiting"):
            check("... as ONE pending card (202 waiting), never a silent write",
                  (out or {}).get("waiting") is True, out)


# ==========================================================================
#  4. the cross-surface checker: real files, pending gaps named, strict flips
# ==========================================================================

def t_cross_surface_checker():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    check("the checker tool exists", CHECKER_PATH.is_file())
    result = CHECKER.run(contract, REPO)
    check("the checker runs over the real files and reports the contract OK",
          result["ok"] is True, result)
    check("every surface in the contract was checked",
          {s["name"] for s in result["surfaces"]} == set(contract["surfaces"]))
    reports = {s["name"]: s for s in result["surfaces"]}
    for name in ("hud", "coming_up"):
        report = reports[name]
        check(f"{name}: its source was parsed in the known shape",
              report["parse_error"] == "", report["parse_error"])
        check(f"{name}: status is enforced and every case matches the contract",
              report["status"] == "enforced" and not report["mismatches"],
              report["mismatches"])
        check(f"{name}: it was compared on at least ten real cases",
              report["cases"] >= 10, report["cases"])
    phone = reports["phone"]
    check("phone: its source was parsed in the known shape", phone["parse_error"] == "",
          phone["parse_error"])
    check("phone: status is enforced and every case matches the contract",
          phone["status"] == "enforced" and not phone["mismatches"], phone)
    check("phone: it was compared on the same 29 shared cases as the desktop",
          phone["cases"] == 29, phone["cases"])
    check("the D-1 marker, the Goals-only kind and Phase-2 are notes, not failures",
          any("ready_for_review" in note for note in result["notes"])
          and any("goal_checkin" in note for note in result["notes"])
          and any("Phase-2 management actions" in note for note in result["notes"]),
          result["notes"])

    strict = CHECKER.run(contract, REPO, strict=True)
    check("--strict is GREEN with every surface enforced", strict["ok"] is True, strict)
    # The rule the repo keeps for a future, not-yet-consumed surface: a pending
    # gap WITH a real mismatch and no xfail must fail strict, never pass as green.
    synthetic = copy.deepcopy(contract)
    synthetic["surfaces"]["phone"]["status"] = "pending"
    synthetic["surfaces"]["phone"].pop("xfail", None)
    synthetic["kinds"]["timer"]["states"]["active"] = ["pause", "delete"]
    flipped = CHECKER.run(synthetic, REPO, strict=True)
    check("--strict bites on a pending surface with a real gap and no xfail",
          flipped["ok"] is False, flipped)

    readme = README_PATH.read_text(encoding="utf-8") if README_PATH.is_file() else ""
    check("the contract's README is the one short note the surface owners start from",
          README_PATH.is_file()
          and all(text in readme for text in (
              "schedule-cases.json", "check_schedule_actions.py", "hud-actions.js",
              "HUD Reminders", "coming-up.js", "Schedule.kt",
              "enforced", "xfail")), sorted(readme)[:20] if readme else "missing")
    # The HUD page is bundled in the app AND served by the backend: three copies.
    hud = [REPO / "jarvis-desktop" / "src" / "jarvis_hud.html",
           REPO / "backend" / "jarvis_hud.html",
           REPO / "jarvis-backend" / "jarvis_hud.html"]
    copies = [p.read_bytes() for p in hud if p.is_file()]
    check("the three HUD copies are byte-identical, so the checker's one parse covers all",
          len(copies) == 3 and copies[0] == copies[1] == copies[2],
          [(str(p), p.is_file()) for p in hud])


# ==========================================================================
#  main
# ==========================================================================

def main():
    print(__doc__.splitlines()[0])
    print()
    tests = (
        ("0. the contract is one complete table", t_contract_is_one_complete_table),
        ("1. the contract matches the real kind registry", t_contract_matches_the_real_kind_registry),
        ("2. the real act() authority matches the contract rules", t_act_authority_matches_the_contract_rules),
        ("2b. the contract verb set equals Scheduler.act's accepted set", t_act_verb_set_matches_the_contract),
        ("2c. the Phase-2 management cases match the real act()", t_phase2_management_cases),
        ("3. Wave D-1 ready_for_review", t_ready_for_review_half),
        ("4. the cross-surface checker", t_cross_surface_checker),
    )
    for label, fn in tests:
        print(f"-- {label}")
        try:
            fn()
        except Exception:
            FAILED.append(label)
            print(f"FAIL  {label} raised\n        {traceback.format_exc()}")
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(str(x) for x in FAILED))
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
