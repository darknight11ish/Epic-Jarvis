#!/usr/bin/env python3
"""Writes jarvis-desktop/tests/fixtures/risky-approval-cases.json, and the
phone's identical copy in jarvis-client/app/src/test/resources/contract/:
which approvals are RISKY - the ones that need the owner's own check (Windows
Hello on the PC, the fingerprint or PIN on the phone) - and what the check's
prompt says. Each case also carries `small`: whether the owner's request of
2026-11-01 makes it a SMALL read-only approval, which is approved by the card
alone (backend/jarvis_owner_check.py `is_small`).

    python3 tools/gen_risky_approval_cases.py            # write the files
    python3 tools/gen_risky_approval_cases.py --check    # compare only

WHY ONE FILE FOR THREE PLACES. Since owner-check.patch (docs/APPROVAL-GAP-
DESIGN.md step 1) the backend asks Windows Hello itself for a risky approval
made on the PC, and the desktop then stops asking - so the backend's rule is
the one that decides on the PC, and it must be the rule the desktop and the
phone already use. `risky`, `small` and `message` in each case are the
backend's own answers (backend/jarvis_owner_check.py `is_risky`, `is_small`
and `approval_message`), run on each row; the desktop's `lock/rules.rs` test
and the phone's `RiskyApprovalContractTest.kt` / `SmallApprovalContractTest.kt`
must give the same answers for every row. backend/test_owner_check.py fails
when the committed files differ from a fresh run.

THE ROWS. Each is what GET /api/pending sends, built the way
backend/test_approval_contract.py builds its rows: the real `notice_for`
and `expires_in` code out of the patches, and a stand-in for `risk_for`
made from the `_RISK` entries the patches add (the real one lives only on
the owner's PC). Hand-made `risk` objects cover the shapes the gate does not
send today (a missing field), because the rule's defaults are part of it.
`raised` appears in the shapes the backend's own tests use: missing, null,
false, true, an object, and the JSON text of an object. The small-read rows
at the end are the gate's own `_RISK` entries for the read-only actions, so
`small` is the real answer for the cards the owner actually approves.
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "risky-approval-cases.json"
PHONE_FIXTURE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
                 / "risky-approval-cases.json")
COPIES = (FIXTURE, PHONE_FIXTURE)

# WHICH BACKEND THIS MEASURES, and why it is not simply ROOT/"backend".
#
# `backend/test_owner_check.py` runs this file as a subprocess from inside
# `backend/run_suites.py`, which sets JARVIS_BACKEND to the folder the suites
# are really exercising (a temporary copy of every shipped module, so the
# shipped LAYOUT is tested rather than this repository's). Hard-coding
# ROOT/"backend" here made the two disagree: the suite imported one
# `jarvis_owner_check` and this file built its rows with another, so the check
# reported the fixture out of date while running the tool by hand said it was
# current (measured 2026-10-10). `_where` is the one answer both use.
sys.path.insert(0, str(ROOT / "backend"))
from _where import BACKEND  # noqa: E402

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import jarvis_owner_check as OC  # noqa: E402
import test_approval_contract as AC  # noqa: E402

NOW = AC.NOW
LOCAL_UNDOABLE = "append_logseq_journal"     # ("yes", "local") in the gate's table
UNKNOWN = "some_tool_nobody_classified"


def _row(rid, action, raised=None, *, drop_raised=False, **extra) -> dict:
    base = {"id": rid, "action": action, "tier": "ask", "created": NOW - 30,
            "detail": "{}", "prompt": f"tool {action} {{}}", "raised": raised}
    if drop_raised:
        del base["raised"]
    row = AC.pending_row(base)
    row.update(extra)
    return row


def _with_risk(rid, risk: dict, action=LOCAL_UNDOABLE, **kw) -> dict:
    row = _row(rid, action, **kw)
    row["risk"] = risk
    return row


def rows() -> list:
    """(name, row). Every name says what the case is about."""
    rushed = {"code": "rushed", "quote": "approve now or lose it", "count_today": 1}
    return [
        ("stays on this PC and can be undone", _row("a1", LOCAL_UNDOABLE)),
        ("stays on this PC and can be undone, no raised field at all",
         _row("a2", LOCAL_UNDOABLE, drop_raised=True)),
        ("stays on this PC and can be undone, raised is false",
         _row("a3", LOCAL_UNDOABLE, raised=False)),
        ("rushed: raised is an object", _row("a4", LOCAL_UNDOABLE, raised=rushed)),
        ("rushed: raised is true (the doorbell's boolean)", _row("a5", LOCAL_UNDOABLE, raised=True)),
        ("rushed: raised is the JSON text of an object (how the database holds it)",
         _row("a6", LOCAL_UNDOABLE, raised=json.dumps(rushed))),
        ("not in the gate's table: unclassified", _row("a7", UNKNOWN)),
        ("classified, leaves this PC",
         _with_risk("a9", {"classified": True, "reach": "outbound", "reversible": "yes",
                           "why": "It leaves this PC.", "swipe_ok": False})),
        ("classified, stays on this PC, cannot be undone",
         _with_risk("a10", {"classified": True, "reach": "local", "reversible": "no",
                            "why": "It cannot be undone.", "swipe_ok": False})),
        # The merge card of an app inside Projects (apps-in-projects.patch:
        # ("no", "local") in the gate's table): risky, so the PC asks Windows
        # Hello and the phone the screen lock; never a swipe.
        ("adding a change to an app: stays on this PC, no Undo yet - risky",
         _with_risk("a17", {"classified": True, "reach": "local", "reversible": "no",
                            "why": "It cannot be undone.", "swipe_ok": False},
                    action="app_merge_change")),
        ("classified, stays on this PC, hard to undo (not risky: only \"no\" is)",
         _with_risk("a11", {"classified": True, "reach": "local", "reversible": "hard",
                            "why": "Undoing it takes work.", "swipe_ok": False})),
        ("classified, but no reach: read as outbound",
         _with_risk("a12", {"classified": True, "reversible": "yes", "why": "x"})),
        ("classified, but no reversible: read as cannot be undone",
         _with_risk("a13", {"classified": True, "reach": "local", "why": "x"})),
        ("classified is false, even for a local undoable action",
         _with_risk("a14", {"classified": False, "reach": "local", "reversible": "yes",
                            "why": "x"})),
    ] + [("no risk object at all", _strip(_row("a15", LOCAL_UNDOABLE), "risk")),
         ("no notice: the prompt names the action instead",
          _strip(_row("a16", LOCAL_UNDOABLE), "notice"))] + _small_rows()


#: THE SMALL READ-ONLY CARDS (the owner's request of 2026-11-01): every action
#: `jarvis_owner_check.SMALL_ACTIONS` classifies small, built from the gate's
#: own `_RISK` row for it - so `small` here is the real answer for the cards
#: the owner actually approves, not a hand-written expectation.
SMALL_ACTIONS = (
    "search_the_web",       # one web search's words
    "web_research",         # a public query
    "news_read",            # the news feeds he chose
    "page_read",            # the one page he already named
    "github_read",          # public GitHub data
    "browse_model_catalog", # a fixed public query
    "calendar_read",
    "email_read",
    "notes_search",
    "home_read",
    "read_calendar",
    "read_files_readonly",
    "read_joplin_note",
    "read_logseq_page",
)


#: The four rows the owner's own gate file carries and NO PATCH IN THIS
#: REPOSITORY ADDS (they are context lines in `jarvis_gate.py` on his PC), so
#: the patch-stack stand-in above cannot see them. Copied from that file's
#: `_RISK` table, word for word. Used only to build a CONTRACT case - the rule
#: itself reads the live table, never this dict.
_LIVE_ONLY_RISK = {
    "web_research": ("outbound", "a public query leaves the machine; nothing changes"),
    "read_calendar": ("local", "reads the calendar; changes nothing in it"),
    "read_files_readonly": ("local", "opens the file; writes nothing back"),
    "read_joplin_note": ("local", "opens the note; the vault is unchanged"),
}


def _small_rows() -> list:
    """(name, row) for the small list, plus the ones that must NOT be small.

    Each small row's `risk` is the gate's OWN row for that action - read from
    the patch stack when it has one, and from `_LIVE_ONLY_RISK` (the owner's
    file) when no patch adds it. A row that claims `reversible` anything but
    "yes" fails here rather than quietly making an irreversible action small.
    """
    table = AC._risk_table()
    out = []
    for action in SMALL_ACTIONS:
        got = table.get(action)
        if got is None:
            reach, why = _LIVE_ONLY_RISK[action]
            reversible = "yes"
        else:
            reversible, reach, why = got
        assert reversible == "yes", (action, got)
        out.append((f"small read: {action}",
                    _with_risk(f"s-{action}",
                               {"classified": True, "reach": reach,
                                "reversible": reversible, "why": why,
                                "swipe_ok": False},
                               action=action)))
    # NEAR MISSES, so `small` cannot become "whatever the action list says":
    # the gate's metadata still has the last word.
    out += [
        ("small action, but the gate says it cannot be undone",
         _with_risk("s-rev-no", {"classified": True, "reach": "outbound",
                                 "reversible": "no", "why": "x", "swipe_ok": False},
                    action="search_the_web")),
        ("small action, but the gate has not classified it",
         _with_risk("s-unclassified", {"classified": False, "reach": "outbound",
                                       "reversible": "yes", "why": "x",
                                       "swipe_ok": False},
                    action="search_the_web")),
        ("small action, but something tried to rush it",
         _row("s-rushed", "search_the_web",
              raised={"code": "rushed", "quote": "approve now or lose it",
                      "count_today": 1})),
        ("local and undoable, but it stops a service: not a read, not small",
         _row("s-docker", "docker_service_stop")),
    ]
    return out


def _strip(row: dict, key: str) -> dict:
    row = copy.deepcopy(row)
    row.pop(key, None)
    return row


def cases() -> list:
    return [{"name": name, "row": row, "risky": OC.is_risky(row),
             "small": OC.is_small(row), "message": OC.approval_message(row)}
            for name, row in rows()]


def render() -> str:
    body = {
        "_about": ("Which approvals are risky (need Windows Hello on the PC, the "
                   "fingerprint or PIN on the phone) and which are SMALL (read-only, "
                   "approved by the card alone - the owner's request of 2026-11-01), and "
                   "what the check's prompt says. `risky`, `small` and `message` are "
                   "backend/jarvis_owner_check.py's own answers for each /api/pending "
                   "row; the desktop (lock/rules.rs) and the phone (SecurityRules) must "
                   "agree. Made by tools/gen_risky_approval_cases.py. Do not edit by "
                   "hand: re-run the tool."),
        "cases": cases(),
    }
    return json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        stale = [p for p in COPIES
                 if not p.is_file() or p.read_text(encoding="utf-8").replace("\r\n", "\n") != text]
        if stale:
            for p in stale:
                print(f"{p.relative_to(ROOT)} is out of date: run "
                      f"python3 tools/gen_risky_approval_cases.py")
            return 1
        print("risky-approval-cases.json (desktop and phone) matches the producer.")
        return 0
    for p in COPIES:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
