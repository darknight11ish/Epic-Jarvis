"""jarvis_watch_policy.py - the first stage of the two-stage gate, and it is pure.

WHAT THIS IS. `gate()` decides, in plain code, whether an event from a watcher
deserves to reach the owner at all: which checks are REQUIRED and which are
merely informational, whether a thread has settled, whether this exact result
has already been reported, and whether the actor is a bot. Only an event that
passes gets as far as a further look (the `assess()` stage in
`jarvis_watch_ci.py`, which may fetch a failing job's log). This is the pattern
this project adopted on 2026-11-04 from `dsh-superagent`'s `src/policy.ts`.

WHY IT IS A SEPARATE MODULE, AND WHY THAT IS NOT TIDINESS. The claim being made
is "the filter costs 0 ms and 0 GPU, and a filtered event NEVER reaches the
part that might spend either". A claim like that is only worth something if it
is STRUCTURAL. So this file imports nothing from Jarvis and nothing that can
reach a disk, a network or a model: no `jarvis_*`, no `sqlite3`, no `urllib`,
no `subprocess`, no `jarvis_router`. It has no clock; `now` is an argument.
Every function here is a total function of its arguments. If somebody later
adds a fetch to this file, the import list is the thing to look at, and
`backend/test_watch_ci.py` fails when a new import appears.

THE FACTS THAT MAKE THE RULES NECESSARY (measured, `docs/ARCHITECTURE.md`):

  * A pull request runs SEVEN checks that gate a merge - `rust`, `frontend`,
    `backend`, `backend-windows`, `credential-manager`, `powershell-5`,
    `phone-unit-tests` - plus `audit` and `python-advisories`, which are
    informational. The seven were read from the ruleset itself (id 24677804);
    `audit` and `python-advisories` are RED today on `main` and merges still
    land, which is what "informational" means. A watcher that counted them as
    failures would cry wolf on every pull request, and one that counted them as
    passes would say "all green" about a tree that is not.
  * The seven finish minutes apart: `rust` in about three, `frontend` in about
    five, `backend` and `backend-windows` in about fifty-five to sixty. A
    watcher that speaks per check sends SEVEN messages about one pull request.
    So one thread (one PR at one commit) is held until it either fails fast or
    settles green, and speaks at most once (Pattern 2).

WHAT A DECISION LOOKS LIKE. Every row this module returns carries the fields
the owner reads in `GET /api/watch/decisions?limit=50`: `at`, `source`,
`thread_key`, `outcome`, `reason_code`, `preview_text` - plus `mode`, `verdict`
and, in observe mode, `shadow_reason_code`. `outcome` is one of
`("would_notify", "ignored", "notified")`; this module itself only ever returns
the first two, because it does not deliver anything. `reason_code` comes from a
CLOSED set, `jarvis_watch.WATCH_REASONS` - this module only returns strings
from it, and the suite checks that both directions hold.

THE ONE RULE WITH NO EXCEPTION: an informational check can never be the reason
for a notification. `audit` and `python-advisories` are dropped by name before
any threshold is calculated, so a red `audit` on a green pull request produces
`ci_all_required_green` and one quiet line, not a false alarm.
"""
from __future__ import annotations

from typing import Optional

#: The seven that gate a merge (docs/ARCHITECTURE.md, the ruleset's own list).
REQUIRED_CI_JOBS = (
    "rust",
    "frontend",
    "backend",
    "backend-windows",
    "credential-manager",
    "powershell-5",
    "phone-unit-tests",
)

#: Informational checks: they may be red while a pull request merges. A watcher
#: must never speak about one, and `classify()` drops them by NAME before any
#: arithmetic - not by a flag a caller could get wrong.
INFORMATIONAL_CI_JOBS = ("audit", "python-advisories")

#: The terminal conclusions that mean "this required check failed" and are
#: worth interrupting for immediately (the spec's own three).
FAIL_CONCLUSIONS = ("FAILURE", "TIMED_OUT", "ACTION_REQUIRED")

#: Terminal, but not a failure in the spec's list. They are still not a pass,
#: and a required check that ends in one of these would otherwise hold the
#: thread open for ever, so they fail the batch too - one notification, with the
#: conclusion named. CANCELLED on a REQUIRED check is not something to be quiet
#: about: on a branch-protected pull request it means the merge is blocked.
OTHER_TERMINAL_NOT_GREEN = ("CANCELLED", "STALE", "NEUTRAL", "SKIPPED")

GREEN_CONCLUSION = "SUCCESS"

#: Check states that mean "still going". Anything else terminal is judged above.
RUNNING_STATUSES = ("QUEUED", "IN_PROGRESS", "PENDING", "WAITING", "REQUESTED")

#: The sources a decision row may name. `repo_check` is this PC's own checkers
#: (the same suite list CI runs), `github_notifications` is the notifications
#: feed, `github_pr_ci` is a pull request's rollup.
SOURCES = ("github_pr_ci", "github_notifications", "repo_check")

#: The bot logins GitHub itself uses. A notification from one of these is never
#: a person asking for something, and `is_bot()` also accepts anything ending
#: in `[bot]` - which is how every GitHub App is named.
BOT_ACTORS = ("github-actions", "dependabot", "renovate", "codecov")

#: Mergeability, as GitHub reports it. Only MERGEABLE settles a green batch.
MERGEABLE = "MERGEABLE"


def one_line(value, cap: int = 120) -> str:
    """One line of text, trimmed and capped. Every string that reaches a
    decision row or a preview goes through this, because a check name or a
    commit message is written by somebody else."""
    s = str(value if value is not None else "")
    s = " ".join(s.replace("\r", " ").replace("\n", " ").split())
    return s[:cap]


def thread_key(trigger: dict) -> str:
    """One key per conversation-with-a-thing, which is what a batch is held on.

    A pull request's thread is `pr:<number>:<first 9 of the head sha>` - the
    same shape the spec names - so a new push starts a NEW thread (a new batch,
    a new settle) rather than reusing the old verdict.
    """
    source = one_line((trigger or {}).get("source"), 40)
    if source == "github_pr_ci":
        pr = as_int((trigger or {}).get("pr"))
        sha = one_line((trigger or {}).get("head_sha"), 40)
        if pr is None or not sha:
            return f"pr:{pr or 0}:{sha[:9]}"
        return f"pr:{pr}:{sha[:9]}"
    if source == "github_notifications":
        tid = one_line((trigger or {}).get("id") or (trigger or {}).get("thread_id"), 60)
        return f"notification:{tid}"
    if source == "repo_check":
        return f"repo:{one_line((trigger or {}).get('name'), 60)}"
    return f"unknown:{source}"


def as_int(value) -> Optional[int]:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def receipt_key(pr, head_sha, verdict: str) -> str:
    """The deterministic idempotency key: `(pr_number, head_sha, verdict)`.

    `verdict` is part of it on purpose. A pull request that fails `rust`, gets
    fixed and then settles green has TWO terminal verdicts for two different
    states of the same commit, and the owner is owed both; the same commit
    re-polled ten times has one, and is owed one.
    """
    return f"{as_int(pr) or 0}:{one_line(head_sha, 40)}:{one_line(verdict, 60)}"


def normalize_checks(checks) -> dict:
    """`{name: {"status", "conclusion"}}` from any of GitHub's two shapes.

    A `CheckRun` says `status`/`conclusion`; a `StatusContext` says `state`.
    Both arrive in the same `statusCheckRollup` list, so both are read here and
    neither is guessed at. Anything unreadable is skipped rather than trusted.
    """
    out: dict = {}
    for c in checks or ():
        if not isinstance(c, dict):
            continue
        name = one_line(c.get("name") or c.get("context"), 80)
        if not name:
            continue
        status = one_line(c.get("status") or "", 24).upper()
        conclusion = one_line(c.get("conclusion") or c.get("state") or "", 24).upper()
        if conclusion and not status:
            # A StatusContext's `state` IS its conclusion, and it is terminal.
            status = "COMPLETED"
        out[name] = {"status": status, "conclusion": conclusion,
                     # How stage two finds the failing run's own log without
                     # guessing a run id. It arrives with the rollup, so it is
                     # kept here rather than fetched a second time.
                     "url": one_line(c.get("detailsUrl") or c.get("targetUrl")
                                     or c.get("url"), 300)}
    return out


def classify(thread: dict) -> dict:
    """Where one thread stands, from the seven required checks and nothing else.

    Returns a dict with `state` one of:

      * `"failed"` - at least one required check ended not-green. Fail fast:
        `failed_job` and `conclusion` name it, `done` says how many of the
        seven had finished.
      * `"green"` - all seven ended SUCCESS. `mergeable` is passed through
        untouched so the caller can decide about GitHub's own answer.
      * `"running"` - at least one required check has not finished, and none
        failed. This is the quiet state.
      * `"none"` - not one of the seven is present in the rollup, which means
        this is not a pull request this watcher knows how to judge.

    Informational checks are dropped FIRST, by name, before any count.
    """
    checks = (thread or {}).get("checks")
    if not isinstance(checks, dict):
        checks = normalize_checks((thread or {}).get("checks"))
    required = {name: checks[name] for name in REQUIRED_CI_JOBS if name in checks}
    informational = [name for name in INFORMATIONAL_CI_JOBS if name in checks]
    if not required:
        return {"state": "none", "done": 0, "total": len(REQUIRED_CI_JOBS),
                "failed_job": "", "conclusion": "", "informational": informational}
    done = 0
    running = []
    failed = []
    for name in REQUIRED_CI_JOBS:
        c = required.get(name)
        if not c:
            running.append(name)
            continue
        status, conclusion = c.get("status", ""), c.get("conclusion", "")
        if conclusion in FAIL_CONCLUSIONS or conclusion in OTHER_TERMINAL_NOT_GREEN:
            done += 1
            failed.append((name, conclusion))
            continue
        if conclusion == GREEN_CONCLUSION:
            done += 1
            continue
        # No conclusion yet, or a state this file has never seen: not finished.
        running.append(name)
    if failed:
        # The FIRST failure in the required order, so the same rollup always
        # produces the same job name and the same receipt key.
        return {"state": "failed", "done": done, "total": len(REQUIRED_CI_JOBS),
                "failed_job": failed[0][0], "conclusion": failed[0][1],
                "failed_jobs": [n for n, _ in failed],
                "informational": informational}
    if running:
        return {"state": "running", "done": done, "total": len(REQUIRED_CI_JOBS),
                "failed_job": "", "conclusion": "", "waiting_on": running,
                "informational": informational}
    return {"state": "green", "done": done, "total": len(REQUIRED_CI_JOBS),
            "failed_job": "", "conclusion": "", "informational": informational}


def is_bot(actor) -> bool:
    """True for a GitHub App or a bot account, by the names GitHub actually
    uses. Nothing here guesses from a display name."""
    login = one_line(actor, 80).lower().strip()
    if not login:
        return False
    if login.endswith("[bot]"):
        return True
    base = login.split("/")[-1]
    if base in BOT_ACTORS:
        return True
    return any(base.endswith(sfx) for sfx in ("-bot", "_bot")) or base == "bot"


def preview(verdict: str, thread: dict, info: Optional[dict] = None) -> str:
    """The exact ONE-LINE message the owner would see. Deterministic: the same
    verdict and thread always produce the same sentence, which is what makes a
    receipt safe to key on and what lets the decisions log be read later."""
    info = info or classify(thread)
    pr = as_int((thread or {}).get("pr")) or 0
    sha = one_line((thread or {}).get("head_sha"), 40)[:9]
    n = info.get("total", len(REQUIRED_CI_JOBS))
    if verdict == "all_green":
        return (f"PR #{pr} is green: all {n} required checks passed and GitHub "
                f"says it is mergeable ({sha}).")
    if verdict.startswith("failed:"):
        job = verdict.split(":", 1)[1] or info.get("failed_job", "a required check")
        return (f"PR #{pr}: required check '{job}' {info.get('conclusion') or 'FAILED'} "
                f"on {sha} - {info.get('done', 0)} of {n} required checks finished, "
                f"so this needs you now.")
    if verdict.startswith("green_not_mergeable:"):
        why = verdict.split(":", 1)[1]
        return (f"PR #{pr}: all {n} required checks passed, but GitHub reports "
                f"mergeable={why} on {sha} - green is not the same as mergeable.")
    if verdict == "running":
        return (f"PR #{pr}: {info.get('done', 0)} of {n} required checks finished, "
                f"none failed - staying quiet until it settles ({sha}).")
    if verdict.startswith("duplicate:"):
        what = verdict.split(":", 1)[1]
        if pr:
            return (f"PR #{pr} at {sha} was already reported ({what}); "
                    f"nothing was repeated.")
        return (f"{thread_key(thread)} was already reported ({what}); "
                f"nothing was repeated.")
    if verdict == "filtered_bot":
        return (f"Ignored a notification from {one_line((thread or {}).get('actor'), 60)} "
                f"because a bot or GitHub App sent it.")
    if verdict == "notification":
        return (f"A GitHub notification from {one_line((thread or {}).get('actor'), 60) or 'someone'} "
                f"is new: {one_line((thread or {}).get('title'), 120) or 'no title'}.")
    if verdict == "repo_clean":
        total = info.get("total", 0)
        return (f"Repo check '{one_line((thread or {}).get('name'), 60)}': all {total} "
                f"checks passed.")
    if verdict.startswith("repo_failed:"):
        return (f"Repo check '{one_line((thread or {}).get('name'), 60)}': "
                f"{verdict.split(':', 1)[1]} - it needs you.")
    if verdict == "budget_dropped":
        return (f"PR #{pr} at {sha} was worth telling you about, but the "
                f"interruption budget was spent, so it was dropped.")
    return (f"Nothing to report about {thread_key(thread)} "
            f"({one_line(verdict, 60) or 'no verdict'}).")


def _row(trigger: dict, thread: dict, *, outcome: str, reason: str,
         verdict: str, mode: str, now: float, shadow: str = "") -> dict:
    return {
        "at": float(now),
        "source": one_line((trigger or {}).get("source"), 40),
        "thread_key": thread_key(thread),
        "outcome": outcome,
        "reason_code": reason,
        "verdict": one_line(verdict, 60),
        "preview_text": one_line(preview(verdict, thread), 300),
        "mode": one_line(mode, 10),
        "shadow_reason_code": shadow,
    }


def gate(trigger: dict, thread: Optional[dict] = None, *,
         receipts=(), mode: str = "active", now: float = 0.0) -> dict:
    """The deterministic filter. Pure: no I/O, no clock, no model, no GPU.

    `trigger` is what a poll saw; `thread` defaults to the trigger (for a pull
    request the two are the same shape) and carries any accumulated state.
    `receipts` is the set of receipt keys already recorded for this thread -
    passed in rather than read, which is what keeps this function a function.

    Returns a decision row (see the module docstring). `outcome` is
    `"would_notify"` or `"ignored"`; only the caller, having actually delivered
    something, may turn the first into `"notified"`.
    """
    trigger = trigger if isinstance(trigger, dict) else {}
    thread = dict(thread or trigger)
    mode = one_line(mode, 10) or "active"
    source = one_line(trigger.get("source"), 40)
    receipts = set(receipts or ())
    if not thread.get("source"):
        thread["source"] = source

    def ignored(reason: str, verdict: str) -> dict:
        return _row(trigger, thread, outcome="ignored", reason=reason,
                    verdict=verdict, mode=mode, now=now)

    def would(reason: str, verdict: str) -> dict:
        # In observe mode the row says the verdict, and `shadow_reason_code`
        # says why it was only written down. The owner reading the log wants
        # both: WHAT it was, and that nothing was delivered.
        shadow = "observe_shadow_logged" if mode == "observe" else ""
        return _row(trigger, thread, outcome="would_notify", reason=reason,
                    verdict=verdict, mode=mode, now=now, shadow=shadow)

    if mode == "off":
        return ignored("watch_off", "off")
    if source not in SOURCES:
        return ignored("source_not_allowed", "unknown_source")

    if source == "repo_check":
        failed = as_int(trigger.get("failed")) or 0
        total = as_int(trigger.get("total")) or 0
        if failed:
            return would("repo_check_failed", f"repo_failed:{failed} of {total}")
        return ignored("repo_check_clean", "repo_clean")

    if source == "github_notifications":
        actor = one_line(trigger.get("actor"), 80)
        tid = one_line(trigger.get("id") or trigger.get("thread_id"), 60)
        thread["actor"] = actor
        thread["title"] = one_line(trigger.get("title"), 120)
        if is_bot(actor):
            return ignored("filtered_bot_actor", "filtered_bot")
        key = receipt_key(0, tid, "notification")
        if key in receipts:
            return ignored("duplicate_sha_state", f"duplicate:notification:{tid}")
        return would("notification_for_you", "notification")

    # --- github_pr_ci: the seven required checks, and one batch ------------
    pr = as_int(trigger.get("pr"))
    head_sha = one_line(trigger.get("head_sha"), 40)
    mergeable = one_line(trigger.get("mergeable"), 20).upper()
    info = classify(thread)
    if not pr or not head_sha:
        return ignored("unreadable_trigger", "unreadable")
    if info["state"] == "none":
        return ignored("ci_no_required_checks", "no_required_checks")
    if info["state"] == "running":
        return ignored("ci_still_running_debounced", "running")
    if info["state"] == "failed":
        verdict = f"failed:{info['failed_job']}"
        if receipt_key(pr, head_sha, verdict) in receipts:
            return ignored("duplicate_sha_state", f"duplicate:{verdict}")
        return would("ci_required_failed", verdict)
    # All seven are green. GitHub's own mergeability answer is the second half
    # of the settle rule: "all green" is not "ready" on a conflicted branch.
    if mergeable == MERGEABLE:
        verdict = "all_green"
        if receipt_key(pr, head_sha, verdict) in receipts:
            return ignored("duplicate_sha_state", f"duplicate:{verdict}")
        return would("ci_all_required_green", verdict)
    verdict = f"green_not_mergeable:{mergeable or 'UNKNOWN'}"
    if receipt_key(pr, head_sha, verdict) in receipts:
        return ignored("duplicate_sha_state", f"duplicate:{verdict}")
    return would("ci_green_not_mergeable", verdict)
