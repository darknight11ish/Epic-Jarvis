"""The ten rebuilt modules: does each one still do what its callers need?

WHY THIS SUITE IS DIFFERENT FROM THE OTHERS IN THIS DIRECTORY

The rest of `backend/test_*.py` proves a PATCH does what it claims. This one
proves a RECONSTRUCTION matches a contract, which is a weaker thing and has to
be tested harder: there is no original to diff against. Ten modules were
rebuilt from a config file, a spec document, and fifty-six call sites, after
the originals were found to exist nowhere - not on the machine, not in any
installer, not in a 104 MB export of every conversation.

So every test here is tied to EVIDENCE, not to an opinion about how the module
should behave. Each one says where its expectation comes from: a surviving
test's assertion, a line in JARVIS-API.md, a comment in jarvis-framework.toml,
or a fragment of verbatim original source quoted in one of the patches.

THE THREE BUGS THAT PROMPTED HALF OF THESE

Written down because all three passed a careful reading and were caught only by
running something:

  1. sqlite-vec was loaded on the connection that CREATED the vec0 table and on
     no other. Every later connection raised "no such module: vec0" inside an
     `except: continue`, so facts were stored, never embedded, never findable
     by meaning - while status() reported "vector_search": true throughout.
  2. Bus.since() returned a list. test_jobs.py unpacks it as `got, _ =`.
  3. Embedder.embed() took a list of clips. jarvis_voice's real shape is one
     clip in, one vector out, and with the wrong signature the surviving
     test's stub was never called at all.

Run it beside the backend:

    $env:JARVIS_BACKEND = "C:\\...\\Desktop program"; python backend\\test_rebuilt.py
"""
import json
import math
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _where import BACKEND, REPO, explain, missing  # noqa: E402


def _words_of(text):
    import jarvis_memory as _m
    return _m._words(text)

REBUILT = Path(__file__).resolve().parent / "rebuilt"

# The rebuilt modules are the ones under test, so they come FIRST on the path -
# ahead of any copy that may be sitting in the backend folder. Testing whichever
# copy happened to be found first is how you get a green suite for code nobody
# is running.
sys.path.insert(0, str(REBUILT))

# A hash embedder, so no model download is needed and results are deterministic.
os.environ.setdefault("JARVIS_NO_EMBED", "1")

_TMP = tempfile.mkdtemp(prefix="jarvis-rebuilt-")
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", os.path.join(_TMP, "cfg"))

# The real 979-line config, if it is anywhere to be found. Several tests assert
# against values in it; they skip rather than invent one.
_CONFIG = None
for _c in (BACKEND / "jarvis-framework.toml",
           BACKEND.parent / "jarvis-framework.toml",
           REPO / "backend" / "jarvis-framework.toml"):
    if _c.is_file():
        _CONFIG = _c
        os.environ["JARVIS_FRAMEWORK_TOML"] = str(_c)
        break

import jarvis_framework as FW      # noqa: E402
import jarvis_events as EV         # noqa: E402
import jarvis_memory as MEM        # noqa: E402
import jarvis_recall as RC         # noqa: E402
import jarvis_router as RT         # noqa: E402
import jarvis_voice as VO          # noqa: E402
import jarvis_power as PW          # noqa: E402
import jarvis_compute as CP        # noqa: E402
import jarvis_sleep as SL          # noqa: E402
import jarvis_initiative as IN     # noqa: E402


# ==========================================================================
#   jarvis_framework
# ==========================================================================

class Framework(unittest.TestCase):

    def test_the_surviving_assertion(self):
        """test_jobs.py:253 asserts this exact thing, and it is the only
        behaviour of action_tier that is KNOWN rather than inferred:

            self.assertEqual(fw.action_tier("web_research"), "auto")
        """
        if _CONFIG is None:
            self.skipTest("jarvis-framework.toml not found; " + explain())
        self.assertEqual(FW.action_tier("web_research"), "auto")

    def test_an_unclassified_action_fails_closed(self):
        """jarvis-framework.toml's own words: "an action nobody classified is
        not thereby safe." Both the config default and the code default are
        "ask", so the fallback chain cannot bottom out in permission."""
        self.assertEqual(FW.action_tier("no_such_action_anywhere"), "ask")
        self.assertEqual(FW.action_tier(""), "ask")
        self.assertEqual(FW.action_tier("../../etc/passwd"), "ask")

    def test_an_unclassified_action_cannot_be_configured_permissive(self):
        """"There is no approve-all anywhere in Jarvis; do not build one" is
        a hard product constraint, and [autonomy].unknown_action_tier used to
        be one config edit away from being exactly that: "auto" or "notify"
        were honoured after a single stderr line, on the reasoning that a
        module outside this repository enforces a ceiling. Nothing in this
        repository can verify that, so nothing here may return anything more
        permissive than "ask" for an action nobody classified."""
        orig = FW.load_framework
        for permissive in ("auto", "notify", "AUTO", " Auto "):
            FW.load_framework = lambda *a, v=permissive, **k: {
                "autonomy": {"unknown_action_tier": v}}
            try:
                self.assertEqual(FW.unknown_action_tier(), "ask",
                                 f"{permissive!r} must not be honoured")
            finally:
                FW.load_framework = orig
        # "never" is stricter than the default, not more permissive - trust
        # it. Same for the shipped default itself.
        FW.load_framework = lambda *a, **k: {
            "autonomy": {"unknown_action_tier": "never"}}
        try:
            self.assertEqual(FW.unknown_action_tier(), "never")
        finally:
            FW.load_framework = orig

    def test_a_typod_tier_is_not_permission(self):
        """A tier value that is not one of the four must be treated as
        unclassified. Reading "atuo" as anything but "ask" would turn a typo
        into an unattended action."""
        orig = FW.load_framework

        def fake(*a, **k):
            d = orig(*a, **k)
            d.setdefault("autonomy", {}).setdefault("tiers", {})["typo_action"] = "atuo"
            return d
        FW.load_framework = fake
        try:
            self.assertEqual(FW.action_tier("typo_action"), "ask")
        finally:
            FW.load_framework = orig

    def test_mutating_the_returned_config_cannot_poison_the_cache(self):
        """The surviving suites wrap load_framework and MUTATE its result:

            d = _orig_load(*a, **k)
            d.setdefault("logging", {})["log_directory"] = _TMP

        If a cached object were handed out, that write would leak into every
        module loaded afterwards - a test quietly reconfiguring the process.
        """
        a = FW.load_framework()
        a.setdefault("logging", {})["log_directory"] = "/tmp/poison-me"
        b = FW.load_framework()
        self.assertNotEqual(b.get("logging", {}).get("log_directory"),
                            "/tmp/poison-me")

    def test_load_framework_takes_the_arguments_the_wrappers_forward(self):
        """Those wrappers are `def _patched_load(*a, **k)` calling
        `_orig_load(*a, **k)`. A signature of () breaks all of them."""
        FW.load_framework()
        FW.load_framework(1, 2, three=3)

    def test_a_broken_config_does_not_stop_the_backend_booting(self):
        """Fifteen modules import this at startup. An exception here means the
        whole backend fails to start over a stray character, with a traceback
        pointing at whichever module imported first."""
        bad = Path(_TMP) / "broken.toml"
        bad.write_text("this is [not valid = toml\n", encoding="utf-8")
        keep = os.environ.get("JARVIS_FRAMEWORK_TOML")
        os.environ["JARVIS_FRAMEWORK_TOML"] = str(bad)
        try:
            FW.reload_framework()
            self.assertEqual(FW.load_framework(), {})
            self.assertEqual(FW.action_tier("web_research"), "ask")  # fails closed
        finally:
            if keep:
                os.environ["JARVIS_FRAMEWORK_TOML"] = keep
            else:
                os.environ.pop("JARVIS_FRAMEWORK_TOML", None)
            FW.reload_framework()

    def test_audit_log_survives_an_unserialisable_value(self):
        d = Path(_TMP) / "logs1"
        orig = FW.load_framework
        FW.load_framework = lambda *a, **k: {"logging": {"enabled": True,
                                                         "log_directory": str(d)}}
        try:
            self.assertTrue(FW.audit_log("weird", {"p": Path("/x"), "s": {1, 2}}))
            written = "".join(f.read_text() for f in d.glob("*.jsonl"))
            self.assertIn("weird", written)
            json.loads(written.strip().splitlines()[-1])   # still one valid line
        finally:
            FW.load_framework = orig

    def test_audit_log_lines_are_never_interleaved(self):
        """One JSON line each, from many threads. A torn line is an audit
        entry that cannot be parsed, which is the same as not having it."""
        d = Path(_TMP) / "logs2"
        orig = FW.load_framework
        FW.load_framework = lambda *a, **k: {"logging": {"enabled": True,
                                                         "log_directory": str(d)}}
        try:
            def spam(n):
                for i in range(40):
                    FW.audit_log("gate.asked", {"who": n, "i": i, "pad": "x" * 200})
            ts = [threading.Thread(target=spam, args=(n,)) for n in range(8)]
            [t.start() for t in ts]; [t.join() for t in ts]
            lines = [l for f in d.glob("*.jsonl")
                     for l in f.read_text().splitlines() if l.strip()]
            self.assertEqual(len(lines), 320)
            for l in lines:
                json.loads(l)
        finally:
            FW.load_framework = orig


# ==========================================================================
#   jarvis_events
# ==========================================================================

class Events(unittest.TestCase):

    def test_since_returns_a_pair(self):
        """test_jobs.py:807 does `got, _ = self.bus.since(0)`. Returning a
        list makes that ValueError: too many values to unpack."""
        b = EV.Bus(size=8)
        b.publish("job", {"state": "running"})
        got, cursor = b.since(0)
        self.assertEqual(len(got), 1)
        self.assertEqual(cursor, got[-1].id)

    def test_since_gives_a_cursor_even_when_nothing_is_new(self):
        """Deriving the cursor from out[-1].id breaks on the empty result,
        which is the common case on a quiet bus."""
        b = EV.Bus(size=8)
        b.publish("power", {"mode": "active"})
        got, cursor = b.since(99)
        self.assertEqual(got, [])
        self.assertIsInstance(cursor, int)

    def test_note_is_quiet_until_something_changes(self):
        """Pollers run every second. Without dedupe every subscriber gets
        86,400 identical events a day, which is a phone battery."""
        b = EV.Bus(size=8)
        b.note("approvals", ["a1"], "approval")          # baseline, silent
        self.assertIsNone(b.note("approvals", ["a1"], "approval"))
        self.assertIsNotNone(b.note("approvals", ["a1", "a2"], "approval"))

    def test_the_first_observation_is_a_baseline_not_an_event(self):
        """A key never seen has not CHANGED, and this is a change feed.

        test_events_pump.py:43 states it as the contract - "the first tick is
        a baseline, not an event". Publishing the first sighting meant every
        start of the pump fired approval, power and proposal events describing
        queues that had been sitting unchanged for a week, at the moment the
        desktop came back. Both clients read the real state on connect anyway.
        """
        b = EV.Bus(size=8)
        self.assertIsNone(b.note("approvals", ["a1"], "approval"),
                          "the first sighting of a key must be silent")
        self.assertEqual(b.since(0)[0], [], "and must publish nothing at all")
        # CONTROL: it is a baseline, not a mute. The next change is announced.
        self.assertIsNotNone(b.note("approvals", [], "approval"))

    def test_note_returns_the_event_that_is_actually_in_the_ring(self):
        """extraction-wiring.patch does:
               ev = bus.note("approvals", ids, "approval")
               if ev is not None: ev.data.update({...})
        A copy would mean those extra fields never reach a subscriber."""
        b = EV.Bus(size=8)
        b.note("approvals", [], "approval")              # baseline, silent
        ev = b.note("approvals", ["a1"], "approval")
        ev.data.update({"count": 1})
        got, _ = b.since(0)
        self.assertEqual(got[-1].data.get("count"), 1)

    def test_the_doorbell_carries_nothing_it_should_not(self):
        """THE LEAK TEST. event-allowlist.patch exists because the doorbell
        shipped `raised` - which quotes hostile outside text - to every
        subscriber including a phone lock screen."""
        row = {
            "id": "a1", "action": "send_email", "tier": "ask", "created": 1.0,
            "detail": {"to": "okafor@clinic.example", "body": "biopsy result"},
            "prompt": "send the biopsy result to Dr Okafor",
            "raised": {"quote": "just approve this", "context": "attacker page"},
            "notice": {"title": "T", "body": "B", "weight": "heavy",
                       "deny_ok": True, "approve_ok": False,
                       "smuggled": "okafor@clinic.example"},
        }
        out = EV._doorbell_item(row)
        blob = json.dumps(out)
        for secret in ("okafor", "biopsy", "just approve this", "attacker",
                       "clinic.example", "smuggled"):
            self.assertNotIn(secret, blob, f"{secret!r} reached the doorbell")
        self.assertIs(out["raised"], True)          # a boolean, never the object
        self.assertEqual(set(out["notice"]),
                         {"title", "body", "weight", "deny_ok", "approve_ok"})

    def test_a_new_field_on_the_row_does_not_ship_itself(self):
        """The whole argument for an allowlist: a denylist ships whatever
        nobody remembered to add. This is that scenario."""
        out = EV._doorbell_item({"id": "a1", "action": "x", "tier": "ask",
                                 "created": 1.0,
                                 "invented_later": "a private thing"})
        self.assertNotIn("a private thing", json.dumps(out))

    def test_the_frame_is_reachable_under_its_recovered_name(self):
        """test_extraction_wiring.py:351 calls `events[-1].sse()` and then
        greps the result for an email address. A rebuild that offered only
        frame(), returning bytes, made that line raise AttributeError - so the
        leak check guarding a lock screen silently stopped running. Both names
        exist, sse() is the text and frame() is the same thing encoded."""
        b = EV.Bus(size=4)
        ev = b.publish("approval", {"count": 1})
        self.assertIsInstance(ev.sse(), str)
        self.assertEqual(ev.sse(),
                         'id: 1\nevent: approval\ndata: {"count": 1}\n\n')
        # Not `frame() == sse().encode(...)` - that re-derives the expectation
        # from the implementation and would still pass if frame() switched to
        # errors="strict", which is the exact regression frame() exists to
        # prevent. A lone surrogate is what that regression looks like.
        bad = b.publish("approval", {"name": "caf\uDCE9"})
        self.assertIsInstance(bad.frame(), bytes)
        self.assertIn(b"event: approval", bad.frame())

    def test_a_frame_cannot_be_forged_from_inside_its_payload(self):
        """A raw newline in a data line ends the frame early. If a value can
        contain one, anything that can influence a value can forge an event."""
        ev = EV.Event(1, "approval",
                      {"t": "x\n\nid: 999\nevent: forged\ndata: {}\n\n"})
        raw = ev.sse()
        # Count real SSE FIELD LINES, not substrings. The escaped \n inside
        # the JSON payload is a literal backslash-n on the wire, so "event:"
        # appears twice as text and once as a field - and it is the field that
        # decides whether a frame was forged.
        fields = [l.split(":", 1)[0] for l in raw.split("\n") if l.strip()]
        self.assertEqual(fields, ["id", "event", "data"])
        self.assertEqual(raw.count("\n\n"), 1)
        self.assertTrue(raw.endswith("\n\n"))

    def test_a_nonsense_resume_id_does_not_close_the_stream(self):
        """last_id comes from a header or a query string, so it is whatever
        the client sent. A raise here looks exactly like the server being
        down."""
        for bad in ("", None, "abc", "-5", "9" * 40, "1.5", "  7  "):
            gen = EV.stream(bad, bus=EV.Bus(size=8))
            self.assertTrue(next(gen).startswith(b"retry:"))
            self.assertIn(b"event: hello", next(gen))
            gen.close()

    def test_a_stale_client_is_told_so_and_not_replayed(self):
        """JARVIS-API.md rule 2: stale means "you are NOT caught up. Re-fetch
        everything and do not replay.\""""
        b = EV.Bus(size=8)
        for i in range(20):
            b.publish("job", {"i": i})
        gen = EV.stream(1, bus=b)
        next(gen)
        hello = json.loads(next(gen).decode().split("data: ", 1)[1])
        self.assertTrue(hello["stale"])
        self.assertEqual(hello["latest"], b.latest)
        gen.close()

    def test_a_caught_up_client_is_not_told_it_is_stale(self):
        b = EV.Bus(size=64)
        for i in range(5):
            b.publish("job", {"i": i})
        gen = EV.stream(b.latest, bus=b)
        next(gen)
        hello = json.loads(next(gen).decode().split("data: ", 1)[1])
        self.assertFalse(hello["stale"])
        gen.close()

    def test_ids_are_unique_under_concurrent_publishers(self):
        b = EV.Bus(size=4096)

        def spam():
            for _ in range(100):
                b.publish("job", {})
        ts = [threading.Thread(target=spam) for _ in range(8)]
        [t.start() for t in ts]; [t.join() for t in ts]
        got, _ = b.since(0)
        self.assertEqual(len(got), 800)
        self.assertEqual(len({e.id for e in got}), 800)

    def test_a_report_is_not_swallowed_as_a_baseline(self):
        """announce_first. The baseline rule is for POLLERS, which ask "has
        the world moved?". set_activity() and Notebook.file() are reporting
        that something just happened, and for them the first call after a
        restart is the most important one there is - the first thing the
        watcher notices, the first "thinking" of the first turn. Without the
        flag the only frame a client saw for that whole turn was the "idle"
        that followed it."""
        b = EV.Bus(size=8)
        self.assertIsNotNone(b.note("activity", {"state": "thinking"},
                                    "activity", announce_first=True))
        # Still deduplicated: it is note(), not publish().
        self.assertIsNone(b.note("activity", {"state": "thinking"},
                                 "activity", announce_first=True))

    def test_set_activity_reports_the_first_turn(self):
        """The live caller, not the mechanism. _ACTIVITY starts at "idle"."""
        EV.BUS.forget()
        before = EV.BUS.latest
        EV.set_activity("thinking", "answering")
        got = [e for e in EV.BUS.since(before)[0] if e.kind == "activity"]
        self.assertEqual([e.data["value"]["state"] for e in got], ["thinking"])

    def test_forget_makes_the_next_note_fire(self):
        """Its name is the contract. Deleting the key instead made it a
        baseline, so forget() followed by note() published nothing at all -
        the opposite of what it says."""
        b = EV.Bus(size=8)
        b.note("power", "active", "power")          # baseline
        self.assertIsNone(b.note("power", "active", "power"))
        b.forget("power")
        self.assertIsNotNone(b.note("power", "active", "power"),
                             "forget() must re-arm, not re-baseline")

    def test_the_proposal_doorbell_is_keyed_on_the_ids(self):
        """Keyed on the COUNT, a queue that changes without changing size is
        silent for ever: the owner reviews proposal 7 while the extractor
        queues 8, the count stays 1, and the new one never rings."""
        import types as _t
        x = _t.ModuleType("jarvis_extract")
        x.pending = lambda: [{"id": 7}]
        sys.modules["jarvis_extract"] = x
        b = EV.Bus(size=8)
        EV._poll_proposals(b)                       # baseline
        x.pending = lambda: [{"id": 9}]             # 7 reviewed, 9 arrived
        EV._poll_proposals(b)
        got = [e for e in b.since(0)[0] if e.kind == "proposal"]
        self.assertEqual(len(got), 1, "a same-size change must still ring")
        self.assertEqual(got[0].data["value"], [9])
        self.assertEqual(got[0].data["count"], 1)
        blob = got[0].sse()
        self.assertNotIn("text", blob, "the doorbell carries ids, never text")

    def test_a_poller_that_throws_does_not_stop_the_others(self):
        b = EV.Bus(size=16)
        calls = []

        def boom(_bus):
            raise RuntimeError("no")

        def fine(_bus):
            calls.append(1)

        keep = EV.POLLERS[:]
        EV.POLLERS[:] = [boom, fine]
        try:
            p = EV.Pump(bus=b)
            p.tick()
            self.assertEqual(calls, [1])
            self.assertEqual(p.errors, 1)
        finally:
            EV.POLLERS[:] = keep


# ==========================================================================
#   jarvis_memory
# ==========================================================================

class Memory(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="mem-")
        MEM.reset()
        self.s = MEM.MemoryStore(Path(self.dir) / "m.db", MEM.HashEmbedder())

    def test_a_correction_never_retires_an_unrelated_fact(self):
        """THE BUG THIS STORE EXISTS TO PREVENT, measured in
        memory-safety.patch: accepting "Mario drives a 1998 Volvo" retired
        "Mario prefers tabs over spaces in Go"."""
        go = self.s.add("Mario prefers tabs over spaces in Go")
        self.s.add("Mario lives at 12 Oak Street")
        hit = self.s.find_one("Mario drives a 1998 Volvo")
        self.assertNotEqual((hit or {}).get("id"), go)

    def test_a_word_ending_in_ss_is_findable_on_its_own(self):
        """THE BUG, reproduced. `facts_fts` is `tokenize='porter unicode61'`
        and Porter deliberately KEEPS a double s ("address" stems to
        "address"). `_words` strips one trailing s from every token, turning
        the query term into "addres", which Porter then stems to something
        the index does not hold - so every word ending in ss was unfindable
        on its own:

            search("email address")  ->  ['My email address is bob@exam...']
            search("address")        ->  []

        `_fts_terms` feeds the RAW token and lets Porter stem both sides.
        """
        self.s.add("My email address is bob@example.com")
        self.s.add("The class starts at nine")
        self.s.add("My boss is called Dana")
        for term, expect in (("address", "email address"),
                             ("class", "class starts"),
                             ("boss", "boss is called")):
            hits = self.s.search(term, k=3)
            self.assertTrue(any(expect in h["text"] for h in hits),
                            f"search({term!r}) found {[h['text'] for h in hits]}")

    def test_a_plural_still_matches_its_singular(self):
        """CONTROL: dropping the hand-rolled s-stripping must not cost the
        plural matching it was standing in for - Porter does that job, which
        is the whole reason the index is built with it."""
        self.s.add("The class starts at nine")
        hits = self.s.search("classes", k=3)
        self.assertTrue(any("class starts" in h["text"] for h in hits),
                        f"search('classes') found {[h['text'] for h in hits]}")

    def test_fts_terms_still_drops_stopwords(self):
        """CONTROL: the other half of _words' job - keeping "the" and "is"
        out of an OR-query that would otherwise match the whole store - is
        unchanged."""
        self.assertEqual(MEM._fts_terms("what is the address"), {"address"})
        self.assertEqual(MEM._fts_terms("address"), {"address"})
        # And the folding _words does for the OVERLAP test is still there.
        self.assertEqual(MEM._words("Mario's"), {"mario"})

    def test_a_possessive_is_not_a_free_overlap_token(self):
        """`_words` folds "'?s$" and drops single characters. Without that,
        "Mario's" splits into {"mario", "s"} and the bare "s" is shared by
        every fact containing an apostrophe - so one real word plus "s"
        cleared the two-word bar. Measured: find_one("Mario's allergy")
        returned "Mario's editor is Vim", the exact pair the patch names."""
        self.s.add("Mario's editor is Vim")
        self.s.add("Mario drives a 1998 Volvo")
        self.assertNotIn("s", _words_of("Mario's car"))
        for q in ("Mario's allergy", "Mario's car", "Mario's address"):
            self.assertIsNone(self.s.find_one(q), q)

    def test_find_one_returns_none_rather_than_a_guess(self):
        """None means "store the new fact and retire nothing". Two facts that
        disagree can be sorted out later; a deleted allergy cannot."""
        self.s.add("Mario prefers tabs over spaces in Go")
        for vague in ("Mario allergy", "address", "the", "", "his car",
                      "something about Mario"):
            self.assertIsNone(self.s.find_one(vague), f"guessed on {vague!r}")

    def test_find_one_does_find_the_right_one(self):
        """The bar has to be clearable, or corrections never supersede."""
        volvo = self.s.add("Mario drives a 1998 Volvo estate")
        self.s.add("Mario prefers tabs over spaces in Go")
        hit = self.s.find_one("Mario drives a 1998 Volvo")
        # A DICT, not an id: the patched jarvis_extract._accept does
        # target["id"], so an int raised TypeError on the one path that matters.
        self.assertIsInstance(hit, dict)
        self.assertEqual(hit["id"], volvo)

    def test_search_with_k_zero_returns_nothing(self):
        """Recall width zero means recall OFF. The truncation appends and THEN
        checks `len(out) >= k`, so k=0 used to return exactly one fact - into
        a prompt, from the function that decides what private text goes there."""
        self.s.add("Mario takes lisinopril 10mg daily")
        for k in (0, -1, -5):
            self.assertEqual(self.s.search("Mario", k=k), [], f"k={k}")

    def test_superseding_a_missing_fact_is_reported(self):
        """add() returns the new id either way, so a caller that believed it
        filed a correction had nothing to check."""
        self.s.add("a fact about something specific")
        self.s.add("a replacement fact", supersedes=999999)
        self.assertTrue(self.s.last_supersede_failed)

    def test_a_retired_fact_cannot_be_rewritten(self):
        """bitemporal's premise is that a superseded version stays readable as
        it was. Editing one makes "where did I live last year" answer with
        today's words."""
        old = self.s.add("Mario lives at 12 Oak Street")
        self.s.add("Mario lives at 40 Elm Road", supersedes=old)
        self.assertFalse(self.s.edit(old, "rewritten history"))

    def test_a_nan_embedding_never_makes_a_fact_unreachable(self):
        """embedding-guard.patch: a NaN row is unreachable FOREVER, because
        every distance comparison against NaN is false. The fact must stay
        findable by WORDS."""
        class Nan(MEM.HashEmbedder):
            name = "nan-v1"
            def embed(self, texts):
                return [[float("nan")] * self.dim for _ in texts]

        s = MEM.MemoryStore(Path(self.dir) / "nan.db", Nan())
        s.add("Mario is allergic to penicillin")
        hits = s.search("penicillin allergy")
        self.assertTrue(hits, "a NaN embedding made the fact unreachable")
        self.assertEqual(s.status()["unembedded"], 1, "status is not honest")

    def test_an_embedder_that_explodes_does_not_lose_the_fact(self):
        class Boom(MEM.HashEmbedder):
            name = "boom-v1"
            def embed(self, texts):
                raise RuntimeError("model died")

        s = MEM.MemoryStore(Path(self.dir) / "boom.db", Boom())
        s.add("Mario is allergic to penicillin")
        self.assertTrue(s.search("penicillin"))

    def test_backfill_terminates_when_nothing_can_be_embedded(self):
        """Without a progress check this loop is infinite whenever a row
        cannot be embedded - which is exactly what a NaN model causes."""
        class Nan(MEM.HashEmbedder):
            name = "nan2-v1"
            def embed(self, texts):
                return [[float("nan")] * self.dim for _ in texts]

        s = MEM.MemoryStore(Path(self.dir) / "nan2.db", Nan())
        for i in range(5):
            s.add(f"fact number {i} about something")
        self.assertEqual(s.backfill_embeddings(), 0)   # returns, does not hang

    def test_vector_search_does_not_claim_to_work_when_it_does_not(self):
        """THE BUG THE TESTS CAUGHT. sqlite-vec loads per CONNECTION. Loading
        it only on the connection that created the table left every later one
        raising "no such module: vec0" inside an except, while status()
        reported vector_search: true and nothing was ever embedded."""
        st = self.s.status()
        if st["vector_search"]:
            self.s.add("a fact worth embedding about penicillin")
            self.assertEqual(self.s.status()["unembedded"], 0,
                             "vector_search says true but nothing embeds")

    def test_retire_reports_whether_it_changed_anything(self):
        f = self.s.add("Mario lives at 12 Oak Street")
        self.assertTrue(self.s.retire(f))
        self.assertFalse(self.s.retire(f), "a no-op reported as a change")
        self.assertFalse(self.s.retire(999999))

    def test_a_superseded_fact_leaves_history_behind(self):
        """bitemporal.patch: "where do I live" returns the current answer and
        "where did I live last year" also works."""
        old = self.s.add("Mario lives at 12 Oak Street")
        self.s.add("Mario lives at 40 Elm Road", supersedes=old)
        live = [r["text"] for r in self.s.search("Mario lives")]
        self.assertIn("Mario lives at 40 Elm Road", live)
        self.assertNotIn("Mario lives at 12 Oak Street", live)
        self.assertIn("Mario lives at 12 Oak Street",
                      [r["text"] for r in self.s.timeline("Mario lives")])

    def test_stopwords_do_not_match_the_whole_store(self):
        """FTS5 has no stoplist; an OR-query built from every word matched
        almost everything on "the" and "is"."""
        for i in range(10):
            self.s.add(f"this is the fact number {i} and it is here")
        self.assertEqual(self.s.search("the is and it"), [])

    def test_an_empty_fact_is_refused(self):
        for bad in ("", "   ", "\n\t"):
            with self.assertRaises(ValueError):
                self.s.add(bad)

    def test_concurrent_writers_do_not_lose_facts(self):
        def spam(n):
            for i in range(20):
                self.s.add(f"thread {n} fact {i} about something specific")
        ts = [threading.Thread(target=spam, args=(n,)) for n in range(6)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(self.s.status()["facts"], 120)

    def test_a_correction_dated_in_the_past_still_links_the_versions(self):
        """"I moved in January, I am telling you in March", which is the whole
        reason the second axis exists. retire()'s docstring tells a caller who
        knows the real date to call it BEFORE adding - which sets valid_to, so
        add(supersedes=) matched nothing, left retired_by NULL, broke the
        chain timeline() walks, and logged memory.supersede_missed on a
        correction filed exactly as instructed."""
        january = time.time() - 60 * 86400
        old = self.s.add("Mario lives in Lisbon")
        self.assertTrue(self.s.retire(old, valid_to=january))
        new = self.s.add("Mario lives in Berlin", valid_from=january,
                         supersedes=old)
        row = self.s.get(old)
        self.assertEqual(row["retired_by"], new, "the versions must be linked")
        self.assertFalse(self.s.last_supersede_failed, "and not reported lost")
        self.assertAlmostEqual(row["valid_to"], january,
                               msg="linking must not overwrite the real date",
                               delta=1)

    def test_last_supersede_failed_can_be_read_on_a_fresh_store(self):
        """add() only assigns it when a supersede is attempted, so the memory
        pane rendering a correction card got AttributeError instead of 'no'."""
        self.assertIs(MEM.MemoryStore(Path(self.dir) / "fresh.db",
                                      MEM.HashEmbedder()).last_supersede_failed,
                      False)

    def test_all_four_readers_agree_about_a_future_valid_to(self):
        """A lease recorded in October as ending in December. current_facts,
        status and search called it current; known_at did not, because
        retire() stamped retired_at unconditionally. The memory pane's as-of
        view showed the lease gone while recall went on injecting it into
        prompts - two screens, opposite answers, no error anywhere."""
        fid = self.s.add("Mario's lease runs to December")
        self.s.retire(fid, valid_to=time.time() + 90 * 86400)
        self.assertIn(fid, [f["id"] for f in self.s.current_facts()])
        self.assertIn(fid, [f["id"] for f in self.s.known_at(time.time() + 1)])
        self.assertEqual(self.s.status()["current"], 1)
        self.assertTrue(self.s.search("lease", k=5)[0]["current"])
        self.assertTrue(self.s.timeline("lease")[0]["current"])
        self.assertIsNone(self.s.get(fid)["retired_at"],
                          "nothing was retracted, so nothing is stamped")

    def test_an_embedder_that_returns_nonsense_never_duplicates_a_fact(self):
        """memory-safety.patch's own words: add()'s INSERT has already
        committed by the time _embed_rows runs, "so an exception escaping here
        reported failure for a fact that was in fact stored - and each retry
        of the 'failed' accept wrote another copy of it"."""
        class Null(MEM.Embedder):
            name, dim, semantic = "null", 8, True

            def embed(self, texts):
                return None

        s = MEM.MemoryStore(Path(self.dir) / "null.db", Null())
        for _ in range(3):
            s.add("a fact that keeps being retried")
        self.assertEqual(s.status()["facts"], 3, "three adds, three rows")

    def test_an_old_store_survives_two_processes_opening_it_at_once(self):
        """The migration reads PRAGMA table_info and then runs a bare ALTER
        TABLE with nothing holding a write lock between them, so two openers
        can both decide the column is missing. The loser's
        "duplicate column name" escaped __init__ as "memory layer failed to
        start". Measured with eight processes: a failure in 2 trials of 8.

        Simulated here rather than raced: the second _init() on a store that
        already has the column is the same code path the loser takes.
        """
        db = Path(self.dir) / "old.db"
        c = sqlite3.connect(db)
        c.executescript("""
            CREATE TABLE facts (
                id INTEGER PRIMARY KEY, text TEXT NOT NULL, source TEXT,
                created REAL NOT NULL, valid_from REAL NOT NULL, valid_to REAL,
                retired_by INTEGER, embedded INTEGER NOT NULL DEFAULT 0,
                meta TEXT);
            CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);""")
        c.commit()
        # The loser's exact race: it read the table BEFORE the winner's ALTER.
        winner = MEM.MemoryStore(db, MEM.HashEmbedder())
        c.execute("ALTER TABLE facts ADD COLUMN spare REAL")
        c.commit(); c.close()
        loser = MEM.MemoryStore(db, MEM.HashEmbedder())   # must not raise
        self.assertEqual(winner.status()["facts"], 0)
        self.assertEqual(loser.status()["facts"], 0)

    def test_a_borrowed_connection_keeps_what_it_writes(self):
        """jarvis_extract owns the review queue but not a database.

        It writes through `with closing(store._connect()) as c` and never
        calls commit(), because these connections have always been autocommit.
        Under the sqlite3 DEFAULT that opens an implicit transaction and
        close() discards it, so propose() returned the rows it had just
        inserted while pending() found an empty queue - every proposal, for
        ever, with no error anywhere. Measured on the owner's machine:
        `proposed [{'id': 1, 'text': 'Mario drives a 1998 Volvo', ...}],
        pending []`.

        jarvis_extract is not in this repository, so this stands in for it:
        the same borrow, the same lack of a commit.
        """
        with closing(self.s._connect()) as c:
            c.execute("CREATE TABLE IF NOT EXISTS proposals "
                      "(id INTEGER PRIMARY KEY, text TEXT)")
            c.execute("INSERT INTO proposals (text) VALUES ('a proposal')")
        with closing(self.s._connect()) as c:
            rows = c.execute("SELECT text FROM proposals").fetchall()
        self.assertEqual([r["text"] for r in rows], ["a proposal"],
                         "a borrowed connection must not need a commit")

    def test_the_embedder_base_class_is_there_to_subclass(self):
        """`class Broken(M.Embedder)` is how two suites build an embedder that
        returns NaN, the wrong width, or raises. Without the base class those
        files die at import with AttributeError and NONE of their assertions
        run - which is what happened: test_memory_safety.py and
        test_embedding_guard.py both reported nothing at all."""
        self.assertTrue(hasattr(MEM, "Embedder"))
        self.assertTrue(issubclass(MEM.HashEmbedder, MEM.Embedder))

        class Fake(MEM.Embedder):
            name, dim, semantic = "fake", 4, True

            def embed(self, texts):
                return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

        s = MEM.MemoryStore(Path(self.dir) / "sub.db", Fake())
        s.add("a fact stored by a subclassed embedder")
        self.assertEqual(s.status()["facts"], 1)

    def test_both_time_axes_are_recorded_separately(self):
        """"I moved in January, I am telling you in March." One axis cannot
        hold it: with valid_to alone you either lie about when the move
        happened or lie about when you were told."""
        january = time.time() - 60 * 86400
        old = self.s.add("Mario lives in Lisbon")
        self.s.retire(old, valid_to=january)
        row = self.s.get(old)
        self.assertAlmostEqual(row["valid_to"], january, delta=1)
        self.assertAlmostEqual(row["retired_at"], time.time(), delta=60)
        # And what was believed a week ago is still answerable.
        week = time.time() - 7 * 86400
        self.assertEqual([f["id"] for f in self.s.known_at(week)], [])

    def test_a_lease_that_ends_in_december_is_current_today(self):
        """CONTROL. Three places computed "current" and one said
        `valid_to is None`, which disagrees with its own neighbour for a
        valid_to in the future."""
        fid = self.s.add("Mario's lease runs to December")
        self.s.retire(fid, valid_to=time.time() + 90 * 86400)
        self.assertIn(fid, [f["id"] for f in self.s.current_facts()])
        self.assertEqual(self.s.status()["current"], 1)
        hits = self.s.search("lease", k=5)
        self.assertTrue(hits and hits[0]["current"] is True)


# ==========================================================================
#   jarvis_recall
# ==========================================================================

class Recall(unittest.TestCase):

    def test_scores_are_parallel_to_the_input(self):
        """jarvis_hud.py:1014 takes rank(...)[0] and zips it against its own
        corpus. A sorted score list silently mislabels every fact."""
        texts = ["nothing to do with it", "Mario drives a Volvo", "also unrelated"]
        scored, _ = RC.rank("Mario Volvo", texts, top_k=len(texts),
                            near_k=0, min_score=0.0)
        # PAIRS, because jarvis_hud.py:1013 does `dict(rank(...)[0])` and then
        # uses the keys as corpus indices. A flat list raised TypeError there
        # and dropped the connection on every /api/retrieve query.
        by_index = dict(scored)
        self.assertEqual(sorted(by_index), list(range(len(texts))))
        self.assertGreater(by_index[1], by_index[0])
        self.assertGreater(by_index[1], by_index[2])

    def test_the_hud_can_dict_the_result(self):
        """The exact expression from jarvis_hud.py:1013, which used to raise."""
        corpus = [{"text": "sage green kitchen wall", "id": 7},
                  {"text": "unrelated", "id": 8},
                  {"text": "also unrelated", "id": 9}]
        all_scores = dict(RC.rank("what colour is the kitchen wall",
                                  [c["text"] for c in corpus],
                                  top_k=len(corpus), near_k=0, min_score=0.0)[0])
        for idx, score in all_scores.items():
            corpus[idx]["id"]           # the caller indexes the corpus by key
        self.assertEqual(len(all_scores), 3)

    def test_the_hud_call_returns_a_score_for_every_item(self):
        texts = [f"row {i}" for i in range(7)]
        scored, _ = RC.rank("nothing matches this", texts, top_k=len(texts),
                            near_k=0, min_score=0.0)
        self.assertEqual(len(scored), 7)
        self.assertEqual([i for i, _ in scored], list(range(7)))

    def test_nothing_relevant_means_nothing_injected(self):
        """Padding the prompt with the least-irrelevant facts spends context,
        evicts the persona block, and invites the model to use what does not
        apply. The caller writes `if chosen_facts:`."""
        facts = [{"text": "Mario drives a Volvo"}, {"text": "Mario likes Go"}]
        self.assertEqual(
            RC.select_facts("what is the capital of Peru", facts,
                            text_of=lambda f: str(f.get("text", ""))), [])

    FACTS = [{"text": "Mario drives a 1998 Volvo estate"},
             {"text": "Mario prefers tabs over spaces"},
             {"text": "Mario lives at 12 Oak Street"},
             {"text": "Mario is allergic to penicillin"}]

    def _pick(self, q):
        return RC.select_facts(q, self.FACTS,
                               text_of=lambda f: str(f.get("text", "")))

    def test_the_one_relevant_fact_is_chosen_and_only_it(self):
        """Every fact about the owner contains the owner's NAME. Without
        corpus weighting, "what car does Mario drive" scores every fact above
        the floor on "mario" alone and four facts get injected for a question
        about one."""
        for q, want in [("what car does Mario drive", "Volvo"),
                        ("where does Mario live", "Oak Street"),
                        ("is Mario allergic to anything", "penicillin")]:
            got = self._pick(q)
            self.assertEqual(len(got), 1, f"{q!r} chose {[g['text'] for g in got]}")
            self.assertIn(want, got[0]["text"])

    def test_a_word_in_every_fact_selects_none_of_them(self):
        """Asking just the owner's name matches everything, which
        distinguishes nothing. Injecting the lot would be the wrong answer."""
        self.assertEqual(self._pick("Mario"), [])

    def test_stems_agree_in_both_directions(self):
        """A stemmer that moves one form and not its pair is worse than none.
        A first version turned "lives" into "liv" and left "live" alone."""
        for a, b in [("drive", "drives"), ("live", "lives"),
                     ("prefer", "prefers"), ("space", "spaces"),
                     # "-oes": "goes"/"does" are four letters, same as the
                     # word being stemmed, so they fell through the sses/
                     # shes/ches/xes/zes group's length gate into the plain
                     # "-s" branch, which stripped one letter too few and
                     # stranded them at "goe"/"doe".
                     ("go", "goes"), ("do", "does"),
                     # CVC-doubling before -ing: "run"/"stop"/"plan" all
                     # geminate their final consonant in English spelling,
                     # and stripping only "-ing" left the double letter in
                     # place - "runn", "stopp", "plann" - matching nothing.
                     ("run", "running"), ("stop", "stopping"),
                     ("shop", "shopping"), ("plan", "planning")]:
            self.assertEqual(RC._stem(a), RC._stem(b), f"{a}/{b}")

    def test_undoubling_does_not_break_a_genuinely_doubled_root(self):
        """CONTROL on the CVC-doubling fix above. Porter's own rule excludes
        L, S and Z because their doubling is the WORD's spelling, not an
        artefact of adding -ing/-ed: "call"/"calling" must both land on
        "call", not "cal", or the fix would trade one asymmetry for another."""
        for a, b in [("call", "calling"), ("miss", "missing"),
                     ("buzz", "buzzing"), ("pass", "passing")]:
            stem_a, stem_b = RC._stem(a), RC._stem(b)
            self.assertEqual(stem_a, stem_b, f"{a}/{b}")
            self.assertFalse(stem_a.endswith(a[-1] * 1) and len(stem_a) < len(a) - 1,
                             f"{a} was over-stripped to {stem_a!r}")

    def test_a_relevant_fact_is_found_across_a_verb_the_stemmer_used_to_split(self):
        """End to end, the module's own worked example pattern: "what car
        does Mario drive" against "Mario drives a 1998 Volvo" is the docstring
        case _stem exists for. This is the same failure with "go"/"goes":
        select_facts("does Mario go", ...) returned [] before the fix."""
        facts = [{"text": "Mario goes running every day"},
                {"text": "Mario prefers tabs"},
                {"text": "Mario has a cat"}]
        got = RC.select_facts("does Mario go", facts, text_of=lambda f: f["text"])
        self.assertTrue(any("running" in f["text"] for f in got), got)

    def test_a_small_corpus_is_not_weighted(self):
        """Below three documents there is nothing to measure - with one fact,
        every word is in every document and all scores would collapse to
        zero. Stated as a test so the behaviour is deliberate, not a surprise."""
        self.assertEqual(RC._idf(["aa bb", "aa cc"]), {})
        self.assertTrue(RC._idf(["aa bb", "aa cc", "aa dd"]))

    def test_empty_inputs_do_not_raise(self):
        self.assertEqual(RC.select_facts("", [], text_of=lambda f: ""), [])
        self.assertEqual(RC.select_facts("anything", []), [])


# ==========================================================================
#   jarvis_router
# ==========================================================================

class Router(unittest.TestCase):

    LANES = ["jarvis-escalate", "jarvis-bulk"]

    def test_the_private_backstop_catches_both_spellings(self):
        """The list otherwise uses American terms (ssn, social security) and
        only had the British "licence" - so "what's my driver's license
        number", typed the way most of this project's owners would type it,
        missed the one backstop meant to catch literal private phrases."""
        for spelling in ("licence", "license"):
            d = RT.choose(f"what's my driver's {spelling} number, explain in "
                          f"detail and compare step by step " * 2,
                          local_model="local", lanes=self.LANES)
            self.assertEqual(d.lane, "local", f"{spelling!r} was not caught")

    def test_a_cloud_lane_is_never_handed_memory(self):
        """JARVIS-FRAMEWORK.md section 1: "There is no third option where a
        cloud model quietly receives your memory." Every branch, not just the
        happy one."""
        for q in ["explain in detail how a transformer works and compare it "
                  "to an RNN, step by step, with trade-offs" * 3,
                  "what is my password", "hello"]:
            for tainted in (True, False):
                d = RT.choose(q, local_model="local", lanes=self.LANES,
                              tainted=tainted)
                if d.lane in self.LANES:
                    self.assertFalse(d.inject_memory,
                                     f"memory offered to cloud lane for {q[:30]!r}")

    def test_taint_pins_the_turn_local(self):
        long_q = ("explain in detail and compare the trade-offs, step by step, "
                  "why this design was chosen " * 4)
        d = RT.choose(long_q, local_model="local", lanes=self.LANES, tainted=True)
        self.assertEqual(d.lane, "local")
        self.assertEqual(d.gate, "taint")

    def test_a_picture_never_goes_to_a_cloud_lane(self):
        """Rule 1. A screen capture can show an email, a file or a password
        manager, and none of the text checks can read it. choose() used to
        escalate a turn with a picture like any other long question, and
        even went looking for a lane with "vision" in its name. A fresh
        Budget (in memory, nothing spent) so the budget gate cannot be what
        keeps it local."""
        long_q = ("explain in detail and compare the trade-offs, step by step, "
                  "why this design was chosen " * 4)
        lanes = ["jarvis-escalate", "jarvis-vision", "jarvis-bulk"]
        fresh = RT.Budget(path=None)
        # CONTROL: the same question with no picture does escalate, so the
        # assertion below is about the picture and nothing else.
        plain = RT.choose(long_q, local_model="local", lanes=lanes, budget=fresh)
        self.assertIn(plain.lane, lanes, f"control did not escalate: {plain}")
        d = RT.choose(long_q, local_model="local", lanes=lanes, has_image=True,
                      budget=fresh)
        self.assertEqual(d.lane, "local")
        self.assertEqual(d.gate, "image")
        self.assertIn("picture", d.reason)

    def test_the_private_backstop_pins_the_turn_local(self):
        d = RT.choose("what is the api key for my bank account and the cvv, "
                      "explain in detail step by step and compare " * 3,
                      local_model="local", lanes=self.LANES)
        self.assertEqual(d.lane, "local")
        self.assertEqual(d.gate, "private")

    def test_local_is_an_unconditional_floor_for_degrade(self):
        """THE TOP FINDING of this audit round. choose() pins a conversation
        to "local" unconditionally on taint or the private backstop - but
        `lanes` can legitimately CONTAIN "local" (jarvis_hud:1738 is cited as
        real evidence for this), and degrade() used to walk past it to
        whatever came next in that list. Reproduced exactly:
        degrade("local", ["local","a","b"], "local") returned "a" - a CLOUD
        lane, for a turn that had already fallen back to local because the
        local model refused or timed out. Local must have nothing beneath it,
        whatever `lanes` or the configured chain contains."""
        for lanes in (["local", "jarvis-escalate", "jarvis-bulk"],
                     ["jarvis-escalate", "local", "jarvis-bulk"],
                     self.LANES):
            self.assertIsNone(RT.degrade("local", lanes, "local"),
                              f"local leaked to a cloud lane via {lanes}")
        # CONTROL: degrading a CLOUD lane down TO local must still work -
        # that direction is the documented, real use of local appearing in
        # the list. Stubbed degrade_chain, not the module's shipped default:
        # the real chain is ["jarvis-escalate","jarvis-bulk","jarvis-critic"],
        # which does not contain "local" at all, and "jarvis-bulk" being IN
        # that chain means degrade() prefers it over any custom `lanes` this
        # test passes - exactly as documented, and not what this control is
        # checking.
        keep_cfg = RT._cfg
        RT._cfg = lambda *a, **k: (["cloud-x", "local"] if a[:2] == ("budget", "degrade_chain") else keep_cfg(*a, **k))
        try:
            self.assertEqual(RT.degrade("cloud-x", [], "local"), "local")
        finally:
            RT._cfg = keep_cfg

    def test_degrade_never_returns_its_own_input(self):
        """jarvis_hud retries with the result. Returning the input is an
        infinite retry against a service that is already refusing."""
        for lane in ["jarvis-escalate", "jarvis-bulk", "jarvis-critic",
                     "local", "unknown-lane", ""]:
            nxt = RT.degrade(lane, self.LANES, "local")
            self.assertNotEqual(nxt, lane, f"degrade({lane!r}) returned itself")

    def test_degrade_terminates(self):
        lane, seen = "jarvis-escalate", set()
        for _ in range(20):
            lane = RT.degrade(lane, self.LANES, "local")
            if lane is None:
                break
            self.assertNotIn(lane, seen, "degrade went round in a circle")
            seen.add(lane)
        else:
            self.fail("degrade did not terminate")

    def test_a_corrupt_budget_file_does_not_stop_a_turn(self):
        p = Path(_TMP) / "budget.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{not json", encoding="utf-8")
        orig = RT.Budget._store_path
        RT.Budget._store_path = classmethod(lambda cls: p)
        try:
            self.assertIsInstance(RT.Budget.load().status(), dict)
        finally:
            RT.Budget._store_path = orig

    def test_the_decision_exposes_what_the_hud_reads(self):
        d = RT.Decision("local", "because", "manual", 0.0, inject_memory=True)
        for attr in ("lane", "reason", "gate", "inject_memory"):
            self.assertTrue(hasattr(d, attr), attr)
        self.assertIsInstance(d.as_dict(), dict)

    # ---- looks_like_a_secret / gate 3 -----------------------------------
    #
    # is_private() catches the WORD for a secret; these catch the secret
    # ITSELF, pasted with nothing naming it - a gap a prior audit found had
    # no scanner at all, only the topic-keyword backstop above.

    def test_recognised_secret_shapes_are_caught(self):
        samples = {
            "a private key": "-----BEGIN RSA PRIVATE KEY-----\nMIIB...",
            "an AWS access key": "AKIAABCDEFGHIJKLMNOP",
            "a GitHub token": "ghp_" + "a" * 36,
            "a Slack token": "xoxb-1234567890-abcdefghij",
            "an OpenAI-style API key": "sk-" + "a" * 24,
            "a JSON web token": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
            "a bearer token": "Bearer " + "a" * 24,
            "a labelled secret value": 'api_key: "abcdefghijklmnop1234"',
        }
        for kind, sample in samples.items():
            found = RT.looks_like_a_secret(f"here is the config: {sample}")
            self.assertIsNotNone(found, f"{kind} was not caught: {sample!r}")
            self.assertIn(kind, found)

    def test_ordinary_text_is_not_flagged(self):
        for q in ["what's the weather like", "explain how photosynthesis works",
                  "my order number is 4471829", "the meeting is at 3pm",
                  "here is a hash: d41d8cd98f00b204e9800998ecf8427e"]:
            self.assertIsNone(RT.looks_like_a_secret(q), f"false positive on {q!r}")

    def test_a_secret_is_never_shown_in_full(self):
        secret = "sk-" + "x" * 40
        found = RT.looks_like_a_secret(secret)
        self.assertIsNotNone(found)
        self.assertNotIn(secret, found, "the full secret leaked into the reason text")

    def test_a_pasted_secret_pins_the_turn_local_with_no_matching_keyword(self):
        # Deliberately no word from _PRIVATE_TERMS anywhere in this message -
        # is_private() must NOT be what catches this one.
        q = ("here's the deploy config: AKIAABCDEFGHIJKLMNOP, explain in "
             "detail step by step and compare the trade-offs " * 2)
        self.assertFalse(RT.is_private(q), "test setup: this must not trip the keyword backstop")
        d = RT.choose(q, local_model="local", lanes=self.LANES)
        self.assertEqual(d.lane, "local")
        self.assertEqual(d.gate, "secret")
        self.assertIn("AWS access key", d.reason)

    def test_secret_gate_lands_on_local_the_same_way_the_other_gates_do(self):
        # A local decision is allowed to carry memory - only a CLOUD lane may
        # not (test_a_cloud_lane_is_never_handed_memory covers that
        # invariant already). What matters here is that gate 3 resolves to
        # `local` through the same local_decision() every other gate uses,
        # rather than some parallel path that could disagree about it.
        q = "ghp_" + "a" * 36  # a shape gate 3 catches with no is_private keyword nearby
        self.assertFalse(RT.is_private(q), "test setup: this must not trip the keyword backstop")
        d = RT.choose(q, local_model="local", lanes=self.LANES)
        self.assertEqual(d.lane, "local")
        self.assertEqual(d.gate, "secret")
        self.assertTrue(d.inject_memory, "a local decision should carry memory like the others do")


# ==========================================================================
#   jarvis_voice
# ==========================================================================

class Voice(unittest.TestCase):
    """The safe failure is to ignore a stranger. Accepting one hands the
    microphone of a machine with an approval queue to whoever is in the room.
    """

    def setUp(self):
        self.prof = Path(_TMP) / "voice.json"
        VO.PROFILE_PATH = self.prof
        if self.prof.exists():
            self.prof.unlink()
        self._cfg = VO._cfg
        VO._cfg = lambda k, d=None: {"enabled": True, "mode": "owner",
                                     "threshold": 0.5}.get(k, d)

    def tearDown(self):
        VO._cfg = self._cfg

    def test_embed_takes_one_clip_and_returns_one_vector(self):
        """THE BUG THE SURVIVING TEST CAUGHT. test_speech.py's stub is
            class FakeEmbedder(V.Embedder):
                def embed(self, audio): return self.vec
        With a list signature the stub is never called at all."""
        v = VO.Embedder().embed(b"\x00\x01" * 2000)
        self.assertTrue(all(isinstance(x, float) for x in v), v)

    def test_no_profile_means_refuse(self):
        v = VO.verify(b"\x00\x01" * 4000)
        self.assertFalse(v.is_owner)
        self.assertIn("no enrolled", v.reason)

    def test_a_corrupt_profile_means_refuse(self):
        for junk in ("{}", "[]", "not json",
                     '{"centroid": []}', '{"centroid": ["a","b"]}',
                     '{"centroid": "1234", "samples": 3}',
                     '{"centroid": {"0":1,"1":0}, "samples": 3}',
                     '{"centroid": [1,2], "threshold": "x"}',
                     # json.loads accepts the bare tokens NaN/Infinity as a
                     # Python-specific extension, and NaN IS a float - so it
                     # passed the isinstance(x, (int,float)) check that
                     # rejects strings and dicts. Fails safe at verify() time
                     # either way (cosine's isfinite guard scores it 0.0),
                     # but load_profile()'s own docstring promises None on
                     # "anything wrong", and a permanently unusable profile
                     # that reports itself enrolled is a silent lockout with
                     # no "corrupt, re-enrol" diagnostic anywhere.
                     '{"centroid": [NaN,NaN,NaN,NaN], "samples": 3}',
                     '{"centroid": [1,Infinity,0,0], "samples": 3}'):
            self.prof.write_text(junk, encoding="utf-8")
            self.assertIsNone(VO.load_profile(), junk)
            self.assertFalse(VO.verify(b"\x00\x01" * 4000).is_owner, junk)

    def test_a_different_voice_is_refused(self):
        class Fixed(VO.Embedder):
            def __init__(self, v): self.v = list(v)
            def embed(self, audio): return self.v

        VO.VoiceProfile(centroid=[1.0, 0.0, 0.0, 0.0], threshold=0.5,
                        samples=3).save(self.prof)
        self.assertFalse(VO.verify(b"x", Fixed([0.0, 1.0, 0.0, 0.0])).is_owner)
        self.assertTrue(VO.verify(b"x", Fixed([1.0, 0.0, 0.0, 0.0])).is_owner)

    def test_broad_mode_is_always_visible_in_the_verdict(self):
        VO._cfg = lambda k, d=None: {"enabled": True, "mode": "broad"}.get(k, d)
        v = VO.verify(b"x")
        self.assertTrue(v.is_owner)
        self.assertEqual(v.mode, "broad")
        self.assertIn("broad", v.reason)

    def test_enrolment_never_raises_the_bar_above_the_config(self):
        """The config's promise: "a strict value here cannot lock you out."
        Lowering is the feature; raising would be a silent policy change."""
        class Fixed(VO.Embedder):
            def __init__(self): self.n = 0
            def embed(self, audio):
                self.n += 1
                return [1.0, 0.0] if self.n % 2 else [0.7, 0.714]

        prof = VO.enroll([b"a", b"b", b"c"], Fixed(), path=self.prof)
        self.assertLessEqual(prof.threshold, 0.5)


# ==========================================================================
#   the small ones
# ==========================================================================

class Small(unittest.TestCase):

    def test_quiet_hours_across_midnight(self):
        """A naive start <= t <= end returns False all night, every night,
        and the setting looks like it does nothing."""
        import datetime as dt
        keep = PW._cfg
        # The key names in the SHIPPED config. This test read
        # quiet_hours_start/end, which appear in no config anywhere, so it
        # passed against a module that also read them - two wrongs agreeing.
        PW._cfg = lambda k, d=None: {"enabled": True, "schedule_enabled": True,
                                     "quiet_start": "22:00",
                                     "quiet_end": "07:00"}.get(k, d)
        try:
            at = lambda h: dt.datetime(2026, 1, 1, h, 30)
            self.assertTrue(PW.in_quiet_hours(at(23)))
            self.assertTrue(PW.in_quiet_hours(at(2)))
            self.assertTrue(PW.in_quiet_hours(at(6)))
            self.assertFalse(PW.in_quiet_hours(at(12)))
            self.assertFalse(PW.in_quiet_hours(at(21)))
            # schedule_enabled=false must switch the whole thing off, or
            # fixing the key names would turn quiet hours ON against a config
            # that says the schedule is disabled.
            PW._cfg = lambda k, d=None: {"enabled": True, "schedule_enabled": False,
                                         "quiet_start": "22:00",
                                         "quiet_end": "07:00"}.get(k, d)
            self.assertFalse(PW.in_quiet_hours(at(23)))
        finally:
            PW._cfg = keep

    def test_an_unknown_power_mode_is_refused_not_stored(self):
        with self.assertRaises(ValueError):
            PW.set_mode("sleeping")
        self.assertIn(PW.current(), PW.MODES)

    def test_compute_plan_never_raises_and_admits_guessing(self):
        p = CP.plan()
        self.assertIsInstance(p.as_dict(), dict)
        for attr in ("text_model", "text_on", "vision_resident",
                     "tts_resident", "simulated"):
            self.assertTrue(hasattr(p, attr), attr)

    def test_a_negative_device_reading_is_not_a_measurement(self):
        """`if pl.total_mb: return pl.total_mb` (jarvis_models.py:489, quoted
        in the property's own docstring) treats exactly 0 as "not measured,
        use the honest default" and anything else as real. A negative number
        - corrupt or injected device data; real nvidia-smi cannot emit one,
        but nothing here enforced that - is not zero, so it was trusted as a
        genuine reading instead of falling through to the safe default."""
        bad = CP.Device(index=0, name="Fake", total_mb=-1000, free_mb=-500)
        good = CP.Device(index=1, name="Real", total_mb=8192, free_mb=4000)
        p = CP.Plan(text_model="m", text_on="cuda:1", devices=[bad, good])
        self.assertEqual(p.total_mb, 8192, "the negative reading was counted")
        p2 = CP.Plan(text_model="m", text_on="cuda:0", devices=[bad])
        self.assertEqual(p2.total_mb, 0, "a lone negative reading must be 0")

    def test_the_two_shells_say_they_are_shells(self):
        """Neither was reconstructible. Reporting them as working would be
        the worst outcome: a Jarvis that looks proactive and is not."""
        self.assertFalse(SL.status()["implemented"])
        e = IN.build_from_config()
        self.assertEqual(e.status()["checks"], 0)
        self.assertIn("not recoverable", e.status()["note"])

    def test_a_check_that_throws_does_not_kill_the_heartbeat(self):
        e = IN.Engine(heartbeat_minutes=1)
        e.register("bad", lambda: (_ for _ in ()).throw(RuntimeError("no")))
        e.register("good", lambda: {"found": 1})
        got = e.beat()
        self.assertEqual(len(got), 1)
        self.assertEqual(e.errors, 1)

    def test_sleep_offers_once_a_day_not_once_a_tick(self):
        keep = SL._cfg
        SL._cfg = lambda k, d=None: {"enabled": False, "remind": True}.get(k, d)
        SL._seen.clear()
        try:
            self.assertIsNotNone(SL.reminder_card())
            self.assertIsNone(SL.reminder_card())
        finally:
            SL._cfg = keep

    def test_sleep_hour_reads_the_real_config_key(self):
        """hour() read config key "hour" under [memory.sleep_time]; the TOML
        key is remind_hour_local (jarvis-framework.toml:367) - the same class
        of typo as the historical quiet_hours_start/quiet_start bug, in a
        different module. No caller wires this in yet (grepped the whole
        repo), so nothing has silently used 3am instead of the owner's
        configured hour - but the moment anything gates on it, it would."""
        keep = SL._cfg
        SL._cfg = lambda k, d=None: {"remind_hour_local": 21}.get(k, d)
        try:
            self.assertEqual(SL.hour(), 21)
        finally:
            SL._cfg = keep
        # And still degrades honestly when the key is missing or garbage.
        SL._cfg = lambda k, d=None: {}.get(k, d)
        try:
            self.assertEqual(SL.hour(), 3)
        finally:
            SL._cfg = keep
        SL._cfg = lambda k, d=None: {"remind_hour_local": 99}.get(k, d)
        try:
            self.assertEqual(SL.hour(), 3)
        finally:
            SL._cfg = keep

    def test_set_enabled_and_set_remind_answer_the_cards_own_actions(self):
        """`reminder_card()` offers three actions - "enable", "not now",
        "stop asking" - and until these two functions existed nothing
        answered the first or the third; a client had the card and nothing
        to send back for it."""
        tmp = Path(tempfile.mkdtemp()) / "sleep_time.json"
        keep = SL._override_path
        SL._override_path = lambda: tmp
        try:
            self.assertFalse(SL.enabled())
            out = SL.set_enabled(True)
            self.assertTrue(out["ok"])
            self.assertTrue(SL.enabled())

            out = SL.set_remind(False)
            self.assertTrue(out["ok"])
            self.assertFalse(SL.remind())
            # Setting remind must not have touched the enabled key it wrote
            # moments before - each call writes ONE key, not the whole file.
            self.assertTrue(SL.enabled())
        finally:
            SL._override_path = keep

    def test_the_override_file_wins_over_the_toml(self):
        """`_cfg`'s whole point: a decision made from the card has to stick
        even though the TOML underneath it was never touched and still says
        the opposite."""
        tmp = Path(tempfile.mkdtemp()) / "sleep_time.json"
        keep_path = SL._override_path
        keep_fw = FW.load_framework
        SL._override_path = lambda: tmp
        FW.load_framework = lambda: {"memory": {"sleep_time": {"enabled": False}}}
        try:
            self.assertFalse(SL.enabled(), "the TOML value should read through untouched")
            SL.set_enabled(True)
            self.assertTrue(SL.enabled(), "the override did not take priority over the TOML")
        finally:
            SL._override_path = keep_path
            FW.load_framework = keep_fw

    def test_a_missing_config_directory_fails_the_write_honestly(self):
        """No silent no-op: a client that shows `out["ok"]` would otherwise
        tell the owner their tap enabled something that was never written."""
        keep = SL._override_path
        SL._override_path = lambda: None
        try:
            out = SL.set_enabled(True)
            self.assertFalse(out["ok"])
            self.assertIn("error", out)
        finally:
            SL._override_path = keep


# ==========================================================================
#   jarvis_initiative
# ==========================================================================

class Initiative(unittest.TestCase):
    """No dedicated coverage existed for this module before this round - only
    two incidental tests inside Small. That gap is why the doorbell bug below
    went uncaught: file() is the one call site that fires an event, and
    nothing exercised it."""

    def test_the_first_finding_after_a_restart_still_rings(self):
        """jarvis_events.Bus.note()'s own docstring names this exact call as
        its example: set_activity() and Notebook.file() are REPORTS, not a
        poller's observation, and the first one after a restart is the most
        important there is. file() called note() with no announce_first, so
        the bus - which has never seen the key "findings" - took the very
        first finding filed after every restart as a baseline and published
        nothing for it."""
        e = IN.Engine(heartbeat_minutes=30)
        bus = EV.Bus()
        import jarvis_events as _ev_mod
        keep = _ev_mod.BUS
        _ev_mod.BUS = bus
        try:
            e.file("watcher", {"text": "something noticed"})
            got = [ev for ev in bus.since(0)[0] if ev.kind == "finding"]
            self.assertEqual(len(got), 1, "the first finding must still ring")
        finally:
            _ev_mod.BUS = keep

    def test_a_same_size_change_in_unseen_count_still_rings(self):
        """The bug: file() announced the UNSEEN count, which is not
        monotonic - mark_seen() lowers it without re-baselining. A fresh
        finding that happened to bring the unseen count back to an
        already-announced value compared equal under note()'s dedupe and was
        silently swallowed: file A (2 unseen, announced) -> owner reads A (1
        unseen, no re-baseline) -> file B, brand new (2 unseen again) ->
        dropped. Keying on `_filed_total` instead (never decremented) means
        A, B and C - EVERY filing - now rings, which is what this checks:
        three findings in, three events out, none swallowed by a count that
        happened to repeat."""
        e = IN.Engine(heartbeat_minutes=30)
        bus = EV.Bus()
        import jarvis_events as _ev_mod
        keep = _ev_mod.BUS
        _ev_mod.BUS = bus
        try:
            a = e.file("watcher", {"text": "finding A"})
            e.file("watcher", {"text": "finding B"})        # unseen=2
            e.mark_seen([a["id"]])                           # unseen drops to 1
            e.file("watcher", {"text": "finding C, brand new"})  # unseen=2 again
            got = [ev for ev in bus.since(0)[0] if ev.kind == "finding"]
            self.assertEqual(len(got), 3, "finding C's doorbell was swallowed")
        finally:
            _ev_mod.BUS = keep

    def test_mark_seen_does_not_touch_a_different_id(self):
        e = IN.Engine(heartbeat_minutes=30)
        a = e.file("s", "one")
        b = e.file("s", "two")
        e.mark_seen([a["id"]])
        unseen = [f["id"] for f in e.findings if not f["seen"]]
        self.assertEqual(unseen, [b["id"]])

    def test_concurrent_filing_produces_no_duplicate_ids(self):
        e = IN.Engine(heartbeat_minutes=30)
        rows = []
        lock = threading.Lock()

        def spam():
            r = e.file("s", "x")
            with lock:
                rows.append(r["id"])
        ts = [threading.Thread(target=spam) for _ in range(40)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(len(rows), len(set(rows)), "duplicate ids were filed")


if __name__ == "__main__":
    print(f"rebuilt modules: {REBUILT}")
    print(f"config:          {_CONFIG or 'NOT FOUND - some tests will skip'}")
    unittest.main(verbosity=1)
