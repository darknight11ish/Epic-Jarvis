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

Left OUT of "adjust", on purpose, said plainly rather than guessed at:
  * Voice (speed, built-in speaker, the better voice, voice follows the
    face - that last one IS a single on/off, but it lives on the voice
    screen with the rest and has not been offered as a spoken "adjust";
    "open Jarvis's voice" reaches it; each animal's own voice, pitch and
    pace, 2026-09-28, is a multi-field row, so open-only too),
    hardware/models, the
    second graphics card, the big model, backups, custom voices, and
    Accounts (credentials) - each is either a multi-field control with no
    single "on/off" a spoken sentence maps to safely, or (Accounts) a
    secret the owner should never be asked to say aloud. All of these are
    "open"-only: SECTIONS still jumps the app there.
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
    Section("hardware", ("hardware and models", "hardware", "graphics cards"), app="desktop"),
    Section("second-card", ("the second graphics card", "second card", "second gpu"),
            app="desktop"),
    Section("big-model", ("the big model", "big model settings"), app="desktop"),
    Section("folders", ("folders jarvis may look in", "folders", "the notion export")),
    Section("backup", ("backups", "backup settings")),
    Section("updates", ("updates", "app updates"), app="desktop"),
    Section("tool-updates", ("tool updates", "check for tool updates"), app="desktop"),
    Section("more-options", ("more options", "startup and logs"), app="desktop"),
    Section("start-jarvis", ("starting jarvis for you", "start jarvis automatically"),
            app="desktop"),
    Section("asks-first", ("what asks first", "asks first settings")),
    Section("prompt-coach", ("prompt coach settings", "the prompt coach page")),
    Section("reach", ("what jarvis can reach", "what jarvis can access")),
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
    Section("about", ("about jarvis", "about")),
    # "Hang and crash notes": inside "More options" on the desktop (its own
    # <section id="crash-notes">). The phone has no such list - its own
    # crash screen only appears after a crash - so OpenPlace.PC_ONLY says so.
    Section("crash-notes", ("crash notes", "hang and crash notes", "the crash notes"),
            app="desktop"),
    Section("backend-supports", ("what this backend supports", "backend capabilities"),
            app="desktop"),
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
    # Spending (2026-09-30): a card on the desktop.
    Section("spending", ("spending", "spending settings", "my spending", "bank files"),
            app="desktop"),
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


# --- the headless browser, Obscura (jarvis_browser_engine.py) --------------

def set_browser_engine(on: bool, *, peer=None, local=None) -> Outcome:
    try:
        import jarvis_browser_engine as BE
    except Exception:
        return _missing("the headless browser")
    code, out = BE.request(bool(on), BE.set_obscura)
    return _say(code, out)


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
        None,
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
        None,
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
        None,
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
        None,
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
        None,
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
        None,
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
        None,
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
        None,
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
    BoolSetting("briefing_senders",
               ("senders in my briefing", "showing senders in my briefing",
                "email senders in the morning briefing"),
               "briefing-settings", set_briefing_senders),
)

_BOOL_BY_NAME = {_bare(name): b for b in BOOL_SETTINGS for name in b.names}


def find_bool_setting(words: str):
    return _BOOL_BY_NAME.get(_bare(words))


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
