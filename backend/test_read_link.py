"""test_read_link.py - "read this link" in chat (2026-11-03).

    python -B backend/test_read_link.py

THE OWNER'S ASK: "read this link", "read this YouTube video and tell me about
it", "summarise this page: <url>". Before this the two readers existed only
behind their own doors - the Quiz page's route for a YouTube link, and the
`read_web_page` model tool (off by default) for a page - so a pasted link in
ordinary words reached the local model, which could read neither.

WHAT THIS SLICE IS. A fast-path intent in jarvis_quick (`read_link`) that
notices an http(s) link in the owner's own sentence and then hands the link to
whichever reader already owns it:

  * a YouTube link  -> jarvis_youtube.parse_link / card / fetch_captions /
                       clean_text, under that module's own action
                       `youtube_captions_read`;
  * any other link  -> jarvis_readpage.prepare / describe / run, under
                       `read_web_page`.

Since Q2 (Gemini's ruling, 2026-11-03) the sentence does not need a read verb at
all when the link IS the message ("https://...") or the link plus a question
about it ("https://... what is this about?"). A link inside a STATEMENT ("here
is a link ...") or a browser command ("open <url> in my browser") is still not a
read, and a watch still belongs to the watcher. The answer's first line carries
the canonical address the card showed, and the page is kept in memory for that
conversation for 900 seconds, so a follow-up is answered with NO second card and
NO second fetch (`read_link_q`).

It adds NO route, NO model tool, NO gate action, NO tier and NO permission of
its own, and it never edits the gate. The card is each reader's own, word for
word; one link is one card; a card that is not approved fetches nothing.

WHAT IS PROVEN HERE, with the gate and the transport stubbed (never a real
card, never a real network fetch, never the owner's files):

  1. ONE CARD, and the Quiz page's own words. A youtube.com or youtu.be link
     in an ordinary sentence makes EXACTLY ONE gate call, under
     `youtube_captions_read`, with a prompt byte-identical to
     `jarvis_youtube.card(parse_link(link))` - the text the Quiz page shows.
  2. ONE CARD for any other link, under `read_web_page`, with the page
     reader's own card text, and `ONE_PAGE_LINE` in the answer.
  3. A DECLINED (or timed-out, or unraisable) card FETCHES NOTHING: the fetch
     stub is never called and the answer claims nothing was fetched. No
     standing permission exists - a second link is a second card.
  4. A video with no captions says so in the caption reader's own sentence and
     invents no summary; a link that is not a page (a PDF) is refused with the
     page reader's own sentence.
  5. "tell me when <url> changes" still routes to `tellme_page`, a WATCH on a
     page, not to the reader - by order in `_match` and again by the matcher's
     own refusal.
  6. The turn is recorded as having read outside text: `Result.read` is
     `["youtube_captions_read"]` or `["read_web_page"]`, and a turn carrying
     that mark refuses `change_setting` with `SETTINGS_AFTER_OUTSIDE` -
     a rule to keep, not fight.

WHAT IT DOES NOT PROVE: a real YouTube fetch, a real page fetch, a real card
being answered by a person, or Live speaking the answer. Those stay
owner-tested.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: This suite must not litter the tree it tests: no .pyc from a plain run.
sys.dont_write_bytecode = True

#: Before ANY import of the backend: a temp config dir, so nothing here can
#: reach the owner's own settings, receipts or chat history.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-read-link-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
(_TMP / "config").mkdir(parents=True, exist_ok=True)
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")
(_TMP / "logs").mkdir(parents=True, exist_ok=True)

#: THIS SUITE TESTS THIS CHECKOUT, never the owner's live install. With
#: JARVIS_BACKEND set (which it is on his PC, and in a shell that exports it)
#: `require_shipped` would compare this tree's modules with the installed ones
#: and stop the run - correctly, because a suite must not report on a copy it
#: did not test. The same two pops test_live_parity.py makes, for the same
#: reason.
os.environ.pop("JARVIS_BACKEND", None)
os.environ.pop("JARVIS_CONFIG_DIR", None)

sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_youtube.py", "jarvis_readpage.py",
                "jarvis_agent.py", "jarvis_settings_registry.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_agent as AG  # noqa: E402
import jarvis_local_http as LH  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_readpage as RP  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402
import jarvis_youtube as YT  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """Printed and counted apart. A check that did not run is not a pass."""
    SKIPPED.append(why)
    print(f"SKIP  {why}")


# --------------------------------------------------------------------------
#   The two things that must never be real here: the card and the fetch
# --------------------------------------------------------------------------

class FakeGate:
    """The one gate's stand-in: records every call, answers as a person did.

    It is handed to the runner as `gate=`, so the real `jarvis_gate.check` -
    which BLOCKS on the "ask" tier - is never entered by this suite.
    """

    def __init__(self, allowed=True, outcome="approved", tier="ask", reason=""):
        self.allowed = allowed
        self.outcome = outcome
        self.tier = tier
        self.reason = reason
        self.calls = []

    def __call__(self, action, detail, prompt):
        self.calls.append({"action": action, "detail": dict(detail or {}),
                           "prompt": prompt})
        return types.SimpleNamespace(allowed=self.allowed, outcome=self.outcome,
                                     tier=self.tier, reason=self.reason, action=action)

    def answers(self):
        return [c["action"] for c in self.calls]


def never_tier(action):
    """A tier reader that is always "ask" - the shipped setting for both."""
    return "ask"


def auto_tier(action):
    return "auto"


YOUTUBE_URLS = ("https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "https://youtu.be/dQw4w9WgXcQ",
                "https://m.youtube.com/watch?v=dQw4w9WgXcQ")

#: The caption reader refuses captions shorter than `jarvis_youtube.TEXT_MIN`
#: (200 characters) with its own "too short" sentence - `fetch_captions` makes
#: that check, not this slice - so a fixture meant to READ has to be long
#: enough to pass it.
CAPTIONS = [{"text": "Hello and welcome to the kettle review.", "start": 0.0},
            {"text": "This kettle boils four cups in about four minutes.", "start": 2.5},
            {"text": "It has a stainless steel body, a cool-touch handle and a "
                     "removable limescale filter, and it pours without dripping.",
             "start": 5.0},
            {"text": "The lid lifts off with one hand, which matters more than it "
                     "sounds when the kettle is full and the tap is behind it.",
             "start": 9.5},
            {"text": "That is all for today, thanks for watching.", "start": 14.0}]

SHORT_CAPTIONS = [{"text": "Too short to read.", "start": 0.0}]


class TranscriptsDisabled(Exception):
    """Named exactly as the caption library names its own error, because
    jarvis_youtube maps a failure by CLASS NAME (`_code_of`)."""


class _NoNetwork:
    """`private_fetch_problem` answers "" and the page fetch is injected.

    The only way to get past `RP.prepare` without a real DNS lookup, and past
    `RP.run` without a real GET - the same two replacements test_readpage.py
    makes, for the same reason.
    """

    def __init__(self, body=b"", kind="text/html; charset=utf-8", boom=None):
        self.body, self.kind, self.boom = body, kind, boom
        self.fetches = []

    def fetch(self, url):
        self.fetches.append(url)
        if self.boom is not None:
            raise self.boom
        return self.body, self.kind

    def __enter__(self):
        self._real_problem = LH.private_fetch_problem
        self._real_deps = RP.DEPS
        LH.private_fetch_problem = lambda url: ""
        RP.DEPS = RP.Deps(fetch=self.fetch)
        return self

    def __exit__(self, *exc):
        LH.private_fetch_problem = self._real_problem
        RP.DEPS = self._real_deps
        return False


def a_page(words: str) -> bytes:
    return (b"<html><head><title>The Kettle</title></head><body><main><p>"
            + words.encode("utf-8") + b"</p></main></body></html>")


PAGE_WORDS = ("The kettle holds one and a half litres. " * 6).strip()


class _Captions:
    """A stand-in transport for the caption reader, installed through the
    module's OWN injection point (`jarvis_youtube.configure(fetch=...)`)."""

    def __init__(self, snippets=None, boom=None):
        self.snippets = CAPTIONS if snippets is None else snippets
        self.boom = boom
        self.calls = []

    def __call__(self, video_id, languages):
        self.calls.append((video_id, tuple(languages)))
        if self.boom is not None:
            raise self.boom
        return list(self.snippets)

    def __enter__(self):
        YT.configure(fetch=self)
        return self

    def __exit__(self, *exc):
        YT._reset_for_tests()
        return False


def read_link(words, gate, tier=None):
    """One turn through the REAL matcher and the REAL runner."""
    intent = Q.match(words)
    if intent is None or intent.name != "read_link":
        return None, intent
    res = Q._run_read_link(intent.f, gate=gate, tier_of=tier or never_tier)
    return res, intent


# --------------------------------------------------------------------------
#   1. A YouTube link: ONE card, and the Quiz page's exact words
# --------------------------------------------------------------------------

def t_a_youtube_link_is_one_card_with_the_quiz_pages_words():
    for url in YOUTUBE_URLS:
        gate = FakeGate()
        with _Captions() as caps:
            res, intent = read_link(f"read this YouTube video and tell me about it {url}",
                                    gate)
        check(f"a YouTube link is a read_link: {url}",
              intent is not None and intent.name == "read_link"
              and intent.f.get("url") == url, None if intent is None else intent.f)
        check(f"...and it raised EXACTLY ONE card: {url}", len(gate.calls) == 1,
              gate.calls)
        check(f"...under the caption reader's own action: {url}",
              gate.calls and gate.calls[0]["action"] == "youtube_captions_read"
              == YT.ACTION, gate.answers())
        parsed = YT.parse_link(url)
        check(f"...whose text is the Quiz page's own, byte for byte: {url}",
              gate.calls and gate.calls[0]["prompt"] == YT.card(parsed),
              (str(gate.calls[0]["prompt"])[:120] + "..." if gate.calls else None))
        check(f"...and the captions were fetched once, for that video: {url}",
              caps.calls == [(parsed["video_id"], tuple(YT.DEFAULT_LANGUAGES))], caps.calls)
        check(f"...the answer quotes the captions and claims the read: {url}",
              res is not None and "kettle review" in res.reply
              and res.read == ["youtube_captions_read"],
              (res.reply if res is not None else None, res.read if res is not None else None))
        check(f"...and it carries the caption reader's own outside-text line: {url}",
              res is not None and Q.READ_LINK_CAPTIONS_OUTSIDE in res.reply,
              res.reply if res is not None else None)
        check(f"...and it does NOT promise a quiz the chat did not run: {url}",
              res is not None and "Your answers are marked" not in res.reply,
              res.reply if res is not None else None)


def t_a_playlist_link_answers_in_the_readers_own_words_and_asks_nothing():
    gate = FakeGate()
    with _Captions() as caps:
        res, intent = read_link("read this https://www.youtube.com/playlist?list=PLabc123",
                                gate)
    check("a playlist link is still a read_link", intent is not None)
    check("...it raises NO card (there is nothing to read)",
          gate.calls == [], gate.calls)
    check("...it fetches nothing", caps.calls == [], caps.calls)
    check("...and it answers in the caption reader's own words",
          res is not None and res.reply == YT.CLASSES["playlist_link"][1],
          res.reply if res is not None else None)
    check("...with no read recorded, because it read nothing",
          res is not None and res.read == [], res.read if res is not None else None)


# --------------------------------------------------------------------------
#   2. Any other link: ONE card under read_web_page, and the one-page line
# --------------------------------------------------------------------------

def t_any_other_link_is_one_card_under_read_web_page():
    gate = FakeGate()
    with _NoNetwork(a_page(PAGE_WORDS)) as net:
        res, intent = read_link("summarise this page: https://example.com/kettle", gate)
    check("a page link is a read_link",
          intent is not None and intent.f.get("url") == "https://example.com/kettle",
          None if intent is None else intent.f)
    check("...it raised EXACTLY ONE card", len(gate.calls) == 1, gate.calls)
    check("...under the page reader's own action",
          gate.calls and gate.calls[0]["action"] == "read_web_page" == RP.ACTION,
          gate.answers())
    page = RP.Page("https://example.com/kettle", 0)
    check("...whose text is the page reader's own card, byte for byte",
          gate.calls and gate.calls[0]["prompt"] == RP.describe(page),
          str(gate.calls[0]["prompt"])[:160] if gate.calls else None)
    check("...and only that ONE address was fetched, once",
          net.fetches == ["https://example.com/kettle"], net.fetches)
    check("...the answer holds the one-page line",
          res is not None and RP.ONE_PAGE_LINE in res.reply,
          res.reply if res is not None else None)
    check("...and the page reader's outside-text line",
          res is not None and RP.OUTSIDE_LINE in res.reply,
          res.reply if res is not None else None)
    check("...the page's own words are quoted",
          res is not None and "one and a half litres" in res.reply,
          res.reply if res is not None else None)
    check("...and the turn is recorded as having read a page",
          res is not None and res.read == ["read_web_page"],
          res.read if res is not None else None)


def t_a_pdf_is_refused_in_the_page_readers_words():
    gate = FakeGate()
    with _NoNetwork(b"%PDF-1.4 not a page at all",
                    kind="application/pdf") as net:
        res, _ = read_link("read this link https://example.com/report.pdf", gate)
    check("a non-page body is refused, not decoded",
          res is not None and "not a web page" in res.reply
          and "application/pdf" in res.reply, res.reply if res is not None else None)
    check("...the card WAS raised first (the tier says ask every time)", len(gate.calls) == 1)
    check("...the address really was fetched once", net.fetches == [
        "https://example.com/report.pdf"], net.fetches)
    check("...and nothing is claimed as read", res is not None and res.read == [],
          res.read if res is not None else None)


# --------------------------------------------------------------------------
#   3. A card that is not approved fetches NOTHING
# --------------------------------------------------------------------------

def t_a_declined_card_fetches_nothing_and_claims_nothing():
    for outcome, action in (("denied", "youtube"), ("timed_out", "youtube"),
                            ("denied", "page"), ("refused", "page")):
        gate = FakeGate(allowed=False, outcome=outcome)
        if action == "youtube":
            with _Captions() as caps:
                res, _ = read_link("read this link https://youtu.be/dQw4w9WgXcQ", gate)
            touched = caps.calls
        else:
            with _NoNetwork(a_page(PAGE_WORDS)) as net:
                res, _ = read_link("read this link https://example.com/kettle", gate)
            touched = net.fetches
        want = (YT.STATE_WORDS.get(outcome) if action == "youtube"
                else Q.READ_LINK_NO.get(outcome))
        check(f"a {outcome} {action} card fetches nothing", touched == [], touched)
        check(f"a {outcome} {action} card never touches the reader at all",
              len(gate.calls) == 1 and res is not None and res.reply == want,
              None if res is None else res.reply)
        check(f"...and it claims no read ({outcome} {action})",
              res is not None and res.read == [],
              res.read if res is not None else None)


def t_a_tier_that_is_not_ask_raises_no_card_at_all():
    gate = FakeGate()
    with _Captions() as caps:
        res, _ = read_link("read this link https://youtu.be/dQw4w9WgXcQ", gate,
                           tier=auto_tier)
    check("a tier other than ask raises no card", gate.calls == [], gate.calls)
    check("...fetches nothing", caps.calls == [], caps.calls)
    check("...and says so in the reader's own sentence",
          res is not None and res.reply == Q.READ_LINK_TIER_NOT_ASK
          == YT.CLASSES["tier_not_ask"][1],
          None if res is None else res.reply)


def t_each_link_is_its_own_card_never_a_standing_permission():
    first, second = FakeGate(), FakeGate(allowed=False, outcome="denied")
    with _Captions():
        read_link("read this link https://youtu.be/dQw4w9WgXcQ", first)
        res, _ = read_link("read this link https://youtu.be/dQw4w9WgXcQ", second)
    check("two links are two cards, not one permission", len(first.calls) == 1
          and len(second.calls) == 1, (len(first.calls), len(second.calls)))
    check("...and the second one being declined fetches nothing",
          res is not None and res.reply == YT.STATE_WORDS["denied"]
          and res.read == [], None if res is None else res.reply)


# --------------------------------------------------------------------------
#   4. No captions: say so, invent nothing
# --------------------------------------------------------------------------

def t_a_video_with_no_captions_says_so_and_invents_no_summary():
    gate = FakeGate()
    with _Captions(boom=TranscriptsDisabled("nope")) as caps:
        res, _ = read_link("read this video and tell me about it "
                           "https://youtu.be/dQw4w9WgXcQ", gate)
    check("the card was raised before the fetch", len(gate.calls) == 1, gate.calls)
    check("...the fetch was tried once", len(caps.calls) == 1, caps.calls)
    check("...and the answer is the caption reader's own 'no captions' sentence",
          res is not None and res.reply == YT.CLASSES["no_captions"][1],
          None if res is None else res.reply)
    check("...no summary is invented and no read is claimed",
          res is not None and res.read == []
          and "They begin" not in res.reply and "It says" not in res.reply,
          None if res is None else (res.reply[:80], res.read))


def t_captions_too_short_to_read_say_so():
    """The caption reader's own 200-character floor, not this slice's rule."""
    gate = FakeGate()
    with _Captions(snippets=SHORT_CAPTIONS):
        res, _ = read_link("read this link https://youtu.be/dQw4w9WgXcQ", gate)
    check("captions under the reader's own floor are refused in its words",
          res is not None and res.reply == YT.CLASSES["too_little_text"][1],
          None if res is None else res.reply)
    check("...and nothing is recorded as read",
          res is not None and res.read == [],
          res.read if res is not None else None)


# --------------------------------------------------------------------------
#   5. It YIELDS to tellme_page - a watch is not a read
# --------------------------------------------------------------------------

def t_tellme_page_still_wins():
    words = "tell me when https://example.com/kettle changes"
    got = Q.match(words)
    check("'tell me when <url> changes' is still the tellme_page watch",
          got is not None and got.name == "tellme_page"
          and got.f.get("url") == "https://example.com/kettle",
          None if got is None else (got.name, got.f))
    check("...and the read-link matcher refuses that sentence itself",
          Q._read_link_intent(words, words) is None,
          Q._read_link_intent(words, words))
    for words in ("read this page and tell me when https://example.com/k changes",
                  "let me know when https://example.com/k changes"):
        got = Q.match(words)
        check(f"a watch sentence is never a read: {words!r}",
              got is None or got.name != "read_link",
              None if got is None else got.name)


def t_a_link_with_no_read_verb_is_only_ours_when_it_is_the_message():
    """A pasted link is a read; a link inside a statement or a command is not.

    Q2 (Gemini's ruling, 2026-11-03): a bare pasted URL - or a URL plus a
    question about it - reaches the reader with the SAME one card per URL. The
    statements and the browser command keep their own paths: a link he pasted
    to talk about must not raise a card.
    """
    for words in ("here is a link https://example.com/kettle",
                  "open https://example.com/kettle in my browser",
                  "i saved https://example.com/kettle for later"):
        got = Q.match(words)
        check(f"a link inside a statement or command is left alone: {words!r}",
              got is None or got.name != "read_link",
              None if got is None else got.name)
    for words in ("https://example.com/kettle",
                  "https://example.com/kettle what is this about?",
                  "https://example.com/kettle is this any good?",
                  "what is this: https://example.com/kettle"):
        got = Q.match(words)
        check(f"a pasted link is a read_link: {words!r}",
              got is not None and got.name == "read_link"
              and got.f.get("url") == "https://example.com/kettle",
              None if got is None else (got.name, got.f))


# --------------------------------------------------------------------------
#   5b. Q2: ONE card per URL, the canonical address on the FIRST line, and the
#       page kept for 15 minutes so a follow-up needs no second card
# --------------------------------------------------------------------------

KEEP_PAGE = ("The kettle holds one and a half litres and pours without dripping. "
             "Its limescale filter lifts out with one hand. It is made of stainless "
             "steel, and the handle stays cool even when the water is boiling.")


def t_a_pasted_link_reads_once_and_names_the_card_address_first():
    gate = FakeGate()
    Q._READ_LINK_KEPT.clear()
    try:
        with _NoNetwork(a_page(KEEP_PAGE)) as net:
            res, intent = read_link("https://example.com/kettle", gate)
        check("a bare pasted link is a read_link",
              intent is not None and intent.f.get("url") == "https://example.com/kettle",
              None if intent is None else intent.f)
        check("...it raised EXACTLY ONE card", len(gate.calls) == 1, gate.calls)
        check("...under the page reader's own action",
              gate.calls and gate.calls[0]["action"] == "read_web_page", gate.answers())
        check("...and fetched that one address once",
              net.fetches == ["https://example.com/kettle"], net.fetches)
        first = (res.reply.split("\n")[0] if res is not None else "")
        check("...and the FIRST line carries the canonical address",
              first.startswith("Read from https://example.com/kettle"),
              res.reply if res is not None else None)
        check("...the page's own words are still quoted",
              res is not None and "one and a half litres" in res.reply,
              res.reply if res is not None else None)
        check("...and the turn is recorded as having read a page",
              res is not None and res.read == ["read_web_page"],
              res.read if res is not None else None)
    finally:
        Q._READ_LINK_KEPT.clear()


def t_the_address_in_the_answer_is_the_cards_never_one_from_the_page():
    gate = FakeGate()
    Q._READ_LINK_KEPT.clear()
    body = a_page(KEEP_PAGE + " More at https://other.example/not-the-card ")
    try:
        with _NoNetwork(body):
            res, _ = read_link("https://example.com/kettle", gate)
        check("the answer opens with the CARD's address",
              res is not None and res.reply.startswith(
                  "Read from https://example.com/kettle"),
              res.reply if res is not None else None)
        head = res.reply.split("It says:")[0] if res is not None else ""
        check("...and never an address taken from the page's own words",
              "other.example" not in head, head)
    finally:
        Q._READ_LINK_KEPT.clear()


def t_a_follow_up_answers_from_the_kept_page_with_no_card_and_no_fetch():
    gate = FakeGate()
    Q._READ_LINK_KEPT.clear()
    try:
        with _NoNetwork(a_page(KEEP_PAGE)) as net:
            first, _ = read_link("https://example.com/kettle", gate)
            check("the page was read once", first is not None and len(gate.calls) == 1,
                  gate.calls)
            # The SAME turn's conversation, one sentence later.
            Q._read_link_remember("conv-kettle", "https://example.com/kettle",
                                  "The Kettle", KEEP_PAGE)
            got = Q.match("what does it say about the limescale filter",
                          conversation="conv-kettle")
            check("a follow-up about the page is its own intent",
                  got is not None and got.name == "read_link_q",
                  None if got is None else got.name)
            res = Q._run_read_link_q(got.f, "conv-kettle") if got is not None else None
            check("...it raises NO second card", len(gate.calls) == 1, gate.answers())
            check("...it fetches NOTHING new",
                  net.fetches == ["https://example.com/kettle"], net.fetches)
            check("...it answers from the kept words",
                  res is not None and "limescale filter" in res.reply,
                  res.reply if res is not None else None)
            check("...it names the address it is quoting from",
                  res is not None and "https://example.com/kettle" in res.reply,
                  res.reply if res is not None else None)
            check("...and it does not claim a fresh read",
                  res is not None and res.read == [], res.read if res is not None else None)
            # A word the page does not have: said plainly, naming the limit.
            got = Q.match("what does it say about the warranty",
                          conversation="conv-kettle")
            res = Q._run_read_link_q(got.f, "conv-kettle") if got is not None else None
            check("a word the kept page does not have is said plainly",
                  res is not None and "do not mention" in res.reply
                  and "characters" in res.reply, res.reply if res is not None else None)
    finally:
        Q._READ_LINK_KEPT.clear()


def t_a_kept_page_lasts_fifteen_minutes_and_one_conversation():
    Q._READ_LINK_KEPT.clear()
    try:
        Q._read_link_remember("conv-a", "https://example.com/kettle", "The Kettle",
                              KEEP_PAGE, now=1000.0)
        check("the page is kept for 15 minutes",
              Q.READ_LINK_KEEP_SECONDS == 900, Q.READ_LINK_KEEP_SECONDS)
        check("...it is there 14 minutes later",
              Q._read_link_kept("conv-a", now=1000.0 + 840) is not None)
        check("...and gone one second past 15 minutes",
              Q._read_link_kept("conv-a", now=1000.0 + 901) is None)
        check("...another conversation never sees it",
              Q._read_link_kept("conv-b", now=1000.0 + 60) is None)
        check("...and with nothing kept a follow-up is not ours",
              Q.match("what does it say about the kettle", conversation="conv-none")
              is None)
        # A new page in the same chat replaces the old one.
        Q._read_link_remember("conv-a", "https://example.com/teapot", "The Teapot",
                              "A teapot holds less.", now=1000.0 + 60)
        kept = Q._read_link_kept("conv-a", now=1000.0 + 120)
        check("a new page in the same chat replaces the old one",
              kept is not None and kept["url"] == "https://example.com/teapot", kept)
    finally:
        Q._READ_LINK_KEPT.clear()


# --------------------------------------------------------------------------
#   6. The turn is marked as having read outside text, and that mark refuses
#      a settings change - the rule that is kept, not fought
# --------------------------------------------------------------------------

class _Shaped:
    """A `_TurnWatch` with exactly one shaped-turn signal set, so a test can
    say which one it is testing."""

    def __init__(self, **kw):
        self.watch = AG._TurnWatch(None, None, tainted=kw.pop("tainted", False))
        for name, value in kw.items():
            setattr(self.watch, name, value)


class _Recording:
    """A stand-in switch that records every setter call, so "nothing was
    changed" can be checked rather than believed."""

    def __init__(self):
        self.calls = []

    def setting(self, key="a test setting"):
        rec = self

        def set_(on, *, peer=None, local=None):
            rec.calls.append(bool(on))
            return R.Outcome(True, "Done.")

        return R.BoolSetting(key, (key,), None, set_)


def t_a_link_read_refuses_a_settings_change_in_that_turn():
    recording = _Recording()
    fake = recording.setting("a test setting")
    real = R.BOOL_SETTINGS
    R.BOOL_SETTINGS = tuple(real) + (fake,)
    try:
        convo, steps = [], []
        call = {"id": "call-1", "function": {"name": AG.SETTINGS_TOOL,
                                             "arguments": {"setting": "a test setting",
                                                           "value": "on"}}}
        shaped = _Shaped(read=["read_web_page"])
        check("a turn that read a link counts as shaped by outside text",
              AG._settings_turn_is_shaped(shaped.watch) is True)
        AG._settings_call({"setting": "a test setting", "value": "on"}, call, convo,
                          steps, lambda *a, **k: None, watch=shaped.watch)
        out = json.loads(convo[-1]["content"])
        check("...and change_setting is refused with SETTINGS_AFTER_OUTSIDE",
              out.get("changed") is False and out.get("error") == AG.SETTINGS_AFTER_OUTSIDE,
              out)
        check("...and the setting's own setter never ran", recording.calls == [],
              recording.calls)
    finally:
        R.BOOL_SETTINGS = real


def t_the_result_carries_the_read_mark_the_refusal_reads():
    gate = FakeGate()
    with _Captions():
        res, _ = read_link("read this link https://youtu.be/dQw4w9WgXcQ", gate)
    check("a YouTube read is marked read=youtube_captions_read",
          res is not None and res.read == ["youtube_captions_read"],
          res.read if res is not None else None)
    with _NoNetwork(a_page(PAGE_WORDS)):
        res2, _ = read_link("read this link https://example.com/kettle", gate)
    check("a page read is marked read=read_web_page",
          res2 is not None and res2.read == ["read_web_page"],
          res2.read if res2 is not None else None)
    check("...and that mark is exactly the signal that refuses a setting",
          AG._settings_turn_is_shaped(_Shaped(read=res.read).watch) is True)


# --------------------------------------------------------------------------
#   7. What this slice deliberately did NOT add
# --------------------------------------------------------------------------

def t_the_caption_readers_own_words_are_cut_not_rewritten():
    """The read path quotes the caption reader's outside-text sentence, but only
    its FIRST sentence: the second one is about the Quiz page's quiz, which a
    chat read does not run. Cut, never re-worded."""
    check("the read path's outside-text sentence is the module's own, as a prefix",
          YT.OUTSIDE_LINE.startswith(Q.READ_LINK_CAPTIONS_OUTSIDE),
          (Q.READ_LINK_CAPTIONS_OUTSIDE, YT.OUTSIDE_LINE))
    check("...and the quiz half is not in the read path's sentence",
          "Your answers are marked" not in Q.READ_LINK_CAPTIONS_OUTSIDE
          and "Your answers are marked" in YT.OUTSIDE_LINE,
          (Q.READ_LINK_CAPTIONS_OUTSIDE, YT.OUTSIDE_LINE))


def t_no_new_route_no_new_tool_no_new_gate_action():
    check("read_link is not a model tool", "read_link" not in AG.TOOLS)
    check("...and neither reader grew one",
          "read_youtube" not in AG.TOOLS)
    check("the two actions are the readers' own, unchanged",
          YT.ACTION == "youtube_captions_read" and RP.ACTION == "read_web_page")
    check("read_link is NOT read-only, so it keeps 'cancel that' safe",
          "read_link" not in Q.READ_ONLY_INTENTS)
    # The module still has exactly ONE gate import (test_ask_to_change.py's own
    # pin), and the read-link runner reaches the gate through it.
    import ast
    tree = ast.parse((HERE / "jarvis_quick.py").read_text(encoding="utf-8"))
    imports = [n for n in ast.walk(tree)
               if isinstance(n, ast.Import)
               and any(a.name.split(".")[0] == "jarvis_gate" for a in n.names)]
    check("jarvis_quick still has exactly one jarvis_gate import",
          len(imports) == 1, [getattr(n, "lineno", None) for n in imports])


def t_a_negated_or_past_sentence_raises_no_card():
    """A STATEMENT is not a request (2026-11-03 audit, BUG 3).

    "don't read https://x" and "i already read https://x yesterday" both used
    to match, and each raised a real approval card. Nothing is fetched without
    a yes, so the blast radius was one unwanted card - but an ordinary sentence
    must not raise a card at all.
    """
    for words in ("don't read https://example.com/kettle",
                  "do not read https://example.com/kettle",
                  "didn't read https://example.com/kettle",
                  "never summarise https://example.com/kettle",
                  "i already read https://example.com/kettle yesterday",
                  "i read https://example.com/kettle yesterday"):
        got = Q.match(words)
        check(f"a statement is not a read request: {words!r}",
              got is None or got.name != "read_link",
              None if got is None else (got.name, got.f))
        check(f"...and the matcher refuses it itself: {words!r}",
              Q._read_link_intent(words, words.lower()) is None,
              Q._read_link_intent(words, words.lower()))
    for words in ("read https://example.com/kettle",
                  "read this link https://example.com/kettle",
                  "summarise https://example.com/kettle",
                  "read https://example.com/kettle, not the other one",
                  "not sure, read https://example.com/kettle and tell me"):
        got = Q.match(words)
        check(f"a real request still matches: {words!r}",
              got is not None and got.name == "read_link",
              None if got is None else (got.name, got.f))


def t_read_this_link_with_no_address_says_how_to_give_one():
    """BUG 5: `READ_LINK_NO_URL` was a constant nothing could ever print.

    *"read this link"* with no address fell to the model, so the friendly
    sentence - "Say the address to read, starting with http:// or https://" -
    was unreachable. The matcher now produces the intent with an empty url for
    exactly that shape, and the runner answers with the constant; a bare "read
    this" is still the model's, because it may mean anything.
    """
    for words in ("read this link", "summarise this page", "read the article"):
        got = Q.match(words)
        check(f"{words!r} reaches the runner with no address",
              got is not None and got.name == "read_link"
              and got.f.get("url") == "", None if got is None else (got.name, got.f))
        if got is not None and got.name == "read_link":
            res = Q._run_read_link(got.f, gate=FakeGate(), tier_of=never_tier)
            check("...and answers with the sentence that was dead",
                  res is not None and res.reply == Q.READ_LINK_NO_URL
                  and Q.READ_LINK_NO_URL.startswith("Say the address"),
                  None if res is None else res.reply)
    for words in ("read this", "here is a link https://example.com/kettle"):
        got = Q.match(words)
        check(f"{words!r} is still not a read_link",
              got is None or got.name != "read_link",
              None if got is None else got.name)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
