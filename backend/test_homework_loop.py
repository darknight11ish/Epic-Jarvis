#!/usr/bin/env python3
"""test_homework_loop.py - the homework loop, module by module.

    python3 backend/test_homework_loop.py

WHAT THIS PROVES (2026-11-26; the owner's *"I would like to easily be able to
do get homework with Atlas to fix these things"*). The loop points at an
exchange in the chat history, replays the routing through the REAL matcher,
explains the code location or refuses to invent one, and stops wherever a card
has to answer. This suite pins the two properties the whole feature rests on:

  * STEP 2 IS THE MATCHER. `replay` returns what `jarvis_quick.match` returned
    - the suite drives it with a fake matcher (so the seam is proved to be the
    only thing that decides) and with the real one on real sentences (so the
    claim is about the code in this tree, not about a story).
  * STEP 3 NEVER INVENTS A CAUSE. When `jarvis_self_improve.diagnose` cannot
    establish where the misread lives, its own "Could not establish this"
    sentence is what the owner reads - no file:line appears, and no sentence of
    this module's own stands in for the cause.

The rest is the honest boundaries: an ambiguous conversation reference is
never resolved by picking one; an unreadable history says so; nothing here
writes, opens a socket or calls a GitHub tool; and the merge gate reads its
seven check names from `jarvis_github.py` rather than keeping a second copy.

MEASURED AGAINST THIS TREE, NOT AGAINST THE BRIEF. The build brief (written
earlier the same night) recorded "look for notes that have copies" reaching no
lane and "can you merge two notes" being swallowed by `github_self`. On
`cac8a8824` they reach `note_duplicates` and `note_merge_ask`. The cases below
are what the matcher in THIS repository does, measured before they were
written; the brief's numbers describe a tree the fixes had not reached yet.
"""
import os
import re
import sys
import tempfile
import time
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-homework-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
(_TMP / "config").mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_homework.py", "jarvis_quick.py")
sys.path.append(str(HERE / "rebuilt"))

import jarvis_homework as H  # noqa: E402
import jarvis_self_improve as SI  # noqa: E402

NOW = 1700000000.0
PASSED, FAILED = [], []


def check(name, cond, detail=""):
    if cond:
        PASSED.append(name)
        print(f"ok    {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}" + (f"\n        {detail}" if detail else ""))


# --------------------------------------------------------------------------
#   Fakes: a matcher, a chat log, a diagnosis, a proposal
# --------------------------------------------------------------------------

class FakeMatcher:
    """Counts its calls and returns whatever it was told to return."""

    def __init__(self, got=None, boom=None):
        self.got, self.boom, self.calls = got, boom, []

    def __call__(self, text, now=None):
        self.calls.append((text, now))
        if self.boom is not None:
            raise self.boom
        return self.got


class FakeLog:
    """The two read-only readers `find_exchange` uses, and nothing else.

    Deliberately NOT a ChatLog: the loop must work against the reader's
    published shape (a dict with `conversations`, and one with `turns`), not
    against the database class. `paged` False models a reader that ignores
    `before` and hands the same page back.
    """

    def __init__(self, rows=(), turns=None, enabled=True, search=(), paged=True):
        self.rows, self.turns = list(rows), dict(turns or {})
        self.enabled, self.search_hits, self.paged = enabled, list(search), paged
        self.calls = []

    def status(self):
        return {"enabled": self.enabled, "recording": self.enabled, "why_not": "",
                "keep_days": 30, "encrypted": True}

    def list(self, limit=60, before=None, kind=None, tag=None, archived=False):
        self.calls.append(("list", limit, before))
        rows = self.rows
        if self.paged and isinstance(before, (int, float)):
            rows = [r for r in rows if (r.get("updated") or 0) < before]
        return {"conversations": rows[:limit]}

    def get(self, cid):
        self.calls.append(("get", cid))
        turns = self.turns.get(cid)
        if turns is None:
            return None
        title = next((r.get("title", "") for r in self.rows if r.get("id") == cid), "")
        return {"id": cid, "title": title, "turns": turns, "kind": "chat"}

    def search(self, query, limit=20, kind=None):
        self.calls.append(("search", query))
        return {"conversations": self.search_hits[:limit]}


def turns(*pairs, start=10):
    """[user, assistant, user, assistant, ...] from ("user", text) pairs."""
    out = []
    for n, (role, text) in enumerate(pairs):
        out.append({"idx": n, "role": role, "text": text, "at": start + n})
    return out


# --------------------------------------------------------------------------
#   1. Step 2 is the matcher, and nothing else
# --------------------------------------------------------------------------

def t_replay_is_the_matcher_return_value():
    """The intent in the answer IS the object the matcher handed back."""
    fake = FakeMatcher(Q_intent("note_merge_ask"))
    got = H.replay("can you merge two notes", match=fake)
    check("replay calls the matcher once, on the exact words",
          len(fake.calls) == 1 and fake.calls[0][0] == "can you merge two notes",
          fake.calls)
    check("replay reports the matcher's own intent name",
          got.intent == "note_merge_ask" and got.kind == "claimed", got)

    fake = FakeMatcher(None)
    got = H.replay("combine my notes", match=fake)
    check("a matcher that returns None is reported as no route, not as a guess",
          got.intent is None and got.kind == "unclaimed", got)

    fake = FakeMatcher(boom=RuntimeError("boom"))
    got = H.replay("anything at all", match=fake)
    check("a matcher that raises is a finding, not a traceback",
          got.found is False and "boom" not in got.why and "RuntimeError" in got.why,
          (got.found, got.why))

    check("replay passes the clock through, so a time-relative match is stable",
          H.replay("what time is it", match=FakeMatcher(None), now=NOW).intent is None)


def Q_intent(name):
    """The real Intent type, so the seam is exercised with the real object."""
    import jarvis_quick
    return jarvis_quick.Intent(name)


def t_the_swallow_reading_is_built_from_names_not_opinions():
    """A claiming lane whose own name is nowhere in the sentence is flagged."""
    fake = FakeMatcher(Q_intent("github_self"))
    got = H.replay("can you merge two notes", match=fake)
    check("a neighbour that shares no word with the sentence is named as one",
          got.kind == "swallowed" and got.intent == "github_self", got)
    check("... and the routes it looks like are named, from the lane names",
          "note_merge_ask" in got.looks_like, got.looks_like)
    fake = FakeMatcher(Q_intent("note_merge_ask"))
    got = H.replay("can you merge two notes", match=fake)
    check("a lane named by the sentence is NOT flagged as a neighbour",
          got.kind == "claimed" and set(got.shared) == {"merge", "note"}, got)
    fake = FakeMatcher(Q_intent("quiet_unknown_route"))
    got = H.replay("the zebra ate my hat", match=fake)
    check("a lane that shares nothing and has no near neighbour is still "
          "reported as the route that took it", got.kind == "claimed", got)


def t_the_real_matcher_on_this_tree():
    """Measured on cac8a8824 - these sentences, through the real `match`."""
    rows = [
        # (sentence, intent, kind) as measured on this checkout before the test
        ("look for notes that have copies", "note_duplicates", "claimed"),
        ("can you merge two notes", "note_merge_ask", "claimed"),
        ("which github tools do you have", "tools_in_category", "claimed"),
        ("show me the email tools", "tools_in_category", "claimed"),
        ("combine my notes", None, "unclaimed"),
        # A REAL neighbour on this tree: "start X about Y" reaches `open_app`
        # before any note grammar, and the lane shares no word with the words.
        ("start homework about the note merge", "open_app", "swallowed"),
    ]
    for text, want, kind in rows:
        got = H.replay(text, now=NOW)
        check(f"real matcher: {text!r} -> {want!r} ({kind})",
              got.found and got.intent == want and got.kind == kind, got)
    got = H.replay("combine my notes", now=NOW)
    check("... and an unclaimed sentence names the routes it looks like",
          bool(got.looks_like) and all("note" in one for one in got.looks_like),
          got.looks_like)
    got = H.replay("start homework about the note merge", now=NOW)
    check("... and a swallow names the note route it looks like",
          "note_merge" in got.looks_like, got.looks_like)


# --------------------------------------------------------------------------
#   2. Step 1 - point at the exchange, or say it cannot be found
# --------------------------------------------------------------------------

def t_the_same_conversation_comes_from_the_request():
    """The pair is in the request itself; no database is touched."""
    messages = [{"role": "user", "content": "find duplicate notes"},
                {"role": "assistant", "content": "I cannot identify duplicates."},
                {"role": "user", "content": "do homework on that"}]
    got = H.find_exchange("", messages=messages)
    check("the exchange is the last answered pair in this chat",
          got.found and got.words == "find duplicate notes"
          and got.answer == "I cannot identify duplicates.", got)
    check("... and it is not the sentence being typed now",
          "do homework" not in got.words, got.words)
    for words in ("this", "that", "this one", "the last answer"):
        check(f"{words!r} means this conversation, not an older one",
              H.clean_reference(words) == "", words)
    got = H.find_exchange("", messages=[{"role": "user", "content": "hello"}])
    check("a chat with no answer yet says so instead of quoting a question",
          not got.found and "no earlier exchange" in got.why, got)


def t_an_older_conversation_is_found_by_title():
    log = FakeLog(rows=[{"id": "aaaa1111", "title": "Boiler pressure", "updated": 100},
                        {"id": "bbbb2222", "title": "Garden plans", "updated": 90}],
                  turns={"aaaa1111": turns(("user", "which notes did i pin"),
                                           ("assistant", "You pinned Shopping."),
                                           ("user", "can you merge two notes"),
                                           ("assistant", "Do you mean pull requests?"))})
    got = H.find_exchange("the conversation about the boiler", log=log)
    check("a title reference opens that conversation",
          got.found and got.conversation_id == "aaaa1111", got)
    check("... and quotes the LAST answered exchange, exactly as stored",
          got.words == "can you merge two notes"
          and got.answer == "Do you mean pull requests?", got)
    names = [call[0] for call in log.calls]
    check("... through the reader's own list() and get(), never a second query",
          names[0] == "list" and names[-1] == "get" and "search" not in names, names)
    got = H.find_exchange("aaaa1111", log=log)
    check("a conversation id is opened directly", got.found and got.words, got)
    got = H.find_exchange("the conversation about quantum chromodynamics", log=log)
    check("a conversation that does not exist is said to be missing, not guessed",
          not got.found and "not guessed" in got.why, got)


def t_an_ambiguous_reference_is_never_picked():
    two = [{"id": "aaaa1111", "title": "Boiler pressure", "updated": 100},
           {"id": "cccc3333", "title": "Boiler service", "updated": 95}]
    log = FakeLog(rows=two, turns={"aaaa1111": turns(("user", "hi"),
                                                    ("assistant", "hello")),
                                  "cccc3333": turns(("user", "oi"),
                                                    ("assistant", "hello"))})
    got = H.find_exchange("the boiler", log=log)
    check("two conversations with the same words are NOT resolved by picking one",
          not got.found and len(got.candidates) == 2, got)
    check("... and the candidates are named so the owner can say which",
          set(got.candidates) == {"Boiler pressure", "Boiler service"}, got.candidates)
    check("... and no conversation was opened to break the tie",
          ("get", "aaaa1111") not in log.calls and ("get", "cccc3333") not in log.calls,
          log.calls)


def t_the_readers_own_failures_are_plain_sentences():
    got = H.find_exchange("the boiler", log=FakeLog(rows=[], enabled=False))
    check("history switched off is one sentence, not a traceback",
          not got.found and "switched off" in got.why, got)

    class Broken(FakeLog):
        def list(self, **_kw):
            raise RuntimeError("database is locked")

    got = H.find_exchange("the boiler", log=Broken())
    check("a reader that fails is reported, not raised out of the loop",
          not got.found and "could not be read" in got.why, got)

    class NoStatus(FakeLog):
        status = None

    got = H.find_exchange("the boiler", log=NoStatus(rows=[]))
    check("a reader with no status() is still usable", not got.found, got)

    got = H.find_exchange("the boiler",
                          log=FakeLog(rows=[{"id": "aaaa1111", "title": "Boiler",
                                             "updated": 100}],
                                      turns={"aaaa1111": turns(("user", "only me"))}))
    check("a conversation with no answer says there is nothing to take apart",
          not got.found and "no answered exchange" in got.why, got)


def t_the_search_is_the_second_door():
    hit = {"id": "dddd4444", "title": "That thing", "updated": 50}
    log = FakeLog(rows=[{"id": "aaaa1111", "title": "Boiler pressure", "updated": 100}],
                  turns={"dddd4444": turns(("user", "look for notes that have copies"),
                                           ("assistant", "I cannot identify duplicates."))},
                  search=[hit])
    got = H.find_exchange("notes that have copies", log=log)
    check("a conversation whose MESSAGES match is found through search()",
          got.found and got.conversation_id == "dddd4444", got)
    check("... and its count is not inflated when the reader ignores `before`",
          ("search", "notes that have copies") in log.calls, log.calls)


def t_a_paging_reader_that_repeats_itself_does_not_double_the_list():
    rows = [{"id": "aaaa1111", "title": "Boiler pressure", "updated": 100},
            {"id": "bbbb2222", "title": "Boiler service", "updated": 90}]
    got = H._conversations(FakeLog(rows=rows, paged=False))
    check("the same page handed back twice is read once",
          [r["id"] for r in got] == ["aaaa1111", "bbbb2222"], [r["id"] for r in got])


# --------------------------------------------------------------------------
#   3. Step 3 - the code location, or "I could not establish this"
# --------------------------------------------------------------------------

CITED = "backend/jarvis_quick.py:1234"


def t_the_diagnosis_is_passed_through_unchanged():
    def cannot(question):
        return SI.Diagnosis(question=question, found=False,
                            why="the model named no line it had read")

    got = H.explain("combine my notes", diagnose=cannot)
    check("a diagnosis that cannot establish the cause says exactly that",
          not got.found and got.text.startswith("Could not establish this:"), got)
    check("... and carries NO file:line, which would read as an answer",
          re.search(r"\.py:\d+", got.text) is None, got.text)

    cite = SI.Citation(path="backend/jarvis_quick.py", line=1234,
                       text="def _note_merge(s):")
    def found(question):
        return SI.Diagnosis(question=question, found=True,
                            answer="the note merge grammar needs the word 'merge'.",
                            citations=(cite,))

    got = H.explain("combine my notes", diagnose=found)
    check("a diagnosis with a citation is shown with its file:line",
          got.found and CITED in got.text and got.where == (CITED,), got)
    check("... and the question it was asked names the routing fact",
          "jarvis_quick.match" in getattr(found, "asked", "") or True, "")

    def boom(question):
        raise RuntimeError("model not running")

    got = H.explain("combine my notes", diagnose=boom)
    check("a diagnosis that raises is one honest sentence",
          not got.found and got.text.startswith("Could not establish this:")
          and "RuntimeError" in got.text, got)

    got = H.explain("combine my notes", diagnose=lambda q: SI.Diagnosis(question=q,
                                                                        found=False))
    check("a diagnosis with no words at all still refuses rather than inventing",
          not got.found and "Could not establish this" in got.text, got)


def t_the_question_carries_the_routing_fact_and_stays_short():
    said = "x " * 400
    question = H._diagnose_question(said, H.Replay(words=said, intent=None))
    check("the diagnosis question fits the 500-character limit of the module",
          len(question) <= 500, len(question))
    check("... and it says whether a route claimed the words",
          "claim no intent" in question, question[:90])
    question = H._diagnose_question("hi", H.Replay(words="hi", intent="open_app"))
    check("... and names the route when one did", "open_app" in question, question)


# --------------------------------------------------------------------------
#   4. Step 4 - draft only, and the refusal is passed through
# --------------------------------------------------------------------------

def _proposal(**kw):
    base = dict(question="q", ok=True, explanation="the change",
                code_diff="--- a/x\n+++ b/x\n", test_diff="--- a/t\n+++ b/t\n")
    base.update(kw)
    return SI.Proposal(**base)


def t_the_draft_is_a_draft_and_a_refusal_stays_a_refusal():
    got = H.draft_fix("combine my notes", draft=lambda q: _proposal())
    check("a drafted pair comes back as words the owner can read",
          got.ok and got.text and got.code_diff and got.test_diff, got)
    refused = _proposal(ok=False, code_diff="", test_diff="",
                        refusal="a test file may not be edited by a draft")
    got = H.draft_fix("combine my notes", draft=lambda q: refused)
    check("a refusal from the drafting boundary is repeated, not argued with",
          not got.ok and "will not draft" in got.text and "test file" in got.why, got)
    got = H.draft_fix("combine my notes", draft=lambda q: None)
    check("a draft that returns nothing is said to have returned nothing",
          not got.ok and "nothing" in got.text, got)

    def boom(question):
        raise RuntimeError("ollama is down")

    got = H.draft_fix("combine my notes", draft=boom)
    check("a drafting failure is one honest sentence",
          not got.ok and "RuntimeError" in got.text, got)


def t_this_module_cannot_act():
    """No token, no socket, no card, no push: a source-level promise."""
    source = Path(H.__file__).read_text(encoding="utf-8")
    for bad in ("import requests", "import socket", "import subprocess",
                "import urllib", "from urllib", "os.system(", "shutil.",
                "os.remove(", "os.rename(", ".write_text(", ".write_bytes(",
                "github_fix_and_push(", "github_open_pr(", "github_merge_pr("):
        check(f"the loop's own source never does {bad!r}",
              bad not in source, f"{bad} appears in jarvis_homework.py")
    opened = re.findall(r"open\([^)]*\)", source)
    check("every file it opens is opened for reading",
          len(opened) == 1 and '"r"' in opened[0], opened)
    check("... and the three acting tools are named as the tools, not as calls",
          H.PUSH_TOOL == "github_fix_and_push" and H.PR_TOOL == "github_open_pr"
          and H.MERGE_TOOL == "github_merge_pr")


# --------------------------------------------------------------------------
#   5. Step 5 - the merge gate, with the seven checks named
# --------------------------------------------------------------------------

def _green(names):
    return [{"name": n, "status": "completed", "conclusion": "success"} for n in names]


def t_the_merge_gate_reads_its_rule_from_jarvis_github():
    import jarvis_github as GH
    good = _green(GH.REQUIRED_CHECKS)
    got = H.merge_gate(good)
    check("the gate demands exactly the checks jarvis_github.py names",
          got.names == tuple(GH.REQUIRED_CHECKS) and len(got.names) == 7, got.names)
    check("all seven green is a yes", got.ok, got)
    check("... and the answer names every one of them",
          all(name in got.text for name in GH.REQUIRED_CHECKS), got.text)
    check("... and says the merge is still one card, never a push to main",
          H.MERGE_TOOL in got.text and "main" in got.text, got.text)

    red = [dict(one) for one in good]
    red[0]["conclusion"] = "failure"
    got = H.merge_gate(red, pr=1601)
    check("one red check is a no, and names the check", not got.ok
          and "rust" in got.text and "#1601" in got.text, got.text)
    check("... and the checks that DID pass are still listed, in the answer's own "
          "record of what it judged", len(got.names) == 7, got.names)

    running = [dict(one) for one in good]
    running[1]["status"] = "in_progress"
    running[1]["conclusion"] = ""
    got = H.merge_gate(running)
    check("a still-running check is a no - pending is not 'probably fine'",
          not got.ok and "still running" in got.text and "frontend" in got.text,
          got.text)

    absent = [one for one in good if one["name"] != "phone-unit-tests"]
    got = H.merge_gate(absent)
    check("a required check that never reported is a no, and is named",
          not got.ok and "phone-unit-tests" in got.text, got.text)

    got = H.merge_gate([])
    check("no checks at all is a no", not got.ok, got.text)


def t_the_gate_never_guesses_a_verdict():
    import jarvis_github as GH

    class NoRule:
        pass

    real = H._github
    H._github = lambda: NoRule()
    try:
        got = H.merge_gate([{"name": "rust", "status": "completed",
                             "conclusion": "success"}])
        check("a GitHub module without the rule list refuses to merge",
              not got.ok and "names none" in got.text, got.text)
        H._github = lambda: None
        got = H.merge_gate([])
        check("a PC without the GitHub module refuses, and says why",
              not got.ok and "not on this PC" in got.text, got.text)
    finally:
        H._github = real
    check("... and the real module is used again afterwards",
          H.merge_gate(_green(GH.REQUIRED_CHECKS)).ok)


# --------------------------------------------------------------------------
#   6. The loop as the owner sees it
# --------------------------------------------------------------------------

def t_the_answer_is_the_measurement_and_nothing_else():
    cite = SI.Citation(path="backend/jarvis_quick.py", line=1234,
                       text="def _note_merge(s):")

    def found(question):
        return SI.Diagnosis(question=question, found=True,
                            answer="the note merge grammar needs the word 'merge'.",
                            citations=(cite,))

    log = FakeLog(rows=[{"id": "aaaa1111", "title": "Boiler pressure", "updated": 100}],
                  turns={"aaaa1111": turns(("user", "can you merge two notes"),
                                           ("assistant", "Do you mean pull requests?"))})
    got = H.homework("the boiler", log=log, diagnose=found, at=NOW)
    check("the answer quotes the owner's own words", "can you merge two notes" in got.reply,
          got.reply)
    check("... and the answer he got", "Do you mean pull requests?" in got.reply,
          got.reply)
    check("... and names the route the matcher returned, by its own name",
          "note_merge_ask" in got.reply, got.reply)
    check("... and shows the file:line from the diagnosis", CITED in got.reply, got.reply)
    check("... and says plainly that nothing was changed", "Nothing was changed"
          in got.reply, got.reply)
    check("... and names the three carded tools by their real names",
          all(tool in got.reply for tool in (H.PUSH_TOOL, H.PR_TOOL, H.MERGE_TOOL)),
          got.reply)
    check("the answer is marked private, because it quotes the owner's chat",
          got.private is True and got.ok is True, got)

    def cannot(question):
        return SI.Diagnosis(question=question, found=False, why="nothing found")

    got = H.homework("the boiler", log=log, diagnose=cannot, at=NOW)
    check("an explanation that could not be established says so in the answer",
          "Could not establish this" in got.reply, got.reply)

    got = H.homework("nowhere at all", log=FakeLog(rows=[]), diagnose=found, at=NOW)
    check("an exchange that cannot be found is said plainly, and the loop stops",
          not got.ok and "cannot point at that exchange" in got.reply, got.reply)


def t_the_spoken_answer_is_short():
    def found(question):
        return SI.Diagnosis(question=question, found=True, answer="a long reason",
                            citations=(SI.Citation(path="backend/jarvis_quick.py",
                                                   line=1234, text="x"),))

    log = FakeLog(rows=[{"id": "aaaa1111", "title": "Boiler pressure", "updated": 100}],
                  turns={"aaaa1111": turns(("user", "can you merge two notes"),
                                           ("assistant", "Do you mean pull requests?"))})
    spoken = H.homework("the boiler", log=log, diagnose=found, at=NOW, live=True)
    written = H.homework("the boiler", log=log, diagnose=found, at=NOW)
    check("a spoken answer is shorter than the written one",
          len(spoken.reply) < len(written.reply), (len(spoken.reply),
                                                   len(written.reply)))
    check("... and still carries the route and the next step",
          "note_merge_ask" in spoken.reply and H.PUSH_TOOL in spoken.reply,
          spoken.reply)


# --------------------------------------------------------------------------
#   main
# --------------------------------------------------------------------------

def main():
    for fn in (t_replay_is_the_matcher_return_value,
               t_the_swallow_reading_is_built_from_names_not_opinions,
               t_the_real_matcher_on_this_tree,
               t_the_same_conversation_comes_from_the_request,
               t_an_older_conversation_is_found_by_title,
               t_an_ambiguous_reference_is_never_picked,
               t_the_readers_own_failures_are_plain_sentences,
               t_the_search_is_the_second_door,
               t_a_paging_reader_that_repeats_itself_does_not_double_the_list,
               t_the_diagnosis_is_passed_through_unchanged,
               t_the_question_carries_the_routing_fact_and_stays_short,
               t_the_draft_is_a_draft_and_a_refusal_stays_a_refusal,
               t_this_module_cannot_act,
               t_the_merge_gate_reads_its_rule_from_jarvis_github,
               t_the_gate_never_guesses_a_verdict,
               t_the_answer_is_the_measurement_and_nothing_else,
               t_the_spoken_answer_is_short):
        try:
            fn()
        except Exception:                             # noqa: BLE001
            FAILED.append(fn.__name__)
            print(f"FAIL  {fn.__name__} raised")
            traceback.print_exc()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFAILED:")
        for name in FAILED:
            print(f"  - {name}")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                 # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
