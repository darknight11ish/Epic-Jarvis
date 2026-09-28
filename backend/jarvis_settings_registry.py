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
same as on the desktop. Saying "open hardware" on the phone (a genuinely
desktop-only section) is the harmless fallback case: the Settings screen
still opens, but there is no row there to scroll to, the same "Show me
where" already has for an unmatched place. Said plainly here rather than
claimed as a feature: a per-app wording would need the backend to read
`X-Jarvis-Client` for this, which it does not do today.

ADJUSTABLE covers ten settings behind a SINGLE existing boolean or choice
function, picked because each already has a proven `handle_*`/`request_*`
entry point this file can call exactly as the REST route does:
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
  * smartwatch_notifications - jarvis_watch_notify.request()
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
    Section("connection", ("connection", "the connection settings", "where jarvis is running")),
    Section("faq", ("the faq", "frequently asked questions", "help")),
    Section("appearance-card", ("appearance", "the theme", "how jarvis looks", "the face")),
    # "Animal options" (2026-09-28): every animal-face option in one place.
    # Desktop: its own card in settings.html. Phone: inside Appearance, so
    # the phone's Settings scrolls to its Appearance row (SettingsScreen.kt
    # SETTINGS_ITEM_INDEX), whose button opens it.
    Section("animal-options", ("animal options", "the animal's options", "animal settings",
                               "the animal's settings", "the animal settings")),
    Section("voice", ("voice", "voice settings", "my voice", "how jarvis listens")),
    Section("manner", ("how jarvis talks", "manner", "warm and brief", "plain mode")),
    Section("briefing-settings", ("the morning briefing", "briefing settings")),
    Section("shortcuts", ("shortcuts", "keyboard shortcuts", "hotkeys"), app="desktop"),
    Section("security", ("security", "app lock", "windows hello")),
    Section("voices", ("jarvis's voice", "jarvis's voices", "custom voices",
                       "how jarvis sounds")),
    Section("web-search", ("web search", "search settings", "the search provider")),
    Section("account-secrets", ("accounts", "account secrets", "credentials"), app="desktop"),
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
    Section("reach", ("what jarvis can reach", "what jarvis can access")),
    Section("email-sending", ("sending email", "email sending settings")),
    Section("about", ("about jarvis", "about")),
    Section("backend-supports", ("what this backend supports", "backend capabilities"),
            app="desktop"),
    Section("watch-notify", ("smartwatch notifications", "watch notifications"),
            app="phone"),
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


# --- smartwatch notifications (jarvis_watch_notify.py) ---------------------

def set_watch_notify(on: bool, *, peer=None, local=None) -> Outcome:
    try:
        import jarvis_watch_notify as WN
    except Exception:
        return _missing("smartwatch notifications")
    code, out = WN.request(bool(on), WN.set_enabled)
    return _say(code, out)


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
    BoolSetting("ask_before_every_search",
               ("asking before every web search", "ask before every search",
                "asking before every search"),
               "web-search", set_ask_every_search),
    BoolSetting("smartwatch_notifications",
               ("smartwatch notifications", "watch notifications",
                "notifications on my watch"),
               "watch-notify", set_watch_notify),
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
    """"Show the sun and moon behind the animal": at once either way, the
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
