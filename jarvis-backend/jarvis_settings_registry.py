"""jarvis_settings_registry.py - "open" and "adjust" any setting, by voice or
chat, on either app.

NEW MODULE, shipped whole (no patch of its own). jarvis_quick.py (already
SHIPPED) is the only importer: its grammar matches "open web search" or
"turn on background learning" and calls straight into this file, which
calls straight into the EXACT function the matching UI toggle already
calls - the same route, the same tier check, the same approval card, the
same jarvis_owner_check.PC_ONLY_ACTIONS refusal. This file adds NO new way
to change a setting; it only gives the existing ways a second door, from
plain English. docs/JARVIS-API.md section 58.

THE OWNER'S SCOPE (their own words, confirmed 2026-09-27)
1. "Open" a settings screen/section is pure navigation - Jarvis jumps the
   app to that screen; the owner still makes the change by hand if they
   want to. Safe by construction: SECTIONS below is read-only data, and
   opening one runs no code that could change anything.
2. "Adjust" a setting means calling the EXACT SAME function the UI toggle
   already calls - never a new, parallel mutation path. ADJUSTABLE below
   holds, for each covered setting, a reference to that existing function
   (imported lazily, so a backend missing one module just answers "not
   there yet" for that one setting rather than failing to import at all).
   A setting already gated by an approval card still raises one; a setting
   on jarvis_owner_check.PC_ONLY_ACTIONS still needs Windows Hello and still
   refuses from the phone - `peer`/`local` (the request's own address, read
   the same way owner-check.patch's do_POST wrapper reads them) are passed
   all the way down to the real gate (jarvis_asks_first.request_tier's and
   request_tool_enable's own `_here(here, peer, local)`), never invented
   and never given a laxer or stricter meaning than that function already
   has.

WHAT IS COVERED, AND WHAT IS NOT (said plainly - CLAUDE.md, "do not claim
more than the evidence supports")

SECTIONS covers every top-level settings.html card id (desktop) that also
has a home on the phone (Settings screen items share the SAME ids since the
2026-09-27 Settings-screen build - SettingsScreen.kt's own `item(key = ...)`
calls) - so ids read straight from both files, not guessed. A phone-only or
desktop-only place is marked in its `app` field, for `sections_for()` and
this file's own tests - but the ANSWER this file gives is the same
sentence on both apps ("Opening <name> in Settings."), because the backend
does not know which app is asking (`/api/chat`'s body carries no client
kind). Saying "open backups" on the phone opens its one Settings screen
AND scrolls to the real backup row it has there - Voice, Security,
Appearance and Backups are ordinary `item(key = ...)` rows on the phone,
same as on the desktop. Where a section is NOT a Settings row on the phone,
the phone decides for itself (jarvis-client's ui/OpenPlace.kt, 2026-09-27):
Help, Checks, Brain or "Jarvis's voice" for the ones it has elsewhere -
including hardware, second-card, big-model and backend-supports, marked
"desktop" here but shown on the phone's Brain - and a plain "only on your
PC" line for the ones it has nowhere. Its OpenPlaceTest reads SECTIONS
from this file, so a new section needs a phone decision too. Said plainly here rather than
claimed as a feature: a per-app wording would need the backend to read
`X-Jarvis-Client` for this, which it does not do today.

ADJUSTABLE covers a dozen settings behind a SINGLE existing boolean or
choice function, picked because each already has a proven `handle_*`/
`request_*` entry point this file can call exactly as the REST route does:
  * web_search_provider  - jarvis_search.use()            (already a quick
                            path: jarvis_quick._web_search/_run_search; kept
                            registered here for "open web search" and so
                            this file's tests can check it end to end)
  * manner                - jarvis_manner.handle_set()      (already a quick
                            path: "from now on ..."; registered the same way)
  * background_learning   - jarvis_auto_learn.handle_post()
  * learn_sensitive_topics- jarvis_auto_learn.handle_post()
  * lights_without_card   - jarvis_asks_first.handle_lights()
  * ask_before_every_search - jarvis_search.request_ask_every_time()
  * web_search            - jarvis_search.request_enabled() (2026-09-30): OFF at once,
                            ON is one card (web_search_enable)
  * smartwatch_notifications - jarvis_watch_notify.request()
  * phone_notifications   - jarvis_phone_notifications.request() (2026-09-28)
  * screen_picture        - jarvis_screen_picture.request() (2026-09-29): ON is one card
  * headless_browser      - jarvis_browser_engine.request() (2026-09-29): ON is one card
  * topic mode            - jarvis_topics.set_mode() (2026-09-30): the four-choice
                            picker's own function. Stricter is at once; looser on a
                            private topic raises its ONE card (topic_loosen). "Switch
                            off my work topic" is ambiguous, so jarvis_quick opens the
                            picker instead of guessing (find_topic / set_topic_mode).
  * briefing_senders      - jarvis_briefing.handle_senders()
  * loosen_asks_first     - jarvis_asks_first.handle_tier()   (PC_ONLY_ACTIONS)
  * enable_reading_tool   - jarvis_asks_first.handle_tools()  (PC_ONLY_ACTIONS)

ANIMAL OPTIONS (2026-09-28, the owner's "Jarvis can change any of them when
asked") are adjustable too, each through the exact function its switch
already calls - see "Animal options" at the end of this file:
  * the shared switches ("Keep the animal still", listening nods, focus
    buddy, small acknowledgements, petting, seasonal touches)
                          - jarvis_animal.set_switch()   (at once, no card)
  * the sun and moon      - jarvis_sky.handle_post({"show": ...})
  * the weather source    - jarvis_sky.handle_post({"weather": ...}): off
                            and Home Assistant at once; Open-Meteo raises
                            its ONE approval card, never skipped
  * sharpness and frame rate are per device, so the PC changes nothing:
    jarvis_quick.py names the change in X-Jarvis-Route (`face_tuning`) and
    the app that asked changes itself (jarvis_animal.step_device).

UNIVERSAL CONTROLS (2026-10-22, the owner's requirement: "make sure i can
turn off or adjust any function or feature or turn it on by typing it into
jarvis on either the desktop or android phone"). The tables above grew with
every switch and named choice whose control ALREADY existed but had no
spoken name - each setter calls the same function its control/route calls, so
its card, tier, stale-link and PC-only rules are unchanged:
  * the switches: chat history, "Write like me", the big model and its wiki /
    deep-question jobs, the second card's combined mode and its two
    bigger-model suggestion switches (BOOL_SETTINGS at the end);
  * the named choices (CHOICE_SETTINGS, "set <name> to <value>"): how long
    chats are kept (0/30/90/365 days), the captcha hand-off (stop early or
    keep offering), whether that window is brought to the front, voice speed,
    the built-in voice the pack really offers, and the focus presets (its
    apply still raises the one switch_model card it always did);
  * the sandbox and media-index switches now name their real Settings cards,
    so "is the sandbox on?" maps to the switch the page draws.

Multi-field boards that need a FILE PICKER, several values at once, or a
SECRET are still open-only, and each is named with its reason in
`jarvis_feature_guide.NO_COMMAND_REASON` (never a silent omission). An
ambiguous value is refused with the real options, never guessed.

Left OUT of "adjust", on purpose, said plainly rather than guessed at:
  * Accounts/API keys and the pairing token - a secret the owner should
    never be asked to say aloud (rule 3), Settings-only by owner decision
    (2026-10-22);
  * Restore backup - replaces memory, chat history, settings and notes with
    an older save; Settings-only by owner decision (2026-10-22) because a
    beginner owner saying the wrong thing by voice should not be one
    sentence away from it;
  * multi-field panels whose control needs a file/folder picked on the PC or
    several values at once (folders, spending layouts, backup folder, custom
    voice enrolment, per-face voice choices, hardware/model lane assignment,
    the appearance theme the desktop's own store owns): "open" reaches them,
    and their NO_COMMAND_REASON row says why a typed value cannot reach the
    same setter safely yet.
All of these are still "open"-only: SECTIONS jumps the app there.
  * `restore_backup` - also PC_ONLY_ACTIONS and already wired
    (jarvis_backup.py), but deliberately not offered as a spoken "adjust":
    it replaces memory, chat history, settings and notes with an older
    save, and a beginner owner saying the wrong thing by voice should not
    be one sentence away from that. Reachable only from Settings, by hand.
  * Everything jarvis_quick.py already answers through its OWN grammar
    with no need for a registry (timers, reminders, focus, media, "tell me
    when", the to-do list, ...) stays exactly as it is; this file is not a
    second version of any of that.

WRITTEN AGAINST test_settings_registry.py, which is the source of truth for
exact wording and exact refusal shapes - read it before changing either.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

#: A leading "the"/"my"/"a"/"an" is not part of a section's or a target's
#: name for matching purposes - jarvis_quick.py's own verb patterns
#: sometimes strip one before calling in here, sometimes do not.
_LEAD_ARTICLE = re.compile(r"^(?:the|my|a|an)\s+")


def _bare(words: str) -> str:
    return _LEAD_ARTICLE.sub("", " ".join(str(words or "").split()))


def _choice_key(words: str) -> str:
    """A spoken value's identity: letters and digits only, lower case.

    Both a row's own labels/ids and the tail of a typed sentence go through
    this, so "American (female) - Heart", "american female heart" and
    "the American female Heart" are one choice. Punctuation is never part of
    a value - a person says the words, not the hyphens."""
    cleaned = " ".join(re.sub(r"[^a-z0-9]+", " ", str(words or "").lower()).split())
    return _LEAD_ARTICLE.sub("", cleaned)

# --------------------------------------------------------------------------
#   "Open": every settings screen/section this file knows how to name -
#   read-only data, no import, no side effect.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Section:
    id: str                    # settings.html's id, and SettingsScreen.kt's item key
    names: tuple                # plain-English things the owner might call it
    app: str = "both"           # "both" | "desktop" | "phone"
    where: str = "settings"     # "settings" (Settings) or "brain" (the Brain/Mind)


#: Desktop: jarvis-desktop/src/settings.html's own `<section class="card"
#: id="...">` ids (and its jump list's own grouping/labels). Phone: the ids
#: SettingsScreen.kt's LazyColumn already uses as `item(key = "...")`, or,
#: for a phone screen reached a different way (Brain, "Platform checks"),
#: the id it is reached BY on this list, kept the same as the desktop's
#: nearest equivalent so one spoken phrase works on both apps.
SECTIONS: tuple = (
    # "Set up Jarvis" (2026-10-06): the first-run card at the top of the
    # desktop Settings screen, holding the five choices that matter on a
    # first run. Desktop only - the phone has no such page, so OpenPlace.kt
    # lists it PC-only and the phone answers "only on your PC".
    Section("first-run", ("set up jarvis", "first run setup", "the setup page",
                          "getting started with jarvis"), app="desktop"),
    # "First-time setup" (S2, 2026-10-20; JARVIS-API section 147): the fourteen
    # questions in one card. BOTH apps - the desktop card is settings.html's
    # id="setup-questionnaire", and the phone has its own READ-ONLY row with the
    # same item key (SettingsScreen.kt). Opening it is pure navigation on either
    # app; applying is the PC's step, where every loosening change raises its
    # own existing approval card (docs/ARCHITECTURE.md section 8).
    Section("setup-questionnaire", ("first time setup", "the setup questionnaire",
                                    "the setup questions", "how jarvis behaves"),
            app="both"),
    Section("connection", ("connection", "the connection settings", "where jarvis is running")),
    # Paired devices (docs/PAIRING-DESIGN.md section 7.2): a card on both apps
    # (settings.html id="devices"; the phone's item(key = "devices")).
    Section("devices", ("devices", "paired devices", "my devices", "my paired devices")),
    # "the faq" / "frequently asked questions" / "help" were here until
    # 2026-10-08, naming the Settings card "Help and FAQ" (settings.html
    # id="faq"). That card was a SECOND way in to the same help the Brain
    # answers, and the owner folded it into one place: the desktop questions
    # moved to the Brain's "Tutorials and the FAQ" (jarvis-desktop/src/
    # desktop-help.js) and the card is gone, so there is no `faq` section left
    # for "open the faq" to name. The questions BOTH apps answer were never
    # this card - the backend serves those at GET /api/faq, exactly as before.
    Section("appearance-card", ("appearance", "the theme", "how jarvis looks", "the face")),
    # "Approval cards" (the owner's request of 2026-10-09): how much of an
    # approval card is shown at first - "Start short" with an "Explain more"
    # control, or "Always show everything".
    #
    # PHONE ONLY, and that is not an oversight. The section's app must match
    # where the row really is, or "open approval cards" names a place the app
    # does not have: this repository's own jarvis-desktop/ and src-tauri/ are
    # the other conversation's surface. So the phone's Settings row
    # (SettingsScreen.kt, item(key = "approval-cards")) is what this names
    # today, and the setting itself is the PC's (GET/POST /api/card-prefs,
    # card-prefs.patch) so the desktop's own switch reads the same value.
    # `backend/test_settings_registry.py` is what caught the first version of
    # this row claiming "both": it refused to let a section say the desktop has
    # a settings.html card (id="approval-cards") which is not on that page.
    # WHEN THE DESKTOP'S CARD LANDS (docs/DESKTOP-APPROVAL-CARD-PREF.md says
    # which file, which control and which field), this becomes
    # `app="both"` - one word - and the row in jarvis_menus.py becomes
    # (DESKTOP, PHONE) with it.
    Section("approval-cards", ("approval cards", "the approval cards",
                               "how much of a card is shown", "explain more",
                               "the explain more button", "cards read short",
                               "the short summary"), app="phone"),
    # "Animal options" (2026-09-28): every animal-face option in one place.
    # Desktop: its own card in settings.html. Phone: inside Appearance, so
    # the phone's Settings scrolls to its Appearance row (SettingsScreen.kt
    # SETTINGS_ITEM_INDEX), whose button opens it.
    Section("animal-options", ("animal options", "the animal's options", "animal settings",
                               "the animal's settings", "the animal settings")),
    Section("voice", ("voice", "voice settings", "my voice", "how jarvis listens")),
    Section("manner", ("how jarvis talks", "manner", "warm and brief", "plain mode")),
    # "A new conversation starts after" (the audit of 2026-10-08): how long a
    # conversation can sit idle before the next message starts a new one - the
    # one timing the owner could not change anywhere. It is a CLIENT-SIDE
    # choice: the PC serves no route for it (`jarvis_limits.py` says so in its
    # own words), so this is "open"-only. Opening it jumps the app to its own
    # Settings row, where the five choices are made by hand; there is no spoken
    # "adjust", on purpose - there is no existing function to call, and a
    # spoken change would have to be a new, parallel mutation path.
    Section("idle-new", ("a new conversation starts after", "when a new conversation starts",
                         "new conversation timing", "how long a chat stays open",
                         "how long before a new chat", "the quiet minutes",
                         "the idle timeout")),
    Section("briefing-settings", ("the morning briefing", "briefing settings")),
    Section("shortcuts", ("shortcuts", "keyboard shortcuts", "hotkeys"), app="desktop"),
    Section("security", ("security", "app lock", "windows hello")),
    Section("voices", ("jarvis's voice", "jarvis's voices", "custom voices",
                       "how jarvis sounds")),
    Section("web-search", ("web search", "search settings", "the search provider")),
    Section("account-secrets", ("accounts", "account secrets", "credentials"), app="desktop"),
    # "Chatbot API keys" (docs/ACCOUNT-KEYS-DESIGN.md steps 1-2, 2026-10-06):
    # the six API services the chatbot driver can use, each key typed on the
    # PC and written straight into Windows Credential Manager. Desktop only -
    # the phone is never asked for an account secret.
    Section("chatbot-api-keys", ("chatbot api keys", "the api keys",
                                 "chatbot keys", "my api keys"), app="desktop"),
    # "Hardware and models" (corrected 2026-10-10, the parity audit): this said
    # "desktop" while `backend/jarvis_menus.py` said both and the phone drew
    # the plate - the disagreement §6.3 of the audit found. The phone HAS this
    # section: BrainScreen.kt `item(key = "hardware")`, menu
    # `settings.hardware`, drawn by HardwarePlate.kt. What is desktop-only is
    # the memory bars, the "Details" arithmetic, Copy and the Modelfile, which
    # ARCHITECTURE section 8 keeps off the phone - a limit of the section, not
    # of its existence.
    Section("hardware", ("hardware and models", "hardware", "graphics cards"), app="both"),
    # "Focus presets" (the owner's preset selector, 2026-10-18): the card
    # settings.html carries above "Hardware and models", showing the five
    # presets the PC sends. DESKTOP ONLY for now - the phone's equivalent
    # selector is not on this tree, and OpenPlace.kt must not claim it. When
    # the phone lands its selector this becomes `app="both"` in the same
    # one-word way the approval-cards row above says.
    Section("focus-presets", ("focus presets", "the focus presets", "presets",
                              "the preset selector", "choose a focus preset",
                              "what are you about to work on"), app="desktop"),
    # "Your second graphics card" (corrected 2026-10-10, the parity audit): the
    # phone has SecondCardPlate.kt - all four rows, `MenuPlaces.INSIDE` - under
    # the same menu id `settings.second-card`, which `jarvis_menus.py` already
    # marks both. The phone cannot create the second card's own copy of Ollama
    # or measure the card, and arch/ARCHITECTURE section 8 says so; the section
    # itself is on both apps.
    Section("second-card", ("the second graphics card", "second card", "second gpu"),
            app="both"),
    # "Big model (slow)" (corrected 2026-10-10, the parity audit): the phone has
    # BigModelPlate.kt, menu `settings.big-model`, marked both in
    # `jarvis_menus.py`. The phone can switch it on and off like the desktop;
    # `colibri` itself runs on the PC.
    Section("big-model", ("the big model", "big model settings"), app="both"),
    Section("folders", ("folders jarvis may look in", "folders", "the notion export")),
    Section("backup", ("backups", "backup settings")),
    # "Updates" (corrected 2026-10-10, the parity audit): the phone HAS its own
    # update card - net/UpdateCheck.kt, platform/UpdateChecker.kt and the
    # "Check for new versions" row on Platform checks (ReadinessScreen.kt, item
    # "this-app"), which is where OpenPlace.kt sends "open updates". Each app
    # checks its own release page. `jarvis_menus.py`'s `settings.updates` is
    # both for the same reason. `tool-updates` below really is the PC's.
    Section("updates", ("updates", "app updates"), app="both"),
    Section("tool-updates", ("tool updates", "check for tool updates"), app="desktop"),
    Section("more-options", ("more options", "startup and logs"), app="desktop"),
    Section("start-jarvis", ("starting jarvis for you", "start jarvis automatically"),
            app="desktop"),
    Section("asks-first", ("what asks first", "asks first settings")),
    Section("prompt-coach", ("prompt coach settings", "the prompt coach page")),
    Section("reach", ("what jarvis can reach", "what jarvis can access")),
    # "Data and maths sandbox" (LM-1C, 2026-10-18): the switch that offers the
    # small read-only Python tool to the AI model. A card on the desktop and a
    # row on the phone, both drawn from GET /api/sandbox, so the two apps say
    # the same words and only a person's approved card flips it.
    Section("sandbox", ("the data sandbox", "the data and maths sandbox",
                        "the python sandbox", "the sandbox")),
    # "Searchable recordings and videos" (F5 S2, the owner's decision of
    # 2026-10-19: readable transcript text kept, ON by default). A card on the
    # desktop drawn from GET /api/media-index; the phone has NO card yet, so
    # this Section is app="desktop" (the phone's own OpenPlace.kt answers
    # "only in Jarvis on your PC"), and docs/ARCHITECTURE.md section 8 records
    # that follow-up. The spoken switch is the BoolSetting later in this file,
    # so "open searchable recordings" opens the right place on the PC.
    Section("media-index", ("searchable recordings",
                            "searchable recordings and videos",
                            "the recording index", "the media index",
                            "the recordings index"), app="desktop"),
    # "Limits and frequency" (2026-10-08): the numbers the owner can change,
    # ONE table on the PC (backend/jarvis_limits.py) behind one read route and
    # one write route (limits-read.patch + limits-settings.patch). BOTH apps
    # have a screen for it - the PC's Settings card (src-tauri/src/limits.rs,
    # src/limits-settings.js) and the phone's Settings row
    # (ui/screens/LimitsPlate.kt, item "limits") - so this is ONE entry,
    # app="both", carrying both sets of words.
    Section("limits", ("limits", "the limits", "limits and frequencies",
                       "limits and frequency",
                       "limits and how often jarvis does things",
                       "how often jarvis does things"),
            app="both"),
    Section("email-sending", ("sending email", "email sending settings")),
    # "About Jarvis" (corrected 2026-10-10, the parity audit): the phone HAS
    # this card - FaqScreen.kt's `AboutCard()` at the end of Help, reached by
    # "open about" (OpenPlace.kt) - so it is on both apps, and
    # `jarvis_menus.py`'s `settings.about` is both for the same reason.
    Section("about", ("about jarvis", "about"), app="both"),
    # "Hang and crash notes": inside "More options" on the desktop (its own
    # <section id="crash-notes">). The phone has no such list - its own
    # crash screen only appears after a crash - so OpenPlace.PC_ONLY says so.
    Section("crash-notes", ("crash notes", "hang and crash notes", "the crash notes"),
            app="desktop"),
    # "What this backend supports" (corrected 2026-10-10, the parity audit):
    # this said "desktop" while `jarvis_menus.py` said both AND the phone drew
    # the plate - BrainScreen.kt `item(key = "capabilities")`, menu
    # `settings.backend-supports` - which the audit's section 6.3 found. Only
    # the capability LIST is read (the app branches on it); nothing here is a
    # desktop-only control.
    Section("backend-supports", ("what this backend supports", "backend capabilities"),
            app="both"),
    Section("watch-notify", ("smartwatch notifications", "watch notifications"),
            app="phone"),
    # The phone's Quick Settings tiles (SettingsScreen.kt item "quick-tiles").
    Section("quick-tiles", ("quick tiles", "quick settings tiles", "the quick tiles"),
            app="phone"),
    # "Screen refresh rate" (2026-10-09): the rate the PANEL is asked to run at
    # while Jarvis is on screen (jarvis-client's SettingsScreen.kt item
    # "screen-rate"; data/ScreenRate.kt, ui/screens/ScreenRatePlate.kt).
    # Phone-only: the rates come from that phone's own
    # Display.getSupportedModes(), which a desktop does not have, so there is no
    # desktop row and none is invented. Not the animal's frame rate - that lives
    # in the face editor under "appearance-card" and is how often the animal is
    # DRAWN; ScreenRate.kt's own doc says why the two must never be merged.
    Section("screen-rate", ("screen refresh rate", "refresh rate", "the refresh rate",
                            "screen rate", "the screen refresh rate"),
            app="phone"),
    # "Floating Jarvis" (2026-09-27): the phone's own Settings row
    # (SettingsScreen.kt's `item(key = "floating-avatar")` - saved on that phone
    # only, so it needs no `canAct` gate). It had NO section here until
    # 2026-10-08, although `features/features.json` claims
    # `settings.floating-avatar`: `jarvis_quick._run_settings_open` reads such an
    # id through `section_by_id`, and the fallback says the raw id, so "open
    # Floating Jarvis" answered "Opening floating-avatar in Settings." and named
    # a place neither app could find. The new check in
    # test_settings_registry.py keeps the next one from going missing the same
    # way.
    Section("floating-avatar", ("floating jarvis", "the floating face",
                                "the floating avatar", "the bubble"),
            app="phone"),
    Section("phone-notify", ("phone notifications", "reading phone notifications",
                            "notifications on my phone"), app="phone"),
    # "Look at this and Watch with me" (2026-09-29: its own card on the
    # desktop, holding the Never look at list and picture mode; on the phone
    # its own Settings row for picture mode).
    Section("screen-look", ("look at this and watch with me", "look at this", "watch with me", "looking at my screen",
                            "watch with me settings", "the screen settings")),
    # The headless browser, Obscura (2026-09-29): its own card on the desktop
    # and its own Settings row on the phone - the switch, which browser Jarvis
    # uses, and the install line.
    Section("browser-engine", ("headless browser settings", "which browser jarvis uses",
                               "browser settings", "the browser settings")),
    # "Pictures" (the owner's decision of 2026-09-27; pictures.patch,
    # JARVIS-API section 129): "Making pictures", which program on this PC draws
    # them (ComfyUI or stable-diffusion.cpp - a setting with named supported
    # values, never guessed at), the folder the pictures are kept in and its
    # size, and the gallery. Desktop-only as a Settings CARD: the phone reaches
    # the same gallery through the Brain's Pictures plate, and it has no drawing
    # program of its own to configure.
    Section("pictures", ("pictures", "making pictures", "the pictures",
                         "my pictures", "the picture gallery", "drawing pictures"),
            app="desktop"),
    # "When the phone does not answer" (2026-10-08): how long the captcha
    # hand-off stays on offer (jarvis_handoff_mode.py; the owner's own decision
    # of that day, "make this a setting for both options with 1 as the default").
    # A card on the desktop and a Settings row on the phone, both fed by the
    # same words from the PC.
    Section("handoff", ("when the phone does not answer", "the captcha hand-off",
                        "how long the hand-off stays on offer", "solve it here settings")),
    # "When a captcha stops Jarvis" (2026-10-09): what a captcha does about the
    # browser window it is blocking (jarvis_handoff_front.py; the owner's own
    # decision of that day, "1 by default with the option for 2 in the settings
    # of Jarvis"). A card on the desktop and a Settings row on the phone, both
    # fed by the same words from the PC - the same shape as the row above, and
    # deliberately its own id: this is a different question (does the window
    # come forward) from that one (how long the phone may watch it).
    Section("handoff-front", ("when a captcha stops jarvis", "the captcha window",
                              "does the browser window come to the front",
                              "bring the window to the front", "leave it where it is")),
    # "Show or hide menus" (2026-09-30): a card on the desktop and Settings row on the phone.
    Section("menu-visibility", ("menu visibility", "show or hide menus", "hidden menus",
                                "the menus", "menus")),
    # "The big HUD window" (the owner's request of 2026-10-06): the one switch
    # that shows or hides the "Open the Jarvis bar" button in the big "Jarvis"
    # window. Desktop only - the phone has no such row, so OpenPlace.kt lists it
    # PC-only. Cosmetic, so it is "open"-only here: the change itself is made by
    # the page (jarvis-desktop/src/hud-window.js, in this computer's
    # localStorage) the moment the switch is clicked, with no route, no approval
    # card and nothing for a spoken "adjust" to call - the same treatment the
    # floating face and "Interrupt Jarvis while it talks" get.
    Section("hud-window", ("the big hud window", "big hud window", "the hud window",
                           "hud window", "the big jarvis window", "big jarvis window"),
            app="desktop"),
    # Spending (2026-09-30): the phone draws this plate itself (BrainScreen.kt
    # `item(key = "spending")`, menu `settings.spending`, which
    # `contract/menu-cases.json` marks available on the phone, and
    # OpenPlace.kt sends "open spending" there). Corrected from "desktop" to
    # "both" on 2026-10-10 (the parity audit): only the bank-file layouts and
    # the categories editor are the PC's (SpendingPlate.kt says "Set up on the
    # PC"); the summaries themselves are on both.
    Section("spending", ("spending", "spending settings", "my spending", "bank files"),
            app="both"),
    # Notifications (2026-10-01): a card on the desktop ONLY, and it said
    # "both" until 2026-10-09 (settings-coverage audit) - which was untrue.
    # The PC's card is per kind: alarms, reminders, the briefing and the
    # captcha hand-off each on or off, plus quiet hours and a Test button
    # (notifications-settings.js; the toasts themselves are raised in Rust,
    # src-tauri/src/notifications.rs, which is why the choices are pushed to
    # it). The phone has no such screen and cannot have this one: its
    # notification controls are Android's own, per channel (strings.xml
    # "channel_alarm", "channel_schedule", "channel_approval",
    # "channel_handoff" - one per kind, which is what the owner asked for on
    # 2026-09-30: "per kind: on/off, style, Test button, quiet hours"). The
    # phone already said so in its own words: jarvis-client ui/OpenPlace.kt
    # lists "notifications" in PC_ONLY, so "open notifications" there answers
    # "only in Jarvis on your PC" - while this table told the same phone the
    # section was on both apps. Corrected here rather than left for the next
    # reader to find; test_settings_registry.py holds the two together now.
    Section("notifications", ("notifications", "notification settings", "desktop notifications"),
            app="desktop"),
    # "All features and abilities" (2026-10-22, #749): the phone's directory of the
    # 139 features. PHONE ONLY, and the reason is the same one the desktop page
    # gives: the desktop's own directory card has NO `<section class="card" id>`
    # (settings.html says so beside the card - it is a generated, read-only index,
    # not a settings section, and it calls nothing). The phone's directory is a
    # real `item(key = "all-features")` row (SettingsScreen.kt), so "open all
    # features and abilities" can name it there; a phone-only row therefore, like
    # "Approval cards" and the notification rows above. It changes nothing.
    Section("all-features", ("all features and abilities", "all features",
                             "abilities and commands", "the feature directory"),
            app="phone"),
    # "Limits and how often Jarvis does things" (2026-10-08): the limits and
)

#: id -> Section, for a direct lookup once a name has matched.
_BY_ID = {s.id: s for s in SECTIONS}


def section_by_id(section_id: str) -> Optional[Section]:
    return _BY_ID.get(section_id)


def sections_for(app: str) -> tuple:
    """Every Section this `app` ("desktop" or "phone") actually has."""
    return tuple(s for s in SECTIONS if s.app in ("both", app))


def find_section(words: str) -> Optional[Section]:
    """The one Section `words` (already lower-cased and tidied, as
    jarvis_quick.normalise() leaves a sentence) names, or None - never a
    fuzzy guess: an exact alias (a leading "the"/"my"/"a"/"an" ignored
    either side), because "open settings" said with the wrong noun should
    say so, not jump somewhere unexpected."""
    bare = _bare(words)
    if not bare:
        return None
    for s in SECTIONS:
        if bare == _bare(s.id.replace("-", " ")) or any(bare == _bare(n) for n in s.names):
            return s
    return None


# --------------------------------------------------------------------------
#   "Adjust": a small, real function per setting - never a new one.
# --------------------------------------------------------------------------


@dataclass
class Outcome:
    """What happened, in the owner's own words - never invented here; every
    `said` is read straight off the real function's own return value."""
    ok: bool
    said: str
    waiting: bool = False       # a card is up; nothing changed yet
    refused_pc_only: bool = False


def _say(code: int, out: dict, *, on_ok: Optional[str] = None) -> Outcome:
    """The common shape every one of these `handle_*`/`request_*` functions
    already returns: (http code, {"ok"?, "message"|"said"?, "error"?,
    "waiting"?, "pc_only"?}). Never invents a sentence: falls back to a
    plain "that did not work" only when the function gave none at all."""
    out = out if isinstance(out, dict) else {}
    if out.get("pc_only"):
        return Outcome(False, str(out.get("error") or "That can only be changed on the PC."),
                       refused_pc_only=True)
    said = str(out.get("message") or out.get("said") or "")
    if code >= 400 or out.get("ok") is False:
        return Outcome(False, said or str(out.get("error") or "That did not work."))
    waiting = bool(out.get("waiting"))
    if not said:
        said = on_ok or ("Waiting for your approval." if waiting else "Done.")
    return Outcome(True, said, waiting=waiting)


def _missing(name: str) -> Outcome:
    return Outcome(False, f"Your PC's Jarvis does not have {name} yet - run "
                          "apply-patches.ps1 on the PC.")



# --- the prompt coach (jarvis_prompt_coach.py) ----------------------------

def set_prompt_coach(on: bool, *, peer=None, local=None) -> Outcome:
    """Off at once, on at once. Neither direction asks: this reads words the
    chat is about to send to the same local model anyway, takes no action, and
    opens no way out of the PC."""
    try:
        import jarvis_prompt_coach as PC
    except Exception:
        return _missing("the prompt coach")
    try:
        out = PC.set_enabled(bool(on))
    except PC.Refused as exc:
        return Outcome(False, str(exc))
    except Exception as exc:
        return Outcome(False, "The prompt coach's setting could not be saved "
                              f"({type(exc).__name__}).")
    return _say(200, out or {})


# --- background learning (jarvis_auto_learn.py) ---------------------------

def set_background_learning(on: bool, *, peer=None, local=None) -> Outcome:
    try:
        import jarvis_auto_learn as AL
    except Exception:
        return _missing("automatic learning")
    code, out = AL.handle_post("/api/memory/learning/auto", {"enabled": bool(on)})
    return _say(code, out)


def set_learn_sensitive(on: bool, *, peer=None, local=None) -> Outcome:
    try:
        import jarvis_auto_learn as AL
    except Exception:
        return _missing("automatic learning")
    code, out = AL.handle_post("/api/memory/learning/sensitive", {"enabled": bool(on)})
    return _say(code, out)


# --- lights, plugs and fans without a card (jarvis_asks_first.py) ---------

def set_lights_without_card(on: bool, *, peer=None, local=None) -> Outcome:
    try:
        import jarvis_asks_first as AF
    except Exception:
        return _missing("\"lights, plugs and fans\"")
    code, out = AF.handle_lights({"enabled": bool(on)})
    return _say(code, out)


# --- web search: "ask before every search" (jarvis_search.py) -------------

def set_ask_every_search(on: bool, *, peer=None, local=None) -> Outcome:
    try:
        import jarvis_search as WS
    except Exception:
        return _missing("web search")
    code, out = WS.request_ask_every_time(bool(on))
    return _say(code, out)


# --- web search on/off (jarvis_search.py, 2026-09-30) ----------------------

def set_web_search(on: bool, *, peer=None, local=None) -> Outcome:
    """OFF at once; ON raises the one approval card (web_search_enable) - the
    same jarvis_search.request_enabled the Settings switch calls."""
    try:
        import jarvis_search as WS
    except Exception:
        return _missing("web search")
    code, out = WS.request_enabled(bool(on))
    return _say(code, out)


# --- smartwatch notifications (jarvis_watch_notify.py) ---------------------

def set_watch_notify(on: bool, *, peer=None, local=None) -> Outcome:
    try:
        import jarvis_watch_notify as WN
    except Exception:
        return _missing("smartwatch notifications")
    code, out = WN.request(bool(on), WN.set_enabled)
    return _say(code, out)


# --- reading phone notifications (jarvis_phone_notifications.py) ----------

def set_phone_notifications(on: bool, *, peer=None, local=None) -> Outcome:
    try:
        import jarvis_phone_notifications as PN
    except Exception:
        return _missing("reading phone notifications")
    code, out = PN.request(bool(on), PN.set_enabled)
    return _say(code, out)


# --- picture mode for the screen (jarvis_screen_picture.py) ----------------

def set_screen_picture(on: bool, *, peer=None, local=None) -> Outcome:
    try:
        import jarvis_screen_picture as SP
    except Exception:
        return _missing("picture mode for the screen")
    code, out = SP.request(bool(on), SP.set_enabled)
    return _say(code, out)


# --- the 30B coder, both cards, Jarvis paused (jarvis_big_coder.py) --------

def set_big_coder(on: bool, *, peer=None, local=None) -> Outcome:
    """Turn the big coding model's opt-in switch on or off. ON is ONE approval
    card inside jarvis_big_coder (action change_own_config, tier "ask"); OFF is
    immediate. This does not START the mode - that is its own call, and it
    pauses the two live lanes first."""
    try:
        import jarvis_big_coder as BC
    except Exception:
        return _missing("the big coding model")
    code, out = BC.set_enabled(bool(on))
    return _say(code, out)


# --- the headless browser, Obscura (jarvis_browser_engine.py) --------------

def set_browser_engine(on: bool, *, peer=None, local=None) -> Outcome:
    try:
        import jarvis_browser_engine as BE
    except Exception:
        return _missing("the headless browser")
    code, out = BE.request(bool(on), BE.set_obscura)
    return _say(code, out)


# --- the data and maths sandbox (jarvis_sandbox_exec.py, LM-1 2026-10-18) --

def set_sandbox_exec(on: bool, *, peer=None, local=None) -> Outcome:
    """Offer (or stop offering) the local data-and-maths sandbox to the AI
    model. OFF is immediate; ON is ONE normal approval card
    (`change_own_config`, tier ask) and nothing is written before a person says
    yes - the module's own `request_enabled()` does both, exactly as a route
    would. There is no static Settings toggle wired to this yet (LM-1C); the
    reachable door tonight is this spoken one, on both apps."""
    try:
        import jarvis_sandbox_exec as SANDBOX
    except Exception:
        return _missing("the data and maths sandbox")
    code, out = SANDBOX.request_enabled(bool(on))
    return _say(code, out)


# --- searchable recordings and videos (jarvis_media_index.py, F5 S2 2026-10-19) --

def set_media_index(on: bool, *, peer=None, local=None) -> Outcome:
    """Keep (or stop keeping) readable words from recordings and videos in the
    owner's listed folders (F5 S2; owner decision of 2026-10-19: readable
    transcript text, ON by default).

    OFF is immediate; ON is ONE normal approval card (`change_own_config`, tier
    ask) raised by the module's own `request_enabled()` - the same function the
    desktop Settings card and its route call, so a direct POST cannot bypass
    the card. ON asks because it starts keeping readable private speech on the
    PC again; OFF never asks, like every narrowing."""
    try:
        import jarvis_media_index as MI
    except Exception:
        return _missing("searchable recordings")
    code, out = MI.request_enabled(bool(on))
    return _say(code, out)


# --- making pictures (jarvis_pictures.py, JARVIS-API section 129) ----------

def set_pictures(on: bool, *, peer=None, local=None) -> Outcome:
    """The one switch the picture feature has. BOTH directions happen at once
    and neither asks for a card.

    Said plainly, because it is the kind of thing that gets "fixed" wrongly
    later: this is NOT one of the switches that must ask. It opens no way out
    of the PC (a picture is drawn by a program on this PC and saved in a
    folder on this PC), changes no account, and loosens no rule - it is the
    same shape as "web search" or "prompt coach", which both flip at once.
    Turning it ON does mean the drawing program will take the second card when
    the owner asks for a picture, which is exactly why it starts OFF and why
    the owner has to say so once (CLAUDE.md: a feature using the second card
    keeps its own switch, off until that feature is measured).

    A Jarvis without jarvis_pictures.py answers in words, never silently.
    """
    try:
        import jarvis_pictures as P
    except Exception:
        return _missing("making pictures")
    path = P.settings_path()
    values = P.load_settings(path)
    values["enabled"] = bool(on)
    P.save_settings(values, path)
    if on and not values.get("runtime"):
        # Switched on, but there is nothing to draw with yet. Say both things:
        # the switch moved, AND nothing can be drawn until a program is named.
        return Outcome(True, "Making pictures is on. " + P.NOT_CONFIGURED)
    return Outcome(True, "Making pictures is on." if on
                   else "Making pictures is off.")


def pictures_on() -> Optional[bool]:
    """Is "Making pictures" switched on? Read here, never by a caller.

    `jarvis_pictures` is imported by exactly one module in this tree, on
    purpose (`test_pictures.py`'s pin): any second importer would make the
    drawing module reachable from a model turn. The Feature Guide needs this
    switch's current state to answer "is making pictures on?", so the read
    lives here, where the import already exists for `set_pictures`, and the
    caller gets None when the answer cannot be read - so it says it could not
    be read rather than guessing "off".
    """
    try:
        import jarvis_pictures as P
        return P.load_settings().get("enabled") is True
    except Exception:
        return None


# --- topic controls: a topic's mode (jarvis_topics.py) ---------------------

def find_topic(words: str) -> Optional[dict]:
    """The one topic `words` names exactly (case ignored), or None."""
    try:
        import jarvis_topics as T
        want = _bare(words).casefold()
        with T._db() as c:
            for t in T.topics_of(c):
                if t["name"].casefold() == want:
                    return t
    except Exception:
        return None
    return None


def set_topic_mode(topic_id: int, mode: str, *, peer=None, local=None) -> Outcome:
    """The exact function the picker calls (POST /api/topics/mode). Stricter:
    at once. Looser on a private topic: its one card, and nothing changes until
    it is approved. Never asked from outside text (jarvis_quick refuses first)."""
    try:
        import jarvis_topics as T
    except Exception:
        return _missing("topic controls")
    code, out = T.set_mode(topic_id, mode)
    if code == 202:
        return Outcome(True, T.WORDS["waiting"] + " Approve the card and the change is made.",
                       waiting=True)
    if code >= 400 or out.get("ok") is False:
        return Outcome(False, str(out.get("message") or "That did not work."))
    row = next((t for t in out.get("topics", []) if t["id"] == int(topic_id)), None)
    name = row["name"] if row else "That topic"
    return Outcome(True, T.WORDS["moved_line"].format(name=name, mode=T.MODE_NAME[mode]))


# --- morning briefing: senders shown (jarvis_briefing.py) -----------------

def set_briefing_senders(on: bool, *, peer=None, local=None) -> Outcome:
    try:
        import jarvis_briefing as BR
    except Exception:
        return _missing("the morning briefing")
    code, out = BR.handle_senders({"enabled": bool(on)})
    return _say(code, out)


# --------------------------------------------------------------------------
#   The settings that were reachable only by opening Settings (2026-10-13).
#
#   Every one of these already had a working route and its own tier before
#   this file named it - the audit of 2026-10-13 (settings-reachability-audit)
#   found that none of them was missing a route or a gate, only a phrase. So
#   each setter below calls the EXACT function the screen calls, and invents
#   no tier of its own:
#
#     * the five notification switches ride jarvis_limits.change(), the same
#       route the phone's Settings rows use. All seven of those rows are
#       `loosening="none"` on purpose (jarvis_limits.py:406-414): a bigger
#       quiet window or a switch turned on only changes when this PC shows its
#       owner a toast, so nothing here raises a card - and an alarm must never
#       fail to ring because a card about it was not answered.
#     * humour is jarvis_manner.handle_set(), at once either way, like manner.
#       (`handle_set`, not `handle_post`: this header named a function that has
#       never existed until 2026-10-13, which is one of the places the wrong name
#       was copied from - see set_humor below.)
#     * "Voice follows the face" is jarvis_voices.set_face_voice(), at once.
#     * the better voice is jarvis_voices.set_better(), OFF at once and ON
#       through its OWN card (better_voice_enable) - unchanged here.
# --------------------------------------------------------------------------

#: The five notification switches, and the `jarvis_limits` key each one is.
_NOTIFY_LIMIT = {
    "pc_alarm_sounds": "notif_alarms",
    "pc_reminder_sounds": "notif_reminders",
    "pc_briefing_notification": "notif_briefing",
    "pc_handoff_notification": "notif_handoff",
    "pc_quiet_hours": "notif_quiet_enabled",
}

#: What each of the five is called in plain words, for the sentence when that
#: backend does not have the row (an older PC) - never invented here.
_NOTIFY_PLAIN = {
    "pc_alarm_sounds": "alarm sounds on your PC",
    "pc_reminder_sounds": "reminder sounds on your PC",
    "pc_briefing_notification": "the briefing notification on your PC",
    "pc_handoff_notification": "the \"a website needs you\" notification",
    "pc_quiet_hours": "quiet hours on your PC",
}


def _set_notify(key: str, on: bool, *, peer=None, local=None) -> Outcome:
    """One of the five `[notifications]` switches, through jarvis_limits.change.

    The same route the phone's own Settings row calls. `loosening="none"` on
    all five, so no card - a change here only moves when this PC speaks up."""
    try:
        import jarvis_limits as LIM
    except Exception:
        return _missing(_NOTIFY_PLAIN.get(key, "that notification setting"))
    limit_key = _NOTIFY_LIMIT[key]
    code, out = LIM.change({"key": limit_key, "value": bool(on)}, peer=peer, local=local)
    return _say(code, out, on_ok=("Done." if on else "Done - Jarvis stays quiet about that."))


def set_pc_alarm_sounds(on: bool, *, peer=None, local=None) -> Outcome:
    return _set_notify("pc_alarm_sounds", on, peer=peer, local=local)


def set_pc_reminder_sounds(on: bool, *, peer=None, local=None) -> Outcome:
    return _set_notify("pc_reminder_sounds", on, peer=peer, local=local)


def set_pc_briefing_notification(on: bool, *, peer=None, local=None) -> Outcome:
    return _set_notify("pc_briefing_notification", on, peer=peer, local=local)


def set_pc_handoff_notification(on: bool, *, peer=None, local=None) -> Outcome:
    return _set_notify("pc_handoff_notification", on, peer=peer, local=local)


def set_pc_quiet_hours(on: bool, *, peer=None, local=None) -> Outcome:
    return _set_notify("pc_quiet_hours", on, peer=peer, local=local)


def set_humor(on: bool, *, peer=None, local=None) -> Outcome:
    """The humour switch: `jarvis_manner.handle_set({"humor": ...})`, the same
    function Settings calls. At once either way - it changes wording only.

    `handle_set`, NOT `handle_post` (fixed 2026-10-13). This called
    `MN.handle_post(...)`, and jarvis_manner.py has never defined a function of
    that name - it has `handle_get` and `handle_set`. So the phrase this file
    exists to add ("turn on humour") raised AttributeError out of `set`, while
    the Settings page's own route, POST /api/manner, went through handle_set and
    worked. `manner.patch` and `thinking.patch` and this file's own set_manner
    (below) all call handle_set; set_humor was the only caller in the tree
    naming handle_post. backend/test_settings_tool.py now walks every setter's
    own imports with `ast` and fails on any module attribute that does not
    exist, which is the check that catches this whole class of mistake. (It does
    NOT call the real setters - they would write the owner's live settings; all
    21 are recording stand-ins in that suite. Said plainly because an earlier
    version of this line claimed it "calls every setter", which it does not.)"""
    try:
        import jarvis_manner as MN
    except Exception:
        return _missing("the humour switch")
    code, out = MN.handle_set({"humor": bool(on)})
    return _say(code, out, on_ok=("Done." if on else "Done - no jokes."))


def set_voice_follows_face(on: bool, *, peer=None, local=None) -> Outcome:
    """`jarvis_voices.set_face_voice({"enabled": ...})` - at once, no card
    either way (jarvis_voices.py:1340)."""
    try:
        import jarvis_voices as JV
    except Exception:
        return _missing("\"voice follows the face\"")
    code, out = JV.set_face_voice({"enabled": bool(on)})
    return _say(code, out)


def set_better_voice(on: bool, *, peer=None, local=None) -> Outcome:
    """`jarvis_voices.set_better({"enabled": ...})`: OFF at once, ON through
    its own card (better_voice_enable). Nothing about that tier is changed
    here - this file adds the phrase, not the rule."""
    try:
        import jarvis_voices as JV
    except Exception:
        return _missing("the better voice")
    code, out = JV.set_better({"enabled": bool(on)})
    return _say(code, out)


# --- the universal-control pass (2026-10-22) ------------------------------
# The owner's requirement: every function or feature can be turned on or off
# by typing at Jarvis on either app. These switches already had a real route
# and a real control somewhere; what they lacked was a spoken name. Each
# setter below calls the EXACT function the control/route already calls (or
# its own route handler, when that is where the gating lives) - never a new
# mutation path, and never a weaker tier than the control's own.

def set_chat_history(on: bool, *, peer=None, local=None) -> Outcome:
    """`jarvis_chat_log.request_settings`: OFF at once, ON is its own card."""
    try:
        import jarvis_chat_log as CL
    except Exception:
        return _missing("chat history")
    code, out = CL.request_settings({"enabled": bool(on)})
    return _say(code, out)


def set_write_like_me(on: bool, *, peer=None, local=None) -> Outcome:
    """`jarvis_voiceprint.handle_post` at its ENABLED_PATH: the one switch the
    "Write like me" control writes. No card either way (it changes whether a
    profile is used, not what may leave the PC)."""
    try:
        import jarvis_voiceprint as VP
    except Exception:
        return _missing("\"Write like me\"")
    code, out = VP.handle_post(VP.ENABLED_PATH, {"enabled": bool(on)})
    return _say(code, out)


def _set_big_model_switch(switch: str, on: bool) -> Outcome:
    try:
        import jarvis_big_model as BM
    except Exception:
        return _missing("the big model")
    code, out = BM.request_change(switch, bool(on))
    return _say(code, out)


def set_big_model(on: bool, *, peer=None, local=None) -> Outcome:
    return _set_big_model_switch("master", on)


def set_big_model_wiki(on: bool, *, peer=None, local=None) -> Outcome:
    return _set_big_model_switch("wiki", on)


def set_big_model_deep_questions(on: bool, *, peer=None, local=None) -> Outcome:
    return _set_big_model_switch("deep_questions", on)


def _set_second_card_feature(feature: str, on: bool) -> Outcome:
    try:
        import jarvis_second_card as SC
    except Exception:
        return _missing("the second graphics card")
    code, out = SC.request_change(feature, bool(on))
    return _say(code, out)


def set_second_card_combined(on: bool, *, peer=None, local=None) -> Outcome:
    return _set_second_card_feature("combined", on)


def _set_second_card_suggestion(signal: str, on: bool) -> Outcome:
    try:
        import jarvis_second_card as SC
    except Exception:
        return _missing("the second graphics card")
    code, out = SC.handle_suggest_post({"signal": signal, "enabled": bool(on)})
    return _say(code, out)


def set_second_card_suggest_struggle(on: bool, *, peer=None, local=None) -> Outcome:
    return _set_second_card_suggestion("struggle", on)


def set_second_card_suggest_correction(on: bool, *, peer=None, local=None) -> Outcome:
    return _set_second_card_suggestion("correction", on)


# --- "what asks first": loosening a named action, the PC only -------------
# jarvis_owner_check.PC_ONLY_ACTIONS holds "loosen_what_asks_first" itself
# (the CARD's approval is PC-only+Hello); the REQUEST to raise that card is
# ALSO refused off this PC by jarvis_asks_first.request_tier itself
# (`_here(here, peer, local)`), which is what `peer`/`local` here feed.

#: What the owner might call each of the four readable things and the three
#: note-writes jarvis_asks_first.LOOSE already lists (its own action names).
_ASKS_FIRST_TARGETS = {
    "calendar_read": ("my calendar", "the calendar", "reading my calendar"),
    "email_read": ("my email", "reading my email", "my mail"),
    "notes_search": ("my notes", "reading my notes", "searching my notes"),
    "home_read": ("home status", "reading home status", "my home assistant"),
    "append_obsidian_daily": ("my obsidian daily note", "writing my obsidian daily note"),
    "append_logseq_journal": ("my logseq journal", "writing my logseq journal"),
    "create_joplin_note": ("a joplin note", "a new joplin note", "writing a joplin note"),
}


def asks_first_targets() -> dict:
    """A copy, for jarvis_quick.py's grammar to build its own alias regex
    from - never hand-typed twice."""
    return dict(_ASKS_FIRST_TARGETS)


def find_asks_first_target(words: str) -> Optional[str]:
    bare = _bare(words)
    for action, names in _ASKS_FIRST_TARGETS.items():
        if any(bare == _bare(n) for n in names):
            return action
    return None


def set_asks_first(action: str, ask: bool, *, peer=None, local=None) -> Outcome:
    """`ask=True` is "ask me first again" (stricter, works from anywhere);
    `ask=False` is "stop asking" (looser, the PC only, one card plus
    Windows Hello - jarvis_asks_first.request_tier's own refusal, not a
    second one invented here)."""
    try:
        import jarvis_asks_first as AF
    except Exception:
        return _missing("\"what asks first\"")
    code, out = AF.handle_tier({"action": action, "ask": bool(ask)}, peer, local)
    return _say(code, out)


# --- offering a reading tool to the AI model at all (jarvis_asks_first.py) -

_TOOL_TARGETS = {
    "calendar_read": ("the calendar tool", "calendar", "my calendar"),
    "email_read": ("the email tool", "email", "my email"),
    "notes_search": ("the notes tool", "notes", "my notes"),
    "home_read": ("the home status tool", "home status"),
}


def tool_targets() -> dict:
    return dict(_TOOL_TARGETS)


def find_tool_target(words: str) -> Optional[str]:
    bare = _bare(words)
    for tool, names in _TOOL_TARGETS.items():
        if any(bare == _bare(n) for n in names):
            return tool
    return None


def set_reading_tool(tool: str, enabled: bool, *, peer=None, local=None) -> Outcome:
    """ON is the PC only, one card plus Windows Hello
    (jarvis_asks_first.request_tool_enable's own refusal); OFF is instant,
    from either app."""
    try:
        import jarvis_asks_first as AF
    except Exception:
        return _missing("offering a reading tool to the AI model")
    code, out = AF.handle_tools({"tool": tool, "enabled": bool(enabled)}, peer, local)
    return _say(code, out)


# --- already-covered by jarvis_quick.py's own grammar - registered here so
#     "open web search"/"open how jarvis talks" resolve, and so this file's
#     own tests can prove the two paths agree, never duplicated. ------------

def set_web_search_provider(provider: str, *, peer=None, local=None) -> Outcome:
    try:
        import jarvis_search as WS
    except Exception:
        return _missing("web search")
    return Outcome(True, WS.use(provider))


def set_personality(personality: str, *, peer=None, local=None) -> Outcome:
    """One of the eight personality presets (jarvis_manner.py, 2026-10-22).

    Cardless by design, like the manner: it changes how Jarvis words things,
    never what it does, asks, approves or remembers. An unknown name is refused
    with the real ones, never guessed."""
    try:
        import jarvis_manner as MN
    except Exception:
        return _missing("\"the personality\"")
    ok, said = MN.set_personality(personality)
    if not ok:
        return Outcome(False, said)
    return Outcome(True, said)


def _personality_choices() -> dict:
    """Every spoken/typed name that really switches a preset -> its id.

    Read FRESH from jarvis_manner (the same callable shape the voices row
    uses), so a built-in renamed in the contract, or a saved "My Personalities"
    preset, appears here without a second hand-typed list."""
    try:
        import jarvis_manner as MN
        out = {}
        for preset in MN.all_personalities():
            for word in [preset["id"], preset.get("title") or ""] + list(
                    preset.get("aliases") or []):
                word = str(word or "").strip()
                if word:
                    out[word] = preset["id"]
        return out
    except Exception:
        return {"warm": "warm_peer", "plain": "tactical_ops"}


def set_manner(manner: str, *, peer=None, local=None) -> Outcome:
    try:
        import jarvis_manner as MN
    except Exception:
        return _missing("\"how jarvis talks\"")
    code, out = MN.handle_set({"manner": manner})
    if code != 200 or not out.get("ok"):
        return Outcome(False, "Jarvis could not change that setting just now.")
    word = "plainly" if manner == "plain" else "warmly and briefly"
    return Outcome(True, f"Done - Jarvis now answers {word}.")


# --------------------------------------------------------------------------
#   The desktop Settings page's own switch rows (2026-10-09): every
#   `<label class="toggle">` in jarvis-desktop/src/settings.html, in the
#   order the page has them, with the words the page shows.
#
#   WHY THIS IS NOT `BOOL_SETTINGS` ABOVE. `BOOL_SETTINGS` is the SPOKEN
#   table: jarvis_quick.py's grammar reads its `names` (jarvis_quick.py:2788)
#   and dispatches on its `set` (:3703-3709). A row here is a thing on a
#   SCREEN. They overlap on ten rows, and the overlap is 2-way on purpose:
#
#     * a row with no `setting` - 15 of the 26 - has NO spoken "adjust" and
#       no setter in this file at all (the switch is acted on by its own
#       desktop module, or by a Tauri command). Adding it to BOOL_SETTINGS
#       would make "turn on autostart" MATCH the grammar and then fail at
#       dispatch; nothing checks that today (backend/test_settings_registry.py
#       only round-trips two keys), so it would be a silent lie.
#     * a `BoolSetting` with no desktop row is the phone's own
#       ("phone_notifications") or lives on the Brain's Memory tab
#       ("background_learning", "learn_sensitive_topics").
#
#   Nothing in this table is ever spoken: `names` and `set` stay exactly
#   where they were. tools/gen_settings_cases.py turns this table into the
#   two byte-identical contract fixtures, the phone's SettingsCatalog.kt and
#   the desktop's settings-catalog.js, and splices the rows back into
#   settings.html between two markers - so the page, the fixtures and both
#   apps cannot drift apart. backend/test_settings_rows.py fails when a
#   hand-added toggle has no row here.
#
#   WORDS ARE A FALLBACK, NOT A SECOND OWNER - see `fallback` below. ELEVEN
#   rows have their visible words sent by the PC at read time
#   (`fallback=True`); for those, the text carried here is the sentence the
#   page shows before the read answers, exactly as the markup has it today.
#   Nothing may be changed HERE to change what the owner reads on those
#   rows: that is the PC's to say. (An earlier count of "12" in the handoff
#   added `spd-accept`; it does NOT belong - its span starts EMPTY and is
#   filled by a local constant, spending.js's BOX.acceptTick, so the PC
#   never sends it and the markup was never a fallback for it.)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SettingRow:
    """One `<label class="toggle">` row on the desktop's Settings page."""

    #: This row's identity: the `<input>`'s own id in settings.html, which
    #: is also what the desktop JavaScript looks the switch up by. Stable -
    #: never renamed.
    dom_id: str
    #: The BoolSetting this row is (side of) the same switch as, or None.
    #: None means no spoken "adjust" exists for it - see the note above.
    setting: Optional[str]
    #: The `<label>`'s own id, when the page puts one there so a module can
    #: hide or relabel the whole row. "" when the label carries no id.
    row_id: str
    #: The id of the `<span>` the label's words sit in, when it is NOT the
    #: `<input>`'s own id. "" when the span has no id (its parent `<label>`
    #: is then the only handle).
    label_span_id: str
    #: The id of the `class="toggle-detail"` span, or "" when that span
    #: carries no id of its own (two rows - `face-auto` and
    #: `cv-better-switch` - never got one). Separate from `has_detail`: a span
    #: without an id still exists and still has to be written back.
    detail_span_id: str
    #: What the page shows as the row's title, and its one-line detail, in
    #: PLAIN TEXT (the fixture is JSON, not markup - a detail containing
    #: `<code>` appears here as the words between the tags).
    label: str
    detail: str
    #: Position on the page, 1-based, top to bottom. Checked against the
    #: page's real order by the generator, the --check mode, the Python test
    #: and the desktop Node test - row order was unprotected before this.
    order: int
    #: The `<section class="card" id="...">` (or `<details id="more-options">`)
    #: this row sits inside. Checked to be a real card AND a SECTIONS id.
    section: str
    #: "desktop" (this row is the desktop's) or "phone" (the words belong to
    #: the phone; the desktop has no such row).
    owner: str
    #: How far the row's own `<label>` is indented in settings.html, in
    #: spaces. The rows do NOT all sit at one depth - `supervise` is three
    #: levels inside "More options", `face-auto` two - and the generated page
    #: has to put each one back exactly where it was, so the depth is
    #: recorded here rather than assumed. Checked against the page on every
    #: run of the generator, which fails loudly if it drifts.
    indent: int = 8
    #: True when the row has a `class="toggle-detail"` span at all. Five rows
    #: have none (`notif-quiet-enabled`, `sp-switch`, `be-switch`, `supervise`,
    #: `autostart`) - the page keeps those to a single line - and a span can
    #: exist without an id of its own (`face-auto`, `cv-better-switch`), which
    #: is why this is a flag rather than "detail_span_id is not empty".
    has_detail: bool = False
    #: The `<input ... />` tag VERBATIM, whitespace collapsed.
    #:
    #: This is the one place the table does not describe a row field by field.
    #: Twenty-five rows spell the tag the same way - `type="checkbox"`, the id,
    #: then any of `checked`/`data-live` - and could be built from flags. The
    #: twenty-second (`spd-accept`) cannot: the page writes
    #: `<input type="checkbox" id="spd-accept" />`, with the type first and the
    #: id second, and every other row the other way round. Rather than invent a
    #: flag meaning "the other word order", the tag itself is recorded, so the
    #: page cannot drift from it and no reader has to work out which flag
    #: produced which ordering.
    input_open: str = ""
    #: True when the label's `<span id="...">` shares its line with the words
    #: instead of opening a line above them. One row does this - `spd-accept`,
    #: whose span starts empty and is filled later by spending-settings.js.
    label_span_inline: bool = False
    #: True when `label_span_id` is the id of the WRAPPER span itself rather
    #: than of a child span inside it. One row does this - `spd-accept`, whose
    #: `<span id="spd-accept-text"></span>` IS the row's only span - and the
    #: renderer must then put the id on the line it already writes instead of
    #: wrapping it in a second span.
    label_span_is_wrapper: bool = False
    #: True when a row with no child span and no detail span still opens the
    #: wrapping `<span>` on a line of its own instead of sharing that line
    #: with the words. One row does this - `notif-quiet-enabled` - and the
    #: difference is whitespace INSIDE the span, so it cannot be worked out
    #: from the words; the page is the only thing that knows.
    span_on_own_line: bool = False
    #: For a phone-owned row: SettingsScreen.kt's `item(key = "...")`.
    phone_key: str = ""
    #: True when the PC sends this row's visible words at read time, so the
    #: text above is the FALLBACK the page starts with, never the words the
    #: owner ends up reading.
    fallback: bool = False
    #: Extra attributes on the `<input>`, reproduced verbatim in settings.html.
    checked: bool = False
    hidden: bool = False
    data_live: bool = False
    #: False for the ONE `<label class="toggle">` that is not a settings
    #: switch at all: `spd-accept` is the spending screen's "accept every
    #: column" control, and its label carries `hidden`. It is described here
    #: (so the page and this table still agree, and the count stays honest)
    #: and flagged `setting_row=False` so nothing treats it as a preference.
    setting_row: bool = True
    #: For a phone-owned row: the Kotlin the words above are copied FROM, so
    #: the two can be compared by eye (there is no build step that reads the
    #: Kotlin, and the phone may one day read the catalogue for it instead).
    source: str = ""


#: The desktop page's 26 toggle rows, in page order. The PAGE-OWNED rows
#: (owner="desktop") are generated into settings.html between its
#: "settings-toggles:begin/end" markers; the two phone rows are carried for
#: the phone's SettingsCatalog.kt only.
SETTINGS_ROWS: tuple = (
    # ------------------------------------------------------------------
    #   The desktop page's own 26 rows, in page order. Every field that
    #   the page can answer for itself (the ids, and the label and detail
    #   words, line breaks included) was read FROM settings.html; the
    #   rest - which BoolSetting a row is the same switch as, which card
    #   it sits in - was written by hand and is checked, not guessed, by
    #   tools/gen_settings_cases.py.
    # ------------------------------------------------------------------
    SettingRow(
        "follow-system",
        None,
        "",
        "",
        "follow-system-detail",
        'Match Windows light or dark mode',
        (
        'Daylight when Windows is light, your dark theme when it is dark.\n'
        'A switch waits until Jarvis is idle, never mid-approval.\n'),
        1,
        "appearance-card",
        "desktop",
        indent=8,
        has_detail=True),
    SettingRow(
        "floating-enabled",
        None,
        "",
        "",
        "floating-detail",
        'Floating face',
        (
        "A small window, always on top, that shows only Jarvis's face -\n"
        'no text box. Drag it anywhere. Say "open a chat", or press\n'
        'Alt+Space, to bring up the real Jarvis bar. Alt+Shift+F shows\n'
        'or hides this face (see Shortcuts below to change either key).\n'),
        2,
        "appearance-card",
        "desktop",
        indent=8,
        has_detail=True),
    # "Click through to what is behind" (2026-10-10, the integration
    # evaluation, docs/INTEGRATION-EVAL-2026-10-10.md): the floating face stops
    # taking clicks everywhere except on the animal itself. Off by default and
    # applied at once, and it has no spoken "adjust" of its own - it is a
    # cosmetic switch on the row below "Floating face", so it needs no entry
    # in BOOL_SETTINGS (see that list's own note).
    SettingRow(
        "floating-click-through",
        None,
        "",
        "floating-click-through-label",
        "floating-click-through-detail",
        'Click through to what is behind',
        (
        "Clicks on the floating face go to whatever is behind it, except on\n"
        'the animal itself - so it can still be dragged, and the face stops\n'
        'getting in the way of whatever is underneath. Off to start.\n'),
        3,
        "appearance-card",
        "desktop",
        indent=8,
        has_detail=True),
    SettingRow(
        "sky-show",
        None,
        "",
        "sky-show-label",
        "sky-show-detail",
        'Show the sun and moon behind the face',
        '',
        4,
        "animal-options",
        "desktop",
        indent=12,
        has_detail=True,
        fallback=True),
    SettingRow(
        "face-auto",
        None,
        "",
        "",
        "",
        'Auto adjust',
        (
        'Picks quality and frame rate for this computer, and steps down\n'
        'if the face runs slow. On a capable graphics chip an animal can\n'
        'go up to Maximum.\n'),
        5,
        "animal-options",
        "desktop",
        indent=10,
        has_detail=True),
    SettingRow(
        "voice-one-moment",
        None,
        "",
        "",
        "voice-one-moment-detail",
        'Say "One moment" if I\'m kept waiting',
        '',
        6,
        "voice",
        "desktop",
        indent=8,
        has_detail=True,
        fallback=True),
    SettingRow(
        "voice-heard-sound",
        None,
        "",
        "",
        "voice-heard-sound-detail",
        'Play a short sound when I finish speaking',
        '',
        7,
        "voice",
        "desktop",
        indent=8,
        has_detail=True,
        fallback=True),
    SettingRow(
        "mn-humor",
        "humor",
        "",
        "",
        "mn-humor-detail",
        'Occasional light humour in answers',
        '',
        8,
        "manner",
        "desktop",
        indent=10,
        has_detail=True,
        fallback=True,
        data_live=True),
    SettingRow(
        "coach-enabled",
        "prompt_coach",
        "",
        "coach-enabled-label",
        "coach-enabled-detail",
        'Prompt coach',
        '',
        9,
        "prompt-coach",
        "desktop",
        indent=10,
        has_detail=True,
        fallback=True),
    SettingRow(
        "br-senders",
        "briefing_senders",
        "br-senders-row",
        "",
        "",
        'Show who new emails are from',
        'The briefing lists who your newest unread emails are from (up to 5), next to how many there are. Off: the number only. Turning it on shows you an approval card first; turning it off happens at once.',
        10,
        "briefing-settings",
        "desktop",
        indent=10,
        has_detail=True),
    SettingRow(
        "notif-alarms",
        "pc_alarm_sounds",
        "notif-alarms-row",
        "",
        "",
        'Alarms and urgent alerts',
        'Alarms and urgent "tell me when" alerts ring until dismissed. They break through Windows Focus Assist so you do not miss them.',
        11,
        "notifications",
        "desktop",
        indent=8,
        has_detail=True,
        checked=True),
    SettingRow(
        "notif-reminders",
        "pc_reminder_sounds",
        "notif-reminders-row",
        "",
        "",
        'Reminders, timers and to-dos',
        'Timers, reminders and to-do items chime once when they are due and offer Snooze.',
        12,
        "notifications",
        "desktop",
        indent=8,
        has_detail=True,
        checked=True),
    SettingRow(
        "notif-briefing",
        "pc_briefing_notification",
        "notif-briefing-row",
        "",
        "",
        'Morning briefing',
        'Tells you when your morning briefing is ready to read in the Brain.',
        13,
        "notifications",
        "desktop",
        indent=8,
        has_detail=True,
        checked=True),
    SettingRow(
        "notif-handoff",
        "pc_handoff_notification",
        "notif-handoff-row",
        "",
        "",
        'Website needs you (Solve it here)',
        'Tells you when a website or support chat pauses at a captcha or sign-in page.',
        14,
        "notifications",
        "desktop",
        indent=8,
        has_detail=True,
        checked=True),
    SettingRow(
        "notif-quiet-enabled",
        "pc_quiet_hours",
        "notif-quiet-row",
        "",
        "",
        'Turn on quiet hours',
        "",
        15,
        "notifications",
        "desktop",
        indent=8,
        span_on_own_line=True),
    SettingRow(
        "hud-open-bar-show",
        None,
        "",
        "",
        "hud-open-bar-detail",
        'Show the "Open the Jarvis bar" button',
        (
        "On: the button sits beside the big window's own chat box, and\n"
        'opens the Jarvis bar ready to type. Off: the button is not drawn\n'
        'there. The chat box, its Send and the microphone button are\n'
        'unchanged, and Alt+Space still opens the Jarvis bar.\n'),
        16,
        "hud-window",
        "desktop",
        indent=8,
        has_detail=True),
    SettingRow(
        "sec-app-lock",
        None,
        "",
        "",
        "sec-app-lock-detail",
        'App lock',
        '',
        17,
        "security",
        "desktop",
        indent=8,
        has_detail=True,
        fallback=True),
    SettingRow(
        "sec-private",
        None,
        "",
        "",
        "sec-private-detail",
        'Windows Hello for memory lists and chat history',
        '',
        18,
        "security",
        "desktop",
        indent=8,
        has_detail=True,
        fallback=True),
    SettingRow(
        "cv-face-switch",
        "voice_follows_face",
        "",
        "cv-face-title",
        "cv-face-detail",
        'Voice follows the face',
        '',
        19,
        "voices",
        "desktop",
        indent=12,
        has_detail=True,
        fallback=True),
    SettingRow(
        "cv-better-switch",
        "better_voice",
        "",
        "",
        "",
        'Make custom voices on the second graphics card',
        'A more natural copy of the voice. Turning it on shows you an approval card first; turning it off happens at once.',
        20,
        "voices",
        "desktop",
        indent=12,
        has_detail=True),
    SettingRow(
        "ws-enabled",
        "web_search",
        "",
        "ws-enabled-label",
        "ws-enabled-detail",
        'Web search',
        '',
        21,
        "web-search",
        "desktop",
        indent=10,
        has_detail=True,
        fallback=True),
    SettingRow(
        "ws-ask",
        "ask_before_every_search",
        "",
        "ws-ask-label",
        "ws-ask-detail",
        'Ask before every web search',
        '',
        22,
        "web-search",
        "desktop",
        indent=10,
        has_detail=True,
        fallback=True),
    SettingRow(
        "spd-accept",
        None,
        "spd-accept-wrap",
        "spd-accept-text",
        "",
        '',
        "",
        23,
        "spending",
        "desktop",
        indent=12,
        input_open='<input type="checkbox" id="spd-accept" />',
        label_span_inline=True,
        label_span_is_wrapper=True,
        setting_row=False,
        hidden=True),
    SettingRow(
        "sp-switch",
        "screen_picture",
        "",
        "sp-switch-label",
        "",
        'Turn on Picture mode (slow)',
        "",
        24,
        "screen-look",
        "desktop",
        indent=10,
        label_span_is_wrapper=True),
    SettingRow(
        "be-switch",
        "headless_browser",
        "",
        "be-switch-label",
        "",
        'Let Jarvis use the windowless browser (Obscura)',
        "",
        25,
        "browser-engine",
        "desktop",
        indent=10,
        label_span_is_wrapper=True),
    SettingRow(
        "supervise",
        None,
        "",
        "",
        "",
        'Let Jarvis Desktop start and stop Jarvis',
        "",
        26,
        "start-jarvis",
        "desktop",
        indent=10),
    SettingRow(
        "autostart",
        None,
        "",
        "",
        "",
        'Start Jarvis Desktop when Windows starts',
        "",
        27,
        "more-options",
        "desktop",
        indent=10),
    # "Making pictures" (the owner's decision of 2026-09-27; pictures.patch,
    # JARVIS-API section 129). The one switch that belongs to the Pictures card
    # and, with the record button above it, the one row on the page whose
    # subject is a whole feature rather than a behaviour. It is linked to its
    # BoolSetting (`pictures`), so "turn on making pictures" and this row are
    # the same switch through the same function.
    #
    # The words are NOT a fallback: `set_pictures` answers in its own sentence
    # and the paragraph above the row carries the PC's own state line, but the
    # row's own label is this page's, always.
    SettingRow(
        "pc-switch",
        "pictures",
        "",
        "pc-switch-label",
        "",
        'Making pictures',
        "",
        28,
        "pictures",
        "desktop",
        indent=10,
        label_span_is_wrapper=True),
    # "Data and maths sandbox" (LM-1C, 2026-10-18). The row's own label is this
    # page's; the state line under it is the PC's (GET /api/sandbox), so both
    # apps show the same sentence and the same card result. The row is last on
    # the page and sits in its own card, id="sandbox".
    SettingRow(
        "sbx-switch",
        "sandbox_exec",
        "",
        "sbx-switch-label",
        "",
        'Let Jarvis run small Python scripts for sums and averages',
        "",
        29,
        "sandbox",
        "desktop",
        indent=10,
        label_span_is_wrapper=True),
    # ------------------------------------------------------------------
    #   The phone's own two rows. There is no desktop toggle for
    #   either, so they are never spliced into settings.html; the
    #   phone reads their words from SettingsCatalog.kt. `source`
    #   records the Kotlin the words were copied from, so the two can
    #   be compared by eye - nothing checks it automatically.
    # ------------------------------------------------------------------
    SettingRow(
        dom_id="watch-notify",
        setting="smartwatch_notifications",
        row_id="",
        label_span_id="",
        detail_span_id="",
        label='Show notifications on a compatible watch',
        detail='Off by default: every notification (approval cards, timers, reminders, "tell me when") stays on this phone only.',
        order=1,
        indent=8,
        section="watch-notify",
        owner="phone",
        phone_key="watch-notify",
        source="WatchNotifyPlate.kt:87-90",
    ),
    SettingRow(
        dom_id="phone-notify",
        setting="phone_notifications",
        row_id="",
        label_span_id="",
        detail_span_id="",
        label='Let your phone read notifications',
        detail='Off by default. Jarvis never sees a phone notification unless you turn this on AND add at least one app below.',
        order=2,
        indent=8,
        section="phone-notify",
        owner="phone",
        phone_key="phone-notify",
        source="PhoneNotificationsPlate.kt:107-110",
    ),
    # "Data and maths sandbox" (LM-1C, 2026-10-18): the phone's own row, drawn
    # by SandboxPlate.kt from the SAME answer as the desktop's card.
    SettingRow(
        dom_id="sandbox",
        setting="sandbox_exec",
        row_id="",
        label_span_id="",
        detail_span_id="",
        label='Data and maths sandbox',
        detail='Off by default. Let the AI model run a small Python script for sums, averages and percentages, in its own sandbox with no network and no file writes. Turning it on asks first.',
        order=3,
        indent=8,
        section="sandbox",
        owner="phone",
        phone_key="sandbox",
        source="SandboxPlate.kt:120-126",
    ),
)

#: The rows that belong on the desktop page, in page order.
DESKTOP_ROWS: tuple = tuple(r for r in SETTINGS_ROWS if r.owner == "desktop")

#: dom id -> row, for a direct lookup.
_ROWS_BY_ID = {r.dom_id: r for r in SETTINGS_ROWS}


def setting_row(dom_id: str) -> Optional[SettingRow]:
    return _ROWS_BY_ID.get(dom_id)


# --------------------------------------------------------------------------
#   The plain, simple on/off settings: one alias table, one setter each.
#   jarvis_quick.py's grammar looks a name up here, then calls `set`.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BoolSetting:
    key: str
    names: tuple
    #: The matching SECTIONS id, for a future "open" alias - or None: the
    #: two learning switches live in the Brain window's Memory tab (`brain.
    #: html#memory-auto`, jarvis-desktop/src/auto-learn.js), a different
    #: navigation surface from settings.html's anchors, which SECTIONS and
    #: "open" only reach today. Not read by any code yet - kept accurate
    #: rather than wired to a place that does not exist, so a later "open
    #: the Brain" pass has the right answer already written down.
    section: Optional[str]
    set: Callable[..., Outcome] = field(repr=False)
    #: What each state is called, for "is background learning on?" - not
    #: built yet (open question for a later pass); kept here so the table
    #: is the one place that would grow it.
    on_word: str = "on"
    off_word: str = "off"


BOOL_SETTINGS: tuple = (
    BoolSetting("background_learning",
               ("background learning", "automatic learning", "learn automatically",
                "learning automatically"),
               None, set_background_learning),
    BoolSetting("learn_sensitive_topics",
               ("remembering sensitive topics automatically",
                "also remember sensitive topics automatically",
                "sensitive topics automatically", "auto-remembering sensitive topics"),
               None, set_learn_sensitive),
    BoolSetting("lights_without_card",
               ("lights without asking", "lights, plugs and fans without a card",
                "lights without a card", "switching lights without asking"),
               "asks-first", set_lights_without_card),
    BoolSetting("prompt_coach",
               ("prompt coach", "the prompt coach", "prompt coaching",
                "coaching my prompts"),
               "prompt-coach", set_prompt_coach),
    BoolSetting("ask_before_every_search",
               ("asking before every web search", "ask before every search",
                "asking before every search"),
               "web-search", set_ask_every_search),
    BoolSetting("web_search",
               ("web search", "searching the web", "the web search", "web searching",
                "searching the internet"),
               "web-search", set_web_search),
    BoolSetting("smartwatch_notifications",
               ("smartwatch notifications", "watch notifications",
                "notifications on my watch"),
               "watch-notify", set_watch_notify),
    BoolSetting("phone_notifications",
               ("phone notifications", "reading phone notifications",
                "notifications on my phone"),
               "phone-notify", set_phone_notifications),
    BoolSetting("screen_picture",
               ("picture mode", "picture mode for my screen", "reading pictures of my screen",
                "looking at pictures of my screen"),
               "screen-look", set_screen_picture),
    BoolSetting("headless_browser",
               ("the headless browser", "headless browser", "obscura", "the obscura browser",
                "the browser with no window"),
               "browser-engine", set_browser_engine),
    # "The data and maths sandbox" (LM-1, 2026-10-18). The ONE tool whose
    # switch is its own rather than a line in [tools].enabled: default OFF, and
    # ON is one normal change_own_config card. Its `section` is the Settings
    # card that draws the switch (the owner approved a real control on
    # 2026-10-22; the feature guide maps "is the sandbox on?" to it).
    BoolSetting("sandbox_exec",
               ("the data sandbox", "data sandbox", "the data and maths sandbox",
                "the python sandbox", "the small python sandbox", "the sandbox",
                "small python scripts", "the data and maths tool"),
               "sandbox", set_sandbox_exec),
    # "Searchable recordings and videos" (F5 S2, the owner's decision of
    # 2026-10-19: readable transcript text, ON by default). Its switch is the
    # shipped `[media_index] enabled = true`; the owner's own file wins, so OFF
    # is instant, and turning it back ON is one normal card (set_media_index,
    # above). The desktop's Settings card is the hand-written panel in
    # `media-index` (disclosure, switch and one Delete); the phone has no card
    # yet (ARCHITECTURE section 8 records that follow-up honestly).
    BoolSetting("media_index",
               ("searchable recordings", "the recording index", "the media index",
                "searchable media", "the recordings index", "searchable videos",
                "recording and video search", "search my recordings"),
               "media-index", set_media_index),
    # "Making pictures" (the owner's decision of 2026-09-27; pictures.patch,
    # JARVIS-API section 129). Its own switch, OFF by default: the second card
    # is shared with the everyday model, and CLAUDE.md's rule is that a feature
    # using the second card stays off until THAT feature is measured. Both
    # directions happen at once - see set_pictures above for why that is not a
    # loosening.
    BoolSetting("pictures",
               ("making pictures", "making pictures on the pc", "the picture maker",
                "drawing pictures", "asking for a picture"),
               "pictures", set_pictures),
    BoolSetting("briefing_senders",
               ("senders in my briefing", "showing senders in my briefing",
                "email senders in the morning briefing"),
               "briefing-settings", set_briefing_senders),
    # The 30B coder (2026-10-11, the owner asked for it by name). OFF by
    # default; turning it ON is ONE card (change_own_config), OFF is instant.
    # It is the one model here that needs BOTH cards, so it pauses the two
    # live lanes and puts them back when it stops - jarvis_big_coder.py.
    BoolSetting("big_coder",
               ("the big coding model", "the big coder", "the 30B coder",
                "the thirty billion coder", "the coder for big jobs"),
               None, set_big_coder),
    # --- the eight that used to be reachable only by opening Settings
    # (2026-10-13). Each already had a route and a tier; this adds the phrase
    # and nothing else. The `section` is the Settings card the owner is sent
    # to by "open ...", so a person can still finish the job by hand.
    BoolSetting("pc_alarm_sounds",
               ("alarm sounds", "the alarm sound", "alarms and urgent alerts",
                "notifications for alarms", "pc alarm sounds"),
               "notifications", set_pc_alarm_sounds),
    BoolSetting("pc_reminder_sounds",
               ("reminder sounds", "the reminder sound", "reminder chimes",
                "notifications for reminders", "reminders timers and to-dos"),
               "notifications", set_pc_reminder_sounds),
    BoolSetting("pc_briefing_notification",
               ("the briefing notification", "briefing notifications",
                "notify me when the briefing is ready",
                "the morning briefing notification"),
               "notifications", set_pc_briefing_notification),
    BoolSetting("pc_handoff_notification",
               ("the website needs me notification", "website needs you",
                "notifications when a website needs me",
                "the solve it here notification"),
               "notifications", set_pc_handoff_notification),
    BoolSetting("pc_quiet_hours",
               ("quiet hours", "the quiet hours", "quiet hours on the pc",
                "the pc's quiet hours"),
               "notifications", set_pc_quiet_hours),
    # "Occasional light humour in answers" (settings.html id="mn-humor").
    # Wording only: it never changes what Jarvis does, so no card either way.
    BoolSetting("humor",
               ("humour", "humor", "light humour", "light humor",
                "jokes in your answers", "the humour switch"),
               "manner", set_humor),
    # "Voice follows the face" (settings.html id="cv-face-switch"): a face may
    # pick its own voice. Cosmetic, at once, no card.
    BoolSetting("voice_follows_face",
               ("voice follows the face", "the voice follows the face",
                "voice follows my face", "the face voice"),
               "voices", set_voice_follows_face),
    # "Make custom voices on the second graphics card" (id="cv-better-switch").
    # OFF at once; ON is its OWN card (better_voice_enable) - kept exactly.
    BoolSetting("better_voice",
               ("the better voice", "the better custom voice",
                "custom voices on the second card",
                "make custom voices on the second graphics card"),
               "voices", set_better_voice),
    # --- the universal-control pass (2026-10-22): switches that had a real
    # route/control but no spoken name. See the setters above; every section
    # is the Settings card that already draws the control.
    BoolSetting("chat_history",
               ("chat history", "keeping chat history", "saving my chats",
                "my conversation history", "keeping conversations"),
               None, set_chat_history),
    BoolSetting("write_like_me",
               ("write like me", "the write like me switch", "my writing voice",
                "the writing style profile", "voiceprint", "my voiceprint"),
               None, set_write_like_me),
    BoolSetting("big_model",
               ("the big model", "the big slow model", "the big model on this pc"),
               "big-model", set_big_model),
    BoolSetting("big_model_wiki",
               ("the big model for the wiki builder", "the wiki builder on the big model",
                "the big model wiki builder"),
               "big-model", set_big_model_wiki),
    BoolSetting("big_model_deep_questions",
               ("the big model for deep questions", "deep questions on the big model",
                "the big model's deep questions"),
               "big-model", set_big_model_deep_questions),
    BoolSetting("second_card_combined",
               ("one bigger model on both cards", "the bigger model on both cards",
                "combining the two cards", "the combined model setting"),
               "second-card", set_second_card_combined),
    BoolSetting("second_card_suggest_struggle",
               ("bigger model suggestions when i am struggling",
                "suggesting a bigger model when i struggle",
                "the struggle suggestion for a bigger model"),
               "second-card", set_second_card_suggest_struggle),
    BoolSetting("second_card_suggest_correction",
               ("bigger model suggestions after a correction",
                "suggesting a bigger model after i correct you",
                "the correction suggestion for a bigger model"),
               "second-card", set_second_card_suggest_correction),
)

_BOOL_BY_NAME = {_bare(name): b for b in BOOL_SETTINGS for name in b.names}


def find_bool_setting(words: str):
    return _BOOL_BY_NAME.get(_bare(words))


# --------------------------------------------------------------------------
#   The same table, read by the AI MODEL's own wording (2026-10-13).
# --------------------------------------------------------------------------

#: Filler a MODEL puts around a setting's real name. ONLY
#: `find_bool_setting_words` below strips these. The spoken grammar must keep
#: using `find_bool_setting` above, which is an exact alias match on purpose:
#: a half-heard or half-typed sentence must fall through rather than change a
#: switch the owner did not name.
_SETTING_NOISE = frozenset({
    "a", "an", "the", "my", "our", "your", "please", "jarvis", "setting",
    "settings", "option", "feature", "control", "switch", "toggle", "thing",
    "for", "to", "of", "in", "is", "it", "and", "or", "current", "currently",
})


def _setting_words(words: str) -> str:
    """`words` lower-cased, punctuation dropped, filler removed - the one form
    the alias table and the model's own wording are both compared in."""
    text = re.sub(r"[^a-z0-9 ]+", " ", str(words or "").lower())
    return " ".join(w for w in text.split() if w and w not in _SETTING_NOISE)


def _one_setting(keys) -> Optional["BoolSetting"]:
    """The single BoolSetting `keys` names, or None when that is not exactly
    one. An ambiguous name is REFUSED, never guessed at: changing a switch the
    owner did not name is worse than changing nothing."""
    if len(keys) != 1:
        return None
    key = next(iter(keys))
    return next((b for b in BOOL_SETTINGS if b.key == key), None)


def find_bool_setting_words(words: str) -> Optional["BoolSetting"]:
    """The ONE plain on/off setting `words` names, or None.

    FOR THE AI MODEL'S OWN WORDING, and never for the spoken grammar - see
    `_SETTING_NOISE` above. `find_bool_setting` is an exact alias match on
    purpose: it runs on a sentence a person spoke or typed, and a near miss
    there must fall through rather than change a switch nobody named. A model
    has no such excuse - it is told which settings exist and restates one in
    its own words ("stop showing me notifications on my watch") - so this
    ignores case, punctuation and that filler, and then accepts an answer ONLY
    while it stays unambiguous:

      1. the stripped words ARE a stripped alias, exactly; else
      2. the request CONTAINS every word of one alias - one direction only, and
         see the comment on the rule itself for the false positives that the
         other direction produced and why they were unacceptable.

    `None` means "no single setting is named", which the caller answers in
    words (see `cannot_change_setting_words`). Deliberately NOT a fuzzy score:
    a near miss must refuse, because the one thing this must never do is change
    a switch the owner did not ask for (2026-10-13)."""
    text = _setting_words(words)
    if not text:
        return None
    exact: dict = {}
    for b in BOOL_SETTINGS:
        for name in b.names:
            exact.setdefault(_setting_words(name), set()).add(b.key)
    if text in exact:
        return _one_setting(exact[text])
    if len(text.split()) < 2:
        # One bare word ("notifications", "sounds") names no ONE switch among
        # these, and guessing which is exactly the failure to avoid.
        return None
    theirs = set(text.split())
    # ONE rule, in ONE direction, and the direction is the whole safety of it
    # (2026-10-13). The request must CONTAIN a whole alias's words, so "stop
    # showing me notifications on my watch" reaches "watch notifications": the
    # request is MORE specific than the name, which is what a person restating a
    # setting does.
    #
    # THE OTHER DIRECTION WAS TRIED AND REMOVED, and this is why. "Every word of
    # the request fits inside one alias" also matched bare category nouns against
    # longer names, and every one of these reads as a switch that has nothing to
    # do with the words:
    #     "graphics card" / "second card"  -> better_voice
    #     "pc sounds"                      -> pc_alarm_sounds
    #     "screen mode"                    -> screen_picture
    #     "the big model"                  -> big_coder
    # The exact spoken matcher above returns None for all four. Worse, those
    # switches apply with NO card, so a phrase naming no setting at all would
    # have flipped a switch the owner never named - the one outcome this whole
    # function exists to prevent. A phrase that names no single setting must be
    # refused, never guessed at; backend/test_settings_tool.py keeps all four as
    # regression cases.
    found: set = set()
    for b in BOOL_SETTINGS:
        for name in b.names:
            mine = set(_setting_words(name).split())
            if mine and mine <= theirs:
                found.add(b.key)
                break
    return _one_setting(found)


def cannot_change_setting_words(words: str = "") -> str:
    """What Jarvis says when a setting it cannot change is named - never a
    claim that it was changed.

    Two shapes, because there are two kinds of "cannot": a switch that IS on
    the Settings page but has no route at all (`NOT_BY_ASKING`, which names the
    screen and the row), and everything else, which gets the list of what can
    be changed. The model is meant to pass this answer on as it stands."""
    asked = " ".join(str(words or "").split())[:80]
    lead = (f'I cannot change "{asked}" by asking.' if asked
            else "I cannot change that by asking.")
    dom_id = find_not_by_asking(words or "")
    if dom_id is not None:
        return f"{lead} {not_by_asking_sentence(dom_id)}"
    return f"{lead} {changeable_words()}"


# --------------------------------------------------------------------------
#   Settings a chat turn CANNOT change yet, and the sentence that says so
#   (2026-10-13). THE DEFECT THIS FIXES: a settings request that matched no
#   phrase used to go to the AI model, which has no settings tool and is never
#   told it cannot - so "the failure looks like success". Every name below is
#   answered in words instead, and nothing is changed.
#
#   THE TEN NAMES ARE THE ONES WITH NO ROUTE AT ALL. Each is a real switch on
#   the desktop's Settings page whose value is kept by the DESKTOP APP (a
#   Tauri command, or `localStorage`), so this backend has no function to call
#   and a phrase alone could not work. Checked one by one: no `/api/theme`,
#   `/api/security`, `/api/autostart`, `/api/supervis*`, `hud_open_bar` or
#   `click_through` route exists in this backend.
#
#   NOT INCLUDED, deliberately, and this is the trap: "Show the sun and moon
#   behind the face" (`sky-show`) and "Auto adjust" (`face-auto`) ALSO have no
#   BoolSetting, but both ARE reachable by asking through the animal and sky
#   grammars (jarvis_quick._animal) - listing them here would take a working
#   phrase away. `spd-accept` is not a preference at all.
# --------------------------------------------------------------------------

#: `SETTINGS_ROWS` id -> the words the owner might use for it. Keyed by id so
#: the label and the Settings place come from the one table above.
NOT_BY_ASKING: dict = {
    "sec-app-lock": ("app lock", "the app lock"),
    "sec-private": ("windows hello for memory lists",
                    "windows hello for memory lists and chat history",
                    "hello for memory lists"),
    "floating-enabled": ("floating face", "the floating face"),
    "floating-click-through": ("click through", "click through to what is behind",
                               "click-through"),
    "follow-system": ("match windows light or dark mode", "follow windows light or dark mode",
                      "windows light or dark mode", "follow the windows theme"),
    "voice-one-moment": ("the one moment sound", "say one moment if i am kept waiting",
                         "the one moment message"),
    "voice-heard-sound": ("the i heard you sound", "i heard you sound",
                          "the short sound when i finish speaking",
                          "the listening sound"),
    "hud-open-bar-show": ("the open the jarvis bar button", "the jarvis bar button"),
    "supervise": ("let jarvis desktop start and stop jarvis", "desktop supervision",
                  "supervision"),
    "autostart": ("autostart", "auto start", "start jarvis when windows starts",
                  "start with windows", "run at startup", "start at login"),
}


def find_not_by_asking(words: str) -> Optional[str]:
    """The `SETTINGS_ROWS` id `words` names exactly and cannot be changed by
    asking, or None. Exact names only, like everything else here."""
    bare = _bare(words)
    for dom_id, names in NOT_BY_ASKING.items():
        if any(bare == _bare(n) for n in names):
            return dom_id
    return None


def not_by_asking_sentence(dom_id: str) -> str:
    """What Jarvis says instead of pretending. One sentence, plain words, and
    the exact place to change it by hand - never a claim that it was done."""
    row = setting_row(dom_id)
    label = row.label if row is not None and row.label else "that setting"
    where = "Settings"
    if row is not None:
        sec = section_by_id(row.section)
        if sec is not None and sec.names:
            where = f"Settings, {sec.names[0]}"
    return (f"That one lives in {where} on your PC and I cannot change it by "
            f"asking yet - open it and it is \"{label}\".")


# --------------------------------------------------------------------------
#   Approval cards read short (the owner's request of 2026-10-09): "a more
#   simple summary, with an explain more button ... and approval card
#   preferences such as this should be changeable in the settings".
#
#   A CHOICE of two, not an on/off, so it is NOT a BoolSetting: "Start short"
#   (the default) or "Always show everything". Both are cosmetic and both are
#   at once, with no card - this changes which words a card draws and nothing
#   else: it approves nothing, starts nothing and reaches nothing. So there is
#   no direction that asks, and the PC-only rule for loosenings does not apply.
#
#   THE SAME FUNCTION THE APP'S OWN SWITCH CALLS (jarvis_card_summary.set_mode),
#   through the one route, so a spoken change and a tap cannot take two
#   different paths. words -> mode is jarvis_card_summary.spoken, which never
#   guesses: an unrecognised phrase answers None and the caller says so.
# --------------------------------------------------------------------------


def find_card_mode(words: str) -> Optional[str]:
    """The display mode `words` names exactly (jarvis_card_summary's own list -
    never typed twice here), or None."""
    try:
        import jarvis_card_summary as CS
    except Exception:
        return None
    return CS.spoken(words)


def set_card_mode(mode: str, *, peer=None, local=None) -> Outcome:
    """At once, from either app or by asking - cosmetic, so no card either way.
    The same jarvis_card_summary.set_mode POST /api/card-prefs calls."""
    try:
        import jarvis_card_summary as CS
    except Exception:
        return _missing("the approval card setting")
    code, out = CS.set_mode(mode)
    return _say(code, out)


# --------------------------------------------------------------------------
#   Settings with MORE THAN TWO choices (2026-10-22, the owner's "every
#   function or feature ... can be turned on, off or adjusted by typing").
# --------------------------------------------------------------------------
#
# The same second-door rule as BOOL_SETTINGS: a phrase resolves to a table
# row, and the row's setter calls the EXACT function the Settings control (or
# its own route handler, when the gating lives there) already calls. A change
# that loosens a rule still raises the card that control raises; a change the
# PC-only rule refuses is still refused; nothing here invents a tier.
#
# VALUES ARE NAMED, NOT GUESSED. Each row maps the words a person says to the
# value the existing function takes. An unrecognised value does NOT fall
# through to the model: jarvis_quick answers settings_choice_bad and says the
# options, so the owner is never told a change happened that did not. A row
# whose choices are read from a module (the voices pack, the presets) asks
# that module at match time, so a new voice or preset appears without editing
# this file.

def _choices_now(choices) -> dict:
    """The spoken->value map for a row: its dict, or a callable's answer.

    A module missing on an older PC gives {} - the name still resolves (so the
    answer can say the setting is not there) but no value can be accepted."""
    if callable(choices):
        try:
            got = choices()
        except Exception:
            return {}
        return dict(got or {})
    return dict(choices or {})


@dataclass(frozen=True)
class ChoiceSetting:
    """One setting whose value is a name from a real list (2+ choices)."""

    key: str
    #: What a person may call the setting. Exact aliases only, like a switch.
    names: tuple
    #: The SECTIONS id whose card draws the control, or None (Brain/History).
    where: Optional[str]
    #: Spoken value -> the value the existing function takes. A dict, or a
    #: callable returning one (read fresh, so new voices/presets appear).
    choices: object
    #: Calls the exact existing function; (value, *, peer, local) -> Outcome.
    set: Callable[..., Outcome] = field(repr=False)
    #: One line for "what can I change?" - never used to dispatch.
    describe: str = ""

    def options(self) -> dict:
        """The spoken->value map, keys normalized the way speech arrives.

        jarvis_quick lower-cases a sentence before this file sees it, and a
        label or id may carry capital letters or a leading "the"; normalizing
        both sides HERE is what keeps "set the built-in voice to Heart" and
        the row's own "American (female) - Heart" the same choice."""
        return {_choice_key(key): value
                for key, value in _choices_now(self.choices).items()}

    def option_words(self) -> str:
        return ", ".join(sorted(set(self.options().keys())))


def _voice_speed_choices() -> dict:
    return {"slower": "slower", "slow": "slower",
            "normal": "normal", "normal speed": "normal",
            "faster": "faster", "fast": "faster"}


def _voice_speaker_choices() -> dict:
    """The voices pack's own list, by name and by label - never typed twice."""
    try:
        import jarvis_voices as JV
        view = JV.speaker_view()
    except Exception:
        return {}
    out = {}
    for row in view.get("choices") or ():
        if not isinstance(row, dict):
            continue
        pid = str(row.get("id") or "").strip()
        if not pid:
            continue
        out[pid] = pid
        label = str(row.get("label") or "").strip()
        if label:
            out[_bare(label)] = pid
        accent = str(row.get("accent") or "").strip()
        if accent:
            out[_bare(f"{label} {accent}")] = pid
    return out


def _preset_choices() -> dict:
    """The focus presets' own ids and titles, read from jarvis_presets."""
    try:
        import jarvis_presets as JP
        rows = JP.PRESETS
    except Exception:
        return {}
    out = {}
    for preset in rows:
        pid = str(getattr(preset, "id", "") or "").strip()
        if not pid:
            continue
        out[pid] = pid
        title = str(getattr(preset, "title", "") or "").strip()
        if title:
            out[_bare(title)] = pid
            out[_bare(f"{title} preset")] = pid
    return out


def _set_handoff_mode(mode: str) -> Outcome:
    try:
        import jarvis_handoff_mode as HM
    except Exception:
        return _missing("the captcha hand-off setting")
    code, out = HM.request(mode)
    return _say(code, out)


def set_handoff_mode(value: str, *, peer=None, local=None) -> Outcome:
    return _set_handoff_mode(str(value))


def _set_handoff_front(mode: str) -> Outcome:
    try:
        import jarvis_handoff_front as HF
    except Exception:
        return _missing("the captcha window setting")
    code, out = HF.request(mode)
    return _say(code, out)


def set_handoff_front(value: str, *, peer=None, local=None) -> Outcome:
    return _set_handoff_front(str(value))


def set_voice_speed(value: str, *, peer=None, local=None) -> Outcome:
    """The same `jarvis_voices.set_speed` POST /api/voice/voices/speed calls."""
    try:
        import jarvis_voices as JV
    except Exception:
        return _missing("the voice speed")
    code, out = JV.set_speed({"speed": str(value)})
    return _say(code, out)


def set_voice_speaker(value: str, *, peer=None, local=None) -> Outcome:
    """The same `jarvis_voices.set_speaker` the voices page's picker calls."""
    try:
        import jarvis_voices as JV
    except Exception:
        return _missing("the built-in voice")
    code, out = JV.set_speaker({"speaker": str(value)})
    return _say(code, out)


def set_focus_preset(value: str, *, peer=None, local=None) -> Outcome:
    """The same `jarvis_presets.apply_from_body` POST /api/work/apply calls -
    including its ONE switch_model card and its rollback."""
    try:
        import jarvis_presets as JP
    except Exception:
        return _missing("the focus presets")
    code, out = JP.apply_from_body({"preset": str(value)})
    return _say(code, out)


CHOICE_SETTINGS: tuple = (
    ChoiceSetting(
        "handoff_mode",
        ("the captcha hand-off", "the handoff", "the hand-off",
         "the hand-off when my phone does not answer", "handoff mode"),
        "handoff", {"stop early": "stop_early", "stop_early": "stop_early",
                    "quick": "stop_early",
                    "keep offering": "keep_offering",
                    "keep offering it": "keep_offering",
                    "keep_offering": "keep_offering",
                    "patient": "keep_offering",
                    "15 minutes": "keep_offering",
                    "fifteen minutes": "keep_offering"},
        set_handoff_mode,
        "how long the captcha hand-off stays on offer (stop early or 15 minutes)"),
    ChoiceSetting(
        "handoff_front",
        ("the captcha window", "the hand-off window", "the handoff window",
         "the captcha window in front"),
        "handoff-front", {"leave it where it is": "leave_in_place",
                          "leave it in place": "leave_in_place",
                          "leave_in_place": "leave_in_place",
                          "where it is": "leave_in_place",
                          "bring it to the front": "bring_to_front",
                          "bring to the front": "bring_to_front",
                          "bring_to_front": "bring_to_front",
                          "in front": "bring_to_front"},
        set_handoff_front,
        "whether a captcha brings its window to the front"),
    ChoiceSetting(
        "voice_speed",
        ("the voice speed", "how fast jarvis speaks", "jarvis's speed",
         "the speed of the voice"),
        "voice", _voice_speed_choices, set_voice_speed,
        "how fast Jarvis speaks (slower, normal, faster)"),
    ChoiceSetting(
        "voice_speaker",
        ("the built-in voice", "which voice jarvis uses", "jarvis's built-in voice",
         "the voice jarvis speaks with", "the voice"),
        "voices", _voice_speaker_choices, set_voice_speaker,
        "which built-in voice Jarvis speaks with"),
    ChoiceSetting(
        "personality",
        ("the personality", "the persona", "jarvis's personality",
         "the character", "which personality"),
        "manner", _personality_choices, set_personality,
        "which of the eight personalities Jarvis speaks in (no card)"),
    ChoiceSetting(
        "focus_preset",
        ("the focus preset", "jarvis's preset", "the model preset",
         "which preset jarvis uses"),
        "focus-presets", _preset_choices, set_focus_preset,
        "which focus preset Jarvis runs (each apply raises its one card)"),
)


def find_choice_setting(words: str):
    """The ChoiceSetting `words` names exactly, or None (never a guess)."""
    bare = _bare(words)
    for setting in CHOICE_SETTINGS:
        if any(bare == _bare(name) for name in setting.names):
            return setting
    return None


def choice_from_words(setting: ChoiceSetting, words: str):
    """The value `words` names in this setting's own list, or None."""
    return setting.options().get(_choice_key(words))


# --------------------------------------------------------------------------
#   The closed (control, field) vocabulary for the ONE generic grammar
#   (Gemini ruling Q3, 2026-10-22): "set <control> <field> to <value>" /
#   "change ...". A pair here maps to the SAME ChoiceSetting (and therefore the
#   same existing setter, card, tier and PC-only gate) the Settings control
#   calls. There is no second mutation path: the handler stores nothing but
#   calls ChoiceSetting.set.
#
#   The grammar is CLOSED-WORLD: a control or field not in this table falls
#   through exactly as before; a control that is named with a missing or
#   ambiguous field, or a value not in its list, is answered deterministically
#   (list the fields / the valid values / the current values) and is NEVER
#   handed to the model.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ControlField:
    """One field of one multi-field control (a name for an existing choice)."""

    field: str          # the word the owner says for the field
    setting: ChoiceSetting
    aliases: tuple = ()


def _choice(key: str) -> ChoiceSetting:
    for choice in CHOICE_SETTINGS:
        if choice.key == key:
            return choice
    raise KeyError(key)


#: control -> its field rows, in the order the clarifying question lists them.
CONTROL_FIELDS: dict = {
    "voice": (
        ControlField("speed", _choice("voice_speed"),
                     ("speed", "speaking speed", "how fast", "pace")),
        ControlField("voice", _choice("voice_speaker"),
                     ("voice", "speaker", "built in voice", "built-in voice",
                      "which voice")),
    ),
    "captcha hand off": (
        ControlField("mode", _choice("handoff_mode"),
                     ("mode", "how long", "offer", "when")),
        ControlField("window", _choice("handoff_front"),
                     ("window", "front", "position")),
    ),
    "focus preset": (
        ControlField("preset", _choice("focus_preset"), ("preset",)),
    ),
}

#: The words a person may say for each control, longest first at match time.
CONTROL_NAMES = {
    "voice": ("the voice", "jarvis's voice", "jarvis voice", "voice"),
    "captcha hand off": ("the captcha hand-off", "the captcha handoff",
                         "the hand-off", "the handoff", "the captcha",
                         "captcha hand-off", "captcha handoff", "hand-off", "handoff"),
    "focus preset": ("the focus preset", "focus preset", "the model preset"),
}


def _norm_control(words: str) -> str:
    cleaned = " ".join(re.sub(r"[^a-z0-9]+", " ", str(words or "").lower()).split())
    return _LEAD_ARTICLE.sub("", cleaned)


#: Built once, longest alias first, so "captcha hand-off" wins over "captcha".
_CONTROL_ALIASES = sorted(
    ((_norm_control(alias), control)
     for control, aliases in CONTROL_NAMES.items() for alias in aliases),
    key=lambda pair: len(pair[0]), reverse=True)


def find_control(words: str):
    """`(control, remainder)` when `words` starts with a real control name.

    The alias must be a whole word prefix ("voice" in "voice speed ..." yes,
    "voicemail ..." no), and the longest alias wins. None when no control is
    named - the caller then falls through exactly as before."""
    text = _norm_control(words)
    for alias, control in _CONTROL_ALIASES:
        if text == alias:
            return control, ""
        if text.startswith(alias + " "):
            return control, text[len(alias):].strip()
    return None


def fields_for_control(control: str) -> tuple:
    return CONTROL_FIELDS.get(control, ())


def find_field(control: str, words: str):
    """`(ControlField, remainder)` when `words` starts with one of its fields."""
    text = _norm_control(words)
    for row in fields_for_control(control):
        names = sorted({_norm_control(row.field),
                        *(_norm_control(a) for a in row.aliases)},
                       key=len, reverse=True)
        for name in names:
            if not name:
                continue
            if text == name:
                return row, ""
            if text.startswith(name + " "):
                return row, text[len(name):].strip()
    return None


def resolve_control_sentence(control_words: str, value_words: str = None) -> dict:
    """Everything the generic handler needs to answer one sentence.

    `control_words` is the part before "to" ("voice speed", "the captcha
    hand-off", "voice"); `value_words` is the part after it, or None when the
    owner only said "adjust the voice".

    Returns one of:
      {"kind": "set",  "control", "field", "key", "value", "setting"}
      {"kind": "ask",  "control"}            - field/value missing or ambiguous
      {"kind": "bad",  "control", "field"}    - a named field's value is invalid
      {"kind": "invalid", "control", "value"} - value matches no field
      {"kind": "none"}                       - no control in the closed table
    Never guesses: two matching fields is "ask", zero is "invalid"."""
    found = find_control(control_words)
    if found is None:
        return {"kind": "none"}
    control, rest = found
    row = None
    if rest:
        by_field = find_field(control, rest)
        if by_field is not None:
            row, leftover = by_field
            if leftover and value_words is None:
                # "voice speed faster" with no "to": treat the leftover as the
                # value, exactly as the generic handler does with a "to" tail.
                value_words = leftover
    if value_words is None:
        return {"kind": "ask", "control": control}
    if row is not None:
        value = choice_from_words(row.setting, value_words)
        if value is None:
            return {"kind": "bad", "control": control, "field": row.field}
        return {"kind": "set", "control": control, "field": row.field,
                "key": row.setting.key, "value": value, "setting": row.setting}
    hits = []
    for candidate in fields_for_control(control):
        value = choice_from_words(candidate.setting, value_words)
        if value is not None:
            hits.append((candidate, value))
    if len(hits) == 1:
        candidate, value = hits[0]
        return {"kind": "set", "control": control, "field": candidate.field,
                "key": candidate.setting.key, "value": value,
                "setting": candidate.setting}
    if not hits:
        return {"kind": "invalid", "control": control, "value": value_words}
    return {"kind": "ask", "control": control}


def control_current_words(setting: ChoiceSetting) -> str:
    """The current value in plain words, or "I could not read it" - never a
    guess. Used by the clarifying question the ruling asks for."""
    key = setting.key
    try:
        if key == "handoff_mode":
            import jarvis_handoff_mode as HM
            mode = str((HM.view() or {}).get("mode") or "")
            return {"stop_early": "stop early",
                    "keep_offering": "keep offering it"}.get(mode, mode) or "unknown"
        if key == "handoff_front":
            import jarvis_handoff_front as HF
            mode = str((HF.view() or {}).get("mode") or "")
            return {"leave_in_place": "leave it where it is",
                    "bring_to_front": "bring it to the front"}.get(mode, mode) or "unknown"
        if key == "voice_speed":
            import jarvis_voices as JV
            return str((JV.speed_view() or {}).get("choice") or "normal")
        if key == "voice_speaker":
            import jarvis_voices as JV
            view = JV.speaker_view() or {}
            return str(view.get("label") or view.get("choice") or "unknown")
        if key == "focus_preset":
            import jarvis_presets as JP
            chosen = JP.choice()
            if not chosen:
                return "no preset chosen"
            row = JP.by_id(chosen)
            return str(getattr(row, "title", "") or chosen)
    except Exception:                       # noqa: BLE001 - said as unknown
        return "unknown"
    return "unknown"


def control_ask_words(control: str) -> str:
    """The deterministic clarifying question: valid fields + current values."""
    parts = []
    for row in fields_for_control(control):
        parts.append(f"{row.field} (currently {control_current_words(row.setting)})")
    listed = "; ".join(parts) if parts else "no fields"
    name = control
    return (f"Which part of {name} would you like to change? You can set: "
            f"{listed}.")


def control_bad_words(control: str, field: str) -> str:
    row = next((r for r in fields_for_control(control) if r.field == field), None)
    if row is None:
        return f"I do not have a field called {field} for {control}."
    options = sorted(row.setting.options().keys())
    return (f"That is not one of the values for {control}'s {field}. "
            f"Say one of: {', '.join(options)}.")


def control_invalid_words(control: str, words: str) -> str:
    rows = fields_for_control(control)
    if not rows:
        return f"I do not have fields for {control}."
    fields = "; ".join(r.field for r in rows)
    return (f"I did not recognise \"{words}\" as a value for {control}. "
            f"Its fields are: {fields}.")


#: The owner's two Settings-only exceptions (ruling Q3.3, 2026-10-22): typing
#: a change to them is refused in plain words with the Settings pointer - never
#: handed to the model, never a card.
SETTINGS_ONLY = {
    "accounts": ("That is Settings-only, by your decision: Accounts and API "
                 "keys are never typed or spoken. Open Settings, Accounts on "
                 "the PC."),
    "restore": ("Restore backup is Settings-only, by your decision: it "
                "replaces memory, chat history, settings and notes. Open "
                "Settings, Backups on the PC."),
}


def settings_only_words(which: str) -> str:
    return SETTINGS_ONLY.get(str(which or ""), SETTINGS_ONLY["accounts"])


def choice_bad_words(setting: ChoiceSetting) -> str:
    """The honest answer when the value is not one this setting has."""
    options = setting.option_words()
    if not options:
        return (f"{setting.names[0] if setting.names else setting.key} has no "
                "choices on this PC yet, so there is nothing to set it to.")
    return (f"That is not one of the choices for "
            f"{setting.names[0] if setting.names else setting.key}. "
            f"Say one of: {options}.")


# --------------------------------------------------------------------------
#   "What can I change?" (the owner's decision, 2026-10-10)
# --------------------------------------------------------------------------
#
# The owner asked to change every setting by talking to Jarvis. Most of the
# machinery was already here: BOOL_SETTINGS above is what "turn off web
# search" and ten more phrases act through, and each setting's own setter
# decides whether it needs a card. What was missing is that Jarvis could not
# TELL him what he may change - "what can I change?" reached the AI model and
# came back with an invention rather than this answer.
#
# This list is DERIVED from the tables above, never typed out again: a switch
# added to BOOL_SETTINGS (or to the asks-first or tool tables) appears here by
# itself, and one removed stops being offered. A second, hand-written list would
# drift from the real switches and nobody would notice - the exact trap this
# project keeps fixing.
#
# IT MUST NOT UNDERSTATE EITHER (fixed 2026-10-13). It used to offer the 13
# BOOL_SETTINGS alone, which told the owner he could change 13 things while
# about 45 were reachable by asking - so most of what worked looked like it did
# not, and he would not try it. The families whose tables live in other modules
# are counted from those modules (see `_OTHER_REACHABLE`) rather than omitted.
#
# The earlier note here said loosening settings were "deliberately NOT
# promised". That reasoning was wrong and is gone: a loosening IS reachable - it
# is reached and then raises its card. Omitting it told the owner he could not
# do something he can do. The answer now says plainly that a change which
# loosens a rule still shows a card first, which is the honest form of the same
# protection (rule 4). The pick-one settings (web search provider, weather
# source) do have phrasings today, so they are listed as the families they are.
#
# STILL NOT LISTED, on purpose:
#   * the secrets themselves - API keys, account passwords, the pairing token.
#     Those are set on the PC only and are never spoken or typed into a chat
#     (rule 3, and the registry's own "left out on purpose" list), so no phrase
#     reaches them and they do not belong here.
#   * a TOPIC's mode (learn / use / off, per topic, `set_topic_mode`). It is
#     reachable, but `jarvis_quick` opens its picker rather than acting on a
#     guessed topic, so the phrasing is not a plain one-liner. Listing it would
#     promise a sentence that needs a picker first - the same reason the
#     pick-one settings used to be held back.

#: Plain short words for what a section is about, so the answer reads like a
#: person talking rather than the Settings screen being read out. Only the
#: sections that can appear below need an entry.
SECTION_PLAIN = {
    "web-search": "the web search",
    "asks-first": "what asks first",
    "voice": "the voice",
    "animals": "the animal faces",
    "screen-look": "looking at the screen",
    "briefing-settings": "the morning briefing",
    "browser-engine": "the browser",
    "sandbox": "the data sandbox",
    "phone-notify": "phone notifications",
    "watch-notify": "watch notifications",
    "prompt-coach": "the prompt coach",
}

#: Settings a chat turn genuinely reaches whose own table lives OUTSIDE this
#: registry - so "derive it from the tables" alone cannot see them, and the
#: answer used to leave every one of them out.
#:
#: Each entry is one row of the answer:
#: `(plain words, group, how many settings, module that owns it)`.
#: The count is how many separate settings that row covers, so the answer can
#: state a truthful number without reading out 43 names. `-1` means "count it
#: from that module" (see `_family_count`), which is what keeps the number from
#: drifting when a switch is added.
#:
#: This promises no phrasing that does not exist. Writing a family here without
#: a route behind it would be lying to the owner, so `test_settings_help.py`
#: runs each family's phrase through the real intent matcher and fails if it
#: reaches the model instead.
#:
#: WHY THESE ARE NOT IN `BOOL_SETTINGS`: they are not on/off booleans this
#: registry sets. The animal options come from `jarvis_animal.SWITCHES` and its
#: `DEVICE_CHANGES`; Lockdown, the menus, the thinking level, the card display,
#: the interruption budget and the manner are reached by `jarvis_quick.py`'s own
#: grammars.
_OTHER_REACHABLE: tuple = (
    # jarvis_animal.SWITCHES - the count is read from that module, never typed
    ("the animal faces: keeping it still, listening nods, a focus buddy, small "
     "acknowledgements, petting, idle moments, seasonal touches",
     "the animal faces", -1, "jarvis_animal"),
    # jarvis_quick.py's sky and weather grammar (jarvis_sky.py)
    ("the sun and moon behind the face", "the animal faces", 1, "jarvis_sky"),
    ("the weather behind the face, and where it comes from", "the animal faces",
     1, "jarvis_sky"),
    # jarvis_animal.DEVICE_CHANGES - each device changes only itself. Two
    # settings, not fourteen: DEVICE_CHANGES lists the verbs and values the
    # grammar accepts ("sharper", "sharpness:high", "frame_rate:60"), and
    # sharpness and frame rate are the two things being set.
    ("how sharp and how smooth the animal is drawn, per device",
     "the animal faces", 2, "jarvis_animal"),
    # jarvis_card_summary.py, reached from jarvis_quick.py
    ("how much of an approval card is shown", "approval cards", 1,
     "jarvis_card_summary"),
    # jarvis_arbiter.py, reached from jarvis_quick.py
    ("how many times a day Jarvis may speak up, and when the brief arrives",
     "when Jarvis speaks up", 2, "jarvis_arbiter"),
    # jarvis_manner.py, reached from jarvis_quick.py. The phrase needs its
    # "from now on" prefix: _TO_PLAIN is only consulted after _FROM_NOW_ON, so
    # a bare "be plainer" reaches the model instead. Verified, not assumed.
    ("how Jarvis talks: warm and brief, or plain (say \"from now on, be "
     "plainer\")", "how Jarvis talks", 1, "jarvis_manner"),
    # jarvis_menus.HIDEABLE, reached from jarvis_quick.py. ONE setting, not 86:
    # HIDEABLE lists the menus it can be applied to, and the setting is
    # "show/hide a menu" with the menu as its parameter.
    ("showing or hiding a menu", "the menus", 1, "jarvis_menus"),
    # jarvis_thinking.py, reached from jarvis_quick.py
    ("how much a model thinks before answering", "thinking", 1,
     "jarvis_thinking"),
    # jarvis_quick.py's "search_use" grammar (Intent("search_use")): "switch to
    # brave for search", "use exa for the web search". A concrete value, so it
    # can be named without promising a phrasing that is not there.
    ("which service web search uses", "the web search", 1, "jarvis_search"),
    # jarvis_asks_first.py, reached from jarvis_quick.py
    ("Lockdown", "what asks first", 1, "jarvis_asks_first"),
)

def _family_count(module_name: str, fallback: int) -> int:
    """How many settings that family covers, counted from its own module.

    Only the animal switches are counted this way, because that is a real table
    of separate on/off switches. A module that is not on this PC (an older
    install) must not make the whole answer fail, so the fallback is used and
    the number is never invented.
    """
    try:
        mod = __import__(module_name)
    except Exception:
        return fallback
    if module_name == "jarvis_animal":
        return len(getattr(mod, "SWITCHES", ()) or ()) or fallback
    return fallback


#: Said when the backend running on the PC cannot do something the app knows
#: about. It says TELL, never update: this detection does not update anything,
#: and the app's own updater carries the desktop binary only.
BACKEND_BEHIND = ("Your Jarvis backend is behind this app: the app knows about "
                  "{expected} abilities and the backend running on this PC has {got} "
                  "of them. Updating the app does not update the backend. On the PC, "
                  "run apply-patches.ps1 to bring the backend up to date.")


def capability_keys() -> list:
    """The stable names of what THIS backend can change, sorted.

    KEYS, not the spoken names: `changeable_settings()` words its rows for
    reading aloud, so two builds can say the same thing in different words and a
    comparison on those strings would cry wolf. These are the switch `key`s, the
    asks-first targets, the reading tools, and the family tables by the module
    that owns them.

    This is the seam for "is my backend behind my app?". The app is built from
    one commit and the backend on the PC runs another, and neither knows the
    other's version - but each can say what it can DO, and that is comparable.
    """
    keys = [f"switch:{b.key}" for b in BOOL_SETTINGS]
    keys += [f"choice:{c.key}" for c in CHOICE_SETTINGS]
    keys += [f"asks_first:{k}" for k in _ASKS_FIRST_TARGETS]
    keys += [f"tool:{k}" for k in _TOOL_TARGETS]
    for what, _where, _count, module in _OTHER_REACHABLE:
        keys.append(f"family:{module or what}")
    return sorted(set(keys))


def capability_report() -> dict:
    """What this backend can change, as the small thing both sides compare:
    {"keys": [...], "count": n}. `count` is the number the owner is told when he
    asks what he can change, so a report can be read out as-is."""
    return {"keys": capability_keys(), "count": changeable_settings()["count"]}


def behind(expected, reported) -> dict:
    """Is the backend behind the app? Two CAPABILITY sets and nothing else.

    `expected`: what the caller's build knows (the app's own report), or an
    "expected" list of keys; `reported`: what the running backend said, or its
    report. Returns {"behind", "missing", "extra", "line"} - `line` is empty
    when the backend is not behind, and plain words when it is.

    WHAT THIS DOES NOT COVER: it sees capability names, so it catches a backend
    that cannot do something the app knows about (the measured 13-vs-51 settings
    case), and it cannot see a difference in behaviour, wording, a bug that was
    fixed, or anything neither side names. It is not a version check.
    """
    if isinstance(expected, dict):
        expected = expected.get("keys") or ()
    if isinstance(reported, dict):
        reported = reported.get("keys") or ()
    want = {str(k) for k in (expected or ())}
    got = {str(k) for k in (reported or ())}
    missing = sorted(want - got)
    if not missing:
        return {"behind": False, "missing": [], "extra": sorted(got - want), "line": ""}
    return {"behind": True, "missing": missing, "extra": sorted(got - want),
            "line": BACKEND_BEHIND.format(expected=len(want), got=len(got))}


def changeable_settings() -> dict:
    """Everything the owner can change by talking, in plain words.

    {"switches": [(name, group), ...], "count": n, "words": "..."}

    `count` is the number of SETTINGS, not the number of rows: a row that covers
    a family states how many settings it covers, so the answer can be spoken
    without reading out 45 separate names.

    WHERE THE LIST COMES FROM, and why it is not just `BOOL_SETTINGS` any more
    (2026-10-13): this used to return the 13 on/off switches alone, so the
    answer told the owner he could change 13 things while far more were
    reachable by asking. The switches below are still derived from
    `BOOL_SETTINGS`, the asks-first rows from `_ASKS_FIRST_TARGETS` and the
    reading-tool row from `_TOOL_TARGETS`; the rest are counted from the module
    that owns them. A switch added to any of those tables appears here by
    itself, and the count rises with it.
    """
    rows = []
    total = 0
    for b in BOOL_SETTINGS:
        name = b.names[0] if b.names else b.key
        where = SECTION_PLAIN.get(b.section or "", "")
        rows.append((name, where))
        total += 1

    # "What asks first" - one row per action, named the way a person says it.
    asks = len(_ASKS_FIRST_TARGETS)
    if asks:
        rows.append((f"what asks first, for {asks} things (my calendar, email, "
                     f"notes, home status, Obsidian, Logseq, Joplin)",
                     "what asks first"))
        total += asks
    # Offering a reading tool to the AI model at all.
    tools = len(_TOOL_TARGETS)
    if tools:
        rows.append((f"which of {tools} reading tools the AI model may use "
                     f"(calendar, email, notes, home status)", "what asks first"))
        total += tools

    # The families whose table lives outside this registry.
    for what, where, count, module_name in _OTHER_REACHABLE:
        rows.append((what, where))
        total += _family_count(module_name, count) if count < 0 else count

    # The named-choice settings (2026-10-22): each row is ONE setting with a
    # list of values, so the count is one per row - never the number of choices.
    for choice in CHOICE_SETTINGS:
        rows.append((choice.describe or choice.key,
                     SECTION_PLAIN.get(choice.where or "", "")))
        total += 1

    return {"switches": rows, "count": total,
            "words": changeable_words(rows, total)}


def changeable_words(rows=None, count=None) -> str:
    """The answer to "what can I change?", as one thing to say.

    Written as a spoken sentence - semicolons between items, no bullet list
    and no markdown - because this reply may be read aloud.

    `count` is how many SETTINGS the answer covers, which is not the number of
    rows: a family row stands for several. Passing it separately is what lets
    the sentence state a truthful number. Left out, the rows are counted, which
    is only right when every row is one setting.

    It leads with that number because the number is the whole point of the
    answer: it used to offer 13 while far more were reachable, so the owner
    reasonably concluded the rest could not be done by asking.
    """
    if rows is None:
        got = changeable_settings()
        rows, count = got["switches"], got["count"]
    if not rows:
        return ("Nothing can be changed by talking on this PC yet. Everything "
                "lives in Settings in the app.")
    if count is None:
        count = len(rows)
    names = [f"{name} ({where})" if where else name for name, where in rows]
    return (f"You can change {count} settings by asking. Here is what they "
            "cover: " + "; ".join(names) +
            ". A family that names a number covers that many separate settings. "
            "Anything that loosens a rule still shows you a card first, and "
            "say \"undo\" in the same chat if you change your mind.")


# --------------------------------------------------------------------------
#   Animal options (2026-09-28): the shared switches, the sun and moon and
#   the weather source - each through the function its own switch calls.
#   jarvis_quick._animal is the grammar; this is the one place it acts.
# --------------------------------------------------------------------------


def find_animal_switch(words: str) -> Optional[str]:
    """The shared animal switch `words` names exactly (jarvis_animal's own
    alias list - never typed twice), or None."""
    try:
        import jarvis_animal as AN
    except Exception:
        return None
    return AN.find_switch(words)


def set_animal_switch(key: str, on: bool, *, peer=None, local=None) -> Outcome:
    """At once, from either app or by asking: cosmetic, no card - the same
    jarvis_animal.set_switch POST /api/animal calls."""
    try:
        import jarvis_animal as AN
    except Exception:
        return _missing("the animal options")
    code, out = AN.set_switch(key, bool(on))
    return _say(code, out)


def _sky_here(peer, local) -> bool:
    try:
        import jarvis_sky as SK
        return SK._from_this_pc(peer, local)
    except Exception:
        return False


def set_sky_show(on: bool, *, peer=None, local=None) -> Outcome:
    """"Show the sun and moon behind the face": at once either way, the
    same jarvis_sky.handle_post({"show": ...}) both apps' switch calls."""
    try:
        import jarvis_sky as SK
    except Exception:
        return _missing("the sun, moon and weather")
    code, out = SK.handle_post({"show": bool(on)}, here=_sky_here(peer, local))
    return _say(code, out)


def set_weather_source(source: str, *, peer=None, local=None) -> Outcome:
    """The weather source: "off" and "home_assistant" at once; "open_meteo"
    raises jarvis_sky's ONE approval card (it sends the rough position to
    the internet) and changes nothing until it is approved - the same
    jarvis_sky.handle_post({"weather": ...}) both apps' choices call."""
    try:
        import jarvis_sky as SK
    except Exception:
        return _missing("the sun, moon and weather")
    code, out = SK.handle_post({"weather": source}, here=_sky_here(peer, local))
    return _say(code, out)


