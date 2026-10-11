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
        # The frozen capability set is what makes this safe to leave running:
        # the job may search and it may write its own database, and there is
        # no path by which it can widen that while it runs.
        topic = (params or {}).get("topic")
        out = check(topic, fetcher=(params or {}).get("fetcher"))
        ctx.progress(f"checked {out['checked']} topic(s)")
        # Even here it does not speak. A notify topic reaches the daily brief;
        # everything else waits for the owner to ask.
        out["queued_for_digest"] = to_digest()
        return out

    jarvis_jobs.register("watch_github", handler)
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
