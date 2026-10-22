#!/usr/bin/env python3
"""check_schedule_actions.py - compare every schedule surface to the ONE contract.

    py -3 tools/check_schedule_actions.py                 # report; exit 0 while the
                                                          # surfaces' gaps are the ones
                                                          # the contract calls EXPECTED
    py -3 tools/check_schedule_actions.py --strict        # a pending gap is a failure
    py -3 tools/check_schedule_actions.py --json          # machine-readable report
    py -3 tools/check_schedule_actions.py --list-cases    # the (kind, state) cases used

THE CONTRACT is `contract/schedule-cases.json` (see `contract/README.md`): the one
`kind -> allowed actions + labels` table, derived from the real
`jarvis_schedule.Scheduler.act()` authority, the Kind registry, and Wave D-1's
`ready_for_review` marker. This tool does NOT decide what the table is - it reads
it, extracts each surface's own table from its source, and compares them.

WHY SOURCE EXTRACTION, NOT A RUNTIME IMPORT. `coming-up.js` is an ES module and
`Schedule.kt` is Kotlin, so neither can be imported by this Python checker; the HUD
table is inline in `jarvis_hud.html`. Each surface's table is therefore read out of
the exact known shape it has today (the function/const names are pinned in this
file, and an unrecognised shape is reported, never guessed at). A surface PR that
replaces its hand-written table with a generated one keeps passing because the
generated values still land in the same public constants; a PR that renames the
table must update this tool's `SURFACES` extraction in the same change.

XFAIL-WITH-REASON (the repo's honest equivalent: `skip`), stated where it lives:
`contract["surfaces"][name]["status"]` is `"pending"` for a surface that has not
consumed the contract yet, with `reason` and `owner` beside it. A pending surface's
mismatches are printed as `EXPECTED-GAP` lines and the tool exits 0 (CI is not red
for a known, named gap); `--strict` turns every one of them into a failure. When the
surface PR lands, it flips `status` to `"enforced"` and this tool becomes the
cross-surface test - mismatches are then failures. Nothing here edits a surface.

No network, no third-party dependency, no writes: reads the four files and prints.
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


# ---------------------------------------------------------------------------
#   Reading the contract and the surfaces
# ---------------------------------------------------------------------------


class SurfaceError(RuntimeError):
    """A surface's table could not be read in its known shape (reported, never guessed)."""


def load_contract(path: Path = None) -> dict:
    contract = json.loads(Path(path or DEFAULT_CONTRACT).read_text(encoding="utf-8"))
    if not isinstance(contract, dict) or contract.get("schema") != 1:
        raise SystemExit(f"{path or DEFAULT_CONTRACT}: not a schema-1 schedule contract")
    return contract


def surface_paths(contract: dict, repo: Path = None) -> dict:
    """{surface name: absolute Path} from the contract's own `surfaces` table."""
    root = Path(repo or REPO)
    return {name: root / spec["file"]
            for name, spec in (contract.get("surfaces") or {}).items()
            if spec.get("file")}


def _brace_block(text: str, start: int, *, open_ch: str = "{", close_ch: str = "}") -> str:
    """The `{...}` (or `(...)`) block starting at/after `start`, brace-aware."""
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
    """{action: label} from `{ do: "x", label: "Y" }` / `{ do: "x", label: "Y", danger: true }`."""
    out = {}
    for match in re.finditer(r'\{\s*do:\s*"([a-z_]+)",\s*label:\s*"([^"]+)"', block):
        out[match.group(1)] = match.group(2)
    return out


# ---------------------------------------------------------------------------
#   The HUD page (inline actionsFor(job, wentOff) + NO_PAUSE_KINDS)
# ---------------------------------------------------------------------------


def parse_hud(text: str) -> dict:
    block = _js_function_block(text, "function actionsFor(job, wentOff)")
    no_pause_block = _brace_block(text, text.find("var NO_PAUSE_KINDS"))
    labels = _js_label_entries(block)
    if "do: \"pause\"" not in block or "do: \"delete\"" not in block:
        raise SurfaceError("actionsFor does not contain the pause/delete entries")
    return {
        "labels": labels,
        "no_pause": set(re.findall(r'([a-z_]+)\s*:\s*true', no_pause_block)),
        "has_review": 'job.kind === "review"' in block,
        "has_todo": 'job.kind === "todo"' in block,
        "has_timer": 'job.kind === "timer"' in block,
        "has_add_time": 'do: "add_time"' in block,
        "has_waiting": 'job.state === "waiting"' in block,
        "has_pause_toggle": 'job.state === "paused"' in block,
        "has_ready": "ready_for_review" in text or "Ready for your review" in text,
    }


def hud_actions(parsed: dict, kind: str, state: str, went_off: bool) -> list:
    """The table `jarvis_hud.html`'s actionsFor() draws, for one fixture."""
    labels = parsed["labels"]

    def entry(action):
        if action not in labels:
            raise SurfaceError(f"HUD has an action {action!r} with no label")
        return action, labels[action]

    if went_off:
        return [entry("snooze"), entry("delete")]
    if kind == "review" and parsed["has_review"]:
        return []
    if state == "waiting" and parsed["has_waiting"]:
        return [entry("delete")]
    if kind == "todo" and parsed["has_todo"]:
        return [entry("done"), entry("delete")]
    out = []
    if kind == "timer" and parsed["has_timer"] and parsed["has_add_time"]:
        out.append(entry("add_time"))
    if kind not in parsed["no_pause"]:
        if state == "paused" and parsed["has_pause_toggle"]:
            out.append(entry("resume"))
        elif state == "active":
            out.append(entry("pause"))
    out.append(entry("delete"))
    return out


# ---------------------------------------------------------------------------
#   coming-up.js (the Brain window's list)
# ---------------------------------------------------------------------------


def parse_coming_up(text: str) -> dict:
    labels = {}
    for match in re.finditer(r'export const (\w+_LABEL)\s*=\s*"([^"]+)"', text):
        labels[match.group(1)] = match.group(2)
    if "PAUSE_LABEL" not in labels:
        raise SurfaceError("coming-up.js has no PAUSE_LABEL")
    went_off = re.search(r"export const WENT_OFF_ACTIONS\s*=\s*Object\.freeze\(\[([^\]]*)\]\)", text)
    if not went_off:
        raise SurfaceError("coming-up.js has no WENT_OFF_ACTIONS list")
    went_off_actions = re.findall(r'"([a-z_]+)"', went_off.group(1))
    block = _js_function_block(text, "function actionsOf(job)")
    label_block = _js_function_block(text, "function labelOf(action)")
    action_labels = {}
    for match in re.finditer(r"(\w+):\s*(\w+_LABEL)", label_block):
        if match.group(2) in labels:
            action_labels[match.group(1)] = labels[match.group(2)]
    if "pause" not in action_labels:
        raise SurfaceError("coming-up.js labelOf has no pause entry")
    return {"labels": action_labels, "went_off": went_off_actions,
            "actions_block": block, "source": text}


def coming_up_actions(parsed: dict, kind: str, state: str, went_off: bool) -> list:
    source = parsed["source"]
    block = parsed["actions_block"]
    labels = parsed["labels"]

    def entry(action):
        if action not in labels:
            raise SurfaceError(f"coming-up.js has an action {action!r} with no label")
        return action, labels[action]

    if went_off:
        return [entry(a) for a in parsed["went_off"]]
    # The surface's own branch lines, in the order the function checks them.
    for match in re.finditer(r'if\s*\(\s*job\.kind\s*===\s*"([a-z_]+)"\s*\)\s*return\s*\[([^\]]*)\];',
                             block):
        if match.group(1) == kind:
            return [entry(a) for a in re.findall(r'"([a-z_]+)"', match.group(2))]
    if re.search(r'if\s*\(\s*job\.state\s*===\s*"waiting"\s*\)\s*return\s*\[([^\]]*)\];', block):
        if state == "waiting":
            return [entry("delete")]
    if state == "paused":
        return [entry("resume"), entry("delete")]
    return [entry("pause"), entry("delete")]


# ---------------------------------------------------------------------------
#   Schedule.kt (the phone)
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


def parse_phone(text: str) -> dict:
    consts = {name: _kt_const(text, name)
              for name in ("PAUSE", "RESUME", "DELETE", "DONE", "SNOOZE")}
    labels = {"pause": consts["PAUSE"], "resume": consts["RESUME"],
              "delete": consts["DELETE"], "done": consts["DONE"],
              "snooze": consts["SNOOZE"]}
    next_time = _kt_const(text, "NEXT_TIME")
    went_off = _kt_list(text, "WENT_OFF_ACTIONS")
    act_actions = _kt_list(text, "ACTIONS")
    actions_block = _js_function_block(text, "fun actionsOf(job: Job)")
    label_block = _js_function_block(text, "fun labelOf(action: String)")
    # Extra names the phone is allowed to label; keep the same action labels.
    for match in re.finditer(r'"([a-z_]+)"\s*->\s*(PAUSE|RESUME|DELETE|DONE|SNOOZE)', label_block):
        labels[match.group(1)] = consts[match.group(2)]
    return {"labels": labels, "went_off": went_off, "act_actions": act_actions,
            "actions_block": actions_block, "next_time": next_time,
            "has_add_time": "add_time" in text and "add_time" in actions_block}


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
    if re.search(r'job\.state\s*==\s*"paused"\s*->\s*listOf\(([^)]*)\)', block):
        if state == "paused":
            return [entry("resume"), entry("delete")]
    return [entry("pause"), entry("delete")]


SURFACES = {
    "hud": {"parse": parse_hud, "actions": hud_actions, "ready": "Ready for your review"},
    "coming_up": {"parse": parse_coming_up, "actions": coming_up_actions, "ready": "Ready for your review"},
    "phone": {"parse": parse_phone, "actions": phone_actions, "ready": "Ready for your review"},
}


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
    """The reachable (kind, state) fixtures every surface is compared on."""
    cases = []
    for kind, spec in contract["kinds"].items():
        if not spec.get("listed"):
            continue
        states = spec.get("states") or {}
        for state, actions in states.items():
            if actions or state == "active":
                cases.append({"kind": kind, "state": state, "went_off": state == "fired"})
    cases.append({"kind": "todo", "state": "ready_for_review", "ready": True})
    return cases


def compare_surface(name: str, contract: dict, repo: Path = None) -> dict:
    spec = SURFACES[name]
    path = surface_paths(contract, repo)[name]
    meta = contract["surfaces"][name]
    report = {"name": name, "file": str(path), "status": meta.get("status", "pending"),
              "owner": meta.get("owner", ""), "reason": meta.get("reason", ""),
              "parse_error": "", "mismatches": [], "ready_marker": False,
              "cases": 0}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        report["parse_error"] = f"cannot read {path}: {exc}"
        return report
    try:
        parsed = spec["parse"](text)
    except SurfaceError as exc:
        report["parse_error"] = str(exc)
        return report
    report["ready_marker"] = (contract["states"]["ready_for_review"]["tag"].lower()
                              in text.lower())
    for case in surface_cases(contract):
        kind, state = case["kind"], case["state"]
        ready = bool(case.get("ready"))
        want = expected_actions(contract, kind, state, ready=ready)
        try:
            got = spec["actions"](parsed, kind, state, bool(case.get("went_off")))
        except SurfaceError as exc:
            report["parse_error"] = str(exc)
            return report
        report["cases"] += 1
        if want != got:
            report["mismatches"].append({"kind": kind, "state": state,
                                         "expected": want, "got": got})
    if not report["ready_marker"]:
        report["mismatches"].append({
            "kind": "todo", "state": "ready_for_review-marker",
            "expected": contract["states"]["ready_for_review"]["tag"], "got": ""})
    return report


def run(contract: dict = None, repo: Path = None, *, strict: bool = False) -> dict:
    contract = contract or load_contract()
    repo = Path(repo or REPO)
    reports = [compare_surface(name, contract, repo) for name in SURFACES]
    ok = True
    for report in reports:
        if report["parse_error"]:
            ok = False
        elif report["status"] == "enforced" and report["mismatches"]:
            ok = False
        elif report["status"] == "pending" and strict and report["mismatches"]:
            ok = False
    return {"contract": str(DEFAULT_CONTRACT), "strict": strict, "ok": ok,
            "surfaces": reports}


def _print_report(result: dict, *, quiet: bool = False) -> None:
    print(f"schedule action contract: {'STRICT' if result['strict'] else 'default'}"
          f" - {'OK' if result['ok'] else 'FAIL'}")
    for report in result["surfaces"]:
        status = report["status"]
        if report["parse_error"]:
            print(f"  {'PARSE':7s} {report['name']:9s} {report['parse_error']}")
            continue
        marker = "ok" if not report["mismatches"] else (
            "pending" if status == "pending" and not result["strict"] else "FAIL")
        print(f"  {marker:7s} {report['name']:9s} {report['cases']:3d} case(s)"
              f"  status={status}  mismatches={len(report['mismatches'])}")
        if quiet:
            continue
        for gap in report["mismatches"]:
            print(f"          EXPECTED-GAP {gap['kind']}.{gap['state']}:"
                  f" expected {gap['expected']!r}, got {gap['got']!r}")
        if report["mismatches"] and status == "pending":
            print(f"          owner: {report['owner']}")
            print(f"          reason: {report['reason']}")


def main(argv: list = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    parser.add_argument("--repo", default=str(REPO))
    parser.add_argument("--strict", action="store_true",
                        help="a pending surface's gap is a failure (for the PR that lands the last surface)")
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
