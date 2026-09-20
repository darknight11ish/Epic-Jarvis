"""The redundancy engine, and the promise that it asks before it reaches out.

Two things are being tested and only one of them is the grading. The other is
that `plan()` cannot touch the network and `run()` cannot be tricked into it,
because the whole design rests on that split being real rather than a comment.

    python3 test_research.py
"""
import socket, sys, time, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# BACKEND is where the modules under test actually live - this folder in
# the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, missing, explain

# jarvis_research.py is OURS - it ships in this repository, it is not part of
# the backend being patched. _where prepends BACKEND to sys.path, which is
# right for jarvis_memory and friends and wrong here: a stale copy sitting in
# someone's backend folder would shadow the real one, and this test would then
# be checking a file nobody edits. Put this directory first, for this import.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_research as R

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class NoNetwork:
    """Any socket at all, in this block, is a failure."""

    def __enter__(self):
        self.real = socket.socket.connect
        def boom(*a, **k):
            raise AssertionError("a socket was opened")
        socket.socket.connect = boom
        return self

    def __exit__(self, *a):
        socket.socket.connect = self.real
        return False


NOW = time.mktime(time.strptime("2026-09-15T00:00:00", "%Y-%m-%dT%H:%M:%S"))


def repo(name="acme/thing", stars=1200, lic="MIT", pushed="2026-08-01T00:00:00Z",
         archived=False):
    return {"full_name": name, "stargazers_count": stars,
            "license": {"spdx_id": lic} if lic else None,
            "pushed_at": pushed, "archived": archived,
            "html_url": f"https://github.com/{name}"}


def t_planning_touches_nothing():
    with NoNetwork():
        p = R.plan("an offline pdf annotator that syncs between my phone and laptop",
                   ["pdf annotation", "offline sqlite sync"])
    check("a plan can be built with the network unplugged", len(p.queries) == 2,
          f"{len(p.queries)} queries")
    check("one query per capability",
          sorted(q.capability for q in p.queries) == ["offline sqlite sync", "pdf annotation"],
          repr([q.capability for q in p.queries]))
    check("every query names exactly one host", all(q.host == "api.github.com" for q in p.queries))
    check("every query carries a reason a person can read",
          all(len(q.why) > 20 for q in p.queries), repr([q.why for q in p.queries]))
    check("the plan says what refusing costs", "BUILD CUSTOM" in p.if_refused,
          p.if_refused)


def t_the_card_prints_the_whole_request():
    p = R.plan("a habit tracker", ["local notifications"])
    card = R.describe(p)
    check("the literal URL is on the card", p.queries[0].url in card,
          "a summarised URL defeats the card that authorises it")
    check("the card says what leaves", "What leaves this machine" in card)
    check("the card says no credential is used", "credential" in card)
    check("the card says what happens on a refusal", "If you say no" in card, card[-200:])
    # The idea in the owner's own words must NOT be what goes out.
    p2 = R.plan("track my lithium doses and mood for my psychiatrist",
                ["chart rendering"])
    check("the outbound query carries derived terms, not the raw sentence",
          "psychiatrist" not in p2.queries[0].url and "lithium" not in p2.queries[0].url,
          p2.queries[0].url)


def t_run_refuses_without_approval():
    p = R.plan("a habit tracker", ["local notifications"])
    with NoNetwork():
        out = R.run(p)                       # no approved=True
    check("run() sends nothing when it was not approved", out["ok"] is False, repr(out))
    check("and says so plainly", "not approved" in out["reason"], out["reason"])
    with NoNetwork():
        out = R.run(p, approved=False)
    check("approved=False is the same as not asking", out["ok"] is False)
    # CONTROL: with approval and an injected fetch it does run.
    calls = []
    out = R.run(p, approved=True, fetch=lambda u: (calls.append(u), {"items": [repo()]})[1])
    check("CONTROL: an approved plan does execute", out["ok"] is True and len(calls) == 1,
          repr(out))


def t_authenticated_requests_are_opt_in_and_disclosed():
    import os
    saved = os.environ.pop(R.TOKEN_ENV, None)
    try:
        check("no token configured by default", R.authenticated() is False)
        p = R.plan("a habit tracker", ["local notifications"])
        check("an unauthenticated plan says so", p.authenticated is False)
        card = R.describe(p)
        check("the card says it is public, not authenticated",
              "No account of yours is used" in card, card)
        check("an unauthenticated card never claims a token is sent",
              "your GitHub token" not in card, card)

        os.environ[R.TOKEN_ENV] = "not-a-real-token"
        check("setting the env var flips authenticated()", R.authenticated() is True)
        p2 = R.plan("a habit tracker", ["local notifications"])
        check("a plan made now captures that", p2.authenticated is True)
        card2 = R.describe(p2)
        check("the card discloses authentication", "Authenticated:" in card2, card2)
        check("but never prints the token itself",
              "not-a-real-token" not in card2, card2)

        # run() must send the header when authenticated - proven with a fake
        # transport, never a socket.
        seen_headers = {}
        def fetch(url):
            return {"items": []}
        # _get is what actually sets headers; run() takes a fetch override for
        # the network call itself, so exercise _get directly with NoNetwork
        # to prove it WOULD attach the header, without opening a socket.
        import urllib.request
        real_urlopen = urllib.request.urlopen
        def fake_urlopen(req, timeout=None):
            seen_headers.update(dict(req.header_items()))
            class Resp:
                def __enter__(self_): return self_
                def __exit__(self_, *a): return False
                def read(self_): return b'{"items": []}'
            return Resp()
        urllib.request.urlopen = fake_urlopen
        try:
            R._get(p2.queries[0].url)
        finally:
            urllib.request.urlopen = real_urlopen
        check("an authenticated request carries the bearer token",
              seen_headers.get("Authorization") == "Bearer not-a-real-token",
              repr(seen_headers))

        # The staleness guard: the token disappearing between describe() and
        # run() must refuse, not silently downgrade to anonymous.
        del os.environ[R.TOKEN_ENV]
        with NoNetwork():
            out = R.run(p2, approved=True)
        check("run() refuses a plan whose auth state changed underneath it",
              out["ok"] is False and "changed" in out["reason"], repr(out))
    finally:
        if saved is None:
            os.environ.pop(R.TOKEN_ENV, None)
        else:
            os.environ[R.TOKEN_ENV] = saved


def t_grading():
    g = R.grade_repo(repo(), NOW)
    check("popular + maintained + permissive is ADOPT", g["verdict"] == "ADOPT", repr(g))

    g = R.grade_repo(repo(pushed="2021-01-01T00:00:00Z"), NOW)
    check("stale but popular and permissive is FORK AND EXTEND",
          g["verdict"] == "FORK AND EXTEND", repr(g))
    check("and it says how stale", "years ago" in g["why"], g["why"])

    g = R.grade_repo(repo(lic=None), NOW)
    check("no licence is never ADOPT", g["verdict"] != "ADOPT", repr(g))
    check("and it says why that matters",
          "no permission to use it" in g["why"], g["why"])

    g = R.grade_repo(repo(lic="GPL-3.0"), NOW)
    check("copyleft is not silently adopted", g["verdict"] != "ADOPT", repr(g))
    check("and it says what copyleft does", "reaches into" in g["why"], g["why"])

    g = R.grade_repo(repo(stars=12), NOW)
    check("12 stars is not something to depend on", g["verdict"] != "ADOPT", repr(g))

    g = R.grade_repo(repo(archived=True), NOW)
    check("archived is never ADOPT", g["verdict"] != "ADOPT", repr(g))
    check("and it says archived", "archived" in g["why"], g["why"])

    # This test used to assert `"no permission" in g["why"]`, and it was
    # pinning the wrong belief. NOASSERTION is GitHub's classifier saying it
    # could not MATCH the licence file, not that there is not one. The first
    # run on real data called janhq/jan - "Licensed under the Apache License,
    # Version 2.0" with an added attribution request - a project with "no
    # permission to use it".
    g = R.grade_repo(repo(lic="NOASSERTION"), NOW)
    check("NOASSERTION is not usable, because nobody has read the file yet",
          g["verdict"] != "ADOPT" and g["licence"] is None, repr(g))
    check("but it is NOT called 'no licence'",
          "no permission" not in g["why"], g["why"])
    check("and it says to go and read the file",
          "OPEN THE FILE" in g["why"], g["why"])

    g = R.grade_repo(repo(lic=None), NOW)
    check("a genuinely absent licence still says no permission",
          "no permission" in g["why"], g["why"])


def t_the_matrix():
    found = {
        "pdf annotation": [repo("good/pdf", 3000), repo("old/pdf", 900, pushed="2019-01-01T00:00:00Z")],
        "offline sqlite sync": [repo("tiny/sync", 4)],
        "the actual idea": [],
    }
    m = R.matrix({"ok": True, "found": found, "errors": []}, NOW)
    by = {r["capability"]: r for r in m["rows"]}
    check("a solved capability reads ADOPT", by["pdf annotation"]["verdict"] == "ADOPT")
    check("the best candidate is the one shown",
          by["pdf annotation"]["best"]["name"] == "good/pdf", repr(by["pdf annotation"]["best"]))
    check("the rejected candidates are kept",
          len(by["pdf annotation"]["considered"]) == 1,
          "a matrix gets overruled when nobody can see what was considered")
    check("an unsolved capability reads BUILD CUSTOM",
          by["offline sqlite sync"]["verdict"] == "BUILD CUSTOM")
    check("an empty result is BUILD CUSTOM but says it is weak evidence",
          by["the actual idea"]["verdict"] == "BUILD CUSTOM"
          and "weaker statement" in (by["the actual idea"]["note"] or ""),
          repr(by["the actual idea"]))
    check("rows are ordered so the things you need not build come first",
          [r["verdict"] for r in m["rows"]][0] == "ADOPT",
          repr([r["verdict"] for r in m["rows"]]))

    m = R.matrix({"ok": False, "reason": "not approved; nothing was sent"})
    check("an unapproved audit produces no matrix at all", m["ok"] is False, repr(m))
    check("and renders as a refusal, not as an empty result",
          "not approved" in R.render(m), R.render(m))


def t_a_failed_request_is_not_a_clear_result():
    out = {"ok": True, "found": {}, "errors": [{"url": "u", "error": "HTTPError: 403"}]}
    text = R.render(R.matrix(out, NOW))
    check("a failed request says the capability is unaudited",
          "unaudited, not clear" in text or "No capabilities" in text, text)


def t_repo_age_is_measured_in_utc_not_the_machines_timezone():
    # GitHub's `pushed_at` is UTC and says so with its trailing Z.
    # time.mktime reads a struct_time as LOCAL time, so the age came out
    # shifted by the machine's own UTC offset - and NEGATIVE for anything
    # pushed within that offset. calendar.timegm reads it as what it is.
    import calendar, os, time as _time
    stamp = "2026-01-01T00:00:00Z"
    now = calendar.timegm(_time.strptime("2026-01-11T00:00:00", "%Y-%m-%dT%H:%M:%S"))

    def age_in(tz):
        old = os.environ.get("TZ")
        os.environ["TZ"] = tz
        try:
            _time.tzset()
            return R._age_days(stamp, now=now)
        finally:
            if old is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old
            _time.tzset()

    ages = {tz: age_in(tz) for tz in
            ("UTC", "America/Los_Angeles", "Asia/Tokyo", "Europe/London")}
    check("the same timestamp is the same age everywhere",
          len({round(a, 6) for a in ages.values()}) == 1, repr(ages))
    check("and it is the right age", abs(ages["UTC"] - 10.0) < 1e-6, repr(ages))


def t_a_repo_pushed_moments_ago_is_never_negative_years_old():
    # The visible face of the same bug, in the timezone that shows it worst.
    import calendar, os, time as _time
    now = calendar.timegm(_time.strptime("2026-01-01T12:00:00", "%Y-%m-%dT%H:%M:%S"))
    old = os.environ.get("TZ")
    os.environ["TZ"] = "Asia/Tokyo"      # UTC+9
    try:
        _time.tzset()
        age = R._age_days("2026-01-01T09:00:00Z", now=now)
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        _time.tzset()
    check("a repo pushed three hours ago is not in the future",
          age is not None and age >= 0, repr(age))
    check("and it is three hours old", abs(age - 0.125) < 1e-6, repr(age))


if __name__ == "__main__":
    for fn in (t_planning_touches_nothing, t_the_card_prints_the_whole_request,
               t_run_refuses_without_approval,
               t_authenticated_requests_are_opt_in_and_disclosed,
               t_grading, t_the_matrix,
               t_a_failed_request_is_not_a_clear_result,
               t_repo_age_is_measured_in_utc_not_the_machines_timezone,
               t_a_repo_pushed_moments_ago_is_never_negative_years_old):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
