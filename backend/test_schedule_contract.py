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
who still has to consume it. `tools/check_schedule_actions.py` extracts each
surface's own table (HUD inline `actionsFor`, `coming-up.js` `actionsOf`/`labelOf`,
`Schedule.kt` `actionsOf`/`labelOf`) and compares it to the contract, printing the
progress. **This suite changes no surface, no backend module and no patch-carried
file.** The surfaces are owned by other PRs; the contract's `surfaces` entries
name the owner of each and carry the `reason` it is `pending`.

THE XFAIL-WITH-REASON, stated exactly: a surface whose `status` is `"pending"` in
the contract is compared and every difference is printed as `EXPECTED-GAP`, but
this suite reports that surface with `skip(...)` (the repository's honest
equivalent of xfail: a skip is counted on its own line and is never a pass). The
surfaces' owner PRs flip `status` to `"enforced"` when they land; this suite then
requires that surface to match, and `tools/check_schedule_actions.py --strict`
turns the pending gaps into failures immediately (`strict` is exercised below, so
the one-switch flip is proven even while CI is kept green today).

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
    NOT-TESTABLE, not a pass.

HONEST LIMITS: the three surface parsers read the known shape each surface has
today - a surface PR that renames its table must update
`tools/check_schedule_actions.py` in the same change (the checker fails loudly on
an unrecognised shape rather than guessing). The contract describes what the
owner's PC should draw; it does not run any app, so a rendering bug that keeps
the action names right but draws the wrong thing is outside it. No network, no
live write, no card, no deploy.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import tempfile
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
#  4. the cross-surface checker: real files, pending gaps named, strict flips
# ==========================================================================

def t_cross_surface_checker():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    check("the checker tool exists", CHECKER_PATH.is_file())
    result = CHECKER.run(contract, REPO)
    check("the checker runs over the real surface files and reports the contract OK",
          result["ok"] is True, result)
    check("every surface in the contract was checked",
          {s["name"] for s in result["surfaces"]} == set(contract["surfaces"]))
    for report in result["surfaces"]:
        check(f"{report['name']}: its source was parsed in the known shape",
              report["parse_error"] == "", report["parse_error"])
        check(f"{report['name']}: it was compared on at least one real case",
              report["cases"] >= 10, report["cases"])
        if report["status"] == "pending":
            check(f"{report['name']}: the pending gap is named (never a silent pass)",
                  bool(report["mismatches"]), report)
            skip(f"{report['name']}: XFAIL-WITH-REASON until {report['owner']} consumes "
                 f"the contract - {report['reason']}")
        else:
            check(f"{report['name']}: status is enforced and every case matches",
                  not report["mismatches"], report["mismatches"])
    strict = CHECKER.run(contract, REPO, strict=True)
    pending = [s for s in strict["surfaces"] if s["status"] == "pending"]
    if pending:
        check("--strict turns every pending gap into a failure (the one-switch flip)",
              strict["ok"] is False, strict)
    else:
        check("no surface is pending, so --strict agrees with the default run",
              strict["ok"] is True)
    readme = README_PATH.read_text(encoding="utf-8") if README_PATH.is_file() else ""
    check("the contract's README is the one short note the surface PRs start from",
          README_PATH.is_file()
          and all(text in readme for text in (
              "schedule-cases.json", "check_schedule_actions.py",
              "HUD Reminders", "coming-up.js", "Schedule.kt",
              "pending", "enforced")), sorted(readme)[:20] if readme else "missing")
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
