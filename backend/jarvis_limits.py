"""jarvis_limits.py - the limits and frequencies the owner can change.

    POST /api/limits/settings   {"key": "jobs_per_tick", "value": 8}

WHY ONE MODULE AND ONE ROUTE. An audit of all 117 features against the real
settings surface (2026-10-08) listed the frequencies and limits the owner could
see and change nowhere. Every one of them is the same shape - a number (or one
on/off) in the owner's own `jarvis-framework.toml`, read by a module that
already knows how to use it - so they share ONE table here and ONE route in
`jarvis_hud.py` (`limits-settings.patch`), rather than one route each. A new
patch costs this repository real work (its place in `apply-patches.ps1`, three
ordering invariants, the stand-in ratchet), so the next limit is a line in
`LIMITS` and nothing else.

WHAT THIS MODULE DOES NOT DO: it does not decide what a limit means, and it does
not change how any module uses its number. Every entry names the table and key
its owning module ALREADY reads, with the same default that module uses, so the
number written here is the number that module acts on. Where a module reads the
key itself (`jarvis_jobs.py`, `jarvis_watch.py`, `jarvis_undo.py`,
`jarvis_entities.py`), nothing in that module changes.

THE RULE, the same one every setting follows:

  * THE SAFE DIRECTION is applied at once, with no card;
  * THE DIRECTION THAT LOOSENS SOMETHING goes through ONE approval card first,
    and nothing is written until a person approves. WHICH direction that is is
    the entry's own `loosening`: "up" means a bigger number (or a bool turned
    ON) lets Jarvis do more or keep more - keeping undo history longer, letting
    a model read the owner's saved facts; "down" means a SMALLER number lets
    MORE through, and the voice check's bar is the one entry of that shape (the
    owner's decision of 2026-10-08: a lower bar means more clips count as the
    owner's voice); "none" means neither direction loosens anything. Which way a
    request goes comes from the value against the number in force - never from
    anything the caller sends.

WHERE A ROW'S NUMBER LIVES. Most entries name a `[table].key` in the owner's
`jarvis-framework.toml` and this module moves that one line. ONE entry does not:
the voice check's bar lives in the owner's ENROLLED VOICE PRINT, which is
encrypted and which `jarvis_voice.py` alone reads and writes. That entry names a
`source` instead (`SOURCES`, below) and keeps no second copy of the number -
see `_VoiceBar`. This module never writes a print file itself, and it logs
nothing about a print; the one thing it takes from one is the bar.
"""
from __future__ import annotations

import os
import re
import stat
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:                                    # pragma: no cover
    fw = None

try:
    import jarvis_notify_prefs as NP
except Exception:                                    # pragma: no cover - shipped beside this file
    NP = None

#: The gate action a loosening going UP is asked under. ONE name for every such
#: limit: the card's own words (below) carry which limit and how far, and a name
#: per limit would mean a name per limit in the card-words table, on the "What
#: asks first" page and in the tier file - three places to keep in step for no
#: gain the owner can see. The value decides whether this loosening is going
#: that way, this name only says "this one is a raise".
RAISE_ACTION = "raise_a_limit"

#: The gate action the ONE loosening that goes DOWN is asked under. Its own name,
#: not `raise_a_limit`: a card that says "Jarvis wants to let Jarvis do more, for
#: longer, or more often" over a LOWER voice-check bar would describe the
#: opposite of what the owner is agreeing to. (The other direction on this entry
#: - making the bar stricter - asks nothing and has no action, exactly as
#: turning any other number down does.)
LOWER_ACTION = "lower_the_voice_check_bar"

#: What a loosening card says it lets through, when the entry names no line of
#: its own.
RAISE_MORE = "That lets Jarvis do more."

ROUTE = "/api/limits/settings"

_SECTION_LINE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")
_SCALAR_LINE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z_][A-Za-z0-9_]*)"
                          r"(?P<eq>\s*=\s*)(?P<value>[^#\r\n]*?)(?P<rest>\s*(?:#.*)?)$")


class SettingsFileError(Exception):
    """The owner's settings file could not be read or written, so nothing was
    changed. The message is shown to the owner as it is, in plain words."""


def _words(n) -> str:
    return f"{n:g}"


# ---------------------------------------------------------------------------
#   A time of day - the one kind that is neither a number nor a switch
# ---------------------------------------------------------------------------
#: The kind a time-of-day row carries. The two quiet-hours ends were the first
#: of these (the owner's decision of 2026-10-08, "the quiet hours' two times").
#: A time of day is NOT a number of minutes: rendering 22:00 as "1320" with no
#: explanation is worse than not offering the row at all, so the value on the
#: wire is the string the owner reads and types, "HH:MM", and the CHECK is
#: `jarvis_notify_prefs.check_time`'s - one home for one rule.
KIND_TIME = "time"


def _time_checked(value) -> str:
    """`value` as "HH:MM", through the module that owns the rule.

    This is deliberately NOT a second copy of the shape check. The value a
    quiet-hours row writes lives in `jarvis_notify_prefs.py`, so that module
    decides what a time is; this call is how the limits table asks."""
    if NP is None:
        raise SettingsFileError("The PC's Jarvis does not have the notification "
                               "settings installed, so nothing was changed")
    try:
        return NP.check_time(value)
    except NP.PrefsError as exc:
        raise SettingsFileError(str(exc))


# ---------------------------------------------------------------------------
#   The one value that lives outside the settings file
# ---------------------------------------------------------------------------
#: The voice check passes a clip when its similarity to the owner's enrolled
#: print is at least a bar, and that bar lives IN THE PRINT (`threshold`). The
#: print is encrypted and `jarvis_voice.py` is the only module that reads or
#: writes it, so this table keeps no second copy of the number in
#: jarvis-framework.toml: the row names this source instead of a `[table].key`.
VOICE_BAR_SOURCE = "voice"

#: What the row reads when no voice has been trained yet: the bar enrolment
#: would give one (jarvis_voice's own `threshold` default, 0.35), as a whole
#: percentage.
VOICE_BAR_DEFAULT = 35


def _percent_to_cosine(percent) -> float:
    """The whole percentage the owner reads, as the print's own bar.

    The stored number is a cosine similarity (0.35 by default) and is not a
    number the owner should have to read; the row is a whole percentage and
    these two functions are the only place the two meet."""
    return float(percent) / 100.0


def _cosine_to_percent(cosine) -> int:
    """The print's own bar as the whole percentage the owner reads."""
    return int(round(float(cosine) * 100))


class _VoiceBar:
    """The owner's voice-check bar, read and written through `jarvis_voice`.

    THE ONE HOME OF THE NUMBER. `read` asks `jarvis_voice.find_profile("")`,
    whose own first step is `load_profile` (the general print) - the same lookup
    `write` uses - so read and write can never disagree about which print holds
    the bar. `write` goes through `jarvis_voice.set_threshold`, the function the
    "someone else" check's own card already uses. Nothing here writes a print
    file, nothing here reads anything from a print but the bar, and nothing here
    logs anything about one.

    `read` returns jarvis_voice's own clamped value: `load_profile` holds every
    bar inside `MIN_THRESHOLD` (5%) .. 1.0 (100%), so a hand-edited print cannot
    show the owner a number the check itself would never use.
    """

    #: The name a `Limit.source` uses, the module the value belongs to, and the
    #: name that module carries in `_where.SHIPPED`. test_limits.py checks all
    #: three agree, so a source cannot point at a module this repository does
    #: not ship whole.
    name = VOICE_BAR_SOURCE
    module = "jarvis_voice"
    owner = "jarvis_voice.py"

    def _voice(self):
        try:
            import jarvis_voice
        except Exception:                    # pragma: no cover - no print, no bar
            return None
        return jarvis_voice

    def read(self):
        """The bar in the print, as a whole percentage."""
        v = self._voice()
        if v is None:
            return VOICE_BAR_DEFAULT
        try:
            prof, _label = v.find_profile("")
        except Exception:                    # pragma: no cover - unreadable print
            return VOICE_BAR_DEFAULT
        if prof is None:
            return VOICE_BAR_DEFAULT
        return _cosine_to_percent(prof.threshold)

    def check(self, percent) -> None:
        """Refuse, in plain words and BEFORE any card is raised, a number the
        print itself would refuse.

        `set_threshold` enforces the model's own floor - "no bar below the
        model's own floor, not by enrolment and not by a card either" - so the
        floor is READ FROM jarvis_voice rather than restated here. Without this,
        the owner would answer a card for a change that then could not happen.
        """
        v = self._voice()
        if v is None:
            raise SettingsFileError("The voice check is not installed on this PC, "
                                    "so nothing was changed")
        prof, _label = v.find_profile("")
        if prof is None:
            raise SettingsFileError("No voice has been trained yet, so there is "
                                    "no bar to change")
        lowest = _cosine_to_percent(v.floor_for(prof.embedder, v.BALANCED))
        if float(percent) < lowest:
            raise SettingsFileError(f"The lowest this voice check allows is "
                                    f"{lowest}%, so nothing was changed")

    def write(self, percent) -> None:
        """Write the bar into the print, through `jarvis_voice.set_threshold`.

        jarvis_voice checks its own floor again here, so this is a second gate
        that fails closed rather than the only one."""
        v = self._voice()
        if v is None:
            raise SettingsFileError("The voice check is not installed on this PC, "
                                    "so nothing was changed")
        try:
            v.set_threshold(_percent_to_cosine(percent))
        except ValueError as exc:
            raise SettingsFileError(f"Your voice check would not take that "
                                    f"({exc}), so nothing was changed")


#: The non-toml homes a row may name, by the name the row uses. A source is the
#: ONLY thing that reads or writes that row's value, and a row naming one
#: carries no `[table].key` at all.
SOURCES: dict = {VOICE_BAR_SOURCE: _VoiceBar()}


# ---------------------------------------------------------------------------
#   The table
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Limit:
    key: str                     # the name the route, the screens and a voice
                                 # sentence use
    section: str                 # the table in jarvis-framework.toml - "" when
                                 # the value lives in a `source` instead
    name: str                    # the key inside it - "" for a source row
    title: str                   # the row's words, in the owner's language
    kind: str                    # "int" | "float" | "bool"
    default: object
    low: float = 0
    high: float = 0
    choices: tuple = ()          # when set, the value must be one of these
    loosening: str = "none"      # which direction asks: "up" | "down" | "none"
    pc_only: bool = False        # may only be changed from this PC
    app: str = "both"            # "both" | "desktop" | "phone"
    unit: str = ""               # what one step of the number means
    note: str = ""               # the row's second line, plain words
    source: str = ""             # a non-toml home for the value (SOURCES), or ""
    action: str = ""             # the gate action a loosening is asked under
                                 # (RAISE_ACTION when empty)
    card_more: str = ""          # the card's last line: what the loosening lets
                                 # through (RAISE_MORE when empty)
    says: Optional[Callable[[object], str]] = None

    @property
    def loosen_up(self) -> bool:
        """Kept for the wire: the view's own `loosen_up` says "a BIGGER value is
        the loosening", which is true of every row but the voice bar."""
        return self.loosening == "up"

    @property
    def asked_action(self) -> str:
        return self.action or RAISE_ACTION

    def words(self, value) -> str:
        if self.says is not None:
            return self.says(value)
        if self.kind == "bool":
            return self.title if value else f"no: {self.title}"
        if self.kind == KIND_TIME:
            # A clock time reads as itself. It is never turned into a number of
            # minutes: "1320" with no explanation is worse than no row at all.
            return f"{value}"
        return f"{_words(value)}{(' ' + self.unit) if self.unit else ''}"


def _ttl_says(v) -> str:
    return {1: "keep undo for an hour",
            24: "keep undo for a day",
            168: "keep undo for a week"}.get(int(v), f"keep undo for {int(v)} hours")






# ---------------------------------------------------------------------------
#   This PC's own notifications - the seven the phone may change too
# ---------------------------------------------------------------------------
# THE OWNER'S DECISION, 2026-10-08: the PC's notification choices - which of
# this PC's own toasts fire (alarms, reminders, the morning briefing, the
# "Solve it here" hand-off) and the quiet hours around them - MUST be
# changeable from the phone too, and the phone must say plainly that these are
# for the PC, not for the phone's own notifications (those are a different
# feature entirely: `/api/notifications/phone`).
#
# They ride THIS table, and this module is the whole reason they can. Before
# it, the four switches and the quiet-hours window lived ONLY in the desktop
# app's own `localStorage` (`notifications-prefs.js`) and were pushed to Rust
# (`jarvis-desktop/src-tauri/src/notifications.rs`), which is what raises a
# toast. There was no route and no `jarvis-framework.toml` key for any of the
# seven - a phone cannot reach another app's `localStorage`, so there was
# nothing for a phone control to read or write.
#
# Now `jarvis_notify_prefs.py` owns `[notifications]` in the owner's own
# settings file, and these rows are how both apps change it. Riding the table
# means NO new patch, NO new route and no new ordering invariant - a row here
# costs a line, while a new patch costs its place in `apply-patches.ps1`,
# three ordering allow-lists and the stand-in ratchet.
#
# `loosening="none"` on ALL SEVEN, deliberately and for a reason the owner
# needs: a limit's card exists to say "this lets Jarvis do more", and NOTHING
# here does. A bigger `quiet_end`, a switch turned on or the quiet window
# moved to the middle of the day changes only when this PC shows its owner a
# toast. Putting a "Jarvis wants to do more" card over "show me the briefing"
# would be a lie, and - much worse - the ONE thing these rows must never do is
# stop an alarm from ringing because a card about it was not answered in time.
# Turning the alarms row off is still the owner's own choice, made on either
# app, and it takes effect at once, exactly as it does on the desktop today.
#
# `app="both"` on all seven, `pc_only=False` on all seven. The four titles
# carry "(on your PC)" in the owner's own language, because the phone draws
# these rows in its own Settings screen next to its OWN notification settings
# (`settings.phone-notify`) and the two must never be confused for each other.
#
# `kind="bool"` needs NO client change: the desktop's `limits.js`/`limits-settings.js`
# and the phone's plate draw any row whose kind they can draw, so a bool row
# appears on both screens the moment it is in this table. The two times are the
# new `kind="time"`, drawn as a real clock picker in both apps.

#: The limits key of the quiet-hours switch, so each app can find the row that
#: decides whether the two times below it matter. The prefix is the same one
#: `jarvis_notify_prefs.SWITCHES` uses, with `notif_` in front.
NOTIFY_QUIET_ON = "notif_quiet_enabled"

#: What each of the owner's notification values writes, and what the row says.
#: The keys are `jarvis_notify_prefs.KEYS`; the titles are the owner's words.
_NOTIFY_ROWS: tuple = (
    ("alarms", "bool", "Speak up when an alarm rings (on your PC)",
     "An alarm, and an urgent \"tell me when\" alert, ring until you dismiss "
     "them and break through Windows Focus Assist. This is the PC's alarm, not "
     "your phone's."),
    ("reminders", "bool", "Chime when a reminder is due (on your PC)",
     "Timers, reminders and to-do items chime once when they are due, on the "
     "PC, and offer Snooze."),
    ("briefing", "bool", "Say when the morning briefing is ready (on your PC)",
     "Tells you on the PC when your morning briefing is ready to read in the "
     "Brain. The briefing itself is not sent to your phone."),
    ("handoff", "bool", "Say when a website needs you (on your PC)",
     "Tells you on the PC when a website or support chat has paused at a "
     "captcha or sign-in page and is waiting for you to solve it there."),
    ("quiet_enabled", "bool", "Be quiet during quiet hours (on your PC)",
     "Silences the PC's non-urgent notifications during the hours below. It "
     "never silences an alarm, an urgent alert or a decision waiting for you."),
    ("quiet_start", KIND_TIME, "Quiet hours start (on your PC)",
     "The hour the PC's quiet window begins, on the PC's own clock."),
    ("quiet_end", KIND_TIME, "Quiet hours end (on your PC)",
     "The hour the PC's quiet window ends, on the PC's own clock."),
)


def _notify_default(pref_key: str):
    """The default the module that owns the value uses, or a safe stand-in when
    that module has not reached this backend. Read from `jarvis_notify_prefs`
    rather than typed twice, so the table and the settings file cannot drift."""
    if NP is not None:
        return NP.DEFAULTS[pref_key]
    return "22:00" if pref_key == "quiet_start" else (
        "07:00" if pref_key == "quiet_end" else pref_key != "quiet_enabled")


def _notify_rows() -> tuple:
    out = []
    for pref_key, kind, title, note in _NOTIFY_ROWS:
        out.append(Limit(
            key=f"notif_{pref_key}", section=NP.SECTION if NP is not None else "notifications",
            name=pref_key, title=title, kind=kind,
            default=_notify_default(pref_key),
            loosening="none", app="both",
            note=note,
        ))
    return tuple(out)


LIMITS: tuple = (
    # `[undo].ttl_hours` - how long an Undo stays possible. LONGER keeps more
    # of the owner's own files recoverable on disk, so UP is the direction
    # that asks (jarvis_undo.py reads this key already).
    Limit("undo_window", "undo", "ttl_hours", "How long you can undo",
          "int", 24, low=1, high=720, choices=(1, 24, 168), loosening="up",
          app="both", unit="hours",
          note="A longer window keeps older copies of your files on this PC.",
          says=_ttl_says),
    # `[jobs].max_jobs_per_tick` - how much Jarvis gets on with at once.
    # Nothing leaves the PC and nothing is spent, so neither direction asks.
    Limit("jobs_per_tick", "jobs", "max_jobs_per_tick", "Jobs at once",
          "int", 4, low=1, high=16, pc_only=True, app="desktop", unit="jobs",
          note="How many jobs one tick may start. More at once is faster and "
               "busier."),
    # `[watch].star_jump` / `star_floor` - what counts as news from a project.
    Limit("watch_star_jump", "watch", "star_jump", "What counts as news: the jump",
          "float", 0.5, low=0.05, high=0.9, app="desktop", unit="of the count",
          note="A repository counts as news when its stars move by this "
               "fraction."),
    Limit("watch_star_floor", "watch", "star_floor", "What counts as news: the floor",
          "int", 25, low=1, high=500, app="desktop", unit="stars",
          note="...but never for a repository with fewer stars than this."),
    # `[decks].run_limit` (2026-10-08): how many cards one review run shows
    # before "Do 10 more" adds ten. The study module reads it now, with the 20
    # it always had as the default and 1..MAX_CARDS as the range. (Named in
    # words, not by module name, on purpose: that module's own suite checks
    # that no other module reaches it, and this table only writes its number.)
    Limit("study_run_cards", "decks", "run_limit", "Cards in a study run",
          "int", 20, low=1, high=1000, app="both", unit="cards",
          note="What one run shows before you can ask for ten more."),
    # `[chat].tag_suggest_quiet_minutes`: how long a chat must sit untouched
    # before the OVERNIGHT TAG SUGGESTER may read it for tags. NOT the
    # new-conversation window - the two are different features, and the file's
    # own comment says so. 0 means no waiting at all.
    Limit("tag_suggest_age", "chat", "tag_suggest_quiet_minutes",
          "Suggest tags for chats older than",
          "int", 30, low=0, high=1440, app="desktop", unit="minutes",
          note="The overnight job may read a chat this old to suggest a tag. "
               "0 means no waiting."),
    # NOT HERE, and said plainly rather than half-done: the "new conversation
    # after 30 quiet minutes" window is CLIENT-SIDE (`chat-history.js`'s
    # `IDLE_NEW_MS`, `ChatSession.kt`) - nothing in the backend reads or serves
    # it, so a key here could not change it. That one needs the two apps' own
    # settings, not a line in this table.
    # `[memory.entities].model_pass` - whether a model reads what the owner
    # saves, looking for people and things. Turning it ON is the loosening: a
    # model reads stored facts (the owner's decision of 2026-09-24 makes every
    # reading of memory a card). OFF is instant.
    Limit("memory_people", "memory.entities", "model_pass",
          "Look for people and things in what you save",
          "bool", False, loosening="up", app="phone",
          note="A model reads what you save to find the people and things in "
               "it. Off, only the plain words you used are kept."),
    # THE VOICE CHECK'S BAR - the owner's decision of 2026-10-08, and the one
    # row here whose loosening goes the OTHER way. It lives in the ENROLLED
    # VOICE PRINT, not in jarvis-framework.toml (the print is encrypted and
    # `jarvis_voice.py` is the only module that reads or writes it), so the row
    # names that `source` instead of a `[table].key`, and the number is
    # `jarvis_voice`'s own `threshold` - never a second copy of it.
    #
    # The owner reads a WHOLE PERCENTAGE: the stored cosine (0.35) is not a
    # number they should have to read, and the conversion happens at the voice
    # boundary (`_percent_to_cosine`). LOWERING it is the loosening - a lower
    # bar means MORE clips count as the owner's voice - so `loosening="down"`
    # and `LOWER_ACTION` is the name its card is asked under. Raising it is the
    # safe direction and applies at once, like every other tightening.
    #
    # 25% is offered though a print whose model floor is 35% (the small model's
    # own balanced bar) refuses it: the floor is jarvis_voice's rule, read from
    # jarvis_voice and never overridden here, and the refusal is in its words.
    Limit("voice_bar", "", "", "How sure Jarvis must be that it is your voice",
          "int", VOICE_BAR_DEFAULT, low=5, high=100,
          choices=(25, 35, 50, 65), loosening="down",
          app="both", pc_only=False, unit="%",
          note="Lower means more clips count as your voice. Going lower asks "
               "you on the PC first.",
          source=VOICE_BAR_SOURCE, action=LOWER_ACTION,
          card_more="That lets more clips count as your voice."),
) + _notify_rows()


def find(key: str) -> Optional[Limit]:
    return next((x for x in LIMITS if x.key == key), None)


def limits_for(app: str) -> tuple:
    """Every limit this app may change. `app` is "desktop" or "phone"."""
    return tuple(x for x in LIMITS if x.app in ("both", app))


# ---------------------------------------------------------------------------
#   Reading and writing the owner's file
# ---------------------------------------------------------------------------
def _config() -> dict:
    try:
        return dict(fw.load_framework() or {}) if fw is not None else {}
    except Exception:
        return {}


def _table(cfg: dict, section: str) -> dict:
    node = cfg
    for part in section.split("."):
        node = (node or {}).get(part)
        if not isinstance(node, dict):
            return {}
    return node


def value_of(limit: Limit):
    """What the owner's file says now, or the default the owning module uses.

    A source-backed row has no key in the settings file at all: its value comes
    from the module that owns it (`_VoiceBar.read` asks `jarvis_voice`)."""
    if limit.source:
        return SOURCES[limit.source].read()
    raw = _table(_config(), limit.section).get(limit.name, limit.default)
    try:
        if limit.kind == "bool":
            return raw is True or str(raw).strip().lower() in ("true", "1", "on", "yes")
        if limit.kind == KIND_TIME:
            # Read through the owning module's own check, so a hand-edited
            # "quiet_start = maybe" shows the owner the default rather than a
            # string no screen can draw - the same way a nonsense number does.
            return _time_checked(raw)
        if limit.kind == "int":
            return int(float(str(raw).strip()))
        return float(str(raw).strip())
    except (TypeError, ValueError, SettingsFileError):
        return limit.default


def _coerced(limit: Limit, value):
    """The value as the file would hold it, or a SettingsFileError to show.

    For a source-backed row this also asks the owning module whether it would
    take the number at all (for the voice bar: the model's own floor), and it
    asks BEFORE any card is raised - so the owner is never asked to approve a
    change that could not happen."""
    if limit.kind == "bool":
        if isinstance(value, bool):
            return value
        if str(value).strip().lower() in ("true", "1", "on", "yes"):
            return True
        if str(value).strip().lower() in ("false", "0", "off", "no"):
            return False
        raise SettingsFileError("That is not on or off.")
    if limit.kind == KIND_TIME:
        # No low/high and no choices: a clock time is checked by SHAPE, by the
        # module that owns the value. See KIND_TIME.
        return _time_checked(value)
    try:
        number = int(float(str(value).strip())) if limit.kind == "int" else float(str(value).strip())
    except (TypeError, ValueError):
        raise SettingsFileError(f"\"{value}\" is not a number.")
    if limit.choices:
        if number not in limit.choices:
            raise SettingsFileError("Choose one of: " + ", ".join(
                _words(c) for c in limit.choices) + ".")
    elif not (limit.low <= number <= limit.high):
        raise SettingsFileError("That has to be between "
                                f"{_words(limit.low)} and {_words(limit.high)}.")
    typed = int(number) if limit.kind == "int" else number
    if limit.source:
        SOURCES[limit.source].check(typed)
    return typed


def _is_loosening(limit: Limit, now, want) -> bool:
    """Is this change the one that must be put to the owner on a card?

    `limit.loosening` says which WAY the loosening goes - "up" (a bigger number,
    or a bool turned ON), "down" (a smaller number lets more through), or
    "none". The direction of THIS request is read from the value against the
    number IN FORCE, never from anything the caller sends."""
    if limit.loosening == "none":
        return False
    if limit.kind == KIND_TIME:
        # Neither direction loosens anything: which hours the PC is quiet in
        # does not let Jarvis do more, spend more or reach further. `none`
        # above is the only setting this row may carry, and this is the second
        # gate in case a later row is written with a direction by mistake.
        return False
    if limit.kind == "bool":
        up, down = bool(want) and not bool(now), bool(now) and not bool(want)
    else:
        up, down = want > now, want < now
    return up if limit.loosening == "up" else down


def _literal(limit: Limit, value) -> str:
    if limit.kind == "bool":
        return "true" if value else "false"
    if limit.kind == KIND_TIME:
        # A QUOTED string, so what the file holds is what the owner reads and
        # what the owning module parses - never a bare 22:00 TOML would read as
        # something else.
        return '"{}"'.format(value)
    return _words(value)


def _toml_path() -> Optional[Path]:
    try:
        p = fw.config_path() if fw is not None else None
    except Exception:
        p = None
    return Path(p) if p else None


def _reload() -> None:
    try:
        if fw is not None:
            fw.reload_framework()
    except Exception:
        pass


def _rewrite(text: str, section: str, key: str, literal: str) -> tuple:
    """(new text, the old line's value or None). Only that one line moves."""
    lines = text.splitlines(keepends=True)
    ending = "\r\n" if "\r\n" in text else "\n"
    start = None
    for i, line in enumerate(lines):
        m = _SECTION_LINE.match(line.rstrip("\r\n"))
        if m and m.group("name").strip() == section:
            start = i
            break
    if start is None:
        tail = "" if (not lines or lines[-1].endswith(("\n", "\r"))) else ending
        lines.append(f"{tail}[{section}]{ending}{key} = {literal}{ending}")
        return "".join(lines), None
    last = start
    for i in range(start + 1, len(lines)):
        bare = lines[i].rstrip("\r\n")
        if _SECTION_LINE.match(bare):
            break                       # the next table starts here
        if not bare.strip():
            continue
        m = _SCALAR_LINE.match(bare)
        if m and m.group("key") == key:
            old = m.group("value").strip()
            lines[i] = (f"{m.group('indent')}{key} = {literal}"
                        f"{m.group('rest')}{ending}")
            return "".join(lines), old
        last = i
    lines.insert(last + 1, f"{key} = {literal}{ending}")
    return "".join(lines), None


_LOCK = threading.RLock()


def set_limit(key: str, value, *, path: Optional[Path] = None) -> dict:
    """Change ONE limit, atomically.

    {"ok", "key", "from", "to", "changed", "loosening"} - and `loosening` says
    whether THIS direction is the one that needs a card (the entry's own
    `loosening`, against the value in force), so the caller (the route, and the
    two apps' own screens) can put it to the owner. Nothing here raises a card
    or pretends to.

    A source-backed row is written by its OWNING module (`_VoiceBar.write` calls
    `jarvis_voice.set_threshold`), and no settings file is touched at all - the
    `path` argument is the settings file's and is not this row's business."""
    limit = find(key)
    if limit is None:
        raise SettingsFileError("That is not a limit Jarvis knows.")
    want = _coerced(limit, value)
    now = value_of(limit)
    asks = _is_loosening(limit, now, want)
    if limit.source:
        if want == now:
            return {"ok": True, "key": key, "from": now, "to": want,
                    "changed": False, "loosening": False}
        SOURCES[limit.source].write(want)
        return {"ok": True, "key": key, "from": now, "to": want, "changed": True,
                "loosening": bool(asks)}
    p = path or _toml_path()
    if p is None or not Path(p).is_file():
        raise SettingsFileError("Jarvis could not find your settings file "
                                "(jarvis-framework.toml), so nothing was changed")
    p = Path(p)
    with _LOCK:
        try:
            raw_bytes = p.read_bytes()
        except OSError as exc:
            raise SettingsFileError(f"Your settings file could not be read "
                                    f"({type(exc).__name__}), so nothing was changed")
        bom = raw_bytes.startswith(b"\xef\xbb\xbf")
        try:
            text = raw_bytes[3:].decode("utf-8") if bom else raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise SettingsFileError("Your settings file is not plain text, so "
                                    "nothing was changed")
        new, old_raw = _rewrite(text, limit.section, limit.name, _literal(limit, want))
        if new == text:
            return {"ok": True, "key": key, "from": now, "to": want,
                    "changed": False, "loosening": False}
        data = (b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8")
        fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp",
                                   dir=str(p.parent))
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            try:
                os.chmod(tmp, stat.S_IMODE(os.stat(p).st_mode))
            except OSError:
                pass
            os.replace(tmp, p)
        except OSError as exc:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise SettingsFileError(f"Your settings file could not be written "
                                    f"({type(exc).__name__}), so nothing was changed")
    _reload()
    return {"ok": True, "key": key, "from": now, "to": want, "changed": True,
            "loosening": bool(asks)}


# ---------------------------------------------------------------------------
#   The card a loosening needs, and the route
# ---------------------------------------------------------------------------
_STATE: dict = {"gate": None, "tier_of": None}


def configure(*, gate=None, tier_of=None) -> None:
    """Tests only: stand in for the approval gate and the tier table."""
    _STATE.update(gate=gate, tier_of=tier_of)


def _dep(name: str, default):
    return _STATE.get(name) or default


def _person_said_yes(v) -> bool:
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    import jarvis_gate
    try:
        return str(jarvis_gate.tier_of(action))
    except Exception:
        try:
            return str(jarvis_gate._tiers().get(action, "ask"))
        except Exception:
            return "ask"


def _done_words(limit: Limit, value) -> str:
    """The sentence `change` answers with once it has worked.

    A switch says "on" or "off"; everything else uses the row's own words. The
    two differ because a switch's `words` in the LIST has to read as a state on
    its own ("Be quiet during quiet hours (on your PC)" / "no: ..."), while a
    sentence needs the state after the title ("... is now on"), not repeated."""
    if limit.kind == "bool":
        return f"{limit.title}: {'on' if value else 'off'}."
    return f"{limit.title} is now {limit.words(value)}."


def _loosening_card(limit: Limit, old, new) -> tuple:
    """The card for the direction that loosens, and the yes. (None, said) when
    it went through; ((status, body), "") when it did not.

    The action is the entry's own when it names one, so a loosening that goes
    DOWN is never asked under a name that says "raise"; and the last line is the
    entry's own when it names one, so the card cannot promise "Jarvis does more"
    about a lower bar, which lets more CLIPS through instead."""
    action = limit.asked_action
    prompt = (f"{limit.title}: change it from {_words(old)} to {_words(new)} "
              f"({limit.words(new)})? {limit.card_more or RAISE_MORE}")
    detail = {"text": prompt, "what": limit.title.lower(),
              "was": old, "now": new, "limit": limit.key,
              "leaves_this_pc": False}
    gate = _dep("gate", _gate)
    tier_of = _dep("tier_of", _tier)
    try:
        if tier_of(action) != "ask":
            return (503, {"ok": False, "error": "Your PC's Jarvis cannot ask you about "
                                                "that yet, so nothing was changed."}), ""
        v = gate(action, detail, prompt)
    except Exception:
        return (503, {"ok": False, "error": "Jarvis could not put that to you just now, "
                                            "so nothing was changed."}), ""
    if not _person_said_yes(v):
        outcome = getattr(v, "outcome", None)
        words = {"denied": "You said no, so nothing was changed.",
                 "timed_out": "The card was not answered in time, so nothing was "
                              "changed."}
        return (409, {"ok": False, "error": words.get(
            outcome, "That was not approved, so nothing was changed.")}), ""
    return None, f"{limit.title} is now {limit.words(new)}."


def view(*, app: Optional[str] = None) -> dict:
    """Every limit, with what the owner's file says now and the owner's words.

    `app=None` - what the route asks for - returns EVERY row, each carrying its
    own `app`, so each screen filters on what a row says rather than on a
    filter guessed here. (Both call the same route: the PC's card must see the
    PC-only limits and the phone must not, and neither can be told apart at the
    route without the caller saying so.) `app="desktop"` / `"phone"` narrows it
    here, which is what the tests and the voice lane ask for.

    THE ROW'S SHAPE DOES NOT CHANGE. `loosen_up` keeps exactly the meaning it has
    always had for both apps - "a BIGGER value is this row's loosening" - so the
    voice bar's row, whose loosening goes the other way, says `false` and carries
    its direction in its own `note` instead. Nothing new is sent, so neither
    screen needs a change to draw the new row.

    ONE ADDITIVE FIELD, 2026-10-08: `quiet_on`. The two quiet-hours times are
    the first rows of `kind="time"`, and a time input is worth drawing only
    while quiet hours are on - so each screen that draws a time row asks the
    row beside it whether to show it. `quiet_on` is that answer, sent on EVERY
    row (the same value on each), and it is the only thing this view has ever
    added: an older screen that ignores it draws the times always, which is what
    the desktop's card did before this change and is not wrong, only untidier."""
    quiet_on = bool(value_of(find(NOTIFY_QUIET_ON))) if find(NOTIFY_QUIET_ON) else False
    rows = []
    for limit in (LIMITS if app is None else limits_for(app)):
        now = value_of(limit)
        rows.append({"key": limit.key, "title": limit.title, "kind": limit.kind,
                     "value": now, "words": limit.words(now),
                     "choices": list(limit.choices), "low": limit.low,
                     "high": limit.high, "unit": limit.unit, "note": limit.note,
                     "loosen_up": limit.loosen_up, "pc_only": limit.pc_only,
                     "app": limit.app, "quiet_on": quiet_on})
    return {"ok": True, "available": True, "limits": rows}


def change(body, *, peer=None, local=None) -> tuple:
    """POST /api/limits/settings - {"key": ..., "value": ...}."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "Send the limit you want to change."}
    key = body.get("key")
    if not isinstance(key, str) or "value" not in body:
        return 400, {"ok": False, "error": "Send a limit and the number you want."}
    limit = find(key)
    if limit is None:
        return 400, {"ok": False, "error": "That is not a limit Jarvis knows."}
    if limit.pc_only:
        from_here = True
        try:
            import jarvis_owner_check as OC
            if peer is not None:
                from_here = bool(OC.from_this_pc(peer, local))
        except Exception:
            from_here = peer is None
        if not from_here:
            return 403, {"ok": False, "pc_only": True,
                         "error": "That can only be changed on the PC."}
    try:
        want = _coerced(limit, body["value"])
    except SettingsFileError as exc:
        return 400, {"ok": False, "error": str(exc)}
    now = value_of(limit)
    asks = _is_loosening(limit, now, want)
    said = ""
    if asks:
        refused, said = _loosening_card(limit, now, want)
        if refused is not None:
            return refused
    try:
        out = set_limit(key, want)
    except SettingsFileError as exc:
        return 400, {"ok": False, "error": str(exc)}
    if not said:
        said = _done_words(limit, out["to"])
    return 200, {"ok": True, "key": key, "changed": out.get("changed", True),
                 "loosening": bool(asks), "approved": bool(asks),
                 "from": out.get("from"), "to": out.get("to"), "said": said}


def handle_post(route: str, body, *, peer=None, local=None) -> tuple:
    """The HUD's own route calls this (limits-settings.patch)."""
    if route != ROUTE:
        return 404, {"error": "no such route"}
    return change(body, peer=peer, local=local)
