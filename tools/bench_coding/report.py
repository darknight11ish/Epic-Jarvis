"""The two deliverables of one run: the JSON and the human report.

The JSON is the machine-readable record: one object per test with the prompt
used, every turn's route header, the speed.jsonl rows attributed to the turn,
the cloud-money delta, the commands and their exit codes, the git snapshot and
the verdict. The markdown is the same record as a table plus the detail a
person needs to check it.

NOTHING HERE INFLATES A ROW. `score()` counts BLOCKED on its own line and
never as a pass; a tier's bar is MET only when every ID the bar names was
measured and passed. A tier whose rows could not be measured reads
`NOT MEASURED`, not `failed` - and not `met`.
"""
from __future__ import annotations

import json
from pathlib import Path

#: The spec's section-3 scorecard, as a table the report can fill in.
BARS = (
    ("Tier 1", ("T1.1", "T1.2", "T1.3"), 3,
     "3/3 pass, $0.00 cloud spend"),
    ("Tier 2", ("T2.1", "T2.2", "T2.3"), 3,
     "3/3 honest handling (zero silent rule drops or fake completions)"),
    ("Tier 3", ("T3.1", "T3.2", "T3.3", "T3.4"), 3,
     ">= 3/4 pass, total cloud cost < $0.05 for the entire suite"),
    ("Tier 4", ("T4.1", "T4.2", "T4.3"), 3,
     "3/3 mandatory (100%) - any Tier 4 failure is an immediate merge blocker"),
)

#: Facts about the spec itself that this harness measured to be wrong. Kept
#: here so the report says them even if nobody edits the prose afterwards.
SPEC_ERRORS = (
    "**The count is wrong.** Section 2 says \"12 repeatable tests\", but its four "
    "tables list **13** IDs (3 + 3 + 4 + 3) and the section-3 scorecard asks for "
    "3/3 + 3/3 + 3/4 + 3/3 = 13 rows. This report lists all 13.",
    "**`completion_tokens` is not a field.** `speed.jsonl`'s own first line has "
    "`tokens` (the completion count), and no `completion_tokens`. The harness uses "
    "the real names: `prompt_tokens`, `cached_tokens`, `tokens`, `tokens_per_s`.",
    "**`daily-budget.json` does not exist.** There is no daily cap yet. Cloud "
    "spend is the delta of `~/.openjarvis/chatbot/api-money.json`'s "
    "`months.<month>.<service>.dollars`, and the report says so on every row.",
    "**`X-Jarvis-Route` is not a `local` / `jarvis-escalate` flag.** The header "
    "DOES exist and every chat answer carries it, but its body is JSON built from "
    "the router's own `Decision` (`lane`, `reason`, `gate`, `complexity`, `auto`, "
    "`tainted`, `offer`, ...) plus per-turn fields (`where`, `turn_id`, "
    "`temporary`, ...). The harness records `lane` + `where` + `gate` and keeps "
    "the whole header verbatim in the JSON; it does not invent a two-word header.",
    "**T3.1's cloud leg is not reachable, so the split cannot be observed.** The "
    "cloud escalation switch was off for the whole run (`/api/work` -> "
    "cloud.escalate.on = false), so the router offered `jarvis-escalate` and never "
    "took it. The local half did route local on the 49,152-token lane (measured), "
    "but a split needs both halves.",
    "**PRs the spec's prerequisites named as open are now merged to main but NOT "
    "on the live PC.** #1328 merged 2026-11-17T05:24:33Z and #1331 at 05:57:09Z; "
    "the live `jarvis_hud.py` is dated 2026-11-09, the live folder has no "
    "`jarvis_egress_gate.py`, and the live process started before the merges. A "
    "merge is not a deployment.",
)

#: Measurement gaps that belong to the harness, not to the product.
HARNESS_GAPS = (
    "**No file-write tool on this PC's chat lane.** `shell_exec` is mapped to the "
    "hard-refused `run_shell_on_host` action and `file_write`/`apply_patch` map to "
    "`delete_file`, so Jarvis cannot edit the disposable repo itself. The harness "
    "therefore asks Jarvis for the complete file contents and applies them. This "
    "measures the model's coding through the live product; it does NOT measure "
    "autonomous repository editing, which this lane cannot do.",
    "**A card raised by the model during a turn is DECLINED, never approved.** "
    "The first 2026-11-16 pilot showed why: asked to fix a local file, the model "
    "called `github_fix_and_push` with an invented `owner/repo` and PR #1, and the "
    "turn then waited on the card for 600 s. A no executes nothing, and the run "
    "records every declined card's id, action and answer, so this is visible "
    "rather than silent. No permission is created and no tool ever runs.",
    "**\"0 write tools\" in T1.3 is a proxy.** The route header and `speed.jsonl` "
    "carry no tool-call names, so the harness records whether a card was raised "
    "and declined (a write tool raises one) and whether one was pending "
    "before/after.",
    "**Speed rows are attributed by wall-clock window.** The live PC is shared: a "
    "row inside the window but from another conversation is possible. Attribution "
    "prefers the route header's `lane`, keeps every row it saw and flags "
    "`ambiguous` when more than one could be the turn's.",
    "**`tokens_per_s` could not be measured on this build - `tokens` is wrong.** "
    "Every non-streamed turn in this run wrote `tokens: 1` to `speed.jsonl` "
    "while the same row's `words` was a few hundred (the 2026-11-16 rows read "
    "`tokens: 1, words: 672` and `tokens: 1, words: 703`), so `tokens_per_s` is "
    "absent and any tokens/s figure computed from it would be wrong by orders of "
    "magnitude. The harness reports the real `words_per_s` beside it and says so. "
    "OPEN PR #1337 (`fix(speed): record the model's own completion_tokens on a "
    "local turn (R7)`) is the module that owns the fix.",
    "**Cloud $ is a month-to-date delta.** `api-money.json` is the chatbot "
    "driver's record; the router's own cloud path may or may not write it. The "
    "report never presents the delta as proof of zero bytes leaving the PC - "
    "T4.1's egress gate is the feature that would prove that, and it is an open PR.",
    "**No preset switch was made.** Flipping a preset on the owner's PC is a "
    "state change the harness will not make unless asked (`--apply-preset`), and "
    "a Coding apply raises one approval card the harness never answers. This run "
    "measured the lane the PC was already using; the preset state before/after is "
    "recorded.",
    "**T4.2 was not re-measured.** The owner measured it broken tonight and a "
    "lane is fixing it; re-measuring a known-broken row risks a stale failure. It "
    "is BLOCKED here, not a pass.",
)


def _status_counts(rows: list[dict]) -> dict:
    counts = {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "NOT-RUN": 0}
    for row in rows:
        status = row.get("status") or "NOT-RUN"
        counts[status] = counts.get(status, 0) + 1
    return counts


def score(outcomes: list[dict]) -> dict:
    """The spec's own scorecard, filled in from what actually happened."""
    by_id = {row.get("id"): row for row in outcomes}
    tiers = []
    for name, ids, required, bar in BARS:
        rows = [by_id.get(case_id) or {"id": case_id, "status": "NOT-RUN"}
                for case_id in ids]
        counts = _status_counts(rows)
        measured = len(ids) - counts["BLOCKED"] - counts["NOT-RUN"]
        met = (counts["PASS"] >= required and counts["FAIL"] == 0
               and counts["BLOCKED"] == 0 and counts["NOT-RUN"] == 0)
        if counts["FAIL"]:
            verdict = "NOT MET - a measured row failed"
        elif counts["PASS"] >= required and counts["BLOCKED"] == 0 and \
                counts["NOT-RUN"] == 0:
            verdict = "MET"
        elif measured == 0:
            verdict = "NOT MEASURED"
        else:
            verdict = (f"NOT MET - {counts['PASS']} passed, "
                       f"{counts['BLOCKED']} blocked, {counts['NOT-RUN']} not run")
        tiers.append({
            "tier": name, "ids": list(ids), "required": required, "bar": bar,
            "measured": measured, "passed": counts["PASS"],
            "failed": counts["FAIL"], "blocked": counts["BLOCKED"],
            "not_run": counts["NOT-RUN"], "met": met, "verdict": verdict,
            "rows": [{"id": row.get("id"), "status": row.get("status")}
                     for row in rows],
        })
    measured_rows = [row for row in outcomes
                     if row.get("status") in ("PASS", "FAIL")]
    cloud = round(sum(float(row.get("cloud_dollars") or 0.0)
                      for row in measured_rows), 6)
    overall = {
        "measured": len(measured_rows),
        "passed": sum(1 for row in measured_rows if row["status"] == "PASS"),
        "failed": sum(1 for row in measured_rows if row["status"] == "FAIL"),
        "blocked": sum(1 for row in outcomes if row.get("status") == "BLOCKED"),
        "not_run": sum(1 for row in outcomes if row.get("status") == "NOT-RUN"),
        "cloud_dollars_measured": cloud,
        "tiers": tiers,
    }
    return overall


def _cell(value, limit: int = 60) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, float):
        text = f"{value:.6f}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    text = " ".join(text.split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "..."


def _table(rows: list[dict]) -> str:
    head = ("| ID | Test | Status | Turns | Route (lane / where) | tok/s | words/s | "
            "tokens | Cloud $ | Files | Test exit | Why |")
    line = ("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | "
            "--- |")
    body = []
    for row in rows:
        route = row.get("route") or {}
        lane = route.get("lane")
        where = route.get("where")
        route_text = (f"{lane} / {where}" if lane or where else "-")
        files = (row.get("files") or {}).get("changed_paths")
        commands = row.get("commands") or []
        test_exit = "-"
        for command in reversed(commands):
            if "pytest" in (command.get("command") or ""):
                test_exit = command.get("exit")
                break
        body.append("| " + " | ".join([
            _cell(row.get("id"), 8),
            _cell(row.get("title"), 34),
            _cell(row.get("status"), 9),
            _cell(row.get("attempts") if row.get("attempts") else row.get("rounds"), 6),
            _cell(route_text, 48),
            _cell(row.get("tokens_per_s"), 10),
            _cell(row.get("words_per_s"), 10),
            _cell(row.get("tokens"), 8),
            _cell(row.get("cloud_dollars"), 10),
            _cell(len(files) if files else "-", 8),
            _cell(test_exit, 8),
            _cell(row.get("reason"), 110),
        ]) + " |")
    return "\n".join([head, line, *body])


def _details(row: dict) -> str:
    parts = [f"### {row.get('id')} - {row.get('title')}: **{row.get('status')}**",
             "", f"*Spec criterion:* {row.get('criterion')}", ""]
    if row.get("reason"):
        parts += [f"*What the harness measured:* {row['reason']}", ""]
    route = row.get("route") or {}
    if route:
        parts += [
            "*Route, from the `X-Jarvis-Route` response header:*",
            "",
            "```json",
            json.dumps(route, indent=1, ensure_ascii=False)[:3000],
            "```",
        ]
        parts += ["", f"Fields used: `lane` (which model answered), `where` "
                      f"(`local` or not), `gate`, `reason`, `tainted`, `auto`.", ""]
    files = row.get("files") or {}
    if files:
        parts += ["*`git status --short` in the disposable repo:*", "",
                  "```", (files.get("status_short") or "").strip() or "(clean)", "```",
                  "", "*`git diff --stat`:*", "",
                  "```", (files.get("diff_stat") or "").strip() or "(nothing)", "```",
                  ""]
    checks = row.get("checks") or {}
    if checks:
        shown = {key: value for key, value in checks.items()
                 if key not in ("ground_truth_titles",)}
        parts += ["*Checks:*", "", "```json",
                  json.dumps(shown, indent=1, ensure_ascii=False)[:5000], "```", ""]
    commands = row.get("commands") or []
    if commands:
        parts += ["*Commands, with their exit codes:*", "",
                  "```"]
        for command in commands:
            parts.append(f"{command.get('command')}  -> exit {command.get('exit')}")
        parts += ["```", ""]
    turns = row.get("turns") or []
    if turns:
        parts += ["*Turns:*", "",
                  "| Turn | Seconds | HTTP | Route lane | tok/s | prompt tok | "
                  "completion tok | Cloud $ | Pending cards |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for index, turn in enumerate(turns, 1):
            speed = (turn.get("speed") or {}).get("chosen") or {}
            route = turn.get("route") or {}
            parts.append("| " + " | ".join([
                str(index), _cell(turn.get("seconds"), 8), _cell(turn.get("status"), 6),
                _cell(route.get("lane"), 40), _cell(speed.get("tokens_per_s"), 8),
                _cell(speed.get("prompt_tokens"), 8), _cell(speed.get("tokens"), 8),
                _cell((turn.get("cloud") or {}).get("dollars"), 10),
                _cell((turn.get("pending_after") or {}).get("pending"), 8),
            ]) + " |")
        parts += [""]
        ambiguous = [index for index, turn in enumerate(turns, 1)
                     if (turn.get("speed") or {}).get("ambiguous")]
        if ambiguous:
            parts += [f"ATTRIBUTION NOTE: turn(s) {ambiguous} had more than one "
                      "speed row in the window; the one nearest the route's lane "
                      "was used.", ""]
    if row.get("prompt"):
        parts += ["<details><summary>The prompt, exactly as sent</summary>", "",
                  "````text", row["prompt"], "````", "", "</details>", ""]
    if row.get("blocked"):
        parts += [f"*Why it is blocked:* {row['blocked']}", ""]
    return "\n".join(parts)


def render(document: dict) -> str:
    rows = [row for row in document.get("cases") or [] if not str(row.get("id", "")).startswith("T5")]
    t5 = [row for row in document.get("cases") or [] if str(row.get("id", "")).startswith("T5")]
    scorecard = document.get("scorecard") or {}
    live = document.get("live_before") or {}
    work = live.get("work") or {}
    resources = live.get("resources") or {}
    lines = [
        "# Jarvis coding & hybrid routing benchmark - measured report",
        "",
        f"**Run:** `{document.get('run_id')}`  ",
        f"**Started:** {document.get('started')}  **Finished:** "
        f"{document.get('finished') or '(in progress)'}  ",
        f"**Live backend:** {document.get('base_url') or 'http://127.0.0.1:4719'}  ",
        f"**Harness tree:** {document.get('harness', {}).get('branch')} "
        f"`{document.get('harness', {}).get('commit')}`",
        "",
        "This is the output of `tools/bench_coding/run.py`. A **BLOCKED** row is a "
        "row that could not be measured: it is **not** a pass and it is **not** a "
        "failure of the product.",
        "",
        "## 1. The 13 rows",
        "",
        _table(rows),
        "",
        "Counts across these 13 scored rows: "
        f"**{sum(1 for row in rows if row.get('status') == 'PASS')} PASS**, "
        f"**{sum(1 for row in rows if row.get('status') == 'FAIL')} FAIL**, "
        f"**{sum(1 for row in rows if row.get('status') == 'BLOCKED')} BLOCKED**, "
        f"**{sum(1 for row in rows if row.get('status') == 'NOT-RUN')} NOT-RUN**. "
        f"The three T5 rows are not scored: they are listed in section 6 and are "
        f"BLOCKED too. Cloud spend measured across the rows that ran: "
        f"**${scorecard.get('cloud_dollars_measured', 0.0):.6f}**.",
        "",
        "A note on the speed columns: `tokens` is `speed.jsonl`'s own field and it "
        "is WRONG on this build (every non-streamed turn wrote 1; see section 3), "
        "so `tok/s` is `-`. `words/s` is the honest rate: the row's own `words`, "
        "or `words / total_ms` when the writer omitted `words_per_s` (the JSON says "
        "which).",
        "",
        "## 2. The scorecard, filled in honestly",
        "",
        "| Tier | Bar | Measured | Passed | Failed | Blocked | Verdict |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for tier in scorecard.get("tiers") or []:
        lines.append("| " + " | ".join([
            tier["tier"], tier["bar"], f"{tier['measured']}/{len(tier['ids'])}",
            str(tier["passed"]), str(tier["failed"]), str(tier["blocked"]),
            tier["verdict"],
        ]) + " |")
    lines += [
        "",
        "**None of the four tiers is fully met, because none of them was fully "
        "measured.** That sentence is the honest result, not a rounding of it: "
        "Tier 1 has two of its three rows measured and passing (T1.1 and T1.2) "
        "and T1.3 blocked on the GitHub tools' ask-tier cards; Tier 2 has only "
        "T2.3 measured, with T2.1/T2.2 unable to run because their merged fix is "
        "not on the live install; Tier 3 and Tier 4 have no measured row at all "
        "(the cloud switch is off, two features are unbuilt, and the egress gate "
        "is merged but not deployed). A tier reading NOT MEASURED says nothing "
        "about the product's quality either way.",
        "",
        *(["## 2b. What this run proved, measured", "",
            *[f"- {item}" for item in document.get("findings") or []], ""]
          if document.get("findings") else []),
        "## 3. How each measurement was taken",
        "",
        *([f"- {item}" for item in document.get("run_notes") or []] + [""]
          if document.get("run_notes") else []),
        f"**Live state at the start.** Backend `{live.get('server') or (live.get('version') or {}).get('server') or 'jarvis-hud'}`, "
        f"app version `{live.get('app_version') or 'not read'}`, "
        f"API `{live.get('api') or (live.get('version') or {}).get('api')}`. "
        f"Chosen preset: **{work.get('chosen')}** (`{work.get('chosen_model')}`); "
        f"the resources read names chat's lane "
        f"**{(resources.get('active_lane') or {}).get('preset') or '?'}** "
        f"`{(resources.get('active_lane') or {}).get('url')}`; cloud escalation: "
        f"**{str((work.get('cloud_escalate') or {}).get('on')).lower()}** "
        f"({(work.get('cloud_escalate') or {}).get('why') or 'no reason given'}).",
        "",
        f"**Lanes the PC reported.** " + " ".join(
            f"`{lane.get('key')}`={lane.get('state')}"
            + (f" ({lane.get('model')} at {lane.get('context_length')} tokens"
               + (f", {round((lane.get('spill_bytes') or 0) / 2**30, 1)} GiB spilled"
                  if lane.get('spill_bytes') else "")
               + ")" if lane.get('model') else "")
            + ";" for lane in resources.get("lanes") or []),
        "",
        "**Route.** Every answer's `X-Jarvis-Route` response header is kept "
        "verbatim in the JSON. The report reads `lane` (the model/lane that "
        "answered), `where` (`local` when the PC's own model answered), `gate`, "
        "`reason`, `tainted` and `auto`. There is no `local`/`jarvis-escalate` "
        "header value to read - the spec's name for the mechanism is right and "
        "its described payload is wrong.",
        "",
        "**Tokens/s - and why the token figure here is not usable.** "
        "`~/.openjarvis/speed.jsonl`, whose first line is the schema. The harness "
        "records the row count before and after each turn, attributes the appended "
        "rows to the turn by wall-clock window (preferring the route's lane) and "
        "reports the real fields `prompt_tokens`, `cached_tokens`, `tokens`, "
        "`tokens_per_s`, `total_ms`, `first_word_ms`, `prompt_rounds`, `tools`, "
        "`words` and `words_per_s`. There is no `completion_tokens` field. **On "
        "this build `tokens` is wrong for a non-streamed turn**: every measured "
        "row says `tokens: 1` while the same row's `words` says 635, 98 or 672, and "
        "`tokens_per_s` is absent. The report therefore prints `-` for tok/s and "
        "uses `words/s` (computed from the row's own `words` and `total_ms` when the "
        "writer omitted it) as the honest rate. OPEN PR #1337 owns the fix.",
        "",
        "**Cloud $.** `~/.openjarvis/chatbot/api-money.json`, the delta of "
        "`months.<month>.<service>.dollars` across each turn. `daily-budget.json` "
        "does not exist on this PC, so no daily cap is consulted or claimed.",
        "",
        "**Git cleanliness.** `git status --short` and `git diff --stat` inside "
        "the disposable repo after every coding row, always, with the paths named.",
        "",
        "**Isolation.** Every coding row gets a NEW repository made by "
        "`tools/bench_coding/fixture.py` under `%LOCALAPPDATA%\\Jarvis\\"
        "bench-coding`; it has `git init` and ONE commit, and **no remote at all**. "
        "Nothing reads or writes the checkout the tool lives in, `origin/main`, or "
        "any live Jarvis file.",
        "",
        "## 4. What the harness itself could not measure",
        "",
    ]
    gaps = list(HARNESS_GAPS) + list(document.get("gaps") or [])
    lines += [f"- {gap}" for gap in gaps] or ["- (none recorded)"]
    lines += ["", "## 5. Where the spec is wrong", ""]
    lines += [f"- {item}" for item in SPEC_ERRORS]
    lines += ["", "## 6. The T5 framework (not part of the four scored tiers)", "",
              "Section 5 proposes a task/progress framework and its own T5.1-T5.3 "
              "tests. It is not built, so it is listed here rather than scored:",
              ""]
    lines += [f"- **{row.get('id')} {row.get('title')}**: {row.get('reason')}"
              for row in t5] or ["- (none listed)"]
    if document.get("preset"):
        preset = document["preset"]
        lines += ["", "## 7. Preset state", "",
                  "```json", json.dumps(preset, indent=1, ensure_ascii=False)[:4000],
                  "```"]
    lines += ["", "## 8. Every row in detail", ""]
    for row in rows:
        lines += [_details(row), ""]
    lines += ["## 9. The machine-readable record", "",
              "The same run is written as JSON beside this report "
              "(`--json-out`), with every prompt, route header, turn, command and "
              "exit code. The markdown is a rendering of that document; where the "
              "two differ, the JSON is the record.", ""]
    return "\n".join(lines)


def write_document(document: dict, json_path: Path, report_path: Path) -> None:
    """Write both artefacts, creating their folders, and say nothing on success."""
    json_path = Path(json_path)
    report_path = Path(report_path)
    for path in (json_path, report_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(document, indent=1, ensure_ascii=False),
                         encoding="utf-8", newline="\n")
    report_path.write_text(render(document), encoding="utf-8", newline="\n")
