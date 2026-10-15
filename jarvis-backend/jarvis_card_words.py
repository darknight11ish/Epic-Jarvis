"""The words on an approval card, in one place: its title, its short summary,
its label, its button order, and what Jarvis SAYS about a card during a spoken
question.

    import jarvis_card_words as W
    W.title_for("switch_model")   # "Jarvis wants to switch to a different AI model"
    W.summary_for("switch_model") # "Jarvis wants to switch to a different AI model."

THE SHORT SUMMARY AND "EXPLAIN MORE" (the owner, 2026-10-09): "for approval
cards, there should be a more simple summary, with an explain more button that
expands the approval card total word length and explains the details more. and
approval card preferences such as this should be changeable in the settings."
So every action has a SHORT row here (`SUMMARY`, read by `summary_for`), the
card shows that until the owner opens it, and the whole card - the exact line
or value being changed, why it matters, what saying no does - is what the
control reveals. Both apps word it from this one place. The preference itself
lives in `jarvis_card_summary.py`, not here: this module stays pure words.

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
    "tidy_inbox": "tidy your inbox (archive, star, mark read or trash)",
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
    "run_plan": "run the safe steps of an approved plan",
    "control_browser": "work a web page for you in a browser",
    "spend_money": "spend money",
    "post_to_external_service": "post to an outside service",
    "open_public_tunnel": "open this PC to the internet",
    # --- the web
    "web_research": "search GitHub",
    "research_authenticated": "search GitHub signed in as you",
    "search_the_web": "search the web",
    # jarvis_chatbot.py: ONE card per conversation with an AI chatbot (not routed yet)
    "chatbot_session": "hold a conversation with an AI chatbot for you",
    # jarvis_chatbot_limits.py (2026-10-06): raising a monthly API limit is a
    # loosening, so it raises ONE card plus Windows Hello; lowering one,
    # removing one, correcting a price and resetting one tighten or correct, so
    # they need no card at all. Two names for one direction of travel, because
    # the owner-check attaches Windows Hello to the action, not the direction.
    "raise_api_limit": "raise a chatbot's monthly spending limit",
    "lower_api_limit": "lower a chatbot's monthly spending limit",
    # jarvis_arbiter.py (2026-10-08): the interruption budget. ONE name, for the
    # raise only - turning the budget DOWN asks nothing and needs no card, so it
    # has no action for a card to be worded for. The card says how many times a
    # day Jarvis may speak up, because that is the number the owner is agreeing
    # to, not "interruptions" in the abstract.
    "raise_attention_budget": "let Jarvis interrupt you more often",
    # jarvis_limits.py (2026-10-08): the limits and frequencies the owner can
    # change, ONE name for every one of them - the card's own words carry which
    # limit and how far. Only the RAISE is named, because turning a number DOWN
    # asks nothing and needs no card; the card itself says the limit and both
    # numbers ("How long you can undo: change it from 24 to 168...").
    "raise_a_limit": "let Jarvis do more, for longer, or more often",
    # The ONE limit whose loosening goes the OTHER way (jarvis_limits.py, the
    # owner's decision of 2026-10-08): LOWERING the voice check's bar means more
    # clips count as the owner's voice, so a lowering is the change that asks.
    # `raise_a_limit` would be a lie over that card, and this row needs its own
    # name for the same reason the chatbot limits have two ("raise_api_limit" /
    # "lower_api_limit"): the owner-check attaches Windows Hello to the action
    # NAME, not to a direction. Making the bar stricter asks nothing at all, so
    # there is no action for that direction to be worded for.
    "lower_the_voice_check_bar": "lower the bar for your voice check",
    # jarvis_support.py (2026-09-28): ONE card per support chat, and ONE per offer
    "support_chat": "chat with a company's customer support for you",
    "support_offer": "accept an offer from customer support in your name",
    # jarvis_youtube.py (2026-09-30): ONE card per YouTube link, caption text only
    "youtube_captions_read": "fetch the caption text of a YouTube video for a quiz",
    # jarvis_quiz_cloud.py (2026-09-30): ONE card per "grade this better" request
    "quiz_cloud_grade": "send a quiz to a cloud AI service to be graded better",
    "stop_asking_before_every_web_search": "stop asking before every web search",
    "web_search_enable": "turn web search back on",
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
    # --- news feeds and "tell me when this page changes" (2026-09-27)
    "news_read": "read a news feed you added",
    "page_read": "fetch a web page you're watching",
    # jarvis_readpage.py (2026-10-05): ONE card per address the owner hands
    # over, then that one page's words are read out. Its own name, not
    # "page_read" above: that one is the watch's per-look fetch.
    "read_web_page": "read a web page out loud",
    # --- GitHub watches in "tell me when" (2026-09-28)
    "github_read": "check GitHub for a \"tell me when\"",
    # --- models and graphics cards
    "browse_model_catalog": "look up AI models online",
    "download_model": "download an AI model",
    "switch_model": "switch to a different AI model",
    "rollback_model": "go back to the AI model you had before",
    "models_create": "make a tuned copy of an AI model",
    "second_card_enable": "start using the second graphics card",
    "second_card_browser_enable": "turn on browser control, which works real web pages",
    "second_card_combined_enable": "run one bigger model across both graphics cards",
    "second_card_third_assign": "move a second-card feature onto a third graphics card",
    # Which card everyday chat runs on (owner's decision, 2026-10-05): one
    # approval card to pin it, immediate to go back to leaving it to Ollama.
    "chat_card_pin": "pin everyday chat to one graphics card",
    "screen_picture_enable": "let it read pictures of your screen (slow, uses your main chip)",
    "obscura_enable": "read web pages with a browser that has no window (Obscura)",
    "browser_form_submit": "send a form you were shown on a website",
    "big_model_enable": "start the big model for background jobs",
    # --- its own settings and code
    "change_own_config": "change one of its settings",
    # One setting going ahead without asking, or (2026-09-28) Lockdown off:
    # both are this one card (jarvis_asks_first.py), so the words cover both.
    "loosen_what_asks_first": "loosen what asks first",
    "enable_reading_tool": "offer a reading tool to the AI model",
    "check_tool_updates": "check online for tool updates",
    "modify_own_code": "change its own code",
    "power_manage": "change its power mode (Active, Quiet or Standby)",
    "schedule_repeat": "set up something that repeats",
    # --- memory, learning and chat history
    "learning_enable": "turn on learning",
    "learning_auto_enable": "turn on automatic learning",
    "learning_sensitive_enable": "also learn sensitive topics automatically",
    "history_enable": "keep your chat history",
    "memory_manage": "change what it remembers",
    # jarvis_topics.py (2026-09-30): turning a private topic back on, and the
    # other loosenings of topic controls
    "topic_loosen": "turn a private topic back on, or let it learn or be used again",
    # jarvis_referee.py (2026-09-30): "This looks done - tick it?"
    "referee_tick": "tick a goal step whose number reached its target",
    # jarvis_tag_suggest.py (2026-09-30): overnight suggested tags
    "chat_tags_suggest_on": "let it read a few of your old chats at night to suggest tags",
    "chat_tag_suggest": "file one chat under a tag it suggests",
    # jarvis_forget_range.py (2026-09-28): ONE card for a whole time frame
    "memory_forget_range": "forget what it learned and delete chats from the days you chose",
    "user_profile_manage": "change your profile",
    # --- voices
    "custom_voice": "keep or use a custom voice",
    "better_voice_enable": "turn on the better custom voice",
    # --- notifications
    "watch_notifications_enable": "let your notifications show on a smartwatch too",
    "phone_notifications_read": "start reading notifications from apps you choose on your phone",
    # --- the captcha hand-off (jarvis_handoff_mode.py, the owner's decision of
    # 2026-10-08): keeping the live picture of one of the owner's own browser
    # windows on offer for the full 15 minutes instead of about a minute.
    "handoff_keep_offering": "keep the phone's live view on offer for 15 minutes",
    # --- what a captcha does about its browser window (jarvis_handoff_front.py,
    # the owner's decision of 2026-10-09): bringing that one stuck window to
    # the front instead of leaving it exactly where it is.
    "handoff_bring_to_front": "bring the stuck browser window to the front",
    # --- the owner's uncensored opt-ins, BOTH halves (jarvis_optin_models.py,
    # the owner's OWN decision of 2026-10-10, Decision 5): one clearly-labelled
    # choice for fiction and role-play, and the abliterated models already on
    # this PC offered as choices with no new download. Two separate switches,
    # both off by default, and turning either one ON is ONE card.
    "uncensored_models_enable": "offer the uncensored AI models already on this PC",
    "fiction_roleplay_enable": "turn on a separate lane for fiction and role-play",
    # --- Docker (jarvis_docker.py, the owner's request of 2026-10-09,
    # docs/DOCKER-INTEGRATION-DESIGN.md): the containers on Jarvis's OWN list,
    # and start/stop for one. The words are the module's own: `card_text()` asks
    # "Start <name> on this PC?" / "Stop <name> on this PC?", and `WORDS["detail"]`
    # says "the containers it uses on this PC". A start gives Jarvis more, so it
    # is tier "ask" and always raises ONE card; a stop gives it less and is
    # expected to be instant, but it still goes through the gate and takes tier
    # "ask" on a fresh install (unknown_action_tier), so it needs a phrase too.
    "docker_service_start": "start one of the containers it uses on this PC",
    "docker_service_stop": "stop one of the containers it uses on this PC",
    # --- backups
    "restore_backup": "restore from a backup, replacing what it knows now",
    # --- devices (jarvis_devices.py, docs/PAIRING-DESIGN.md, 2026-09-28)
    "pair_device": "connect a new device",
    "unretire_shared_key": "let the old shared key work from other devices again",
    # phase 2 (docs/PAIRING-DESIGN.md section 11). A title is built from the
    # action's name only, never the payload, so the phone's name is on the
    # card's text instead.
    "register_approval_key": "let a phone approve risky actions with its fingerprint or PIN",
    # --- the app builder (docs/APP-BUILDER-DESIGN.md)
    "app_merge_change": "add its change to one of your apps",
    # --- action receipts (2026-10-14): putting one recorded change back
    "undo_action": "put back a change it made",
    # --- helpers and anything else a tool asks for
    "agent_spawn": "start a helper task",
    "agent_kill": "stop a helper task",
    "execute_pending_actions": "run actions it has lined up",
    "unclassified_tool": "use a tool it has no plain name for",
}

#: The SHORT words on a card, keyed on the same action names as TITLES - what
#: the owner asked for on 2026-10-09: "for approval cards, there should be a
#: more simple summary, with an explain more button that expands the approval
#: card total word length and explains the details more."
#:
#: So a card shows THIS as its summary, with an "Explain more" control that
#: reveals the whole card (the notice's `full`: the exact line or value being
#: changed, "Nothing else in it changes", the Windows Hello line where it
#: applies, and "If you say no: nothing changes"). `summary_for` below is this
#: table's one reader; `approval-notice.patch` puts its words in the row both
#: apps read, and `jarvis_card_summary.py` adds the reason from the risk table,
#: so the phone and the desktop cannot word the same summary two ways.
#:
#: WHY IT IS NOT JUST THE TITLE. The title - "Jarvis wants to send an email" -
#: is already shown above the summary, and on a long card the title plus the
#: card's whole body is the wall of text the owner is complaining about. A row
#: here is the one thing being agreed to, said in a breath: the same fact as
#: the title's phrase, cut to what a person needs to recognise the action.
#: Never a code name, never a full stop, never a paragraph.
#:
#: EVERY action in TITLES has a row here: `backend/test_card_short_words.py`
#: fails when one does not, which is what keeps an action added tomorrow from
#: reaching the owner's card without short words of its own.
SUMMARY = {
    # --- email and calendar
    "send_email": "send the email shown",
    "draft_email": "save an email draft",
    "tidy_inbox": "tidy your inbox",
    "email_read": "read your email",
    "read_calendar": "read your calendar",
    "calendar_read": "read your calendar",
    "edit_calendar_event": "change a calendar event",
    "delete_calendar_event": "delete a calendar event",
    # --- files, commands, the computer and the phone
    "read_files_readonly": "read files on this PC",
    "delete_file": "delete a file",
    "run_shell_on_host": "run a command on this PC",
    "control_computer": "use your mouse and keyboard",
    "control_phone": "tap and type on your phone",
    "run_plan": "run the safe steps of a plan",
    "control_browser": "work a web page in a browser",
    "spend_money": "pay for something with your money",
    "post_to_external_service": "post to an outside service",
    "open_public_tunnel": "open this PC to the internet",
    # --- the web
    "web_research": "search GitHub",
    "research_authenticated": "search GitHub signed in as you",
    "search_the_web": "look something up online",
    "chatbot_session": "talk to an AI chatbot for you",
    "raise_api_limit": "raise a chatbot's monthly limit",
    "lower_api_limit": "lower a chatbot's monthly limit",
    "raise_attention_budget": "interrupt you more often",
    "raise_a_limit": "do more, for longer, or more often",
    "lower_the_voice_check_bar": "lower the bar for your voice check",
    "support_chat": "chat with a company's support for you",
    "support_offer": "accept a support offer in your name",
    "youtube_captions_read": "read a YouTube video's captions",
    "quiz_cloud_grade": "send a quiz to a cloud service",
    "stop_asking_before_every_web_search": "stop asking before each web search",
    "web_search_enable": "turn web search back on",
    # --- notes
    "read_joplin_note": "read a Joplin note",
    "create_joplin_note": "add a Joplin note",
    "edit_joplin_note": "change a Joplin note",
    "delete_joplin_note": "delete a Joplin note",
    "read_logseq_page": "read a Logseq page",
    "append_logseq_journal": "add to today's Logseq journal",
    "create_logseq_page": "make a Logseq page",
    "edit_logseq_page": "change a Logseq page",
    "delete_logseq_page": "delete a Logseq page",
    "append_obsidian_daily": "add to today's Obsidian note",
    "write_notes_after_outside_text": "write to your notes after outside text",
    "notes_search": "search your notes",
    "wiki_update": "write pages in the Jarvis Wiki",
    # --- the smart home
    "home_read": "check your smart home",
    "home_control": "change something in your home",
    # --- news feeds and "tell me when this page changes"
    "news_read": "read a news feed you added",
    "page_read": "fetch a page you're watching",
    "read_web_page": "read a web page out loud",
    # --- GitHub watches in "tell me when"
    "github_read": "check GitHub for a \"tell me when\"",
    # --- models and graphics cards
    "browse_model_catalog": "look up AI models online",
    "download_model": "download an AI model",
    "switch_model": "switch to a different AI model",
    "rollback_model": "go back to the model you had before",
    "models_create": "make a tuned copy of a model",
    "second_card_enable": "start using the second graphics card",
    "second_card_browser_enable": "turn on browser control",
    "second_card_combined_enable": "run one model across both graphics cards",
    "second_card_third_assign": "move a second-card feature to a third card",
    "chat_card_pin": "pin everyday chat to one graphics card",
    "screen_picture_enable": "let it read pictures of your screen",
    "obscura_enable": "read web pages with a windowless browser",
    "browser_form_submit": "send a form you were shown",
    "big_model_enable": "start the big model for background jobs",
    # --- its own settings and code
    "change_own_config": "change one of its settings",
    "loosen_what_asks_first": "stop asking first for one thing",
    "enable_reading_tool": "offer a reading tool to the model",
    "check_tool_updates": "check online for tool updates",
    "modify_own_code": "change its own code",
    "power_manage": "change its power mode",
    "schedule_repeat": "set up something that repeats",
    # --- memory, learning and chat history
    "learning_enable": "turn on learning",
    "learning_auto_enable": "turn on automatic learning",
    "learning_sensitive_enable": "learn sensitive topics automatically",
    "history_enable": "keep your chat history",
    "memory_manage": "change what it remembers",
    "topic_loosen": "turn a private topic back on",
    "referee_tick": "tick a finished goal step",
    "chat_tags_suggest_on": "read old chats at night to suggest tags",
    "chat_tag_suggest": "file one chat under a suggested tag",
    "memory_forget_range": "forget the days you chose",
    "user_profile_manage": "change your profile",
    # --- voices
    "custom_voice": "keep or use a voice you made",
    "better_voice_enable": "turn on the better custom voice",
    # --- notifications
    "watch_notifications_enable": "show notifications on your watch too",
    "phone_notifications_read": "read notifications from apps you choose",
    # --- the captcha hand-off
    "handoff_keep_offering": "keep the phone's live view for 15 minutes",
    "handoff_bring_to_front": "bring the stuck browser window to the front",
    # --- the owner's uncensored opt-ins, BOTH halves (jarvis_optin_models.py,
    # the owner's OWN decision of 2026-10-10, Decision 5). The same two actions
    # TITLES carries above, cut to a breath: the one thing each card agrees to.
    # `uncensored-optins.patch` put both rows in the gate's _RISK table, and
    # test_card_short_words.py fails when an action there has no short row here.
    "uncensored_models_enable": "offer the uncensored models on this PC",
    "fiction_roleplay_enable": "turn on the fiction and role-play lane",
    # --- Docker (jarvis_docker.py): Jarvis's OWN containers, never the owner's
    "docker_service_start": "start one of its containers",
    "docker_service_stop": "stop one of its containers",
    # --- backups
    "restore_backup": "restore from a backup",
    # --- devices
    "pair_device": "connect a new device",
    "unretire_shared_key": "let the old shared key work again",
    "register_approval_key": "let a phone approve with its fingerprint",
    # --- the app builder
    "app_merge_change": "add its change to one of your apps",
    # --- action receipts (2026-10-14): putting one recorded change back
    "undo_action": "put back the change shown",
    # --- helpers and anything else a tool asks for
    "agent_spawn": "start a helper task",
    "agent_kill": "stop a helper task",
    "execute_pending_actions": "run actions it has lined up",
    "unclassified_tool": "use a tool it has no plain name for",
}

#: The most words a summary may be. Long enough for the honest ones above
#: ("keep the phone's live view on offer for 15 minutes"), short enough that
#: the summary is a glance and the full card waits behind the control. A row
#: over this is a paragraph the owner did not ask for - and a test, not a
#: reviewer's memory, is what says so.
SUMMARY_MAX_WORDS = 9

#: The start of every title with a phrase.
LEAD = "Jarvis wants to "

#: The title when the row names no action at all.
NO_ACTION = "Jarvis is asking for your approval"

#: The title for an action with no phrase above: its name, in words, quoted
#: as a name - so it reads as English ("Jarvis wants your OK for "big model
#: enable"") rather than as a broken sentence ("Jarvis wants to big model
#: enable"). `{name}` is the action with its underscores as spaces.
FALLBACK = 'Jarvis wants your OK for "{name}"'

#: The plug-in programs' actions (jarvis_mcp.py): "mcp_start__<program>" and
#: "mcp__<program>__<tool>".
PLUGIN_START_PREFIX = "mcp_start__"
PLUGIN_USE_PREFIX = "mcp__"
PLUGIN_START = 'start the plug-in program "{name}"'
PLUGIN_USE = 'use a tool from the plug-in program "{name}"'

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
    # The plug-in programs (jarvis_mcp.py): one action per program and per
    # tool, so no fixed phrase. The PROGRAM's name is the owner's own (the
    # [mcp.servers.<name>] line); a tool's name is the program's, so it is
    # left off the title - the card itself shows it, in full.
    if action.startswith(PLUGIN_START_PREFIX):
        name = _name(action[len(PLUGIN_START_PREFIX):])
        if name:
            return LEAD + PLUGIN_START.format(name=name)
    elif action.startswith(PLUGIN_USE_PREFIX):
        name = _name(action[len(PLUGIN_USE_PREFIX):].split("__", 1)[0])
        if name:
            return LEAD + PLUGIN_USE.format(name=name)
    name = _name(action)
    return FALLBACK.format(name=name) if name else NO_ACTION


def _first_sentence(text: str) -> str:
    """`text` up to and including its first full stop, question mark or
    exclamation mark - or all of it when it has none.

    THE RULE THIS KEEPS: a summary is never cut mid-word. A card's text is
    full of things that cannot survive a truncation - a command, a recipient,
    a file path - so where there is no written short phrase the sentence is
    taken whole, and the rest stays behind the "Explain more" control.
    """
    flat = " ".join(str(text or "").split())
    for i, ch in enumerate(flat):
        if ch in ".!?":
            return flat[:i + 1].strip()
    return flat.strip()


def _short_enough(words: str) -> bool:
    """Whether `words` may stand as a card's summary: a glance, not a
    paragraph. The word count is the rule; the title's own phrases for a few
    long actions ("tidy your inbox (archive, star, mark read or trash)") are
    longer than this on purpose, and fall through to the card's first sentence
    instead."""
    return len(str(words or "").split()) <= SUMMARY_MAX_WORDS


def summary_for(action, full: str = "") -> str:
    """The SHORT words on a card for the gate action `action` - the summary the
    owner reads before deciding whether to open the whole card.

    Reads the action NAME and this module's own tables. `full` is read only as
    a fallback, so this stays as safe to compute for a lock-screen notice as
    `title_for` is.

    In order, the three things it will answer with (the owner's rule, task
    "cards read short", 2026-10-09):

      1. SUMMARY[action] - the written short phrase ("Jarvis wants to send the
         email shown."), the same fact as the title's, cut to a glance.
      2. The first WHOLE sentence of the card's own full text, when the action
         has no row AND the title's phrase is too long to be a summary - a
         plugin program's card, or an action added on the owner's PC that this
         repository has never seen. Whole: never cut mid-word.
      3. The title itself, when there is nothing else - and `title_for` already
         guarantees that is readable words rather than the raw action id.

    The "why this matters" - the risk table's own reason, and the raised
    warning, and "nothing has happened yet" - is the whole card, not the
    summary: it is what the "Explain more" control opens.

    NEVER empty, NEVER a truncated word, and never the raw action id: the
    owner's own words were "a card he cannot read at a glance is the problem".
    `backend/test_card_short_words.py` pins all three, and fails when an action
    the gate knows has no row above.
    """
    action = str(action or "").strip()
    phrase = SUMMARY.get(action)
    if not phrase:
        # The plugin programs (jarvis_mcp.py): one action per program and per
        # tool, so no fixed row. The program's own name is on the title.
        if action.startswith(PLUGIN_START_PREFIX):
            phrase = "start a plug-in program on this PC"
        elif action.startswith(PLUGIN_USE_PREFIX):
            phrase = "use one of its plug-in programs"
        phrase = phrase or str(TITLES.get(action) or "")
    if phrase and _short_enough(phrase):
        return LEAD + phrase + "."
    # No short words of its own: the card's own first sentence, whole.
    line = _first_sentence(full) or title_for(action)
    return line if line.endswith((".", "!", "?")) else line + "."


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
