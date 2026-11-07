"""
jarvis_watch.py - "tell me what's new on GitHub for the things I care about".

You name a topic. Jarvis searches GitHub for it on a schedule, remembers what
it has already shown you, and the next time you ASK it tells you what is new
and what has moved since. It does not come and find you: this is a pull, and
the whole module is built around that being the default rather than a setting
you have to go and switch off.

Four decisions worth reading before the code.

PULL, NOT PUSH. "Keep me updated if I ask" is a different feature from "tell
me when something happens", and building the second and calling it the first
is how a tool ends up muted. Nothing here interrupts. Results accumulate and
`report()` hands them over when asked. A topic can be marked `notify = true`
individually if you want it in the daily digest, and even then it goes through
jarvis_arbiter with can_defer set, so it lands in the brief and never in the
room.

A REPO PAGE IS TEXT FROM A STRANGER. A repository description, its topic tags
and its README are written by whoever published it, and they arrive in front
of a model that reads them as if you had typed them. This is exactly the
surface jarvis_content_risk exists for, so every field goes through it: the
invisible characters come out, hidden instructions are refused, and a repo that
tries to hurry you into installing it gets flagged rather than summarised. A
search result that fails the scan is still LISTED - you should know it exists -
but its text is replaced with the reason and it is never handed to a model.

NEW AND UPDATED ARE DIFFERENT QUESTIONS. "New" is easy: an id never seen
before. "Updated" is the one that needs care, because a repository's push
timestamp moves every time somebody fixes a typo. An update is only worth your
attention when something structural changed: a new release tag, the licence
changed, it got archived, the description changed, or the star count moved by
enough to mean something. Everything else is noise wearing a timestamp.

THE LICENCE IS A FIRST-CLASS FIELD, not a footnote. This build is
non-commercial and its whole dependency policy is "state the licence", so an
entry without one says so in the list rather than being quietly listed as
though it were fine.

THE ONE ASKING STEP (DEF-024, 2026-10-31). `register_job()` is the ONE
production job body on this PC, and its handler ASKS before it searches:
`ctx.require("github_read")` - the same action name `jarvis_tellme.py`'s own
GitHub look uses. A job scheduled with `needs: []` (which both Work panes send
on purpose) therefore parks in `waiting_approval` with ONE one-shot grant, and
the Work pane offers "No" and "Allow once". No fails the job without a search;
Allow once spends the grant and the search runs on the retry tick. Nothing
here widens the frozen set or leaves a standing rule - the park/answer/spend
loop is the queue's own (`docs/ARCHITECTURE.md` section 10).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import jarvis_framework as fw
    _CFG_DIR = Path(fw.CONFIG_DIR)
except Exception:                                    # pragma: no cover
    fw = None
    _CFG_DIR = Path(os.path.expanduser("~/.openjarvis"))

DB_PATH = Path(os.environ.get("JARVIS_WATCH_DB", str(_CFG_DIR / "watch.db")))
UA = "jarvis-watch/1.0 (personal, non-commercial)"
API = "https://api.github.com"

# --------------------------------------------------------------------------
#   How loud a watcher is allowed to be (pattern 1, 2026-11-04)
# --------------------------------------------------------------------------
# A proactive watcher has three states, not two, and the middle one is the
# point. `observe` runs the WHOLE pipeline - polling, batching, evaluation,
# receipts - and never interrupts anybody: it writes a decision row (see
# `jarvis_watch_policy.py` and `jarvis_watch_ci.py`) saying what it would have
# said. That is how a rule earns `active`: the owner reads
# `GET /api/watch/decisions?limit=50` and promotes it once the log shows no
# noise. The alternative - build the rule, switch it on, get interrupted - is
# how a watcher ends up muted.
#
# NEW PROACTIVE RULES DEFAULT TO `observe`. Nothing existing changed: the topic
# watcher below is a PULL and has no mode at all, because it never speaks
# unless asked, and this tuple is about the rules that would otherwise reach
# out. `off` is still what "no watcher" means - the CI watcher is off until a
# job names a pull request, and its ALERT mode is `observe` even then.
WATCH_MODES: tuple = ("off", "observe", "active")

#: The closed set of reasons a decision row may carry. Closed on purpose: the
#: owner reads these rows to decide whether a watcher is trustworthy, so a
#: free-text reason would be unpublishable. `jarvis_watch_ci.py` only returns
#: keys from here, and `backend/test_watch_ci.py` checks both directions.
WATCH_REASONS: dict = {
    # -- pull-request CI (the seven required checks) ----------------------
    "ci_all_required_green": "All 7 required checks passed and the PR is mergeable",
    "ci_required_failed": "Required check {failed_job} failed on {head_sha}",
    "ci_still_running_debounced": "Checks still running ({done}/7 complete) - "
                                  "batched, waiting for settle",
    "ci_green_not_mergeable": "All 7 required checks passed but GitHub does "
                              "not report the PR as mergeable",
    "ci_no_required_checks": "This PR reports none of the 7 required checks, "
                             "so it is not one this watcher judges",
    # -- dedupe, filtering, and the shadow log ----------------------------
    "duplicate_sha_state": "Already reported this exact (pr, head_sha, verdict)",
    "observe_shadow_logged": "Recorded in observe mode (would notify if the "
                             "mode were active)",
    "filtered_bot_actor": "Sent by a bot or GitHub App, so never a person "
                          "asking for something",
    "notification_for_you": "A GitHub notification that is not from a bot and "
                            "has not been reported",
    "attention_budget_dropped": "The interruption budget was spent, so this "
                                "was offered and dropped",
    # -- this PC's own checkers, and the switch ---------------------------
    "repo_check_clean": "This PC's checker suite passed",
    "repo_check_failed": "This PC's checker suite failed",
    "watch_off": "The watcher is switched off; nothing was polled or recorded",
    "source_not_allowed": "The event came from a source this watcher does not read",
    "unreadable_trigger": "The poll answered something this watcher could not read",
    # -- per-repository watching (2026-11-07) -----------------------------
    "repo_new_release": "A new release was published in a watched repository",
    "repo_new_commit": "A new commit landed on the watched default branch",
    "repo_new_issue": "A new issue was opened in a watched repository",
    "repo_new_pr": "A new pull request was opened in a watched repository",
    "repo_ci_changed": "A watched repository's CI state changed on a new commit",
    "repo_new_repo": "A repository new to the followed topic appeared",
    "repo_observe_shadow": "Recorded in observe mode (would notify if the "
                           "watch were active)",
    "repo_frequency_off": "The watch is pull-only, so the item is kept and "
                          "never spoken",
    "repo_digest_due": "The daily or weekly digest carried this item",
    "repo_instant_due": "Handed to the notification pipeline as it arrived",
    "repo_baseline": "First poll records what already exists, so an old "
                     "release is not announced as new",
    "repo_poll_skipped": "Not due yet at this frequency, so GitHub was not "
                         "asked",
    "repo_unauthenticated_public": "Polled without a token; public data only",
}


def pr_checks_mode() -> str:
    """The CI watcher's alert mode: `[watch] pr_checks_mode` in the owner's
    settings file, `observe` when it is absent or unreadable.

    FAILING TO `observe` RATHER THAN TO `active` IS THE POINT. A settings file
    with a typo in it must not turn a shadow watcher into one that speaks; the
    cost of being wrong in this direction is that the owner sees the log instead
    of a notification, and the cost of being wrong in the other is the spam that
    made this feature necessary.
    """
    try:
        value = str(_cfg("pr_checks_mode", "observe") or "").strip().lower()
    except Exception:                                    # pragma: no cover
        return "observe"
    return value if value in WATCH_MODES else "observe"


_LOCK = threading.RLock()
_inited = False


def _cfg(key: str, default):
    try:
        return fw.load_framework().get("watch", {}).get(key, default)
    except Exception:
        return default


def _audit(event: str, detail: dict) -> None:
    try:
        fw.audit_log(event, detail)
    except Exception:
        pass


class RateLimited(RuntimeError):
    pass


# --------------------------------------------------------------------------
#   Talking to GitHub
# --------------------------------------------------------------------------
# The token is read from the environment and nowhere else. Unauthenticated
# search is 10 requests a minute, which is enough for a handful of topics
# checked a few times a day; a token raises it to 30 and is worth setting if
# you watch more than that. It is a public-data read either way: no token
# means fewer requests, not less information.

def _token() -> str:
    for name in ("JARVIS_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        v = os.environ.get(name, "").strip()
        if v:
            return v
    return ""


def _get(url: str, timeout: float = 12.0, headers: Optional[dict] = None) -> Optional[str]:
    h = {"User-Agent": UA, "Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    tok = _token()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    h.update(headers or {})
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise RateLimited(f"github rate-limited ({e.code})") from e
        return None
    except Exception:
        return None


def search_url(query: str, sort: str = "updated", per_page: int = 30) -> str:
    """GitHub's search syntax, built rather than pasted.

    `sort=updated` is the right default for this feature: the question is
    "what has moved", not "what is most popular". Popularity sorting would
    show the same famous repositories for ever.
    """
    q = urllib.parse.quote(query)
    return (f"{API}/search/repositories?q={q}&sort={sort}&order=desc"
            f"&per_page={max(1, min(100, int(per_page)))}")


# --------------------------------------------------------------------------
#   Storage
# --------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), timeout=10.0, isolation_level=None)
    c.row_factory = sqlite3.Row
    return c


def _init() -> None:
    global _inited
    with _LOCK:
        if _inited:
            return
        with closing(_connect()) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("""
                CREATE TABLE IF NOT EXISTS topics (
                    name     TEXT PRIMARY KEY,
                    query    TEXT NOT NULL,
                    min_stars INTEGER NOT NULL DEFAULT 0,
                    language TEXT,
                    notify   INTEGER NOT NULL DEFAULT 0,
                    added    REAL NOT NULL,
                    checked  REAL,
                    error    TEXT
                )""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS repos (
                    topic      TEXT NOT NULL,
                    repo_id    INTEGER NOT NULL,
                    full_name  TEXT NOT NULL,
                    stars      INTEGER NOT NULL DEFAULT 0,
                    licence    TEXT,
                    archived   INTEGER NOT NULL DEFAULT 0,
                    pushed_at  TEXT,
                    release    TEXT,
                    descr      TEXT,
                    first_seen REAL NOT NULL,
                    last_seen  REAL NOT NULL,
                    PRIMARY KEY (topic, repo_id)
                )""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS findings (
                    id        TEXT PRIMARY KEY,
                    topic     TEXT NOT NULL,
                    repo_id   INTEGER NOT NULL,
                    kind      TEXT NOT NULL,      -- new | updated
                    what      TEXT NOT NULL,      -- json: the changed fields
                    at        REAL NOT NULL,
                    reported  REAL
                )""")
            c.execute("CREATE INDEX IF NOT EXISTS ix_find_unreported"
                      " ON findings(reported, at)")
            # ---- per-repository watches (2026-11-07) --------------------
            # One row per repository the owner named, with its own frequency,
            # which parts it follows, and whether it may speak. The ETag
            # columns are the conditional-request memory: a poll that sends
            # them back costs 0 GitHub rate-limit points when nothing changed.
            c.execute("""
                CREATE TABLE IF NOT EXISTS repo_watches (
                    full_name      TEXT PRIMARY KEY,
                    frequency      TEXT NOT NULL DEFAULT 'daily',
                    prev_frequency TEXT NOT NULL DEFAULT 'daily',
                    events         TEXT NOT NULL DEFAULT '[]',
                    mode           TEXT NOT NULL DEFAULT 'observe',
                    etag_repo      TEXT, etag_releases TEXT, etag_commits TEXT,
                    etag_issues    TEXT, etag_prs      TEXT, etag_ci      TEXT,
                    added          REAL NOT NULL,
                    last_polled    REAL, last_said REAL, baselined INTEGER NOT NULL DEFAULT 0,
                    error          TEXT
                )""")
            # One row per ITEM, not per poll: the primary key is what makes a
            # second poll of the same release/commit/issue/PR say nothing.
            c.execute("""
                CREATE TABLE IF NOT EXISTS repo_items (
                    key       TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    kind      TEXT NOT NULL,
                    title     TEXT,
                    url       TEXT,
                    at        REAL NOT NULL,
                    seen      REAL NOT NULL,
                    said      REAL
                )""")
            # A followed topic: every repo that appears in its search for the
            # first time is an item; after that it is remembered and silent.
            c.execute("""
                CREATE TABLE IF NOT EXISTS repo_follows (
                    topic       TEXT PRIMARY KEY,
                    frequency   TEXT NOT NULL DEFAULT 'daily',
                    mode        TEXT NOT NULL DEFAULT 'observe',
                    added       REAL NOT NULL,
                    last_polled REAL, error TEXT
                )""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS repo_topic_seen (
                    topic     TEXT NOT NULL,
                    repo_id   INTEGER NOT NULL,
                    full_name TEXT NOT NULL,
                    first_seen REAL NOT NULL,
                    PRIMARY KEY (topic, repo_id)
                )""")
        _inited = True


# --------------------------------------------------------------------------
#   The watchlist
# --------------------------------------------------------------------------

@dataclass
class Topic:
    name: str
    query: str
    min_stars: int = 0
    language: str = ""
    notify: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def add(name: str, query: str = "", *, min_stars: int = 0,
        language: str = "", notify: bool = False) -> dict:
    """Watch a topic. `query` is GitHub search syntax; if you leave it out,
    the name is the query, which is what you want most of the time."""
    _init()
    name = str(name).strip()[:80]
    if not name:
        return {"ok": False, "reason": "a topic needs a name"}
    q = (query or name).strip()[:400]
    with closing(_connect()) as c:
        c.execute("INSERT INTO topics (name,query,min_stars,language,notify,added)"
                  " VALUES (?,?,?,?,?,?)"
                  " ON CONFLICT(name) DO UPDATE SET query=excluded.query,"
                  " min_stars=excluded.min_stars, language=excluded.language,"
                  " notify=excluded.notify",
                  (name, q, max(0, int(min_stars)), str(language)[:40],
                   1 if notify else 0, time.time()))
    _audit("watch.topic_added", {"topic": name, "notify": bool(notify)})
    return {"ok": True, "topic": name, "query": q}


def remove(name: str) -> dict:
    """Stop watching, and forget everything remembered about it. A watchlist
    you cannot empty is a watchlist that accumulates."""
    _init()
    with closing(_connect()) as c:
        n = c.execute("DELETE FROM topics WHERE name=?", (name,)).rowcount
        c.execute("DELETE FROM repos WHERE topic=?", (name,))
        c.execute("DELETE FROM findings WHERE topic=?", (name,))
    return {"ok": n > 0, "topic": name}


def topics() -> list:
    _init()
    with closing(_connect()) as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM topics ORDER BY name").fetchall()]


# --------------------------------------------------------------------------
#   Reading a search result safely
# --------------------------------------------------------------------------
# Every string below was written by whoever published the repository. None of
# it is trusted, and the scan happens BEFORE anything is stored - a refused
# description must not sit in the database waiting for some later code path to
# hand it to a model.

def _scan(text: str, where: str) -> tuple:
    """Returns (safe_text, note). `note` is non-empty when something was
    stripped or refused."""
    if not text:
        return "", ""
    try:
        import jarvis_content_risk as cr
        a = cr.assess(text, source=f"github:{where}", where=where, latch=False)
    except Exception:
        # No scanner: keep the text but say so, rather than silently trusting
        # it or silently dropping it.
        return text[:400], "not scanned - the content-risk module is unavailable"
    if a.verdict == "refuse":
        codes = sorted({f["code"] for f in a.findings + a.hidden_findings})
        return "", ("text withheld: this repository's " + where + " matched "
                    + ", ".join(codes[:3]) + ". The entry is listed so you know "
                    "it exists; its text was not passed to a model.")
    note = ""
    if a.rush:
        note = "this text tried to rush you: " + a.rush[0]["phrase"]
    elif a.normalised.get("stripped"):
        note = f"{a.normalised['stripped']} invisible characters removed"
    return a.text[:400], note


def _licence_of(item: dict) -> str:
    lic = item.get("license") or item.get("licence") or {}
    if isinstance(lic, dict):
        return str(lic.get("spdx_id") or lic.get("key") or "").strip()
    return str(lic or "").strip()


@dataclass
class Repo:
    repo_id: int
    full_name: str
    stars: int = 0
    licence: str = ""
    archived: bool = False
    pushed_at: str = ""
    release: str = ""
    descr: str = ""
    note: str = ""
    url: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _parse(item: dict) -> Optional[Repo]:
    try:
        rid = int(item.get("id"))
    except (TypeError, ValueError):
        return None
    name = str(item.get("full_name") or "")[:140]
    descr, note = _scan(str(item.get("description") or ""), "description")
    # Topic tags are short and are a favourite place to hide things, because
    # nobody reads them and a model does.
    tags = item.get("topics") or []
    if isinstance(tags, list) and tags:
        _t, tnote = _scan(" ".join(str(x) for x in tags[:20]), "topics")
        if tnote and not note:
            note = tnote
    return Repo(repo_id=rid, full_name=name,
                stars=int(item.get("stargazers_count") or 0),
                licence=_licence_of(item),
                archived=bool(item.get("archived")),
                pushed_at=str(item.get("pushed_at") or ""),
                descr=descr, note=note,
                url=f"https://github.com/{name}" if name else "")


# --------------------------------------------------------------------------
#   What counts as an update
# --------------------------------------------------------------------------
# A repository's push timestamp moves when somebody fixes a typo in a comment.
# If that counted, every check would return everything and the feature would be
# useless within a week. These are the changes that mean something.

def _changes(old: dict, new: Repo) -> list:
    out = []
    if bool(old["archived"]) != new.archived:
        out.append("archived" if new.archived else "un-archived")
    old_lic = (old["licence"] or "").strip()
    if old_lic != new.licence:
        out.append(f"licence {old_lic or 'none'} -> {new.licence or 'none'}")
    if (old["release"] or "") != new.release and new.release:
        out.append(f"new release {new.release}")
    if (old["descr"] or "") != new.descr and new.descr:
        out.append("description changed")
    # Stars: a proportional jump, floored, so a 40-star project going to 400
    # registers and a 40,000-star project gaining 60 does not.
    jump = float(_cfg("star_jump", 0.5) or 0.5)
    floor = int(_cfg("star_floor", 25) or 25)
    grew = new.stars - int(old["stars"] or 0)
    if grew >= max(floor, int(old["stars"] or 0) * jump):
        out.append(f"stars {old['stars']} -> {new.stars}")
    return out


# --------------------------------------------------------------------------
#   Checking
# --------------------------------------------------------------------------

def check(name: Optional[str] = None, *, fetcher: Optional[Callable] = None,
          now: Optional[float] = None) -> dict:
    """Run the search for one topic, or all of them. Records findings; tells
    nobody.

    `fetcher` defaults to None and is resolved HERE rather than being bound as
    a default argument. A default argument is evaluated once when the module
    loads, so `fetcher=_get` in the signature would freeze the original
    function and a caller who replaced the module's `_get` - to add backoff, a
    cache, or a test double - would find it silently ignored. Resolving at call
    time means one substitution reaches every call site.
    """
    _init()
    fetcher = fetcher or _get
    now = time.time() if now is None else now
    want = [t for t in topics() if name is None or t["name"] == name]
    out = {"checked": 0, "new": 0, "updated": 0, "errors": {}}
    for t in want:
        q = t["query"]
        if t["min_stars"]:
            q += f" stars:>={int(t['min_stars'])}"
        if t["language"]:
            q += f" language:{t['language']}"
        try:
            raw = fetcher(search_url(q))
        except RateLimited as exc:
            out["errors"][t["name"]] = str(exc)
            _note_error(t["name"], str(exc))
            continue
        if not raw:
            out["errors"][t["name"]] = "no response from GitHub"
            _note_error(t["name"], "no response from GitHub")
            continue
        try:
            items = json.loads(raw).get("items") or []
        except Exception as exc:
            out["errors"][t["name"]] = f"unreadable response ({exc})"
            _note_error(t["name"], "unreadable response")
            continue
        n_new, n_upd = _absorb(t["name"], items, now)
        out["checked"] += 1
        out["new"] += n_new
        out["updated"] += n_upd
        _note_error(t["name"], "", checked=now)
    _audit("watch.checked", {"topics": out["checked"], "new": out["new"],
                             "updated": out["updated"]})
    return out


def _note_error(topic: str, err: str, checked: Optional[float] = None) -> None:
    with closing(_connect()) as c:
        if checked is None:
            c.execute("UPDATE topics SET error=? WHERE name=?", (err[:200], topic))
        else:
            c.execute("UPDATE topics SET error=?, checked=? WHERE name=?",
                      (err[:200] or None, checked, topic))


def _absorb(topic: str, items: list, now: float) -> tuple:
    n_new = n_upd = 0
    with closing(_connect()) as c:
        for item in items:
            r = _parse(item if isinstance(item, dict) else {})
            if not r:
                continue
            old = c.execute("SELECT * FROM repos WHERE topic=? AND repo_id=?",
                            (topic, r.repo_id)).fetchone()
            if old is None:
                c.execute("INSERT INTO repos (topic,repo_id,full_name,stars,licence,"
                          "archived,pushed_at,release,descr,first_seen,last_seen)"
                          " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                          (topic, r.repo_id, r.full_name, r.stars, r.licence,
                           1 if r.archived else 0, r.pushed_at, r.release,
                           r.descr, now, now))
                _finding(c, topic, r, "new", ["first seen"], now)
                n_new += 1
                continue
            changed = _changes(dict(old), r)
            c.execute("UPDATE repos SET full_name=?,stars=?,licence=?,archived=?,"
                      "pushed_at=?,release=?,descr=?,last_seen=?"
                      " WHERE topic=? AND repo_id=?",
                      (r.full_name, r.stars, r.licence, 1 if r.archived else 0,
                       r.pushed_at, r.release, r.descr, now, topic, r.repo_id))
            if changed:
                _finding(c, topic, r, "updated", changed, now)
                n_upd += 1
    return n_new, n_upd


def _finding(c, topic: str, r: Repo, kind: str, what: list, now: float) -> None:
    fid = f"{topic}:{r.repo_id}:{kind}:{int(now)}"
    c.execute("INSERT OR REPLACE INTO findings (id,topic,repo_id,kind,what,at,reported)"
              " VALUES (?,?,?,?,?,?,NULL)",
              (fid, topic, r.repo_id, kind, json.dumps(what), now))


# --------------------------------------------------------------------------
#   Telling you - only when asked
# --------------------------------------------------------------------------

def report(topic: Optional[str] = None, limit: int = 50,
           mark: bool = True) -> dict:
    """What is new and what has moved since you last asked.

    `mark=False` is a peek. The default marks what it hands over, because the
    question is "what is new SINCE LAST TIME" and a report that does not
    remember having been read answers a different question every time.
    """
    _init()
    with closing(_connect()) as c:
        rows = c.execute(
            "SELECT f.*, r.full_name, r.stars, r.licence, r.archived, r.descr"
            " FROM findings f JOIN repos r"
            "   ON r.topic = f.topic AND r.repo_id = f.repo_id"
            " WHERE f.reported IS NULL" + (" AND f.topic = ?" if topic else "") +
            " ORDER BY f.at DESC LIMIT ?",
            ((topic, limit) if topic else (limit,))).fetchall()
        items = []
        for r in rows:
            try:
                what = json.loads(r["what"])
            except Exception:
                what = []
            items.append({
                "topic": r["topic"], "kind": r["kind"],
                "repo": r["full_name"],
                "url": f"https://github.com/{r['full_name']}",
                "stars": r["stars"],
                "licence": r["licence"] or "none stated",
                "archived": bool(r["archived"]),
                "description": r["descr"] or "",
                "what_changed": what, "at": r["at"],
            })
        if mark and rows:
            c.execute("UPDATE findings SET reported=? WHERE id IN ({})".format(
                ",".join("?" * len(rows))),
                [time.time(), *[r["id"] for r in rows]])
    new = [i for i in items if i["kind"] == "new"]
    upd = [i for i in items if i["kind"] == "updated"]
    return {"new": new, "updated": upd, "count": len(items),
            "topics": [t["name"] for t in topics()],
            "note": ("Licences are shown as GitHub reports them. 'none stated' "
                     "means the repository has no licence file, which is not the "
                     "same as permissive - it means you have no permission to "
                     "use it at all.")}


def to_digest(now: Optional[float] = None) -> int:
    """Hand anything from a `notify` topic to the arbiter, which will put it
    in the daily brief. Never speaks: `can_defer` is set, so if the budget
    happens to be free it still waits for the digest rather than taking an
    interruption for something that was never urgent."""
    _init()
    peek = report(mark=False, limit=200)
    wanted = {t["name"] for t in topics() if t["notify"]}
    sent = 0
    try:
        import jarvis_arbiter
    except Exception:
        return 0
    for item in peek["new"] + peek["updated"]:
        if item["topic"] not in wanted:
            continue
        verb = "is new" if item["kind"] == "new" else "changed"
        jarvis_arbiter.deliver(
            source="github-watch",
            title=f"{item['repo']} {verb} ({item['topic']})",
            body=(item["description"] or "") + "\n" + ", ".join(item["what_changed"]),
            kind="finding", priority="low", can_defer=True,
            ref=item["url"], want=jarvis_arbiter.NOTIFY, now=now)
        sent += 1
    return sent


# --------------------------------------------------------------------------
#   Running it unattended
# --------------------------------------------------------------------------

def register_job() -> bool:
    """Make this a Long Fuse job so it runs on a schedule without a
    conversation open. Registered by name rather than by handing over a
    callable, because jarvis_jobs stores a handler NAME and a params dict -
    never pickled code - and this module is the right place to say what its
    own handler is called.
    """
    try:
        import jarvis_jobs
    except Exception:
        return False

    def handler(ctx, params):
        # DEF-024 (2026-10-31): searching GitHub is a real capability, and the
        # framework's name for it is `github_read` - the action jarvis_tellme.py
        # already asks under for its own GitHub look. The frozen set on the row
        # is the owner's yes from when he scheduled this job; if it does not
        # carry `github_read`, require() parks the job in `waiting_approval`
        # with ONE one-shot grant, where the Work pane offers "No" / "Allow
        # once". No fails this job before anything is fetched; Allow once spends
        # the grant and this line passes on the retry tick. Nothing here widens
        # the set or writes a standing rule.
        #
        # This is the one production body that asks, so the park -> answer ->
        # spend loop is reachable on this PC and not only in the suite.
        ctx.require("github_read")
        # The frozen capability set is what makes this safe to leave running:
        # the job may search (now asked for explicitly above) and it may write
        # its own database, and there is no path by which it can widen that
        # while it runs.
        topic = (params or {}).get("topic")
        out = check(topic, fetcher=(params or {}).get("fetcher"))
        ctx.progress(f"checked {out['checked']} topic(s)")
        # Even here it does not speak. A notify topic reaches the daily brief;
        # everything else waits for the owner to ask.
        out["queued_for_digest"] = to_digest()
        return out

    jarvis_jobs.register("watch_github", handler)
    # THE CI WATCHER'S BODY REGISTERS HERE TOO, and this is the honest place
    # for it (2026-11-04). A job body must be registered by name before a route
    # can offer it, and the ONE start-up call that does that on this PC is
    # `jarvis_watch.register_job()`, from `jarvis_hud.main()` (jobs-routes.patch).
    # Registering the sibling at the same call means the new `watch_pr_checks`
    # body is runnable without a second hunk in that patch - and without this
    # module knowing anything about how the CI watcher works, because the whole
    # of it is that module's own `register_job()`. Off unless a job asks for it:
    # registering a body starts nothing.
    try:
        import jarvis_watch_ci
        jarvis_watch_ci.register_job()
    except Exception:
        pass
    # THE PER-REPOSITORY WATCHER'S BODY (2026-11-07). Same one startup call,
    # same convention: registered by name, and nothing polls until a job asks
    # for it. `github_read` is required per run (`ctx.require`), so a job
    # scheduled with `needs: []` parks in `waiting_approval` with ONE one-shot
    # grant - never a standing rule - exactly like `watch_github` above.
    def repo_handler(ctx, params):
        ctx.require("github_read")
        out = poll_repos()
        out["digest"] = deliver_digest()
        ctx.progress(f"checked {out['checked']} repository watch(es), "
                     f"{out['new']} new item(s)")
        return out

    try:
        jarvis_jobs.register("watch_repos", repo_handler)
    except Exception:
        pass
    # The repeating half: the scheduler's own kind for this watcher, so the
    # job that keeps checking is created by `add_repeat` - the same call the
    # older "tell me when" GitHub watch makes, with the same one card.
    _register_schedule_kind()
    return True


def status() -> dict:
    _init()
    with closing(_connect()) as c:
        pending = c.execute(
            "SELECT COUNT(*) n FROM findings WHERE reported IS NULL").fetchone()["n"]
        known = c.execute("SELECT COUNT(*) n FROM repos").fetchone()["n"]
    ts = topics()
    return {"available": True, "topics": len(ts), "tracking": known,
            "waiting_for_you": pending,
            "authenticated": bool(_token()),
            "rate_limit": ("30 searches/minute (token found)" if _token()
                           else "10 searches/minute (no token - set "
                                "JARVIS_GITHUB_TOKEN to raise it)"),
            "list": [{"name": t["name"], "query": t["query"],
                      "notify": bool(t["notify"]), "checked": t["checked"],
                      "error": t["error"]} for t in ts]}


# --------------------------------------------------------------------------
#   PER-REPOSITORY WATCHING (2026-11-07)
# --------------------------------------------------------------------------
# The owner: "i can tell jarvis what frequency of notifications or to stop or
# follow new or any combination of these things through jarvis live and chat".
#
# WHAT THIS IS. The topic watcher above is a PULL: it searches and waits to be
# asked. This is the other shape - one repository the owner NAMED, checked on
# its own, following any combination of releases, commits, issues, pull
# requests and CI, at a frequency the owner chose. It reuses the two decisions
# the CI watcher already made and the owner already accepted:
#
#   * A NEW RULE IS OBSERVE FIRST. Every watch starts in `observe`: it polls,
#     dedupes and writes what it WOULD say to the same `/api/watch/decisions`
#     ring buffer the CI watcher writes, and it says nothing. Chat and Live can
#     ask for a watch in one sentence, but the yes that lets it speak is the
#     owner's own card (`schedule_repeat`, raised by the quick path).
#   * EVERY POLL IS CONDITIONAL. GitHub answers `If-None-Match` with 304 Not
#     Modified, and a 304 does not count against the rate limit - so an
#     unchanged poll is free. Public repositories work with NO token at all;
#     `_token()` only adds `Authorization` when one is configured, and no code
#     here ever writes the token to a database, a decision row or an error.
#
# WHY THE ITEMS TABLE IS THE DEDUPE. A repository has no "last poll" cursor to
# trust: the same release is on page one forever. A row per item - release id,
# commit sha, issue number, pull number, (ci sha, state) - means the second
# poll of the same item inserts nothing and therefore cannot announce it twice.
#
# FIRST POLL IS A BASELINE. The first look at a repository finds its whole
# recent history; announcing that as "new" would be a wall of old news. The
# first successful poll records what exists and marks it already-seen; only
# what appears AFTER that is an item.
#
# ORDINARY NOTIFICATIONS NEVER RING. Every delivery below goes through
# `jarvis_arbiter` with `can_defer=True` and priority `low`, exactly like the
# topic digest: it can appear in the brief, and it can never take an
# interruption or ring a phone. "Instant" means handed over as it arrives, not
# urgent; nothing here may ever be `want=SHOUT`.

REPO_FREQUENCIES: tuple = ("instant", "daily", "weekly", "off")
REPO_FREQUENCY_WORDS: dict = {
    "instant": "as soon as it happens",
    "daily": "in the daily digest",
    "weekly": "in the weekly digest",
    "off": "only when you ask me",
}
REPO_EVENTS: tuple = ("releases", "commits", "issues", "prs", "ci")
REPO_EVENT_WORDS: dict = {
    "releases": "new releases",
    "commits": "new commits",
    "issues": "new issues",
    "prs": "new pull requests",
    "ci": "CI state changes",
}
#: The repository "watch your repo" means when no owner/name was said.
REPO_DEFAULT = "darknight11ish/Epic-Jarvis"
#: How often a watch may be polled at each frequency, in seconds. `off` never
#: polls on its own; the job is still free to re-read the local table.
REPO_POLL_SECONDS: dict = {"instant": 600.0, "daily": 6 * 3600.0,
                           "weekly": 6 * 3600.0, "off": 0.0}
REPO_MAX_WATCHES = 25
#: GitHub's own shape for an owner and a repository name, near enough.
_REPO_NAME_RX = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_-][A-Za-z0-9._-]{0,99}")


def _repo_name(value) -> str:
    """`owner/name` as GitHub spells it, or "" if it is not one."""
    m = _REPO_NAME_RX.fullmatch(str(value or "").strip())
    if not m:
        return ""
    owner, name = m.group(0).split("/", 1)
    return f"{owner}/{name}"


def _frequency(value) -> str:
    v = str(value or "").strip().lower()
    return v if v in REPO_FREQUENCIES else "daily"


def _events(value) -> list:
    """The parts to follow, as a sorted list. Empty/absent means all of them,
    because "watch my repo" without a list is the whole point."""
    if value is None:
        return list(REPO_EVENTS)
    if isinstance(value, str):
        value = [value]
    got = {str(v).strip().lower() for v in value if str(v).strip()}
    if not got:
        return list(REPO_EVENTS)
    return [e for e in REPO_EVENTS if e in got]


def watch_repo(full_name=None, *, frequency="daily", events=None,
               mode="observe", now=None) -> dict:
    """Start (or re-shape) watching one repository. Returns the watch.

    `mode="observe"` is the default on purpose: a watcher that has just been
    set up must not be able to speak before the owner's card says it may. The
    quick path raises that card and calls `set_repo_mode()` after a yes.
    """
    _init()
    name = _repo_name(full_name or REPO_DEFAULT)
    if not name:
        return {"ok": False, "reason": ("A repository is written owner/name, like "
                                        "darknight11ish/Epic-Jarvis.")}
    freq = _frequency(frequency)
    ev = _events(events)
    mode = "active" if str(mode).strip().lower() == "active" else "observe"
    now = time.time() if now is None else now
    with closing(_connect()) as c:
        old = c.execute("SELECT * FROM repo_watches WHERE full_name=?",
                        (name,)).fetchone()
        if old is None:
            n = c.execute("SELECT COUNT(*) n FROM repo_watches").fetchone()["n"]
            if n >= REPO_MAX_WATCHES:
                return {"ok": False,
                        "reason": (f"There are already {REPO_MAX_WATCHES} repositories "
                                   "watched - stop one first.")}
            c.execute("INSERT INTO repo_watches (full_name,frequency,prev_frequency,"
                      "events,mode,added) VALUES (?,?,?,?,?,?)",
                      (name, freq, freq if freq != "off" else "daily",
                       json.dumps(ev), mode, now))
        else:
            prev = old["frequency"]
            remember = (prev if prev != "off" else old["prev_frequency"] or "daily")
            c.execute("UPDATE repo_watches SET frequency=?, events=?,"
                      " prev_frequency=?, mode=? WHERE full_name=?",
                      (freq, json.dumps(ev), remember if freq != "off" else
                       old["prev_frequency"], mode, name))
    _audit("watch.repo_watch_set", {"repo": name, "frequency": freq,
                                    "events": ev, "mode": mode,
                                    "new": old is None})
    return {"ok": True, "repo": name, "frequency": freq, "events": ev,
            "mode": mode, "new": old is None}


def set_repo_mode(name: str, mode: str) -> dict:
    """`observe` or `active` - called ONLY after the owner's card, and by a
    stop (a stop is instant). Moving to `active` is the one change that lets
    this watch reach the owner, so it is the one change with a card."""
    _init()
    name = _repo_name(name)
    mode = "active" if str(mode).strip().lower() == "active" else "observe"
    with closing(_connect()) as c:
        n = c.execute("UPDATE repo_watches SET mode=? WHERE full_name=?",
                      (mode, name)).rowcount
    _audit("watch.repo_watch_mode", {"repo": name, "mode": mode})
    return {"ok": n > 0, "repo": name, "mode": mode}


def set_repo_frequency(name: str, frequency: str) -> dict:
    """Change the cadence. Instant: the watch already exists and was already
    allowed, so a cadence change is not a new permission."""
    _init()
    name = _repo_name(name)
    freq = _frequency(frequency)
    with closing(_connect()) as c:
        old = c.execute("SELECT frequency, prev_frequency FROM repo_watches"
                        " WHERE full_name=?", (name,)).fetchone()
        if old is None:
            return {"ok": False, "repo": name, "reason": "not watching it"}
        remember = (old["prev_frequency"] if freq == "off"
                    else (freq if freq != "off" else "daily"))
        if freq == "off":
            remember = old["frequency"] if old["frequency"] != "off" else \
                old["prev_frequency"]
        c.execute("UPDATE repo_watches SET frequency=?, prev_frequency=?"
                  " WHERE full_name=?", (freq, remember or "daily", name))
    _audit("watch.repo_watch_frequency", {"repo": name, "frequency": freq})
    return {"ok": True, "repo": name, "frequency": freq}


def resume_repo(name: str) -> dict:
    """Resume telling the owner after a stop: the frequency it had before."""
    _init()
    name = _repo_name(name)
    with closing(_connect()) as c:
        old = c.execute("SELECT frequency, prev_frequency FROM repo_watches"
                        " WHERE full_name=?", (name,)).fetchone()
        if old is None:
            return {"ok": False, "repo": name, "reason": "not watching it"}
        freq = old["prev_frequency"] or "daily"
        if old["frequency"] != "off":
            freq = old["frequency"]
        c.execute("UPDATE repo_watches SET frequency=?, prev_frequency=?"
                  " WHERE full_name=?", (freq, freq, name))
    _audit("watch.repo_watch_resume", {"repo": name, "frequency": freq})
    return {"ok": True, "repo": name, "frequency": freq}


def stop_repo(name: str) -> dict:
    """Stop watching, and forget everything remembered about it. Removing is
    instant and needs no card, like every other stop."""
    _init()
    name = _repo_name(name) or str(name or "").strip()[:140]
    with closing(_connect()) as c:
        n = c.execute("DELETE FROM repo_watches WHERE full_name=?",
                      (name,)).rowcount
        c.execute("DELETE FROM repo_items WHERE full_name=?", (name,))
    _audit("watch.repo_watch_stopped", {"repo": name, "existed": n > 0})
    return {"ok": n > 0, "repo": name}


def follow_new(topic: str, *, frequency="daily", mode="observe",
               now=None) -> dict:
    """Follow a topic's NEW repositories: "follow new repos for topic X".
    Same shape as a repository watch - observe first, a card before it speaks."""
    _init()
    topic = str(topic or "").strip()[:120]
    if not topic:
        return {"ok": False, "reason": "Say which topic, like \"follow new repos "
                                       "for topic mcp\"."}
    freq = _frequency(frequency)
    mode = "active" if str(mode).strip().lower() == "active" else "observe"
    now = time.time() if now is None else now
    with closing(_connect()) as c:
        old = c.execute("SELECT * FROM repo_follows WHERE topic=?",
                        (topic,)).fetchone()
        n = c.execute("SELECT COUNT(*) n FROM repo_follows").fetchone()["n"]
        if old is None and n >= REPO_MAX_WATCHES:
            return {"ok": False, "reason": (f"There are already {REPO_MAX_WATCHES} "
                                            "follows - stop one first.")}
        c.execute("INSERT INTO repo_follows (topic,frequency,mode,added)"
                  " VALUES (?,?,?,?) ON CONFLICT(topic) DO UPDATE SET"
                  " frequency=excluded.frequency",
                  (topic, freq, mode if old is None else old["mode"], now))
    _audit("watch.repo_follow_new", {"topic": topic, "frequency": freq,
                                     "new": old is None})
    return {"ok": True, "topic": topic, "frequency": freq,
            "mode": mode if old is None else old["mode"], "new": old is None}


def stop_follow(topic: str) -> dict:
    _init()
    topic = str(topic or "").strip()[:120]
    with closing(_connect()) as c:
        n = c.execute("DELETE FROM repo_follows WHERE topic=?", (topic,)).rowcount
        c.execute("DELETE FROM repo_topic_seen WHERE topic=?", (topic,))
    return {"ok": n > 0, "topic": topic}


def set_follow_mode(topic: str, mode: str) -> dict:
    """`observe` or `active` for a followed topic - the same one change the
    card gate makes, called only after the owner's yes."""
    _init()
    topic = str(topic or "").strip()[:120]
    mode = "active" if str(mode).strip().lower() == "active" else "observe"
    with closing(_connect()) as c:
        n = c.execute("UPDATE repo_follows SET mode=? WHERE topic=?",
                      (mode, topic)).rowcount
    _audit("watch.repo_follow_mode", {"topic": topic, "mode": mode})
    return {"ok": n > 0, "topic": topic, "mode": mode}


def repo_watches() -> list:
    _init()
    with closing(_connect()) as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM repo_watches ORDER BY full_name").fetchall()]
    for r in rows:
        try:
            r["events"] = _events(json.loads(r.get("events") or "[]"))
        except Exception:
            r["events"] = list(REPO_EVENTS)
        r["baselined"] = bool(r.get("baselined"))
    return rows


def follows() -> list:
    _init()
    with closing(_connect()) as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM repo_follows ORDER BY topic").fetchall()]


# --------------------------------------------------------------------------
#   Talking to GitHub - conditionally, and never with a token in the log
# --------------------------------------------------------------------------

def _default_gh(url: str, headers: dict) -> tuple:
    """(status, parsed body or None, ETag). A 304 is an answer, not an error:
    GitHub sent no body and charged no rate-limit point."""
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12.0) as r:
            raw = r.read().decode("utf-8", "replace")
            etag = str(r.headers.get("ETag") or "")
            try:
                body = json.loads(raw)
            except Exception:
                body = None
            return int(getattr(r, "status", 200) or 200), body, etag
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return 304, None, str(e.headers.get("ETag") or "")
        if e.code in (403, 429):
            raise RateLimited(f"github rate-limited ({e.code})") from e
        return int(e.code), None, ""
    except RateLimited:
        raise
    except Exception:
        return 0, None, ""


def _gh(url: str, *, etag: str = "", fetcher: Optional[Callable] = None) -> dict:
    """One conditional GET. `fetcher(url, headers)` replaces the network in
    the suites and nowhere else; it is resolved at CALL time for the same
    reason `check()` resolves its own."""
    h = {"User-Agent": UA, "Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    if etag:
        h["If-None-Match"] = str(etag)
    tok = _token()
    if tok:
        # The ONLY place the token is attached. It is never put on a row, in
        # an error, in a decision preview or in the audit line below.
        h["Authorization"] = f"Bearer {tok}"
    fetcher = fetcher or _default_gh
    try:
        status, body, new_etag = fetcher(url, h)
    except RateLimited:
        raise
    except Exception:
        return {"status": 0, "body": None, "etag": etag}
    return {"status": int(status or 0), "body": body,
            "etag": str(new_etag or etag)}


def _items_url(name: str, what: str, branch: str) -> str:
    if what == "releases":
        return f"{API}/repos/{name}/releases?per_page=10"
    if what == "commits":
        return f"{API}/repos/{name}/commits?per_page=10"
    if what == "issues":
        return f"{API}/repos/{name}/issues?state=open&sort=created&direction=desc&per_page=20"
    if what == "prs":
        return f"{API}/repos/{name}/pulls?state=all&sort=created&direction=desc&per_page=20"
    return f"{API}/repos/{name}/commits/{urllib.parse.quote(branch or 'HEAD')}/status"


def _read_items(what: str, body, now: float) -> list:
    """GitHub's answer -> `[(kind, item_id, title, url, at)]`. The shape is
    read here, once, so nothing later sees a stranger's raw JSON fields."""
    out = []
    if body is None:
        return out
    if what == "ci":
        sha = str((body or {}).get("sha") or "")
        state = str((body or {}).get("state") or "")
        if sha and state:
            out.append(("ci", sha, f"{state}", str((body or {}).get("target_url") or ""),
                        now - 1))
        return out
    rows = body if isinstance(body, list) else (body or {}).get("items") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if what == "releases":
            rid, title = row.get("id"), row.get("tag_name") or row.get("name")
            url = row.get("html_url") or ""
        elif what == "commits":
            rid = row.get("sha")
            commit = row.get("commit") or {}
            title = str((commit.get("message") or "").splitlines()[0] if
                        commit.get("message") else "")[:120]
            url = row.get("html_url") or ""
        elif what == "issues":
            if row.get("pull_request") is not None:
                continue           # a pull request is not an issue here
            rid, title = row.get("id"), row.get("title")
            url = row.get("html_url") or ""
        else:                      # prs
            rid, title = row.get("id"), row.get("title")
            url = row.get("html_url") or ""
        if rid is None:
            continue
        when = str(row.get("created_at") or row.get("published_at") or "")
        out.append((what, str(rid), str(title or "")[:160], str(url)[:300], now))
    return out


def _record_item(c, name: str, kind: str, item_id: str, title: str, url: str,
                 now: float, *, baseline: bool) -> str:
    """The item's key when it had never been seen, "" otherwise. The INSERT OR
    IGNORE is the whole dedupe: the same release id on a later poll changes no
    row, so a second poll of the same item cannot announce it twice."""
    key = f"{name}:{kind}:{item_id}"
    said = now if baseline else None
    cur = c.execute("INSERT OR IGNORE INTO repo_items (key,full_name,kind,title,url,"
                    "at,seen,said) VALUES (?,?,?,?,?,?,?,?)",
                    (key, name, kind, title, url, now, now, said))
    return "" if baseline else (key if cur.rowcount > 0 else "")


def _due(watch: dict, now: float) -> bool:
    freq = _frequency(watch.get("frequency"))
    if freq == "off":
        return False
    last = float(watch.get("last_polled") or 0)
    return (now - last) >= REPO_POLL_SECONDS.get(freq, 6 * 3600.0)


def _new_row(name: str, watch: dict, kind: str, title: str, url: str,
             now: float, *, delivered: bool, reason: str) -> dict:
    """One decision row, in exactly the shape the CI watcher's rows carry, so
    `/api/watch/decisions` reads the same for both watchers."""
    freq = _frequency(watch.get("frequency"))
    mode = "observe" if str(watch.get("mode") or "observe") != "active" else freq
    return {
        "at": now,
        "source": "github-watch-repos",
        "thread_key": f"repo:{name}",
        "outcome": "would_notify" if mode == "observe" else (
            "delivered" if delivered else "recorded"),
        "reason_code": reason,
        "preview_text": f"{name}: {REPO_EVENT_WORDS.get(kind, kind)} - {title}"[:240],
        "mode": mode,
        "verdict": f"repo_{kind}",
        "delivery": ("none" if mode == "observe" else
                     ("instant" if freq == "instant" else freq)),
        "repo": name,
        "freq": freq,
        "url": url,
    }


def _record_row(row: dict, now: float) -> bool:
    """Write the row into the ONE decisions ring buffer. A backend without the
    CI watcher keeps going - the log is the only thing lost, never an item."""
    try:
        import jarvis_watch_ci as WC
        WC.default_store().record(row, now=now)
        return True
    except Exception:
        return False


def _deliver(name: str, kind: str, title: str, url: str, now: float) -> bool:
    """Hand one item to the arbiter. `can_defer=True` and `low` priority are
    what make "never rings, never interrupts" true by construction - this
    function has no way to ask for anything louder."""
    try:
        import jarvis_arbiter
    except Exception:
        return False
    try:
        jarvis_arbiter.deliver(
            source="github-watch-repos",
            title=f"{name}: {REPO_EVENT_WORDS.get(kind, kind)}",
            body=title, kind="finding", priority="low", can_defer=True,
            ref=url, want=jarvis_arbiter.NOTIFY, now=now)
        return True
    except Exception:
        return False


def _poll_one(watch: dict, fetcher: Optional[Callable], now: float, out: dict) -> None:
    name = watch["full_name"]
    events = watch["events"]
    baseline = not bool(watch.get("baselined"))
    try:
        # The repository's own record first: the default branch is needed for
        # the CI endpoint, and the ETag proves the repository itself is
        # unchanged on an otherwise empty poll.
        meta = _gh(f"{API}/repos/{name}", etag=watch.get("etag_repo") or "",
                   fetcher=fetcher)
        if meta["status"] == 403 or meta["status"] == 429:
            raise RateLimited("github rate-limited")
        branch = "HEAD"
        if meta["status"] == 200 and isinstance(meta["body"], dict):
            branch = str(meta["body"].get("default_branch") or "HEAD")
        updates = {}
        fresh = []
        for what in events:
            etag = watch.get(f"etag_{what}") or ""
            got = _gh(_items_url(name, what, branch), etag=etag, fetcher=fetcher)
            if got["status"] == 304:
                continue           # unchanged: no body, no rate-limit cost
            if got["status"] in (403, 429):
                raise RateLimited("github rate-limited")
            if got["status"] != 200:
                continue
            updates[f"etag_{what}"] = got["etag"]
            fresh.extend(_read_items(what, got["body"], now))
        with closing(_connect()) as c:
            for kind, item_id, title, url, at in fresh:
                key = _record_item(c, name, kind, item_id, title, url, at,
                                   baseline=baseline)
                if key:
                    out["new"] += 1
                    _decide(c, watch, key, kind, title, url, now, out)
            if meta["status"] == 200:
                updates["etag_repo"] = meta["etag"]
            if updates:
                sets = ",".join(f"{k}=?" for k in updates)
                c.execute(f"UPDATE repo_watches SET {sets}, last_polled=?,"
                          " baselined=1, error=NULL WHERE full_name=?",
                          (*updates.values(), now, name))
            else:
                c.execute("UPDATE repo_watches SET last_polled=? WHERE full_name=?",
                          (now, name))
        out["checked"] += 1
    except RateLimited as exc:
        out["errors"][name] = str(exc)
        _note_repo_error(name, str(exc))


def _decide(c, watch: dict, key: str, kind: str, title: str, url: str,
            now: float, out: dict) -> None:
    """What a genuinely new item does, which is entirely the mode and the
    frequency the owner chose. `off` and `observe` both record and stay quiet."""
    name = watch["full_name"]
    freq = _frequency(watch.get("frequency"))
    active = str(watch.get("mode") or "observe") == "active"
    delivered = False
    if not active:
        reason = "repo_observe_shadow"
    elif freq == "off":
        reason = "repo_frequency_off"
    elif freq == "instant":
        delivered = _deliver(name, kind, title, url, now)
        reason = "repo_instant_due"
        if delivered:
            c.execute("UPDATE repo_items SET said=? WHERE key=?", (now, key))
            out["said"] += 1
    else:
        # Kept for the digest; `deliver_digest()` carries it and marks it.
        reason = "repo_digest_due"
    row = _new_row(name, watch, kind, title, url, now, delivered=delivered,
                   reason=reason)
    if _record_row(row, now):
        out["recorded"] += 1


def _note_repo_error(name: str, err: str) -> None:
    with closing(_connect()) as c:
        c.execute("UPDATE repo_watches SET error=? WHERE full_name=?",
                  (str(err)[:200], name))


def _follow_row(topic: str, full: dict, watch: dict, now: float,
                out: dict) -> None:
    row = _new_row(topic, watch, "new_repo", str(full.get("full_name") or ""),
                   f"https://github.com/{full.get('full_name') or ''}", now,
                   delivered=False,
                   reason=("repo_observe_shadow" if str(watch.get("mode")) != "active"
                           else "repo_new_repo"))
    row["thread_key"] = f"follow:{topic}"
    row["repo"] = str(full.get("full_name") or "")
    _record_row(row, now)
    out["new"] += 1


def _poll_follow(f: dict, fetcher: Optional[Callable], now: float,
                 out: dict) -> None:
    topic = f["topic"]
    try:
        got = _gh(search_url(topic, per_page=30), fetcher=fetcher)
        if got["status"] in (403, 429):
            raise RateLimited("github rate-limited")
        if got["status"] != 200 or not isinstance(got["body"], dict):
            return
        items = got["body"].get("items") or []
        baseline = not bool(f.get("last_polled"))
        with closing(_connect()) as c:
            for item in items:
                if not isinstance(item, dict):
                    continue
                try:
                    rid = int(item.get("id"))
                except (TypeError, ValueError):
                    continue
                cur = c.execute("INSERT OR IGNORE INTO repo_topic_seen"
                                " (topic,repo_id,full_name,first_seen)"
                                " VALUES (?,?,?,?)",
                                (topic, rid, str(item.get("full_name") or "")[:140],
                                 now))
                if cur.rowcount > 0 and not baseline:
                    _follow_row(topic, item, f, now, out)
            c.execute("UPDATE repo_follows SET last_polled=? WHERE topic=?",
                      (now, topic))
    except RateLimited as exc:
        out["errors"][topic] = str(exc)


def poll_repos(now: Optional[float] = None,
               fetcher: Optional[Callable] = None) -> dict:
    """One pass over every repository watch and followed topic whose own
    frequency says it is due. Records items and decisions; returns what it
    did. Nothing here ever speaks directly: delivery is `deliver_digest()`'s
    job (daily/weekly) or the instant hand-off inside `_decide`."""
    _init()
    now = time.time() if now is None else now
    out = {"checked": 0, "new": 0, "said": 0, "recorded": 0,
           "skipped": 0, "errors": {}}
    for w in repo_watches():
        if not _due(w, now):
            out["skipped"] += 1
            continue
        _poll_one(w, fetcher, now, out)
    for f in follows():
        last = float(f.get("last_polled") or 0)
        if _frequency(f.get("frequency")) == "off":
            out["skipped"] += 1
            continue
        if (now - last) < REPO_POLL_SECONDS.get(_frequency(f.get("frequency")),
                                               6 * 3600.0):
            out["skipped"] += 1
            continue
        _poll_follow(f, fetcher, now, out)
    _audit("watch.repo_polled", {"checked": out["checked"], "new": out["new"],
                                 "recorded": out["recorded"]})
    return out


def deliver_digest(now: Optional[float] = None) -> int:
    """The daily/weekly half: one message per repository, through the arbiter
    with can_defer=True, then the items are marked said so they never repeat.
    Returns how many items were carried."""
    _init()
    now = time.time() if now is None else now
    carried = 0
    for w in repo_watches():
        freq = _frequency(w.get("frequency"))
        if str(w.get("mode") or "observe") != "active" or freq not in ("daily", "weekly"):
            continue
        last = float(w.get("last_said") or 0)
        wait = 86400.0 if freq == "daily" else 7 * 86400.0
        if (now - last) < wait:
            continue
        with closing(_connect()) as c:
            rows = c.execute(
                "SELECT * FROM repo_items WHERE full_name=? AND said IS NULL"
                " ORDER BY at", (w["full_name"],)).fetchall()
            if not rows:
                continue
            names = [f"{REPO_EVENT_WORDS.get(r['kind'], r['kind'])}: {r['title']}"
                     for r in rows[:12]]
            body = "; ".join(names)
            title = f"{len(rows)} new item(s) in {w['full_name']}"
            ok = _deliver(w["full_name"], "releases", body, "", now)
            _record_row(_new_row(w["full_name"], w, "releases", title, "", now,
                                 delivered=ok, reason="repo_digest_due"), now)
            if ok:
                marks = [r["key"] for r in rows]
                c.execute("UPDATE repo_items SET said=? WHERE key IN ({})".format(
                    ",".join("?" * len(marks))), [now, *marks])
                c.execute("UPDATE repo_watches SET last_said=? WHERE full_name=?",
                          (now, w["full_name"]))
                carried += len(marks)
    return carried


def repo_status() -> dict:
    """What the owner is watching, in plain words, with the cadence and the
    parts of each repository. Reads only."""
    _init()
    watches = repo_watches()
    followed = follows()
    with closing(_connect()) as c:
        waiting = c.execute("SELECT COUNT(*) n FROM repo_items WHERE said IS NULL"
                            ).fetchone()["n"]
    return {
        "available": True,
        "authenticated": bool(_token()),
        "watched": [{"repo": w["full_name"], "frequency": w["frequency"],
                     "frequency_words": REPO_FREQUENCY_WORDS.get(
                         _frequency(w["frequency"]), w["frequency"]),
                     "events": [REPO_EVENT_WORDS.get(e, e) for e in w["events"]],
                     "mode": w["mode"], "last_polled": w["last_polled"],
                     "error": w["error"]} for w in watches],
        "followed": [{"topic": f["topic"], "frequency": f["frequency"],
                      "mode": f["mode"]} for f in followed],
        "waiting_for_you": waiting,
        "default": REPO_DEFAULT,
        "frequencies": list(REPO_FREQUENCIES),
        "event_kinds": list(REPO_EVENTS),
    }



# --------------------------------------------------------------------------
#   HOW A WATCH ACTUALLY POLLS: the scheduler kind (2026-11-07)
# --------------------------------------------------------------------------
# A Long Fuse job (`register_job` below) is ONE run. The thing that REPEATS on
# this PC is the scheduler (`jarvis_schedule.py`), and that is exactly how the
# older "tell me when CI fails on ..." GitHub watch stays alive: a kind added
# with `jarvis_schedule.register_kind`, a job row created by `add_repeat` only
# after ONE `schedule_repeat` approval card, and an `on_fire(job_id)` callback
# that runs every N minutes. The per-repository watcher uses that SAME path -
# its own kind name and payload, the same card, the same approval queue, the
# same "deleting it is immediate" - so "watch X daily" really polls, with no
# new permission model and no second approval door.
#
# WHY `silent=True`: this kind's own on_fire does the telling (through
# `jarvis_arbiter`, low priority, can_defer), so the scheduler must NOT also
# announce that the watch "went off". WHY `leaves=True`: a look leaves this PC
# for api.github.com, and the card says so. WHY `first_now=True`: the first
# look is due the moment the card is approved, so the baseline is taken then.
KIND = "repo_watch"
NOUN = "repository watch"
LOCK_SCREEN = "Jarvis: a GitHub repository watch cannot look right now."
#: How often a watch may look, in minutes. Ten is the same floor the older
#: GitHub "tell me when" watch uses; each look is conditional, so an unchanged
#: repository costs no rate-limit point.
POLL_MINUTES = 10
POLL_MAX_MINUTES = 24 * 60
POLL_DEFAULT_MINUTES = POLL_MINUTES


def repo_rule(rule, now: float) -> dict:
    """This kind's own rule check (register_kind(check=...)): every N minutes,
    from a start, with the repository and what to follow. The generic rule
    check refuses minutes outright, so no other kind can look this often."""
    if not isinstance(rule, dict):
        raise ValueError("a repository watch needs what to watch")
    watch = rule.get("watch")
    if not isinstance(watch, dict):
        raise ValueError("a repository watch needs the repository")
    follow = str(watch.get("follow") or "").strip()[:120]
    if not follow and not watch.get("repo"):
        raise ValueError("a repository watch needs the repository")
    n = rule.get("minutes", POLL_DEFAULT_MINUTES)
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError("how often is a whole number of minutes")
    if n < POLL_MINUTES:
        raise ValueError("the most often it can look is every "
                         f"{POLL_MINUTES} minutes")
    if n > POLL_MAX_MINUTES:
        raise ValueError("the least often it can look is every day")
    start = rule.get("start")
    if not isinstance(start, (int, float)) or isinstance(start, bool):
        start = now
    if follow:
        return {"every": "minutes", "minutes": int(n), "start": float(start),
                "watch": {"follow": follow,
                          "frequency": _frequency(watch.get("frequency")),
                          "events": []}}
    name = _repo_name(watch.get("repo") or REPO_DEFAULT)
    if not name:
        raise ValueError("a repository is written owner/name, like "
                         f"{REPO_DEFAULT}")
    return {"every": "minutes", "minutes": int(n), "start": float(start),
            "watch": {"repo": name, "frequency": _frequency(watch.get("frequency")),
                      "events": _events(watch.get("events"))}}


def repo_words(name: str, events=None, *, follow: bool = False) -> str:
    """The row's words in Coming up: the owner's own subject, never a token."""
    if follow:
        return f"new repositories for topic {name}"
    evs = _events(events)
    parts = ", ".join(REPO_EVENT_WORDS.get(e, e) for e in evs)
    return f"{name} on GitHub ({parts})"


def repo_card(rule, text: str, now: float) -> str:
    """The ONE approval card's words. It says exactly what is looked at, how
    often, where each look goes and what is kept - the same shape the older
    GitHub "tell me when" card uses."""
    w = rule.get("watch") or {}
    follow = str(w.get("follow") or "")
    name = w.get("repo") or REPO_DEFAULT
    freq = _frequency(w.get("frequency"))
    evs = _events(w.get("events"))
    parts = ", ".join(REPO_EVENT_WORDS.get(e, e) for e in evs)
    subject = (f"Topic: {follow} (each repository that appears in it for the "
               "first time is reported once)" if follow else f"Repository: {name}")
    lines = [
        ("Follow a GitHub topic's new repositories." if follow
         else "Watch a GitHub repository."),
        "",
        subject,
        f"What is followed: {parts}",
        f"How often it looks: every {rule.get('minutes', POLL_MINUTES)} minutes",
        f"When it tells you: {REPO_FREQUENCY_WORDS.get(freq, freq)}",
        "",
        "Each look is ONE conditional read of api.github.com. A repository that "
        "has not changed answers \"not modified\", which costs no GitHub "
        "rate-limit points. Public repositories need no token; if you connected "
        "one it is used for higher limits and private repositories, and it is "
        "never shown, written down or logged.",
        "",
        "Nothing on GitHub is changed, and no personal data is sent. Ordinary "
        "notifications cannot ring or interrupt you. What it would tell you is "
        "always readable at GET /api/watch/decisions, and stopping, pausing or "
        "deleting it is immediate from either app.",
        "",
        "If you say no: nothing is set up.",
    ]
    return "\n".join(lines)


def repo_on_fire(job_id: str) -> dict:
    """One look, on the scheduler's own thread, after the owner approved the
    repeating job. The approved job IS the yes, so the first fire makes the
    watch active; nothing here raises into the scheduler loop."""
    out = {"ok": False}
    try:
        import jarvis_schedule as S
        sched = S.get()
        job = sched.job(job_id)
    except Exception:
        return out
    if not job:
        return out            # deleted while it fired: nothing to do
    w = {}
    try:
        extra = sched.extra(job_id)
        w = extra.get("watch") if isinstance(extra.get("watch"), dict) else {}
    except Exception:
        w = {}
    follow = str(w.get("follow") or "").strip()
    freq = _frequency(w.get("frequency"))
    evs = _events(w.get("events"))
    try:
        if follow:
            follow_new(follow, frequency=freq, mode="active")
            set_follow_mode(follow, "active")
        else:
            name = _repo_name(w.get("repo") or "") or REPO_DEFAULT
            watch_repo(name, frequency=freq, events=evs, mode="active")
        # The scheduler's OWN clock: a job that fired on the fake clock in a
        # test must look on that clock too, not on wall time.
        fired_at = sched.now()
        out = poll_repos(now=fired_at)
        out["digest"] = deliver_digest(now=fired_at)
        out["ok"] = True
    except Exception as exc:                            # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def repo_jobs(sched=None) -> list:
    """The scheduler's own rows for this kind, with the payload read back from
    the kind's OWN `extra` state. Read only; the scheduler remains the owner
    of the row, and its public view withholds `rule["watch"]` on purpose (a
    "tell me when" watch can carry someone's name there)."""
    try:
        import jarvis_schedule as S
        sched = sched or S.get()
        rows = [j for j in sched.listed() if j.get("kind") == KIND]
    except Exception:
        return []
    out = []
    for job in rows:
        try:
            extra = sched.extra(job.get("id"))
        except Exception:
            extra = {}
        payload = extra.get("watch") if isinstance(extra.get("watch"), dict) else {}
        out.append({"id": job.get("id"), "state": job.get("state"),
                    "repo": _repo_name(payload.get("repo") or ""),
                    "follow": str(payload.get("follow") or "").strip(),
                    "frequency": _frequency(payload.get("frequency")),
                    "events": _events(payload.get("events")),
                    "minutes": extra.get("minutes") or POLL_MINUTES,
                    "payload": payload})
    return out


def ensure_repo_watch_job(repo, frequency="daily", events=None, *, sched=None,
                          follow=False) -> dict:
    """Create the repeating job that makes a watch poll - ONCE per repository.

    This is the same call the older GitHub "tell me when" watch makes
    (`Scheduler.add_repeat`): it creates the row in `waiting`, raises the ONE
    `schedule_repeat` card itself, and the row starts firing only after the
    owner's yes. Nothing here raises a second card or approves anything.
    """
    _init()
    if follow:
        name = str(repo or "").strip()[:120]
        if not name:
            return {"ok": False, "reason": "Say which topic to follow."}
    else:
        name = _repo_name(repo or REPO_DEFAULT)
        if not name:
            return {"ok": False, "reason": ("A repository is written owner/name, like "
                                            f"{REPO_DEFAULT}.")}
    for job in repo_jobs(sched):
        if (job["follow"] == name) if follow else (job["repo"] == name):
            return {"ok": True, "repo": name, "job": job["id"],
                    "state": job["state"], "existing": True}
    freq = _frequency(frequency)
    evs = [] if follow else _events(events)
    try:
        import jarvis_schedule as S
        sched = sched or S.get()
    except Exception:
        return {"ok": False, "reason": ("Your PC's Jarvis cannot repeat a check yet - "
                                        "run apply-patches.ps1 on the PC.")}
    payload = ({"follow": name, "frequency": freq, "events": []} if follow else
               {"repo": name, "frequency": freq, "events": evs})
    try:
        view = sched.add_repeat(
            KIND,
            {"every": "minutes", "minutes": POLL_MINUTES, "watch": payload},
            text=repo_words(name, evs, follow=follow), source="quick")
        # The kind's own small state, through the scheduler's documented
        # door for exactly this: what to look at, read back on every fire.
        jid = (view or {}).get("id")
        if jid:
            try:
                sched.set_extra(jid, {"watch": payload, "minutes": POLL_MINUTES})
            except Exception:
                pass
    except (ValueError, OverflowError) as exc:
        return {"ok": False, "reason": str(exc).rstrip(".") + "."}
    except Exception as exc:                            # noqa: BLE001
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "repo": name, "job": view.get("id"),
            "state": view.get("state"), "existing": False}


def stop_repo_watch_jobs(repo, *, sched=None, follow=False) -> int:
    """Delete the scheduler's rows for one repository (or one followed topic).
    Removing is instant and needs no card, exactly like deleting any other
    repeating job."""
    name = str(repo or "").strip()[:120] if follow else _repo_name(repo or "")
    n = 0
    try:
        import jarvis_schedule as S
        sched = sched or S.get()
    except Exception:
        return 0
    for job in repo_jobs(sched):
        if name and ((job["follow"] == name) if follow else (job["repo"] == name)):
            try:
                sched.delete(job["id"])
                n += 1
            except Exception:
                pass
    return n


def _sentence(text: str) -> str:
    text = str(text or "").strip()
    return text[:1].upper() + text[1:] if text else text


def _register_schedule_kind() -> bool:
    """Register the kind with the ONE scheduler, from import and again from
    `register_job()`. Idempotent: register_kind overwrites its own name.

    It has to happen at IMPORT time for a job that already exists: the
    scheduler imports the modules named in `KIND_MODULES` before its loop
    first runs, so `jarvis_watch` is in that tuple and a watch set up before
    the PC restarted still finds its on_fire. The `register_job()` call is the
    second, harmless door for every path that imports the module later.
    """
    try:
        import jarvis_schedule as S
        S.register_kind(
            KIND, NOUN, LOCK_SCREEN, has_text=True, owner_listed=True,
            repeatable=True, silent=True, first_now=True, leaves=True,
            what=("check a GitHub repository for new releases, commits, issues, "
                  "pull requests and CI changes, and tell the owner at the "
                  "cadence they chose"),
            check=repo_rule, card=repo_card, on_fire=repo_on_fire,
            about=("Checks api.github.com for one repository the owner named. "
                   "Reads only; nothing on GitHub changes. Every look is "
                   "conditional, so an unchanged repository costs no rate-limit "
                   "point, and the log is GET /api/watch/decisions."),
        )
        return True
    except Exception:
        return False


_register_schedule_kind()


if __name__ == "__main__":                                # pragma: no cover
    import pprint, sys
    if len(sys.argv) > 2 and sys.argv[1] == "add":
        pprint.pprint(add(sys.argv[2], " ".join(sys.argv[3:])))
    elif len(sys.argv) > 1 and sys.argv[1] == "check":
        pprint.pprint(check())
    elif len(sys.argv) > 1 and sys.argv[1] == "report":
        pprint.pprint(report())
    else:
        pprint.pprint(status())
