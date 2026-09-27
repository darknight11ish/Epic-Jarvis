"""jarvis_sayable.py - "Things you can say": a short, fixed list of real
sentences Jarvis already answers WITHOUT the AI model, served from one place
so the empty Jarvis bar / Home screen, the walkthrough, Help, and the "what
can you do?" command in both apps show exactly the same words - the same
"one source, both apps read it" pattern jarvis_manner.view() and
jarvis_wellbeing.view() use.

NEW MODULE, shipped whole. sayable.patch adds GET /api/sayable to
jarvis_hud.py (read-only, no settings, so no approval card either way).
jarvis_quick.py's _match() answers "what can you do?" (and close phrasings)
from sentence() below, with no model. docs/JARVIS-API.md section 41,
backend/README.md "Things you can say".

THE OWNER'S DECISION: already approved as feasibility idea I116, "Now"
(docs/FEASIBILITY-AUDIT-2026-09-26.md:268: "Served by the PC; fills the box,
never sends"). Picked up by the ease-of-use audit's own "do first" table, row
4 (docs/EASE-OF-USE-AUDIT-2026-09-27.md): "about 5-8 real sentences Jarvis
already understands without the AI model ... They replace the 10 shortcut
rows in the empty Jarvis bar, with one line 'More: right-click the Jarvis
icon by the clock.' Also one 'what can you do?' command answered from the
same list, 3 examples on walkthrough screen 2, and a Help answer in both
apps. Tapping a line fills the box and never sends." The audit's own critic
(docs/ease-audit-2026-09-27/critic.md section 3.3) scoped the fuller original
design (docs/CUTTING-EDGE-2026-09-26-round2-experience.md section 3: a
searchable, grouped "/" command palette) down to "one list, in fewer places":
this flat list, the footer line, Help, and the "what can you do?" intent -
dropping the extra onboarding screen and the grouped headings.

EVERY SENTENCE BELOW IS REAL, CHECKED AGAINST jarvis_quick.py's OWN GRAMMAR
(test_sayable.py calls jarvis_quick.match() on the exact text of every one,
byte for byte as it is served, and fails if any comes back None - a sentence
that stopped matching, or was never wired up, cannot silently stay on this
list):
  * "Set a timer for 10 minutes." -> timer_set
  * "What did I miss?" -> missed (jarvis_briefing.build_missed)
  * "Tell me when an email from Alex arrives." -> tellme_email (jarvis_tellme.py)
  * "Focus for 30 minutes." -> focus_start (jarvis_focus.py)
  * "Remind me to call Mom at 6pm." -> reminder_set
  * "Add milk to the shopping list." -> todo_add (a named list, 2026-09-25)
  * "Brief me now." -> briefing_now (jarvis_briefing.py)
Chosen to show the spread the audit's own examples pointed at (timers,
"what did I miss?", "tell me when ...", focus) plus three more real ones
(a plain reminder, a named list, and the briefing) - not a grab-bag of every
fast-path sentence jarvis_quick.py answers, most of which need a timer
already running, a list already started, or other state a first-time reader
does not have yet.

WHAT IT IS NOT
Not a searchable command palette, not grouped, and not a 4th onboarding
screen - the critic's own reasons for dropping those are above. Tapping a
line only fills the box; it is never sent by the list itself (CLAUDE.md: the
owner's own words, then, count as `typed`, and a command that raises a card
still raises it - nothing here loosens anything, so no approval card either
way, like jarvis_manner.py and jarvis_reach.py).
"""
from __future__ import annotations

#: The words both apps show above the list.
TITLE = "Things you can say"
DETAIL = ("Real sentences Jarvis already answers without the AI model. Tap one to put it in "
          "the box - it does not send.")

#: The line replacing the bar's 10 shortcut-key rows (the exact words the
#: ease-of-use audit's do-first table row 4 gives; see the module docstring).
#: Points at Settings -> Shortcuts, where the rebindable hotkeys already live.
FOOTER = "More: right-click the Jarvis icon by the clock."

#: The list itself - see the module docstring for what each one does and how
#: it was checked. Order matters: it is the order both apps show, and the
#: order the walkthrough and Help quote from (WALKTHROUGH, HELP below).
SENTENCES = (
    "Set a timer for 10 minutes.",
    "What did I miss?",
    "Tell me when an email from Alex arrives.",
    "Focus for 30 minutes.",
    "Remind me to call Mom at 6pm.",
    "Add milk to the shopping list.",
    "Brief me now.",
)

#: Three of the list, for the walkthrough's screen 2 (never screen 1 or 3;
#: the ease-of-use audit's do-first table row 4 and its critic section 3.3
#: are specific about that). The first three read best out of order context -
#: a timer, catching up, and a reminder - so they are not just SENTENCES[:3].
WALKTHROUGH_EXAMPLES = (
    "Set a timer for 10 minutes.",
    "What did I miss?",
    "Remind me to call Mom at 6pm.",
)
assert set(WALKTHROUGH_EXAMPLES) <= set(SENTENCES)
assert len(WALKTHROUGH_EXAMPLES) == 3

#: The Help/FAQ answer (both apps show this same paragraph).
HELP_TITLE = "What can I say?"
HELP_BODY = ("Jarvis answers some sentences straight away, without the AI model - so they work "
             "even when the model is slow, unloaded or asleep. A few real ones: "
             + " ".join(SENTENCES) + " Type \"what can you do?\" any time to see this list again. "
             "Anything else goes to the AI model as before.")

#: Spoken/typed answer for "what can you do?" (jarvis_quick.py, no model).
_INTRO = "Some things you can say without waiting on the model: "


def sentence() -> str:
    """The one-paragraph answer for "what can you do?" - the same facts as
    view(), worded as a sentence. Never raises."""
    return _INTRO + " ".join(SENTENCES) + " " + FOOTER


def view() -> dict:
    """GET /api/sayable. Never raises: this is fixed text, not a setting."""
    return {
        "available": True,
        "title": TITLE,
        "detail": DETAIL,
        "sentences": list(SENTENCES),
        "footer": FOOTER,
        "walkthrough_examples": list(WALKTHROUGH_EXAMPLES),
        "help_title": HELP_TITLE,
        "help_body": HELP_BODY,
        "written_by": "code",
    }


def handle_get() -> tuple:
    return 200, view()
