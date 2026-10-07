"""jarvis_research.py - has someone already built this?

WHAT IT IS FOR
Before an Android app idea becomes a directory full of code, the cheapest
possible question is whether the thing already exists and is maintained. This
module asks GitHub, grades what comes back, and produces a Redundancy Matrix:
for each capability the idea needs, ADOPT an existing library, FORK AND EXTEND
one, or BUILD CUSTOM because nothing close exists.

THE PERMISSION MODEL, WHICH IS THE POINT
Jarvis is local-first. It does not decide on its own to talk to the internet.

So this module is split in two halves that cannot be confused for each other:

    plan(idea)          works out what it would need to ask, and asks nothing.
                        No socket is opened. Returns a Plan.
    run(plan, fetch)    executes a plan that a human has already approved.

The Plan is the thing a person reads. It carries the LITERAL URL of every
request, the host it goes to, one plain sentence saying why that request is
worth making, and - the part that is easy to leave out and matters most - what
Jarvis will do instead if the answer is no. A permission request that does not
say what refusing costs is not a question, it is a nudge.

WHY ONE CARD FOR SEVERAL QUERIES IS NOT AN "APPROVE ALL"
There is no approve-all in Jarvis and this does not build one. An approve-all
is a control that grants permission for FUTURE, UNNAMED actions. This grants
permission for one bounded set of requests, every one of them written out in
full, for one audit, once. Approving it cannot authorise a request that is not
printed on the card, and it expires with the audit. That is the same shape as
approving a single shell command that happens to have several arguments.

WHAT ACTUALLY LEAVES
Only a search term, by default. GitHub's code and repository search is public
and needs no credential of the owner's, so unauthenticated use of this module
stores no key and needs none. The search term is derived from the idea
locally, and it is shown on the card verbatim - because the honest version of
"may I search for this" is to print the string, not to summarise it.

AUTHENTICATED REQUESTS - OPT IN, NEVER STORED HERE
If `JARVIS_GITHUB_TOKEN` is set in the environment, requests carry it and can
therefore see private repositories and a much higher rate limit. This module
never writes that token to disk, never logs it, and never puts it in a Plan or
a Query - `describe()` says only THAT a request is authenticated, never with
what. Persisting the token between runs (so the owner is not setting an
environment variable every session) is deliberately left to whatever process
already handles the pairing token with the same care - not duplicated here.
"""

from __future__ import annotations

import calendar
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional

GITHUB_API = "https://api.github.com"

#: Set this, per the owner's own machine, to search private repositories too
#: and stop hitting the public rate limit. Read fresh on every request rather
#: than cached at import time, so rotating it needs no restart.
TOKEN_ENV = "JARVIS_GITHUB_TOKEN"


def _token() -> str:
    return os.environ.get(TOKEN_ENV, "").strip()


def authenticated() -> bool:
    """Whether a token is configured. Never reveals the token itself."""
    return bool(_token())

# Licences that can be taken into a project without changing its terms. This
# is a compatibility judgement, not legal advice, and it is deliberately
# conservative: anything not on the list is graded as needing a look rather
# than being quietly treated as fine.
PERMISSIVE = {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc",
              "unlicense", "0bsd", "zlib", "mpl-2.0"}
# Usable, but they reach into what you build. Worth knowing BEFORE the code is
# written rather than after.
COPYLEFT = {"gpl-2.0", "gpl-3.0", "agpl-3.0", "lgpl-2.1", "lgpl-3.0"}

# A repository that has not been touched in this long is not maintained,
# whatever its star count says.
FRESH_DAYS = 365
# Below this, you are the maintenance plan.
POPULAR_STARS = 500
# And below THIS, it is not a candidate at all. A four-star repository is one
# person's weekend, and "fork and extend" implies there is enough there to be
# worth taking over. Reading it may still be useful; depending on it is not,
# and neither is inheriting it.
VIABLE_STARS = 50

_STOP = {
    "a", "an", "and", "app", "application", "android", "are", "as", "at", "be",
    "build", "building", "but", "by", "can", "create", "for", "from", "have",
    "i", "in", "is", "it", "its", "just", "like", "make", "me", "my", "of",
    "on", "or", "small", "so", "some", "that", "the", "their", "them", "then",
    "there", "they", "thing", "this", "to", "up", "use", "user", "want", "was",
    "what", "when", "which", "with", "would", "you", "your",
}


# --------------------------------------------------------------------------
#   The plan - built locally, read by a human, executed by nothing
# --------------------------------------------------------------------------

@dataclass
class Query:
    """One request, written out in full because that is what gets approved."""
    url: str
    host: str
    why: str
    capability: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Plan:
    idea: str
    queries: list = field(default_factory=list)
    capabilities: list = field(default_factory=list)
    # What happens if this is refused. Written at plan time, not improvised
    # afterwards, so the person deciding can see the cost of saying no.
    if_refused: str = ""
    # Captured at plan() time, not read fresh by describe()/run(): the person
    # approves the card that was PRINTED. If the token gets set or unset
    # between the card being shown and run() actually executing, run() must
    # refuse rather than silently do something other than what was disclosed.
    authenticated: bool = False

    def hosts(self) -> list:
        return sorted({q.host for q in self.queries})

    def as_dict(self) -> dict:
        d = asdict(self)
        d["hosts"] = self.hosts()
        return d


def terms(idea: str, limit: int = 6) -> list:
    """Salient words from the idea. Local, dumb on purpose, and inspectable.

    A model could do this better. It is deliberately a visible rule instead,
    because these words are the thing that leaves the machine - and a person
    approving the request should be able to see exactly why each one is there.
    """
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{1,}", str(idea).lower())
    out = []
    for w in words:
        w = w.strip(".-")
        if len(w) < 3 or w in _STOP or w in out:
            continue
        out.append(w)
    return out[:limit]


def plan(idea: str, capabilities: Optional[list] = None) -> Plan:
    """Work out what would have to be asked. Opens no socket.

    `capabilities` is the architectural slice - "offline sqlite sync",
    "background location", "pdf annotation" - so the matrix grades each part
    of the app separately. An idea is rarely redundant as a whole; it is
    usually two solved problems and one that is not.
    """
    words = terms(idea)
    caps = [str(c).strip() for c in (capabilities or []) if str(c).strip()]
    if not caps:
        caps = [" ".join(words[:3])] if words else []

    queries: list = []
    for cap in caps:
        cap_terms = terms(cap, limit=4) or words[:3]
        if not cap_terms:
            continue
        q = " ".join(cap_terms) + " language:kotlin OR language:java"
        url = (f"{GITHUB_API}/search/repositories?q="
               + urllib.parse.quote(q, safe="")
               + "&sort=stars&order=desc&per_page=10")
        queries.append(Query(
            url=url, host="api.github.com", capability=cap,
            why=f"find maintained libraries that already do {cap!r}, "
                f"so it is not written twice"))
    return Plan(
        idea=str(idea), queries=queries, capabilities=caps,
        if_refused=("no GitHub audit: the matrix will be empty and every "
                    "capability defaults to BUILD CUSTOM, which may mean "
                    "rewriting something that already exists and is better"),
        authenticated=authenticated())


def describe(p: Plan) -> str:
    """The card text. Every URL in full - no summarising, no ellipsis.

    Summarising an outbound request on the card that authorises it defeats the
    card. If it is too long to read, that is information about the request.
    """
    if not p.queries:
        return ("Nothing to ask. No search terms could be derived from that "
                "idea, so there is nothing to look up and nothing will be sent.")
    auth_line = (
        "Authenticated: this will identify you to GitHub with your configured "
        "token, to reach private repositories and a higher rate limit."
        if p.authenticated else
        "Public repository search. No account of yours is used and no "
        "credential is sent."
    )
    lines = [f"Jarvis would like to search GitHub about: {p.idea}",
             "",
             f"{len(p.queries)} request(s), to {', '.join(p.hosts())}.",
             auth_line,
             ""]
    for i, q in enumerate(p.queries, 1):
        lines += [f"  {i}. {q.why}", f"     {q.url}", ""]
    lines += ["What leaves this machine: the search terms above, and nothing "
              "else. Not the idea in your words, not your files, not your "
              "conversation" + (", and your GitHub token, to that request "
              "only." if p.authenticated else "."),
              "",
              f"If you say no: {p.if_refused}"]
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Execution - only ever with a plan a human said yes to
# --------------------------------------------------------------------------

class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """Stops a redirect from carrying the GitHub token to another host.

    `urllib` copies every header except content-length/content-type onto the
    redirect target, cross-host included, so a 302 hands over the token.
    Rule 3 says a key is "sent only to the one service it authenticates
    against", and following a redirect is how it stops being.

    Lower risk here than in `jarvis_home`, because the host is the fixed
    `api.github.com` rather than one the owner points at an env var - but
    the control is the same one and cheap, and "low risk" is a property of
    today's URL builder, not of this function.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"refused to follow a redirect to {newurl}: the GitHub token "
            f"would have been sent there.",
            headers,
            fp,
        )


def _get(url: str, timeout: float = 20.0) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "jarvis-research",
    }
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(_RefuseRedirect)
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def run(p: Plan, *, fetch: Optional[Callable[[str], dict]] = None,
        approved: bool = False) -> dict:
    """Execute an approved plan.

    `approved` is not a courtesy argument and it has no default of True. The
    caller has to have gone and got an answer. A module that can reach the
    network must not be one function call away from doing it by accident.

    `fetch` is injectable so the grading below can be tested without a socket,
    which is also how it is tested here.
    """
    if not approved:
        return {"ok": False, "reason": "not approved; nothing was sent",
                "plan": p.as_dict()}
    # The person approved the card that was printed, and that card said
    # whether this was authenticated. If the token was set or unset in the
    # gap between the card being shown and run() actually being called, this
    # is no longer the plan that was approved - refuse rather than silently
    # send something other than what was disclosed.
    if p.authenticated != authenticated():
        return {"ok": False,
                "reason": ("refused: whether a GitHub token is configured "
                           "changed since this plan was approved - the "
                           "approved card no longer describes what would "
                           "actually be sent"),
                "plan": p.as_dict()}
    get = fetch or _get
    found: dict = {}
    errors: list = []
    for q in p.queries:
        try:
            body = get(q.url)
        except Exception as exc:
            errors.append({"url": q.url, "error": f"{type(exc).__name__}: {exc}"})
            continue
        items = (body or {}).get("items") or []
        found.setdefault(q.capability, []).extend(items)
    return {"ok": True, "found": found, "errors": errors,
            "asked": [q.as_dict() for q in p.queries]}


# --------------------------------------------------------------------------
#   The matrix
# --------------------------------------------------------------------------

def _age_days(pushed_at: str, now: Optional[float] = None) -> Optional[float]:
    if not pushed_at:
        return None
    try:
        t = time.strptime(str(pushed_at)[:19], "%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        return None
    # calendar.timegm, not time.mktime. GitHub's `pushed_at` is UTC and says
    # so with its trailing Z; mktime reads a struct_time as LOCAL time, so
    # the age of a repository came out shifted by the machine's own UTC
    # offset - and for a repository pushed within that offset, NEGATIVE.
    # The owner is in a timezone where that is hours, not minutes.
    return ((now or time.time()) - calendar.timegm(t)) / 86400.0


def grade_repo(repo: dict, now: Optional[float] = None) -> dict:
    """One repository, graded on the three things that decide the answer.

    Stars are popularity, which is a proxy for "someone else has hit the bugs
    you are about to hit". Recency is maintenance. Licence is whether you can
    use it at all. A repo can be enormous and still be the wrong answer on any
    one of the three, and the grade says which, because "no" without a reason
    gets overruled by the next person who looks.
    """
    stars = int(repo.get("stargazers_count") or 0)
    raw_lic = ((repo.get("license") or {}).get("spdx_id") or "").lower()

    # NOASSERTION is NOT "no licence". It is GitHub's classifier saying it
    # could not match the LICENSE file against a known template - which is
    # exactly what a custom or amended licence looks like to it.
    #
    # The first run of this function on real data called janhq/jan and
    # open-webui "NO LICENCE, which means no permission to use it". Both have
    # licence files, and both had already been read in this project:
    #
    #   jan         "Licensed under the Apache License, Version 2.0", with an
    #               added request for attribution - which is why the matcher
    #               balks. Permissive.
    #   open-webui  a custom "Open WebUI License": BSD-3 plus a clause
    #               forbidding removal of their branding above fifty users.
    #               NOT permissive.
    #
    # Opposite answers. Collapsing both into "no permission" skips a usable
    # project for no reason, and would be wrong in the dangerous direction the
    # moment the rest of the row said ADOPT.
    #
    # So: absent means absent, unclassified means go and read the file.
    # Neither counts as usable, because "go and read it" is not "yes".
    unclassified = raw_lic == "noassertion"
    lic = "" if raw_lic in ("noassertion", "none", "") else raw_lic

    age = _age_days(repo.get("pushed_at") or "", now)
    archived = bool(repo.get("archived"))

    reasons = []
    if archived:
        reasons.append("archived by its owner")
    if age is None:
        reasons.append("no push date")
    elif age > FRESH_DAYS:
        reasons.append(f"last push {age / 365:.1f} years ago")
    if stars < POPULAR_STARS:
        reasons.append(f"{stars} stars")
    if unclassified:
        reasons.append("GitHub could not identify the licence, which usually "
                       "means a custom or amended one - OPEN THE FILE. This is "
                       "not the same as having none")
    elif not lic:
        reasons.append("NO LICENCE, which means no permission to use it")
    elif lic in COPYLEFT:
        reasons.append(f"{lic} reaches into what you build")
    elif lic not in PERMISSIVE:
        reasons.append(f"{lic} needs reading before it is relied on")

    maintained = not archived and age is not None and age <= FRESH_DAYS
    popular = stars >= POPULAR_STARS
    viable = stars >= VIABLE_STARS
    usable = lic in PERMISSIVE

    if maintained and popular and usable:
        verdict = "ADOPT"
    elif lic and viable and (maintained or popular):
        # Enough there to be worth taking over, and a licence that allows it -
        # but something is wrong with it: stale, or copyleft, or not popular
        # enough to have had its bugs found by anyone but you.
        verdict = "FORK AND EXTEND"
    else:
        verdict = "BUILD CUSTOM"
    if not viable and stars:
        reasons.append(f"below {VIABLE_STARS} stars is not a candidate, "
                       f"though it may still be worth reading")

    return {"name": repo.get("full_name") or repo.get("name") or "?",
            "url": repo.get("html_url") or "",
            "stars": stars, "licence": lic or None,
            "archived": archived,
            "days_since_push": None if age is None else round(age),
            "verdict": verdict,
            "why": "; ".join(reasons) if reasons
                   else f"{stars} stars, {lic}, pushed {round(age)} days ago"}


def matrix(result: dict, now: Optional[float] = None) -> dict:
    """The Redundancy Matrix: one verdict per capability, with its evidence.

    The capability verdict is the BEST repo's verdict, because the question
    being asked is "is there something to adopt", and one good answer settles
    it. The rejected candidates are kept alongside, since the usual reason a
    matrix gets overruled later is that nobody could see what was considered.
    """
    if not result.get("ok"):
        return {"ok": False, "reason": result.get("reason", "no result"),
                "rows": []}
    order = {"ADOPT": 0, "FORK AND EXTEND": 1, "BUILD CUSTOM": 2}
    rows = []
    for cap, repos in (result.get("found") or {}).items():
        graded = sorted((grade_repo(r, now) for r in repos if isinstance(r, dict)),
                        key=lambda g: (order[g["verdict"]], -g["stars"]))
        rows.append({
            "capability": cap,
            "verdict": graded[0]["verdict"] if graded else "BUILD CUSTOM",
            "best": graded[0] if graded else None,
            "considered": graded[1:6],
            "note": None if graded else
                    "nothing came back for this capability, which is a weaker "
                    "statement than 'nothing exists' - it may be the search terms",
        })
    rows.sort(key=lambda r: order[r["verdict"]])
    return {"ok": True, "rows": rows, "errors": result.get("errors") or []}


def render(m: dict) -> str:
    """The matrix as something a person reads rather than parses."""
    if not m.get("ok"):
        return f"No matrix: {m.get('reason', 'unknown')}"
    if not m.get("rows"):
        return "No capabilities were audited."
    out = []
    for row in m["rows"]:
        out.append(f"{row['verdict']:<16} {row['capability']}")
        b = row.get("best")
        if b:
            out.append(f"                 {b['name']}  ({b['stars']} stars, "
                       f"{b['licence'] or 'no licence'})")
            out.append(f"                 {b['why']}")
        elif row.get("note"):
            out.append(f"                 {row['note']}")
        out.append("")
    if m.get("errors"):
        out.append(f"{len(m['errors'])} request(s) failed; those capabilities "
                   f"are unaudited, not clear.")
    return "\n".join(out)
