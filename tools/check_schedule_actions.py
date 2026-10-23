#!/usr/bin/env python3
"""check_schedule_actions.py - compare every schedule surface to the ONE contract.

    py -3 tools/check_schedule_actions.py                 # report; default run
    py -3 tools/check_schedule_actions.py --strict        # a non-xfail gap is a failure
    py -3 tools/check_schedule_actions.py --json          # machine-readable report
    py -3 tools/check_schedule_actions.py --list-cases    # the (kind, state) cases used

THE CONTRACT is `contract/schedule-cases.json` (see `contract/README.md`): the one
`kind -> allowed actions + labels` table, derived from the real
`jarvis_schedule.Scheduler.act()` authority, the Kind registry, and Wave D-1's
`ready_for_review` marker. This tool does NOT decide what the table is - it reads
it, extracts each surface's own table from its source, and compares them.

WHERE EACH SURFACE'S TABLE NOW LIVES (2026-10-22, coherence slice #729):
  * `jarvis-desktop/src/hud-actions.js` is the SHARED module every desktop
    surface reads: `ACTION_LABELS`, `WENT_OFF_ACTIONS`, `NO_PAUSE_KINDS`,
    `actionsFor()` and `actionNames()`. The HUD's Reminders panel imports it
    (`window.__hudActionsFor`) and keeps a browser-served FALLBACK table for a
    page with no module graph; the Brain's `coming-up.js` imports the same
    functions (`actionsOf` delegates to `actionNames`, `labelOf` reads
    `ACTION_LABELS`). Both are checked against the contract, and the HUD fallback
    is checked through the same cases as the shared module.
  * `jarvis-client/.../Schedule.kt` now offers `add_time` with the contract's
    label, so it is ENFORCED like the other two (consumed by the Android Q2/F5
    PR, 2026-10-23). No surface is pending any more; the pending/xfail machinery
    stays so a future surface can be reported honestly while it is consumed.

XFAIL-WITH-REASON (the repository's honest equivalent: `skip`). A surface whose
contract entry is `pending` must say `"xfail": true` with `owner` + `reason`; its
differences are printed as `EXPECTED-GAP` lines and the tool exits 0. `--strict`
turns a pending gap WITHOUT `xfail` (and every enforced-surface difference, and
every unreadable surface) into a failure - so the day a surface's owner removes
`xfail` (or flips `status` to `enforced`), CI starts biting. The suite exercises
that flip on a copy of the contract, so the switch is proven today.

The `ready_for_review` marker (Wave D-1, merged as #722) is on the backend and in
the contract, but no surface draws it yet (`states.ready_for_review.surface_status`
= "pending-d1-surfacing"); the tool reports that as a note, not as a surface
difference, because the marker's surface PR is still to come.

No network, no third-party dependency, no writes: reads the contract and the four
surface/shared files and prints.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_CONTRACT = REPO / "contract" / "schedule-cases.json"


class SurfaceError(RuntimeError):
    """A surface's table could not be read in its known shape (reported, never guessed)."""


# ---------------------------------------------------------------------------
#   Reading the contract and the files
# ---------------------------------------------------------------------------


def load_contract(path: Path = None) -> dict:
    contract = json.loads(Path(path or DEFAULT_CONTRACT).read_text(encoding="utf-8"))
    if not isinstance(contract, dict) or contract.get("schema") != 1:
        raise SystemExit(f"{path or DEFAULT_CONTRACT}: not a schema-1 schedule contract")
    return contract


def surface_paths(contract: dict, repo: Path = None) -> dict:
    root = Path(repo or REPO)
    return {name: root / spec["file"]
            for name, spec in (contract.get("surfaces") or {}).items()
            if spec.get("file")}


def shared_path(contract: dict, repo: Path = None) -> Path:
    spec = contract.get("shared") or {}
    if not spec.get("file"):
        raise SurfaceError("the contract does not name its shared table (`shared.file`)")
    return Path(repo or REPO) / spec["file"]


def _read(path: Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SurfaceError(f"cannot read {path}: {exc}") from exc


# ---------------------------------------------------------------------------
#   Small JS/Kotlin shape helpers (the shapes are pinned; an unknown one refuses)
# ---------------------------------------------------------------------------


def _brace_block(text: str, start: int, *, open_ch: str = "{", close_ch: str = "}") -> str:
    at = text.index(open_ch, start)
    depth = 0
    for i in range(at, len(text)):
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
            if depth == 0:
                return text[at:i + 1]
    raise SurfaceError(f"unterminated {open_ch} block after offset {start}")


def _js_function_block(text: str, signature: str) -> str:
    at = text.find(signature)
    if at < 0:
        raise SurfaceError(f"cannot find {signature!r}")
    return _brace_block(text, at)


def _js_label_entries(block: str) -> dict:
    out = {}
    for match in re.finditer(r'\{\s*do:\s*"([a-z_]+)",\s*label:\s*"([^"]+)"', block):
        out[match.group(1)] = match.group(2)
    return out


def _frozen_object(text: str, name: str) -> str:
    at = text.find(f"export const {name} = Object.freeze({{")
    if at < 0:
        raise SurfaceError(f"cannot find export const {name} = Object.freeze({{...}})")
    return _brace_block(text, at)


def _frozen_array(text: str, name: str) -> list:
    match = re.search(rf"export const {name}\s*=\s*Object\.freeze\(\[([^\]]*)\]\)", text)
    if not match:
        raise SurfaceError(f"cannot find export const {name} = Object.freeze([...])")
    return re.findall(r'"([a-z_]+)"', match.group(1))


def _labels_object(block: str) -> dict:
    return {m.group(1): m.group(2)
            for m in re.finditer(r"([a-z_]+)\s*:\s*\"([^\"]+)\"", block)}


# ---------------------------------------------------------------------------
#   The shared module: hud-actions.js (the ONE desktop table since #729)
# ---------------------------------------------------------------------------


def parse_shared(text: str) -> dict:
    labels = _labels_object(_frozen_object(text, "ACTION_LABELS"))
    went_off = _frozen_array(text, "WENT_OFF_ACTIONS")
    no_pause = _frozen_array(text, "NO_PAUSE_KINDS")
    block = _js_function_block(text, "export function actionsFor(")
    for needle in ('kind === "review"', 'state === "waiting"', 'kind === "todo"',
                   'kind === "timer"', 'state === "active"', 'state === "paused"',
                   "WENT_OFF_ACTIONS.map"):
        if needle not in block:
            raise SurfaceError(f"shared actionsFor is missing {needle!r}")
    if 'kind === "timer"' not in _js_function_block(text, "export function kindAllowsAddTime("):
        raise SurfaceError("shared kindAllowsAddTime does not name a timer")
    return {"labels": labels, "went_off": went_off, "no_pause": set(no_pause)}


def shared_actions(parsed: dict, kind: str, state: str, went_off: bool) -> list:
    labels = parsed["labels"]

    def entry(action):
        if action not in labels:
            raise SurfaceError(f"the table has an action {action!r} with no label")
        return action, labels[action]

    if went_off:
        return [entry(a) for a in parsed["went_off"]]
    if kind == "review":
        return []
    if state == "waiting":
        return [entry("delete")]
    if kind == "todo":
        return [entry("done"), entry("delete")]
    out = []
    if kind == "timer":
        out.append(entry("add_time"))
    if kind not in parsed["no_pause"]:
        if state == "active":
            out.append(entry("pause"))
        elif state == "paused":
            out.append(entry("resume"))
    out.append(entry("delete"))
    return out


# ---------------------------------------------------------------------------
#   The HUD page: the shared module's import + the browser-served fallback table
# ---------------------------------------------------------------------------


def parse_hud(repo: Path, contract: dict, shared: dict) -> dict:
    text = _read(surface_paths(contract, repo)["hud"])
    if "hud-actions.js" not in text or "window.__hudActionsFor" not in text:
        raise SurfaceError("the HUD page does not import the shared hud-actions.js table")
    block = _js_function_block(text, "function fallbackActionsFor(job, wentOff)")
    labels = _js_label_entries(block)
    no_pause_block = _brace_block(text, text.find("var NO_PAUSE_KINDS"))
    no_pause = set(re.findall(r"([a-z_]+)\s*:\s*true", no_pause_block))
    for needle in ('job.kind === "review"', 'job.state === "waiting"', 'job.kind === "todo"',
                   'job.kind === "timer"', 'job.state === "active"', 'job.state === "paused"'):
        if needle not in block:
            raise SurfaceError(f"the HUD fallback table is missing {needle!r}")
    if "window.__hudActionsFor" not in _js_function_block(text, "function actionsFor(job, wentOff)"):
        raise SurfaceError("the HUD actionsFor() never reads the shared window.__hudActionsFor")
    return {"labels": labels, "went_off": ["snooze", "delete"], "no_pause": no_pause,
            "shared": shared, "source": "inline fallback + shared module"}


def hud_actions(parsed: dict, kind: str, state: str, went_off: bool) -> list:
    return shared_actions(parsed, kind, state, went_off)


# ---------------------------------------------------------------------------
#   coming-up.js: a pure consumer of the shared module
# ---------------------------------------------------------------------------


def parse_coming_up(repo: Path, contract: dict, shared: dict) -> dict:
    text = _read(surface_paths(contract, repo)["coming_up"])
    if 'from "./hud-actions.js"' not in text:
        raise SurfaceError("coming-up.js does not import the shared hud-actions.js table")
    for needle in ("ACTION_LABELS", "WENT_OFF_ACTIONS as SHARED_WENT_OFF_ACTIONS", "actionNames"):
        if needle not in text:
            raise SurfaceError(f"coming-up.js does not import {needle!r} from the shared table")
    actions_block = _js_function_block(text, "export function actionsOf(job)")
    if "actionNames(job, false)" not in actions_block:
        raise SurfaceError("coming-up.js actionsOf does not delegate to the shared actionNames()")
    label_block = _js_function_block(text, "export function labelOf(action)")
    if "add_time: ACTION_LABELS.add_time" not in label_block:
        raise SurfaceError("coming-up.js labelOf does not read the shared add_time label")
    if "export const WENT_OFF_ACTIONS = SHARED_WENT_OFF_ACTIONS" not in text:
        raise SurfaceError("coming-up.js no longer re-exports the shared WENT_OFF_ACTIONS")
    return dict(shared, source="shared hud-actions.js")


def coming_up_actions(parsed: dict, kind: str, state: str, went_off: bool) -> list:
    return shared_actions(parsed, kind, state, went_off)


# ---------------------------------------------------------------------------
#   Schedule.kt (the phone): still its own hand-written table (pending Session B)
# ---------------------------------------------------------------------------


def _kt_const(text: str, name: str) -> str:
    match = re.search(rf'const val {name}\s*=\s*"([^"]+)"', text)
    if not match:
        raise SurfaceError(f"Schedule.kt has no const val {name}")
    return match.group(1)


def _kt_list(text: str, name: str) -> list:
    match = re.search(rf"val {name}\s*=\s*listOf\(([^)]*)\)", text)
    if not match:
        raise SurfaceError(f"Schedule.kt has no val {name} = listOf(...)")
    return re.findall(r'"([a-z_]+)"', match.group(1))


def parse_phone(repo: Path, contract: dict, shared: dict) -> dict:
    text = _read(surface_paths(contract, repo)["phone"])
    consts = {name: _kt_const(text, name)
              for name in ("PAUSE", "RESUME", "DELETE", "DONE", "SNOOZE", "ADD_TIME")}
    labels = {"pause": consts["PAUSE"], "resume": consts["RESUME"],
              "delete": consts["DELETE"], "done": consts["DONE"],
              "snooze": consts["SNOOZE"], "add_time": consts["ADD_TIME"]}
    next_time = _kt_const(text, "NEXT_TIME")
    went_off = _kt_list(text, "WENT_OFF_ACTIONS")
    act_actions = _kt_list(text, "ACTIONS")
    actions_block = _js_function_block(text, "fun actionsOf(job: Job)")
    label_block = _js_function_block(text, "fun labelOf(action: String)")
    for match in re.finditer(
            r'"([a-z_]+)"\s*->\s*(PAUSE|RESUME|DELETE|DONE|SNOOZE|ADD_TIME)',
            label_block):
        labels[match.group(1)] = consts[match.group(2)]
    return {"labels": labels, "went_off": went_off, "act_actions": act_actions,
            "actions_block": actions_block, "next_time": next_time,
            "has_add_time": bool("add_time" in act_actions or "add_time" in actions_block),
            "source": "hand-written"}


def phone_actions(parsed: dict, kind: str, state: str, went_off: bool) -> list:
    block = parsed["actions_block"]
    labels = parsed["labels"]

    def entry(action):
        if action not in labels:
            raise SurfaceError(f"Schedule.kt has an action {action!r} with no label")
        return action, labels[action]

    if went_off:
        return [entry(a) for a in parsed["went_off"]]
    for match in re.finditer(r'job\.kind\s*==\s*"([a-z_]+)"\s*->\s*emptyList\(\)', block):
        if match.group(1) == kind:
            return []
    for match in re.finditer(r'job\.kind\s*==\s*"([a-z_]+)"\s*->\s*listOf\(([^)]*)\)', block):
        if match.group(1) == kind:
            return [entry(a) for a in re.findall(r'"([a-z_]+)"', match.group(2))]
    if re.search(r"job\.kind\s*==\s*NEXT_TIME\s*->\s*listOf\(([^)]*)\)", block):
        if kind == parsed["next_time"]:
            return [entry("delete")]
    if re.search(r'job\.state\s*==\s*"waiting"\s*->\s*listOf\(([^)]*)\)', block):
        if state == "waiting":
            return [entry("delete")]
    state_when = re.search(
        r'job\.kind\s*==\s*"([a-z_]+)"\s*->\s*when\s*\(job\.state\)\s*\{(.*?)\n\s*\}',
        block, re.S)
    if state_when is not None and state_when.group(1) == kind:
        body = state_when.group(2)
        for state_match in re.finditer(
                r'"([a-z_]+)"\s*->\s*listOf\(([^)]*)\)', body):
            if state_match.group(1) == state:
                return [entry(a) for a in re.findall(r'"([a-z_]+)"', state_match.group(2))]
        fallback = re.search(r'else\s*->\s*listOf\(([^)]*)\)', body)
        if fallback is not None:
            return [entry(a) for a in re.findall(r'"([a-z_]+)"', fallback.group(1))]
        return []
    if re.search(r'job\.state\s*==\s*"paused"\s*->\s*listOf\(([^)]*)\)', block):
        if state == "paused":
            return [entry("resume"), entry("delete")]
    return [entry("pause"), entry("delete")]


# ---------------------------------------------------------------------------
#   The comparison
# ---------------------------------------------------------------------------


def expected_actions(contract: dict, kind: str, state: str, *, ready: bool = False) -> list:
    if ready:
        actions = contract["states"]["ready_for_review"]["actions"]
    else:
        actions = (contract["kinds"].get(kind) or {}).get("states", {}).get(state, [])
    labels = contract["labels"]
    return [(action, labels[action]["label"]) for action in actions]


def surface_cases(contract: dict) -> list:
    """The reachable (kind, state) action cases every surface must draw the same."""
    cases = []
    for kind, spec in contract["kinds"].items():
        if not spec.get("listed") or spec.get("surface_compare") is False:
            continue
        for state, actions in (spec.get("states") or {}).items():
            if state == "ready_for_review":
                continue            # the D-1 marker is not drawn by any surface yet
            if actions or state == "active":
                cases.append({"kind": kind, "state": state, "went_off": state == "fired"})
    return cases


SURFACE_SPECS = {
    "hud": (parse_hud, hud_actions),
    "coming_up": (parse_coming_up, coming_up_actions),
    "phone": (parse_phone, phone_actions),
}


def compare_surface(name: str, contract: dict, repo: Path = None) -> dict:
    parse, actions = SURFACE_SPECS[name]
    path = surface_paths(contract, repo)[name]
    meta = contract["surfaces"][name]
    report = {"name": name, "file": str(path), "status": meta.get("status", "pending"),
              "xfail": bool(meta.get("xfail")), "owner": meta.get("owner", ""),
              "reason": meta.get("reason", ""), "parse_error": "",
              "mismatches": [], "ready_marker": False, "cases": 0}
    try:
        shared = parse_shared(_read(shared_path(contract, repo)))
        parsed = parse(Path(repo or REPO), contract, shared)
    except SurfaceError as exc:
        report["parse_error"] = str(exc)
        return report
    report["ready_marker"] = (contract["states"]["ready_for_review"]["tag"].lower()
                              in _read(path).lower())
    for case in surface_cases(contract):
        kind, state = case["kind"], case["state"]
        try:
            got = actions(parsed, kind, state, bool(case.get("went_off")))
        except SurfaceError as exc:
            report["parse_error"] = str(exc)
            return report
        report["cases"] += 1
        want = expected_actions(contract, kind, state)
        if want != got:
            report["mismatches"].append({"kind": kind, "state": state,
                                         "expected": want, "got": got})
    return report


def _notes(contract: dict, reports: list) -> list:
    """Contract entries that are deliberately outside the surface comparison yet."""
    notes = []
    spec = (contract.get("states") or {}).get("ready_for_review") or {}
    if spec and not any(report.get("ready_marker") for report in reports):
        notes.append("ready_for_review marker: " + str(spec.get("surface_status", "pending"))
                     + " - " + str(spec.get("surface_note")
                                  or "Wave D-1's marker is on the backend; no surface draws it yet."))
    for kind, spec in (contract.get("kinds") or {}).items():
        if spec.get("listed") and spec.get("surface_compare") is False:
            notes.append(f"{kind} kind: not in the cross-surface comparison yet - "
                         + str(spec.get("surface_note") or "owned by its own module"))
    return notes


def run(contract: dict = None, repo: Path = None, *, strict: bool = False) -> dict:
    contract = contract or load_contract()
    repo = Path(repo or REPO)
    reports = [compare_surface(name, contract, repo) for name in SURFACE_SPECS]
    notes = _notes(contract, reports)
    ok = True
    for report in reports:
        if report["parse_error"]:
            ok = False
        elif report["status"] == "enforced" and report["mismatches"]:
            ok = False
        elif report["status"] == "pending" and strict and report["mismatches"] \
                and not report["xfail"]:
            ok = False
    return {"contract": str(DEFAULT_CONTRACT), "strict": strict, "ok": ok,
            "surfaces": reports, "notes": notes}


def _print_report(result: dict, *, quiet: bool = False) -> None:
    print(f"schedule action contract: {'STRICT' if result['strict'] else 'default'}"
          f" - {'OK' if result['ok'] else 'FAIL'}")
    for report in result["surfaces"]:
        status = report["status"]
        if report["parse_error"]:
            print(f"  {'PARSE':7s} {report['name']:9s} {report['parse_error']}")
            continue
        pending_ok = status == "pending" and report["xfail"]
        marker = "ok" if not report["mismatches"] else (
            "xfail" if pending_ok else "FAIL")
        print(f"  {marker:7s} {report['name']:9s} {report['cases']:3d} case(s)"
              f"  status={status}{' xfail' if report['xfail'] else ''}"
              f"  mismatches={len(report['mismatches'])}")
        if quiet:
            continue
        for gap in report["mismatches"]:
            print(f"          EXPECTED-GAP {gap['kind']}.{gap['state']}:"
                  f" expected {gap['expected']!r}, got {gap['got']!r}")
        if report["mismatches"] and status == "pending":
            print(f"          owner: {report['owner']}")
            print(f"          reason: {report['reason']}")
    if not quiet:
        for note in result.get("notes") or []:
            print(f"  note    {note}")


def main(argv: list = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    parser.add_argument("--repo", default=str(REPO))
    parser.add_argument("--strict", action="store_true",
                        help="a pending surface without an explicit xfail is a failure")
    parser.add_argument("--json", action="store_true", help="print the JSON report")
    parser.add_argument("--list-cases", action="store_true", help="print the comparison cases")
    args = parser.parse_args(argv)
    contract = load_contract(Path(args.contract))
    if args.list_cases:
        for case in surface_cases(contract):
            print(case)
        return 0
    result = run(contract, Path(args.repo), strict=args.strict)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_report(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
