#!/usr/bin/env python3
"""test_web_access_truth.py - Jarvis tells the truth about what reaches the web.

    py -3 -B backend/test_web_access_truth.py

WHY THIS EXISTS (the owner's 2026-11-09 report)

The owner asked why Jarvis denied web browsing while `web_search` was switched
ON, and asked it to create a repository called "Fitness Band". Both were the
same fault in how Jarvis describes itself: FOUR different things leave this PC
for the internet, each with its own switch, and the answer treated "the web" as
one thing:

  (a) web search            - Settings, Web search + the web_search tool row
  (b) reading one web page  - the read_web_page tool, one card per address
  (c) browser control       - a real tab clicked and typed in (its own switch,
                              plus the second card's browser lane or Obscura)
  (d) the GitHub integration - a saved token plus its own tools, one card each

WHAT THIS SUITE PROVES, with no model, no socket and no real token:

  1. every one of those four questions ROUTES to the fixed answer (it does not
     reach the language model, which is what denied the capability);
  2. the answer names all four as SEPARATE things, and says ON or OFF for each
     from `jarvis_reach.view()` - the same rows both apps draw - and from
     `jarvis_github.connected()` / `jarvis_asks_first`;
  3. an OFF item carries the row's own reason and what turns it on, so "why
     was I refused" has a real answer;
  4. the GitHub half is separate from the three web halves, says whether a
     token is saved and how many of its seven tools are on;
  5. "are you able to create a repository?" is answered with the real carded
     action (and the real reason it is off), while the imperative "create a
     repository called Fitness Band" is DELIBERATELY not claimed - it must reach
     the model, which calls github_create_repo;
  6. the fixed words are the ones the model's own `self_portrait` carries
     (`jarvis_feature_guide.SELF_FACTS["internet_access"]`), so the
     deterministic answer and a model turn cannot say different things;
  7. the intent is read-only, so "cancel that" cannot undo a question.

Nothing here opens a socket, raises a card, or reads the owner's real token:
`jarvis_github._token` is replaced with "" for the whole run.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

# A temp config dir BEFORE any backend import: the gate opens an approval queue
# at import time, and this suite must not read or write the owner's own.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-web-truth-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ.pop("JARVIS_BACKEND", None)
(_TMP / "config").mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE / "rebuilt"))

import jarvis_asks_first as ASK          # noqa: E402
import jarvis_feature_guide as FG        # noqa: E402
import jarvis_github as GH               # noqa: E402
import jarvis_quick as Q                 # noqa: E402
import jarvis_reach as REACH             # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: counted on its own, never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


class NoSocket:
    """Refuses every real socket, for the whole run."""

    def __enter__(self):
        import socket
        self._socket = socket.socket
        self._pair = socket.socketpair

        def refuse(*_a, **_k):
            raise AssertionError("this suite must never open a socket")

        socket.socket = refuse
        socket.socketpair = refuse
        return self

    def __exit__(self, *_exc):
        import socket
        socket.socket = self._socket
        socket.socketpair = self._pair
        return False


class _NoToken:
    """The whole run: no token is saved, and the credential store is never read."""

    def __enter__(self):
        self._was = GH._token
        GH._token = lambda: ""
        return self

    def __exit__(self, *_exc):
        GH._token = self._was
        return False


def _row(id_, name, state, line, asks="Yes, every time"):
    return {"id": id_, "name": name, "state": state, "on": state == "on",
            "state_words": REACH.STATE_WORDS.get(state, state), "where": "",
            "asks": asks, "line": line}


def _view(**rows):
    """A `jarvis_reach.view()`-shaped answer with the four ids under test."""
    default = {
        "web_search": _row("web_search", "Web search", "on",
                           "Searches with DuckDuckGo."),
        "read_web_page": _row(
            "read_web_page", "Read one web page out loud", "off",
            'Off. Switch it on in Settings, "What asks first", on your PC (one '
            "approval card and Windows Hello)."),
        "browser": _row(
            "browser", "Browser control", "off",
            "Off: it needs the second graphics card's \"Browser control\" switch (a "
            "browser window you can see), or a browser with no window (Obscura), "
            "and both are off."),
    }
    default.update(rows)
    return {"available": True, "rows": list(default.values()), "tools": []}


def _with_view(view, fn):
    keep = REACH.view
    REACH.view = lambda *_a, **_k: view
    try:
        return fn()
    finally:
        REACH.view = keep


def _reply(sentence):
    intent = Q.match(sentence)
    if intent is None:
        return None, ""
    return intent, str(Q.run(intent, None, 0.0).reply)


def _answer(sentence, view=None):
    """Run one question with a chosen reach view and no token at all."""
    view = view or _view()
    keep = REACH.view
    REACH.view = lambda *_a, **_k: view
    try:
        with _NoToken():
            return _reply(sentence)
    finally:
        REACH.view = keep


# --------------------------------------------------------------------------
#   1. the four questions route deterministically
# --------------------------------------------------------------------------

#: The owner's own sentence, and the shapes a person actually types. Each must
#: reach the fixed answer rather than the model: that is the whole fix.
ROUTES = (
    "can you browse the web?",
    "browse the web",
    "do you have web browsing?",
    "do you have internet access?",
    "are you able to browse the internet?",
    "are you able to read a web page?",
    "do you have browser control?",
    "control my browser",
    "search the web",
    "why did you say you can't browse the web?",
    "why can't you access the internet?",
    "what web access do you have?",
)


def t_the_four_questions_route_to_the_fixed_answer():
    for sentence in ROUTES:
        intent = Q.match(sentence)
        got = intent.name if intent is not None else None
        check(f"{sentence!r} -> internet_access", got == "internet_access", got)
    check("the answer is read-only (cancel that cannot undo a question)",
          "internet_access" in Q.READ_ONLY_INTENTS)


def t_a_real_task_with_extra_words_still_reaches_its_own_path():
    """The bare phrase is claimed; a phrase with a TASK in it is not.

    `normalise()` strips a leading "can you", so "browse the web" is the only
    shape that is a capability question and nothing else. "browse the web for
    flights" is a real request and must keep the path that can do something.
    """
    for sentence in ("browse the web for cheap flights to Rome",
                     "search the web for the weather in Tokyo",
                     "read this page https://example.com",
                     "create a repository called Fitness Band",
                     "make a repository named Fitness Band"):
        intent = Q.match(sentence)
        got = intent.name if intent is not None else None
        check(f"{sentence!r} is not answered as a capability question",
              got != "internet_access", got)


# --------------------------------------------------------------------------
#   2. the answer distinguishes all four, with live state
# --------------------------------------------------------------------------


def t_the_answer_names_all_four_and_their_state():
    _intent, reply = _answer("can you browse the web?")
    for name in ("Web search", "Read one web page out loud", "Browser control",
                 "GitHub integration"):
        check(f"the answer names {name!r}", name.lower() in reply.lower(), reply[:400])
    check("it says one being on never turns on another",
          "never turns on another" in reply, reply[:300])
    check("web search is reported ON from the reach row",
          "Web search is On." in reply, reply[:600])
    check("reading one page is reported OFF, with the row's own reason",
          "Read one web page out loud is Off." in reply
          and 'switch it on in settings, "what asks first"' in reply.lower(),
          reply[:900])
    check("browser control is reported OFF, with its own lane reason",
          "Browser control is Off." in reply
          and "second graphics card" in reply, reply[:1200])
    check("it never states the old blanket denial as its own answer",
          not reply.strip().lower().startswith("i cannot browse the web"), reply[:120])


def t_an_on_item_says_it_asks_first_and_an_off_item_says_how_to_turn_it_on():
    view = _view(
        web_search=_row("web_search", "Web search", "off",
                        "Off: you switched web search off. Turn it back on in "
                        "Settings, Web search (a card asks you first)."),
        read_web_page=_row("read_web_page", "Read one web page out loud", "on",
                           "Fetches the one address the card shows."),
    )
    _intent, reply = _answer("do you have web browsing?", view)
    check("a switch that is off says so and says how to turn it on",
          "Web search is Off." in reply
          and "turn it back on in settings, web search" in reply.lower(),
          reply[:900])
    check("a switch that is on says it is on", "Read one web page out loud is On."
          in reply, reply[:900])
    check("... and that it asks first", "asks you first every time" in reply.lower(),
          reply[:900])

    # All four off: every one is said OFF, and nothing is claimed as available.
    view = _view(
        web_search=_row("web_search", "Web search", "off",
                        "Off. Switch it on in Settings."),
        browser=_row("browser", "Browser control", "off",
                     "Off: it needs the second card's browser lane."),
    )
    _intent, reply = _answer("can you browse the web?", view)
    check("with every switch off, all three web rows are said Off",
          reply.count(" is Off.") >= 3, reply[:1200])


def t_the_github_half_is_separate_and_read_from_the_modules():
    _intent, reply = _answer("can you browse the web?")
    check("with no token the GitHub half says so",
          "no GitHub token is saved" in reply, reply[-500:])
    check("... and says none of its seven tools is on",
          "none of its 7 tools is switched on" in reply, reply[-500:])
    check("... and that creating a repository is one of its actions",
          "creating one new empty repository" in reply.lower()
          and "own card" in reply.lower(), reply[-500:])

    keep = ASK.tools_enabled_set
    try:
        ASK.tools_enabled_set = lambda: {"github_list", "github_create_repo"}
        _intent, reply = _answer("can you browse the web?")
    finally:
        ASK.tools_enabled_set = keep
    check("two tools on says two of seven", "2 of its 7 tools are switched on"
          in reply, reply[-500:])

    # A saved token is said as a saved token, never as a working connection.
    saved = GH.connected
    try:
        GH.connected = lambda: True
        _intent, reply = _answer("can you browse the web?")
    finally:
        GH.connected = saved
    check("a saved token says a GitHub token is saved",
          "a GitHub token is saved" in reply, reply[-500:])


# --------------------------------------------------------------------------
#   3. the fixed words are the model's own digest (one source)
# --------------------------------------------------------------------------


def t_the_fixed_words_are_the_models_own_digest():
    check("internet_access is one of the bounded SELF_FACT_IDS",
          "internet_access" in FG.SELF_FACT_IDS, FG.SELF_FACT_IDS)
    row = FG.self_fact("internet_access") or {}
    digest = str(row.get("digest") or "")
    sentence = str(row.get("sentence") or "")
    check("the row has both a digest and an owner-facing sentence",
          len(digest) > 100 and len(sentence) > 100, (len(digest), len(sentence)))
    low = digest.lower()
    for word in ("web search", "reading one web page", "browser control",
                 "github integration"):
        check(f"the digest names {word!r}", word in low, digest[:400])
    check("the digest says they are separate", "separate" in low, digest[:400])
    check("the digest forbids the blanket denial",
          "cannot browse the web" in low and "which of the four is off" in low,
          digest[:600])
    check("the model's self_portrait reads every SELF_FACT_IDS digest",
          "SELF_FACT_IDS" in (HERE / "jarvis_agent.py").read_text(encoding="utf-8"))
    # The chat answer IS that sentence plus the live rows: one source.
    _intent, reply = _answer("can you browse the web?")
    check("the chat answer opens with the feature guide's own sentence",
          reply.startswith(sentence[:80]), reply[:200])


# --------------------------------------------------------------------------
#   4. the create-a-repository question has a real, carded answer
# --------------------------------------------------------------------------


def t_the_create_repository_question_is_answered_with_the_real_action():
    intent, reply = _answer("are you able to create a repository?")
    check("the question is github_self, not the model",
          intent is not None and intent.name == "github_self"
          and intent.f.get("shape") == "create_repo",
          (intent.name, intent.f) if intent else None)
    for needle in ("Yes", "one new, empty repository", "approval card",
                   "never an organization", "Fitness-Band", "does not allow spaces"):
        check(f"the answer says {needle!r}", needle.lower() in reply.lower(),
              reply[:900])
    check("with no token it says the token is missing",
          "no token is saved" in reply.lower(), reply[-400:])

    keep = ASK.tools_enabled_set
    try:
        ASK.tools_enabled_set = lambda: {"github_create_repo"}
        _intent, reply = _answer("are you able to create a repository?")
    finally:
        ASK.tools_enabled_set = keep
    check("its own tool being on is said", "is switched on" in reply, reply[:900])

    keep = ASK.tools_enabled_set
    try:
        ASK.tools_enabled_set = lambda: set()
        _intent, reply = _answer("are you able to create a repository?")
    finally:
        ASK.tools_enabled_set = keep
    check("its own tool being off is said, with what turns it on",
          "switched OFF" in reply and "settings, what asks first" in reply.lower(),
          reply[:1200])
    check("the answer never claims a merge card or an automatic create",
          "merge card" not in reply.lower() or "no merge card" in reply.lower(),
          reply[:400])


# --------------------------------------------------------------------------

def main() -> int:
    try:
        with NoSocket(), _NoToken():
            t_the_four_questions_route_to_the_fixed_answer()
            t_a_real_task_with_extra_words_still_reaches_its_own_path()
            t_the_answer_names_all_four_and_their_state()
            t_an_on_item_says_it_asks_first_and_an_off_item_says_how_to_turn_it_on()
            t_the_github_half_is_separate_and_read_from_the_modules()
            t_the_fixed_words_are_the_models_own_digest()
            t_the_create_repository_question_is_answered_with_the_real_action()
    except Exception:
        FAILED.append("the suite itself raised")
        traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  FAILED  {name}")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
