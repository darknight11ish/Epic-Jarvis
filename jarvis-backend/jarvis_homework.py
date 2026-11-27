"""jarvis_homework.py - the homework loop: point at a misread, replay the
routing, explain it, and stop wherever a card has to answer.

WHY THIS EXISTS (the owner, 2026-11-26: *"I run into a lot of problems with
Atlas misrecognizing tools or commands or requests. I would like to easily be
able to do get homework with Atlas to fix these things by just asking in the
same conversation or in a different conversation and referring to an older
conversation"*). Nothing in the program could take a sentence the owner had
complained about and say WHICH lane claimed it - or that none did. So a session
about a misread started from the model's memory of itself, which is the one
witness that cannot be trusted in this question.

THE FIVE STEPS, AND WHICH OF THEM THIS MODULE OWNS:

  1. POINT AT IT - `find_exchange`. The exchange comes out of the encrypted
     chat log through the EXISTING read-only readers (`jarvis_chat_log.list`,
     `.get`, `.search`); nothing is copied out, nothing is written back, and an
     exchange that cannot be found is said to be not found rather than guessed.
  2. REPLAY THE ROUTING - `replay`. The owner's exact words go through the real
     `jarvis_quick.match`, in-process, and the intent it returns is reported as
     a name or as nothing. NO MODEL IS ASKED ANYTHING in this step, and no
     sentence of this module paraphrases the matcher: the number in the answer
     is the value the matcher returned.
  3. EXPLAIN - `explain`. `jarvis_self_improve.diagnose` reads the source and
     returns a quote with `file:line`; when it cannot establish the cause its own
     "Could not establish this" sentence is passed through unchanged. This
     module never fills that gap with a guess of its own.
  4. FIX - `draft_fix` only DRAFTS, through `jarvis_self_improve.draft`, which
     already refuses a protected file, a tier table and any test file. Applying
     it is `github_fix_and_push` and opening the pull request is
     `github_open_pr`: both are the model's carded tools, both live in
     `jarvis_github.py`, and **this module cannot call either of them and does
     not try.** A card is raised by the turn's own gate; a read-only lane that
     pushed by itself would be a card bypass, which rule 4 forbids.
  5. MERGE - `merge_gate`. The judgement is not re-implemented here: the seven
     required check names and the "which of them is not green" rule are read
     from `jarvis_github.py` (`REQUIRED_CHECKS`, `_required_problems`,
     `_running`), so a check added to that tuple is a check this gate demands
     the same day. Only all seven green passes; red, still-running and absent
     each stop the loop and say which one stopped it.

WHAT THIS MODULE DOES NOT DO, ON PURPOSE: it writes no file, opens no socket,
raises no card, applies no patch, pushes nothing and merges nothing. Every
function here returns data or a sentence; the acting stays where the cards are.

A PRIVATE CHAT hands this to the model instead of running it: `homework_loop`
is in `jarvis_quick.READ_ONLY_INTENTS`, and that is the existing rule for every
deterministic read (see `jarvis_quick.answer`). Quoting an earlier exchange is
exactly what a private chat must not do behind the owner's back.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Sequence, Tuple

#: How much of the owner's own sentence or of the answer he got is quoted in
#: one reply. A homework answer is read in a chat window, not printed to a
#: file, and the exchange it points at is one message long; these caps only
#: stop a pasted wall of text from crowding out the routing line, which is the
#: part that matters.
MAX_WORDS = 240
MAX_ANSWER = 360

#: How many conversations a title search reads, newest first, and how many
#: candidates it will name when the reference is ambiguous. A title match that
#: is not unique is NOT resolved by picking one: the loop says which ones it
#: found and stops, because guessing the exchange is the one failure the owner
#: named ("do not guess which exchange he meant").
LIST_PAGE = 60
LIST_PAGES = 3
MAX_CANDIDATES = 5

#: Words a sentence and an intent's own name are compared by. Every one is
#: grammar rather than subject matter, so removing it cannot hide the subject
#: of a lane name: "note_merge_ask" still says note and merge, and "github_self"
#: still says github. "self" and "ask" are here because a dozen lanes carry
#: them, not because they are English filler.
_STOP = frozenset("""
a an the of to in on for and or is are was were be been being it this that
these those i me my mine you your yours we our us do does did can could would
should will shall may might must have has had what which who whom whose how
why when where please just about with from at by as so if then than there
here some any all one two three now new get got set run ran let lets also
still very much many more most other another same such own
""".split())

#: Parts of an INTENT NAME that say nothing about its subject. A lane called
#: `plugin_on_state` is about plug-ins, not about state; `tools_in_category` is
#: about tools. Dropping these keeps "the lane's own name appears in your
#: sentence" an honest test instead of one that any `_ask` suffix can satisfy.
_NAME_STOP = frozenset("""
ask self cmd state list info one two more now all new get set run do does
the of to in on for and or is are it this that a an
""".split())

_CID = re.compile(r"\b[0-9a-f]{8,32}\b")

#: The three tools the last two steps belong to, by the names `jarvis_github.py`
#: itself registers. They are named here so the answer can say what the next
#: step is CALLED; this module calls none of them and has no token and no card
#: to call them with.
PUSH_TOOL = "github_fix_and_push"
PR_TOOL = "github_open_pr"
MERGE_TOOL = "github_merge_pr"


def _stem(word: str) -> str:
    """A word without its plural, so "notes" meets `note_*` and vice versa."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _words(text: str) -> set:
    """The content words of a sentence, stemmed. No library, no model."""
    out = set()
    for raw in re.findall(r"[a-z0-9']+", str(text or "").lower()):
        word = raw.strip("'")
        word = word.replace("'s", "")
        if len(word) < 2 or word in _STOP or raw in _STOP:
            continue
        out.add(_stem(word))
    return out


def _name_words(intent: str) -> set:
    """The subject words of an intent's own name, e.g. `note_merge_ask`.

    The name is the lane's own vocabulary - it is the string every existing
    test in this repository writes - so comparing a sentence with it is a
    comparison with the code's own words, not with a list typed for this
    module.
    """
    out = set()
    for part in re.split(r"[^a-z0-9]+", str(intent or "").lower()):
        if len(part) < 2 or part in _NAME_STOP:
            continue
        out.add(_stem(part))
    return out


# --------------------------------------------------------------------------
#   Step 1 - point at the exchange
# --------------------------------------------------------------------------

@dataclass
class Exchange:
    """The exchange the owner complained about, and what he was told.

    `words` and `answer` are the log's own bytes, opened by the key they were
    written with: this module copies nothing out of the encrypted database and
    writes nothing back (`jarvis_chat_log.search` makes the same promise).
    """
    conversation_id: str = ""
    title: str = ""
    words: str = ""
    answer: str = ""
    at: int = 0
    found: bool = False
    why: str = ""
    candidates: Tuple[str, ...] = ()

    @property
    def said(self) -> str:
        """The owner's words, cut for one chat answer - never rewritten."""
        return _cut(self.words, MAX_WORDS)

    @property
    def told(self) -> str:
        """The answer he got, cut for one chat answer - never summarised."""
        return _cut(self.answer, MAX_ANSWER)


def _cut(text: str, limit: int) -> str:
    flat = " ".join(str(text or "").split())
    if len(flat) <= limit:
        return flat
    return flat[:limit].rstrip() + " ..."


def _chat_log():
    """The program's own chat log, or (None, why) when it cannot be read.

    Imported lazily: this module must be importable on a backend whose history
    module is absent (an older PC), and the answer for that is one sentence,
    not an ImportError.
    """
    try:
        import jarvis_chat_log as CL
    except Exception as exc:                       # noqa: BLE001 - absent is a state
        return None, (f"the chat history module is not on this PC "
                      f"({type(exc).__name__}), so an older exchange cannot be "
                      f"found")
    try:
        log = CL._log()
    except Exception as exc:                       # noqa: BLE001
        return None, f"the chat history could not be opened ({type(exc).__name__})"
    return log, ""


def _title_of(row) -> str:
    if isinstance(row, dict):
        return str(row.get("title") or "")
    return ""


def _id_of(row) -> str:
    if isinstance(row, dict):
        return str(row.get("id") or "")
    return ""


def _conversations(log, *, limit: int = LIST_PAGE * LIST_PAGES) -> list:
    """Up to `limit` conversation rows, newest first, through the reader.

    `ChatLog.list` pages by whole seconds and returns one page at a time; a
    title search reads a few pages and stops. A paging shape this module does
    not recognise ends the walk instead of raising, so a newer reader with more
    keys still answers.
    """
    rows, before, seen = [], None, 0
    have = set()
    while len(rows) < limit and seen < LIST_PAGES:
        page = log.list(limit=LIST_PAGE, before=before)
        got = page.get("conversations") if isinstance(page, dict) else None
        if not got:
            break
        fresh = [row for row in got
                 if isinstance(row, dict) and _id_of(row) and _id_of(row) not in have]
        if not fresh:
            # A reader that ignores `before` hands the same page back. Stop
            # rather than count the same conversation twice: a doubled list
            # would make every reference look ambiguous.
            break
        for row in fresh:
            have.add(_id_of(row))
        rows.extend(fresh)
        seen += 1
        oldest = got[-1].get("updated") if isinstance(got[-1], dict) else None
        if not isinstance(oldest, (int, float)) or oldest == before:
            break
        before = oldest
    return rows[:limit]


def _match_conversations(rows: Sequence, reference: str) -> list:
    """[(score, title, id)] for the reference, best first.

    The score is the number of the reference's own words that appear in the
    conversation's title, so "the chat about the boiler" finds a chat called
    "Boiler pressure". A single word in common is not enough on its own: the
    floor is one word only when the reference IS one word, and two otherwise -
    a title search that matches on "the" would be a guess wearing a number.
    """
    want = _words(reference)
    if not want:
        return []
    floor = 1 if len(want) == 1 else 2
    scored = []
    for row in rows:
        title = _title_of(row)
        if not title:
            continue
        have = _words(title)
        score = len(want & have)
        if score >= floor:
            scored.append((score, title, _id_of(row)))
    scored.sort(key=lambda item: (-item[0], item[1].lower()))
    return scored


def _last_exchange(turns: Sequence) -> Tuple[str, str, int]:
    """(owner's words, the answer he got, when) from one conversation's turns.

    The LAST answered exchange: the newest assistant turn, and the owner's
    message that prompted it. That is the pair he is complaining about when he
    says "why did that go wrong", and it is a fact of the stored order rather
    than a choice about relevance.
    """
    answer, answer_at = "", 0
    for i in range(len(turns) - 1, -1, -1):
        turn = turns[i]
        if turn.get("role") == "assistant" and str(turn.get("text") or "").strip():
            answer, answer_at = str(turn.get("text") or ""), int(turn.get("at") or 0)
            for j in range(i - 1, -1, -1):
                before = turns[j]
                if before.get("role") == "user" and str(before.get("text") or "").strip():
                    return (str(before.get("text") or ""), answer,
                            int(before.get("at") or 0) or answer_at)
            return "", answer, answer_at
    return "", answer, answer_at


def _content_text(content) -> str:
    """A message's words, whichever shape the request carried them in.

    A chat message's `content` is a string on an ordinary turn and a list of
    parts when a picture rides with it (the phone sends its own screenshots).
    Stringifying a list would quote "({'type': 'image', ...})" back at the owner
    as if he had said it, so the parts are read for their text and the pictures
    are dropped here - `jarvis_homework` never needs the bytes.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        out = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                out.append(part["text"])
        return " ".join(out)
    return ""


def _messages_exchange(messages: Sequence) -> Tuple[str, str, int]:
    """The same pair out of THIS turn's own messages.

    A request carries its conversation's messages, so the exchange being
    complained about is in the request itself and no database is touched. The
    newest assistant message is the answer; the owner's message before it is
    what got it.
    """
    if not isinstance(messages, Sequence) or isinstance(messages, str):
        return "", "", 0
    for i in range(len(messages) - 1, -1, -1):
        item = messages[i]
        if not isinstance(item, dict):
            continue
        if item.get("role") == "assistant" and _content_text(item.get("content")).strip():
            answer = _content_text(item.get("content"))
            for j in range(i - 1, -1, -1):
                before = messages[j]
                if isinstance(before, dict) and before.get("role") == "user" \
                        and _content_text(before.get("content")).strip():
                    return _content_text(before.get("content")), answer, 0
            return "", answer, 0
    return "", "", 0


#: Phrases that mean "the exchange we just had", not an older conversation.
#: They are the owner's own deixis, matched whole rather than by their letters
#: appearing in a title - "the last answer" is not a conversation called
#: "Answer", and "this one" is not one either.
_THIS_ONE = tuple(one.strip() for one in """
this
that
it
this one
that one
this chat
that chat
this conversation
that conversation
this exchange
that exchange
the last exchange
the last answer
that answer
the previous answer
the answer above
the message above
that message
""".splitlines() if one.strip())

#: How the owner names an older conversation. Stripped before the title search,
#: so "the conversation about the boiler" is looked up as "the boiler".
_REF_LEAD = re.compile(
    r"^(?:please\s+)?(?:my|the|our|that|this)?\s*"
    r"(?:older|old|earlier|previous|last)?\s*"
    r"(?:conversation|chat|chatlog|chat log|exchange|thread)\s*"
    r"(?:called|named|titled|about|on|where|with|from)?\s*", re.I)


def clean_reference(reference: str) -> str:
    """The words to search a title for: the owner's own, minus the lead-in.

    "the conversation about the boiler" -> "boiler"; "this one" -> "" (the
    exchange in front of us); a conversation id is passed through untouched.
    """
    text = " ".join(str(reference or "").split()).strip(" .!?,;:\"'")
    if not text:
        return ""
    if _CID.fullmatch(text):
        return text
    got = _REF_LEAD.sub("", text).strip(" .!?,;:\"'")
    if not got or " ".join(got.lower().split()) in _THIS_ONE:
        return ""
    return got


def find_exchange(reference: str = "", *, messages: Sequence = (),
                  log=None, at: Optional[float] = None) -> Exchange:
    """The exchange the owner pointed at, or `found=False` and the reason.

    Two ways to point, and no third:
      * no reference (or "this"/"that") - the last answered exchange in THIS
        turn's own messages, which is the conversation the owner is in;
      * a reference - a conversation id, or words from an older conversation's
        title, found through `ChatLog.list` and then opened with
        `ChatLog.get`. `ChatLog.search` is the fallback when no title matches.

    An ambiguous reference returns the candidates and `found=False`. It never
    picks one: "do not guess which exchange he meant" is the rule, and a guess
    here would make every later step about the wrong sentence.
    """
    ref = clean_reference(reference)
    if not ref:
        words, answer, when = _messages_exchange(messages or ())
        if not words or not answer:
            return Exchange(
                found=False,
                why=("there is no earlier exchange in this chat to look at yet - "
                     "ask me again after an answer you want to take apart"))
        return Exchange(conversation_id="", title="", words=words, answer=answer,
                        at=int(when or at or 0), found=True)

    log, why = (log, "") if log is not None else _chat_log()
    if log is None:
        return Exchange(found=False, why=why)
    try:
        status = log.status() if hasattr(log, "status") else {}
    except Exception:                              # noqa: BLE001
        status = {}
    if isinstance(status, dict) and status.get("enabled") is False:
        return Exchange(found=False,
                        why=("chat history is switched off on this PC, so there is "
                             "no older exchange to point at"))

    cid, title = "", ""
    if _CID.fullmatch(ref):
        cid = ref
        try:
            got = log.get(cid)
        except Exception as exc:                   # noqa: BLE001
            return Exchange(found=False,
                            why=f"that conversation could not be opened ({type(exc).__name__})")
        if not got:
            return Exchange(found=False, why="there is no conversation with that id")
        title = str(got.get("title") or "")
    else:
        try:
            rows = _conversations(log)
        except Exception as exc:                   # noqa: BLE001
            return Exchange(found=False,
                            why=f"the list of conversations could not be read ({type(exc).__name__})")
        scored = _match_conversations(rows, ref)
        from_search = False
        if not scored:
            # The reader's own full-text search is the second door, and it is
            # the same read-only one History uses: it opens each turn with the
            # key, compares, and drops it. A hit there is a conversation, not
            # an exchange, so the conversation's last exchange is quoted.
            scored = _search_conversations(log, ref)
            from_search = True
        if not scored:
            return Exchange(found=False,
                            why=(f"no conversation of yours is about \"{_cut(ref, 80)}\" - "
                                 f"nothing in the titles or the messages matches, so "
                                 f"this is not guessed"))
        best = scored[0][0]
        top = [item for item in scored if item[0] == best][:MAX_CANDIDATES]
        # A tie is ambiguous whether the words matched a title or a message; a
        # zero score is only allowed through when the search found ONE
        # conversation, because then there is nothing to choose between.
        tied = len(top) > 1 or (from_search and best == 0 and len(scored) > 1)
        if tied:
            return Exchange(found=False,
                            why=(f"\"{_cut(ref, 80)}\" matches {max(len(top), len(scored))} "
                                 f"conversations. Say which one by its title."),
                            candidates=tuple(f"{title}" for _score, title, _cid_ in top))
        _score, title, cid = top[0]

    try:
        got = log.get(cid)
    except Exception as exc:                       # noqa: BLE001
        return Exchange(found=False,
                        why=f"that conversation could not be opened ({type(exc).__name__})")
    if not got:
        return Exchange(found=False, why="that conversation is no longer there")
    turns = got.get("turns") if isinstance(got, dict) else None
    words, answer, when = _last_exchange(turns or [])
    if not words:
        return Exchange(found=False,
                        why=("that chat has no answered exchange in it yet, so "
                             "there is nothing to take apart"),
                        title=str(got.get("title") or title))
    return Exchange(conversation_id=str(got.get("id") or cid),
                    title=str(got.get("title") or title), words=words,
                    answer=answer, at=int(when or at or 0), found=True)


def _search_conversations(log, reference: str) -> list:
    """Hits out of `ChatLog.search`, as the same (score, title, id) rows.

    The reader's own full-text search is the second door and it is a read-only
    one: it opens each turn with the key, compares, and drops it. Its hits are
    conversations whose MESSAGES contain the reference, so a hit with nothing
    in its title still counts - which is why a score of zero is kept here and
    the caller decides about ambiguity. A search that raises, or a backend
    without one, is the same as no hit: never an exception out of this module.
    """
    try:
        found = log.search(reference, limit=LIST_PAGE)
    except Exception:                              # noqa: BLE001 - no search is a state
        return []
    rows = found.get("conversations") if isinstance(found, dict) else None
    if not rows:
        return []
    want = _words(reference)
    scored = []
    for row in rows:
        title = _title_of(row)
        cid = _id_of(row)
        if not cid:
            continue
        scored.append((len(want & _words(title)), title, cid))
    scored.sort(key=lambda item: (-item[0], item[1].lower()))
    return scored


# --------------------------------------------------------------------------
#   Step 2 - replay the routing, deterministically
# --------------------------------------------------------------------------

def _matcher() -> Optional[Callable]:
    """The real matcher, or None when this backend has no routing module."""
    try:
        import jarvis_quick as Q
    except Exception:                              # noqa: BLE001 - absent is a state
        return None
    return getattr(Q, "match", None)


_LANES: Optional[frozenset] = None


def _lane_names() -> frozenset:
    """Every intent name `jarvis_quick.py` itself writes, read from its source.

    The names are read out of the module's own file - `Intent("note_merge")`
    and friends - because there is no exported list of lanes and inventing one
    here would be a second vocabulary that drifts. Used ONLY to say which lane
    a sentence looks like it belonged to; the routing fact is the matcher's
    return value and nothing else.
    """
    global _LANES
    if _LANES is not None:
        return _LANES
    names = set()
    try:
        import jarvis_quick as Q
        path = getattr(Q, "__file__", "")
        if path:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            names = set(re.findall(r"\bIntent\(\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']",
                                   text))
    except Exception:                              # noqa: BLE001
        names = set()
    _LANES = frozenset(names)
    return _LANES


@dataclass
class Replay:
    """What the matcher said about the owner's exact words.

    `intent` is the matcher's own return value: a lane name, or None when the
    sentence reached no lane. `kind` is the plain-word reading of that value,
    and `looks_like` is a HINT built by comparing the claiming lane's name with
    the sentence - it never changes `intent`, and a lane can be right even when
    the hint fires.
    """
    words: str = ""
    intent: Optional[str] = None
    kind: str = "unclaimed"          # unclaimed | claimed | swallowed
    shared: Tuple[str, ...] = ()
    looks_like: Tuple[str, ...] = ()
    lanes: int = 0
    found: bool = True
    why: str = ""


def replay(words: str, *, match: Optional[Callable] = None,
           now: Optional[float] = None) -> Replay:
    """Run the real matcher on `words` and report what it returned.

    This is the part of the loop that is provably mechanical: the only thing
    that decides `intent` is `jarvis_quick.match(words)`. `match` is a seam for
    the suite; the default is the module's own function, called in-process with
    the same `now` every other caller passes.
    """
    text = " ".join(str(words or "").split())
    if not text:
        return Replay(found=False, why="there is no sentence to replay")
    matcher = match if match is not None else _matcher()
    if matcher is None:
        return Replay(words=text, found=False,
                      why="the routing module is not on this PC, so nothing was replayed")
    try:
        got = matcher(text, now=time.time() if now is None else now)
    except Exception as exc:                       # noqa: BLE001 - a crash is a finding
        return Replay(words=text, found=False,
                      why=f"the matcher failed on those words ({type(exc).__name__})")
    name = getattr(got, "name", None) if got is not None else None
    name = str(name) if isinstance(name, str) and name else None
    lanes = _lane_names()
    mine = _words(text)
    if name is None:
        likes = _nearest(mine, lanes, skip="")
        return Replay(words=text, intent=None, kind="unclaimed",
                      looks_like=likes, lanes=len(lanes))
    shared = tuple(sorted(mine & _name_words(name)))
    if shared:
        return Replay(words=text, intent=name, kind="claimed", shared=shared,
                      lanes=len(lanes))
    likes = _nearest(mine, lanes, skip=name)
    return Replay(words=text, intent=name,
                  kind="swallowed" if likes else "claimed",
                  looks_like=likes, lanes=len(lanes))


def _nearest(mine: set, lanes: Iterable[str], *, skip: str) -> Tuple[str, ...]:
    """The lanes whose own names share the most words with the sentence.

    Sorted by shared words then by name, at most three, and only lanes that
    share at least one - so an unrelated lane is never named as "the one you
    meant". This is a reading aid built from the code's own vocabulary; it is
    not evidence, and no step of the loop treats it as any.
    """
    scored = []
    for lane in lanes:
        if not lane or lane == skip:
            continue
        common = mine & _name_words(lane)
        if common:
            scored.append((len(common), lane))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return tuple(lane for _n, lane in scored[:3])


# --------------------------------------------------------------------------
#   Step 3 - explain, or say plainly that the cause was not established
# --------------------------------------------------------------------------

@dataclass
class Explanation:
    """The code location and the plain words, or the honest refusal."""
    text: str = ""
    found: bool = False
    where: Tuple[str, ...] = ()
    why: str = ""


def _self_improve():
    try:
        import jarvis_self_improve as SI
    except Exception:                              # noqa: BLE001 - absent is a state
        return None
    return SI


def _diagnose_question(words: str, outcome: Replay) -> str:
    """The question `diagnose` is asked - the routing fact first.

    The question names the fact so that a reader of the evidence can see what
    was being looked up: no lane for these words, or this lane claiming them.
    Kept under `jarvis_self_improve.MAX_QUESTION_CHARS` (500) by cutting the
    sentence, never by dropping the fact.
    """
    said = _cut(words, 160)
    if outcome.intent is None:
        lead = (f"Why does jarvis_quick.match claim no intent for the sentence "
                f"\"{said}\"?")
    else:
        lead = (f"Why does jarvis_quick.match claim the intent "
                f"\"{outcome.intent}\" for the sentence \"{said}\"?")
    return lead


def _coder_lane_now() -> Tuple[bool, str]:
    """(can a code diagnosis run here, why not). Read-only, never raises.

    The owner's ruling of 2026-11-27 (Q6), measured the expensive way: on a PC
    whose only loaded lane was the one-card everyday model, `diagnose` spent
    64.6 s degrading a code question onto a 9B and then said "Could not
    establish this". Steps 1 and 2 of this loop cost under a second and need no
    model at all, so the honest thing is to answer with them and SAY which lane
    is missing, rather than burn a minute to produce the same refusal.

    The evidence is `jarvis_model_lanes.pooled_state()`, the same `/api/ps`
    read that decides every other question about a lane being up - never the
    preset's name and never a guess. A PC where that read cannot be made is
    answered as "not ready", which is the safe direction: the caller then says
    so instead of starting a slow call that cannot succeed.
    """
    try:
        import jarvis_model_lanes as ML
        state = ML.pooled_state()
    except Exception as exc:                       # noqa: BLE001 - said, not raised
        return False, f"the model lanes could not be read ({type(exc).__name__})"
    if (state or {}).get("row") is None:
        return False, "the pooled lane on port 11450 is not holding a model"
    return True, ""


def explain(words: str, *, outcome: Optional[Replay] = None,
            diagnose: Optional[Callable] = None,
            ask: Optional[Callable] = None) -> Explanation:
    """The source location for the misread, through `jarvis_self_improve`.

    `diagnose` and `ask` are seams for the suite. With neither, the real
    `jarvis_self_improve.diagnose` is used, which reads the source, asks THIS
    PC's own model, and cites the lines it read; its own refusal ("Could not
    establish this: ...") is returned as it wrote it. A cause this module
    cannot establish is never replaced by a sentence this module invented -
    that is the difference between diagnosing and narrating.
    """
    outcome = outcome if outcome is not None else replay(words)
    SI = _self_improve()
    if SI is None:
        return Explanation(
            found=False,
            why="the self-improvement module is not on this PC",
            text="Could not establish this: the self-improvement module is not "
                 "on this PC, so the source was not read.")
    runner = diagnose if diagnose is not None else SI.diagnose
    if diagnose is None:
        ready, why_not = _coder_lane_now()
        if not ready:
            return Explanation(
                found=False,
                why=why_not,
                text="I replayed the routing above, but reading the source "
                     "needs the Coder preset (the pooled graphics-card lane on "
                     f"port 11450), which is not active right now ({why_not}). "
                     "Switch to Coder and say 'continue homework' and I will "
                     "diagnose it and draft the fix.")
    question = _diagnose_question(words, outcome)
    try:
        if diagnose is not None:
            got = runner(question)
        else:
            got = runner(question, ask=ask) if ask is not None else runner(question)
    except Exception as exc:                       # noqa: BLE001
        return Explanation(
            found=False, why=f"the diagnosis failed ({type(exc).__name__})",
            text=f"Could not establish this: the diagnosis failed "
                 f"({type(exc).__name__}), so nothing was read out.")
    text = ""
    try:
        text = str(SI.text(got) or "").strip()
    except Exception:                              # noqa: BLE001 - a shape we do not read
        text = ""
    where = tuple(str(getattr(cite, "where", "") or "")
                  for cite in (getattr(got, "citations", ()) or ()))
    where = tuple(one for one in where if one)
    found = bool(getattr(got, "found", False))
    if not text:
        return Explanation(found=False, why="the diagnosis returned no words",
                           text="Could not establish this: the diagnosis returned "
                                "no words, so there is nothing to show.")
    return Explanation(text=text, found=found, where=where,
                       why="" if found else str(getattr(got, "why", "") or ""))


# --------------------------------------------------------------------------
#   Step 4 - draft the fix; the carded tools carry it
# --------------------------------------------------------------------------

@dataclass
class Draft:
    """A drafted change and its test, or `jarvis_self_improve`'s refusal."""
    ok: bool = False
    text: str = ""
    code_diff: str = ""
    test_diff: str = ""
    why: str = ""


def draft_fix(words: str, *, outcome: Optional[Replay] = None,
              draft: Optional[Callable] = None,
              ask: Optional[Callable] = None) -> Draft:
    """Draft the routing change and its test through `jarvis_self_improve`.

    `jarvis_self_improve.draft` is the boundary that already refuses a
    protected file (`jarvis_gate.py`, `_where.py`, `apply-patches.ps1`), a tier
    table and any test file, and it returns a refusal in plain words. The
    drafted pair is NOT applied here: `github_fix_and_push` pushes it on one
    card and `github_open_pr` opens the pull request on another, both from the
    model's own tool list, and this module has no token and no card.
    """
    outcome = outcome if outcome is not None else replay(words)
    SI = _self_improve()
    if SI is None:
        return Draft(ok=False, why="the self-improvement module is not on this PC",
                     text="I could not draft a fix: the self-improvement module "
                          "is not on this PC, so nothing was drafted.")
    runner = draft if draft is not None else SI.draft
    said = _cut(words, 160)
    if outcome.intent is None:
        question = (f"jarvis_quick.match claims no intent for the sentence "
                    f"\"{said}\". Add the smallest routing change that claims it, "
                    f"with a test that fails without the change.")
    else:
        question = (f"jarvis_quick.match claims the intent \"{outcome.intent}\" "
                    f"for the sentence \"{said}\". Add the smallest routing change "
                    f"that claims it correctly, with a test that fails without it.")
    try:
        if draft is not None:
            got = runner(question)
        else:
            got = runner(question, ask=ask) if ask is not None else runner(question)
    except Exception as exc:                       # noqa: BLE001
        return Draft(ok=False, why=f"the draft failed ({type(exc).__name__})",
                     text=f"I could not draft a fix: the draft failed "
                          f"({type(exc).__name__}), so nothing was drafted.")
    if not got:
        return Draft(ok=False, why="the draft returned nothing",
                     text="I could not draft a fix: nothing came back, so nothing "
                          "was drafted.")
    refused = str(getattr(got, "refusal", "") or "")
    if refused:
        return Draft(ok=False, why=refused,
                     text=f"I will not draft that: {refused}")
    try:
        text = str(SI.proposal_text(got) or "").strip()
    except Exception:                              # noqa: BLE001
        text = ""
    code = str(getattr(got, "code_diff", "") or "")
    test = str(getattr(got, "test_diff", "") or "")
    if not text:
        return Draft(ok=False, why="the draft came back empty",
                     text="I could not draft a fix: nothing came back, so nothing "
                          "was drafted.")
    return Draft(ok=bool(code or test), text=text, code_diff=code, test_diff=test)


# --------------------------------------------------------------------------
#   Step 5 - the merge gate: the seven checks, named
# --------------------------------------------------------------------------

@dataclass
class MergeGate:
    """Whether a merge may go ahead, with the seven checks named either way."""
    ok: bool = False
    names: Tuple[str, ...] = ()
    running: Tuple[str, ...] = ()
    problems: Tuple[str, ...] = ()
    text: str = ""
    why: str = ""


def _github():
    try:
        import jarvis_github as GH
    except Exception:                              # noqa: BLE001 - absent is a state
        return None
    return GH


def _check_name(one) -> str:
    if isinstance(one, dict):
        return str(one.get("name") or one.get("context") or "")
    return str(getattr(one, "name", "") or "")


def merge_gate(checks: Sequence, *, required: Optional[Sequence[str]] = None,
               pr: Optional[int] = None) -> MergeGate:
    """May this pull request be merged? Red, running and absent all say no.

    The seven names and the judgement come from `jarvis_github.py` - the same
    tuple its own merge refuses on and the same helper that names a check which
    finished red - so this is ONE rule with one owner, not a second one that
    can drift. A merge whose checks are still running is not "probably fine":
    it stops here too, because `_required_problems` deliberately does not call
    a running check a problem and only `_running` names it.

    `checks` is the shape `github_ci_status` already returns: a list of
    `{"name": ..., "status": ..., "conclusion": ...}`.
    """
    GH = _github()
    if GH is None:
        return MergeGate(
            ok=False, why="the GitHub module is not on this PC",
            text="I could not check the seven required checks: the GitHub module "
                 "is not on this PC, so nothing was merged and nothing was read.")
    names = tuple(required if required is not None else
                  getattr(GH, "REQUIRED_CHECKS", ()))
    if not names:
        return MergeGate(ok=False, why="no required check list",
                         text="I could not check the seven required checks: the "
                              "GitHub module names none, so a merge must not go ahead.")
    runs = [one for one in (checks or ()) if _check_name(one)]
    try:
        running = tuple(str(n) for n in GH._running(runs))
        problems = tuple(str(n) for n in
                         GH._required_problems(runs, names))
    except Exception as exc:                       # noqa: BLE001
        return MergeGate(ok=False, names=names,
                         why=f"the check judgement failed ({type(exc).__name__})",
                         text=f"I could not judge the checks ({type(exc).__name__}), "
                              f"so a merge must not go ahead.")
    where = f"pull request #{int(pr)}" if pr else "this pull request"
    total = _count(len(names), "required checks")
    if running:
        return MergeGate(
            names=names, running=running,
            text=(f"Not yet - {_count(len(running), 'of the ' + total)} "
                  f"{'is' if len(running) == 1 else 'are'} still running on {where}: "
                  f"{_join(running)}. A merge waits for all of them."))
    if problems:
        return MergeGate(
            names=names, problems=problems,
            text=(f"Stop - a merge must not go ahead on {where}: "
                  f"{_join(problems)}. Red is never merged past, and I will not "
                  f"force anything."))
    return MergeGate(
        ok=True, names=names,
        text=(f"All {total} are green on {where}: {_join(names)}. "
              f"The merge itself is still one card ({MERGE_TOOL}) - and never a "
              f"push to main."))


def _count(n: int, what: str) -> str:
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
             7: "seven"}
    return f"{words.get(n, str(n))} {what}"


def _join(items: Sequence[str], sep: str = ", ") -> str:
    got = [str(one) for one in items]
    if len(got) <= 1:
        return "".join(got)
    return sep.join(got[:-1]) + " and " + got[-1]


# --------------------------------------------------------------------------
#   The loop itself
# --------------------------------------------------------------------------

#: The merge tool's own name lives with the other two at the top of the file;
#: this module calls it never.


@dataclass
class Homework:
    """One homework run: the exchange, the routing fact, and what it means.

    `reply` is what the owner reads. Everything in it that is a fact came from
    `exchange`, `routing` or `explanation`; nothing in it is a claim about the
    program that this run did not measure.
    """
    reply: str = ""
    exchange: Exchange = field(default_factory=Exchange)
    routing: Replay = field(default_factory=Replay)
    explanation: Explanation = field(default_factory=Explanation)
    draft: Optional[Draft] = None
    ok: bool = False
    why: str = ""
    private: bool = True             # it quotes the owner's own chat


def _routing_words(outcome: Replay) -> str:
    """The routing fact, in one plain sentence, with the lane named.

    "Route" rather than "lane" for the owner's own reading: the name that
    follows it is the program's own name for the grammar that took the words,
    and it is the evidence - so it is quoted exactly, never prettified.
    """
    if outcome.intent is None:
        said = (f"No route claimed those exact words. That is the miss: nothing in "
                f"my routing knows this sentence, so the model has to improvise "
                f"the answer.")
        if outcome.looks_like:
            said += (f" The nearest routes by name are "
                     f"{_join(outcome.looks_like)}.")
        return said
    line = f"The route named {outcome.intent} claimed those exact words."
    if outcome.shared:
        count = _count(len(outcome.shared), "of your words")
        line += (f" {count[:1].upper() + count[1:]} "
                 f"{'is' if len(outcome.shared) == 1 else 'are'} in that route's "
                 f"own name: {_join(outcome.shared)}.")
    if outcome.kind == "swallowed":
        line += (f" None of that route's own name is in your sentence, so this "
                 f"looks like a neighbour taking it rather than the route you "
                 f"meant; {_join(outcome.looks_like)} is closer by name.")
    return line


def _next_step(*, drafted: Optional[Draft]) -> str:
    """What happens next, and what does NOT happen here.

    The honest half of the loop: this lane reads and drafts, and the acting
    steps are the model's carded tools. Saying so is cheaper than a promise the
    code cannot keep.
    """
    head = (f"Nothing was changed: this answer reads and drafts only. The change "
            f"goes through {PUSH_TOOL} on one card, {PR_TOOL} on the next, and a "
            f"merge only through {MERGE_TOOL} - with all seven required checks "
            f"green and named on the card.")
    if drafted is not None and drafted.ok:
        return (f"The draft is above. {head}")
    if drafted is not None and not drafted.ok:
        return (f"No draft: {drafted.why or 'it was refused'}. {head}")
    return head


def homework(reference: str = "", *, messages: Sequence = (), log=None,
             match: Optional[Callable] = None, diagnose: Optional[Callable] = None,
             ask: Optional[Callable] = None, draft: bool = False,
             draft_fn: Optional[Callable] = None, live: bool = False,
             at: Optional[float] = None) -> Homework:
    """Run the loop over one exchange and return the words for the chat.

    Steps 1-3 always run. Step 4 runs only when `draft` is true, and even then
    it only drafts: nothing is applied, pushed or merged here. `live` shortens
    the answer, because Live reads it aloud and a wall of file paths is not an
    answer by voice.
    """
    exchange = find_exchange(reference, messages=messages, log=log, at=at)
    if not exchange.found:
        why = str(exchange.why or "").rstrip(" .")
        lines = [f"I cannot point at that exchange: {why}."]
        if exchange.candidates:
            lines.append("Did you mean: " + _join(exchange.candidates) + "?")
        return Homework(reply="\n".join(lines), exchange=exchange, ok=False,
                        why=exchange.why)
    routing = replay(exchange.words, match=match, now=at)
    if not routing.found:
        return Homework(
            reply=(f"You said: \"{exchange.said}\"\n"
                   f"I answered: \"{exchange.told}\"\n\n"
                   f"I could not replay the routing: {routing.why}.\n"
                   f"{_next_step(drafted=None)}"),
            exchange=exchange, routing=routing, ok=False, why=routing.why)
    explanation = explain(exchange.words, outcome=routing, diagnose=diagnose, ask=ask)
    drafted = None
    if draft:
        drafted = draft_fix(exchange.words, outcome=routing, draft=draft_fn, ask=ask)

    lines = []
    where = f"the chat \"{exchange.title}\"" if exchange.title else "this chat"
    lines.append(f"Homework on {where}.")
    lines.append(f"You said: \"{exchange.said}\"")
    lines.append(f"I answered: \"{exchange.told}\"")
    lines.append("")
    lines.append("Routing, replayed just now by the real matcher - no model was "
                 "asked:")
    lines.append(f"  {_routing_words(routing)}")
    lines.append("")
    if live:
        lines.append(_one_line(explanation.text))
        lines.append("")
        lines.append(_next_step(drafted=drafted))
        return Homework(reply="\n".join(lines), exchange=exchange, routing=routing,
                        explanation=explanation, draft=drafted, ok=True)
    lines.append("Where it goes wrong:")
    for one in explanation.text.splitlines():
        lines.append("  " + one if one.strip() else "")
    if drafted is not None:
        lines.append("")
        lines.append("The draft:")
        for one in drafted.text.splitlines():
            lines.append("  " + one if one.strip() else "")
    lines.append("")
    lines.append(_next_step(drafted=drafted))
    return Homework(reply="\n".join(lines), exchange=exchange, routing=routing,
                    explanation=explanation, draft=drafted, ok=True)


def _one_line(text: str) -> str:
    """A multi-line diagnosis as one spoken sentence and its first quote."""
    kept = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        kept.append(line)
        if len(kept) >= 2:
            break
    return " ".join(kept)
