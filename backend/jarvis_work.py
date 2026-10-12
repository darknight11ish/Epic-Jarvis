"""jarvis_work.py - the "work setups": combinations of local models chosen for
a kind of work, each explained in plain words before the owner starts.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py).
Everything that reads the PC - what is installed, what the approval card says -
is wrapped and may fail; every function that decides something is pure.

WHAT IT IS FOR. The owner asked (2026-10-10):

    "analyze what different model combinations from the latest and best
     models available for download would be best for different work for
     jarvis. like if i was going to code an android app, or work on admin
     stuff from my own life. and have these as selectable options that
     explain what they do before i start work. and jarvis can also
     recommend loading up certain combos if i talk about work i'd like to do"

So this module holds five SETUPS - model combinations, each for a kind of
work - and a pure `match()` that reads the owner's own newest words and says
which one to OFFER. The design note is
.dsh-scratch/android-verify/WORK-SETUPS-DESIGN-2026-10-10.md, and every number
in it is from the measurements of 2026-10-10
(.dsh-scratch/android-verify/MODEL-BENCH-2026-10-10.md and
MODEL-STRATEGY-2026-10-10.md). Nothing here re-measures anything.

THE RULES THE SETUPS FOLLOW, each one a measurement, not a preference:

  1. One model per card, whenever it fits on one card. A model that fits on
     one card ran 3x slower split across both (13.4 against 44.9 tok/s).
  2. The RTX 2060 (12 GB) is the long-context card: qwen3.5:9b holds 196,608
     tokens there with nothing spilled. The RTX 2080 SUPER (8 GB) holds the
     same model at only 8,192.
  3. The RTX 2080 SUPER is the FAST card even though it is the smaller one:
     qwen3:8b writes at 64.0 tok/s there against 49.3 on the 2060.
  4. Both cards run a model at once for free: the main model lost 1.9% of its
     speed while the other card was generating.
  5. qwen3.5:9b is the awkward one. It is the best-quality model measured and
     the only picture-capable one installed, and at 196,608 tokens it fills
     9.17 of the 2060's 12 GB on its own, so nothing fits beside it. Every
     setup either gives the 2060 to it and accepts one model there, or gives
     the 2060 to something else and gives up the 196k context.

NOTHING HERE CHANGES A MODEL. Recommending a setup switches nothing, and
choosing one only records the choice. Switching or installing a model is the
existing `/api/models/switch` and `/api/models/install` card, tier "ask" -
the same card the owner already knows. There is no new gate action and no new
tier in this module (CLAUDE.md: switching a model raises an approval card
like any other change).

THE THINKING TRAP, said in the setups rather than hidden: qwen3.5:9b and
ornith:9b default to thinking ON, and with a normal budget that returned an
EMPTY answer on all three measured questions. The per-model thinking setting
(jarvis_thinking.py, "Thinking levels", default off) is what makes them
usable; these setups assume it and never change it.

Two words that mean something specific below:

    readiness   whether each model a setup names is downloaded on this PC -
                asked of Ollama's /api/tags. Never guessed, never a download.
    card        the words ONE approval card would carry, if the owner chose
                to switch to the setup's main model.

Standard library only. Never raises from a public call.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

#: The measured evidence every `why`, `cost` and speed figure in this module
#: comes from. `tools/check_work_claims.py` reads it and fails when a number or
#: a phrase quoted here is not in the report (or in the benchmark beside it) -
#: a claim that cannot be traced back to a measurement does not ship.
EVIDENCE = (
    ".dsh-scratch/android-verify/MODEL-STRATEGY-2026-10-10.md",
    ".dsh-scratch/android-verify/MODEL-BENCH-2026-10-10.md",
)

#: The two cards, as the owner's PC reports them. Names only: they are what
#: the screens show, and what the design note calls them.
CARD_BIG = "RTX 2060"
CARD_FAST = "RTX 2080 SUPER"

#: The file the choice is kept in, beside the other settings
#: (hardware-choice.json, second-card-*.json). A choice is a preference, not a
#: permission: it changes no model by itself.
CHOICE_FILE = "work-setup-choice.json"

#: The route a setup's step posts to. The owner's own words (CLAUDE.md,
#: 2026-09-18): switching the local model from the phone is allowed, between
#: models the desktop already has, and it raises an approval card. This is the
#: ONLY route this module ever names - a setup that needs a model that is not
#: downloaded says so in words and offers nothing, rather than pulling it.
SWITCH_PATH = "/api/models/switch"

#: How long a /api/tags answer is trusted. Long enough that opening the picker
#: asks Ollama once, short enough that a model downloaded a minute ago shows.
_TAGS_SECONDS = 20.0


# --------------------------------------------------------------------------
#   A model on a card
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Place:
    """One model of a setup: where it sits and what it costs there.

    Every figure is MEASURED on this PC on 2026-10-10 - the model's own size
    on disk, the video memory it takes at that context on that card, and its
    writing speed there. `spill_gib` is 0.0 for every place in every setup:
    a setup may not contain a model that spills, because a spilled model
    writes at 8-26 tok/s and nothing warns (the strategy report, section 2).
    """
    role: str               # "main" or "beside"
    model: str
    card: str
    ctx: int
    disk_gb: float          # the file on disk
    vram_gib: float         # in video memory at this context, ON THIS CARD
    speed: float            # tokens a second on this card
    spill_gib: float        # 0.0 always - see the class docstring
    words: str              # what this place is for, in plain words

    @property
    def card_gb(self) -> float:
        return 12.0 if self.card == CARD_BIG else 8.0

    @property
    def free_gib(self) -> float:
        """What is left on the card for anything else. None of it is used by
        this setup - a second card's room is left free on purpose."""
        return round(self.card_gb - self.vram_gib, 2)

    @property
    def clean(self) -> bool:
        return self.spill_gib <= 0.0

    def as_dict(self) -> dict:
        return {"role": self.role, "model": self.model, "card": self.card,
                "context": self.ctx, "context_words": f"{self.ctx // 1024}K",
                "disk_gb": self.disk_gb, "vram_gib": self.vram_gib,
                "speed_tokens_per_s": self.speed, "spill_gib": self.spill_gib,
                "clean": self.clean, "free_gib": self.free_gib,
                "words": self.words}


@dataclass(frozen=True)
class Setup:
    """One combination of models for one kind of work.

    `words` is what a person reads, and it is the same on both apps and in the
    design note: `what` (one sentence, the first thing shown), `cost` (what it
    costs, honestly), `worse` (what it is honestly worse at), `uses` (whether
    both cards work, or one), `thinking` (the thinking trap, when it applies).
    """
    id: str
    name: str
    work: str               # the kind of work, a few words
    places: tuple           # (Place, ...) - main first
    what: str
    cost: str
    worse: str
    uses: str
    why: str                # the measured reason, shown under "Why this"
    thinking: str = ""
    #: The words that ask for this setup. Plain words a person would use about
    #: their own work, never a model name (the owner talks about work, not
    #: about models). Matched on whole words and phrases only.
    triggers: tuple = ()
    #: Phrases that name this setup's kind of work outright. One of these
    #: alone is enough; a trigger word on its own needs a second signal
    #: (see `match`).
    strong: tuple = ()

    @property
    def main(self) -> Place:
        return self.places[0]

    @property
    def beside(self) -> Optional[Place]:
        return self.places[1] if len(self.places) > 1 else None

    @property
    def both_cards(self) -> bool:
        return len({p.card for p in self.places}) > 1

    @property
    def models(self) -> tuple:
        out = []
        for p in self.places:
            if p.model not in out:
                out.append(p.model)
        return tuple(out)

    def summary(self) -> str:
        """One line: the main model, its context, and its card."""
        m = self.main
        return (f"{m.model} at {m.ctx:,} tokens on the {m.card} "
                f"({m.speed:g} tokens a second), with {self.beside.model} "
                f"({self.beside.ctx:,} tokens) on the {self.beside.card}"
                if self.beside else
                f"{m.model} at {m.ctx:,} tokens on the {m.card} "
                f"({m.speed:g} tokens a second)")


# --------------------------------------------------------------------------
#   The five setups
# --------------------------------------------------------------------------
#
#   Order is the order the picker shows: the ordinary case first, then the two
#   kinds of work the owner named, then the two extremes.

SETUPS = (
    Setup(
        id="everyday",
        name="Everyday quick answers",
        work="short questions, writing, checking things, one-off tasks",
        places=(
            Place("main", "qwen3:8b", CARD_FAST, 16384, 4.87, 5.84, 64.0, 0.0,
                  "The everyday model, on the faster card"),
            Place("beside", "qwen3.5:9b", CARD_BIG, 196608, 6.10, 9.17, 44.9, 0.0,
                  "A second, better model waiting with room for a very long chat"),
        ),
        what=("For short questions, a bit of writing, checking things and one-off "
              "tasks - the ordinary use of Jarvis, where waiting is the annoying part."),
        cost=("Both models sit loaded at once, one per card, and that measured only "
              "-1.9% off the main model's speed while the other card worked. The "
              "everyday model's own conversation is capped at about 15,600 tokens of "
              "real input - that is its ceiling, not a guess."),
        worse=("Chosen for speed, not for the best answer: on the quality questions "
               "asked today qwen3:8b gave the weakest explanation of the three, and "
               "it led with the outdated reason."),
        uses=("Yes - both cards work at once, one model each. Nothing is split across "
              "both cards: that measured 3x slower."),
        why=("qwen3:8b on the 2080 SUPER is the fastest useful setup measured: 64.0 "
             "tokens a second against 49.3 for the same model on the 2060. It scored "
             "10/10 on the coding test and found a planted fact at both the start and "
             "the end of a 13,780-token prompt. The other card is not wasted beside it "
             "- it holds qwen3.5:9b at its full 196,608 tokens, which is 12x the "
             "conversation the everyday setting holds today."),
        thinking=("Neither model thinks before answering here, and qwen3.5:9b is set "
                  "that way in Thinking levels - left on it answered nothing at all "
                  "on all three test questions."),
        triggers=("quick question", "quick questions", "everyday", "just asking",
                  "short question", "chat with you", "everyday use", "a quick"),
        strong=("everyday use", "quick questions"),
    ),
    Setup(
        id="coding",
        name="Building an Android app",
        work="writing code, reading a file, fixing an error, multi-step coding work",
        places=(
            Place("main", "qwen3.5:9b", CARD_BIG, 196608, 6.10, 9.17, 44.9, 0.0,
                  "Writes the code, with room for a whole project in view"),
            Place("beside", "qwen3.5:4b", CARD_FAST, 65536, 3.16, 4.15, 77.1, 0.0,
                  "Answers quick questions about the code, fast"),
        ),
        what=("For building an Android app, or any other coding work: writing code, "
              "reading a file, fixing an error, or a long job where Jarvis has to keep "
              "a lot of the project in view at once."),
        cost=("The card that writes the code is the slower one - 44.9 tokens a second "
              "against 64.0 on the other card - and qwen3.5:9b fills 9.17 of its 12 GB "
              "at this context, so the other card is the only place a second model "
              "can go. What the slow card buys is 196,608 tokens of project in view "
              "instead of 16,384, about twelve times as much. Both cards still work "
              "at once, for the same -1.9%."),
        worse=("The coding model writes more slowly than qwen3:8b would on the fast "
               "card, and the small model beside it is the one that got a trap "
               "question wrong when asked as an explanation - it is here for speed on "
               "short questions, not for careful reasoning."),
        uses=("Yes - both cards, one model each, run at once. Both fit entirely in "
              "video memory at these sizes: nothing spills and nothing is split."),
        why=("qwen3.5:9b scored 10/10 on the coding test and gave the best explanation "
             "answer measured, and it holds 196,608 tokens on the 12 GB card with "
             "nothing spilled. The 4B beside it also scored 10/10 and is the fastest "
             "model that still got the reasoning question right (77.1 tokens a "
             "second), so short questions do not pay the 9B's price."),
        thinking=("qwen3.5:9b has thinking ON by default, and with it on the answer "
                  "came back EMPTY on all three measured questions. Thinking levels "
                  "is what turns it off for ordinary turns; this setup assumes that "
                  "setting and changes nothing itself."),
        triggers=("code", "coding", "program", "programming", "android", "app",
                  "app development", "debug", "function", "gradle", "kotlin",
                  "python", "script", "compile", "bug", "repository", "git",
                  "unit test", "refactor", "api", "database", "frontend",
                  "backend", "class", "module", "syntax", "error message",
                  "android app", "mobile app"),
        strong=("android app", "mobile app", "an app for", "writing code",
                "write code", "fix this bug", "fix a bug", "my code",
                "the code for", "build an app", "code an", "app development"),
    ),
    Setup(
        id="admin",
        name="Admin and paperwork",
        work="letters, statements, forms, policies and things to sort out",
        places=(
            Place("main", "qwen3.5:9b", CARD_BIG, 196608, 6.10, 9.17, 44.9, 0.0,
                  "Reads the whole letter or statement and answers about it"),
            Place("beside", "qwen3:8b", CARD_FAST, 16384, 4.87, 5.84, 64.0, 0.0,
                  "Drafts and rewords quickly"),
        ),
        what=("For your own life admin: a long letter, a bank statement, a policy "
              "document, a form to fill in, or a pile of things to sort out and "
              "summarise - where being right matters more than being quick."),
        cost=("The model that reads it all writes about 30% slower than qwen3:8b "
              "would on the fast card, and the fast card's conversation is only "
              "16,384 tokens while it is the second model. The 12 GB card is fully "
              "committed, so nothing else fits on it."),
        worse=("The step from \"best explanation answer measured\" to \"best for "
               "paperwork\" is a reading, not a measurement: no "
               "summarise-a-whole-document test was run today. It rests on the "
               "explanation result and on the 196,608-token ceiling."),
        uses=("Yes - both cards, one model each, run at once, nothing spilled."),
        why=("qwen3.5:9b gave the best answer of the models asked the explanation "
             "question, and it is the one model that holds 196,608 tokens in video "
             "memory on this PC - which is what a letter, a statement or a policy "
             "document actually needs. qwen3:8b on the fast card keeps drafting "
             "quick."),
        thinking=("qwen3.5:9b's thinking is off here (Thinking levels). With it on and "
                  "an ordinary budget it answered nothing at all."),
        triggers=("admin", "paperwork", "letter", "letters", "form", "forms",
                  "statement", "statements", "tax", "taxes", "invoice", "bill",
                  "bills", "insurance", "policy", "renewal", "bank", "budget",
                  "council", "landlord", "tenancy", "appointment", "deadline",
                  "email", "inbox", "spreadsheet", "receipt", "receipts",
                  "application", "benefits", "pension", "medical", "prescription",
                  "sorting out", "fill in", "fill out", "fill this in"),
        strong=("life admin", "my admin", "paperwork", "fill in a form",
                "fill out a form", "my taxes", "a letter from", "bank statement",
                "insurance", "the forms", "my inbox", "my bills"),
    ),
    Setup(
        id="long",
        name="Long conversations and big documents",
        work="one very long back-and-forth, or a document too big for anything else",
        places=(
            Place("main", "qwen3.5:4b", CARD_BIG, 262144, 3.16, 8.27, 63.1, 0.0,
                  "Holds the most text this PC can load at once"),
            Place("beside", "qwen3:8b", CARD_FAST, 16384, 4.87, 5.84, 64.0, 0.0,
                  "Answers ordinary questions while the long one stays loaded"),
        ),
        what=("For one very long back-and-forth, or a document too big for any other "
              "setup - the most text this PC can genuinely hold at once."),
        cost=("262,144 tokens, which is a third more than the better model reaches "
              "and sixteen times the everyday setting. It is paid for in answer "
              "quality, not in speed: the small model writes at 63.1 tokens a second."),
        worse=("The model holding all that text got a trap question WRONG (\"all but 9 "
               "run away\" answered as 8, with a self-contradictory reason), and on "
               "the 12 GB card it produced a muddled explanation the same weights did "
               "not produce on the other card. Use it for size, not for care."),
        uses=("Yes - both cards, one model each, at once, nothing spilled."),
        why=("Measured: qwen3.5:4b is the only model that holds 262,144 tokens in "
             "video memory on the 2060 with zero spill, at 63.1 tokens a second - and "
             "262,144 is the model's own limit, not the card's. qwen3.5:9b at that "
             "size spills 2.91 GB and falls to 21.9 tokens a second, and qwen3:8b "
             "stops at 40,960 because that is the model's own limit."),
        triggers=("long document", "long documents", "long conversation",
                  "long chat", "whole book", "manuscript", "thesis",
                  "dissertation", "transcript", "long thread", "huge file",
                  "very long", "entire document", "long report", "novel",
                  "long pdf", "big pdf", "whole document", "everything at once",
                  "long file", "read it all", "the whole thing"),
        strong=("long document", "long conversation", "the whole document",
                "read it all", "long pdf", "whole book", "the entire document"),
    ),
    Setup(
        id="specialist",
        name="Careful coding with a coding specialist",
        work="multi-step coding work with tools, files and many steps",
        places=(
            Place("main", "ornith:9b", CARD_BIG, 196608, 5.24, 8.93, 49.1, 0.0,
                  "The model built for long, tool-driven coding jobs, MIT licensed"),
            Place("beside", "qwen3.5:9b", CARD_FAST, 8192, 6.10, 5.22, 58.1, 0.0,
                  "The better general model, with a short conversation"),
        ),
        what=("For long, multi-step coding work - many files, tools and steps - using "
              "the one model here that is purpose-built for it."),
        cost=("On the one test both were given, the coding specialist scored WORSE: "
              "8/10 against 10/10 for the general models. It is also slower than "
              "qwen3:8b on the same card (45.6 against 49.3 tokens a second). And the "
              "better general model beside it gets only 8,192 tokens, because the "
              "8 GB card cannot hold more."),
        worse=("Everything in the line above: it scored 8/10 and lost the only measured "
               "coding comparison it was in, by ignoring the word \"DISTINCT\". One "
               "question with ten cases is not a verdict - but it is why this setup is "
               "not the default for coding."),
        uses=("Yes - both cards, one model each, at once, nothing spilled."),
        why=("ornith:9b is the only model installed that is built and benchmarked for "
             "multi-step agentic work (SWE-bench, Terminal-Bench), it carries the MIT "
             "licence and a 256K window, and it holds 196,608 tokens on the 12 GB card "
             "with nothing spilled. This setup exists so the choice can be settled on "
             "real work: the measured comparison today favours the general models (8/10 "
             "against 10/10), and the cheap way to settle it is to use both for a week."),
        thinking=("ornith:9b has thinking ON by default too, and the same trap applies: "
                  "with thinking on and a normal budget it answered nothing. Thinking "
                  "levels is what turns it off."),
        triggers=("agentic", "multi-step", "many steps", "tool use", "swe-bench",
                  "terminal", "whole project", "many files", "long coding task",
                  "coding agent", "autonomous", "step by step coding"),
        strong=("coding specialist", "agentic coding", "multi-step coding",
                "many files", "tool-driven"),
    ),
)

SETUP_IDS = tuple(s.id for s in SETUPS)
_BY_ID = {s.id: s for s in SETUPS}


def claim_text(setup: Setup) -> str:
    """Every word of `setup` that states a fact about this PC, in one string,
    for `tools/check_work_claims.py` to trace back to the measurements. The
    on-screen words (`what`, `uses`) are left out: they describe the kind of
    work, not the hardware."""
    return " ".join([setup.why, setup.cost, setup.worse, setup.thinking])


def by_id(setup_id) -> Optional[Setup]:
    """The setup with this id, or None. Never raises."""
    try:
        return _BY_ID.get(str(setup_id or "").strip())
    except Exception:
        return None


def name_of(setup_id) -> str:
    s = by_id(setup_id)
    return s.name if s else "Custom (your own models)"


# --------------------------------------------------------------------------
#   Recommending one from the owner's own words
# --------------------------------------------------------------------------
#
#   PURE. No files, no network, no model. `match()` is the whole decision, and
#   tests hold it to the same examples every time.
#
#   It OFFERS. It never switches, never loads, never writes. The caller - the
#   route - only ever puts the sentence in front of the owner; switching is
#   still the existing /api/models/switch approval card.

#: Words that mean "do not offer anything this turn". A turn about someone in
#: real distress is never a moment to suggest a model combination - the same
#: "crisis messages are never learned from and never counted" rule the rest of
#: Jarvis already follows (CLAUDE.md, 2026-09-28), extended here to offers.
#: Deliberately short and specific: it is a reason to say nothing, so a false
#: positive costs an offer nobody needed, and a false negative costs an offer
#: at a bad moment.
CRISIS = re.compile(
    r"\b(kill myself|killing myself|end my life|ending my life|want to die|"
    r"wish i was dead|wish i were dead|suicidal|suicide|self[- ]harm|"
    r"hurt myself|hurting myself|no reason to live|can'?t go on)\b", re.I)

#: Words about a model or about switching one. If the owner is already talking
#: about that, the picker is the answer, not a suggestion to open it.
_ALREADY = re.compile(
    r"\b(switch|switching|swap|model|models|ollama|context window|"
    r"work setup|work setups|which setup)\b", re.I)

#: The words that say "this is work I am about to do", not "tell me about
#: work". Without one of these, a bare trigger word is not enough on its own -
#: so "I read a letter yesterday" does not offer anything, while "I need to
#: work on a letter" does.
_INTENT = re.compile(
    r"\b(i'?m going to|i am going to|i wanna|i want to|i'?d like to|i would like to|"
    r"i need to|i have to|i'?ve got to|help me|can you help|going to|about to|"
    r"start(?:ing)?|begin|work(?:ing)? on|working on|do some|doing some|"
    r"let'?s|lets|shall we|tomorrow i|today i|this (?:morning|afternoon|evening)|"
    r"how do i|how should i|what'?s the best way|best way to)\b", re.I)

_WORD = re.compile(r"[a-z0-9']+(?:[-/][a-z0-9']+)*")


def _norm_words(text: str) -> str:
    """The owner's words, lowercased, with the punctuation that carries no
    meaning removed. Kept as a string so a whole phrase can be searched for
    with word boundaries - never as a set, which would lose the phrases."""
    return " ".join(_WORD.findall(str(text or "").lower()))


def _has_phrase(words: str, phrase: str) -> bool:
    """Is `phrase` in `words` as WHOLE words? "app" matches "an app for", and
    does not match "apparently" or "happen"."""
    p = _norm_words(phrase)
    return bool(p) and re.search(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])", words) is not None


def looks_like_crisis(text) -> bool:
    """True when the owner's words are about real distress. Never raises; a
    non-string is False."""
    try:
        return bool(text) and isinstance(text, str) and bool(CRISIS.search(text))
    except Exception:
        return False


def score(setup: Setup, words: str) -> int:
    """How strongly these words ask for `setup`. 0 means "not at all".

    A strong phrase alone scores 3 and is enough on its own. Ordinary trigger
    words score 1 each, and two of them are needed - one word is too easy to
    say by accident ("I read a long report once"). A phrase that is both a
    trigger and a strong phrase counts once, at the higher weight.
    """
    if not words:
        return 0
    n = 3 if any(_has_phrase(words, p) for p in setup.strong) else 0
    n += sum(1 for p in setup.triggers if _has_phrase(words, p))
    return n


def match(text) -> Optional[dict]:
    """Which setup to OFFER for these words, and the sentence to say - or None.

    Pure and total: any input, including None, an empty string or a whole
    paragraph, gives a dict or None, and nothing is changed anywhere.

    The rules, in order, and each one is why it is there:

      1. A turn about real distress offers nothing (CRISIS above).
      2. Two words that name this setup's work, or one phrase that names it
         outright - never a single loose word.
      3. The owner's own words must say they are about to do the work, not
         merely mention it (_INTENT), OR name it outright with a strong phrase.
      4. If the owner is already talking about models or switching, say
         nothing: they have found the picker, and a suggestion would be noise.
      5. The strongest score wins; a tie goes to the earlier setup in SETUPS,
         which is the order the picker shows.

    {"id", "name", "work", "words", "why"} - `words` is the whole sentence,
    ready to show, and it always says what the setup is for and that nothing
    happens until the owner approves a switch card.
    """
    try:
        if not isinstance(text, str) or not text.strip():
            return None
        if looks_like_crisis(text):
            return None
        words = _norm_words(text)
        if not words or _ALREADY.search(text):
            return None
        ranked = []
        for i, s in enumerate(SETUPS):
            n = score(s, words)
            if n:
                ranked.append((n, -i, s))
        if not ranked:
            return None
        ranked.sort(reverse=True, key=lambda r: (r[0], r[1]))
        best_score, _, best = ranked[0]
        strong = any(_has_phrase(words, p) for p in best.strong)
        # Two ordinary words, or one phrase that names the work outright, or
        # one word plus the owner saying they are about to do it.
        if not strong and best_score < 2 and not _INTENT.search(text):
            return None
        if not strong and not _INTENT.search(text):
            return None
        return {"id": best.id, "name": best.name, "work": best.work,
                "words": offer_words(best),
                "why": (f"Your words mention {best.work}.")}
    except Exception:
        return None


def offer_words(setup: Setup) -> str:
    """The one or two sentences Jarvis says when it offers this setup. Plain
    words, says what the setup is for, and says that it has changed nothing.

    Kept to three short sentences on purpose: this is said inside an answer,
    so `why` - the measured reason, which can run long - is a separate field
    and is shown on the setup's own card, not here.
    """
    m = setup.main
    second = (f", with {setup.beside.model} on the {setup.beside.card} beside it"
              if setup.beside else "")
    return (f"That sounds like {setup.work}. The \"{setup.name}\" setup puts "
            f"{m.model} on the {m.card} for it{second}. Nothing has changed - the "
            f"setup screen explains it before anything moves, and switching is yours "
            f"to approve.")


def wake_phrase(setup: Setup) -> str:
    """The short thing the owner can say to open the picker on this one."""
    return f"\"start {setup.name.lower()}\""


# --------------------------------------------------------------------------
#   What is downloaded on this PC (the only part that touches anything)
# --------------------------------------------------------------------------

_TAGS_LOCK = threading.Lock()
_TAGS: dict = {"at": -1e9, "names": None}


def _main_url() -> str:
    """The everyday Ollama. Read from jarvis_hardware when it is there, so
    the two modules can never disagree about which server that is."""
    try:
        import jarvis_hardware
        return jarvis_hardware._main_url()
    except Exception:
        return (os.environ.get("OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/")


def _fetch_tags(url: str) -> Optional[set]:
    try:
        import jarvis_hardware
        return jarvis_hardware._tags(url)
    except Exception:
        return None


def installed(force: bool = False) -> Optional[set]:
    """The model names Ollama has, or None when Ollama could not be asked
    (None is "unknown", never "nothing installed"). Cached for
    `_TAGS_SECONDS` so opening the picker asks once, not five times."""
    now = time.time()
    with _TAGS_LOCK:
        if not force and _TAGS["names"] is not None and now - _TAGS["at"] < _TAGS_SECONDS:
            return _TAGS["names"]
    names = _fetch_tags(_main_url())
    with _TAGS_LOCK:
        _TAGS.update(at=now, names=names)
    return names


def has_model(names: Optional[set], model: str) -> Optional[bool]:
    """Is `model` downloaded? None when Ollama could not be asked."""
    if names is None:
        return None
    want = {model} if ":" in model else {model, model + ":latest"}
    return bool(want & names)


#: "Go and ask Ollama", for a `names` argument. A plain None means "could not
#: be reached" - a different thing, and the one the words on screen turn on:
#: reporting a model as missing when Jarvis merely could not ask would send the
#: owner to download something they already have. So the two are never the same
#: value, and no default can quietly turn one into the other.
ASK = object()


def readiness(setup: Setup, names=ASK) -> dict:
    """Which of a setup's models are downloaded here.

    {"state": "ready" | "partial" | "missing" | "unknown",
     "have": [...], "need": [...], "words": "<a sentence>"}

    A setup whose models are not all here is still SHOWN - with the missing
    ones named and the download card offered as the ordinary one
    (/api/models/install, tier "ask"). Nothing is ever downloaded by this
    module, and `need` never triggers a pull.

    `names` left at ASK means "go and ask Ollama"; `names=None` means "Ollama
    could not be reached" - never "nothing is installed" - and answers
    "unknown" rather than "missing".
    """
    models = setup.models
    if names is ASK:
        names = installed()
    if names is None:
        return {"state": "unknown", "have": [], "need": list(models),
                "words": ("Jarvis could not ask Ollama which models are downloaded, so "
                          "it cannot tell whether this setup needs one. Check that "
                          "Ollama is running, then open this again - nothing is "
                          "downloaded and nothing is changed either way.")}
    have, need = [], []
    for m in models:
        (have if has_model(names, m) else need).append(m)
    if not need:
        state = "ready"
        words = "Both models are downloaded already." if len(models) > 1 \
            else "The model is downloaded already."
    elif len(need) == len(models):
        state = "missing"
        words = ("Not downloaded yet: " + ", ".join(need)
                 + ". Choosing this setup would ask to download it, with the usual "
                   "card - nothing downloads until you approve it.")
    else:
        state = "partial"
        words = ("Already here: " + ", ".join(have) + ". Still to download: "
                 + ", ".join(need) + " - the usual download card, nothing until you "
                   "approve it.")
    return {"state": state, "have": have, "need": need, "words": words}


# --------------------------------------------------------------------------
#   The choice (the owner's preference - not a permission)
# --------------------------------------------------------------------------


def _config_dir() -> Path:
    try:
        import jarvis_hardware
        return jarvis_hardware._config_dir()
    except Exception:
        return Path(os.environ.get("OPENJARVIS_CONFIG_DIR")
                    or os.environ.get("JARVIS_CONFIG_DIR")
                    or (Path.home() / ".openjarvis"))


def _choice_path() -> Path:
    return _config_dir() / CHOICE_FILE


def _read_json(p: Path) -> dict:
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _write_json(p: Path, data: dict) -> Optional[str]:
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(p)
    except OSError as exc:
        return f"could not save it ({type(exc).__name__})"
    return None


def choice() -> dict:
    """{"setup", "at"} - the remembered preference. An id this module does not
    know is read as no choice at all, so a renamed setup cannot leave the
    screens pointing at nothing."""
    raw = _read_json(_choice_path())
    if raw.get("setup") not in SETUP_IDS:
        raw["setup"] = None
    return raw


def choose(setup_id) -> tuple:
    """Remember the owner's choice, or forget it (None). (http code, body).

    It changes NO model, no setting and no file of Ollama's. Returns the
    setup's record, and - when its main model is not the one running now and
    IS downloaded - the one step that would switch to it. That step is the
    EXISTING /api/models/switch card, raised by the app that posts it, and it
    is never posted from here.
    """
    if setup_id is not None and str(setup_id).strip() not in SETUP_IDS:
        return 400, {"error": f"there is no work setup called {str(setup_id)[:40]!r}; "
                              f"the setups are {', '.join(SETUP_IDS)}"}
    setup = by_id(setup_id) if setup_id is not None else None
    data = choice()
    data.update(setup=setup.id if setup else None, at=int(time.time()))
    err = _write_json(_choice_path(), data)
    if err:
        return 500, {"error": err}
    if setup is None:
        return 200, {"ok": True, "chosen": None, "setup": None,
                     "message": ("No work setup is chosen. Your models are exactly as "
                                 "they are; nothing was changed.")}
    names = installed()
    return 200, {"ok": True, "chosen": setup.id,
                 "setup": setup_view(setup, names, _current_model()),
                 "message": (f"\"{setup.name}\" chosen. Nothing has changed: the models "
                             f"are the ones already loaded. The step below switches one "
                             f"model, and it raises its own card.")}


def step(setup: Setup, names: Optional[set] = None, current: Optional[str] = None) -> dict:
    """The ONE thing that would have to change to use `setup`, as a step the
    apps already know how to draw.

    {"kind": "none" | "missing" | "switch" | "unknown", "title", "detail",
     "route", "body", "done", "words"}

    `names=None` means "Ollama could not be reached" - the answer is then
    "unknown", never "missing" (see readiness).

    `route` is only ever SWITCH_PATH, and only when the model is already
    downloaded: this module will not name a download route, because a download
    is a different card and the apps own that flow.
    """
    m = setup.main
    have = has_model(names, m.model)
    if names is None:
        return {"kind": "unknown", "title": "Which model is running could not be read",
                "detail": ("Jarvis could not ask Ollama which model is running, so it "
                           "cannot say whether anything needs to change."),
                "route": None, "body": None, "done": None,
                "words": ("Nothing to do yet: Jarvis could not reach Ollama. Check that "
                          "Ollama is running, then open this again.")}
    if not have:
        return {"kind": "missing", "title": f"Download {m.model} first",
                "detail": (f"{m.model} is not downloaded on this PC. The download card "
                           f"is the usual one (Brain, Models) - Jarvis does not download "
                           f"a model from this screen."),
                "route": None, "body": None, "done": False,
                "words": (f"{m.model} is not downloaded yet, so this setup cannot be "
                          f"used. Download it from Brain, Models - the usual card - and "
                          f"then choose this setup again.")}
    if current and _same(current, m.model):
        return {"kind": "none", "title": f"{m.model} is already the everyday model",
                "detail": "Nothing to change.", "route": None, "body": None, "done": True,
                "words": (f"{m.model} is already the model Jarvis uses, so this setup is "
                          f"ready - nothing needs changing.")}
    return {"kind": "switch", "title": f"Switch everyday chat to {m.model}",
            "detail": ("Raises the usual model-switch card. The model you use now stays "
                       "downloaded, so switching back is one more switch."),
            "route": SWITCH_PATH, "body": {"ref": m.model}, "done": False,
            "words": (f"Ready when you are: switching to {m.model} raises the usual "
                      f"approval card, and nothing changes until you approve it.")}


def _same(a: str, b: str) -> bool:
    strip = lambda s: s[:-7] if s.endswith(":latest") else s
    return bool(a and b) and strip(str(a).strip()) == strip(str(b).strip())


def _current_model() -> Optional[str]:
    try:
        import jarvis_hardware
        return jarvis_hardware._current_model()
    except Exception:
        return None


# --------------------------------------------------------------------------
#   The card's own words (what an approval card would show)
# --------------------------------------------------------------------------


def card_words(setup: Setup) -> str:
    """The whole text of the approval card for switching to this setup's main
    model - the setup named, what it is for, and what it costs. The card that
    is really raised is the backend's own (`/api/models/switch`); this is what
    a screen shows beside it, and it never claims the switch happened."""
    m = setup.main
    lines = [
        f"Switch everyday chat to {m.model}, for \"{setup.name}\"?",
        "",
        f"What this setup is for: {setup.work}.",
        f"Where it goes: the {m.card}, holding {m.ctx:,} tokens of conversation "
        f"({m.vram_gib:g} GB of the card's {m.card_gb:g} GB, measured - nothing spills).",
    ]
    if setup.beside:
        b = setup.beside
        lines.append(f"Beside it: {b.model} on the {b.card}, {b.ctx:,} tokens.")
    lines += [
        "",
        f"What it costs: {setup.cost}",
        f"What it is worse at: {setup.worse}",
        "",
        "Nothing has changed yet. Approving this card switches one model; it does "
        "not download anything and it does not change any of Ollama's settings. "
        "The model you use now stays downloaded, so switching back is one more "
        "switch.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   The two reads and the three writes
# --------------------------------------------------------------------------


def setup_view(setup: Setup, names=ASK, current: Optional[str] = None) -> dict:
    """One setup, as both apps read it. All words, no shape of their own."""
    r = readiness(setup, names)
    return {
        "id": setup.id, "name": setup.name, "work": setup.work,
        "what": setup.what, "cost": setup.cost, "worse": setup.worse,
        "uses": setup.uses, "why": setup.why, "thinking": setup.thinking,
        "both_cards": setup.both_cards,
        "summary": setup.summary(),
        "models": list(setup.models),
        "places": [p.as_dict() for p in setup.places],
        "ready": r["state"], "ready_words": r["words"],
        "have": r["have"], "need": r["need"],
        "main_model": setup.main.model,
        "step": step(setup, names, current),
        "card_words": card_words(setup),
    }


def status(now: Optional[float] = None) -> dict:
    """GET /api/work. Never raises; no token, no key.

    `now` is accepted and unused, like the other status readers in this
    backend: a caller that wants a clock passed in finds the parameter
    already there.
    """
    try:
        return _status()
    except Exception as exc:
        return {"available": True, "setups": [], "recommended": None,
                "found": f"Jarvis could not work out the work setups "
                         f"({type(exc).__name__}).", "error": type(exc).__name__}


def _status() -> dict:
    names = installed()
    current = _current_model()
    ch = choice()
    chosen = by_id(ch.get("setup"))
    return {
        "available": True,
        "found": (f"{len(SETUPS)} work setups for this PC's own cards: "
                  + ", ".join(f"\"{s.name}\"" for s in SETUPS) + "."),
        "setups": [setup_view(s, names, current) for s in SETUPS],
        "recommended": (chosen.id if chosen else None),
        "chosen": chosen.id if chosen else None,
        "chosen_name": chosen.name if chosen else None,
        "chosen_at": ch.get("at") if chosen else None,
        "current_model": current,
        "ollama_seen": names is not None,
        "known_models": sorted(names) if names is not None else None,
        "how_to": ("Say what you are about to work on and Jarvis will offer the setup "
                   "for it - or pick one here before you start. Choosing only remembers "
                   "the choice; switching a model is its own card, as always."),
        "switch_path": SWITCH_PATH,
        "not_a_catalogue": ("These are combinations of models already on this PC. There "
                            "is no list here of models that could be downloaded, and no "
                            "search."),
    }


def recommend(words) -> dict:
    """The offer for these words, as GET/POST answers carry it. Never raises.

    {"offered": bool, "id", "name", "words", "why", "step"?} - `step` is what
    the apps already know how to raise (the existing switch card), and it is
    present only when the model is already downloaded.

    THE RULE THIS FUNCTION EXISTS TO KEEP: it returns an offer. It does not
    switch, load, unload or write anything - not the choice file, nothing.
    """
    try:
        m = match(words)
        if not m:
            return {"offered": False}
        s = by_id(m["id"])
        if s is None:                       # cannot happen; belt and braces
            return {"offered": False}
        names = installed()
        out = {"offered": True, "id": s.id, "name": s.name, "work": s.work,
               "words": m["words"], "why": m["why"],
               "switched": False,
               "step": step(s, names, _current_model())}
        return out
    except Exception as exc:
        return {"offered": False, "error": type(exc).__name__}


def handle_recommend(body) -> tuple:
    """POST /api/work/recommend {"words": "..."} -> (200, recommend(words)).

    The owner's words arrive from the app that has them; nothing is stored and
    nothing is read from anywhere else. A body with no usable "words" is a 400,
    not a silent nothing, so a caller with a bug finds out.
    """
    words = body.get("words") if isinstance(body, dict) else None
    if not isinstance(words, str) or not words.strip():
        return 400, {"error": "send {\"words\": \"what you are about to work on\"}"}
    return 200, recommend(words)


def handle_choose(body) -> tuple:
    if not isinstance(body, dict) or "setup" not in body:
        return 400, {"error": ("send {\"setup\": \"everyday\" | \"coding\" | \"admin\" | "
                               "\"long\" | \"specialist\" | null}")}
    return choose(body.get("setup"))
