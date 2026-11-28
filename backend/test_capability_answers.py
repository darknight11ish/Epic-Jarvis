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

  1. the owner trap sentences, with the row each one must resolve to. TWO OF
     THEM CHANGED ON 2026-11-18: "Can I send a file from my phone to my PC?"
     must now be answered by `document-from-phone`, not fall through. Since
     2026-11-15 that row's aliases include "send a file from my phone to my pc"
     and "send a photo from my phone to my pc", so the catalogue has the door -
     the matcher was returning None because the highest-scoring row was the
     OPPOSITE-direction `file-from-pc` and it gave up instead of taking the
     honest one. The owner's own sentence of that day, "Can you send a file for
     me to my PC?", is in the list too (it needed a second fix: "can you ..."
     was never a capability lead); see `t_the_owner_s_phone_file_question`;
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
  6. every catalogue row produces an answer built from that row alone -
     its own what/where quoted verbatim, its own surface sentence, a denial
     phrase nowhere - and every row the matcher names is a real catalogue row;
  7. it is read-only: `capability_answer` is in READ_ONLY_INTENTS (a private
     chat hands it to the model), the intent carries no card, route or action,
     and a private chat gets None;
  8. THE THREE MEASURED FALSE-DENIAL QUESTIONS (2026-11-18, CHAT-GAPS section
     4): "Can you send a file from my PC to my phone?", "Can you read my phone
     notifications?" and "Can you add up my spending?" (with "Can you check my
     bank export?"). All three reached the local model while the catalogue had
     the row and its real steps, so the model could answer "I can't" about
     something that exists. Each must answer from its row's own what/where and
     its own rule, and every widened lead has a negative control that must keep
     the path it had before - including "can you write a nice email for my
     boss?", pinned to the writer's own path by `test_chat_honesty.py`;
  9. THE "and" REGRESSION (2026-11-18, CHAT-GAPS section 6): the explicit
     feature lane used to short-circuit on "and" before trying `_FEAT_EXPLICIT`,
     which sent all six measured feature questions with "and" in the subject to
     the model (49 catalogue rows were in that blast radius). Every one of the
     six must now reach its row and quote its words, and action sentences that
     contain "and" must keep the deterministic path they already had.
 10. THE LAST FOURTEEN MEASURED QUESTIONS (2026-11-18, CHAT-GAPS 1b): PR #1377
     took the measured reach from 159/180 to 166/180; these 14 were what was
     left, and FOUR of them answered the WRONG CATALOGUE ROW - a confident
     answer about a different ability, which is worse than no answer. Each now
     reaches its own row and quotes that row's `what`/`where`, never the wrong
     row, never the old family's answer; the row that used to win a shared word
     keeps its own question; and the audit's three traps stay closed.
 11. THE BEFORE/AFTER SWEEP (2026-11-18): every row's aliases, title and id
     words in 35 ordinary question shapes - 5410 questions - measured on
     origin/main at 8a20b523c and again after the change. A row may gain reach,
     never lose it: 4429 -> 4476 own-row answers, 53 changed, 47 gained, 0
     regressed. The full per-row baseline is pinned below as a ratchet.
 12. THE TWO CI GUARDS (2026-11-18, the external review's ruling). The full
     sweep above caught a real cross-pull-request break - two PRs that each
     touched jarvis_quick.py were green alone and changed each other's
     behaviour when merged, and main went red on "cloud-escalation 63 < 65".
     So every PR now runs a fast CORE SUBSET (237 pinned cases: one question
     per catalogue row naming its own title, plus the 53 answers the capability
     fix changed), and the full 5,410-question sweep runs only when
     features/features.json or the feature catalogue
     (backend/jarvis_feature_catalogue.py or its twin) changed - ci.yml's
     backend-shard job computes that with its own changed-file step and sets
     JARVIS_CAPABILITY_FULL_SWEEP=1 for one step. The two questions a later
     cloud-settings merge had lost were fixed on 2026-11-18 ("cloud-escalation"
     answers its own row again) and removed from the dated list, which is EMPTY
     today; a recorded loss is still printed on every run and never counted as
     a pass, and a NEW loss still fails the core subset.

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
#: instead of falling through.
#:
#: THE TWO "SEND A FILE FROM MY PHONE TO MY PC" SENTENCES LEFT THIS PENDING
#: STATE ON 2026-11-18. They used to fall through, correctly, while the
#: catalogue had one file row: the only file row described the PC sending TO
#: the phone, so the matcher declined rather than answer backwards (the model's
#: own denial of this class was measured on 2026-11-06). Two things changed
#: since: on 2026-11-15 the phone->PC row gained the aliases "send a file from
#: my phone to my pc" and "send a photo from my phone to my pc", and the
#: owner's own phone ask of 2026-11-18 was "Can you send a file for me to my
#: PC?" - answered "I can't send files directly" with those steps in the
#: catalogue. So they must resolve now, and the owner's exact words are the
#: fixture (both first and last entries below). The PC->phone direction still
#: answers its own row: see `t_the_thresholds_decline_rather_than_guess`.
TRAPS = (
    ("Can you send a file for me to my PC?", "document-from-phone"),
    ("Can I open and import my Notion notes as a markdown file and can you "
     "process it in the Android app and send it to the main Jarvis?",
     "notion-import"),
    ("Can I upload documents from my phone through the app and have you "
     "process them?", "document-from-phone"),
    ("Can I import a Notion export from my phone?", "notion-import"),
    ("Can I send a file from my phone to my PC?", "document-from-phone"),
    ("Can I open and import my Notion notes as a markdown file and can you "
     "process it in the Android app and send it to the main Jarvis please?",
     "notion-import"),
    ("Can I upload documents from my phone app and have you process them?",
     "document-from-phone"),
    ("Can I import a Notion export from my phone into my vault?",
     "notion-import"),
    ("Can I send a file from my phone to my PC wirelessly?", "document-from-phone"),
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

#: THE THREE MEASURED FALSE-DENIAL QUESTIONS (2026-11-18, CHAT-GAPS section 4).
#: Each one fell to the local model while the catalogue had the row with the
#: real steps, so the model could answer "I can't" about something that exists:
#:   * the PC -> phone file question - `_CAP_CAN_YOU_TO_PC` is one-way (only
#:     toward this PC), and `send_file_to_phone` is a real tool, so the mirror
#:     direction the `file-from-pc` row describes was missed;
#:   * phone notifications and spending were both named in the measured model
#:     denials of 2026-11-06.
#: `_CAP_CAN_YOU_NAMED` (jarvis_quick) claims each in `_explicit_feature_question`
#: only - the last lane in `match()`, after every action path declined - and the
#: required phrase is the row's own rule, which the false denial hid.
FALSE_DENIAL = (
    ("Can you send a file from my PC to my phone?", "file-from-pc",
     "one approval card per file"),
    ("Can you send me a file from my PC?", "file-from-pc",
     "one approval card per file"),
    ("Can you read my phone notifications?", "phone-notifications",
     "off by default"),
    ("Can you add up my spending?", "spending", "no card"),
    ("Can you check my bank export?", "spending", "no card"),
)

#: THE "and" REGRESSION (2026-11-18, CHAT-GAPS section 6). Every one of these
#: fell to the model because `_explicit_feature_question` short-circuited on
#: "and" before `_FEAT_EXPLICIT` was tried; the audit measured all six. Two of
#: them ("lets you ...", "lets Jarvis ...") also needed the speaker's frame
#: ("lets you") taken off the subject, or the row was replaced by the honest
#: "I do not have that one" - still deterministic, still wrong.
AND_QUESTIONS = (
    ("Do you have a feature that lets you type a question and Jarvis answers "
     "in the box?", "typing"),
    ('Do you have a feature called "The whole conversation, and carrying it '
     'on"?', "chat-thread"),
    ('Do you have a feature called "People and things"?', "memory-people"),
    ("Do you have a feature that lets Jarvis stop acting, and says so, rather "
     "than guessing?", "stale-link"),
    ('Do you have a feature called "Small Python scripts for sums and averages"?',
     "data-sandbox"),
    ("Do you have a feature that shows content risk and the audit chain?", "trust"),
)

#: NEGATIVE CONTROLS for every widened lead (2026-11-18). A lead may only claim
#: the one false-denial question it was written for; each sentence here keeps the
#: path it had BEFORE the lead existed. `None` as the name means "no
#: deterministic answer, so the model / its real tool keeps it" - the path those
#: sentences already had. `field`/`value` pin the field that path carries.
NARROW = (
    # a writing request is the writer's, never `email-send` - the trap the
    # audit measured when a bare "can you" lead was considered.
    ("can you write a nice email for my boss?", None, None, None),
    # the file lead requires "from my PC": the plain action shape toward the
    # phone keeps its path, and a named file is the real send_file door.
    ("Can you send a file to my phone?", None, None, None),
    ("can you send report.pdf from my desktop to my phone", "send_file",
     "query", "report.pdf"),
    ("send report.pdf from my desktop to my phone", "send_file",
     "query", "report.pdf"),
    # the file lead's destination must be the phone: "to my boss" is not it
    ("Can you send a file from my PC to my boss?", None, None, None),
    # the notification lead is read-only and needs "phone notifications": the
    # smartwatch question belongs to the phone-watch row and keeps reminder_notify
    ("Can you show my phone notifications on my watch?", "reminder_notify",
     None, None),
    # the spending lead needs spending/bank-export words: the spending DOOR and
    # the email read keep their own deterministic answers
    ("how much did I spend last month", "honest_chat", "row", "spending"),
    ("Can you read my email?", "honest_chat", "shape", "capability_off"),
    # a real sum is not "spending"
    ("Can you add 2 and 3?", None, None, None),
)

#: Action sentences that contain "and" and already had a deterministic path:
#: the short-circuit was removed from the FEATURE lane only, so these must be
#: untouched (the audit's "it cannot steal an action path" claim, pinned).
AND_ACTIONS = (
    ("remind me to call mum and dad at 5pm", "reminder_set"),
    ("add milk and eggs to my shopping list", "todo_add"),
    ("turn on the lights and the fan", "honest_chat"),
)

#: THE LAST FOURTEEN MEASURED QUESTIONS (2026-11-18, CHAT-GAPS section 1b:
#: 166/180 after PR #1377, these 14 left). Each already says its own row's
#: EXACT catalogue name - its title, or an exact alias - and was nevertheless
#: answered from somewhere else, because a generic family shares ONE word with
#: that name, or because the generic scorer read the shared word as the name:
#:
#:   * "called" stems to "call", and "call" + "phone" is `call-recording`'s own
#:     two-word name "phone call" - so "Also on my phone" and "Open an app on my
#:     phone" both landed on call-recording;
#:   * "interrupt you" is `_CAP_SAFETY`'s stop-everything phrase, so "How much
#:     Jarvis may interrupt you" was answered "Yes - Stop everything";
#:   * "start ... local model" outscored the quoted name, so the automatic
#:     restart question answered the manual start row;
#:   * the reminder family reads "sound", "reminder", "asks me ..." and "ring";
#:     the read-a-link lane reads "read ..."; the goals lane reads "goals" and
#:     the guide lane reads "reminder ...".
#:
#: Columns: (measured question, the row it must answer from, the row it must
#: NOT answer from - None when the old answer named no catalogue row at all,
#: the old intent name it must no longer be - None when the old answer had the
#: right intent name but the wrong row).
FIXED_MISSES = (
    ("Do you have a feature that lets Jarvis learn what you sound like, so it "
     "only listens to you?", "voice-training", None, "reminder_sound"),
    ('Do you have a feature called "Timers, alarms, reminders and lists"?',
     "coming-up", None, "reminder_capability"),
    ('Do you have a feature called "A reminder that asks you a question"?',
     "reminder-asks", None, "reminder_capability"),
    ('Do you have a feature called "How much Jarvis may interrupt you"?',
     "attention-budget", "stop-everything", None),
    ('Do you have a feature called "Read the words in a recording or video"?',
     "media-read", None, "read_link"),
    ('Do you have a feature called "Photo to reminder"?',
     "photo-reminder", None, "reminder_capability"),
    ('Do you have a feature called "Goals"?', "goals", None, "goal_capability"),
    ('Do you have a feature called "Also on my phone"?',
     "also-on-phone", "call-recording", None),
    ("Do you have a feature that lets Jarvis make your phone ring, to help you "
     "find it?", "find-phone", None, "reminder_sound"),
    ('Do you have a feature called "Open an app on your phone"?',
     "phone-apps", "call-recording", None),
    ('Do you have a feature called "Jarvis starts the local model again by '
     'itself when it dies"?', "restart-the-model-lane",
     "start-the-model-lane", None),
    ('Do you have a feature called "A reminder that opens something, or asks '
     'to do one task"?', "reminder-actions", None, "reminder_capability"),
    ('Do you have a feature called "Read one web page out loud"?',
     "read-web-page", None, "read_link"),
    ("Do you have a feature that asks me my saved study questions again on a "
     "schedule?", "decks", "reminder-asks", None),
)

#: THE ROWS THAT MUST NOT BE STOLEN (2026-11-18). The exact-name lane answers a
#: question only when it quotes a row's own EXACT catalogue name, so the row
#: that used to win a shared word must keep its own question, and a generic
#: family's own shape must keep its own answer. Columns: (sentence, intent
#: name, row id or None when the intent names no catalogue row).
EXACT_NAME_NEIGHBOURS = (
    ('Do you have a feature called "Record a phone call and file it as a note"?',
     "capability_answer", "call-recording"),
    ('Do you have a feature called "Start the local model when it is not '
     'running"?', "capability_answer", "start-the-model-lane"),
    ("Do you have a feature for reminder buttons?",
     "capability_answer", "reminder-asks"),
    ("Can you stop mid-answer?", "capability_answer", "stop-everything"),
    ("Can you read my phone notifications?", "capability_answer",
     "phone-notifications"),
    ("what sound does a reminder make?", "reminder_sound", None),
)

#: EVERY ORDINARY SHAPE'S OWN-ROW REACH on origin/main at 8a20b523c - the merge
#: this lane started from - measured before any change here: how many of the 35
#: questions built from that row's own aliases, title and id words answer from
#: that row THROUGH THE CATALOGUE LANE (see `CATALOGUE_INTENTS`). 4429 of 5410
#: in total. THIS IS A RATCHET: a row may gain reach, never lose it (the fix
#: measured 4476 after, 53 changed answers, 47 gained, 0 regressed).
#: Regenerate only when a catalogue name is deliberately changed, and then the
#: diff must explain every loss.
BASELINE_REACH = {k: int(v) for k, v in (
    pair.split(":") for pair in """
typing:19 prompt-coach:13 talk-button:22 wake-word:12 read-aloud:22 spoken-style:13 voice-training:17
voice-check:22 custom-voices:22 manner:29 write-like-me:19 anti-slop:39 interrupt:18 live:12 live-extras:22
talk-to-type:37 chat-thread:31 temporary-chat:37 private-chat:13 history-search:37 briefing:26 coming-up:10
reminder-asks:33 today:12 widgets:21 jobs:12 now:12 attention-budget:28 focus:12 media-transport:31
memory-tab:13 memory-saved:19 memory-waiting:13 memory-known:13 memory-people:13 people-dossier:13
pinned-facts:13 between-us:12 topics:21 memory-learning:13 wiki:12 deep-questions:13 memory-as-of:24
import-chats:22 history:12 chat-tags:22 forget-range:13 galaxy:18 media-read:33 places:24 look-at-this:22
watch-with-me:21 picture-mode:22 photo-reminder:11 live-camera:13 quiz:18 pictures:13 search-audio-video:32
decks:16 notes-write:22 notes-editor:76 folders:21 documents:36 tutorials:12 pc-help:13 web-search:12
browser-engine:22 github-watchlist:22 connected-github:36 chatbot:12 support:38 projects:12 goals:10
progress:12 file-from-pc:45 document-from-phone:97 notion-import:112 vault-organizer:31 picture-conversion:43
spending:21 retirement:21 chatbot-money:13 sensitive-facts:13 crisis-help:23 parking:39 price-radar:51
habit-checkins:58 mood-log:58 product-check:61 home-status:13 lights:21 locks:11 calendar:12 jarvis-calendar:12
weather-sky:13 email-read:13 email-send:22 email-drafts:22 inbox-tidy:13 news-and-page-watches:14 connection:21
devices:21 phone-notifications:22 phone-watch:19 phone-settings-backup:40 phone-floating:28 phone-pip:13
phone-tiles:22 phone-screen-rate:13 also-on-phone:12 find-phone:17 phone-limits:13 phone-apps:60
call-recording:40 appearance:12 crash-notes:13 faces:12 animal-options:13 first-run:28 setup-questionnaire:31
menu-visibility:31 shortcuts:12 models:12 compute:12 skills:21 model-memory:13 notifications:12 start-jarvis:12
work-tab:13 job-list:31 hardware:13 focus-presets:23 cloud-escalation:65 second-card:22 big-model:13 updates:21
tool-updates:13 settings-file:29 backend-supports:13 about:11 hud-window:13 backup:27 accounts:13 reach:28
undo:12 past-approvals:22 limits:23 settings-by-asking:13 start-the-model-lane:31 restart-the-model-lane:30
clipboard-time-machine:31 file-history:40 reminder-actions:46 thinking-levels:30 calculator:24 open-programs:31
github-research:32 computer-control:23 browser-control:22 shell-commands:41 read-web-page:33
reverse-engineering:22 android-builder:31 docker-containers:34 model-knowledge:76 voicestudio:30
wifi-auto-reconnect:43 creator-mode:31 approvals:12 what-asks-first:22 app-lock:13 captcha-handoff:13
stale-link:18 stop-everything:12 trust:18 rush-latch:22 outside-text:24 settings-entry:13 data-sandbox:28
protected-items:66 propose-plan:31 card-summary:28 receipts:27 plugin-switch:43
""".split())}


#: The intents that ANSWER FROM A CATALOGUE ROW. `honest_chat` also carries an
#: `f["row"]` for a real settings read, and whether it does depends on the
#: settings folder it reads - so the sweep counts a question as reaching its
#: row only when a catalogue answer names it. Without this the sweep would
#: measure this PC's config as much as the matcher (measured: one `spending`
#: shape answered `honest_chat` with the row in the scratch env and without it
#: under the suite's own temp config dir - a false regression).
CATALOGUE_INTENTS = frozenset({
    "capability_answer", "feature_explain", "feature_detail",
    "feature_capabilities", "feature_what", "feature_state", "feature_use",
    "feature_where", "feature_limits", "feature_asks", "feature_app",
    "feature_why", "feature_change", "feature_difference", "feature_on_off",
    "feature_switch", "feature_howto", "feature_train", "feature_how_works",
    "feature_overview", "feature_overview_about", "features_list",
    "feature_groups", "feature_detail_capability", "feature_row",
    "feature_guide",
})


def _ordinary_shapes(row):
    """The audit's 35 ordinary questions for one catalogue row.

    Every alias in ten question shapes, the title in ten, the id words in five
    - a person's ordinary words, never the row's title pasted inside a wrapper.
    This is the scratch sweep (`matrix.py` / `battery_for`) that measured the
    baseline above, kept here so the ratchet is the same instrument.
    """
    out = []
    for alias in (row.get("aliases") or ()):
        alias = str(alias).strip().rstrip(".")
        if not alias:
            continue
        for shape in ("Can you %s?", "Do you have a way to %s?",
                      "Do you have a feature for %s?", "How do I %s?",
                      "Can I %s?", "Does Jarvis %s?", "What is %s?",
                      "Where is %s?", "How do I use %s?", "Tell me about %s."):
            out.append(shape % alias)
    title = str(row.get("title") or "").strip().rstrip(".")
    for shape in ("What is %s?", "How do I use %s?", "Where is %s?",
                  "Is %s on?", "Tell me about %s.", "Do you have a feature for %s?",
                  "Can you %s?", "What are the limits of %s?",
                  "Does %s ask first?", "Explain %s."):
        out.append(shape % title)
    idwords = str(row.get("id") or "").replace("-", " ")
    for shape in ("What is %s?", "Can you %s?", "How do I %s?",
                  "Do you have a feature for %s?", "Tell me about %s."):
        out.append(shape % idwords)
    return out


# --------------------------------------------------------------------------
#   THE FAST CORE SUBSET (2026-11-18, the two CI guards the review asked for)
# --------------------------------------------------------------------------
# WHY. The 5,410-question sweep below is the exhaustive reach ratchet, and it
# found a REAL cross-pull-request break on 2026-11-18: two PRs that each touched
# `backend/jarvis_quick.py` were green alone, merged, and changed each other's
# behaviour - main is red on "no ordinary shape lost its row", cloud-escalation
# 63 < 65. The full sweep is cheap enough to keep (measured on 2026-11-18 on
# the owner's PC, three runs: the whole suite with the sweep 32-36 s, the same
# suite without it 10.4-12.7 s, so the sweep itself is about 22 s), but it is
# the wrong shape for the every-PR gate: it is one aggregate check over every
# row, so ONE slow question and 5,409 fast ones are all-or-nothing, and a
# catalogue change can add a row whose questions the every-PR job has no
# budget to learn. The review's ruling, implemented here:
#
#   * EVERY PR runs the core subset below - 237 cases, measured at 3.8-4.1 s
#     on its own - in the required `backend` job;
#   * the FULL sweep runs only when `features/features.json` or
#     `backend/jarvis_feature_catalogue.py` (or its twin
#     `jarvis-backend/jarvis_feature_catalogue.py`) changed. ci.yml's
#     `backend-shard` job computes that with its own changed-file step and
#     sets `JARVIS_CAPABILITY_FULL_SWEEP=1` for one step; nothing else sets it,
#     so a normal pull request never pays for it.
#
# WHAT THE CORE IS - two pinned lists, both questions the full sweep already
# asks, so "the core is a subset of the full sweep" is a fact this file can
# prove (and `backend/test_capability_core_subset.py` does prove).
#
# CORE_OWNER_WORDED (184): one ordinary question naming each catalogue row's
# own title - the words the owner reads on the Features pages. It is the
# per-row ratchet, one question per row, so a row that loses its own words
# fails on every PR. 184 is the catalogue's own length; the review's "180" was
# the live audit's measured-row count, and a row added without a reachable
# title question fails here the same way.
#
# CORE_REGRESSION (53): every sweep question whose answer the 2026-11-18
# capability fix CHANGED, measured on the pre-fix tree (origin/main at
# 8a20b523c) and again on the fixed tree: 53 changed, 47 gained their own row,
# 0 regressed, and six multi-row answers stopped naming a second row they
# should never have named. These are the questions a later matcher change is
# most likely to disturb, so they are pinned by name.
#
# CORE_KNOWN_LOST (0 today): the same measurement re-run on THIS tree had also
# shown two questions LOST after the fix, by the later cloud-settings lane:
# "Does Jarvis escalate to the cloud?" and "What is cloud escalation?" answered
# `cloud_settings` instead of the `cloud-escalation` row - the full sweep's
# "cloud-escalation 63 < 65", measured on main on 2026-11-18. That row was
# fixed on 2026-11-18: the sweep now prints "FIXED" for both and they were
# removed, so this dated list is EMPTY. Keep the mechanism: an entry added here
# is printed on EVERY run and NEVER counted as a pass, a loss that is NOT on
# this list fails the core subset, and an entry whose row is fixed again prints
# "FIXED, remove me" (backend/test_capability_core_subset.py proves both halves
# by planting entries, since the live list is empty today).
CORE_OWNER_WORDED = (
    ('What is Type a message and read the answer?', 'typing'),
    ('What is Check a prompt before you send it?', 'prompt-coach'),
    ('What is The talk button?', 'talk-button'),
    ('What is Say "Hey Jarvis"?', 'wake-word'),
    ('What is Jarvis reads its answers aloud?', 'read-aloud'),
    ('What is Short answers to spoken questions?', 'spoken-style'),
    ('What is Teach Jarvis your voice?', 'voice-training'),
    ('What is How strict the voice check is?', 'voice-check'),
    ('What is The voice Jarvis speaks with?', 'custom-voices'),
    ('What is How Jarvis talks?', 'manner'),
    ('What is Write like me?', 'write-like-me'),
    ('What is Anti-Slop filter?', 'anti-slop'),
    ('What is Interrupt Jarvis while it talks?', 'interrupt'),
    ('What is Jarvis Live?', 'live'),
    ('What is The extras around Live?', 'live-extras'),
    ('What is Talk-to-type?', 'talk-to-type'),
    ('What is The whole conversation, and carrying it on?', 'chat-thread'),
    ('What is Incognito chat?', 'temporary-chat'),
    ('What is Private chat?', 'private-chat'),
    ('What is Search what was said?', 'history-search'),
    ('Tell me about The morning briefing.', 'briefing'),
    ('What is Timers, alarms, reminders and lists?', 'coming-up'),
    ('What is A reminder that asks you a question?', 'reminder-asks'),
    ('What is Today?', 'today'),
    ('What is Widgets you describe?', 'widgets'),
    ('What is Background jobs?', 'jobs'),
    ('What is What Jarvis is doing right now?', 'now'),
    ('What is How much Jarvis may interrupt you?', 'attention-budget'),
    ('What is Focus session?', 'focus'),
    ('What is Play or pause what is on this PC?', 'media-transport'),
    ('What is The Memory tab?', 'memory-tab'),
    ('What is Facts Jarvis saved by itself?', 'memory-saved'),
    ('What is Facts waiting for your yes?', 'memory-waiting'),
    ('What is What Jarvis knows about you?', 'memory-known'),
    ('What is People and things?', 'memory-people'),
    ('What is Person dossier?', 'people-dossier'),
    ('What is Always keep in mind?', 'pinned-facts'),
    ('What is Between us?', 'between-us'),
    ('What is Topics?', 'topics'),
    ('What is The learning switches?', 'memory-learning'),
    ('What is The wiki Jarvis builds?', 'wiki'),
    ('What is Deep questions?', 'deep-questions'),
    ('What is What did I believe on this date??', 'memory-as-of'),
    ('What is Bring in old chats?', 'import-chats'),
    ('What is Your past chats?', 'history'),
    ('What is Chat tags?', 'chat-tags'),
    ('What is Forget a time frame?', 'forget-range'),
    ('What is Galaxy?', 'galaxy'),
    ('What is Read the words in a recording or video?', 'media-read'),
    ('What is Where did I put things?', 'places'),
    ('What is Look at this?', 'look-at-this'),
    ('What is Watch with me?', 'watch-with-me'),
    ('What is Picture mode?', 'picture-mode'),
    ('What is Photo to reminder?', 'photo-reminder'),
    ('What is Show Jarvis the camera in Live?', 'live-camera'),
    ('What is Quiz me on a text?', 'quiz'),
    ('What is Ask for a picture, and keep it?', 'pictures'),
    ('What is Search what was said in audio and video?', 'search-audio-video'),
    ('What is My study decks?', 'decks'),
    ('What is Write a note for you?', 'notes-write'),
    ('What is Create and customize your notes?', 'notes-editor'),
    ('What is Folders Jarvis may look in?', 'folders'),
    ('What is Ask about a PDF, a Word file or a Notion page?', 'documents'),
    ('What is Tutorials and the FAQ?', 'tutorials'),
    ('What is PC help?', 'pc-help'),
    ('What is Web search?', 'web-search'),
    ('What is A browser without a window?', 'browser-engine'),
    ("What is What's new on GitHub?", 'github-watchlist'),
    ('What is Read and act on your own GitHub?', 'connected-github'),
    ('What is Talk to a chatbot for me?', 'chatbot'),
    ('What is Deal with customer support for me?', 'support'),
    ('What is Projects?', 'projects'),
    ('What is Goals?', 'goals'),
    ('What is Progress?', 'progress'),
    ('What is File from your PC?', 'file-from-pc'),
    ('What is Send a document from your phone?', 'document-from-phone'),
    ('What is Import a Notion export into an Obsidian vault?', 'notion-import'),
    ('What is Organize an Obsidian vault?', 'vault-organizer'),
    ("What is Make a PDF from pictures, or change a picture's format?", 'picture-conversion'),
    ('What is Spending summaries?', 'spending'),
    ('What is Retirement what-if?', 'retirement'),
    ('What is Chatbot keys and a monthly money limit?', 'chatbot-money'),
    ('What is Health and money facts wait for your yes?', 'sensitive-facts'),
    ('What is Crisis help?', 'crisis-help'),
    ('What is What a parking stay costs, and free parking?', 'parking'),
    ('What is Flight prices and a price history?', 'price-radar'),
    ('What is Habit check-ins?', 'habit-checkins'),
    ('What is Mood log?', 'mood-log'),
    ("What is Check a product's reviews?", 'product-check'),
    ('What is Ask how the house is?', 'home-status'),
    ('What is Lights, plugs and fans?', 'lights'),
    ('What is Locks, doors, alarms and covers?', 'locks'),
    ('What is Read your own calendar?', 'calendar'),
    ('What is Jarvis Calendar?', 'jarvis-calendar'),
    ('What is Weather and the sky behind the animals?', 'weather-sky'),
    ('What is Jarvis reads your email?', 'email-read'),
    ('What is Send an email for you?', 'email-send'),
    ('What is Save a draft to your Drafts folder?', 'email-drafts'),
    ('What is Tidy the inbox by voice?', 'inbox-tidy'),
    ('What is News headlines, and pages that change?', 'news-and-page-watches'),
    ('What is Pairing and the connection?', 'connection'),
    ('What is Devices?', 'devices'),
    ('What is Let Jarvis read phone notifications?', 'phone-notifications'),
    ('What is Smartwatch notifications?', 'phone-watch'),
    ('What is Set up a new phone from a settings backup?', 'phone-settings-backup'),
    ('What is Floating Jarvis?', 'phone-floating'),
    ('What is Picture-in-picture?', 'phone-pip'),
    ('What is Quick Settings tiles?', 'phone-tiles'),
    ('What is Screen refresh rate?', 'phone-screen-rate'),
    ('What is Also on my phone?', 'also-on-phone'),
    ('What is Ring my phone?', 'find-phone'),
    ('What is What the phone deliberately does not do?', 'phone-limits'),
    ('What is Open an app on your phone?', 'phone-apps'),
    ('What is Record a phone call and file it as a note?', 'call-recording'),
    ('What is Appearance?', 'appearance'),
    ('What is Hang and crash notes?', 'crash-notes'),
    ("What is Choose Jarvis's face?", 'faces'),
    ('What is Animal options?', 'animal-options'),
    ('What is Set up Jarvis?', 'first-run'),
    ('What is First-time setup questionnaire?', 'setup-questionnaire'),
    ('What is Show or hide menus?', 'menu-visibility'),
    ('What is Keyboard shortcuts?', 'shortcuts'),
    ('What is Models?', 'models'),
    ('What is Compute?', 'compute'),
    ('What is Skills?', 'skills'),
    ('What is Memory on the Model page?', 'model-memory'),
    ('What is Notifications?', 'notifications'),
    ('What is Starting Jarvis for you?', 'start-jarvis'),
    ('What is The Work tab?', 'work-tab'),
    ('What is Jobs that keep going after the chat ends?', 'job-list'),
    ('What is Hardware and models?', 'hardware'),
    ('Tell me about Focus presets.', 'focus-presets'),
    ('What is Cloud (an API service you choose)?', 'cloud-escalation'),
    ('What is The second graphics card?', 'second-card'),
    ('What is The big model (slow)?', 'big-model'),
    ('What is Updates?', 'updates'),
    ('What is Check for tool updates?', 'tool-updates'),
    ('What is The settings file, the logs and starting with Windows?', 'settings-file'),
    ('What is What this backend supports?', 'backend-supports'),
    ('What is About Jarvis?', 'about'),
    ('What is The big HUD window?', 'hud-window'),
    ('What is Backups?', 'backup'),
    ('What is Accounts and keys?', 'accounts'),
    ('What is What Jarvis can reach?', 'reach'),
    ('What is Undo?', 'undo'),
    ('What is Activity: cards you already decided?', 'past-approvals'),
    ('What is Limits and frequency?', 'limits'),
    ('What is Change a setting by asking, in any words?', 'settings-by-asking'),
    ('What is Start the local model when it is not running?', 'start-the-model-lane'),
    ('What is Jarvis starts the local model again by itself when it dies?', 'restart-the-model-lane'),
    ('What is Clipboard history, and three one-press cleanups for what you copy?', 'clipboard-time-machine'),
    ('What is File history?', 'file-history'),
    ('What is A reminder that opens something, or asks to do one task?', 'reminder-actions'),
    ('What is Thinking levels?', 'thinking-levels'),
    ('What is Do arithmetic?', 'calculator'),
    ('What is Open a program or Windows panel by name?', 'open-programs'),
    ('What is Find and grade a library on GitHub?', 'github-research'),
    ('What is Click and type in another program?', 'computer-control'),
    ('What is Drive one browser tab?', 'browser-control'),
    ('What is Run one shell command?', 'shell-commands'),
    ('What is Read one web page out loud?', 'read-web-page'),
    ('What is Inspect a program or app statically?', 'reverse-engineering'),
    ('What is Build the Android app in a project task?', 'android-builder'),
    ('What is Docker containers Jarvis ships?', 'docker-containers'),
    ('What is Ask which model is answering?', 'model-knowledge'),
    ('What is A second voice program (VoiceStudio)?', 'voicestudio'),
    ('What is Reconnect to Wi-Fi by itself?', 'wifi-auto-reconnect'),
    ('What is Creator mode: put a skill or a plug-in in a waiting folder?', 'creator-mode'),
    ('What is Approval cards?', 'approvals'),
    ('What is What asks first?', 'what-asks-first'),
    ('What is Lock Jarvis, and hide what it remembers?', 'app-lock'),
    ('What is Hand a captcha to your phone ("Solve it here")?', 'captcha-handoff'),
    ('What is When the connection is catching up?', 'stale-link'),
    ('What is Stop everything?', 'stop-everything'),
    ('What is Trust: content risk and the audit chain?', 'trust'),
    ('What is A warning when text tried to rush you?', 'rush-latch'),
    ('What is Jarvis marks what it read from outside?', 'outside-text'),
    ('What is Settings itself?', 'settings-entry'),
    ('What is Small Python scripts for sums and averages?', 'data-sandbox'),
    ('Tell me about Protected from Jarvis.', 'protected-items'),
    ('What is A short plan of several steps, one card?', 'propose-plan'),
    ('What is A short card, then Explain more?', 'card-summary'),
    ('What is A receipt for every change?', 'receipts'),
    ('What is Turn a drop-in module on or off by asking?', 'plugin-switch'),
)

CORE_REGRESSION = (
    ('Do you have a feature for Type a message and read the answer?', 'typing'),
    ('Do you have a way to learn what you sound like, so it only listens to you?', 'voice-training'),
    ('Do you have a feature for learn what you sound like, so it only listens to you?', 'voice-training'),
    ('Do you have a feature for Timers, alarms, reminders and lists?', 'coming-up'),
    ('Do you have a way to reminder buttons?', 'reminder-asks'),
    ('Do you have a feature for reminder buttons?', 'reminder-asks'),
    ('Do you have a way to reminder answer?', 'reminder-asks'),
    ('Do you have a feature for reminder answer?', 'reminder-asks'),
    ('Do you have a feature for A reminder that asks you a question?', 'reminder-asks'),
    ('Do you have a feature for reminder asks?', 'reminder-asks'),
    ('Do you have a feature for How much Jarvis may interrupt you?', 'attention-budget'),
    ('Do you have a feature for Read the words in a recording or video?', 'media-read'),
    ('Do you have a feature for Photo to reminder?', 'photo-reminder'),
    ('Do you have a feature for photo reminder?', 'photo-reminder'),
    ('Do you have a way to asks me my saved study questions again on a schedule?', 'decks'),
    ('Do you have a feature for asks me my saved study questions again on a schedule?', 'decks'),
    ('Do you have a way to reads a pdf or a word file and answers questions about it?', 'documents'),
    ('Do you have a feature for reads a pdf or a word file and answers questions about it?', 'documents'),
    ('Do you have a feature for Goals?', 'goals'),
    ('Do you have a feature for goals?', 'goals'),
    ('Do you have a feature for Locks, doors, alarms and covers?', 'locks'),
    ('Do you have a way to make your phone ring, to help you find it?', 'find-phone'),
    ('Do you have a feature for make your phone ring, to help you find it?', 'find-phone'),
    ('Do you have a feature for Ring my phone?', 'find-phone'),
    ('Do you have a way to tells me when a newer build of this app exists and installs it?', 'updates'),
    ('Do you have a feature for tells me when a newer build of this app exists and installs it?', 'updates'),
    ('Do you have a feature for Jarvis starts the local model again by itself when it dies?', 'restart-the-model-lane'),
    ('Do you have a way to reminder action?', 'reminder-actions'),
    ('Do you have a feature for reminder action?', 'reminder-actions'),
    ('Do you have a way to open a page from a reminder?', 'reminder-actions'),
    ('Do you have a feature for open a page from a reminder?', 'reminder-actions'),
    ('Do you have a way to open a file from a reminder?', 'reminder-actions'),
    ('Do you have a feature for open a file from a reminder?', 'reminder-actions'),
    ('Do you have a way to reminder that opens?', 'reminder-actions'),
    ('Do you have a feature for reminder that opens?', 'reminder-actions'),
    ('Do you have a way to run a task from a reminder?', 'reminder-actions'),
    ('Do you have a feature for run a task from a reminder?', 'reminder-actions'),
    ('Do you have a feature for A reminder that opens something, or asks to do one task?', 'reminder-actions'),
    ('Do you have a feature for reminder actions?', 'reminder-actions'),
    ('Do you have a feature for Click and type in another program?', 'computer-control'),
    ('Do you have a way to read a web page?', 'read-web-page'),
    ('Do you have a feature for read a web page?', 'read-web-page'),
    ('Do you have a way to read a page?', 'read-web-page'),
    ('Do you have a feature for read a page?', 'read-web-page'),
    ('Do you have a way to read a link?', 'read-web-page'),
    ('Do you have a feature for read a link?', 'read-web-page'),
    ('Do you have a way to reading a link?', 'read-web-page'),
    ('Do you have a feature for reading a link?', 'read-web-page'),
    ('Do you have a feature for Read one web page out loud?', 'read-web-page'),
    ('Do you have a feature for read web page?', 'read-web-page'),
    ('Do you have a way to put a skill in a waiting folder?', 'creator-mode'),
    ('Do you have a feature for put a skill in a waiting folder?', 'creator-mode'),
    ('Do you have a feature for When the connection is catching up?', 'stale-link'),
)

#: EMPTY today: the two cloud-escalation questions this dated list recorded on
#: 2026-11-18 were fixed on 2026-11-18 and removed. Keep the mechanism - a new
#: loss that is NOT on this list fails the core subset.
CORE_KNOWN_LOST = ()

#: The ONE variable that turns the full 5,410-question sweep on. ci.yml's
#: `backend-shard` job sets it for a commit that changed the feature catalogue
#: (see the changed-file step there); nothing else ever sets it.
FULL_SWEEP_ENV = "JARVIS_CAPABILITY_FULL_SWEEP"


def full_sweep_enabled(environ=None):
    """Is this run allowed to pay for the full 5,410-question sweep?"""
    env = os.environ if environ is None else environ
    return env.get(FULL_SWEEP_ENV, "") == "1"


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


def _ids_of(reply_or_intent):
    """Every catalogue row id a matched intent names - one row or several."""
    if reply_or_intent is None:
        return []
    f = reply_or_intent.f or {}
    out = [f["id"]] if f.get("id") else []
    out += list(f.get("ids") or ())
    return out


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
    # The measured report needs at least six of the traps answered without a model.
    check("at least 6 of the traps are answered without the model",
          resolved >= 6, f"{resolved} answered")


# --------------------------------------------------------------------------
#   1b. the owner's phone report of 2026-11-18, verbatim
# --------------------------------------------------------------------------
def t_the_owner_s_phone_file_question():
    """The owner asked, on the phone: "Can you send a file for me to my PC?"

    Jarvis answered "I can't send files directly, but I can help you move files
    between your phone and PC. Would you like me to show you how to do that?" -
    while the catalogue carried the exact steps (`where` on `document-from-
    phone`) and, since 2026-11-15, the alias "send a file from my phone to my
    pc". TWO causes, pinned separately here so fixing one cannot hide the other:

      * "can you ..." was never a capability lead. `_CAP_LEAD` takes "can i",
        "do you have", "how do i" and so on, but NOT "can you" - that is the
        shape the owner uses to ask Jarvis to DO things, and
        `backend/test_chat_honesty.py` pins that a writing request keeps its
        own path. So on this sentence the tail was empty and the catalogue was
        never consulted at all; the question went to the model.
      * with a lead that DOES match ("Can I send a file from my phone to my
        PC?") the resolver still returned None: `file-from-pc` - whose own id
        says "file from pc" - scored highest, the direction rule rejected it,
        and `_cap_resolve` gave up instead of taking the direction-correct
        `document-from-phone`.

    Both are answered from the catalogue now, with the row's own words and its
    own steps, and the measured denial is gone.
    """
    said = "Can you send a file for me to my PC?"
    res, intent = _answer(said)
    check("the owner's exact sentence is answered from the catalogue",
          _row_of(intent) == "document-from-phone", _row_of(intent))
    row = BY_ID["document-from-phone"]
    if res is not None:
        check("... with the row's own what quoted verbatim",
              _quote(row, "what") in res.reply, res.reply[:200])
        check("... and its own steps (where) quoted verbatim",
              _quote(row, "where") in res.reply, res.reply[:240])
        check("... naming the phone's own Settings door",
              "Settings, Folders Jarvis may look in, then Send a file from your "
              "phone" in res.reply, res.reply[:280])
        check("... and never the model's measured denial",
              not any(d in res.reply.lower() for d in DENIALS), res.reply[:200])
    # The measured words ARE a catalogue alias now, so the matcher names the
    # door from the source rather than from a phrase in this file.
    check("the owner's measured words are a catalogue alias",
          any("send a file for me to my pc" in str(a)
              for a in row.get("aliases") or ()), row.get("aliases"))
    # Cause 2 on its own, with a lead the old matcher already took.
    res2, intent2 = _answer("Can I send a file from my phone to my PC?")
    check("the 'can I' form resolves to the same door",
          _row_of(intent2) == "document-from-phone", _row_of(intent2))
    check("... and never to the opposite-direction PC door",
          _row_of(intent2) != "file-from-pc", _row_of(intent2))
    # The direction the real tool DOES cover keeps its own path: send_file_to_phone
    # is a real tool that raises its one card, so a "can you" sentence toward the
    # phone must not be claimed by the catalogue lane.
    check("the PC-to-phone direction keeps its own path",
          Q.match("Can you send a file to my phone?") is None,
          Q.match("Can you send a file to my phone?"))


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
#   1c. the three measured false-denial questions (CHAT-GAPS section 4)
# --------------------------------------------------------------------------
def t_the_three_measured_false_denial_questions():
    """Each must answer from the catalogue row, not fall to the model.

    Before the leads existed all five sentences below returned None from
    `match()`, so the local model answered - and that model was measured
    denying all three feature classes on this PC (2026-11-06).
    """
    for sentence, row_id, rule in FALSE_DENIAL:
        res, intent = _answer(sentence)
        check(f"false denial is answered from the catalogue: {sentence!r}",
              _row_of(intent) == row_id, f"{_row_of(intent)} != {row_id}")
        if res is None:
            continue
        row = BY_ID[row_id]
        check(f"... quoting the row's own what: {sentence!r}",
              _quote(row, "what") in res.reply, res.reply[:220])
        check(f"... quoting the row's own where: {sentence!r}",
              _quote(row, "where") in res.reply, res.reply[:240])
        low = res.reply.lower()
        check(f"... with its own rule ({rule!r}) and no denial: {sentence!r}",
              rule in low and not any(d in low for d in DENIALS),
              res.reply[:260])
        # THE REAL ROUTE, not only match(): /api/chat calls `answer_turn`, and
        # the question must come back from there with the same row - a fixed
        # `match()` that the request path never asks is no fix at all. The
        # route hands back a `Result` (not the Intent), so the row is read off
        # the answer's own quoted `what`, which only that row carries.
        body = {"messages": [{"role": "user", "content": sentence,
                              "provenance": "typed"}]}
        turn = Q.answer_turn(body, sched=Sched())
        check(f"... and /api/chat's own route answers it without the model: "
              f"{sentence!r}",
              turn is not None and turn.intent == "capability_answer"
              and _quote(row, "what") in turn.reply,
              None if turn is None else (turn.intent, turn.reply[:160]))


def t_the_false_denial_leads_stay_narrow():
    """Every widened lead has a control that keeps the path it had before.

    The audit's trap is measured: a bare "can you ..." capability lead would
    claim "can you write a nice email for my boss?" as `email-send`, which
    `backend/test_chat_honesty.py` pins to the writer's own path. So each lead
    is the words of ONE question, and every sentence here is a neighbour that
    must not move.
    """
    for sentence, expected, field, value in NARROW:
        intent = Q.match(sentence)
        name = None if intent is None else intent.name
        check(f"a widened lead did not claim its control: {sentence!r}",
              name == expected, f"{name!r} != {expected!r}")
        if field is not None and intent is not None:
            got = (intent.f or {}).get(field)
            check(f"... and it still carries its own {field}: {sentence!r}",
                  got == value, f"{field}={got!r}")
        # ... and the request route keeps it too (/api/chat calls answer_turn).
        body = {"messages": [{"role": "user", "content": sentence,
                              "provenance": "typed"}]}
        turn = Q.answer_turn(body, sched=Sched())
        turn_name = None if turn is None else turn.intent
        check(f"... and /api/chat's route keeps that path: {sentence!r}",
              turn_name == expected, f"{turn_name!r} != {expected!r}")


# --------------------------------------------------------------------------
#   1d. the "and" regression (CHAT-GAPS section 6)
# --------------------------------------------------------------------------
def t_a_feature_question_with_and_reaches_its_row():
    """The explicit feature lane no longer short-circuits on "and".

    Before the fix every sentence below returned None from `match()` (the
    model answered), because `_explicit_feature_question` refused any text
    containing "and" before trying `_FEAT_EXPLICIT`. It was redundant: the
    two-part matcher ran earlier and this lane runs last in `match()`.
    """
    for sentence, row_id in AND_QUESTIONS:
        label = sentence[:54] + ("..." if len(sentence) > 54 else "")
        res, intent = _answer(sentence)
        check(f"an 'and' feature question reaches its row: {label}",
              _row_of(intent) == row_id, f"{_row_of(intent)} != {row_id}")
        if res is None:
            continue
        low = res.reply.lower()
        check(f"... answered from the row's own words, never 'not that one': "
              f"{label}",
              _quote(BY_ID[row_id], "what") in res.reply
              and "do not have that one" not in low
              and "i do not have" not in low, res.reply[:220])
    # Removing the short-circuit from the FEATURE lane must not touch a
    # sentence that already has a deterministic owner - that is the audit's
    # "this lane runs last, so it cannot steal an action path" claim, pinned.
    for sentence, expected in AND_ACTIONS:
        intent = Q.match(sentence)
        name = None if intent is None else intent.name
        check(f"an 'and' action keeps its own path: {sentence!r}",
              name == expected, f"{name!r} != {expected!r}")


# --------------------------------------------------------------------------
#   1e. the LAST fourteen measured questions (CHAT-GAPS 1b, 166/180 -> 180/180)
# --------------------------------------------------------------------------
def t_the_last_fourteen_measured_questions_reach_their_rows():
    """Each of these names its own row exactly and used to answer elsewhere.

    The fix is `_named_feature_question` (`jarvis_quick`): a question that says
    "feature" and quotes a catalogue row's EXACT id, title or alias is that
    row's question, and it now runs before the generic families that share one
    word with the name. Before it, these 14 were the measured 166/180:
      * four answered a WRONG CATALOGUE ROW - the worst kind of answer, a
        confident sentence about a different ability (attention-budget ->
        stop-everything; also-on-phone and phone-apps -> call-recording;
        restart-the-model-lane -> start-the-model-lane, and decks ->
        reminder-asks);
      * the other nine were answered by another deterministic family (the
        reminder sound/capability family, the read-a-link lane, the goals lane)
        or did not answer from the row's own words at all.
    """
    for sentence, row_id, wrong_row, old_intent in FIXED_MISSES:
        label = sentence[:54] + ("..." if len(sentence) > 54 else "")
        res, intent = _answer(sentence)
        check(f"a measured miss reaches its row: {label}",
              _row_of(intent) == row_id, f"{_row_of(intent)} != {row_id}")
        if wrong_row is not None:
            # THE WRONG ROW IT MUST NO LONGER RESOLVE TO - read from the ids,
            # never from the answer's prose (a row's name can appear in another
            # row's words).
            check(f"... never the row that used to win ({wrong_row}): {label}",
                  wrong_row not in _ids_of(intent), str(_ids_of(intent)))
        if old_intent is not None:
            # The old answer was a DIFFERENT deterministic family - a real
            # answer, about the wrong ability. It must be gone, not only outranked.
            name = None if intent is None else intent.name
            check(f"... and not the old answer ({old_intent}): {label}",
                  name != old_intent, f"{name!r}")
        if res is None:
            continue
        row = BY_ID[row_id]
        check(f"... quoting the row's own what: {label}",
              _quote(row, "what") in res.reply, res.reply[:220])
        check(f"... quoting the row's own where: {label}",
              _quote(row, "where") in res.reply, res.reply[:240])
        low = res.reply.lower()
        check(f"... with no denial and no invented app: {label}",
              not any(d in low for d in DENIALS)
              and not any(i in low for i in INVENTED), res.reply[:220])
        # The real request route, not only match(): /api/chat calls answer_turn.
        body = {"messages": [{"role": "user", "content": sentence,
                              "provenance": "typed"}]}
        turn = Q.answer_turn(body, sched=Sched())
        check(f"... and /api/chat's own route answers it: {label}",
              turn is not None and turn.intent == "capability_answer"
              and _quote(row, "what") in turn.reply,
              None if turn is None else (turn.intent, turn.reply[:160]))


def t_the_exact_name_lane_steals_no_other_row_s_question():
    """Fixing a shared word must leave the other row's own question alone.

    The four wrong-row answers shared a word; the row that used to win it must
    keep its own question, and the generic families above must keep their own
    shapes. Only an EXACT catalogue name is claimed, so none of these moved.
    """
    for sentence, expected_intent, expected_row in EXACT_NAME_NEIGHBOURS:
        intent = Q.match(sentence)
        name = None if intent is None else intent.name
        got_row = _row_of(intent)
        check(f"an exact-name fix left its neighbour alone: {sentence[:46]}",
              name == expected_intent and got_row == expected_row,
              f"{name!r}/{got_row!r} != {expected_intent!r}/{expected_row!r}")
    # The audit's three traps, verbatim: the lane must not widen to catch them.
    for sentence in ("can you write a nice email for my boss?",
                     "Can you send a file to my phone?",
                     "Can you add 2 and 3?"):
        check(f"the trap stays closed: {sentence!r}",
              Q.match(sentence) is None, repr(Q.match(sentence)))


# --------------------------------------------------------------------------
#   1f. THE FAST CORE SUBSET (every pull request), and the full sweep (only
#       when the feature catalogue changed)
# --------------------------------------------------------------------------
def t_the_core_subset_holds():
    """The 237 cases every pull request runs, proving the per-row ratchet.

    Three groups, all questions the full sweep below already asks:
      * CORE_OWNER_WORDED - one question naming each catalogue row's own title;
      * CORE_REGRESSION - the 53 answers the capability fix changed;
      * CORE_KNOWN_LOST - a dated allowance that is EMPTY today: the two
        answers a later merge had taken away (the full sweep's "cloud-escalation
        63 < 65") were fixed on 2026-11-18 and removed. Any loss NOT on the
        list fails here, so the list can only ever shrink honestly.
    """
    rows = {row["id"] for row in C.FEATURES}
    pinned = {row_id for _sentence, row_id in CORE_OWNER_WORDED}
    new_rows = sorted(rows - pinned)
    old_rows = sorted(pinned - rows)
    check(f"the core subset carries its {len(CORE_OWNER_WORDED)} owner-worded "
          "cases, one for EVERY catalogue row",
          len(CORE_OWNER_WORDED) == len(C.FEATURES) == 184
          and pinned == rows and not new_rows and not old_rows,
          f"{len(CORE_OWNER_WORDED)} cases, {len(C.FEATURES)} rows; "
          f"rows with no core question: {new_rows[:5]}; pinned ids that are "
          f"no longer rows: {old_rows[:5]} - add one question naming the new "
          "row's own title to CORE_OWNER_WORDED")
    check("... its 53 regression-sensitive cases",
          len(CORE_REGRESSION) == 53, str(len(CORE_REGRESSION)))
    check("... and no dated known-loss entries today (the two cloud-escalation "
          "questions were fixed on 2026-11-18 and removed)",
          len(CORE_KNOWN_LOST) == 0, str(len(CORE_KNOWN_LOST)))

    known = {sentence for sentence, _row, _wrong in CORE_KNOWN_LOST}
    questions = ([sentence for sentence, _row in CORE_OWNER_WORDED]
                 + [sentence for sentence, _row in CORE_REGRESSION]
                 + [sentence for sentence, _row, _wrong in CORE_KNOWN_LOST])
    matches = {sentence: Q.match(sentence) for sentence in questions}

    lost = []
    for sentence, row_id in CORE_OWNER_WORDED:
        got = _row_of(matches[sentence])
        if got != row_id and sentence not in known:
            lost.append(f"{sentence!r} -> {got!r}, not {row_id!r}")
    check(f"every catalogue row still answers a question naming its own title "
          f"({len(CORE_OWNER_WORDED)} rows, 0 lost required)",
          not lost, "; ".join(lost[:8]))

    broken = []
    for sentence, row_id in CORE_REGRESSION:
        got = _row_of(matches[sentence])
        if got != row_id and sentence not in known:
            broken.append(f"{sentence!r} -> {got!r}, not {row_id!r}")
    check(f"every one of the {len(CORE_REGRESSION)} answers the capability fix "
          "changed still reaches its own row (0 regressions required)",
          not broken, "; ".join(broken[:8]))

    # The dated known losses: reported ALWAYS, never counted as passes, and a
    # NEW loss fails. A recorded one that starts passing asks to be removed.
    for sentence, row_id, _wrong in CORE_KNOWN_LOST:
        intent = matches[sentence]
        got = _row_of(intent)
        if got == row_id:
            print(f"   FIXED, remove from CORE_KNOWN_LOST: {sentence!r} answers "
                  f"{row_id!r} again")
        else:
            where = repr(got) if got else f"no catalogue row (intent " \
                f"{getattr(intent, 'name', None)!r})"
            print(f"   KNOWN LOST (recorded 2026-11-18, the cloud-settings "
                  f"merge; NOT a pass): {sentence!r} must answer {row_id!r}, "
                  f"it answers {where}")
    unexpected = [f"{sentence!r} -> {_row_of(matches[sentence])!r}"
                  for sentence, _row in CORE_OWNER_WORDED + CORE_REGRESSION
                  if sentence not in known
                  and _row_of(matches[sentence]) != _row]
    check("every core case answers from its own row - the dated known-loss list "
          "is empty today, so any NEW loss fails here",
          not unexpected, "; ".join(unexpected[:8]))
    print(f"   the full 5,410-question sweep is "
          f"{'RUNNING' if full_sweep_enabled() else 'NOT running in this mode; it runs when features/features.json or the feature catalogue changed'}")


# --------------------------------------------------------------------------
#   1g. the before/after sweep over EVERY row's ordinary shapes
# --------------------------------------------------------------------------
def t_no_ordinary_shape_lost_its_row():
    """Every row's aliases, title and id words, in ordinary question shapes.

    5410 questions (184 rows: 10 forms per alias, 10 title forms, 5 id forms).
    This is the sweep that measured origin/main at 8a20b523c before the change
    and the fixed tree after, so a regression is a row that used to be
    reachable by its own ordinary words and no longer is:
      * before: 4429/5410 questions answered from their own row;
      * after:  4476/5410; 53 answers changed, 47 gained their own row,
        0 regressed, and 6 multi-row answers lost a second row they should
        never have named (they answered two rows because "and" split the
        subject, e.g. "Do you have a feature for Click and type in another
        program?" named computer-control AND talk-to-type; it now names only
        computer-control).
    "Answered from their own row" means a CATALOGUE answer names it (see
    `CATALOGUE_INTENTS`): the sweep must measure the matcher, not this PC's
    settings folder.
    BOTH TREES: `backend/` and the published base `jarvis-backend/` were swept
    separately and gave the identical 4476. That is not surprising - the two
    matcher files are byte-identical (asserted below) and `check_stale_twins`
    holds every shipped twin - so one in-process run on the checkout's copy is
    enough here.
    """
    if not full_sweep_enabled():
        print("SKIP the full 5,410-question sweep: this run is the every-PR "
              "CORE subset, which passed above. The full sweep runs only when "
              "features/features.json or the feature catalogue (or its twin) "
              "changed - ci.yml's backend-shard job sets "
              f"{FULL_SWEEP_ENV}=1 for that run. This is NOT a pass for the "
              "full sweep: it did not run here.")
        return
    twin = REPO / "jarvis-backend" / "jarvis_quick.py"
    check("the swept matcher has a byte-identical twin in jarvis-backend",
          twin.is_file() and twin.read_bytes() == (HERE / "jarvis_quick.py").read_bytes())
    total, below, gained_rows = 0, [], []
    for row in C.FEATURES:
        got = 0
        for sentence in _ordinary_shapes(row):
            intent = Q.match(sentence)
            if (intent is not None and intent.name in CATALOGUE_INTENTS
                    and row["id"] in _ids_of(intent)):
                got += 1
        total += got
        base = BASELINE_REACH.get(row["id"])
        if base is not None and got < base:
            below.append("%s %d<%d" % (row["id"], got, base))
        if base is not None and got > base:
            gained_rows.append(row["id"])
    check(f"the sweep has the {len(BASELINE_REACH)}-row baseline's reach: "
          f"{total} own-row answers (baseline {sum(BASELINE_REACH.values())})",
          total >= sum(BASELINE_REACH.values()),
          f"{total} < {sum(BASELINE_REACH.values())}")
    check("no ordinary shape lost its row (0 regressions required)",
          not below, "; ".join(below[:8]))
    check("the sweep measured a gain, not only a preserved total",
          len(gained_rows) >= 10, f"{len(gained_rows)} rows gained")


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
#   6. every one of the 184 rows answers from itself
# --------------------------------------------------------------------------
# 184 since 2026-11-18, the picture-conversion row (pictures into one PDF, or
# one picture into another format). The pin is the catalogue's real length, so
# a row that is added without an answer of its own words fails here.
def t_every_catalogue_row_answers_from_its_own_words():
    check("the catalogue has its 184 rows", len(C.FEATURES) == 184,
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
    questions = list(TRAPS) + list(AVAILABILITY) + list(HOWTO) + list(INVERSIONS)
    questions += [(q, r) for q, r, _ in FALSE_DENIAL]
    questions += list(AND_QUESTIONS)
    for entry in questions:
        intent = Q.match(entry[0])
        if intent is not None:
            named.add(_row_of(intent))
    for _, row_id, _ in INVERSIONS:
        named.add(row_id)
    for _, row_id, _ in FALSE_DENIAL:
        named.add(row_id)
    for _, row_id in AND_QUESTIONS:
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
    # The direction rule, ON ITS OWN (2026-11-18): the catalogue now has TWO
    # file rows - `file-from-pc` (PC -> phone) and `document-from-phone` (phone
    # -> this PC) - so a "from my phone" question must be answered by the phone
    # door and never by the PC one, which its own id words ("file from pc")
    # score highest for. Before this, a direction-wrong winner made
    # `_cap_resolve` return None and the question went to the model.
    resolved = Q._cap_resolve("Can I send a file from my phone to my PC?")
    got = (resolved or {}).get("id")
    check("the phone door answers a from-my-phone question",
          got == "document-from-phone", got)
    check("... never the opposite-direction PC door", got != "file-from-pc", got)
    check("... and the PC door still answers its own direction",
          _row_of(Q.match(
              "Do you have a feature that sends one file from my PC to my "
              "phone? Answer in one sentence.")) == "file-from-pc")


def t_it_is_dispatched_and_arrives_without_a_card():
    res = Q.run(Q.Intent("capability_answer", {"id": "folders"}), None, NOW)
    check("run() dispatches capability_answer", res is not None
          and res.intent == "capability_answer")
    check("... with the row's words and nothing else",
          res is not None and BY_ID["folders"]["what"] in res.reply)


def t_a_question_about_a_destructive_verb_answers_and_never_starts_it():
    """DEF-106, the owner's ruling of 2026-11-27: questions answer, orders card.

    Measured before the fix, on the live PC: "can you empty the trash" lost its
    "can you" to the normaliser, arrived as the ORDER and answered "The approval
    gate refused it"; "can you delete a section of a note" arrived as a note
    delete looking for a note called "section of a". Both are QUESTIONS.

    Every assertion below states behaviour that was WRONG before the fix, so
    reverting the fix reddens this test rather than silently passing.
    """
    got = Q.match("can you empty the trash")
    check("a trash QUESTION keeps its ask flag",
          got is not None and got.name == "note_empty_trash"
          and got.f.get("ask") is True, (got.name, got.f) if got else None)
    got = Q.match("empty the vault trash")
    check("... and the ORDER still asks for its one card",
          got is not None and got.name == "note_empty_trash"
          and got.f.get("ask") is False, (got.name, got.f) if got else None)
    res, _intent = _answer("can you empty the trash")
    check("... the question is ANSWERED, not refused",
          res is not None and "refused" not in res.reply.lower(),
          res.reply[:200] if res is not None else None)

    got = Q.match("can you delete a section of a note")
    check("a section QUESTION answers from its own capability lane",
          got is not None and got.name == "note_section_delete_capability",
          got.name if got is not None else None)
    got = Q.match("delete a section of a note")
    check("... the section ORDER asks which one, instead of hunting a note "
          "called 'section of a'",
          got is not None and got.name == "note_section_delete"
          and not got.f.get("name") and not got.f.get("heading"),
          (got.name, got.f) if got else None)
    got = Q.match("delete the Warm-up section from my workout log")
    check("... while a real section order keeps its own note and heading",
          got is not None and got.name == "note_section_delete"
          and got.f.get("name") == "workout log"
          and got.f.get("heading") == "Warm-up",
          (got.name, got.f) if got else None)

    got = Q.match("can you delete my notes")
    check("the older capability questions are unchanged",
          got is not None and got.name == "note_delete_capability",
          got.name if got is not None else None)
    got = Q.match("delete my Shopping note")
    check("... and a note delete that NAMES its note is still a request",
          got is not None and got.name == "note_delete",
          got.name if got is not None else None)


def t_a_github_request_is_never_answered_with_the_feature_list():
    """Measured on the owner's own PC, 2026-11-27, in his own words.

    He asked: "can you do a pull request on the Epic Jarvis GitHub to fix this?
    i would like to be able to adjust that setting, which is voice" - and Atlas
    answered "I do not have a feature called 'you a pull request on the epic
    jarvis github to fix this? ...'". Two lanes did it: the "can you <X>"
    capability lane claimed the sentence because it contains "setting", and
    "open a pull request" resolved through jarvis_open as an app called "a pull
    request".

    A GitHub request is work to do, not a feature to describe, so neither lane
    may claim it. Every check below is the OLD behaviour written as a failure.
    """
    for sentence in (
            "can you do a pull request on the Epic Jarvis GitHub to fix this",
            "can you do a pull request on the Epic Jarvis GitHub to fix this? "
            "i would like to be able to adjust that setting, which is voice",
            "can you open a pull request for me"):
        got = Q.match(sentence)
        check(f"a GitHub request is not a feature answer: {sentence[:44]!r}",
              got is None or got.name not in ("feature_unknown", "open_app"),
              got.name if got is not None else "the model")
    # The adverb form of the off question (the same day): "what tools are
    # currently off" fell to the model while "what tools are off" was answered.
    got = Q.match("what tools are currently off")
    check("'what tools are currently off' answers from the switch list",
          got is not None
          and got.name in ("tools_switched_off", "tool_switches_on_off"),
          got.name if got is not None else "went to the model")


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


def main(argv=None):
    """Run this suite.

    `--core` runs ONLY the fast core subset, and is how ci.yml's named
    every-PR guard calls it (`backend/test_capability_answers.py --core`): the
    237 pinned cases, without the other measured lists this suite carries,
    because those already run in the required backend sweep. The full suite -
    every measured list plus the core subset - is what `run_suites.py` runs,
    and the full 5,410-question sweep inside it is gated on
    JARVIS_CAPABILITY_FULL_SWEEP=1 (see full_sweep_enabled above).
    """
    argv = sys.argv[1:] if argv is None else list(argv)
    if "--core" in argv:
        print("--- t_the_core_subset_holds (--core: the every-PR subset only) ---")
        try:
            t_the_core_subset_holds()
        except Exception:
            FAILED.append("t_the_core_subset_holds")
            traceback.print_exc()
        print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
        if FAILED:
            print("failed: " + ", ".join(FAILED))
        return 1 if FAILED else 0
    for fn in (t_the_owner_trap_sentences,
               t_the_owner_s_phone_file_question,
               t_the_phone_door_and_a_pc_only_row_are_both_said_plainly,
               t_the_three_measured_false_denial_questions,
               t_the_false_denial_leads_stay_narrow,
               t_a_feature_question_with_and_reaches_its_row,
               t_the_last_fourteen_measured_questions_reach_their_rows,
               t_the_exact_name_lane_steals_no_other_row_s_question,
               t_the_core_subset_holds,
               t_no_ordinary_shape_lost_its_row,
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
               t_a_question_about_a_destructive_verb_answers_and_never_starts_it,
               t_a_github_request_is_never_answered_with_the_feature_list,
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
