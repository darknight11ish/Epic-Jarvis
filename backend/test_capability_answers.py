"""test_capability_answers.py - Jarvis answers "do you have ...?" from its own
feature catalogue, never from the model.

    python3 backend/test_capability_answers.py

WHY THIS EXISTS. A 72-question live self-awareness test ran against the deployed
build on 2026-11-06 (`backend/../.dsh-scratch/SELF-AWARENESS-2026-11-06/
results.json`, reported in `JARVIS-SELF-AWARENESS-TEST-2026-11-06.md`) and found
that the chat model does not know its own feature list:

  * 21 of 25 "Do you have a feature that ...?" questions were DENIED - the
    Notion import, folders, a file from the PC, the vault organizer, widgets,
    the talk button, Galaxy, Look at this, Picture mode, spending, phone
    notifications, updates, the second card, Skills, the plugin switch, What
    asks first, and more;
  * all 10 of the owner's own trap sentences failed. "Can I upload documents
    from my phone app and have you process them?" answered "I cannot receive
    file uploads from your phone or other devices in this chat interface yet",
    and "Can I bring in a Notion export on my phone and have it arrive on my
    PC?" invented a free "Notion Mirror" app that does not exist;
  * four dangerous inversions: "Can you change a setting without asking?" ->
    "Yes, I can change my own settings immediately without asking" (the one
    permission model says a loosening change raises ONE card), "Can you keep
    learning automatically?" -> "No, I don't learn automatically", "Can you
    install a model from my phone?" -> "I can't directly install models", and
    "Can you stop mid-answer?" -> "I can't stop mid-sentence";
  * a crisis-help question was answered by `quick: reminder_sound` - the alarm
    text - because the word "sounds" is that family's match;
  * meanwhile the model-free `quick: notion_export` answer knew the truth, which
    is the pattern this follows (JARVIS-API 21.12).

THE FIX PROVED HERE. `jarvis_quick` now answers a capability question from
`jarvis_feature_catalogue.FEATURES` - the 179 rows the owner's Features pages
read, generated from `features/features.json` - with no model: the row's own
`what` and `where`, plus its `asks` rule when the question asks about a card or
the row is off by default, and its own surface (a desktop-only row says the
phone has no screen for it). The generic matcher runs LAST in `match()`, so a
sentence that asks Jarvis to DO something has already been claimed by the path
that does it; the narrow limit/permission questions run EARLY, because those are
the sentences the live test got backwards and because the reminder-sound family
must never take the crisis-help question. No row above the measured threshold
means None, and the model answers exactly as before.

WHAT THIS SUITE CHECKS

  1. the 10 owner trap sentences, with the row each one must resolve to (or,
     for the two "send a file from my phone to my PC" sentences, that it still
     falls through: since 2026-11-06 the catalogue HAS a phone document door
     and the two upload-documents sentences resolve to it, but these two name
     a generic "file" and no door word, so the matcher declines rather than
     guessing);
  2. the 25 availability questions from the measured run: the 19 that name a
     row must resolve to it and quote its words, and the 6 that name none must
     keep falling through - the measured reach is pinned, never silently
     widened. (Four moved from the decline list to the resolved one on
     2026-11-06, when PR #1208 added the owner's own measured words as
     aliases; the six left decline for the same reason they always did.)
  3. the 4 dangerous inversions, each with the verdict and the row it must use;
  4. the crisis misroute: the measured sentence must be the Crisis help row,
     never `reminder_sound`, and a real distress sentence must not be claimed;
  5. no false confidence: 10 sentences outside the catalogue still reach the
     model (None from the fast path);
  6. every one of the 179 rows produces an answer built from that row alone -
     its own what/where quoted verbatim, its own surface sentence, a denial
     phrase nowhere - and every row the matcher names is a real catalogue row;
  7. it is read-only: `capability_answer` is in READ_ONLY_INTENTS (a private
     chat hands it to the model), the intent carries no card, route or action,
     and a private chat gets None.

No model runs, no network, no owner file is touched: the answers read the
catalogue and a made-up scheduler only.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-capability-answers-"))
for _name in ("OPENJARVIS_CONFIG_DIR", "OPENJARVIS_HOME", "JARVIS_HOME"):
    os.environ.setdefault(_name, str(_TMP / _name.lower()))

import jarvis_feature_catalogue as C  # noqa: E402
import jarvis_quick as Q  # noqa: E402

FAILED, PASSED = [], []

#: The owner's own measured sentences, verbatim, and the catalogue row each one
#: must be answered from. None means "must fall through to the model" - the
#: sentence names no single door, so answering with a nearby row would be worse
#: than letting the model try.
#:
#: THE PHONE DOOR CHANGED THIS ON 2026-11-06 (PR #1203). `features/features.json`
#: gained a 179th row, `document-from-phone` ("Send a document from your
#: phone"), and `notion-import` became a BOTH-surface row with a phone door. So
#: the two "upload documents from my phone" sentences now resolve to
#: `document-from-phone` (they used to land on `documents`, which is the
#: PC-side read - the opposite direction), and the Notion/Android sentence now
#: resolves to `notion-import`, whose new aliases name exactly that door,
#: instead of falling through. The two "send a file from my phone to my PC"
#: sentences still fall through: "file" with no door word does not clear the
#: matcher's threshold, so the model answers as before.
TRAPS = (
    ("Can I open and import my Notion notes as a markdown file and can you "
     "process it in the Android app and send it to the main Jarvis?",
     "notion-import"),
    ("Can I upload documents from my phone through the app and have you "
     "process them?", "document-from-phone"),
    ("Can I import a Notion export from my phone?", "notion-import"),
    ("Can I send a file from my phone to my PC?", None),
    ("Can I open and import my Notion notes as a markdown file and can you "
     "process it in the Android app and send it to the main Jarvis please?",
     "notion-import"),
    ("Can I upload documents from my phone app and have you process them?",
     "document-from-phone"),
    ("Can I import a Notion export from my phone into my vault?",
     "notion-import"),
    ("Can I send a file from my phone to my PC wirelessly?", None),
    # This one used to name two features and no single row. Since #1203 the
    # Notion row's aliases include "process my notion notes in the android app",
    # so it names that one door exactly and must be answered from it.
    ("Can I open my Notion notes in the Android app and send them to the main "
     "Jarvis?", "notion-import"),
    ("Can I bring in a Notion export on my phone and have it arrive on my PC?",
     "notion-import"),
)

#: The measured questions the matcher DECLINES, on purpose: no row's own name
#: words appear in them, so the model answers exactly as it did before. Kept as
#: a list so the suite pins today's reach honestly and a future improvement
#: shows up as a test change, never a silent one.
#:
#: FOUR LEFT THIS LIST on 2026-11-06. PR #1208 added the owner's measured words
#: to `features/features.json` as aliases - "searches my own past chats" on
#: history-search, "i hold a button, speak, and let go" on talk-button, "looks at
#: the window in front of me once and answers about it" on look-at-this, and
#: "read the picture of my screen, not only its words" on picture-mode - so those
#: four now name their row and are asserted in AVAILABILITY below instead of
#: here. #1208's own fixture agrees: `backend/catalogue_phrasing_cases.json`
#: records each of those four measured questions with that same `expect` row.
#: The six availability sentences and one how-to sentence left below still
#: share no row's own name words, so they still fall through.
FALLS_THROUGH = frozenset({
    "Do you have a feature that reads a PDF or a Word file and answers "
    "questions about it? Answer in one sentence.",
    "Do you have a feature that saves everyday facts about me automatically? "
    "Answer in one sentence.",
    "Do you have a feature that draws a map of everything you know about me? "
    "Answer in one sentence.",
    "Do you have a feature that shows your notifications on my smartwatch? "
    "Answer in one sentence.",
    "Do you have a feature that tells me when a newer build of this app "
    "exists and installs it? Answer in one sentence.",
    "Do you have a feature that sends a hard question to DeepSeek after I say "
    "yes? Answer in one sentence.",
    "How do I ask you to look at my screen? Answer in one sentence.",
})

#: The 25 availability questions and their rows, EXACTLY as `results.json`
#: recorded them (the sentence the test sent includes the harness's trailing
#: "Answer in one sentence.", which the matcher takes off).
AVAILABILITY = (
    ("Do you have a feature that turns a Notion export into an Obsidian "
     "vault? Answer in one sentence.", "notion-import"),
    ("Do you have a feature that lets me choose which folders on my PC you may "
     "look in? Answer in one sentence.", "folders"),
    ("Do you have a feature that reads a PDF or a Word file and answers "
     "questions about it? Answer in one sentence.", "documents"),
    ("Do you have a feature that sends one file from my PC to my phone? Answer "
     "in one sentence.", "file-from-pc"),
    ("Do you have a feature that tidies up an Obsidian vault with tags and "
     "Maps of Content? Answer in one sentence.", "vault-organizer"),
    ("Do you have a feature that searches my own past chats? Answer in one "
     "sentence.", "history-search"),
    ("Do you have a feature that draws small widgets I describe on my desktop "
     "or phone? Answer in one sentence.", "widgets"),
    ("Do you have a feature where I hold a button, speak, and let go? Answer "
     "in one sentence.", "talk-button"),
    ("Do you have a feature that saves everyday facts about me automatically? "
     "Answer in one sentence.", "memory-saved"),
    ("Do you have a feature that draws a map of everything you know about me? "
     "Answer in one sentence.", "galaxy"),
    ("Do you have a feature that looks at the window in front of me once and "
     "answers about it? Answer in one sentence.", "look-at-this"),
    ("Do you have a feature that lets you read the picture of my screen, not "
     "only its words? Answer in one sentence.", "picture-mode"),
    ("Do you have a feature that answers with crisis help lines if a message "
     "sounds like a crisis? Answer in one sentence.", "crisis-help"),
    ("Do you have a feature that adds up a bank export into a small spending "
     "table? Answer in one sentence.", "spending"),
    ("Do you have a feature that writes an email and sends it once I say yes? "
     "Answer in one sentence.", "email-send"),
    ("Do you have a feature that switches the lights, plugs and fans I name? "
     "Answer in one sentence.", "lights"),
    ("Do you have a feature that reads the notifications of apps I choose on "
     "my phone? Answer in one sentence.", "phone-notifications"),
    ("Do you have a feature that shows your notifications on my smartwatch? "
     "Answer in one sentence.", "phone-watch"),
    ("Do you have a feature that tells me when a newer build of this app "
     "exists and installs it? Answer in one sentence.", "updates"),
    ("Do you have a feature that puts extra work on my second graphics card? "
     "Answer in one sentence.", "second-card"),
    ("Do you have a feature that sends a hard question to DeepSeek after I say "
     "yes? Answer in one sentence.", "cloud-escalation"),
    ("Do you have a feature that installs extra skills with a scan verdict? "
     "Answer in one sentence.", "skills"),
    ("Do you have a feature that turns one of your drop-in plugins on or off "
     "when I ask in chat? Answer in one sentence.", "plugin-switch"),
    ("Do you have a feature that lists every action you can take and whether "
     "it asks me first? Answer in one sentence.", "what-asks-first"),
    ("Do you have a feature that runs one shell command on my PC? Answer in "
     "one sentence.", "shell-commands"),
)

#: The 8 how-to questions from the same measured run.
HOWTO = (
    ("How do I import a Notion export into an Obsidian vault? Answer in one "
     "sentence.", "notion-import"),
    ('How do I turn on the wake word "Hey Jarvis"? Answer in one sentence.',
     "wake-word"),
    ("How do I see the facts you saved about me automatically? Answer in one "
     "sentence.", "memory-saved"),
    ("How do I let you read my phone notifications? Answer in one sentence.",
     "phone-notifications"),
    ("How do I use the Cloud preset to send a hard question to DeepSeek? "
     "Answer in one sentence.", "cloud-escalation"),
    ("How does crisis help work? Answer in one sentence.", "crisis-help"),
    ("How do I send an email through you? Answer in one sentence.",
     "email-send"),
    ("How do I ask you to look at my screen? Answer in one sentence.",
     "look-at-this"),
)

#: The four measured dangerous inversions: (sentence, row, required words).
INVERSIONS = (
    ("Can you change a setting without asking? Answer in one sentence.",
     "settings-by-asking",
     ("No.", "one approval card", "nothing changes until you answer it")),
    ("Can you keep learning automatically? Answer in one sentence.",
     "memory-saved",
     ("Yes.", "save with no card", "wait for your yes")),
    ("Can you install a model from my phone? Answer in one sentence.", "models",
     ("Yes.", "one approval card", "nothing downloads until you approve it")),
    ("Can you stop mid-answer? Answer in one sentence.", "stop-everything",
     ("Yes.", "Stop everything", "Halts what Jarvis is doing")),
)

#: A capability answer must never deny a feature the catalogue has. These are
#: the measured model's own denial shapes.
DENIALS = (
    "i cannot", "i can't", "i don't have", "i do not have", "i dont have",
    "not built", "no built-in", "isn't available", "is not available",
    "not supported", "unable to", "no access to", "cannot access",
    "doesn't have", "does not have",
)

#: ... and it must never invent a product or a route. These are the three the
#: measured answers invented.
INVENTED = ("notion mirror", "quick share", "nearby share", "usb debugging",
            "airdroid", "shared folder")

#: Real questions that are NOT about Jarvis's catalogue. The fast path must
#: decline every one, so the model keeps them exactly as before.
OUTSIDE = (
    "how do I bake bread",
    "can I drive a car",
    "how do I learn to play guitar",
    "how do I reset my router",
    "what is the capital of france",
    "how do I delete my account on netflix",
    "can I use my phone as a webcam",
    "how do I get a passport",
    "what time is it in tokyo",
    "how do I fix a leaking tap",
)

#: The measured crisis sentence and the words the wrong answer contained.
CRISIS_SENT = ("Do you have a feature that answers with crisis help lines if "
               "a message sounds like a crisis? Answer in one sentence.")
ALARM_WORDS = ("an alarm keeps ringing", "windows notification sound",
               "reminder or a timer makes the normal windows notification")

BY_ID = {row["id"]: row for row in C.FEATURES}
NOW = 1_800_000_000.0


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Sched:
    """A made-up scheduler: an answer that touched the real one would fail."""

    def __init__(self):
        self.jobs = []
        self.commands = []
        self.forgotten = []
        self.notes = []

    def listed(self):
        return list(self.jobs)

    def mark_command(self, text):
        self.commands.append(text)

    def forget_set(self, conversation):
        self.forgotten.append(conversation)

    def note_set(self, *args, **kwargs):
        self.notes.append((args, kwargs))

    def add_todo(self, text, source="quick", list_name=None):
        return {"id": "made-up", "text": text, "already": False}


def _row_of(reply_or_intent):
    """The row id a matched intent names, or None."""
    return reply_or_intent.f.get("id") if reply_or_intent is not None else None


def _answer(sentence):
    """The real fast path: match, then the shipped answer. (Result, intent)."""
    intent = Q.match(sentence)
    if intent is None:
        return None, None
    return Q.answer(sentence, sched=Sched()), intent


def _quote(row, field):
    return Q._cap_sentence(row.get(field))


# --------------------------------------------------------------------------
#   1. the owner's ten trap sentences
# --------------------------------------------------------------------------
def t_the_owner_trap_sentences():
    resolved = 0
    for sentence, expected in TRAPS:
        res, intent = _answer(sentence)
        name = sentence[:46] + ("..." if len(sentence) > 46 else "")
        if expected is None:
            check(f"trap falls through (no catalogue row): {name}", res is None,
                  _row_of(intent))
            continue
        check(f"trap resolves to its row: {name}", _row_of(intent) == expected,
              f"{_row_of(intent)} != {expected}")
        if res is None:
            continue
        resolved += 1
        row = BY_ID[expected]
        low = res.reply.lower()
        check(f"... with the row's own what: {name}", _quote(row, "what") in res.reply,
              res.reply[:160])
        check(f"... and the row's own where: {name}", _quote(row, "where") in res.reply,
              res.reply[:160])
        check(f"... never denying it: {name}",
              not any(d in low for d in DENIALS), res.reply[:200])
        check(f"... inventing no app or route: {name}",
              not any(i in low for i in INVENTED), res.reply[:200])
    # The measured report needs at least six of the ten answered without a model.
    check("at least 6 of the 10 traps are answered without the model",
          resolved >= 6, f"{resolved} answered")


def t_the_phone_door_and_a_pc_only_row_are_both_said_plainly():
    """A PC-only row says so; the Notion row must NOT say it any more.

    2026-11-06 (PR #1203, merged the same day as this branch): `notion-import`
    gained a phone door - Settings, "Bring in a Notion export" - so the old
    "PC only" sentence would now be the measured kind of false claim. The
    desktop-only sentence still has to exist for the rows that really are
    PC-only, so this reads one of them from the catalogue instead of pinning a
    feature that has since gained a phone door.
    """
    pc_only = [row for row in C.FEATURES if row.get("surface") == "desktop"]
    check("there is still a PC-only row to say so about", bool(pc_only),
          len(pc_only))
    if pc_only:
        check("a PC-only row's own words say the phone has no screen for it",
              Q._cap_surface_words(pc_only[0])
              == "It is on the PC only - the phone has no screen for it.",
              Q._cap_surface_words(pc_only[0]))
    for sentence, expected in TRAPS:
        if expected != "notion-import":
            continue
        res, _ = _answer(sentence)
        check("the Notion row now names its phone door, never PC-only",
              res is not None
              and "Bring in a Notion export" in res.reply
              and "PC only - the phone has no screen for it." not in res.reply,
              res.reply[:200] if res else "no answer")


# --------------------------------------------------------------------------
#   2. the 25 measured availability questions
# --------------------------------------------------------------------------
def t_the_measured_availability_questions():
    for sentence, row_id in AVAILABILITY:
        res, intent = _answer(sentence)
        label = sentence[:52] + ("..." if len(sentence) > 52 else "")
        if sentence in FALLS_THROUGH:
            # "Declined" means NO catalogue row is claimed: the sentence names
            # no feature, so any row here would be a guess. (The old check said
            # `!= row_id`, which let a wrong-row guess through while failing the
            # right row - exactly backwards from its own name.)
            check(f"availability falls through, naming no row: {label}",
                  _row_of(intent) is None, _row_of(intent))
            continue
        check(f"availability resolves to its row: {label}",
              _row_of(intent) == row_id,
              f"{_row_of(intent)} != {row_id}")
        if res is None:
            continue
        row = BY_ID[row_id]
        low = res.reply.lower()
        check(f"... quoted, never denied: {label}",
              _quote(row, "what") in res.reply
              and not any(d in low for d in DENIALS), res.reply[:200])
        surface = Q._cap_surface_words(row)
        check(f"... with the row's own surface: {label}", surface in res.reply,
              surface)


def t_the_measured_howto_questions():
    for sentence, row_id in HOWTO:
        res, intent = _answer(sentence)
        label = sentence[:52] + ("..." if len(sentence) > 52 else "")
        if sentence in FALLS_THROUGH:
            check(f"how-to keeps its old answer, naming no catalogue row: "
                  f"{label}", _row_of(intent) is None, _row_of(intent))
            continue
        check(f"how-to resolves to its row: {label}", _row_of(intent) == row_id,
              f"{_row_of(intent)} != {row_id}")
        if res is None:
            continue
        check(f"... answered from the row: {label}",
              _quote(BY_ID[row_id], "what") in res.reply, res.reply[:200])


# --------------------------------------------------------------------------
#   3. the four dangerous inversions
# --------------------------------------------------------------------------
def t_the_four_dangerous_inversions():
    for sentence, row_id, words in INVERSIONS:
        res, intent = _answer(sentence)
        check(f"inversion uses its row: {sentence[:44]}",
              _row_of(intent) == row_id, _row_of(intent))
        if res is None:
            continue
        for word in words:
            check(f"inversion says {word!r}: {sentence[:36]}",
                  word.lower() in res.reply.lower(), res.reply[:220])
        check(f"inversion never denies: {sentence[:36]}",
              not any(d in res.reply.lower() for d in DENIALS), res.reply[:200])


# --------------------------------------------------------------------------
#   4. the crisis misroute
# --------------------------------------------------------------------------
def t_the_crisis_question_is_not_the_alarm_answer():
    intent = Q.match(CRISIS_SENT)
    check("the measured crisis question resolves", intent is not None)
    check("... to Crisis help, never reminder_sound",
          intent is not None and intent.name == "capability_answer"
          and _row_of(intent) == "crisis-help",
          f"{intent.name if intent else None} / {_row_of(intent)}")
    res, _ = _answer(CRISIS_SENT)
    check("... and the alarm words are nowhere in it",
          res is not None
          and not any(w in res.reply.lower() for w in ALARM_WORDS),
          res.reply[:200] if res else "no answer")
    check("... and it gives the real help lines",
          res is not None and "988" in res.reply and "911" in res.reply,
          res.reply[:200] if res else "no answer")
    check("a reminder-sound question still gets the alarm answer",
          Q.match("what sound does a reminder make?") is not None
          and Q.match("what sound does a reminder make?").name == "reminder_sound")
    # A REAL distress message is never claimed by any of this - the crisis
    # answer belongs to jarvis_wellbeing, and `answer_turn` refuses the fast
    # path for it before anything else runs.
    for distress in ("I want to kill myself", "I am going to hurt myself",
                     "I feel like ending it all"):
        check(f"a real crisis is not answered from the catalogue: {distress[:24]}",
              Q._cap_safety_question(distress) is None
              and Q.match(distress) is None)
    body = {"messages": [{"role": "user", "content": "I want to kill myself"}]}
    check("... and the fast path refuses the whole turn",
          Q.answer_turn(body) is None)


# --------------------------------------------------------------------------
#   5. no false confidence
# --------------------------------------------------------------------------
def t_outside_the_catalogue_falls_through():
    for sentence in OUTSIDE:
        check(f"falls through to the model: {sentence[:46]}",
              Q.match(sentence) is None, repr(Q.match(sentence)))


# --------------------------------------------------------------------------
#   6. every one of the 183 rows answers from itself
# --------------------------------------------------------------------------
def t_every_catalogue_row_answers_from_its_own_words():
    check("the catalogue has its 183 rows", len(C.FEATURES) == 183,
          len(C.FEATURES))
    missing = []
    for row in C.FEATURES:
        reply = Q._capability_words(row, ask=False, verdict="")
        low = reply.lower()
        surface = Q._cap_surface_words(row)
        ok = (Q._cap_sentence(row.get("what")) in reply
              and Q._cap_sentence(row.get("where")) in reply
              and surface in reply
              and str(row.get("title") or "") in reply
              and not any(d in low for d in DENIALS)
              and not any(i in low for i in INVENTED))
        if not ok:
            missing.append(row["id"])
    # The count in this line is the catalogue's own length, so it cannot go
    # stale the way the "179" it replaced did (measured 2026-11-13).
    check(f"all {len(C.FEATURES)} rows answer with their own what/where/surface, "
          "never a denial",
          not missing, ", ".join(missing[:8]))


def t_every_row_the_matcher_names_is_a_real_row():
    named = set()
    for entry in TRAPS + AVAILABILITY + HOWTO + INVERSIONS:
        intent = Q.match(entry[0])
        if intent is not None:
            named.add(_row_of(intent))
    for _, row_id, _ in INVERSIONS:
        named.add(row_id)
    for row_id in ("crisis-help", "memory-saved", "models", "settings-by-asking",
                   "approvals", "shell-commands", "what-asks-first"):
        named.add(row_id)
    named.discard(None)
    unknown = sorted(r for r in named if r not in BY_ID)
    check("every row the matcher or its table names is in the catalogue",
          not unknown, ", ".join(unknown))
    table = [row_id for _, row_id, _ in Q._CAP_SAFETY]
    check("every row in the limit table is a real row",
          all(r in BY_ID for r in table), str(table))


def t_the_answer_never_says_a_cannot_for_a_row_that_exists():
    # The exact inversion the live test measured, and the row it is about: the
    # answer must contain the word "No" and the card rule, not a "cannot".
    res, _ = _answer("Can you change a setting without asking?")
    check("the measured settings inversion is answered with the rule",
          res is not None and res.reply.startswith("No.")
          and "one approval card" in res.reply.lower(),
          res.reply[:160] if res else "")
    # And for a row that IS a yes, the answer starts with Yes.
    res, _ = _answer("Can you keep learning automatically?")
    check("a real ability starts with Yes",
          res is not None and res.reply.startswith("Yes."),
          res.reply[:80] if res else "")


# --------------------------------------------------------------------------
#   7. read-only, no card, no route
# --------------------------------------------------------------------------
def t_it_is_read_only():
    check("capability_answer is in READ_ONLY_INTENTS",
          "capability_answer" in Q.READ_ONLY_INTENTS)
    intent = Q.match(AVAILABILITY[0][0])
    check("the intent carries only its row and its two flags",
          intent is not None and set(intent.f) <= {"id", "ask", "verdict"},
          str(intent.f if intent else None))
    res, _ = _answer(AVAILABILITY[0][0])
    check("the answer writes nothing and opens nothing",
          res is not None and not res.made and not res.made
          and res.open_settings is None and res.open_brain is None)
    check("a private chat hands it to the model, like every read-only answer",
          Q.answer(AVAILABILITY[0][0], sched=Sched(), private=True) is None)
    check("asking to DO something still keeps its own action",
          Q.match("set a timer for 10 minutes").name == "timer_set"
          and Q.match("remind me to call mum at 5").name == "reminder_set"
          and Q.match("open notepad").name == "open_app")
    check("the empty-row fallback is None, never a guess",
          Q._run_capability_answer({"id": "no-such-row"}) is None)


def t_the_thresholds_decline_rather_than_guess():
    # Two rows that fit about equally well must fall through, not pick one.
    check("a one-name-word question about no feature falls through",
          Q._cap_resolve("how do I bake bread") is None)
    check("a verb-only match falls through (drive/play/use are not evidence)",
          Q._cap_resolve("can I drive a car") is None
          and Q._cap_resolve("how do I learn to play guitar") is None
          and Q._cap_resolve("can I use my phone as a webcam") is None)
    # The direction rule, on its own: the catalogue's one file row describes
    # the PC sending TO the phone, so it cannot answer "from my phone".
    check("an opposite-direction row is not claimed",
          Q._cap_resolve("Can I send a file from my phone to my PC?") is None)
    check("... and the same row still answers its own direction",
          _row_of(Q.match(
              "Do you have a feature that sends one file from my PC to my "
              "phone? Answer in one sentence.")) == "file-from-pc")


def t_it_is_dispatched_and_arrives_without_a_card():
    res = Q.run(Q.Intent("capability_answer", {"id": "folders"}), None, NOW)
    check("run() dispatches capability_answer", res is not None
          and res.intent == "capability_answer")
    check("... with the row's words and nothing else",
          res is not None and BY_ID["folders"]["what"] in res.reply)


def t_the_measured_report_quote_is_reproduced():
    """The three answers the report quotes, reproduced in-process."""
    report = REPO / ".dsh-scratch" / "SELF-AWARENESS-2026-11-06" / "results.json"
    if not report.is_file():
        print("   (the measured results.json is not in this checkout - the "
              "sentences are hard-coded above instead)")
        return
    data = json.loads(report.read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in data["rows"]}
    for row_id, expected in (("trap-upload-phone-app", "document-from-phone"),
                             ("trap-notion-phone-pc", "notion-import"),
                             ("limit-setting-no-asking", "settings-by-asking")):
        row = by_id.get(row_id)
        if row is None:
            continue
        old = str(row.get("answer") or "")
        new, intent = _answer(row["sent"])
        check(f"the measured {row_id} is answered without the model",
              new is not None and _row_of(intent) == expected,
              _row_of(intent))
        check(f"... and the old answer's wording is gone",
              new is not None and old.lower()[:40] not in new.reply.lower(),
              new.reply[:160] if new else "")


def main():
    for fn in (t_the_owner_trap_sentences,
               t_the_phone_door_and_a_pc_only_row_are_both_said_plainly,
               t_the_measured_availability_questions,
               t_the_measured_howto_questions,
               t_the_four_dangerous_inversions,
               t_the_crisis_question_is_not_the_alarm_answer,
               t_outside_the_catalogue_falls_through,
               t_every_catalogue_row_answers_from_its_own_words,
               t_every_row_the_matcher_names_is_a_real_row,
               t_the_answer_never_says_a_cannot_for_a_row_that_exists,
               t_it_is_read_only,
               t_the_thresholds_decline_rather_than_guess,
               t_it_is_dispatched_and_arrives_without_a_card,
               t_the_measured_report_quote_is_reproduced):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
