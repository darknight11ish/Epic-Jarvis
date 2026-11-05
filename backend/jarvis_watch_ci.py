"""jarvis_watch_ci.py - "would my GitHub watcher have bothered me today?"

THE QUESTION THIS ANSWERS, IN THE OWNER'S OWN WORDS (2026-11-04). Before a
watcher is allowed to interrupt him, he wants to see what it WOULD have said:
*"what would your GitHub watcher have told me today?"* That is Pattern 1 from
`dsh-superagent`, adopted here by the spec he forwarded: a new proactive rule
starts in `observe` mode, runs the whole pipeline - poll, batch, evaluate - and
writes one structured decision row per event instead of speaking. When the log
shows no noise, the owner promotes the rule to `active`, which is the only
change between "shadow" and "real".

`GET /api/watch/decisions?limit=50` is that log. Each row carries `at`,
`source`, `thread_key`, `outcome`, `reason_code` (a closed set - see
`jarvis_watch.WATCH_REASONS`), `preview_text` (the exact one-line message that
was, or would have been, shown), `mode`, `verdict`, `delivery` and, in observe
mode, `shadow_reason_code`.

THE SHAPE OF THE SEVEN-CHECK PROBLEM, AND WHY ONE THREAD. A pull request runs
seven checks that gate a merge (`REQUIRED_CI_JOBS`) plus two that are
informational (`audit`, `python-advisories`). They finish minutes apart - `rust`
in three, `frontend` in five, `backend` in about fifty-five. Polling naively
speaks seven times per pull request. So every poll is folded into ONE thread,
`thread_key = f"pr:{number}:{head_sha[:9]}"`, and the rule is (Pattern 2):

  * **fail fast** - any required check FAILURE/TIMED_OUT/ACTION_REQUIRED, or any
    other terminal conclusion that is not SUCCESS, speaks ONCE, immediately;
  * **settle green** - all seven SUCCESS *and* `mergeable == "MERGEABLE"`
    speaks ONCE;
  * **still running, nothing failed** - stays silent
    (`ci_still_running_debounced`) until it settles;
  * **a terminal verdict already reported for this (pr, head_sha, verdict)** -
    silent (`duplicate_sha_state`), so twenty polls of one commit alert once.

TWO STAGES, AND ONLY ONE OF THEM CAN COST ANYTHING (Pattern 3). `gate()` in
`jarvis_watch_policy.py` is pure: no disk, no network, no model. This module is
the second stage. `assess()` may run only for a terminal event that actually
needs a summary - a failed REQUIRED check - and it fetches the failing job's own
log through the same deterministic `gh` path the poll uses. An informational
check, a duplicate, a quiet batch and a bot notification never reach it: the
call sits behind the gate's answer, and `backend/test_watch_ci.py` proves it by
passing a counter that must stay at zero.

NO MODEL IS CALLED ON THIS PC TODAY, SAID PLAINLY. `assess_failure()` has a
`summarizer` seam, and nothing passes one: the shipped code formats its one line
from the log text with plain string work. That keeps rule 1 trivially true and
keeps a background watcher from waking a graphics card to say "rust failed".

WRITE-BEFORE-SEND, SO A RESTART CANNOT LOSE A NOTICE (Pattern 5B). In `active`
mode a terminal verdict is written to `jarvis_outbox` (kind `pr_ci_notice`) and
its receipt is recorded BEFORE anything is delivered. A crash between those
writes and the delivery therefore leaves a pending outbox entry that the next
run re-sends exactly once; a crash after them cannot lose it, because the entry
is the record. The honest limit is in `jarvis_outbox`'s docstring: at-least-once.

WATCHERS STAY OFF UNTIL SOMETHING ASKS FOR THEM. This module registers a job
body (`watch_pr_checks`) and a route; it starts no thread, no timer and no
polling of its own. Nothing is watched until a job is created with a pull
request number, and its ALERT mode still defaults to `observe` - so even a
running watcher does not interrupt anybody until the owner promotes it.

WHERE THINGS LIVE. `watch-decisions.json` (the ring buffer, bounded) and
`watch-receipts.json` (the idempotency keys) sit beside `watch.db` in the
settings folder, or wherever `JARVIS_WATCH_CI_DIR` points - which is how the
suites keep a direct run off the owner's real files.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlsplit

import jarvis_watch
import jarvis_watch_policy as policy

try:
    import jarvis_outbox as outbox
except Exception:                                      # pragma: no cover
    outbox = None

#: The route this module answers. It is added by wrapping the running server's
#: `do_GET` (this module's `install()`), the same way `jarvis_watch_notify.py`
#: adds its own - `jarvis_hud.py`'s real text is not in this repository, so a new
#: route can only be added after the handler is built.
PATH = "/api/watch/decisions"

#: How many decision rows the ring buffer keeps. Old enough to answer "today",
#: bounded so a busy month cannot grow the file without limit.
MAX_DECISIONS = 500

#: How many receipts are kept. One per terminal verdict per commit, so this is
#: hundreds of pull requests' worth; the oldest go first.
MAX_RECEIPTS = 2000

#: The job body's registered name. `jarvis_jobs.register()` is how a job runs
#: with nobody looking, and this is the name a Work pane's `POST /api/jobs`
#: sends as `kind`.
HANDLER = "watch_pr_checks"

#: The action the handler asks before it reads GitHub, exactly like
#: `jarvis_watch.register_job()`'s own `github_read`. A job created with
#: `needs: ["github_read"]` already carries the owner's yes and never parks.
ACTION = "github_read"

_LOCK = threading.RLock()
_STORE: Optional["Store"] = None
_ARMED = False


# --------------------------------------------------------------------------
#   Where the store is
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    try:
        import jarvis_framework as fw
        return Path(fw.CONFIG_DIR)
    except Exception:
        env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
        if env:
            return Path(os.path.expanduser(env))
        return Path(os.path.expanduser("~")) / ".openjarvis"


def store_dir() -> Path:
    """Beside `watch.db` unless told otherwise, so the watcher's own files stay
    together and a suite can move all of them with one variable."""
    env = os.environ.get("JARVIS_WATCH_CI_DIR")
    if env:
        return Path(os.path.expanduser(env))
    try:
        return Path(jarvis_watch.DB_PATH).parent
    except Exception:                                  # pragma: no cover
        return _config_dir()


def _write(doc: dict, path: Path) -> None:
    """One crash-safe writer for both files, shared with the outbox."""
    if outbox is not None:
        outbox.write_json_atomic(path, doc)
        return
    path.parent.mkdir(parents=True, exist_ok=True)     # pragma: no cover
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def _read(path: Path) -> dict:
    if outbox is not None:
        doc, _note = outbox.read_json(path)
        return doc if isinstance(doc, dict) else {}
    try:                                               # pragma: no cover
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


# --------------------------------------------------------------------------
#   The decisions ring buffer and the receipts
# --------------------------------------------------------------------------

class Store:
    """Two small JSON files: what was decided, and what was already reported.

    Both are written with `write_json_atomic` (temp file, flush, rename), so a
    reader never sees half a file and a crash leaves the previous whole one.
    Both are bounded. Neither is authoritative about anything except history:
    the receipts only stop a repeat, and losing them costs one repeat, never a
    missed alert.
    """

    def __init__(self, decisions_path=None, receipts_path=None):
        base = store_dir()
        self.decisions_path = Path(decisions_path or (base / "watch-decisions.json"))
        self.receipts_path = Path(receipts_path or (base / "watch-receipts.json"))

    # -- decisions ---------------------------------------------------------

    def record(self, row: dict, *, now: Optional[float] = None) -> dict:
        row = dict(row or {})
        row.setdefault("at", float(now if now is not None else time.time()))
        with _LOCK:
            doc = _read(self.decisions_path)
            rows = doc.get("rows")
            rows = rows if isinstance(rows, list) else []
            nxt = int(doc.get("next_id") or 1)
            row["id"] = nxt
            rows.append(row)
            if len(rows) > MAX_DECISIONS:
                rows = rows[-MAX_DECISIONS:]
            _write({"version": 1, "next_id": nxt + 1, "rows": rows},
                   self.decisions_path)
        return row

    def decisions(self, limit: int = 50) -> list:
        with _LOCK:
            doc = _read(self.decisions_path)
        rows = doc.get("rows")
        rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
        rows.reverse()
        return rows[:max(1, int(limit))]

    # -- receipts ----------------------------------------------------------

    def receipts(self) -> dict:
        with _LOCK:
            doc = _read(self.receipts_path)
        got = doc.get("receipts")
        return got if isinstance(got, dict) else {}

    def receipt_keys_for(self, thread_key: str) -> list:
        """The receipt keys that belong to one thread, so `gate()` can answer
        "have I already reported this exact result?" without any I/O of its
        own. A pull request's keys are `<pr>:<sha>:...`; a notification's are
        `0:<id>:notification`."""
        parts = str(thread_key or "").split(":")
        prefix = ""
        if len(parts) == 3 and parts[0] == "pr":
            prefix = f"{parts[1]}:"
        elif len(parts) >= 2 and parts[0] == "notification":
            prefix = "0:"
        return [k for k in self.receipts() if not prefix or k.startswith(prefix)]

    def receipt(self, key: str) -> Optional[dict]:
        return self.receipts().get(str(key))

    def record_receipt(self, key: str, *, verdict: str, pr=0, head_sha: str = "",
                       mode: str = "", source: str = "",
                       now: Optional[float] = None) -> dict:
        key = str(key or "")[:240]
        entry = {"pr": int(pr or 0), "head_sha": str(head_sha or "")[:40],
                 "verdict": str(verdict or "")[:60], "mode": str(mode or "")[:10],
                 "source": str(source or "")[:40],
                 "at": float(now if now is not None else time.time())}
        if not key:
            return entry
        with _LOCK:
            doc = _read(self.receipts_path)
            got = doc.get("receipts")
            got = got if isinstance(got, dict) else {}
            if key in got:
                return entry
            got[key] = entry
            if len(got) > MAX_RECEIPTS:
                for old in sorted(got, key=lambda k: float(got[k].get("at") or 0))[
                        : len(got) - MAX_RECEIPTS]:
                    got.pop(old, None)
            _write({"version": 1, "receipts": got}, self.receipts_path)
        return entry

    def status(self) -> dict:
        with _LOCK:
            drows = _read(self.decisions_path)
            rrows = _read(self.receipts_path)
        n = drows.get("rows")
        got = rrows.get("receipts")
        return {"decisions": len(n) if isinstance(n, list) else 0,
                "receipts": len(got) if isinstance(got, dict) else 0,
                "decisions_path": str(self.decisions_path),
                "receipts_path": str(self.receipts_path)}


def default_store() -> Store:
    global _STORE
    with _LOCK:
        if _STORE is None:
            _STORE = Store()
        return _STORE


def set_store(store: Optional[Store]) -> Optional[Store]:
    """Point the module at another store (the suites, and nothing else)."""
    global _STORE
    with _LOCK:
        _STORE = store
        return _STORE


def _reset_for_tests() -> None:
    global _STORE, _ARMED
    with _LOCK:
        _STORE = None
        _ARMED = False


# --------------------------------------------------------------------------
#   The mode: observe by default, and nothing else
# --------------------------------------------------------------------------

def mode_from(value) -> str:
    """One of `jarvis_watch.WATCH_MODES`, and a bad value is OBSERVE.

    Failing to observe rather than to active is deliberate: a settings file
    with a typo in it must not turn a shadow watcher into one that speaks.
    """
    got = str(value if value is not None else "").strip().lower()
    return got if got in jarvis_watch.WATCH_MODES else "observe"


def alert_mode() -> str:
    """This watcher's alert mode, from `[watch] pr_checks_mode`."""
    try:
        return mode_from(jarvis_watch._cfg("pr_checks_mode", "observe"))
    except Exception:                                  # pragma: no cover
        return "observe"


#: Readable alias. A local variable named `mode` (the argument every entry
#: point takes) shadows it, so the internal calls use `alert_mode()`.
mode = alert_mode


# --------------------------------------------------------------------------
#   Talking to GitHub - the deterministic path, injectable for tests
# --------------------------------------------------------------------------

def _gh() -> str:
    return shutil.which("gh") or "gh"


def runner_default(args: list, timeout: float = 25.0) -> str:
    """Run `gh` and return its stdout. Raises on a non-zero exit.

    The ONLY way this module reaches the network, and it is not a new tool: it
    is the same `gh` program the rest of this repository's tooling already uses.
    A test never gets here - every entry point takes `runner=`.

    The child gets `jarvis_child_env.inherited()`, never this process's whole
    environment, like every other spawn in this backend: `gh` needs PATH and
    the user's profile folders (it keeps its own sign-in in its config file, so
    it works without `GH_TOKEN`), and it must never be handed
    HUD_TOKEN/JARVIS_TOKEN. `inherited()` strips anything that looks like a
    secret, so those cannot leak even if one is set later.
    """
    import jarvis_child_env
    p = subprocess.run([_gh(), *args], capture_output=True, text=True,
                       timeout=timeout, env=jarvis_child_env.inherited())
    if p.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} exited {p.returncode}")
    return p.stdout or ""


def normalize_trigger(raw, *, pr=None, repo: str = "") -> dict:
    """`gh pr view --json ...` output -> the trigger `gate()` reads.

    Kept tolerant on purpose: GitHub's rollup holds two different shapes
    (`CheckRun` and `StatusContext`), either may be absent, and a field this
    function does not recognise must make the batch quieter, never louder.
    """
    doc = raw if isinstance(raw, dict) else {}
    number = doc.get("number") or pr
    return {
        "source": "github_pr_ci",
        "repo": str(repo or doc.get("repository") or "")[:120],
        "pr": int(number) if str(number or "").isdigit() else number,
        "head_sha": str(doc.get("headRefOid") or doc.get("headRefName") or "")[:40],
        "mergeable": str(doc.get("mergeable") or "")[:20],
        "title": str(doc.get("title") or "")[:120],
        "checks": doc.get("statusCheckRollup") or [],
    }


def poll(pr, *, runner: Optional[Callable] = None, repo: str = "") -> dict:
    """Read one pull request's rollup. Never raises: a watcher that cannot look
    records that it could not look, and says nothing."""
    runner = runner or runner_default
    args = ["pr", "view", str(pr), "--json",
            "number,headRefOid,mergeable,title,statusCheckRollup"]
    if repo:
        args += ["-R", str(repo)]
    try:
        raw = json.loads(runner(args) or "{}")
    except Exception as exc:                           # noqa: BLE001
        return {"source": "github_pr_ci", "pr": pr, "head_sha": "", "repo": repo,
                "mergeable": "", "checks": [],
                "error": f"{type(exc).__name__}"}
    return normalize_trigger(raw, pr=pr, repo=repo)


# --------------------------------------------------------------------------
#   Stage two: the optional summary of a failed required job
# --------------------------------------------------------------------------

_RUN_ID = re.compile(r"/actions/runs/(\d+)")


def _failed_check(thread: dict, job: str):
    checks = (thread or {}).get("checks")
    if isinstance(checks, dict):
        return checks.get(job) or {}
    for c in checks or ():
        if isinstance(c, dict) and str(c.get("name") or c.get("context") or "") == job:
            return c
    return {}


def assess_failure(decision: dict, thread: dict, *, runner: Optional[Callable] = None,
                   summarizer: Optional[Callable[[str], str]] = None) -> str:
    """One line about WHY a required check failed. Deterministic by default.

    Reached only from `evaluate()` and only when the decision's reason is
    `ci_required_failed`; the log is fetched with the same `gh` path the poll
    uses (the run id is read out of the check's own details URL, so nothing is
    guessed at). Any failure here returns "" and the caller keeps the
    deterministic preview - a watcher must never lose its line because a log
    could not be read.

    `summarizer` is the model seam and NOTHING passes one in the shipped code:
    with it absent this function is 0 GPU and does plain string work.
    """
    info = policy.classify(thread or {})
    job = info.get("failed_job") or str((decision or {}).get("verdict", "")).split(":", 1)[-1]
    if not job:
        return ""
    check = _failed_check(thread or {}, job)
    url = str(check.get("detailsUrl") or check.get("url") or check.get("targetUrl") or "")
    m = _RUN_ID.search(url)
    if not m:
        return ""
    runner = runner or runner_default
    try:
        text = runner(["run", "view", m.group(1), "--log-failed"]) or ""
    except Exception:                                  # noqa: BLE001
        return ""
    line = ""
    for raw in str(text).splitlines():
        s = " ".join(raw.replace("\r", " ").split())
        if not s:
            continue
        if s.startswith("##[error]"):
            # GitHub's own error marker, and what follows it is the line worth
            # having. Skipped as scaffolding, it used to hide the only real
            # error in the whole log.
            s = s[len("##[error]"):].strip()
            if not s:
                continue
        elif s.startswith("##["):
            # ##[group], ##[section], ##[command] - scaffolding, not failures.
            continue
        low = s.lower()
        if "error" in low or "failed" in low or "panic" in low or "assert" in low:
            line = s[:180]
            break
    if not line:
        return ""
    if summarizer is not None:
        try:
            line = str(summarizer(line) or line)[:180]
        except Exception:                              # noqa: BLE001
            pass
    pr = policy.as_int((thread or {}).get("pr")) or 0
    sha = str((thread or {}).get("head_sha") or "")[:9]
    return policy.one_line(
        f"PR #{pr}: required check '{job}' failed on {sha} - {line}", 300)


# --------------------------------------------------------------------------
#   Delivering a notice, when the mode is active
# --------------------------------------------------------------------------

def _notify_arbiter(decision: dict) -> Optional[str]:
    """Hand one notice to the ONE authority that decides whether to interrupt.

    `jarvis_arbiter.deliver()` is that authority (`docs/ARCHITECTURE.md` section
    3): it owns the interruption budget, the digest and the mute switch, and it
    answers with a channel. `None` means it could not be reached or could not
    answer at all, and that is DELIBERATELY distinct from "dropped": None leaves
    the outbox entry pending so the next active run (or the next start) delivers
    it, while "dropped" is the arbiter's own decision and is settled. Collapsing
    the two would turn a missing module into a silently lost notice.
    """
    failed = str(decision.get("reason_code") or "") == "ci_required_failed"
    try:
        import jarvis_arbiter
        got = jarvis_arbiter.deliver(
            source="github-watch-ci",
            title=str(decision.get("preview_text") or "GitHub watch")[:300],
            body=str(decision.get("preview_text") or "")[:4000],
            kind="job",
            priority="high" if failed else "normal",
            can_defer=not failed,
            ref=str(decision.get("thread_key") or ""),
        )
        return str(getattr(got, "channel", "") or "") or None
    except Exception:                                  # noqa: BLE001
        return None


def _deliver_pending(notify: Callable[[dict], object], *, now=None) -> list:
    """Send the `pr_ci_notice` entries a previous run wrote but never delivered.

    This is the crash window closing: written before the send, so a restart has
    the entry; this drains it. Only this module's own kind - the job queue
    drains `job_card`/`job_done` itself, because it owns those senders.
    """
    if outbox is None:
        return []
    done = []
    for entry in outbox.pending("pr_ci_notice", limit=20):
        payload = entry.get("payload") or {}
        want = payload.get("decision") if isinstance(payload, dict) else None
        try:
            channel = notify(want or payload)
        except Exception:                              # noqa: BLE001
            continue
        if channel is None:
            continue            # still owed: the sender could not answer
        if channel == "dropped":
            outbox.resolve("pr_ci_notice", entry["key"], now=now, why="dropped")
        else:
            outbox.resolve("pr_ci_notice", entry["key"], now=now, why=str(channel))
        done.append(entry["key"])
    return done


# --------------------------------------------------------------------------
#   The pipeline: poll -> gate -> (assess) -> deliver or shadow -> decision row
# --------------------------------------------------------------------------

def _notice_key(thread_key: str, verdict: str) -> str:
    """The delivery-level dedupe key for one notice. Deterministic, and it
    carries the verdict because a fixed commit that settles green after a
    failure owes the owner two different sentences."""
    return f"{thread_key}:{str(verdict or '')[:60]}"


def evaluate(trigger: dict, *, mode: Optional[str] = None, now: Optional[float] = None,
             store: Optional[Store] = None, notify: Optional[Callable] = None,
             assess: Optional[Callable] = None, thread: Optional[dict] = None) -> dict:
    """One event through the whole pipeline, ending in exactly one decision row.

    Nothing here decides anything `gate()` did not: this function's jobs are to
    look up the receipts, call the second stage when (and only when) the gate
    admitted a terminal failure, write what it is about to do, deliver it in
    `active` mode, and record the row. In `observe` mode it writes the row and
    returns - that is the whole difference between the two modes.
    """
    now = time.time() if now is None else float(now)
    store = store or default_store()
    mode = mode_from(mode if mode is not None else alert_mode())
    thread = dict(thread or (trigger if isinstance(trigger, dict) else {}))
    notify = notify or _notify_arbiter
    tkey = policy.thread_key(thread)

    # 1. The switch is checked BEFORE the gate and before anything else: `off`
    #    is a watcher that does nothing at all, so it must not even drain.
    if mode == "off":
        return store.record(policy.gate(trigger, thread, receipts=(), mode=mode,
                                        now=now), now=now)

    # 2. Anything a previous run wrote but never delivered, first, so a restart
    #    cannot leave a notice pending for ever. ONLY in `active` mode: draining
    #    is a delivery, and the promise `observe` makes is that nothing is
    #    delivered. A pending notice therefore waits for the mode to be
    #    promoted (or for the next `active` poll) instead of being sent by a
    #    shadow run - the one rule this module must never break.
    if mode == "active":
        _deliver_pending(notify, now=now)

    decision = policy.gate(trigger, thread,
                           receipts=store.receipt_keys_for(tkey), mode=mode, now=now)
    if decision.get("outcome") != "would_notify":
        return store.record(decision, now=now)

    # 3. Stage two. Only a terminal failure of a REQUIRED check has anything to
    #    summarise, and only this branch can reach the fetch.
    if decision.get("reason_code") == "ci_required_failed" and assess is not None:
        try:
            better = assess(decision, thread)
        except Exception:                              # noqa: BLE001
            better = ""
        if better:
            decision["preview_text"] = policy.one_line(better, 300)

    verdict = str(decision.get("verdict") or "")
    receipt = policy.receipt_key(thread.get("pr"),
                                 thread.get("head_sha") or str(thread.get("id") or ""),
                                 verdict)
    decision["receipt_key"] = receipt
    decision["delivery"] = "shadow"

    if mode == "observe":
        # The spec's own rule: a terminal verdict logged in observe mode is
        # recorded as a receipt too, so promoting to active later cannot
        # re-report a commit that is already finished.
        store.record_receipt(receipt, verdict=verdict, pr=thread.get("pr") or 0,
                             head_sha=thread.get("head_sha") or "",
                             mode=mode, source=decision.get("source") or "", now=now)
        return store.record(decision, now=now)

    # 4. Active: write it down, then receipt it, then deliver. In that order,
    #    so a crash at any point either loses nothing (the outbox entry is
    #    pending and gets drained) or repeats once (at-least-once, said plainly
    #    in jarvis_outbox's docstring).

    key = _notice_key(tkey, verdict)
    if outbox is not None:
        st = outbox.enqueue("pr_ci_notice", key,
                            {"decision": decision, "preview_text":
                             decision.get("preview_text") or ""}, now=now)
        if st.get("state") == "duplicate" and st.get("entry", {}).get("state") == "done":
            dup = dict(decision, outcome="ignored",
                       reason_code="duplicate_sha_state", delivery="already",
                       preview_text=policy.preview(f"duplicate:{verdict}", thread))
            return store.record(dup, now=now)
    store.record_receipt(receipt, verdict=verdict, pr=thread.get("pr") or 0,
                         head_sha=thread.get("head_sha") or "",
                         mode=mode, source=decision.get("source") or "", now=now)
    try:
        channel = notify(decision)
    except Exception:                                  # noqa: BLE001
        channel = None
    if channel is None:
        decision["delivery"] = "failed"
        decision["outcome"] = "would_notify"
        return store.record(decision, now=now)
    if outbox is not None:
        outbox.resolve("pr_ci_notice", key, now=now, why=str(channel))
    if str(channel) == "dropped":
        decision["outcome"] = "ignored"
        decision["reason_code"] = "attention_budget_dropped"
        decision["delivery"] = "dropped"
    else:
        decision["outcome"] = "notified"
        decision["delivery"] = "sent"
    return store.record(decision, now=now)


def decisions(limit: int = 50, *, store: Optional[Store] = None) -> list:
    """The recent rows, newest first - what `GET /api/watch/decisions` serves."""
    return (store or default_store()).decisions(limit)


def status(*, store: Optional[Store] = None) -> dict:
    st = (store or default_store()).status()
    st.update({"mode": alert_mode(), "modes": list(jarvis_watch.WATCH_MODES),
               "required_jobs": list(policy.REQUIRED_CI_JOBS),
               "informational_jobs": list(policy.INFORMATIONAL_CI_JOBS),
               "armed": _ARMED, "handler": HANDLER, "path": PATH})
    return st


# --------------------------------------------------------------------------
#   The job body: what makes this run with nobody looking
# --------------------------------------------------------------------------
# Registered by NAME, exactly like `jarvis_watch.register_job()`, because
# jarvis_jobs stores a handler name and a params dict and never code. Nothing
# here starts on its own: a job is created through POST /api/jobs, and until
# then this module polls nothing.

def handler(ctx, params: dict) -> dict:
    """One poll of the pull requests named in `params`, then one row each.

    `params` is `{"pr": 1135}` or `{"prs": [1135, 1140]}` plus an optional
    `"repo"`. In `off` mode nothing is fetched at all - the switch is checked
    before the network, not after.
    """
    params = params or {}
    m = alert_mode()
    if m == "off":
        return {"mode": "off", "checked": 0, "note": "the watcher is switched off"}
    prs = []
    if params.get("pr"):
        prs.append(params.get("pr"))
    for p in params.get("prs") or ():
        prs.append(p)
    out_prs = []
    seen = set()
    for p in prs:
        try:
            n = int(p)
        except (TypeError, ValueError):
            continue
        if n in seen:
            continue
        seen.add(n)
        out_prs.append(n)
    if not out_prs:
        return {"mode": m, "checked": 0,
                "note": "no pull request number - nothing was watched"}
    # Rule 4's shape, the same one `watch_github` uses: reading the owner's own
    # GitHub is a real capability and it ASKS. A job created with
    # `needs: ["github_read"]` already carries that yes (the frozen set) and
    # never parks; one created with `needs: []` parks with ONE one-shot grant
    # and the owner's Allow once spends it for this tick.
    ctx.require(ACTION)
    runner = params.get("_runner") if callable(params.get("_runner")) else None
    repo = str(params.get("repo") or "")
    rows = []
    for n in out_prs:
        trigger = poll(n, runner=runner, repo=repo)
        if trigger.get("error"):
            rows.append({"pr": n, "outcome": "ignored", "reason_code": "unreadable_trigger"})
            continue
        row = evaluate(trigger, mode=m, assess=lambda d, t: assess_failure(d, t, runner=runner))
        rows.append({"pr": n, "outcome": row.get("outcome"),
                     "reason_code": row.get("reason_code"),
                     "preview_text": row.get("preview_text")})
    try:
        ctx.progress(f"checked {len(out_prs)} pull request(s)")
    except Exception:                                  # noqa: BLE001
        pass
    return {"mode": m, "checked": len(out_prs), "decisions": rows}


def register_job() -> bool:
    """Make `watch_pr_checks` a Long Fuse job body. False if the queue is not
    importable - the route below still works, and nothing polls."""
    try:
        import jarvis_jobs
    except Exception:
        return False
    jarvis_jobs.register(HANDLER, handler)
    return True


# --------------------------------------------------------------------------
#   The route: GET /api/watch/decisions
# --------------------------------------------------------------------------

def view(limit: Optional[str] = None, *, store: Optional[Store] = None) -> dict:
    """The body of the route. `limit` is the raw query value; anything that is
    not a whole number in 1..200 is clamped rather than refused, because this
    is a read and the owner asked for "the recent ones"."""
    n = 50
    if limit is not None and str(limit).strip():
        try:
            n = int(str(limit).strip())
        except (TypeError, ValueError):
            n = 50
    n = max(1, min(200, n))
    st = status(store=store)
    return {"available": True,
            "mode": st["mode"],
            "modes": st["modes"],
            "required_jobs": st["required_jobs"],
            "informational_jobs": st["informational_jobs"],
            "count": len(decisions(n, store=store)),
            "decisions": decisions(n, store=store),
            "reasons": dict(jarvis_watch.WATCH_REASONS)}


def armed() -> bool:
    """True once `install()` has wrapped the running server's do_GET."""
    return _ARMED


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` so `GET /api/watch/decisions` is answered here,
    after the server's own origin and token checks. Every other GET goes
    straight to the original - the same shape as `jarvis_watch_notify.install()`.
    """
    global _ARMED
    get0 = handler_cls.do_GET
    if getattr(get0, "_jarvis_watch_decisions", False):
        _ARMED = True
        return f"  watch      What the GitHub watcher would say answers at {PATH} (already on)"

    def do_GET(self):
        route = urlsplit(str(getattr(self, "path", "") or ""))
        if route.path.rstrip("/") != PATH:
            return get0(self)
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return None
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return None
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return None
        try:
            q = parse_qs(route.query or "")
            out = view((q.get("limit") or [None])[0])
        except Exception as exc:                       # noqa: BLE001
            return self._send(503, {"error": type(exc).__name__})
        return self._send(200, out)

    do_GET._jarvis_watch_decisions = True
    handler_cls.do_GET = do_GET
    _ARMED = True
    return (f"  watch      GitHub watcher in {alert_mode()} mode; what it would say "
            f"answers at {PATH}")


if __name__ == "__main__":                             # pragma: no cover
    import pprint
    pprint.pprint(view("10"))
