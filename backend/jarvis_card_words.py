"""The words on an approval card, in one place: its title, its label, its
button order, and what Jarvis SAYS about a card during a spoken question.

    import jarvis_card_words as W
    W.title_for("switch_model")   # "Jarvis wants to switch to a different AI model"

WHY A TABLE. The notice's title (approval-notice.patch, `notice_for`) used
to be the gate's action name with its underscores taken out: "Jarvis wants
to switch model", "Jarvis wants to learning enable", "Jarvis wants to models
create". The Jarvis bar and the widget showed the bare code name
(`switch_model`), the widget under "APPROVAL REQUIRED". The creativity audit
(docs/creativity-2026-09-25/experience.md, finding 1) found the one screen
that matters most speaking three dialects. So every action the gate can ask
about has a plain phrase here, written by us, and `notice_for` reads it. The
phone and the PC both show `notice.title`, so both show these words.

SAFE ON A LOCK SCREEN, AS BEFORE. `title_for` reads the action NAME and
nothing else - never `detail`, `prompt` or `raised`. Every word it returns is
in this file. An action with no phrase here still gets a readable title
(`FALLBACK`), built from its name; backend/test_card_words.py fails when an
action the gate knows has no phrase, so the fallback is for an action added
on the owner's PC that this repository has never seen.

WHAT THE APPS SHOW, IN ONE ORDER (docs/ARCHITECTURE.md §3, "One card on
every screen"): the label (`KICKER`), the title, then the rest of the card,
with Deny on the left and Approve on the right (`BUTTONS`) - in the Jarvis
bar, the widget, the HUD page and the phone's card alike.

VOICE. When a spoken question ends up waiting on a card, Jarvis says so
(`VOICE["waiting"]`), and once the card is answered or runs out of time it
says what happened (`VOICE[<outcome>]`, the gate's own outcome words:
approved, denied, timed_out). Fixed sentences, never the model's words and
never anything from the card, so they are safe to say aloud in any room.
There is no approving by voice and there never will be: the voice check
cannot tell a recording from the owner (CLAUDE.md), so a "yes" said aloud
answers nothing. These lines only say where the card is.

tools/gen_card_words_cases.py writes all of this into one file both apps'
tests read, so the two cannot drift apart.

Standard library only. No I/O.
"""
from __future__ import annotations

import re

#: What Jarvis wants to do, finishing the sentence "Jarvis wants to ...".
#: Keyed on the gate's action names: jarvis_gate._RISK, [autonomy.tiers] in
#: jarvis-framework.toml, and the actions the shipped modules ask under.
#: Plain words for someone who does not know the code. Lower case, no full
#: stop - it is the end of a sentence that starts elsewhere.
TITLES = {
    # --- email and calendar
    "send_email": "send an email",
    "draft_email": "write an email draft",
    "email_read": "read your email",
    "read_calendar": "read your calendar",
    "calendar_read": "read your calendar",
    "edit_calendar_event": "change an event in your calendar",
    "delete_calendar_event": "delete an event from your calendar",
    # --- files, commands, the computer and the phone
    "read_files_readonly": "read files on this PC",
    "delete_file": "delete a file",
    "run_shell_on_host": "run a command on this PC",
    "control_computer": "use the mouse and keyboard on this PC",
    "control_phone": "tap and type on your phone",
    "control_browser": "work a web page for you in a browser",
    "spend_money": "spend money",
    "post_to_external_service": "post to an outside service",
    "open_public_tunnel": "open this PC to the internet",
    # --- the web
    "web_research": "search GitHub",
    "research_authenticated": "search GitHub signed in as you",
    "search_the_web": "search the web",
    "stop_asking_before_every_web_search": "stop asking before every web search",
    # --- notes
    "read_joplin_note": "read a note in Joplin",
    "create_joplin_note": "add a note in Joplin",
    "edit_joplin_note": "change a note in Joplin",
    "delete_joplin_note": "delete a note in Joplin",
    "read_logseq_page": "read a page in Logseq",
    "append_logseq_journal": "add to today's Logseq journal",
    "create_logseq_page": "make a new page in Logseq",
    "edit_logseq_page": "change a page in Logseq",
    "delete_logseq_page": "delete a page in Logseq",
    "append_obsidian_daily": "add to today's Obsidian daily note",
    "write_notes_after_outside_text": "write to your notes after reading outside text",
    "notes_search": "search your notes",
    "wiki_update": "write pages in the Jarvis Wiki",
    # --- the smart home
    "home_read": "check your smart home",
    "home_control": "change something in your home",
    # --- models and graphics cards
    "browse_model_catalog": "look up AI models online",
    "download_model": "download an AI model",
    "switch_model": "switch to a different AI model",
    "rollback_model": "go back to the AI model you had before",
    "models_create": "make a tuned copy of an AI model",
    "second_card_enable": "start using the second graphics card",
    "second_card_browser_enable": "turn on browser control, which works real web pages",
    "big_model_enable": "start the big model for background jobs",
    # --- its own settings and code
    "change_own_config": "change one of its settings",
    "loosen_what_asks_first": "let one action go ahead without asking you first",
    "modify_own_code": "change its own code",
    "power_manage": "change its power mode (Active, Quiet or Standby)",
    "schedule_repeat": "set up something that repeats",
    # --- memory, learning and chat history
    "learning_enable": "turn on learning",
    "learning_auto_enable": "turn on automatic learning",
    "learning_sensitive_enable": "also learn sensitive topics automatically",
    "history_enable": "keep your chat history",
    "memory_manage": "change what it remembers",
    "user_profile_manage": "change your profile",
    # --- voices
    "custom_voice": "keep or use a custom voice",
    "better_voice_enable": "turn on the better custom voice",
    # --- helpers and anything else a tool asks for
    "agent_spawn": "start a helper task",
    "agent_kill": "stop a helper task",
    "execute_pending_actions": "run actions it has lined up",
    "unclassified_tool": "use a tool it has no plain name for",
}

#: The start of every title with a phrase.
LEAD = "Jarvis wants to "

#: The title when the row names no action at all.
NO_ACTION = "Jarvis is asking for your approval"

#: The title for an action with no phrase above: its name, in words, quoted
#: as a name - so it reads as English ("Jarvis wants your OK for "big model
#: enable"") rather than as a broken sentence ("Jarvis wants to big model
#: enable"). `{name}` is the action with its underscores as spaces.
FALLBACK = 'Jarvis wants your OK for "{name}"'

#: The small label above the title, on every screen.
KICKER = "Needs your OK"

#: The two buttons, left to right, on every screen: Deny on the left,
#: Approve on the right. Why this order (docs/ARCHITECTURE.md §3): Android's
#: own dialogs put the confirming button on the right; the phone's card
#: already approves with a swipe to the RIGHT and denies with one to the
#: left, so the buttons now sit where the gesture goes; the Jarvis bar, the
#: desktop's main card, already had this order; and the first button a
#: keyboard's Tab reaches is the safe one.
BUTTONS = ("Deny", "Approve")

#: What Jarvis says aloud during a SPOKEN question that waits on a card
#: (`waiting`), and afterwards (the gate's outcome: approved, denied,
#: timed_out). The last three are said only after `waiting` was.
VOICE = {
    "waiting": "I need your OK for that. There's a card on your screen.",
    "approved": "Approved. Carrying on.",
    "denied": "OK, I won't do that.",
    "timed_out": "That card timed out, so nothing was done.",
}

#: How a spoken or typed command that raises a card ends its answer
#: (jarvis_quick.py). A "yes" said aloud approves nothing - only the card
#: does - so the sentence names the card.
UNTIL_APPROVED = "Nothing is set up until you approve the card."

_MAX_NAME = 60


def _name(action: str) -> str:
    """The action name as words: underscores to spaces, one space at most,
    nothing but letters, digits and spaces, and not too long to read."""
    words = re.sub(r"[^A-Za-z0-9 ]+", " ", action.replace("_", " "))
    words = " ".join(words.split())
    return words[:_MAX_NAME].strip()


def title_for(action) -> str:
    """The card's title for the gate action `action`. Reads the name only."""
    action = str(action or "").strip()
    if not action:
        return NO_ACTION
    phrase = TITLES.get(action)
    if phrase:
        return LEAD + phrase
    name = _name(action)
    return FALLBACK.format(name=name) if name else NO_ACTION


def voice_lines(words) -> list:
    """What a spoken question says as the chat stream's status words arrive,
    in order - the reference both apps follow (desktop card-words.js
    `createCardVoice`, phone voice/CardVoice.kt). "approval" says the waiting
    line once per card; an outcome word says what happened, and only after
    the waiting line was said; every other word says nothing."""
    out, waiting = [], False
    for word in words:
        if word == "approval":
            if not waiting:
                waiting = True
                out.append(VOICE["waiting"])
        elif word in ("approved", "denied", "timed_out"):
            if waiting:
                waiting = False
                out.append(VOICE[word])
    return out
