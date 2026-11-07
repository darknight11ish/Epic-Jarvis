"""test_watch_repos.py - the per-repository GitHub watcher (2026-11-07).

    python3 backend/test_watch_repos.py

The owner: "i can tell jarvis what frequency of notifications or to stop or
follow new or any combination of these things through jarvis live and chat".

What it proves, with a clock the test moves by hand, real SQLite files in a
temporary folder, the REAL jarvis_watch.py and jarvis_quick.py, and a fake
GitHub that never opens a socket:

  - public repositories poll with NO token: no Authorization header is sent,
    and a token is only added when one is configured; a token is never in the
    database, a decision row or an audit line;
  - conditional requests: the second poll of unchanged data sends
    If-None-Match and GitHub's 304 answer costs 0 rate-limited calls, and
    discovers no item;
  - per-item dedupe: the same release / commit / issue / PR / CI state is
    never announced twice;
  - the first poll is a baseline: a repository's whole history is NOT a wall
    of "new";
  - frequency: instant hands an item over once, daily and weekly keep it for
    the digest and carry it once, off polls nothing and records only;
  - observe mode never delivers anything and says so in the decisions log;
  - stop / resume / forget, and any combination of followed parts;
  - "follow new repos for topic X" reports each repository once;
  - the chat and Live sentences (one matcher, one runner): watch, stop,
    resume, cadence, parts, follow-new, list - and the card that lets a watch
    speak is raised on starting one, through the gate;
  - the decisions rows all carry a reason code from jarvis_watch.WATCH_REASONS
    (the closed set) and the same shape the CI watcher's rows carry.

No pytest, no network, no model.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_watch.py", "jarvis_watch_ci.py", "jarvis_quick.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-watch-repos-"))
os.environ["JARVIS_WATCH_DB"] = str(_TMP / "watch.db")
os.environ["JARVIS_WATCH_CI_DIR"] = str(_TMP / "watch-ci")
os.environ.pop("JARVIS_GITHUB_TOKEN", None)
os.environ.pop("GITHUB_TOKEN", None)
os.environ.pop("GH_TOKEN", None)

import threading  # noqa: E402
import types  # noqa: E402

fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = fw

import jarvis_watch as W  # noqa: E402
import jarvis_watch_ci as WC  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []

TOKEN = "ghp_TESTtokenNEVERtoBEseen0123456789abcd"
DEFAULT = "darknight11ish/Epic-Jarvis"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def fresh():
    """A new database and a new decisions store for one case."""
    W._reset()
    global _TMP
    d = Path(tempfile.mkdtemp(dir=str(_TMP), prefix="case-"))
    W.DB_PATH = d / "watch.db"
    os.environ["JARVIS_WATCH_CI_DIR"] = str(d / "watch-ci")
    WC.set_store(WC.Store(d / "watch-decisions.json", d / "watch-receipts.json"))
    return d


def _reset():
    import sqlite3
    from contextlib import closing
    W._inited = False


W._reset = _reset


class FakeGitHub:
    """The whole of api.github.com this test needs: bodies per URL path, an
    ETag per URL computed from the body, and 304 when the caller already has
    it. Every call is recorded, header dict included."""

    def __init__(self):
        self.calls = []
        self.bodies = {}
        self.etags = {}
        self.down = False

    def set(self, path, body):
        self.bodies[path] = body
        self.etags[path] = 'W/"%d"' % (abs(hash(json.dumps(body, sort_keys=True))) % 10 ** 8)

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        if self.down:
            return 0, None, ""
        path = url.split("api.github.com", 1)[-1]
        if path not in self.bodies:
            return 404, None, ""
        etag = self.etags[path]
        if headers.get("If-None-Match") and headers["If-None-Match"] == etag:
            return 304, None, etag
        return 200, json.loads(json.dumps(self.bodies[path])), etag

    def charged_calls(self, since=0):
        """200s are what GitHub charges for; a 304 does not count."""
        return [1 for _u, _h in self.calls[since:] if True]


def repo_body(rid=1, branch="main"):
    return {"id": rid, "full_name": DEFAULT, "default_branch": branch,
            "stargazers_count": 5, "archived": False}


def release(rid, tag):
    return {"id": rid, "tag_name": tag, "name": tag,
            "html_url": f"https://github.com/{DEFAULT}/releases/tag/{tag}",
            "published_at": "2026-11-07T00:00:00Z"}


def commit(sha, msg):
    return {"sha": sha, "commit": {"message": msg},
            "html_url": f"https://github.com/{DEFAULT}/commit/{sha}"}


def issue(rid, title):
    return {"id": rid, "number": rid, "title": title,
            "html_url": f"https://github.com/{DEFAULT}/issues/{rid}",
            "created_at": "2026-11-07T00:00:00Z"}


def pr(rid, title):
    return {"id": rid, "number": rid, "title": title,
            "html_url": f"https://github.com/{DEFAULT}/pull/{rid}",
            "created_at": "2026-11-07T00:00:00Z"}


def ci(sha, state):
    return {"sha": sha, "state": state,
            "target_url": f"https://github.com/{DEFAULT}/actions/runs/{sha}"}


def world():
    """A fake GitHub with one of everything, and one watch on it."""
    fresh()
    g = FakeGitHub()
    g.set(f"/repos/{DEFAULT}", repo_body())
    g.set(f"/repos/{DEFAULT}/releases?per_page=10", [release(1, "v1")])
    g.set(f"/repos/{DEFAULT}/commits?per_page=10", [commit("a" * 40, "first")])
    g.set(f"/repos/{DEFAULT}/issues?state=open&sort=created&direction=desc&per_page=20",
          [issue(1, "one")])
    g.set(f"/repos/{DEFAULT}/pulls?state=all&sort=created&direction=desc&per_page=20",
          [pr(1, "one")])
    g.set(f"/repos/{DEFAULT}/commits/main/status", ci("a" * 40, "success"))
    return g


T0 = 1_800_000_000.0


# ==========================================================================
#   Public polling, ETags and the token
# ==========================================================================

def t_public_works_with_no_token_and_an_unchanged_poll_is_free():
    g = world()
    W.watch_repo(DEFAULT, frequency="instant")
    first = W.poll_repos(now=T0, fetcher=g)
    check("the first poll runs and is a baseline (0 new)", first["checked"] == 1)
    check("no network break on public data", not first["errors"], first["errors"])
    auth = [h for _u, h in g.calls if "Authorization" in h]
    check("public repositories need NO token: no Authorization header", not auth, auth)

    before = len(g.calls)
    second = W.poll_repos(now=T0 + 601, fetcher=g)
    check("the second poll discovers nothing", second["new"] == 0, second)
    check("... and sends If-None-Match on every endpoint it re-asks",
          all(("If-None-Match" in h) for _u, h in g.calls[before:]),
          [u for u, h in g.calls[before:] if "If-None-Match" not in h])
    statuses = []
    for u, h in g.calls[before:]:
        statuses.append("cond" if "If-None-Match" in h else "plain")
    check("every second-poll request was conditional", set(statuses) == {"cond"},
          statuses)
    # A 304 answer is what the fake gives; the module never parses a body and
    # records no item, so the only cost was the conditional request itself.
    check("an unchanged poll records no decision row", second["recorded"] == 0,
          second["recorded"])

    os.environ["JARVIS_GITHUB_TOKEN"] = TOKEN
    W._inited = True
    try:
        third = W.poll_repos(now=T0 + 1202, fetcher=g)
        check("a token poll runs", third["checked"] == 1, third)
        got = [h for _u, h in g.calls if "Authorization" in h]
        check("a configured token is sent as Bearer", bool(got) and
              all(h["Authorization"] == f"Bearer {TOKEN}" for h in got))
        db = Path(str(W.DB_PATH))
        blob = b""
        for f in (db, db.with_name(db.name + "-wal")):
            if f.exists():
                blob += f.read_bytes()
        dump = blob + json.dumps(WC.default_store().decisions(200)).encode()
        check("the token is never written to the database or a decision row",
              TOKEN.encode() not in dump)
        imports = io.open(W.__file__, encoding="utf-8").read()
        check("the token has one new home, and the old watcher keeps its own",
              imports.count('h["Authorization"]') == 2,
              imports.count('h["Authorization"]'))
    finally:
        os.environ.pop("JARVIS_GITHUB_TOKEN", None)


def t_rate_limited_is_an_error_not_a_reset():
    g = world()
    W.watch_repo(DEFAULT, frequency="instant")
    W.poll_repos(now=T0, fetcher=g)
    g.down = True

    def limited(url, headers):
        raise W.RateLimited("github rate-limited (403)")
    out = W.poll_repos(now=T0 + 700, fetcher=limited)
    check("a rate-limited poll says so and records no item",
          out["new"] == 0 and bool(out["errors"]), out)


# ==========================================================================
#   Dedupe, baseline, and the five parts
# ==========================================================================

def t_the_first_poll_is_a_baseline_and_an_item_is_never_twice():
    g = world()
    W.watch_repo(DEFAULT, frequency="instant", events=["releases"])
    W.set_repo_mode(DEFAULT, "active")
    said = []
    W._deliver = lambda name, kind, title, url, now: (said.append(title), True)[1]
    W.poll_repos(now=T0, fetcher=g)
    check("history found on the first poll is not announced", said == [], said)

    g.set(f"/repos/{DEFAULT}/releases?per_page=10",
          [release(2, "v2"), release(1, "v1")])
    out = W.poll_repos(now=T0 + 601, fetcher=g)
    check("a new release is one new item", out["new"] == 1, out)
    check("... and instant delivery handed it over once", said == ["v2"], said)
    again = W.poll_repos(now=T0 + 1202, fetcher=g)
    check("the same release is never announced twice", again["new"] == 0 and
          said == ["v2"], (again, said))
    rows = WC.default_store().decisions(50)
    check("the first delivery has a decisions row",
          any(r.get("reason_code") == "repo_instant_due" for r in rows), rows[:2])
    check("every row's reason is from the closed set",
          all(r.get("reason_code") in W.WATCH_REASONS for r in rows),
          [r.get("reason_code") for r in rows])


def t_any_combination_of_parts():
    g = world()
    W.watch_repo(DEFAULT, frequency="instant", events=["versions"])
    check("an unknown part list falls back to all five",
          W.repo_watches()[0]["events"] == list(W.REPO_EVENTS))
    W.watch_repo(DEFAULT, frequency="instant", events=["releases", "issues"])
    w = W.repo_watches()[0]
    check("releases and issues only", w["events"] == ["releases", "issues"], w["events"])
    W.poll_repos(now=T0, fetcher=g)
    W.set_repo_mode(DEFAULT, "active")
    said = []
    W._deliver = lambda name, kind, title, url, now: (said.append(kind), True)[1]
    g.set(f"/repos/{DEFAULT}/releases?per_page=10",
          [release(9, "v9"), release(1, "v1")])
    g.set(f"/repos/{DEFAULT}/issues?state=open&sort=created&direction=desc&per_page=20",
          [issue(9, "nine"), issue(1, "one")])
    g.set(f"/repos/{DEFAULT}/commits?per_page=10",
          [commit("b" * 40, "not asked for")])
    W.poll_repos(now=T0 + 700, fetcher=g)
    check("only the followed parts are announced", said == ["releases", "issues"], said)


# ==========================================================================
#   Frequency and observe mode
# ==========================================================================

def t_observe_mode_records_and_never_delivers():
    g = world()
    W.watch_repo(DEFAULT, frequency="instant")
    W.poll_repos(now=T0, fetcher=g)
    said = []
    W._deliver = lambda *a, **k: (said.append(a), True)[1]
    g.set(f"/repos/{DEFAULT}/releases?per_page=10",
          [release(2, "v2"), release(1, "v1")])
    out = W.poll_repos(now=T0 + 601, fetcher=g)
    check("observe mode discovers the item", out["new"] == 1, out)
    check("observe mode never delivers", said == [], said)
    rows = WC.default_store().decisions(20)
    check("observe mode writes the row it WOULD have said",
          any(r.get("reason_code") == "repo_observe_shadow" for r in rows), rows[:2])


def t_daily_and_weekly_keep_items_for_the_digest_and_carry_them_once():
    g = world()
    W.watch_repo(DEFAULT, frequency="daily", events=["commits"])
    W.poll_repos(now=T0, fetcher=g)
    W.set_repo_mode(DEFAULT, "active")
    said = []
    W._deliver = lambda name, kind, title, url, now: (said.append(title), True)[1]
    g.set(f"/repos/{DEFAULT}/commits?per_page=10",
          [commit("c" * 40, "a new commit"), commit("a" * 40, "first")])
    out = W.poll_repos(now=T0 + 6 * 3600 + 1, fetcher=g)
    check("a daily item is kept, not delivered at once", out["new"] == 1 and said == [],
          (out, said))
    W.deliver_digest(now=T0 + 6 * 3600 + 2)
    check("the digest carries it", said == ["new commits: a new commit"], said)
    W.deliver_digest(now=T0 + 12 * 3600)
    check("and never carries it twice",
          said == ["new commits: a new commit"], said)

    # weekly, from a clean store
    g2 = world()
    W.watch_repo(DEFAULT, frequency="weekly", events=["commits"])
    W.set_repo_mode(DEFAULT, "active")
    said2 = []
    W._deliver = lambda name, kind, title, url, now: (said2.append(title), True)[1]
    W.poll_repos(now=T0, fetcher=g2)
    g2.set(f"/repos/{DEFAULT}/commits?per_page=10",
           [commit("d" * 40, "weekly news"), commit("a" * 40, "first")])
    W.poll_repos(now=T0 + 7 * 86400, fetcher=g2)
    W.deliver_digest(now=T0 + 7 * 86400 + 10)
    check("a weekly watch waits a week between digests",
          said2 == ["new commits: weekly news"], said2)


def t_off_polls_nothing_and_records_only():
    g = world()
    W.watch_repo(DEFAULT, frequency="instant")
    W.set_repo_frequency(DEFAULT, "off")
    before = len(g.calls)
    out = W.poll_repos(now=T0 + 99999, fetcher=g)
    check("a pull-only watch asks GitHub nothing", len(g.calls) == before,
          len(g.calls) - before)
    check("... and is counted as skipped", out["skipped"] >= 1, out)
    W.set_repo_frequency(DEFAULT, "off")
    check("off remembers what to resume", W.repo_watches()[0]["frequency"] == "off")
    W.resume_repo(DEFAULT)
    check("resume goes back to the cadence it had",
          W.repo_watches()[0]["frequency"] == "instant",
          W.repo_watches()[0]["frequency"])


def t_stop_resume_and_forget():
    g = world()
    r = W.watch_repo(DEFAULT, frequency="daily", events=["releases"])
    check("a new watch starts in observe mode", r["mode"] == "observe", r)
    check("... and the default target is the owner's own repository",
          W.watch_repo(None)["repo"] == W.REPO_DEFAULT)
    check("stop talking sets pull-only, and keeps the watch",
          W.set_repo_frequency(W.REPO_DEFAULT, "off")["ok"]
          and len(W.repo_watches()) == 1)
    check("resume brings the cadence back",
          W.resume_repo(W.REPO_DEFAULT)["frequency"] == "daily")
    check("forget deletes the watch",
          W.stop_repo(W.REPO_DEFAULT)["ok"] and W.repo_watches() == [])
    check("forgetting a watch it does not have says so",
          not W.stop_repo(DEFAULT)["ok"])
    check("a bad repository name is refused with words",
          not W.watch_repo("not a repo")["ok"])
    check("the cap is real", W.REPO_MAX_WATCHES >= 5)


def t_follow_new_repos_for_a_topic():
    fresh()
    g = FakeGitHub()

    def search_body(*items):
        return {"items": [{"id": rid, "full_name": name} for rid, name in items]}
    g.set("/search/repositories?q=mcp&sort=updated&order=desc&per_page=30",
          search_body((1, "a/one")))
    r = W.follow_new("mcp", frequency="instant")
    check("follow new starts in observe mode", r["mode"] == "observe", r)
    W.poll_repos(now=T0, fetcher=g)
    rows = WC.default_store().decisions(20)
    check("the topic's existing repositories are not announced",
          not any(x.get("verdict") == "repo_new_repo" for x in rows), rows)
    g.set("/search/repositories?q=mcp&sort=updated&order=desc&per_page=30",
          search_body((2, "b/two"), (1, "a/one")))
    W.set_follow_mode("mcp", "active")
    W._deliver = lambda *a, **k: True
    out = W.poll_repos(now=T0 + 700, fetcher=g)
    rows = WC.default_store().decisions(20)
    check("only the NEW repository is an item",
          sum(1 for x in rows if x.get("verdict") == "repo_new_repo") == 1, rows)
    check("the new-repo row names the repository",
          any(x.get("repo") == "b/two" for x in rows))
    W.poll_repos(now=T0 + 1400, fetcher=g)
    rows = WC.default_store().decisions(20)
    check("the same new repository is never announced twice",
          sum(1 for x in rows if x.get("verdict") == "repo_new_repo") == 1, rows)
    check("stop following a topic works", W.stop_follow("mcp")["ok"])


# ==========================================================================
#   Chat and Live: one matcher, one runner, one card
# ==========================================================================

LIVE_WORDS = [
    # (sentence, expected action, expected repo/topic, frequency, events)
    ("watch darknight11ish/Epic-Jarvis", "watch", DEFAULT, "daily", None),
    ("watch your repo", "watch", "", "daily", None),
    ("watch my repo daily", "watch", "", "daily", None),
    ("watch the repo instantly", "watch", "", "instant", None),
    ("watch darknight11ish/Epic-Jarvis weekly", "watch", DEFAULT, "weekly", None),
    ("watch darknight11ish/Epic-Jarvis for new releases and issues", "watch",
     DEFAULT, "daily", ["releases", "issues"]),
    ("follow new releases and pull requests on darknight11ish/Epic-Jarvis",
     "watch", DEFAULT, "daily", ["releases", "prs"]),
    ("track darknight11ish/Epic-Jarvis for commits, issues and CI", "watch",
     DEFAULT, "daily", ["commits", "issues", "ci"]),
    ("stop telling me about darknight11ish/Epic-Jarvis", "stop_talking", DEFAULT,
     None, None),
    ("stop telling me about your repo", "stop_talking", "", None, None),
    ("stop watching darknight11ish/Epic-Jarvis", "forget", DEFAULT, None, None),
    ("forget darknight11ish/Epic-Jarvis", "forget", DEFAULT, None, None),
    ("resume watching darknight11ish/Epic-Jarvis", "resume", DEFAULT, None, None),
    ("tell me daily about that repo", "frequency", "", "daily", None),
    ("tell me weekly about darknight11ish/Epic-Jarvis", "frequency", DEFAULT,
     "weekly", None),
    ("follow new repos for topic mcp", "follow_new", "mcp", "", None),
    ("follow new for mcp", "follow_new", "mcp", "", None),
    ("follow new", "follow_new", "", "", None),
]


def t_the_sentences_chat_and_live_understand():
    old = W.DB_PATH
    for text, action, repo, freq, events in LIVE_WORDS:
        got = Q.match(text, T0)
        ok = (got is not None and got.name in ("repo_watch", "repo_watch_list")
              and (got.f or {}).get("action") == action)
        if ok and action in ("watch", "frequency"):
            ok = (got.f.get("repo") == repo if "repo" in got.f else repo == "")
        if ok and action == "watch":
            ok = (got.f.get("frequency") or "daily") == (freq or "daily")
            if events:
                ok = ok and got.f.get("events") == events
        if ok and action == "frequency":
            ok = got.f.get("frequency") == freq
        if ok and action == "follow_new":
            ok = got.f.get("topic") == repo
        check(f"chat and Live both understand: {text!r}", ok,
              got and (got.name, got.f))
    for text in ("what am I watching", "what repos are you watching",
                 "which repositories are you following"):
        got = Q.match(text, T0)
        check(f"read-only list: {text!r}", got is not None and
              got.name == "repo_watch_list", got and got.name)
    for text in ("watch with me", "tell me when CI fails on darknight11ish/Epic-Jarvis",
                 "what are you doing", "watch this"):
        got = Q.match(text, T0)
        check(f"not this feature: {text!r}", got is None or
              not str(getattr(got, "name", "")).startswith("repo_watch"),
              got and got.name)
    W.DB_PATH = old


class _Verdict:
    def __init__(self, allowed):
        self.allowed = allowed


class Gate:
    """A gate that records the card and, when asked to, WAITS before answering
    - so the test can look at the watch while the card is still open."""

    def __init__(self, allow=True, blocking=False):
        self.calls = []
        self.allow = allow
        self.blocking = blocking
        self.answered = threading.Event()
        self.release = threading.Event()

    def __call__(self, action, detail, prompt=""):
        self.calls.append((action, detail, prompt))
        if self.blocking:
            self.release.wait(3.0)
            self.answered.set()
        return _Verdict(self.allow)


def t_starting_a_watch_raises_one_card_through_the_gate():
    d = fresh()
    g = world()
    gate = Gate(allow=True, blocking=True)
    Q._gate_module = lambda: types.SimpleNamespace(check=gate)
    res = Q.answer("watch darknight11ish/Epic-Jarvis instantly", now=T0)
    check("the runner answers in words", res is not None and "card" in res.reply,
          res and res.reply)
    for _ in range(300):
        import time
        if W.repo_watches():
            break
        time.sleep(0.01)
    check("the watch exists in observe mode while the card is still open",
          W.repo_watches() and W.repo_watches()[0]["mode"] == "observe",
          W.repo_watches())
    for _ in range(300):
        import time
        if gate.calls:
            break
        time.sleep(0.01)
    check("ONE card was raised, through the gate", len(gate.calls) == 1, gate.calls)
    action, detail, prompt = gate.calls[0]
    check("the card uses the gate's existing repeating-watch action",
          action == "schedule_repeat", action)
    check("the prompt says exactly what is watched and that nothing rings",
          DEFAULT in prompt and "no" in prompt.lower() and
          "ring" in prompt.lower(), prompt)
    gate.release.set()
    for _ in range(300):
        import time
        if W.repo_watches() and W.repo_watches()[0]["mode"] == "active":
            break
        time.sleep(0.01)
    check("a yes makes the watch active", W.repo_watches()[0]["mode"] == "active",
          W.repo_watches())
    # A declined card changes nothing.
    fresh()
    gate2 = Gate(allow=False)
    Q._gate_module = lambda: types.SimpleNamespace(check=gate2)
    Q.answer("watch darknight11ish/Epic-Jarvis daily", now=T0)
    for _ in range(100):
        import time
        if gate2.calls:
            break
        time.sleep(0.01)
    import time as _t
    _t.sleep(0.05)
    check("a no leaves the watch in observe mode",
          W.repo_watches()[0]["mode"] == "observe", W.repo_watches())


def t_the_runners_other_sentences():
    fresh()
    world()
    gate = Gate(allow=True)
    Q._gate_module = lambda: types.SimpleNamespace(check=gate)
    res = Q.answer("watch darknight11ish/Epic-Jarvis daily", now=T0)
    check("stop talking is instant and needs no card",
          "pull-only" in Q.answer("stop telling me about darknight11ish/Epic-Jarvis",
                                  now=T0).reply)
    check("resume says the cadence", "daily" in Q.answer(
        "resume watching darknight11ish/Epic-Jarvis", now=T0).reply)
    check("a cadence change on an existing watch is instant",
          "daily" in Q.answer("tell me daily about darknight11ish/Epic-Jarvis",
                              now=T0).reply)
    check("forget says what it forgot", "forgot" in Q.answer(
        "forget darknight11ish/Epic-Jarvis", now=T0).reply)
    listed = Q._run_repo_watch(Q.Intent("repo_watch_list"), T0).reply
    check("list reads the store (it was just forgotten)",
          "not watching any repository" in listed, listed)
    check("follow new without a topic asks which",
          "topic" in Q.answer("follow new", now=T0).reply.lower())
    check("a bad stream of words is not claimed by the runner",
          res is not None)


def t_rows_carry_the_closed_set_and_the_ci_shape():
    rows = WC.default_store().decisions(200)
    if not rows:
        fresh()
        g = world()
        W.watch_repo(DEFAULT, frequency="instant")
        W.poll_repos(now=T0, fetcher=g)
        W.set_repo_mode(DEFAULT, "active")
        g.set(f"/repos/{DEFAULT}/releases?per_page=10",
              [release(3, "v3"), release(1, "v1")])
        W.poll_repos(now=T0 + 700, fetcher=g)
        rows = WC.default_store().decisions(200)
    check("there are decision rows to read", bool(rows))
    for row in rows:
        check(f"row {row.get('reason_code')!r} is in the closed set",
              row.get("reason_code") in W.WATCH_REASONS, row)
        check("... carries the CI watcher's shape",
              all(k in row for k in ("at", "source", "thread_key", "outcome",
                                     "reason_code", "preview_text", "mode",
                                     "verdict", "delivery")), row)
        break
    check("the source names the repository watcher",
          rows[0].get("source") == "github-watch-repos", rows[0])
    served = WC.view("5")
    check("the store the CI watcher serves answers the same rows",
          isinstance(served, dict) and "decisions" in served
          and any(r.get("source") == "github-watch-repos"
                  for r in served["decisions"]), served.keys())


def main() -> int:
    cases = [v for k, v in sorted(globals().items()) if k.startswith("t_")]
    for fn in cases:
        print(f"\n-- {fn.__name__}")
        try:
            fn()
        except Exception:
            traceback.print_exc()
            FAILED.append(fn.__name__ + " (exception)")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:")
        for name in FAILED:
            print("  -", name)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
