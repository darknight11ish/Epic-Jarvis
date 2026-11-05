"""The quote feature (2026-11-05): a local public-domain corpus, a `quote` kind
on the one scheduler, and the model-free "send me a quote" path.

What this proves, in the order it checks it:

  - the corpus itself: every entry is public domain (a work published in or
    before 1929), carries its licence, its author, its work and its year, no
    two entries are the same words, and not one of them carries a Gutenberg
    header, footer, licence paragraph or trademark reference;
  - the loader REFUSES a bad entry - a missing author, a licence it does not
    allow, a work too new to be public domain, a duplicate, a Gutenberg mark -
    rather than serving an unattributable quote;
  - the picker: `(day * STEP + OFFSET) % SIZE` with `math.gcd(STEP, SIZE) == 1`,
    so day by day it sees all SIZE quotes exactly once before any repeats, with
    no state file; the same day gives the same quote, and reading one writes
    nothing;
  - the fast path: "send me a quote", "give me a quote", "quote of the day" and
    "daily quote" answer word for word from that corpus, with no model - and
    the phrases that merely contain the word "quote" ("quote the last email")
    do not;
  - the kind: registered through the scheduler's own register_kind, listed in
    Coming up, repeatable, with a REPEATING quote raising ONE `schedule_repeat`
    card that lists the next three times, and a one-off raising none;
  - firing: ONE state:"fired" event whose `text` is that firing's quote and
    attribution - the words change from one firing to the next, and the job
    itself has no words of its own;
  - the two-file rule: the module and the corpus are the same bytes in
    `backend/` and `jarvis-backend/`, the module is in SHIPPED, and the corpus
    is in the BESIDE table the base is re-taken from.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-quotes-"))
# Before anything imports jarvis_framework: its CONFIG_DIR is read once.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_SCHEDULE_DB"] = str(_TMP / "schedule.db")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_quotes.py", "jarvis_schedule.py", "jarvis_quick.py")

if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_schedule as S  # noqa: E402
import jarvis_quotes as Q  # noqa: E402
import jarvis_quick as K  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class Verdict:
    def __init__(self, allowed, tier, outcome):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome


def local(y, mo, d, hh, mm):
    return S.wall_to_epoch(y, mo, d, hh, mm)


class World:
    """A scheduler with a hand-moved clock, a gate that records, the bus
    captured. Nothing opens a socket and nothing needs a model."""

    def __init__(self, t, *, answer="approved", tier="ask", name="w"):
        self.clock = Clock(t)
        self.events, self.cards = [], []
        self.answer, self.tier = answer, tier
        path = _TMP / f"{name}-{len(os.listdir(_TMP))}.db"
        self.s = S.Scheduler(path, clock=self.clock, gate=self.gate, tier_of=lambda a: self.tier,
                             spawn=lambda fn: fn(), publish=lambda k, d: self.events.append((k, d)))

    def gate(self, action, detail, prompt):
        self.cards.append((action, detail, prompt))
        if self.answer == "approved":
            return Verdict(True, "ask", "approved")
        return Verdict(False, "ask", self.answer)

    def fired(self):
        return [d for k, d in self.events if k == "schedule" and d.get("state") == "fired"]


# --------------------------------------------------------------------------
#   The corpus
# --------------------------------------------------------------------------

def t_the_corpus_is_public_domain_and_attributed():
    rows = Q.CORPUS
    check("the corpus has at least 50 quotes", len(rows) >= 50, f"{len(rows)} quotes")
    fields = set(Q.FIELDS)
    bad_fields = [r for r in rows if set(r) != fields]
    check("every quote has exactly the six fields it needs", not bad_fields, str(bad_fields[:2]))
    missing = [r for r in rows if not all(str(r.get(k) or "").strip() for k in Q.FIELDS[:5])]
    check("every quote names its words, author, work, source and licence", not missing,
          str(missing[:2]))
    licences = sorted({r["licence"] for r in rows})
    check("every licence is one of the two this file allows", set(licences) <= Q.LICENCES,
          str(licences))
    too_new = sorted({r["year"] for r in rows if r["year"] > Q.MAX_YEAR})
    check(f"every work is public domain (published {Q.MAX_YEAR} or earlier)", not too_new,
          str(too_new))
    schemes = sorted({r["source_id"].split(":", 1)[0] for r in rows})
    check("every source is one of the documented public-domain ones",
          set(schemes) <= set(Q.SOURCES), str(schemes))
    check("the corpus carries no Gutenberg header, footer, licence or trademark reference",
          not [r for r in rows if any(m in Q._clean(r["text"]).lower() for m in Q.GUTENBERG_MARKS)])
    folded = [Q._clean(r["text"]).lower() for r in rows]
    check("no two quotes are the same words", len(set(folded)) == len(folded),
          f"{len(set(folded))} distinct of {len(folded)}")
    years = sorted({r["work"] for r in rows if r["year"] < 1600})
    check("... and the oldest work in it is still properly attributed", bool(years), str(years))
    raw = (HERE / Q.CORPUS_NAME).read_text(encoding="utf-8")
    check("the corpus FILE itself carries no Gutenberg mark",
          not any(m in raw.lower() for m in Q.GUTENBERG_MARKS))


def t_the_loader_refuses_an_entry_it_cannot_use():
    good = dict(Q.CORPUS[0])

    def refused(entry, why):
        where = _TMP / f"bad-{len(os.listdir(_TMP))}.json"
        where.write_text(json.dumps({"quotes": [entry]}), encoding="utf-8")
        try:
            Q.load(where)
        except ValueError as exc:
            return why in str(exc)
        return False

    check("a quote with no author is refused at load time",
          refused({k: v for k, v in good.items() if k != "author"}, "missing author"))
    check("a licence this file does not allow is refused",
          refused(dict(good, licence="all-rights-reserved"), "not one of"))
    check("a work too new to be public domain is refused",
          refused(dict(good, year=Q.MAX_YEAR + 1), "public-domain year"))
    check("a source that is not documented is refused",
          refused(dict(good, source_id="wikiquote:something"), "source_id must be"))
    where = _TMP / "dupe.json"
    where.write_text(json.dumps({"quotes": [good, dict(good)]}), encoding="utf-8")
    try:
        Q.load(where)
        duped = ""
    except ValueError as exc:
        duped = str(exc)
    check("a second copy of the same words is refused", "already" in duped, duped)
    check("a Gutenberg licence line left in the words is refused",
          refused(dict(good, text=good["text"] + " Project Gutenberg-tm"),
                  "still carry"))


# --------------------------------------------------------------------------
#   The picker
# --------------------------------------------------------------------------

def t_the_picker_visits_every_quote_before_it_repeats():
    check("the step shares no factor with the corpus size",
          math.gcd(Q.STEP, Q.SIZE) == 1, f"gcd({Q.STEP}, {Q.SIZE})")
    seen = [Q.CORPUS.index(Q.pick(Q.day_index(0) + i)) for i in range(Q.SIZE)]
    check(f"{Q.SIZE} days in a row see every quote exactly once", len(set(seen)) == Q.SIZE
          and sorted(seen) == list(range(Q.SIZE)), f"{len(set(seen))} of {Q.SIZE}")
    check("... so the day after the full cycle is the first quote again",
          Q.pick(1000) == Q.pick(1000 + Q.SIZE))


def t_the_same_day_gives_the_same_quote_and_writes_nothing():
    t = local(2026, 11, 5, 9, 0)
    a, b = Q.for_now(t), Q.for_now(t + 3600)
    check("the same day gives the same quote, morning or afternoon", a == b, f"{a} != {b}")
    check("... and the next day gives a different one", Q.for_now(t + 86400) != a)
    line = Q.line(a)
    check("the line carries the words, the author, the work and the year",
          line.startswith(a["text"]) and a["author"] in line and a["work"] in line
          and f"({a['year']})" in line, line)
    check("the attribution reads \"Author - Work (Year)\"", Q.byline(a) ==
          f"{a['author']} - {a['work']} ({a['year']})")
    before = {p.name: p.stat().st_mtime_ns for p in HERE.glob("*.json")}
    for i in range(50):
        Q.for_now(t + i * 86400)
    after = {p.name: p.stat().st_mtime_ns for p in HERE.glob("*.json")}
    check("picking 50 quotes writes no file at all", before == after)


# --------------------------------------------------------------------------
#   The fast path
# --------------------------------------------------------------------------

def t_the_fast_path_answers_from_the_corpus_with_no_model():
    now = local(2026, 11, 5, 9, 0)
    want = Q.today_line(now)
    for words in ("send me a quote", "give me a quote", "quote of the day", "daily quote",
                  "send me today's quote", "give me a daily quote", "read me a quote"):
        got = K.match(words, now)
        check(f"{words!r} is the quote fast path",
              got is not None and got.name == "quote_now", str(got))
        res = K.answer(words, now=now)
        check(f"... and answers the corpus's own words, with no model",
              res is not None and res.reply == want and not res.read and not res.made,
              "" if res is None else res.reply)
    # No model is reachable from this path at all: these are `Result`s, which is
    # what the backend returns INSTEAD of asking a model.
    check("the answer is a finished Result, so nothing is sent to a model",
          isinstance(K.answer("send me a quote", now=now), K.Result))


def t_phrases_that_merely_contain_the_word_do_not_hit_it():
    now = local(2026, 11, 5, 9, 0)
    for words in ("quote the last email", "quote this in your answer",
                  "quote the paragraph above", "put that in quotes",
                  "quote me a price for the job", "the quote check flagged it"):
        check(f"{words!r} is NOT the quote feature", K.match(words, now) is None,
              str(K.match(words, now)))


def t_a_repeating_quote_is_asked_for_with_one_sentence():
    now = local(2026, 11, 5, 9, 0)
    got = K.match("send me a quote every morning at 8", now)
    check("a repeating quote is understood as one sentence",
          got is not None and got.name == "quote_set" and got.f["when"].rule is not None,
          str(got))
    one = K.match("give me a quote tomorrow at 6", now)
    check("a one-off quote is understood too",
          one is not None and one.name == "quote_set" and one.f["when"].rule is None,
          str(one))
    check("when is my quote is a question, not a change",
          (lambda i: i is not None and i.name == "quote_list")(K.match("when is my quote", now)))
    check("stop my quote stops one",
          (lambda i: i is not None and i.name == "quote_cancel")(K.match("stop my quote", now)))


# --------------------------------------------------------------------------
#   The schedule kind
# --------------------------------------------------------------------------

def t_the_kind_is_registered_the_repo_s_way():
    k = S.KINDS.get(Q.KIND)
    check("quote is a kind of job on the one scheduler",
          k is not None and k.name == Q.KIND, str(k))
    check("... listed in Coming up, repeatable, with no words of its own",
          k is not None and k.owner_listed and k.repeatable and not k.has_text
          and not k.plain_repeat, str(k and (k.owner_listed, k.repeatable, k.has_text)))
    check("... and says this firing's words, not the job's",
          k is not None and k.say is not None and k.say("job") == Q.today_line())
    check("get() imports the module before the loop first runs",
          "jarvis_quotes" in S.KIND_MODULES)
    check("... the lock-screen words say only that a quote is ready",
          k is not None and k.lock_screen == Q.LOCK_SCREEN
          and "quote" in k.lock_screen.lower() and Q.CORPUS[0]["text"] not in k.lock_screen)


def t_a_repeating_quote_raises_one_card_with_the_next_three_times():
    w = World(local(2026, 11, 5, 20, 0), name="card")
    j = w.s.add_repeat(Q.KIND, {"every": "day", "at": "07:00"})
    check("a repeating quote waits for ONE card", j["state"] == "waiting" and len(w.cards) == 1,
          f"{j.get('state')}, {len(w.cards)} card(s)")
    action, detail, prompt = w.cards[0]
    check("... raised by the scheduler's own schedule_repeat action",
          action == "schedule_repeat" and "quote" in str(detail.get("what") or ""), str(detail))
    check("... which lists the next three fire times",
          prompt.count(" at 07:00") >= 3
          and "Friday 6 November at 07:00" in prompt
          and "Saturday 7 November at 07:00" in prompt
          and "Sunday 8 November at 07:00" in prompt, prompt)
    check("... and says where the words come from and that nothing is sent",
          "public-domain" in prompt and "Nothing is sent anywhere" in prompt
          and "no AI model" in prompt, prompt)
    check("a quote job has no words of its own", w.s.job(j["id"])["text"] == "")
    try:
        w.s.add_repeat(Q.KIND, {"every": "day", "at": "07:00"})
        dup = None
    except ValueError as exc:
        dup = str(exc)
    check("the same repeating quote twice is refused, and says why",
          dup is not None and "already set up" in dup, dup)
    n = len(w.cards)
    one = w.s.add_at(Q.KIND, local(2026, 11, 5, 21, 0))
    check("a one-off quote needs no card, and is set up at once",
          len(w.cards) == n and one["state"] == "active", str(one.get("state")))


def t_firing_sends_one_event_whose_words_are_that_firing_s_quote():
    w = World(local(2026, 11, 5, 20, 0), name="fire")
    S._SCHED = w.s
    due = local(2026, 11, 6, 7, 0)
    job = w.s.add_at(Q.KIND, due)
    check("nothing goes off early", w.s.tick() == [])
    w.clock.t = due + 1
    went = w.s.tick()
    events = w.fired()
    check("it goes off once", went == [job["id"]] and len(events) == 1,
          f"{went}, {len(events)} fired event(s)")
    ev = events[0]
    check("the event is the scheduler's ordinary state:\"fired\", with the kind",
          ev.get("id") == job["id"] and ev.get("kind") == Q.KIND
          and ev.get("state") == "fired", str(ev))
    check("its body carries the quote and \"Author - Work (Year)\"",
          ev.get("text") == Q.today_line(w.clock.t), str(ev.get("text")))
    check("... and that is the quote of the day it went off on",
          Q.today_line(w.clock.t) == Q.line(Q.for_now(w.clock.t)))
    # The NEXT day's firing of a job set up today says the NEXT day's quote:
    # the words are the firing's, not the job's (a repeating job keeps its row).
    w2 = World(local(2026, 11, 6, 20, 0), name="fire2")
    S._SCHED = w2.s
    due2 = local(2026, 11, 7, 7, 0)
    w2.s.add_at(Q.KIND, due2)
    w2.clock.t = due2 + 1
    w2.s.tick()
    check("a later firing says the later day's quote, not the first one's",
          w2.fired()[0].get("text") == Q.today_line(due2 + 1) != Q.today_line(w.clock.t),
          str(w2.fired()[0].get("text")))
    S._SCHED = None
    check("nothing about a firing is written into the corpus", Q.pick(0) == Q.pick(0))


# --------------------------------------------------------------------------
#   The two-file rule, and both apps
# --------------------------------------------------------------------------

def t_the_module_and_the_corpus_travel_together():
    import _where
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "gen_base_from_backend", REPO / "tools" / "gen_base_from_backend.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    check("the module is on the SHIPPED list",
          "jarvis_quotes.py" in _where.SHIPPED)
    beside = [n for n, _w, _y in gen.BESIDE]
    check("the corpus is in the BESIDE table the base is re-taken from",
          Q.CORPUS_NAME in beside, str(beside))
    for leaf in ("jarvis_quotes.py", Q.CORPUS_NAME):
        ours, theirs = HERE / leaf, REPO / "jarvis-backend" / leaf
        check(f"jarvis-backend/{leaf} is this repository's own bytes",
              theirs.is_file() and theirs.read_bytes() == ours.read_bytes(),
              "missing or different")
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8", errors="replace")
    check("scripts/apply-patches.ps1 ships the module too",
          "'jarvis_quotes.py'" in ps1)
    check("... and the two apps name the same kind and title",
          "quote" in (REPO / "jarvis-desktop" / "src" / "coming-up.js").read_text(encoding="utf-8")
          and "Quote of the day" in (REPO / "jarvis-desktop" / "src" / "coming-up.js")
          .read_text(encoding="utf-8"))


def main():
    orig_tz = os.environ.get("TZ")
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:  # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        if orig_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = orig_tz
        if hasattr(time, "tzset"):
            time.tzset()
        if S._SCHED is not None:
            S._SCHED.stop()
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
