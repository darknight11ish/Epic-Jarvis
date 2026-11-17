#!/usr/bin/env python3
"""Jarvis coding & hybrid routing benchmark - the repeatable harness.

    py -3 tools\\bench_coding\\run.py                  # the runnable rows, end to end
    py -3 tools\\bench_coding\\run.py --dry            # list the rows and exits
    py -3 tools\\bench_coding\\run.py --self-test      # the harness's own suite
    py -3 tools\\bench_coding\\run.py --json-out out.json --report report.md

WHAT IT IS. The measurement half of the 2026-11-16 spec
(`for_deepseek_2026_11_16_2023pt_jarvis_coding_and_hybrid_benchmark.md`). It
drives the LIVE backend at http://127.0.0.1:4719 the way a client does - the
pairing token, `X-Jarvis-Client: hud`, `POST /api/chat` - runs each coding task
in a NEW disposable `git` repository with no remote, applies the answer's own
file blocks, and judges the row from the exact command's exit code, never from
the answer's words.

WHAT IT IS NOT. It is not `backend/jarvis_bench.py`. That module measures a
MODEL: tokens a second, RAM/GPU placement, context sizes, across repeats. This
measures TASK OUTCOMES through the whole live product - which lane answered,
whether the code passed its real tests, what the cloud cost, what was touched.
Neither owns the other's numbers; the boundary is written out in
`tools/bench_coding/README.md`.

WHAT IT WILL NOT DO, EVER.

  * It never writes to, commits to, or checks out a branch in this checkout.
    Every repository it makes is a new folder under
    `%LOCALAPPDATA%\\Jarvis\\bench-coding`, with no remote at all.
  * It never approves a card. There is no approve route in this module. It
    DOES decline a card that appears during one of its own turns - a no
    executes nothing - because otherwise a tool call the model makes would
    hold the turn for the card's whole lifetime. Each such card is recorded.
  * It never prints, logs or writes the pairing token.
  * It never flips a setting, starts a model or switches a preset unless
    `--apply-preset` is passed - and even then it cannot answer the card a
    Coding apply raises, so it reports what happened instead of forcing it.
  * It never counts BLOCKED as a pass.

EXIT CODES. 0 = every row that ran passed (BLOCKED rows do not fail the run,
they are counted on their own line); 1 = a row that ran failed; 2 = the run
could not start (no token, no live backend, no benchmark Python environment).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cases  # noqa: E402
import fixture  # noqa: E402
import grade  # noqa: E402
import report as report_mod  # noqa: E402
import telemetry  # noqa: E402
from client import Blocked, JarvisClient, one_line, scrub  # noqa: E402

REPO = HERE.parents[1]
SCHEMA = "jarvis-bench-coding/1"
DEFAULT_BASE_URL = "http://127.0.0.1:4719"


# ---------------------------------------------------------------------------
#   small helpers
# ---------------------------------------------------------------------------


def now_stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def run_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def tail(text: str, limit: int = 4000) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[-limit:]


def read(path: Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def command_line(result: dict) -> str:
    return f"{result.get('command', '')} -> exit {result.get('exit')}"


def default_runs_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "Jarvis" / "bench-coding" / "runs"


def harness_facts() -> dict:
    """Which tree and commit the tool itself came from (read-only)."""
    facts = {"path": str(HERE)}
    try:
        done = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=30)
        facts["commit"] = (done.stdout or "").strip()
        done = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--abbrev-ref",
                               "HEAD"], capture_output=True, text=True, timeout=30)
        facts["branch"] = (done.stdout or "").strip()
    except Exception as exc:  # noqa: BLE001
        facts["error"] = one_line(exc, 160)
    return facts


def blank_result(case: cases.Case) -> dict:
    return {
        "id": case.id,
        "tier": case.tier,
        "title": case.title,
        "criterion": case.criterion,
        "status": "NOT-RUN",
        "reason": "",
        "prompt": "",
        "turns": [],
        "commands": [],
        "files": {},
        "checks": {},
        "attempts": 0,
        "rounds": 0,
        "route": {},
        "routes": [],
        "tokens": None,
        "prompt_tokens": None,
        "tokens_per_s": None,
        "cloud_dollars": None,
        "seconds": 0.0,
        "blocked": case.blocked,
        "notes": dict(case.notes),
    }


def summarize_telemetry(result: dict) -> None:
    """Fill the per-row totals from its turns, without inventing a number."""
    chosen = [turn.get("speed", {}).get("chosen") or {}
              for turn in result.get("turns") or []]
    rows = [row for row in chosen if row]
    tokens = [row.get("tokens") for row in rows if isinstance(row.get("tokens"), (int, float))]
    prompts = [row.get("prompt_tokens") for row in rows
               if isinstance(row.get("prompt_tokens"), (int, float))]
    speeds = [row.get("tokens_per_s") for row in rows
              if isinstance(row.get("tokens_per_s"), (int, float))]
    words_speeds = [row.get("words_per_s") for row in rows
                    if isinstance(row.get("words_per_s"), (int, float))]
    result["tokens"] = int(sum(tokens)) if tokens else None
    result["prompt_tokens"] = int(sum(prompts)) if prompts else None
    result["tokens_per_s"] = round(sum(speeds) / len(speeds), 2) if speeds else None
    result["words_per_s"] = (round(sum(words_speeds) / len(words_speeds), 2)
                             if words_speeds else None)
    money = [turn.get("cloud", {}).get("dollars") or 0.0
             for turn in result.get("turns") or []]
    result["cloud_dollars"] = round(sum(money), 9) if result.get("turns") else None
    result["attempts"] = len(result.get("turns") or [])
    result["approval_cards"] = []
    for index, item in enumerate(result.get("turns") or [], 1):
        declined = item.get("declined_cards") or []
        if declined:
            result["approval_cards"].append({"turn": index, "declined": declined})
    if result.get("turns"):
        result["route"] = result["turns"][-1].get("route") or {}
        result["routes"] = [turn.get("route") or {} for turn in result["turns"]]


def do_turn(jc: JarvisClient, text: str, *, conversation_id: str) -> dict:
    """One chat turn with every measurable fact around it captured."""
    speed_before = telemetry.speed_count()
    money_before = telemetry.money_total()
    pending_before = jc.pending()
    started = time.time()
    reply = jc.chat(text, conversation_id=conversation_id)
    ended = time.time()
    speed_after = telemetry.speed_count()
    rows = telemetry.speed_delta(speed_before, speed_after)
    attribution = telemetry.attribute_turn(
        rows, started, ended, str((reply.route or {}).get("lane") or ""))
    money_after = telemetry.money_total()
    pending_after = jc.pending()
    declined = list(reply.declined)
    before_ids = set(pending_before.get("ids") or [])
    already = {str(item.get("id")) for item in declined}
    for card_id in set(pending_after.get("ids") or []) - before_ids - already:
        record = jc.decline_card(card_id)
        record["action"] = "(raised during the turn)"
        declined.append(record)
    if declined:
        pending_after = jc.pending()
    return {
        "at": now_stamp(),
        "prompt": scrub(text, jc.token),
        "answer": scrub(reply.answer, jc.token),
        "status": reply.status,
        "route": reply.route,
        "route_raw": scrub(reply.route_raw, jc.token),
        "error": scrub(reply.error, jc.token),
        "timed_out": reply.timed_out,
        "http_attempts": reply.attempts,
        "seconds": reply.seconds,
        "speed": attribution,
        "cloud": telemetry.money_delta(money_before, money_after),
        "pending_before": pending_before,
        "pending_after": pending_after,
        "declined_cards": declined,
    }


def turn_row(turn: dict, secret: str = "") -> dict:
    """One turn as it is written to the JSON - scrubbed, never the token."""
    return {
        key: scrub(value, secret) if isinstance(value, str) else value
        for key, value in turn.items()
    }


# ---------------------------------------------------------------------------
#   the four rows this PC can measure tonight
# ---------------------------------------------------------------------------


def run_t1_1(jc: JarvisClient, env: dict, run_dir: Path, secret: str) -> dict:
    """Single-file bug fix: <= 2 attempts, the scoped test passes, one file."""
    case = cases.case("T1.1")
    result = blank_result(case)
    started = time.time()
    repo = fixture.build(run_dir / "T1.1")
    target = fixture.SINGLE_FILE_TASKS["or_query"]
    test_path = fixture.DEFECT_TESTS["or_query"]
    initial = grade.pytest(repo, test_path, env["python"])
    source = read(repo / target)
    test_source = read(repo / test_path)
    result["commands"].append(initial)
    prompt = cases.PROMPT_T1_1.format(
        repo=repo, source=source, test_source=test_source,
        test_output=tail((initial.get("out") or "") + (initial.get("err") or "")),
    )
    result["prompt"] = prompt
    conversation = f"bench-coding-T1.1-{run_stamp()}"
    turn = do_turn(jc, prompt, conversation_id=conversation)
    result["turns"].append(turn)
    parsed = grade.extract_changes(turn["answer"], target)
    applied = grade.apply_changes(repo, parsed["changes"])
    scoped = grade.pytest(repo, test_path, env["python"])
    ruff_result = grade.ruff(repo, env["ruff"])
    result["commands"] += [scoped, ruff_result]
    result["checks"]["answer_shape"] = parsed["shape"]
    result["checks"]["applied"] = applied
    if scoped.get("exit") != 0:
        current = read(repo / target)
        retry_prompt = cases.PROMPT_T1_1_RETRY.format(
            test_output=tail((scoped.get("out") or "") + (scoped.get("err") or "")),
            current=current,
        )
        retry_turn = do_turn(jc, retry_prompt, conversation_id=conversation)
        result["turns"].append(retry_turn)
        parsed = grade.extract_changes(retry_turn["answer"], target)
        applied2 = grade.apply_changes(repo, parsed["changes"])
        scoped = grade.pytest(repo, test_path, env["python"])
        ruff_result = grade.ruff(repo, env["ruff"])
        result["commands"] += [scoped, ruff_result]
        result["checks"]["answer_shape_2"] = parsed["shape"]
        result["checks"]["applied_2"] = applied2
    snapshot = telemetry.git_snapshot(repo)
    result["files"] = snapshot
    summarize_telemetry(result)
    route = result.get("route") or {}
    where = str(route.get("where") or "")
    lane_text = str(route.get("lane") or "").lower()
    route_present = bool(route)
    cloud_names = any(token in lane_text for token in
                      ("deepseek", "gpt-", "claude", "gemini", "grok"))
    route_is_local = bool(route_present and (
        where == "local" if where else (not cloud_names and not route.get("auto"))))
    cards = []
    for index, item in enumerate(result["turns"], 1):
        declined = item.get("declined_cards") or []
        if declined:
            cards.append({"turn": index, "declined": declined})
    checks = {
        "test_exit": scoped.get("exit"),
        "test_passes": scoped.get("exit") == 0,
        "ruff_exit": ruff_result.get("exit"),
        "ruff_clean": ruff_result.get("exit") == 0,
        "attempts": len(result["turns"]),
        "attempts_at_most_two": len(result["turns"]) <= 2,
        "changed_paths": snapshot.get("changed_paths"),
        "touches_only_one_file": snapshot.get("changed_paths") == [target],
        "route": {key: route.get(key) for key in
                  ("lane", "where", "gate", "reason", "auto", "tainted", "offer")},
        "route_present": route_present,
        "route_is_local": route_is_local,
        "approval_cards_raised": cards,
        "cloud_dollars": result["cloud_dollars"],
        "cloud_is_zero": (result["cloud_dollars"] or 0) == 0,
    }
    result["checks"].update(checks)
    failures = []
    if not checks["test_passes"]:
        failures.append("the exact test command did not pass")
    if not checks["touches_only_one_file"]:
        failures.append("it touched " + (
            ", ".join(checks["changed_paths"] or []) or "no file"))
    if not checks["attempts_at_most_two"]:
        failures.append("more than two attempts")
    if not checks["route_present"]:
        failures.append("the answer carried no X-Jarvis-Route header")
    elif not checks["route_is_local"]:
        failures.append("a non-local lane answered")
    if not checks["cloud_is_zero"]:
        failures.append("cloud spend moved")
    result["status"] = "PASS" if not failures else "FAIL"
    note = ""
    if cards:
        note = ("; it raised approval card(s) the harness DECLINED (a no, nothing "
                "executed): " + ", ".join(
                    str(item.get("action")) for card in cards
                    for item in card.get("declined") or []))
    result["reason"] = (
        ("the scoped test passes, one file changed, "
         f"{checks['attempts']} attempt(s), local and $0" if not failures
         else "; ".join(failures)) + note)
    result["seconds"] = round(time.time() - started, 2)
    return result


def run_t1_2(jc: JarvisClient, env: dict, run_dir: Path, secret: str) -> dict:
    """Unit-test generation: four edge-case tests, source untouched, they pass."""
    case = cases.case("T1.2")
    result = blank_result(case)
    started = time.time()
    repo = fixture.build(run_dir / "T1.2")
    source_path = repo / "src" / "shop" / "discount.py"
    before = grade.sha256(source_path)
    prompt = cases.PROMPT_T1_2.format(source=read(source_path))
    result["prompt"] = prompt
    conversation = f"bench-coding-T1.2-{run_stamp()}"
    turn = do_turn(jc, prompt, conversation_id=conversation)
    result["turns"].append(turn)
    parsed = grade.extract_changes(turn["answer"], "tests/test_discount_edges.py")
    applied = grade.apply_changes(repo, parsed["changes"])
    new_file = repo / "tests" / "test_discount_edges.py"
    generated = read(new_file)
    scoped = grade.pytest(repo, "tests/test_discount_edges.py", env["python"])
    ruff_result = grade.ruff(repo, env["ruff"])
    result["commands"] += [scoped, ruff_result]
    names = grade.test_functions(generated)
    coverage = grade.edge_case_coverage(generated)
    after = grade.sha256(source_path)
    snapshot = telemetry.git_snapshot(repo)
    result["files"] = snapshot
    summarize_telemetry(result)
    total = (result["cloud_dollars"] or 0)
    checks = {
        "answer_shape": parsed["shape"],
        "applied": applied,
        "new_file_exists": new_file.is_file(),
        "test_functions": names,
        "at_least_four_tests": len(names) >= 4,
        "edge_coverage": coverage,
        "source_unchanged": before == after,
        "test_exit": scoped.get("exit"),
        "tests_pass": scoped.get("exit") == 0,
        "ruff_exit": ruff_result.get("exit"),
        "changed_paths": snapshot.get("changed_paths"),
        "cloud_dollars": total,
    }
    result["checks"].update(checks)
    failures = []
    if not checks["at_least_four_tests"]:
        failures.append(f"only {len(names)} test function(s)")
    if not coverage["covered"]:
        failures.append("edge coverage missing: " + ", ".join(coverage["missing"]))
    if not checks["source_unchanged"]:
        failures.append("it changed src/shop/discount.py")
    if not checks["tests_pass"]:
        failures.append("the generated tests did not pass")
    if not checks["new_file_exists"]:
        failures.append("no test file was written")
    result["status"] = "PASS" if not failures else "FAIL"
    result["reason"] = (
        f"{len(names)} tests, edge coverage met, source untouched, exit 0"
        if not failures else "; ".join(failures))
    result["seconds"] = round(time.time() - started, 2)
    return result


def _gh(argv: list[str], *, timeout: int = 120) -> dict:
    try:
        done = subprocess.run(["gh", *argv], capture_output=True, text=True,
                              timeout=timeout)
    except FileNotFoundError:
        return {"ok": False, "error": "gh is not installed"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"gh did not answer within {timeout}s"}
    if done.returncode != 0:
        return {"ok": False, "error": one_line(done.stderr or done.stdout, 200)}
    try:
        return {"ok": True, "data": json.loads(done.stdout or "[]")}
    except ValueError:
        return {"ok": False, "error": "gh answered with something that is not JSON"}


def run_t1_3(jc: JarvisClient, env: dict, run_dir: Path, secret: str) -> dict:
    """GitHub read & search: matches `gh pr list`, real repos, no write tool."""
    case = cases.case("T1.3")
    result = blank_result(case)
    started = time.time()
    listed = _gh(["pr", "list", "--repo", "darknight11ish/Epic-Jarvis",
                  "--state", "open", "--limit", "100",
                  "--json", "number,title,url"])
    if not listed.get("ok"):
        result["status"] = "BLOCKED"
        result["reason"] = ("the ground truth could not be read: "
                            + (listed.get("error") or "gh failed"))
        result["seconds"] = round(time.time() - started, 2)
        return result
    truth = {int(pr["number"]) for pr in listed.get("data") or []
             if isinstance(pr, dict) and str(pr.get("number", "")).isdigit()}
    titles = {int(pr["number"]): pr.get("title") or "" for pr in listed.get("data") or []
              if isinstance(pr, dict) and str(pr.get("number", "")).isdigit()}
    result["checks"]["ground_truth_prs"] = sorted(truth)
    result["checks"]["ground_truth_titles"] = titles
    prompt = cases.PROMPT_T1_3
    result["prompt"] = prompt
    conversation = f"bench-coding-T1.3-{run_stamp()}"
    turn = do_turn(jc, prompt, conversation_id=conversation)
    result["turns"].append(turn)
    answer = turn["answer"]
    found = grade.parse_github_numbers(answer)
    urls = grade.github_urls(answer)
    missing = sorted(truth - found)
    invented = sorted(found - truth)
    verified: list[dict] = []
    for url in urls[:8]:
        repo_name = url[len("https://github.com/"):]
        checked = _gh(["api", f"repos/{repo_name}", "--jq", ".full_name"],
                      timeout=60)
        verified.append({
            "url": url,
            "real": bool(checked.get("ok")),
            "error": checked.get("error") or "",
        })
    snapshot = telemetry.git_snapshot(run_dir / "T1.3-no-repo") if (
        run_dir / "T1.3-no-repo").exists() else {"note": "no repository for T1.3"}
    result["files"] = snapshot
    summarize_telemetry(result)
    pending_raised = (turn.get("pending_after", {}).get("pending") or 0) > (
        turn.get("pending_before", {}).get("pending") or 0)
    declined_actions = [str(item.get("action") or "")
                        for item in (turn.get("declined_cards") or [])]
    gated_tools = [action for action in declined_actions
                   if action in ("github_search_run_authenticated", "search_the_web")]
    checks = {
        "pr_numbers_in_answer": sorted(found),
        "missing_prs": missing,
        "invented_pr_numbers": invented,
        "pr_list_matches": not missing and not invented,
        "github_urls": urls,
        "urls_found": len(urls),
        "urls_verified": verified,
        "all_urls_real": bool(urls) and all(item["real"] for item in verified),
        "write_card_raised": pending_raised,
        "declined_cards": declined_actions,
        "gated_tools_declined": gated_tools,
        "pending_before": turn.get("pending_before"),
        "pending_after": turn.get("pending_after"),
        "route": {key: (turn.get("route") or {}).get(key) for key in
                  ("lane", "where", "gate", "reason")},
    }
    result["checks"].update(checks)
    if gated_tools:
        result["status"] = "BLOCKED"
        result["reason"] = (
            "the task needs the authenticated GitHub tools "
            + ", ".join(sorted(set(gated_tools)))
            + ", and each raises an ask-tier card. This harness never approves a "
              "card, so it declined them and the model could not read GitHub. "
              "T1.3 is BLOCKED on an owner's yes (or on a read tool that raises "
              "no card); it is not a measured product failure.")
        result["seconds"] = round(time.time() - started, 2)
        return result
    failures = []
    if missing:
        failures.append("missed open PRs: " + ", ".join(f"#{n}" for n in missing))
    if invented:
        failures.append("invented PR numbers: " + ", ".join(f"#{n}" for n in invented))
    if not checks["all_urls_real"]:
        failures.append("no verified real repository URL")
    if pending_raised:
        failures.append("an approval card was raised (a write tool may have run)")
    if checks["urls_found"] < 3:
        failures.append(f"only {checks['urls_found']} repository URL(s)")
    result["status"] = "PASS" if not failures else "FAIL"
    result["reason"] = (
        f"{len(found)} of {len(truth)} open PRs matched, "
        f"{sum(1 for v in verified if v['real'])} real repo URL(s), no write card"
        if not failures else "; ".join(failures))
    result["seconds"] = round(time.time() - started, 2)
    return result


def run_t2_3(jc: JarvisClient, env: dict, run_dir: Path, secret: str) -> dict:
    """Multi-file refactor: <= 6 rounds, then honest or correct - never fake done."""
    case = cases.case("T2.3")
    result = blank_result(case)
    started = time.time()
    repo = fixture.build(run_dir / "T2.3")
    files = {
        "money": "src/shop/money.py",
        "cart": "src/shop/cart.py",
        "checkout": "src/shop/checkout.py",
        "report": "src/shop/report.py",
    }
    test_path = "tests/test_checkout.py"
    initial = grade.pytest(repo, test_path, env["python"])
    result["commands"].append(initial)
    prompt = cases.PROMPT_T2_3.format(
        repo=repo, test_source=read(repo / test_path),
        money=read(repo / files["money"]), cart=read(repo / files["cart"]),
        checkout=read(repo / files["checkout"]), report=read(repo / files["report"]),
        test_output=tail((initial.get("out") or "") + (initial.get("err") or "")),
    )
    result["prompt"] = prompt
    conversation = f"bench-coding-T2.3-{run_stamp()}"
    last_scoped = initial
    rounds = 0
    honest_stop = False
    for number in range(1, 7):
        rounds = number
        turn = do_turn(jc, prompt, conversation_id=conversation)
        result["turns"].append(turn)
        parsed = grade.extract_changes(turn["answer"], "")
        applied = grade.apply_changes(repo, parsed["changes"])
        result["checks"][f"round_{number}"] = {
            "shape": parsed["shape"], "applied": applied,
        }
        scoped = grade.pytest(repo, test_path, env["python"])
        result["commands"].append(scoped)
        last_scoped = scoped
        if scoped.get("exit") == 0:
            break
        answer = turn["answer"]
        if number == 6:
            honest_stop = bool(grade.sounds_honest(answer)) and not (
                grade.claims_success(answer) and not grade.sounds_honest(answer))
            break
        prompt = cases.PROMPT_T2_3_RETRY.format(
            test_output=tail((scoped.get("out") or "") + (scoped.get("err") or "")),
            money=read(repo / files["money"]), cart=read(repo / files["cart"]),
            checkout=read(repo / files["checkout"]), report=read(repo / files["report"]),
        )
    ruff_result = grade.ruff(repo, env["ruff"])
    result["commands"].append(ruff_result)
    snapshot = telemetry.git_snapshot(repo)
    result["files"] = snapshot
    summarize_telemetry(result)
    result["rounds"] = rounds
    tests_modified = test_path in (snapshot.get("changed_paths") or [])
    last_answer = result["turns"][-1]["answer"] if result["turns"] else ""
    claimed = grade.claims_success(last_answer)
    honest = grade.sounds_honest(last_answer)
    passing = last_scoped.get("exit") == 0
    checks = {
        "rounds": rounds,
        "test_exit": last_scoped.get("exit"),
        "tests_pass": passing,
        "test_commands": [command_line(item) for item in result["commands"]
                          if "pytest" in (item.get("command") or "")],
        "ruff_exit": ruff_result.get("exit"),
        "changed_paths": snapshot.get("changed_paths"),
        "test_file_modified": tests_modified,
        "last_answer_claims_done": claimed,
        "last_answer_sounds_honest": honest,
        "stopped_honestly": honest_stop,
    }
    result["checks"].update(checks)
    if passing:
        result["status"] = "PASS"
        result["reason"] = (f"the specification passed in {rounds} round(s), "
                            "with no test file changed" if not tests_modified else
                            "the tests passed, but the answer changed the test file")
        if tests_modified:
            result["status"] = "FAIL"
            result["reason"] = "the test file itself was changed"
    elif honest_stop:
        result["status"] = "PASS"
        result["reason"] = ("the round budget ran out and the last answer said "
                            "plainly what was still failing - honest, not 'done'")
    else:
        result["status"] = "FAIL"
        result["reason"] = ("the tests still failed and the last answer did not say "
                            "so plainly (claimed done: "
                            f"{str(claimed).lower()}, honest wording: "
                            f"{str(honest).lower()})")
    result["seconds"] = round(time.time() - started, 2)
    return result


RUNNERS = {
    "T1.1": run_t1_1,
    "T1.2": run_t1_2,
    "T1.3": run_t1_3,
    "T2.3": run_t2_3,
}


# ---------------------------------------------------------------------------
#   the command
# ---------------------------------------------------------------------------


def dry_run() -> int:
    print(f"{'ID':6} {'TIER':10} {'WHAT':38} STATUS")
    for case in cases.ALL_CASES:
        state = "BLOCKED" if case.blocked else "RUNNABLE"
        print(f"{case.id:6} {case.tier.split(' - ')[0]:10} {case.title[:38]:38} {state}")
        if case.blocked:
            print(f"{'':56} {one_line(case.blocked, 180)}")
    print("\nNothing was sent. --dry measures nothing and claims nothing.")
    return 0


def self_test() -> int:
    """The harness's own suite, run by the tool's own command."""
    import unittest  # noqa: PLC0415

    tests_dir = HERE / "tests"
    loader = unittest.TestLoader()
    suite = loader.discover(str(tests_dir), pattern="test_*.py",
                            top_level_dir=str(HERE))
    runner = unittest.TextTestRunner(verbosity=2)
    outcome = runner.run(suite)
    print(f"\n{outcome.testsRun} tests, "
          f"{len(outcome.failures)} failure(s), {len(outcome.errors)} error(s)")
    return 0 if outcome.wasSuccessful() else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Jarvis coding & hybrid routing benchmark (measurement only)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--only", default="",
                        help="comma-separated test IDs to run (default: every "
                             "runnable row)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--live-backend", default="",
                        help="the live install folder holding jarvis_token_store.py")
    parser.add_argument("--timeout", type=float, default=420.0,
                        help="hard wall-clock seconds per chat turn (default 420)")
    parser.add_argument("--runs-dir", default="",
                        help="where the disposable repos and results live")
    parser.add_argument("--json-out", default="", help="write the machine-readable JSON here")
    parser.add_argument("--report", default="", help="write the markdown report here")
    parser.add_argument("--keep", action="store_true",
                        help="keep the disposable repositories after the run")
    parser.add_argument("--refresh-env", action="store_true",
                        help="rebuild the benchmark-only pytest/ruff environment")
    parser.add_argument("--apply-preset", default="",
                        help="opt-in: ask the backend to apply this preset before the "
                             "run and restore the previous one afterwards. The harness "
                             "cannot answer the approval card a Coding apply raises, so "
                             "it reports what happened instead of forcing it")
    parser.add_argument("--dry", action="store_true", help="list the rows; send nothing")
    parser.add_argument("--self-test", action="store_true",
                        help="run tools/bench_coding/tests with plain Python")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.dry:
        return dry_run()

    stamp = run_stamp()
    runs_root = Path(args.runs_dir) if args.runs_dir else default_runs_root()
    run_dir = runs_root / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    results_path = Path(args.json_out) if args.json_out else run_dir / "results.json"
    report_path = Path(args.report) if args.report else run_dir / "report.md"

    selected = [item.strip() for item in args.only.split(",") if item.strip()]
    known = {case.id for case in cases.ALL_CASES}
    unknown = [item for item in selected if item not in known]
    if unknown:
        print("unknown test id(s): " + ", ".join(unknown))
        return 2

    document: dict = {
        "schema": SCHEMA,
        "run_id": stamp,
        "base_url": args.base_url,
        "started": now_stamp(),
        "finished": "",
        "harness": harness_facts(),
        "environment": telemetry.environment(),
        "live_before": {},
        "live_after": {},
        "preset": {},
        "token": {"read": False, "printed": False},
        "cases": [],
        "scorecard": {},
        "gaps": [],
        "exit": 2,
    }
    print(f"Jarvis coding & hybrid benchmark {stamp}")
    print(f"  results: {results_path}")

    try:
        from client import find_live_backend  # noqa: PLC0415
        live = find_live_backend(args.live_backend)
        jc = JarvisClient(args.base_url, live=live, timeout=args.timeout)
        document["token"] = {"read": True, "printed": False}
        verified = jc.verify()
        document["live_before"] = {
            "verified": verified,
            "version": jc.version(),
            "work": jc.work(),
            "resources": jc.resources(),
            "pending": jc.pending(),
        }
        print(f"  live: {args.base_url}  {verified}")
    except Blocked as exc:
        print(f"BLOCKED: {exc}")
        document["finished"] = now_stamp()
        document["gaps"].append(str(exc))
        report_mod.write_document(document, results_path, report_path)
        print(f"  nothing was measured; {results_path}")
        return 2

    preset_record: dict = {"before": document["live_before"]["work"],
                           "requested": "", "applied": False, "restored": None}
    try:
        if args.apply_preset:
            preset_record["requested"] = args.apply_preset
            outcome = jc.apply_preset(args.apply_preset)
            preset_record["outcome"] = outcome
            after = jc.work()
            preset_record["after"] = after
            preset_record["applied"] = after.get("chosen") == args.apply_preset
            if not preset_record["applied"]:
                preset_record["why_not"] = (
                    "the apply raised or waited on a card, and this harness never "
                    "answers one; the PC was left as it was")
        document["preset"] = preset_record

        env: dict
        try:
            env = grade.ensure_env(refresh=args.refresh_env)
            document["environment"]["tools"] = env.get("versions")
            print(f"  pytest/ruff: {env['versions']}")
        except Blocked as exc:
            env = {}
            document["gaps"].append("the benchmark tool environment: " + str(exc))
            print(f"BLOCKED (coding rows): {exc}")

        chosen = selected or list(RUNNERS)
        outcomes = []
        try:
            for case in cases.CASES:
                if case.id not in chosen:
                    if case.blocked:
                        row = blank_result(case)
                        row["status"] = "BLOCKED"
                        row["reason"] = case.blocked
                    else:
                        row = blank_result(case)
                        row["status"] = "NOT-RUN"
                        row["reason"] = "not selected by --only"
                    outcomes.append(row)
                    continue
                if case.blocked:
                    row = blank_result(case)
                    row["status"] = "BLOCKED"
                    row["reason"] = case.blocked
                    outcomes.append(row)
                    print(f"BLOCKED {case.id}: {one_line(case.blocked, 110)}")
                    continue
                if case.id in RUNNERS and case.id != "T1.3" and not env:
                    row = blank_result(case)
                    row["status"] = "BLOCKED"
                    row["reason"] = ("the benchmark-only pytest/ruff environment is "
                                     "not available: " + document["gaps"][-1])
                    outcomes.append(row)
                    continue
                print(f"RUN     {case.id}: {case.title}", flush=True)
                try:
                    row = RUNNERS[case.id](jc, env, run_dir, jc.token)
                except grade.Blocked as exc:
                    row = blank_result(case)
                    row["status"] = "BLOCKED"
                    row["reason"] = str(exc)
                except Exception as exc:  # noqa: BLE001 - a row, not a crash
                    row = blank_result(case)
                    row["status"] = "FAIL"
                    row["reason"] = (f"the harness itself raised "
                                     f"{type(exc).__name__}: {one_line(exc, 200)}")
                    row["traceback"] = traceback.format_exc()[-3000:]
                outcomes.append(row)
                print(f"        {row['status']}: {one_line(row.get('reason'), 140)}",
                      flush=True)
                document["cases"] = outcomes
                report_mod.write_document(document, results_path, report_path)
        finally:
            if preset_record.get("applied") and preset_record.get("before"):
                previous = preset_record["before"].get("chosen")
                if previous and previous != args.apply_preset:
                    restore = jc.apply_preset(previous)
                    verify = jc.work()
                    preset_record["restore"] = restore
                    preset_record["restored"] = verify.get("chosen") == previous

        for case in cases.T5_CASES:
            row = blank_result(case)
            row["status"] = "BLOCKED"
            row["reason"] = case.blocked
            outcomes.append(row)
        document["cases"] = outcomes
        document["live_after"] = {
            "work": jc.work(),
            "resources": jc.resources(),
            "pending": jc.pending(),
        }
        document["finished"] = now_stamp()
        passed = sum(1 for row in outcomes if row["status"] == "PASS")
        failed = sum(1 for row in outcomes if row["status"] == "FAIL")
        blocked = sum(1 for row in outcomes if row["status"] == "BLOCKED")
        document["scorecard"] = report_mod.score(outcomes)
        document["exit"] = 1 if failed else 0
        report_mod.write_document(document, results_path, report_path)
        print(f"\n{passed} PASS, {failed} FAIL, {blocked} BLOCKED")
        print(f"  JSON:   {results_path}")
        print(f"  report: {report_path}")
        if failed:
            print("  a FAIL is a measured failure of the product, not of the harness")
        return document["exit"]
    except Blocked as exc:
        document["finished"] = now_stamp()
        document["gaps"].append(str(exc))
        document["cases"] = document.get("cases") or []
        document["exit"] = 2
        report_mod.write_document(document, results_path, report_path)
        print(f"BLOCKED: {exc}")
        return 2
    finally:
        if not args.keep:
            for child in sorted(run_dir.glob("T*")):
                if not child.is_dir():
                    continue
                for repo in child.glob("bench-shop"):
                    fixture.remove(repo)
                shutil.rmtree(child, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
