"""jarvis_feature_guide.py - "what is this feature?", "where is it?", "is it on?"

The owner's request (2026-10-20, after the field test of 2026-10-19/20): "Does
Jarvis ... have the ability to explain the different features the program has
and activate/deactivate them for me?" Chat could already CHANGE 52 settings by
fixed phrases, but it could not explain a single feature, and "is the prompt
coach on?" was answered "I don't know its current state directly". This module
is the missing read half - and it only ever reports facts that are written
down, never a guess:

  * WHAT a feature is, and WHERE it is switched on, come VERBATIM from the
    owner's own feature list (`features/features.json`, 140 rows). The list is
    turned into a shipped Python module by `tools/gen_feature_guide_catalogue.py`
    because features.json itself lives in this repository and is NOT copied to
    the backend folder the PC runs - a module cannot read a file that is not
    there. `backend/test_feature_guide.py` runs the generator's `--check`, so a
    changed list that is not regenerated fails a suite rather than drifting.
    Nothing here rewords it: `what`, `where`, `asks`, `limit` are the list's own
    words. The MODEL side (the `feature_guide` tool) is allowed to reword them;
    it is not allowed to add a fact, and the fixed phrases in jarvis_quick.py
    answer without a model at all.
  * WHICH SWITCH A FEATURE HAS (if any): a feature's `covers` names settings
    places (`settings.prompt-coach`), and `jarvis_settings_registry.BoolSetting`
    already records which on/off switch owns each place. Those are the same
    entries `change_setting` and the fixed "turn on <setting>" phrases use, so
    "is it on?" reads the SAME switch a change would write - never a second
    table that could disagree.
  * IS IT ON RIGHT NOW: read by calling the owning module's own public reader
    (`jarvis_prompt_coach.enabled()`, `jarvis_search.settings()["enabled"]`,
    `jarvis_limits.value_of(...)`, ...). A module that is missing or cannot
    answer returns None, and the answer then SAYS it could not read it - the
    one thing this must never do is claim a state it did not read.
  * NO FEATURE IS INVENTED: an unknown name gets "I do not have that one; here
    are the groups", and an ambiguous one gets the real candidates. There is no
    fuzzy best guess that could hand back a different feature's facts.
  * NINE QUESTIONS, NOT THREE (2026-10-26, the owner's requested field test).
    Besides "what is it?" / "is it on?" / "how do I turn it on?", chat answers
    "what does it do", "tell me about", "explain", "how do I use", "where is"
    and "can I change" - all from the same row, so a feature is never answered
    one way here and another way there. "Can I change it?" comes from the same
    five owner-facing labels and the same switch table `turn on` writes
    through, and changes nothing.
  * THE ANSWER NAMES BOTH APPS. `surface` says which apps have it; when one
    does not, the answer gives the row's own `surface_reason` (written for every
    one-sided row on 2026-10-26), so "the phone does not have it" is never a
    bare claim. A both-apps answer points at the phone's copy of the feature
    list by name, because the row's `where` is written from the PC's side.
  * ALIASES ARE THE OWNER'S OTHER NAMES. A row may carry `aliases` ("customer
    support" for "Deal with customer support for me"); they are matched EXACTLY,
    like the id and the title, so they widen what a person can say without
    widening what counts as a guess.
  * THE TEMPLATE SENTENCES ARE DATA (2026-10-26 semantic read of 20 live
    answers). "A change that loosens a rule still asks on a card first." is
    appended only for a switch in `CARD_ON_LOOSENING` - it was false on manner,
    prompt-coach, write-like-me and pictures - and the Always-On "cannot be
    turned off" sentence is replaced by `ALWAYS_ON_OFF_PATH` for `app-lock`,
    whose rule is also a real switch with an OFF path (Windows Hello). A
    reminder that repeats a claim the app contradicts is not a harmless
    template. The rewording of a Status line from those tables is DISPLAY ONLY,
    exactly like the phone-only one: `label_for()`, the five approved label
    strings and their pinned counts do not move.

WHAT IT DOES NOT DO, said plainly:

  * It does not switch anything by itself. The fixed "turn on <feature>" phrase
    resolves a feature to the ONE switch it names and then goes through
    `BoolSetting.set` - the same setter, card rule and PC-only rule every other
    spoken setting change uses (see jarvis_quick._run_feature_switch).
  * It does not read a setting's state where no public reader exists: it says
    so instead. `read_state()` returning None is an honest "I do not know", not
    an "off".
  * It reads no owner data: the catalogue is the list the Features page shows
    both apps, and the switch reads are the boolean flags Settings draws.
    Standard library only, no network, no card, no route of its own.

Each answer carries a `words` sentence built here from the facts, so the model
has one exact sentence to reword and the fixed phrases have one to say as-is.
"""
from __future__ import annotations

import re

from typing import Optional

try:                                    # shipped beside this module
    import jarvis_feature_catalogue as CATALOGUE
except Exception:                       # noqa: BLE001 - a PC without it says so
    CATALOGUE = None

#: Words that describe the question rather than the feature. Removed before
#: matching, so "what is the prompt coach feature" finds "Prompt coach".
_GENERIC = frozenset({"feature", "features", "jarvis", "setting", "settings",
                      "option", "options", "thing", "mode", "function", "ability"})
#: Leading possessives/articles a person says around a name.
_LEAD = ("the", "my", "a", "an", "your", "this", "that")

#: Words too common to say which feature is meant, for the loose alias search
#: (only used when the question itself says "feature"/"explain").
_STOP = frozenset({"and", "the", "you", "your", "with", "for", "from", "that",
                   "this", "what", "how", "does", "can", "are", "was", "were",
                   "into", "onto", "its", "it", "is", "be", "to", "of", "on",
                   "in", "or", "a", "an", "as", "at", "by", "so", "if", "then",
                   "not", "no", "yes", "me", "my", "if", "when", "where", "why"})

ON_WORD, OFF_WORD = "on", "off"


# --------------------------------------------------------------------------
#   The list and its groups
# --------------------------------------------------------------------------

def features() -> list:
    """Every row, as copies, so a caller cannot change the shipped list."""
    if CATALOGUE is None:
        return []
    return [dict(row) for row in CATALOGUE.FEATURES]


def groups() -> list:
    """[{"group", "count", "ids"}] in the list's own order."""
    out = []
    if CATALOGUE is None:
        return out
    for name in CATALOGUE.GROUPS:
        ids = [r["id"] for r in CATALOGUE.FEATURES if r["group"] == name]
        if ids:
            out.append({"group": name, "count": len(ids), "ids": ids})
    return out


def row_by_id(feature_id: str) -> Optional[dict]:
    for row in features():
        if row["id"] == feature_id:
            return row
    return None


def feature_count() -> int:
    return len(CATALOGUE.FEATURES) if CATALOGUE is not None else 0


# --------------------------------------------------------------------------
#   Matching owner words to a row
# --------------------------------------------------------------------------

def _norm(text) -> str:
    """Lower case, punctuation to spaces, collapsed, leading articles gone."""
    out = "".join(c if (c.isalnum() or c.isspace()) else " " for c in str(text or "").lower())
    words = out.split()
    while words and words[0] in _LEAD:
        words = words[1:]
    return " ".join(words)


#: Words ending in "s" that are not plurals. Without this "this" becomes
#: "thi" and a feature called "Look at this" stops being findable.
_SINGULAR_KEEP = frozenset({"this", "his", "its", "was", "is", "as", "has", "us",
                            "yes", "always", "does", "goes", "news", "series",
                            "species", "physics", "bus", "gas", "plus", "minus"})


def _singular(word: str) -> str:
    """A crude singular for matching only: coaches -> coach, boxes -> box.
    Never used to change a fact or a name."""
    if len(word) < 4 or word in _SINGULAR_KEEP:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "sses", "xes", "zes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tokens(text) -> tuple:
    return tuple(_singular(w) for w in _norm(text).split())


#: Owner names that mean one catalogue row but are NOT in the row's own
#: `aliases` (which stay the list's data to keep). They are matched exactly,
#: like an alias, so they can only ever resolve to that one row - never a
#: guess from a shared word. "Today board" is the owner's name for the "Today"
#: row (the live audit of 2026-10-31 asked about it); "quiet hours", "thinking
#: level", "personality" and "memories" are the settings-shaped names the same
#: audit found the model mis-describing.
_OWNER_ALIASES = {
    "today": ("today board",),
    "notifications": ("quiet hours", "notification settings", "do not disturb"),
    "attention-budget": ("interruption level",),
    "memory-saved": ("memories", "saved memories"),
    "memory-known": ("what you remember about me", "memory list"),
}


def _row_aliases(row: dict) -> tuple:
    """The row's own aliases plus the owner names this module knows for it."""
    return tuple(row.get("aliases") or ()) + tuple(_OWNER_ALIASES.get(row["id"], ()))


def _name_tokens(row: dict) -> tuple:
    out = _tokens(row["id"].replace("-", " ")) + _tokens(row["title"])
    for alias in _row_aliases(row):
        out += _tokens(alias)
    return out


def _extra_tokens(row: dict) -> tuple:
    """Words from `what`/`where`: aliases the owner may use ("the coach
    button"), only consulted when the question says "feature"/"explain"."""
    out = []
    for key in ("what", "where"):
        for word in _tokens(row.get(key) or ""):
            if len(word) >= 4 and word not in _STOP:
                out.append(word)
    for alias in _row_aliases(row):
        for word in _tokens(alias):
            if len(word) >= 4 and word not in _STOP:
                out.append(word)
    return tuple(out)


def _query(words, *, loose: bool) -> tuple:
    """(tokens, wants_feature) for a piece of owner text."""
    text = _norm(words)
    wants_feature = any(w in _GENERIC for w in text.split())
    got = tuple(_singular(w) for w in text.split() if w not in _GENERIC)
    if not loose:
        return got, wants_feature
    return got, wants_feature


def _exact(row: dict, query: str) -> bool:
    """Does `query` name this row exactly - its id, its title, or an alias?

    `aliases` are the other names a person says for ONE feature: "customer
    support" for the row whose title is "Deal with customer support for me".
    They are matched EXACTLY, like the id and the title, never as a substring,
    so a general question cannot be answered with a feature's facts.
    """
    if query in (_norm(row["id"].replace("-", " ")), _norm(row["title"])):
        return True
    return any(query == _norm(alias) for alias in _row_aliases(row))


def _contains_all(have: tuple, want: tuple) -> bool:
    return all(w in have for w in want)


def find(words, *, loose: bool = False) -> dict:
    """What the owner's words name, from the list alone.

    Returns one of:
      {"kind": "feature", "row": row}
      {"kind": "group", "group": name, "rows": [rows]}
      {"kind": "ambiguous", "rows": [up to 6 rows]}
      {"kind": "unknown"}
    `loose`: also allow the feature's `what`/`where` words as aliases (only for
    a question that itself says "feature"/"explain", so "what is the weather"
    cannot be turned into a feature answer by a word in a row's prose).
    """
    query = _norm(words)
    if not query:
        return {"kind": "unknown"}
    rows = features()
    if not rows:
        return {"kind": "unknown"}
    # 1. The id or the title, exactly.
    for row in rows:
        if _exact(row, query):
            return {"kind": "feature", "row": row}
    # 2. The group's own name, exactly - or once the question's own words are
    # taken off ("what is in the memory group" -> "memory").
    for group in groups():
        if _norm(group["group"]) == query:
            return {"kind": "group", "group": group["group"],
                    "rows": [r for r in rows if r["group"] == group["group"]]}
    query_words, wants_feature = _query(words, loose=loose)
    if query_words:
        joined = " ".join(query_words)
        for group in groups():
            if _norm(group["group"]) == joined:
                return {"kind": "group", "group": group["group"],
                        "rows": [r for r in rows if r["group"] == group["group"]]}
    if not query_words:
        return {"kind": "unknown"}

    def hits_of(want: tuple) -> list:
        return [r for r in rows if _contains_all(_name_tokens(r), want)]

    hits = hits_of(query_words)
    if not hits:
        # A joining word the list's own name does not use: "timers AND
        # reminders" still finds "Timers, alarms, reminders and lists". Only
        # from TWO content words up: one common noun ("weather", "memory") is
        # how a different question starts, and is not turned into a feature.
        short = tuple(w for w in query_words if w not in _STOP)
        if len(short) >= 2 and short != query_words:
            got = hits_of(short)
            if len(got) == 1:
                return {"kind": "feature", "row": got[0]}
            hits = got
    if len(hits) == 1:
        return {"kind": "feature", "row": hits[0]}
    if len(hits) > 1:
        # A word shared by several names: prefer the name whose own words are
        # fewest ("manner" beats a long title that only mentions the manner).
        # Two equally short names are reported as ambiguous, never guessed.
        hits.sort(key=lambda r: len(_name_tokens(r)))
        if len(_name_tokens(hits[0])) == len(_name_tokens(hits[1])):
            return {"kind": "ambiguous", "rows": hits[:6]}
        return {"kind": "feature", "row": hits[0]}
    if loose and wants_feature:
        hits = [r for r in rows
                if _contains_all(_name_tokens(r) + _extra_tokens(r), query_words)]
        if len(hits) == 1:
            return {"kind": "feature", "row": hits[0]}
        if hits:
            return {"kind": "ambiguous", "rows": hits[:6]}
    return {"kind": "unknown"}


def find_feature(words, *, strong: bool = True):
    """The one FEATURE row a question names, or None (never a group/guess).

    `strong` (the fixed phrases' rule): the name has to be the row's exact id
    or title, or share at least TWO of the row's own words. A single common
    noun - "weather", "memory" - is how a different question starts, so the
    phrase grammar falls through to the model/other paths there rather than
    answering a different question with a feature's facts. The tool keeps the
    looser `find()` because its caller has already said "feature".
    """
    got = find(words, loose=False)
    if got["kind"] != "feature":
        return None
    row = got["row"]
    if not strong:
        return row
    query = tuple(w for w in _query(words, loose=False)[0] if w not in _STOP)
    if len(query) >= 2:
        return row
    if _exact(row, _norm(words)):
        return row
    return None


def find_exact(words):
    """The one feature whose own name IS `words`, or None.

    THE FIXED PHRASES' GATE (Gemini's review, 2026-10-20, section 11.8.3).
    The spoken grammar must not swallow a general question, so a sentence with
    no explicit Jarvis context ("here", "my settings", or the name "Jarvis")
    only answers when the subject after "what is [the] ..." / "is [the] ... on"
    is EXACTLY a catalogue name - case, punctuation and a leading article are
    ignored, and nothing else is. No substring, no shared words:

      "what is the prompt coach"           -> the row (exact title)
      "what is a focus session"            -> the row (exact title)
      "what is a focus session in psychology" -> None, falls to the model
      "how do I turn on dark mode in chrome"  -> None, falls to the model

    A row's names here are its exact id (with hyphens read as spaces) and its
    exact title; the looser matching in `find()`/`find_feature()` is kept for
    the model's own tool, whose caller has already said "feature"."""
    query = _norm(words)
    if not query:
        return None
    for row in features():
        if _exact(row, query):
            return row
    return None


# --------------------------------------------------------------------------
#   Which switch (if any) a feature has, and what it reads right now
# --------------------------------------------------------------------------

#: How each switch's state is read: the owning module's own public reader, the
#: same place the Settings screen and the setter read it. Each entry returns
#: True/False, or raises (caught below) - never a guessed default. A module
#: that is not on this PC makes the answer "I could not read it", not "off".
def _read_prompt_coach():
    import jarvis_prompt_coach as M
    return M.enabled() is True


def _read_handsfree():
    """Hands-free mode's one switch (2026-11-04, jarvis_handsfree.py).

    Read from the module itself, never from a copy of the rule: `enabled()`
    fails to OFF, so a settings file that cannot be read can never teach this
    answer that the mode is on."""
    import jarvis_handsfree as M
    return M.enabled() is True


def _read_antislop():
    """The Anti-Slop filter's master switch (2026-10-28).

    Read from the module itself, never from a copy of the rule: OFF is also
    what a PC that cannot answer reads as far as `read_state` is concerned, and
    `A.is_enabled()` fails to OFF - so a damaged file can never read as "on".
    """
    import jarvis_antislop as M
    return M.is_enabled() is True


def _read_jarvis_calendar():
    """The Jarvis calendar's switch (2026-10-29): ON when no file says otherwise.

    Read from the module itself. A damaged settings file reads OFF there (with
    a reason the route carries), which is the safe direction for "is it on?".
    """
    import jarvis_local_calendar as M
    return M.is_on() is True


def _read_auto_learn(key: str):
    import jarvis_auto_learn as M
    return M.settings().get(key) is True


def _read_lights_without_card():
    import jarvis_asks_first as M
    return (M.view().get("lights") or {}).get("on") is True


def _read_search(flag: str):
    import jarvis_search as M
    return M.settings().get(flag) is True


def _read_notify(flag: str):
    import jarvis_limits as M
    limit = M.find(flag)
    return None if limit is None else M.value_of(limit) is True


def _read_wifi_auto_reconnect():
    """The auto Wi-Fi reconnect's switch (2026-11-08, owner ruling Q4).

    Read from the module itself, never from a copy of the rule: `enabled()`
    reads a missing or damaged settings file as OFF (the safe direction for
    "is it on?"), and a module that cannot answer reads as "I could not read
    it", never as off."""
    import jarvis_wifi as M
    return M.enabled() is True


def _read_watch_notify():
    import jarvis_watch_notify as M
    return M.settings().get("enabled") is True


def _read_phone_notifications():
    import jarvis_phone_notifications as M
    return M.settings().get("enabled") is True


def _read_screen_picture():
    import jarvis_screen_picture as M
    return M.settings().get("enabled") is True


def _read_headless_browser():
    import jarvis_browser_engine as M
    return M.settings().get("obscura") is True


def _read_pictures():
    # Read through the settings registry: it is the one module allowed to
    # import jarvis_pictures (test_pictures.py's pin keeps the drawing module
    # out of every model turn's reach), so the Feature Guide asks it instead.
    import jarvis_settings_registry as R
    return R.pictures_on()


def _read_briefing_senders():
    import jarvis_briefing as M
    return M.senders_status().get("on") is True


def _read_humor():
    import jarvis_manner as M
    return M.view().get("humor") is True


def _read_voice_follows_face():
    import jarvis_voices as M
    return ((M.status().get("face_voice") or {}).get("enabled")) is True


def _read_better_voice():
    import jarvis_voices as M
    return ((M.status().get("better_voice") or {}).get("enabled")) is True


def _read_one_moment():
    """2026-11-01: "Say \"One moment\" if I'm kept waiting", read from the module
    that owns it - `one_moment_enabled()`, the same value `/api/voice/status`
    reports and both apps gate the clip on (the TOML switch AND the owner's own
    answer). Never a second copy of the rule: the ordering above it is the
    module's own."""
    import jarvis_voice_flow as M
    return M.one_moment_enabled() is True


def _read_voice_check_locked():
    """2026-11-03: "Only check my voice on a locked phone", read from the
    module that owns the rule - jarvis_live.voice_check_setting() is the same
    answer `GET /api/voice/live` reports and the same one
    jarvis_live.voice_check_needed() acts on, never a second copy. ON is the
    exemption (the default); OFF gives the full checks back."""
    import jarvis_live as M
    return M.voice_check_setting() is True


def _read_sandbox():
    import jarvis_sandbox_exec as M
    return M.enabled() is True


def _read_big_coder():
    import jarvis_big_coder as M
    return M.enabled() is True


def _read_media_index():
    """F5 S2 (2026-10-19): the owner's own "searchable recordings" switch,
    read from the module that owns it - never a second copy of the rule."""
    import jarvis_media_index as M
    return M.enabled() is True


# --- the universal-control pass (2026-10-22) ------------------------------
# Each of these reads the switch's own public answer, the same one its
# Settings/Brain control reads. None is guessed: a module that is absent or
# cannot answer raises, and read_state turns that into an honest None.

def _read_chat_history():
    import jarvis_chat_log as M
    return M.status().get("enabled") is True


def _read_write_like_me():
    import jarvis_voiceprint as M
    return M.status().get("enabled") is True


def _read_big_model():
    import jarvis_big_model as M
    return M.status().get("enabled") is True


def _read_big_model_job(job: str):
    def reader():
        import jarvis_big_model as M
        for row in M.status().get("switches") or ():
            if isinstance(row, dict) and row.get("id") == job:
                return row.get("enabled") is True
        raise LookupError(job)
    return reader


def _read_second_card_combined():
    """Read through the module's OWN public reader (2026-11-02).

    The old reader parsed `M.status()["features"]` as a dict keyed by feature
    id, and looked for "combined" in it. The module changed shape underneath
    it: `status()` has no "features" key at all any more, the features are a
    LIST of rows under FEATURE_IDS, and "combined" was never one of them - it
    is a sibling of `master`, not a feature. So the reader raised, read_state
    said None, and the Feature Guide answered "I could not read The second
    graphics card's switch" for a card whose state the module reports fine.
    `switch_enabled()` is the reader the module itself now exposes for exactly
    this question: the same state file and the same defaults its own setters
    use, and an unknown name raises rather than answering "off".
    """
    import jarvis_second_card as M
    return M.switch_enabled("combined") is True


def _read_second_card_suggest(signal: str):
    """Read one suggestion signal through `suggest_setting()` (2026-11-02).

    The old reader looked for `suggest_settings()["switches"]`, which does not
    exist: that answer is `{available, title, detail, signals:[{id, enabled}]}`
    - the rows are `signals`, not `switches`. Every second-card suggestion
    therefore read as None. `suggest_setting(signal)` is the module's own
    public reader for one signal, and it applies the same default the switch
    does (both suggestions ON when the state file is missing or damaged).
    """
    def reader():
        import jarvis_second_card as M
        return M.switch_enabled(signal) is True
    return reader


#: BoolSetting.key -> the reader above. One entry per switch in
#: jarvis_settings_registry.BOOL_SETTINGS; `test_feature_guide.py` fails if a
#: switch is added to that table without a reader here, so "is it on?" can
#: never silently answer for only some of the switches.
STATE_READERS = {
    "background_learning": lambda: _read_auto_learn("auto"),
    "learn_sensitive_topics": lambda: _read_auto_learn("auto_sensitive"),
    # 2026-11-02: "Save facts even when Jarvis had to reword them".
    "learn_paraphrase": lambda: _read_auto_learn("auto_paraphrase"),
    "lights_without_card": _read_lights_without_card,
    "prompt_coach": _read_prompt_coach,
    "handsfree": _read_handsfree,
    "antislop": _read_antislop,
    "jarvis_calendar": _read_jarvis_calendar,
    "ask_before_every_search": lambda: _read_search("ask_every_time"),
    "web_search": lambda: _read_search("enabled"),
    "smartwatch_notifications": _read_watch_notify,
    "phone_notifications": _read_phone_notifications,
    "screen_picture": _read_screen_picture,
    "headless_browser": _read_headless_browser,
    "sandbox_exec": _read_sandbox,
    "media_index": _read_media_index,
    "pictures": _read_pictures,
    "briefing_senders": _read_briefing_senders,
    "big_coder": _read_big_coder,
    "pc_alarm_sounds": lambda: _read_notify("notif_alarms"),
    "pc_reminder_sounds": lambda: _read_notify("notif_reminders"),
    "pc_briefing_notification": lambda: _read_notify("notif_briefing"),
    "pc_handoff_notification": lambda: _read_notify("notif_handoff"),
    # Wave B, "Personalize Jarvis" (2026-11-03): the reminder that the quiz is
    # still unfinished. Read through the same limits row the card writes.
    "pc_setup_notification": lambda: _read_notify("notif_setup"),
    "pc_quiet_hours": lambda: _read_notify("notif_quiet_enabled"),
    "humor": _read_humor,
    "voice_follows_face": _read_voice_follows_face,
    "better_voice": _read_better_voice,
    # The universal-control pass (2026-10-22). One entry per switch added to
    # jarvis_settings_registry.BOOL_SETTINGS - the suite fails if one is
    # missing, so "is it on?" never answers for only some of the switches.
    "chat_history": _read_chat_history,
    "write_like_me": _read_write_like_me,
    "big_model": _read_big_model,
    "big_model_wiki": _read_big_model_job("wiki"),
    "big_model_deep_questions": _read_big_model_job("deep_questions"),
    "second_card_combined": _read_second_card_combined,
    "second_card_suggest_struggle": _read_second_card_suggest("struggle"),
    "second_card_suggest_correction": _read_second_card_suggest("correction"),
    # 2026-11-01: "Say \"One moment\" if I'm kept waiting" became a real switch
    # by asking (the owner's own ask), so it needs its state reader like every
    # other switch in the table above.
    "one_moment": _read_one_moment,
    # 2026-11-03: "Check my voice when my phone is locked" (the owner's ask).
    # Its one rule lives in jarvis_live.voice_check_needed(); this reads the
    # same answer the PC acts on, never a second copy.
    "voice_check_locked": _read_voice_check_locked,
    # 2026-11-08: the auto Wi-Fi reconnect (owner ruling Q4) is a registry
    # switch, so it gets its state reader here like every other one - "is
    # auto wifi reconnect on?" answers from the module's own enabled().
    "wifi_auto_reconnect": _read_wifi_auto_reconnect,
}


def read_state(setting_key: str) -> Optional[bool]:
    """The switch's current value, or None when it cannot be read here.

    None is an honest "I do not know": a missing module, a damaged settings
    file or a reader that raises all land here, and no answer says on/off from
    a None."""
    reader = STATE_READERS.get(str(setting_key or ""))
    if reader is None:
        return None
    try:
        value = reader()
    except Exception:                       # noqa: BLE001 - said as "could not read"
        return None
    return value if isinstance(value, bool) else None


def _registry():
    try:
        import jarvis_settings_registry as R
        return R
    except Exception:                       # noqa: BLE001
        return None


#: Feature id -> switch keys the feature's `covers` section links that are NOT
#: its own control. A section can hold two unrelated switches, and the section
#: link alone cannot tell them apart.
#:
#: `anti-slop` (measured 2026-11-02): its row covers `settings.manner` because
#: the filter is switched on the How Jarvis talks card, and that card also holds
#: the HUMOUR switch. `antislop`'s own BoolSetting carries section None (it is
#: not a section switch), so the section link found `humor` and missed the real
#: one: "is the Anti-Slop filter on?" answered "on right now (humour)" and "turn
#: on the anti-slop filter" resolved to the humour setter. The row's own switch
#: is linked by `EXTRA_CONTROLS` below; this entry drops the section-mate.
#: Every key here must be a real switch in the row's own sections, and the row
#: must still name one switch afterwards - `test_feature_guide.py` checks both,
#: so the entry cannot quietly remove a row's only control.
SECTION_MATES_NOT_THIS_FEATURE = {
    "anti-slop": ("humor",),
}


def switches_for(row: dict) -> list:
    """The BoolSetting objects this feature's OWN controls are.

    The link starts with the feature list's own `covers` (`settings.<section
    id>`) and BoolSetting.section - the same section ids `jarvis_quick` opens
    by name - and is then corrected twice, because a section link alone can be
    wrong in both directions:

      * a switch whose BoolSetting has NO section (its control is drawn inside
        another card) is linked by hand in `EXTRA_CONTROLS`, exactly as the
        read path always did. Without this, the answer said "say turn on write
        like me" while `switch_target()` refused the same phrase as a
        "Command-Only ability" (write-like-me, lights, picture-mode), and
        anti-slop read the humour switch instead of its own filter. Measured
        2026-11-02 on this tree.
      * a section can hold a DIFFERENT feature's switch as well; those are
        named in `SECTION_MATES_NOT_THIS_FEATURE` and dropped.

    An Always-On SAFETY RULE owns no switch (ALWAYS_ON_IDS, Lead's 2026-10-22
    ruling): "Lock Jarvis" (app-lock) and the chat-history switch both live in
    Settings, Security, so without that an Always-On title would find one
    switch in its section and "turn on Lock Jarvis" would have turned chat
    history on (2026-10-28, caught by tools/check_feature_controls.py guard 2).
    `_build_matrix` clears them again for the same reason; this keeps every
    other caller - including jarvis_quick.switch_target - on the same rule."""
    R = _registry()
    if R is None or not row:
        return []
    fid = str(row.get("id") or "")
    if fid in ALWAYS_ON_IDS:
        return []
    covers = set(row.get("covers") or ())
    out = []
    for setting in R.BOOL_SETTINGS:
        section = getattr(setting, "section", None)
        if section and f"settings.{section}" in covers:
            out.append(setting)
    for key in EXTRA_CONTROLS.get(fid, ()):     # links the covers cannot name
        if key not in [s.key for s in out]:
            setting = _setting_by_key(key)
            if setting is not None:
                out.append(setting)
    mates = SECTION_MATES_NOT_THIS_FEATURE.get(fid, ())
    if mates:
        out = [s for s in out if s.key not in mates]
    return out


def _setting_words(setting) -> str:
    """What a switch is called in plain words (its first name)."""
    names = getattr(setting, "names", ()) or ()
    return str(names[0]) if names else str(setting.key)


def _setting_by_key(key: str):
    R = _registry()
    if R is None:
        return None
    return next((b for b in getattr(R, "BOOL_SETTINGS", ())
                 if b.key == str(key or "")), None)


def _matrix_row(row: dict):
    """This feature's control-matrix row (cached), or None."""
    global _MATRIX_BY_ID
    fid = str((row or {}).get("id") or "")
    if _MATRIX_CACHE is None:
        _matrix()
    if _MATRIX_BY_ID is None:
        _MATRIX_BY_ID = {r["id"]: r for r in (_MATRIX_CACHE or [])}
    return _MATRIX_BY_ID.get(fid)


def feature_switches(row: dict) -> list:
    """[{"key","label"}] - the switches the READ answers name for this row.

    The control matrix's `switch_keys` is the authority, not `covers` alone: a
    few rows' switch is linked by hand in `EXTRA_CONTROLS` (Memory saved ->
    Background learning, Your past chats -> Chat history), and `covers` cannot
    name them. Using the matrix keeps "is it on?" and "can I change it?" naming
    the SAME switch the five labels are built from. `switches_for()` - the
    write path's rule - now reads `EXTRA_CONTROLS` and the section-mate
    exclusions too (2026-11-02), so `switch_target()` resolves the same switch
    the answer names rather than refusing a phrase this answer just gave.
    """
    mine = _matrix_row(row)
    keys = list((mine or {}).get("switch_keys") or [])
    if keys:
        out = []
        for key in keys:
            setting = _setting_by_key(key)
            out.append({"key": key,
                        "label": _setting_words(setting) if setting is not None
                                 else str(key).replace("_", " ")})
        return out
    return [{"key": s.key, "label": _setting_words(s)} for s in switches_for(row)]


def _switch_state_rows(row: dict) -> list:
    out = []
    for setting in feature_switches(row):
        out.append({"key": setting["key"], "label": setting["label"],
                    "state": read_state(setting["key"])})
    return out


PHONE_FEATURES_PAGE = ("The phone lists it in the same feature list, under Brain, "
                       "\"See every feature\".")


def surface_words(row: dict) -> str:
    """Which app(s) have it, and - when one does not - the row's own reason.

    The reason is the feature list's `surface_reason`, written for every
    one-sided row on 2026-10-26 (the desktop-only rows gained theirs then). When
    a row has no reason the answer says that plainly rather than inventing one.
    """
    surface = str(row.get("surface") or "")
    if surface == "both":
        return ("It is in both apps - the PC and the phone. " + PHONE_FEATURES_PAGE)
    reason = str(row.get("surface_reason") or "").strip()
    if surface == "desktop":
        line = "It is on the PC only"
    elif surface == "phone":
        line = "It is on the phone only"
    else:
        return ""
    if reason:
        return f"{line}: {reason}"
    return f"{line}, and the feature list does not record why the other app has none."


#: Control-matrix `status` values that mean a REAL control exists for the row
#: even though no boolean switch could be read for it: the control is a typed
#: adjust phrase ("adjust"), a Settings screen ("open-only") or a switch the
#: matrix links but this build cannot read for this row ("switch"). Everything
#: else - "planned", "not-a-setting" - really has no on/off to report.
_HAS_A_CONTROL = frozenset({"switch", "adjust", "open-only"})

#: THE AI-TOOL SWITCH PLACE, and the rows whose own `where` names it. Since the
#: owner's decision of 2026-11-04 every tool the AI model can be offered has its
#: own switch on Settings, "What asks first", under "Let the AI use this"
#: (jarvis_asks_first.tools_status). That is NOT a BoolSetting, so `covers`
#: cannot name it and `feature_switches()` cannot see it - and the answer said
#: "The feature list names no on/off switch for it" DIRECTLY beside a `where`
#: that says "switch it on" (measured 2026-11-07, the four-way contradiction in
#: the github-research answer). These rows are read from the same page the apps
#: draw instead: `TOOL_SWITCHES` is the rows where the exact tool is known, so
#: the live state can be read; a row that only names the place still gets an
#: honest sentence, never the "no switch" falsehood.
TOOL_SWITCH_PLACE = "let the ai use this"
TOOL_SWITCHES = {
    # The GitHub research tool (jarvis_agent TOOLS "github_search"; its switch
    # title is "GitHub research" in jarvis_asks_first.tools_status).
    "github-research": ("github_search",),
    # The sixteen on-demand tools: one switch each, all off by default. The list
    # is every model tool in the connected surface, because the row's own `where`
    # names all sixteen - a short list here said "six switches" for a surface
    # with ten (measured 2026-11-10, the 2026-11-07 miss, wave 16's three and
    # the 22:30 ruling's six).
    "connected-github": ("github_list", "github_read_file", "github_ci_status",
                         "github_comment", "github_open_issue",
                         "github_rerun_workflow", "github_create_repo",
                         "github_pr_scan", "github_merge_pr",
                         "github_fix_and_push", "github_pr_detail",
                         "github_open_pr", "github_workflow",
                         "github_issue_labels", "github_edit_pr",
                         "github_pr_review", "github_issue_state"),
}


def _names_tool_switch(row: dict) -> bool:
    """Does this row's own `where` say it is switched on in that page?"""
    if not row:
        return False
    if str(row.get("id") or "") in TOOL_SWITCHES:
        return True
    return TOOL_SWITCH_PLACE in str(row.get("where") or "").lower()


def _tool_switch_rows(row: dict) -> list:
    """[{"key","label","state"}] for a row switched on by AI-tool switches.

    Read from `jarvis_asks_first.tools_status()` - the same read the Settings
    page and both apps use - so the state is never typed here. A module that is
    missing or does not answer leaves `state` None and the sentence says so.
    """
    keys = TOOL_SWITCHES.get(str((row or {}).get("id") or "")) or ()
    if not keys:
        return []
    labels, states = {}, {}
    try:
        import jarvis_asks_first as AF
        view = AF.tools_status(here=False)
        for item in view.get("items") or ():
            key = str((item or {}).get("id") or "")
            labels[key] = str(item.get("title") or key)
            states[key] = item.get("on")
    except Exception:                       # noqa: BLE001 - older PC: read nothing
        labels, states = {}, {}
    out = []
    for key in keys:
        state = states.get(key)
        out.append({"key": key, "label": labels.get(key, str(key)),
                    "state": state if isinstance(state, bool) else None})
    return out


def _tool_switch_words(row: dict) -> str:
    """The honest switch sentence for a row switched on by AI-tool switches.

    One known switch says its name and live state; several say each one; a row
    whose tool is not recorded says the place and that it cannot read which
    tool it is - never "there is no switch", which the row's own `where`
    contradicts.
    """
    if not _names_tool_switch(row):
        return ""
    place = ('Settings, What asks first, under "Let the AI use this"')
    switches = _tool_switch_rows(row)
    known = [s for s in switches if isinstance(s["state"], bool)]
    if len(switches) == 1 and len(known) == 1:
        return (f'Its own switch is "{switches[0]["label"]}" in {place}; right now '
                f'it is {ON_WORD if known[0]["state"] else OFF_WORD}.')
    if switches and known:
        said = ", ".join(f'"{s["label"]}" is {ON_WORD if s["state"] else OFF_WORD}'
                         for s in known)
        return f'Its own switches are in {place}: {said} right now.'
    if switches:
        return (f'Its own switches are in {place}; I could not read their live '
                f'state, so I will not say whether they are on.')
    return (f'Its own switch is in {place}; the feature list does not record which '
            f'tool it is, so I could not read its state from chat.')


def _no_switch_words(row: dict) -> str:
    """What to say when `feature_switches(row)` named no readable switch.

    THE HONEST SPLIT (2026-11-04 self-awareness audit, "knows partly"). 43 of
    the 175 features carry the Switchable/Adjustable label, and 43 - 24 = 19 of
    them have no boolean switch the read path can resolve: their control is a
    typed adjustment, a Settings screen, or a planned row. The old sentence
    said "The feature list names no on/off switch for it" for ALL of them,
    which reads as "there is nothing to set" for features that really do have
    a control (topics, focus presets, reach, limits, captcha hand-off...).

    The control matrix already knows which is which (`status`), so this reads
    that rather than a second list: a row with a real control gets the honest
    "I cannot read that switch from chat", with the place and, where the matrix
    has one, the exact phrase the owner can type. A row that really has no
    on/off keeps the old, true sentence.
    """
    mine = _matrix_row(row) or {}
    status = str(mine.get("status") or "")
    tool_words = _tool_switch_words(row)
    if tool_words:
        # A row the AI-tool switch page really does hold: the "no switch"
        # sentence would contradict the row's own `where` (2026-11-07).
        return tool_words
    if status not in _HAS_A_CONTROL:
        return ("The feature list names no on/off switch for it, so there is no "
                "state for me to read.")
    where = str(mine.get("where") or row.get("where") or "").strip()
    said = "I could not read a live on/off for it from chat."
    phrase = ""
    for adjust in mine.get("adjust") or ():
        phrase = str((adjust or {}).get("phrase") or "").strip()
        if phrase:
            break
    if phrase:
        said += f' To change it, say "{phrase}".'
    elif where:
        said += f" To change it, use the control at {where}"
        said += "" if said.endswith(".") else "."
    return said


def _planned_reason(row: dict) -> str:
    """Why this row is still marked planned - its own table's words, never a new guess.

    THE WAKE-WORD LIE (2026-11-13). A planned row has no phrase the matrix can
    prove, so three answer paths (`state()`, `how_to()` and
    `ability_explanation()`) fell through to "The feature list names no on/off
    switch ... Command-Only ... no fixed sentence". The wake-word row's own
    `where` said "Turn it on in Settings, Voice, then tap Listen on the phone"
    while the answer said there was nothing to turn on - and "turn on the wake
    word" worked. Read-aloud's row says the same thing today (its Settings
    switch ships; only the registry phrase is missing). So a planned row now
    says the TYPED path is not wired yet, in its own PLANNED_SWITCHABLE reason,
    and never that the feature has no switch.
    """
    mine = _matrix_row(row) or {}
    return (str(mine.get("reason") or "").strip()
            or "no own typed control is wired for it yet.")


def _state_clause(rows: list, row: Optional[dict] = None) -> str:
    """One plain sentence about the switches, or the honest no-reader sentence."""
    if not rows:
        return _no_switch_words(row or {})
    known = [(r, r["state"]) for r in rows if isinstance(r["state"], bool)]
    unknown = [r for r in rows if not isinstance(r["state"], bool)]
    if not known:
        return ("I could not read its switch on this PC, so I am not going to say "
                "whether it is on.")
    parts = [f"{r['label']} is {ON_WORD if state else OFF_WORD}" for r, state in known]
    said = "Right now, " + "; ".join(parts) + "."
    if unknown:
        said += (" I could not read " + ", ".join(r["label"] for r in unknown)
                 + " on this PC.")
    return said


# --------------------------------------------------------------------------
#   The answers
# --------------------------------------------------------------------------

def _limit_words(row: dict) -> str:
    limit = str(row.get("limit") or "").strip()
    return limit if limit else "The feature list gives no limit for this one."


def _example_words(row: dict) -> str:
    """One real sentence to use it, or the honest "none is pinned"."""
    phrase = EXAMPLE_PHRASES.get(str(row.get("id") or ""))
    if phrase:
        return f'Say, for example: "{phrase}".'
    return "Ask for it in your own words when you want it."


def _phone_settings_words(row: dict) -> str:
    """The phone's own Settings place, named from the row's own `where`.

    The row's `where` starts with "Settings, " on every phone row, and the
    sentence around this already says Settings, so the leading word is dropped
    rather than reading "Settings, Settings, ...".
    """
    where = str(row.get("where") or "").strip()
    head, sep, rest = where.partition(",")
    if head.strip().lower() == "settings" and sep:
        where = rest.strip()
    if where and not where.endswith("."):
        where += "."
    return f"the phone's own Settings, {where}"


#: The phone-only rows whose feature the PC ALSO has, as a DIFFERENT control.
#: Each row's own `surface_reason` says so - "the desktop's frame-rate setting is
#: the animal's, a different thing" (phone-screen-rate) - so "The PC does not have
#: that control" contradicted the surface line printed in the same answer
#: (2026-10-26, part B). The PC's control is not this setting, and the row's
#: `where` names only the phone's.
#:
#: phone-floating was here until 2026-10-29; the settings wrong-app audit
#: (finding 6) found the row was not phone-only at all - the PC's floating face is
#: a toggle inside Appearance - so it is `surface: "both"` now and this map is
#: never asked about it.
PHONE_PC_COUNTERPART = {
    "phone-screen-rate": "The PC's frame-rate setting is the animal's, a different control.",
}


def _phone_pc_claim(row: dict) -> str:
    """What this phone row says about the PC's own side, from the row's data."""
    return PHONE_PC_COUNTERPART.get(
        str(row.get("id") or ""), "The PC does not have that control.")


def phone_change_words(row: dict) -> str:
    """How a PHONE-ONLY row is changed: on the phone, never "on this PC".

    Four rows (phone-notifications, phone-watch, phone-tiles, phone-screen-rate)
    carry the PC-Only label because the phone is the only app with the control,
    and `_label_from` picks that label from the row's reason without looking at
    `surface`. The label's own words therefore said "on this PC" for rows the PC
    does not have at all (2026-10-26 review, F3). The row's `surface` wins, and
    the row's own `where` names the place. phone-floating was the fifth until
    2026-10-29: the settings wrong-app audit (finding 6) found the PC really does
    have a floating face - the toggle inside Appearance - so that row is `both`
    now and never reaches this sentence.

    The closing claim about the PC is per row (`_phone_pc_claim`): three of the
    four really have no PC control, and saying so for the other one would
    contradict the surface line in the same answer.
    """
    return (f"It is changed in {_phone_settings_words(row)} "
            f"{_phone_pc_claim(row)}")


def both_pc_change_words(row: dict) -> str:
    """How a row BOTH apps have, whose CONTROL lives in the PC's Settings, changes.

    Four rows (chat-thread, connection, appearance, faces) are `surface: "both"`
    and carry the PC-Only label because the SETTING CONTROL is the PC's, not the
    feature. Read out of the label alone, the sentence said "It is changed at
    Settings, a new conversation starts after on this PC; the phone says so
    rather than pretending it changed" (2026-10-26, part B): the place was glued
    to "on this PC" with no sentence of its own, and the label's own words told
    the owner the phone lacked a feature both apps have. The row's `surface`
    decides now: the setting is the PC's, and the phone does not change it. It
    does not claim the phone has no control it might have - only that THIS
    setting is the PC's (the contract's own reason for these rows is "no backend
    route to change it").

    THREE rows are the exception, and their sentence is replaced rather than
    softened for all of them: the phone's Appearance screen really does write the
    SHARED document - it picks a face and pushes it, and the desktop adopts it
    (2026-10-26 semantic read, finding 3) - and the phone's Floating Jarvis card
    really does turn its own bubble on. See BOTH_PHONE_WRITES.
    """
    fid = str(row.get("id") or "")
    if fid in BOTH_PHONE_WRITES:
        return (f"Its setting is in {settings_path_words(row)}. "
                f"{BOTH_PHONE_WRITES[fid]}")
    return (f"Its setting is in {settings_path_words(row)}. It is changed on the "
            f"PC; the phone has the feature but cannot change the PC's setting.")


def change_words(row: dict) -> str:
    """How to use, turn on, or change this feature - never an invented switch.

    A PHONE-ONLY row is answered from its `surface` BEFORE the label: the label
    says PC-Only for the five phone controls (the phone is the only app with a
    control), and reading that label's words out loud told the owner to change a
    phone setting "on this PC" (2026-10-26 review, F3). A row BOTH apps have is
    answered from its `surface` too, for the same reason: its control is the
    PC's, and the phone is not said to lack the feature. No label count changes.

    The five owner-facing labels decide the rest of the shape, so this can never
    call a Command-Only ability a switch or a safety rule a setting:

      * Switchable / Adjustable - the exact phrase for the ONE switch, or the
        names of the several (nothing changes until one is named). A row whose
        typed control is still planned says so instead of naming a phrase.
      * Always On - cannot be turned off; its approved exception is named.
      * Settings-Only / PC-Only - the exact Settings place, and which app may
        change it.
      * Command-Only - no switch of its own; a real example sentence where the
        list pins one, plus the Settings place it is listed at.
    """
    label = label_for(row)
    surface = str(row.get("surface") or "")
    # The surface wins over the label's own words: see this docstring,
    # phone_change_words() and both_pc_change_words(). Both Settings-shaped
    # labels are covered because either one would otherwise say "on this PC" /
    # "Open ... on the PC".
    if surface == "phone" and label in (LABEL_PC_ONLY, LABEL_SETTINGS_ONLY):
        return phone_change_words(row)
    if surface == "both" and label == LABEL_PC_ONLY:
        return both_pc_change_words(row)
    settings = feature_switches(row)
    if label == LABEL_SWITCH_ADJUST and settings:
        labels = [setting["label"] for setting in settings]
        if len(labels) == 1:
            only = labels[0]
            said = (f'To turn it on or off, say "turn on {only}" or "turn off '
                    f'{only}".')
            # The card sentence is DATA, not a template (2026-10-26 semantic
            # read, finding 5): it used to be appended to every single-switch
            # row, and four of them never raise a card. See CARD_ON_LOOSENING.
            if settings[0].get("key") in CARD_ON_LOOSENING:
                said += (" A change that loosens a rule still asks on a card "
                         "first.")
            return said
        return ("It has more than one switch: " + ", ".join(f'"{l}"' for l in labels)
                + '. Say "turn on <one of those>" for the one you mean; nothing '
                  'changes until you name one.')
    if label == LABEL_SWITCH_ADJUST:
        adjust = list((_matrix_row(row) or {}).get("adjust") or [])
        phrase = str((adjust[0] if adjust else {}).get("phrase") or "")
        if phrase:
            return f'To change it, say "{phrase}".'
        return (f"Its typed control is not wired yet; open {settings_path_words(row)} "
                f"to change it.")
    if label == LABEL_ALWAYS_ON:
        fid = str(row.get("id") or "")
        off_path = ALWAYS_ON_OFF_PATH.get(fid)
        if off_path:
            # Not every Always-On rule is an off-less control: App lock is a
            # real switch whose OFF asks Windows Hello (2026-10-26 semantic
            # read, finding 2). The rule under it is what stays on.
            return f"It is Always On (Core Safety Rule). {off_path}"
        extra = ALWAYS_ON_EXCEPTION.get(fid)
        return ("It is Always On (Core Safety Rule) and cannot be turned off."
                + (f" {extra}" if extra else ""))
    if label == LABEL_SETTINGS_ONLY:
        return (f"It is changed only at {settings_path_words(row)}: by your decision "
                f"it is never typed or spoken.")
    if label == LABEL_PC_ONLY:
        return (f"It is changed at {settings_path_words(row)} on this PC; the phone "
                f"says so rather than pretending it changed.")
    tool_words = _tool_switch_words(row)
    if tool_words:
        # The state sentence is in `_state_clause` just above this call; this
        # half says how to CHANGE it, and repeats no state claim.
        return ('To change it, use its own switch in Settings, What asks first, '
                'under "Let the AI use this". ' + _example_words(row)
                + f" It is listed at {settings_path_words(row)}.")
    return ("It runs when you ask and has no switch of its own. "
            + _example_words(row)
            + f" It is listed at {settings_path_words(row)}.")


#: The Status line a PHONE-ONLY row shows. DISPLAY ONLY: `label_for()` keeps the
#: owner-approved five-label mix, pinned to `contract/feature-controls.json` and
#: to the same counts the two apps' feature lists render. But a phone-only row's
#: Status line read "PC-Only Setting (Honest Refusal on Phone)" while the very
#: same answer said "It is on the phone only" (2026-10-26, part B): the label was
#: picked from the row's reason without looking at `surface`, and the two halves
#: of one answer contradicted each other. The Status line is therefore derived
#: from `surface` here, and from nothing else.
PHONE_ONLY_DISPLAY_LABEL = "Phone-Only Setting (Changed in the phone's Settings)"


def status_label(row: dict) -> str:
    """The five-label kind as the Status line says it - `surface` first.

    Only a phone-only row whose label is one of the two Settings-shaped labels
    is reworded; every other row returns its contract label untouched, so the
    counts and both apps' directories are exactly as approved. The phone lists'
    own rendering of that label (a data-level change in both apps) is recorded
    as a separate PR, not done here.
    """
    label = label_for(row)
    if (str(row.get("surface") or "") == "phone"
            and label in (LABEL_PC_ONLY, LABEL_SETTINGS_ONLY)):
        return PHONE_ONLY_DISPLAY_LABEL
    if label == LABEL_ALWAYS_ON:
        # Display only, same shape as the phone-only reword above: the five
        # label strings and their pinned counts are `label_for()`'s, but an
        # Always-On row with a real OFF path must not read out "Cannot Be
        # Turned Off" (see ALWAYS_ON_DISPLAY).
        return ALWAYS_ON_DISPLAY.get(str(row.get("id") or ""), label)
    return label


def surface_context(row: dict) -> str:
    """What the CURRENT app adds to this row, or "" (unknown surface / no
    one-sided fact to add).

    The owner's requirement of 2026-10-31: Jarvis knows whether he is talking
    from the Android app or the desktop program, so a feature answer says what
    THIS app can do with that feature. The row's own `surface` and `where`
    decide the facts - nothing is reworded or invented here:
      * a PC-only feature asked from the phone says it is on the PC only and
        where the PC door is;
      * a phone-only feature asked from the PC says it is on the phone only and
        where the phone door is;
      * a both-apps feature adds only which app is asking (its `where` already
        names both routes), so the answer says nothing new about the feature;
      * with no header (an older client, a test, a script) this returns "" and
        the answer is exactly what it was before.
    A module that cannot load is the same as no header: no line."""
    try:
        import jarvis_surface as S
        current = S.current()
    except Exception:
        return ""
    if current not in ("phone", "desktop"):
        return ""
    surface = str(row.get("surface") or "")
    where = str(row.get("where") or "").strip()
    asking = ("You are asking from the phone." if current == "phone"
              else "You are asking from the PC.")
    if current == "phone":
        if surface == "desktop":
            return (asking + " This one is on the PC only - open it there: "
                    + (where or "the desktop program."))
        if surface == "phone":
            return asking + " This one is in this phone app."
        return asking
    if surface == "phone":
        return (asking + " This one is on the phone only - open it there: "
                + (where or "the Android app."))
    if surface == "desktop":
        return asking + " This one is in the desktop program."
    return asking


def explain_words(row: dict) -> str:
    """The exact facts, in plain words, made only from the row and the switches."""
    parts = [f"{row['title']}.", str(row.get("what") or "").strip(),
             f"Status: {status_label(row)}.",
             f"Settings: {settings_path_words(row)}.", "",
             f"Where: {str(row.get('where') or '').strip()}",
             f"Does it ask first? {str(row.get('asks') or '').strip()}",
             f"The honest limit: {_limit_words(row)}"]
    if surface_words(row):
        parts.append(surface_words(row))
    rows = _switch_state_rows(row)
    clause = _state_clause(rows, row)
    if clause:
        parts.append(clause)
    parts.append(change_words(row))
    context = surface_context(row)
    if context:
        parts.append(context)
    parts.append(f"(Feature list group: {row['group']}.)")
    return "\n\n".join(p for p in parts if p is not None and p != "").replace("\n\n\n", "\n\n")


def groups_words() -> str:
    got = groups()
    if not got:
        return ("The feature list is not installed on this PC, so I cannot read it.")
    listed = "; ".join(f"{g['group']} ({g['count']})" for g in got)
    return (f"Jarvis lists {feature_count()} features in {len(got)} groups: {listed}. "
            f"Ask \"what is <a feature>\" for the exact facts about one, "
            f"or name a group to see what is in it.")


def unknown_words(words: str) -> str:
    return (f"I do not have a feature called \"{str(words or '').strip()}\" in the list. "
            + groups_words())


#: The owner asked about "cloud sync" in the live field test and the local model padded its
#: "I do not have that" with generic OneDrive/Google Drive/iCloud advice. Gemini's post-review
#: (2026-10-20, HIGH-4) asked for a deterministic answer instead: pointing a third-party sync
#: folder at the private Jarvis folders is a privacy hazard, so the guide says what Jarvis
#: actually does and never suggests one. These are whole phrases after `_norm` (lower case,
#: punctuation to spaces), matched as substrings so "how do I turn on cloud sync" also hits.
_CLOUD_SYNC_TOPICS = (
    "cloud sync", "cloud storage", "cloud backup", "sync across devices",
    "sync my files", "sync files between", "sync between my devices",
    "onedrive", "one drive", "google drive", "dropbox", "icloud",
)

CLOUD_SYNC_WORDS = (
    "Jarvis does not use cloud sync. Your PC and phone talk directly over your "
    "private Tailscale or NordVPN Meshnet link, and backups are saved as encrypted "
    ".jbak files. Nothing is uploaded to OneDrive, Google Drive, Dropbox or iCloud."
)


def _cloud_sync_asked(words) -> bool:
    """True when the owner is asking about cloud sync - answered, not invented."""
    text = " " + _norm(words) + " "
    return any(topic in text for topic in _CLOUD_SYNC_TOPICS)


def _ambiguous_words(rows: list) -> str:
    names = "; ".join(f"{r['title']} ({r['id']})" for r in rows)
    return (f"That could be more than one feature: {names}. "
            f"Say which one by its name or its id (for example, "
            f"\"what is {rows[0]['id']}\").")


def _group_words(group: str, rows: list) -> str:
    titles = "; ".join(f"{r['title']} ({r['id']})" for r in rows)
    return (f"The {group} group has {len(rows)} features: {titles}. "
            f"Ask \"what is <one>\" for its exact facts.")


def _feature_facts(row: dict) -> dict:
    out = {k: row.get(k) for k in ("id", "group", "title", "what", "where",
                                   "asks", "limit", "surface")}
    # The settings places this feature covers, as the list itself records them
    # (`settings.prompt-coach` and the Features-page areas). Facts only - the
    # answer's words use `where`; this is for a caller that wants the list.
    out["covers"] = list(row.get("covers") or [])
    if row.get("surface_reason"):
        out["surface_reason"] = row["surface_reason"]
    if row.get("aliases"):
        out["aliases"] = list(row["aliases"])
    return out


def explain(words) -> dict:
    """Exact facts about the feature the owner named (the tool's main answer)."""
    if CATALOGUE is None:
        return {"ok": False, "kind": "missing",
                "words": ("The feature list is not installed on this PC, so I cannot "
                          "read it. Nothing here was invented.")}
    if _cloud_sync_asked(words):
        return {"ok": True, "kind": "note", "words": CLOUD_SYNC_WORDS}
    got = find(words, loose=True)
    kind = got["kind"]
    if kind == "feature":
        row = got["row"]
        rows = _switch_state_rows(row)
        return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                "switches": rows, "words": explain_words(row)}
    if kind == "group":
        return {"ok": True, "kind": "group", "group": got["group"],
                "features": [{"id": r["id"], "title": r["title"]} for r in got["rows"]],
                "words": _group_words(got["group"], got["rows"])}
    if kind == "ambiguous":
        return {"ok": False, "kind": "ambiguous",
                "candidates": [{"id": r["id"], "title": r["title"]} for r in got["rows"]],
                "words": _ambiguous_words(got["rows"])}
    return {"ok": False, "kind": "unknown", "groups": [g["group"] for g in groups()],
            "words": unknown_words(words)}


def change(words) -> dict:
    """Can it be changed, and how? - the answer to "can I change <feature>".

    Says which of the five owner-facing kinds it is, whether it has one switch,
    several or none, and the exact phrase or Settings place. It changes
    nothing: `switch_target()` and the fixed "turn on/off" phrase are the
    write path, and they are untouched here.
    """
    if CATALOGUE is None:
        return {"ok": False, "kind": "missing",
                "words": ("The feature list is not installed on this PC, so I cannot "
                          "read it. Nothing here was invented.")}
    if _cloud_sync_asked(words):
        return {"ok": True, "kind": "note", "state": None, "words": CLOUD_SYNC_WORDS}
    got = find(words, loose=True)
    if got["kind"] == "feature":
        row = got["row"]
        rows = _switch_state_rows(row)
        words_out = (f"{row['title']}. Status: {status_label(row)}. "
                     f"{change_words(row)}")
        clause = _state_clause(rows)
        if clause:
            words_out += " " + clause
        known = [r["state"] for r in rows if isinstance(r["state"], bool)]
        return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                "label": status_label(row), "switches": rows,
                "state": known[0] if len(set(known)) == 1 else None,
                "words": words_out}
    if got["kind"] == "ambiguous":
        return {"ok": False, "kind": "ambiguous",
                "candidates": [{"id": r["id"], "title": r["title"]} for r in got["rows"]],
                "words": _ambiguous_words(got["rows"])}
    setting, label = _setting_target(words)
    if setting is None:
        # A key is how the fixed phrase carries a plain switch it resolved
        # itself (jarvis_quick's _feature_change_intent), not a name the owner
        # said.
        R = _registry()
        raw_key = str(words or "").strip()
        setting = next((b for b in getattr(R, "BOOL_SETTINGS", ())
                        if b.key == raw_key), None) if R is not None else None
        label = _setting_words(setting) if setting is not None else ""
    if setting is not None:
        value = read_state(setting.key)
        section = getattr(setting, "section", None)
        where = f"Settings, {section}" if section else "Settings"
        clause = ("" if not isinstance(value, bool) else
                  f" It is {ON_WORD if value else OFF_WORD} right now.")
        return {"ok": True, "kind": "setting", "setting": setting.key, "label": label,
                "state": value,
                "words": (f"{label.capitalize()} is an on/off setting in {where}. "
                          f"Say \"turn on {label}\" or \"turn off {label}\" and I will "
                          f"do it; a change that loosens a rule still asks on a card "
                          f"first.{clause}")}
    return {"ok": False, "kind": "unknown", "groups": [g["group"] for g in groups()],
            "words": unknown_words(words)}


def list_features(words=None) -> dict:
    """The groups (empty words), or one group's features when a group is named."""
    if CATALOGUE is None:
        return {"ok": False, "kind": "missing",
                "words": "The feature list is not installed on this PC, so I cannot read it."}
    if not _norm(words):
        return {"ok": True, "kind": "groups", "groups": groups(),
                "words": groups_words()}
    got = find(words, loose=True)
    if got["kind"] == "group":
        return {"ok": True, "kind": "group", "group": got["group"],
                "features": [{"id": r["id"], "title": r["title"]} for r in got["rows"]],
                "words": _group_words(got["group"], got["rows"])}
    return explain(words)


# ---------------------------------------------------------------------------
#   "What can you do with <area>?" - the capability overview (2026-10-31)
# ---------------------------------------------------------------------------
#
# THE FIELD-TEST GAP (2026-10-31, pass 9, PART B). Eight questions were asked
# through the live HUD's own chat box and only two answers were accurate.
# "what can you do with the calendar?" went to the model, which claimed
# invitations and availability that do not exist; "what are the smart features
# of the calendar?" said it was unaware of them; "what can you edit in my
# notes?" invented adding entries; "can I protect a folder from you?" invented
# a filesystem-permissions workaround. The owner's own feature list already
# held the honest answers - these rows, in the words both apps' Features pages
# show.
#
# So a capability question is answered from the rows and NEVER from the
# model's memory: the area is matched against the rows' own names first (the
# exact ids and titles, then a group's name), and the matching rows are quoted
# back with their own title, where, asks and limit. It claims no more than a
# row says, it says plainly when a thing is not a feature, and when more than
# a few rows match it names them and asks which one - it never guesses.

CAPABILITY_NOT_A_FEATURE = "That is not one of my features on this PC."
CAPABILITY_TAIL = ('Open "Everything Jarvis can do" - Brain, Tutorials and the '
                   "FAQ - to read the whole list.")

#: Words that belong to the QUESTION, not to the area being asked about.
_CAP_FILLER = frozenset({
    "what", "which", "who", "whom", "can", "could", "would", "should", "do",
    "does", "did", "you", "jarvis", "i", "me", "my", "mine", "the", "a", "an",
    "of", "about", "with", "for", "in", "on", "onto", "into", "from", "to",
    "is", "are", "was", "were", "there", "your", "yours", "it", "this",
    "that", "these", "those", "here", "please", "tell", "know", "capable",
    "able", "ability", "abilities", "describe", "explain", "list", "show",
    "name", "get", "have", "smart", "feature", "features", "option",
    "options", "setting", "settings", "something", "anything", "stuff",
    "things", "thing", "all", "many", "much", "so", "currently", "right",
    "now",
})
#: Asking verbs. A capability question may say what the owner wants to DO
#: ("what can you edit in my notes?"); the verb is answered from the rows' own
#: words, never assumed.
_CAP_VERBS = frozenset({
    "add", "create", "make", "put", "edit", "change", "delete", "remove",
    "rename", "see", "view", "read", "check", "find", "search", "open",
    "use", "set", "track", "schedule", "cancel", "stop", "start", "share",
    "send", "write", "save", "move", "copy", "update", "protect", "block",
    "control", "manage",
})
#: The words a row may use to show that it supports the asking verb. A match
#: is a plain substring of the row's own title/what/where/asks/limit, lowered.
_CAP_VERB_WORDS = {
    "add": ("add",), "create": ("creat",), "make": ("make", "creat"),
    "put": ("put", "add"), "edit": ("edit", "change", "rewrit", "modif"),
    "change": ("change", "edit", "adjust"), "delete": ("delet", "remov"),
    "remove": ("remov", "delet"), "rename": ("rename", "edit"),
    "see": ("see", "read", "view", "show"), "view": ("view", "see"),
    "read": ("read", "see"), "check": ("check", "read", "see"),
    "find": ("find", "search"), "search": ("search", "find"),
    "open": ("open",), "use": ("use", "say", "ask", "press", "tap"),
    "set": ("set", "chang", "turn"), "track": ("track", "watch", "follow"),
    "schedule": ("schedul", "repeat"),
    "cancel": ("cancel", "delet", "remov", "stop"), "stop": ("stop", "cancel"),
    "start": ("start", "open"), "share": ("share", "send"),
    "send": ("send", "share"), "write": ("writ", "note"), "save": ("sav", "writ"),
    "move": ("move", "drag"), "copy": ("cop", "duplicat"),
    "update": ("updat",), "protect": ("protect", "block", "read-only"),
    "block": ("block", "protect"), "control": ("control", "tap", "press"),
    "manage": ("manag", "change", "edit"),
}
#: More matching rows than this and the answer names them and asks which one.
_CAP_AMBIGUOUS_LIMIT = 4

#: RULING (d), 2026-10-31 (Gemini, after the overnight wave): common owner words
#: are mapped to the catalogue rows they mean, so a capability is never falsely
#: denied because the list uses a different word. "obsidian"/"vault" are the
#: notes rows, "schedule"/"events"/"appointments" the calendar rows,
#: "block"/"exclude"/"permissions" the protected-items row, and "send file"/
#: "download file" the files rows. Each pattern is whole-word, so it cannot
#: rewrite the middle of another word.
CAPABILITY_SYNONYMS = (
    (re.compile(r"\b(?:obsidian|vault|vaults)\b"), "notes"),
    (re.compile(r"\b(?:schedule|schedules|scheduled|event|events|"
                r"appointment|appointments)\b"), "calendar"),
    (re.compile(r"\b(?:block|blocks|blocked|blocking|exclude|excludes|"
                r"excluded|permission|permissions)\b"), "protected from jarvis"),
    (re.compile(r"\b(?:send|sending|sent|download|downloads|downloading)"
                r"\s+(?:a\s+|an\s+|the\s+|my\s+)?files?\b"), "files"),
)

#: RULING (d): topics the list genuinely does NOT have, so the hard "That is not
#: one of my features on this PC." sentence is allowed even when another word in
#: the sentence overlaps a row. Each is a phrase the field test caught the model
#: inventing; the list has no row for any of them. "permissions" alone is NOT
#: here - ruling (d) maps it to the Protected from Jarvis row - only the invented
#: "system permissions"/"filesystem permissions" workaround is.
CAPABILITY_UNSUPPORTED = (
    "system permissions",
    "filesystem permissions",
    "notification history",
    "calendar invitations",
    "invitations",
    "availability",
)


def _capability_canonical(words) -> tuple:
    """(the area words with ruling (d)'s synonyms applied, unsupported topic).

    The unsupported topic is returned (and the words left alone) when the
    question names one of CAPABILITY_UNSUPPORTED; the caller may then use the
    hard "not one of my features" sentence. Otherwise owner words are mapped to
    the catalogue's own words before the row lookup.

    Only a REPEATED canonical word is collapsed ("schedule events" is one
    calendar, not two). An ordinary repeated word is kept: a feature's own
    title can repeat one ("Picture-in-picture"), and flattening that would stop
    its title naming its own row.
    """
    text = " ".join(_norm(words).split())
    for phrase in CAPABILITY_UNSUPPORTED:
        if phrase in text:
            return text, phrase
    changed = text
    for rx, target in CAPABILITY_SYNONYMS:
        if rx.search(changed):
            changed = rx.sub(target, changed)
    out = []
    for word in changed.split():
        if out and out[-1] == word:
            continue
        out.append(word)
    return " ".join(out), None


def _capability_overlap_rows(words, *, strip_verbs: bool = True) -> list:
    """Rows whose own prose shares a real word with the question.

    Ruling (d): this is the "catalogue overlap" a hard denial must not ignore.
    Only words of three letters or more count, and the rows with the most shared
    words come first (catalogue order breaks ties), up to the same short list an
    ambiguous answer uses. It never invents: the rows are quoted by the caller.
    """
    query = _capability_query(words, strip_verbs=strip_verbs)
    tokens = {_singular(w) for w in _norm(query).split()
              if w not in _STOP and len(w) >= 3}
    if not tokens:
        return []
    scored = []
    for index, row in enumerate(features()):
        blob = " ".join(str(row.get(key) or "") for key in
                        ("title", "what", "where", "asks", "limit", "group"))
        have = {_singular(w) for w in re.findall(r"[a-z0-9]+", blob.lower())}
        shared = tokens & have
        if shared:
            scored.append((len(shared), -index, row))
    scored.sort(key=lambda item: (-item[0], -item[1]))
    return [row for _shared, _index, row in scored[:_CAP_AMBIGUOUS_LIMIT]]


def _capability_display(words) -> str:
    """The area as the owner said it, for the answer's own sentences."""
    parts = _norm(words).split()
    if parts and parts[0] in ("the", "my", "your", "a", "an"):
        parts = parts[1:]
    return " ".join(parts) or "that"


def _capability_query(words, *, strip_verbs: bool = True) -> str:
    """The area words in a capability question - its verbs and filler taken off."""
    keep = _CAP_FILLER if strip_verbs else (_CAP_FILLER - _CAP_VERBS)
    return " ".join(w for w in _norm(words).split()
                    if w not in keep and (not strip_verbs or w not in _CAP_VERBS))


def _capability_title_tokens(row: dict) -> tuple:
    """The row's OWN names: its id and title words (never its prose, never its
    aliases - an alias belongs to one feature and must not pull a group in)."""
    return _tokens(row["id"].replace("-", " ")) + _tokens(row["title"])


def _capability_rows(words, *, strip_verbs: bool = True) -> list:
    """The rows whose own names (or whose group's name) match the area words."""
    rows = features()
    raw = _norm(str(words or ""))
    # A row's own TITLE or alias, said exactly, is that row - always. This is
    # what makes every feature in the list answerable by its own name, even
    # when its words would otherwise be eaten as filler ("About Jarvis").
    for row in rows:
        if raw and (raw == _norm(row["title"])
                    or any(raw == _norm(alias) for alias in row.get("aliases") or ())):
            return [row]
    query = _capability_query(words, strip_verbs=strip_verbs)
    if not query:
        # An id made only of filler words ("now", "about") still names its own
        # row: fall back to the exact id rather than answering "not a feature".
        for row in rows:
            if raw and raw == _norm(row["id"].replace("-", " ")):
                return [row]
        return []
    tokens = tuple(sorted({w for w in _singular_all(query).split() if w not in _STOP}))
    if not tokens:
        for row in rows:
            if raw and raw == _norm(row["id"].replace("-", " ")):
                return [row]
        return []
    # A multi-word id said exactly ("phone-notifications") wins over the loose
    # token hits, which would otherwise answer with a neighbouring feature.
    if len(raw.split()) >= 2:
        for row in rows:
            if raw == _norm(row["id"].replace("-", " ")):
                return [row]
    # A feature whose own name is the whole multi-word phrase wins next:
    # "prompt coach" is one row, and it must not be diluted by the loose title
    # words of nearby rows.
    if strip_verbs and len(tokens) >= 2:
        got = find(" ".join(tokens), loose=True)
        if got["kind"] == "feature":
            return [got["row"]]
        if got["kind"] == "ambiguous":
            return got["rows"]
    if strip_verbs and "-" in str(words or ""):
        got = find(words, loose=False)
        if got["kind"] == "feature":
            return [got["row"]]
    id_hits = [r for r in rows if _contains_all(_tokens(r["id"].replace("-", " ")),
                                                tokens)]
    title_hits = [r for r in rows if _contains_all(_tokens(r["title"]), tokens)]
    hits = id_hits or title_hits
    groups_hit = []
    for group in groups():
        group_words = tuple(w for w in _singular_all(_norm(group["group"])).split()
                            if w not in _STOP)
        if _contains_all(group_words, tokens):
            groups_hit.append(group["group"])
    if groups_hit:
        # A word that names a GROUP belongs to the group's rows: "files" is the
        # Notes and files group's documents row, not the config file's own id
        # ("settings-file") outside it. The id/title preference still applies
        # INSIDE the group first.
        id_in_group = [r for r in id_hits if r["group"] in groups_hit]
        if id_in_group:
            return id_in_group
        title_in_group = [r for r in title_hits if r["group"] in groups_hit]
        if title_in_group:
            return title_in_group
        if not hits:
            return [r for r in rows if r["group"] in groups_hit]
    return hits


def _singular_all(text: str) -> str:
    """`_norm`ed words singularised once, for the tokens used in a lookup."""
    return " ".join(_singular(w) for w in _norm(text).split())


#: The suffix forms a verb stem may take in the catalogue's own prose, so the
#: match is on a WHOLE word's beginning: "adding" is the verb add, "address" is
#: not (the old plain-substring test called the read-only iCal row an adding
#: feature because "address" contains "add").
_VERB_SUFFIX = r"(?:s|e|es|ed|ing|ion|ions|er|ers|ment|ments)?"


def _capability_verb_supported(verb: str, rows: list) -> bool:
    """Does any matching row's own words show it can do this asking verb?"""
    want = _CAP_VERB_WORDS.get(verb, (verb,))
    patterns = [re.compile(r"(?<![a-z0-9])" + re.escape(word) + _VERB_SUFFIX
                           + r"(?![a-z0-9])") for word in want]
    for row in rows:
        blob = " ".join(str(row.get(k) or "").lower()
                        for k in ("title", "what", "where", "asks", "limit"))
        if any(rx.search(blob) for rx in patterns):
            return True
    return False


def _capability_row_words(row: dict) -> str:
    """One row's own facts, in the order the list itself writes them."""
    bits = [str(row["title"]).strip() + "."]
    for key, label in (("what", ""), ("where", "Where: "),
                       ("asks", "Does it ask first? "), ("limit", "The honest limit: ")):
        value = str(row.get(key) or "").strip()
        if value:
            bits.append(label + value)
    return " ".join(bits)


def _capability_rows_words(rows: list, query: str) -> str:
    head = (f"Here is what my feature list says about {query}:"
            if query else "Here is what my feature list says:")
    return head + "\n\n" + "\n\n".join(_capability_row_words(r) for r in rows)


def capabilities(words, *, verb: str = "", strip_verbs: bool = True) -> dict:
    """The owner asked what Jarvis can do with something - answer from the list.

    `words` is the area ("the calendar", "my notes", ...); `verb` is the asking
    verb when the sentence had one ("edit", "add"). Every sentence in `words`
    comes from a catalogue row or says a thing is not a feature; nothing is
    inferred and the model is never involved.

    `strip_verbs=False` keeps a verb that is part of the SUBJECT ("can I
    protect a folder from you?") - the area must then really be a row's name,
    or the honest "not one of my features" answer is given.
    """
    if CATALOGUE is None:
        return {"ok": False, "kind": "missing",
                "words": ("The feature list is not installed on this PC, so I cannot "
                          "read it. Nothing here was invented.")}
    verb = str(verb or "").strip().lower()
    canonical, unsupported = _capability_canonical(words)
    query = _capability_query(canonical, strip_verbs=strip_verbs)
    display = _capability_display(canonical)
    rows = _capability_rows(canonical, strip_verbs=strip_verbs)
    if not rows and query and not unsupported:
        got = find(query, loose=True)
        if got["kind"] == "feature":
            rows = [got["row"]]
        elif got["kind"] == "ambiguous":
            return {"ok": False, "kind": "ambiguous",
                    "candidates": [{"id": r["id"], "title": r["title"]}
                                   for r in got["rows"]],
                    "words": _ambiguous_words(got["rows"]) + " " + CAPABILITY_TAIL}
    if not rows:
        # RULING (d), 2026-10-31: the hard sentence is for NO catalogue overlap
        # or a known unsupported topic only. When the question shares real words
        # with the list, quote the nearest rows and point at the whole list
        # instead - a capability must never be falsely denied because a synonym
        # or a phrase was not an exact row name.
        if not unsupported:
            nearest = _capability_overlap_rows(canonical, strip_verbs=strip_verbs)
            if nearest:
                return {"ok": True, "kind": "rows",
                        "features": [{"id": r["id"], "title": r["title"]}
                                     for r in nearest],
                        "words": _capability_rows_words(nearest, display)
                        + " " + CAPABILITY_TAIL}
        return {"ok": False, "kind": "unknown",
                "words": CAPABILITY_NOT_A_FEATURE + " " + CAPABILITY_TAIL}
    # An asking verb narrows an area to the rows that really do it: "what can
    # you edit in my notes?" is the notes editor, not every note feature. When
    # no matching row shows the verb, the rows stay as they are and the answer
    # says plainly that the ability is not there.
    if verb:
        supporting = [r for r in rows if _capability_verb_supported(verb, [r])]
        if supporting:
            rows = supporting
    supported = not verb or _capability_verb_supported(verb, rows)
    if verb and not supported:
        # RULING (d): this is not a denial of the feature (the rows above ARE
        # in the list) - it says the list has no such asking verb for them, in
        # the list's own words, and still points at the whole list.
        head = (f"My feature list has no {verb} for your {display} - here is "
                f"what it does say about it.")
        body = _capability_rows_words(rows, display)
        return {"ok": False, "kind": "not_feature",
                "features": [{"id": r["id"], "title": r["title"]} for r in rows],
                "words": head + "\n\n" + body + " " + CAPABILITY_TAIL}
    if len(rows) > _CAP_AMBIGUOUS_LIMIT:
        return {"ok": False, "kind": "ambiguous",
                "candidates": [{"id": r["id"], "title": r["title"]}
                               for r in rows[:_CAP_AMBIGUOUS_LIMIT]],
                "words": _ambiguous_words(rows[:_CAP_AMBIGUOUS_LIMIT])
                + " " + CAPABILITY_TAIL}
    return {"ok": True, "kind": "rows",
            "features": [{"id": r["id"], "title": r["title"]} for r in rows],
            "words": _capability_rows_words(rows, display) + " " + CAPABILITY_TAIL}


# --------------------------------------------------------------------------
#   Discussion shapes: limits, asks-first, which app, why, difference,
#   overview, and the owner's own exact names (2026-10-31, pass-11 audit)
# --------------------------------------------------------------------------
# The audit measured that `tell me about X` and `how does X work` were correct
# for 25/25 features, `what are the limits of X` for 3/25 - the other 22 were
# the model inventing limits or describing a different product - and that
# "Today board", "quiet hours", "thinking level", "personality" and "memories"
# did not resolve. These shapes quote the SAME row `explain()` quotes; they
# never add a fact and never guess which row was meant.

def _discussion_got(words):
    """The row/group/ambiguity `find()` returns, without the cloud-sync side."""
    if CATALOGUE is None:
        return {"kind": "missing"}
    return find(words, loose=True)


def _discussion_ambiguous(rows: list) -> dict:
    return {"ok": False, "kind": "ambiguous",
            "candidates": [{"id": r["id"], "title": r["title"]} for r in rows],
            "words": _ambiguous_words(rows) + " " + CAPABILITY_TAIL}


def _discussion_unknown() -> dict:
    # The same hard sentence the capability path uses, for the SAME reason:
    # the question names nothing in the list. ("Zero overlap" - a word shared
    # with a row's prose but not its name is handled by `find(loose=True)`
    # only when the question itself asked about a feature; here the owner
    # named a thing, so an unknown name gets the honest sentence.)
    return {"ok": False, "kind": "unknown",
            "words": CAPABILITY_NOT_A_FEATURE + " " + CAPABILITY_TAIL}


def _discussion_row(words):
    """(row, None) or (None, the ready answer dict) for a discussion shape."""
    got = _discussion_got(words)
    if got["kind"] == "feature":
        return got["row"], None
    if got["kind"] == "ambiguous":
        return None, _discussion_ambiguous(got["rows"])
    return None, _discussion_unknown()


def _row_limit_words(row: dict) -> str:
    limit = str(row.get("limit") or "").strip()
    return limit or "The feature list records no limit for it."


def limits(words) -> dict:
    """"What are the limits of X?" - the row's own `limit` field, verbatim."""
    if CATALOGUE is None:
        return {"ok": False, "kind": "missing",
                "words": "The feature list is not installed on this PC, so I cannot read it."}
    row, bad = _discussion_row(words)
    if bad is not None:
        return bad
    return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
            "words": (f"{row['title']}. The honest limit: {_row_limit_words(row)} "
                      f"Where: {str(row.get('where') or '').strip()}")}


def asks_first(words) -> dict:
    """"Does X ask first?" - the row's own `asks` field, verbatim."""
    if CATALOGUE is None:
        return {"ok": False, "kind": "missing",
                "words": "The feature list is not installed on this PC, so I cannot read it."}
    row, bad = _discussion_row(words)
    if bad is not None:
        return bad
    return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
            "words": (f"{row['title']}. Does it ask first? "
                      f"{str(row.get('asks') or '').strip()}")}


def which_app(words) -> dict:
    """"Which app can use X?" - the row's own `surface` field, in its own words."""
    if CATALOGUE is None:
        return {"ok": False, "kind": "missing",
                "words": "The feature list is not installed on this PC, so I cannot read it."}
    row, bad = _discussion_row(words)
    if bad is not None:
        return bad
    return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
            "words": f"{row['title']}. {surface_words(row)}"}


def why_use(words) -> dict:
    """"Why would I use X?" - what the row says it does, plus where and its limit."""
    if CATALOGUE is None:
        return {"ok": False, "kind": "missing",
                "words": "The feature list is not installed on this PC, so I cannot read it."}
    row, bad = _discussion_row(words)
    if bad is not None:
        return bad
    return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
            "words": (f"{row['title']}. {str(row.get('what') or '').strip()} "
                      f"Where: {str(row.get('where') or '').strip()} "
                      f"The honest limit: {_row_limit_words(row)}")}


def _compare_state(row: dict) -> str:
    """One short token for a feature's live state, from the same switch read.

    Tokens, not prose, so a caller gets a structured side-by-side it can render
    itself; `state_words` beside it carries the existing honest sentence. Every
    branch below is a state the row really has - a switch that could not be read
    is never turned into "off".
    """
    rows = _switch_state_rows(row)
    known = [r["state"] for r in rows if isinstance(r["state"], bool)]
    if known:
        if all(known):
            return "on"
        if not any(known):
            return "off"
        return "partly on"
    if rows:
        return "cannot be read on this PC"
    mine = _matrix_row(row) or {}
    status = str(mine.get("status") or "")
    if status in _HAS_A_CONTROL:
        return "a control this build cannot read as on/off"
    if status in ("planned", "not-a-setting"):
        return "no on/off switch"
    label = label_for(row)
    if label == LABEL_ALWAYS_ON:
        return "always on (core safety rule)"
    if label == LABEL_COMMAND_ONLY:
        return "always available by command"
    if label == LABEL_SETTINGS_ONLY:
        return "Settings only, no chat control"
    if label == LABEL_PC_ONLY:
        return "a setting read and changed on this PC"
    return "no on/off switch"


def state_token(row: dict) -> str:
    """The row's short live-state token, for a caller that compares two rows.

    The public form of `_compare_state` so the generic two-feature answer in
    `jarvis_quick` reads the SAME token the difference answer carries - one
    reader, one vocabulary, and no second state list.
    """
    return _compare_state(row)


def _compare_facts(row: dict) -> dict:
    """One feature's structured side of a comparison, from its own row + readers.

    THE STRUCTURE, NOT JUST PROSE (2026-11-04, the self-awareness audit's fix
    #4). A "what is the difference between X and Y" answer used to be two prose
    paragraphs; a caller could not compare a field without parsing words. This
    names each field the catalogue really holds - where it lives, the switch it
    has (or none), its live on/off, what asks first, and its own honest limit -
    and every value is read, never typed. `state_words` is the existing
    `_state_clause` sentence, so the structured and the prose answers cannot
    disagree.
    """
    switches = feature_switches(row)
    return {
        "id": str(row.get("id") or ""),
        "title": str(row.get("title") or ""),
        "where": str(row.get("where") or "").strip(),
        "has_switch": bool(switches),
        "switch": [str(s.get("label") or s.get("key") or "") for s in switches],
        "state": _compare_state(row),
        "state_words": _state_clause(_switch_state_rows(row), row),
        "asks": str(row.get("asks") or "").strip(),
        "limit": _row_limit_words(row),
        "what": str(row.get("what") or "").strip(),
        "kind_label": status_label(row),
    }


def _comparison_block(row: dict) -> str:
    facts = _compare_facts(row)
    switch = ("Its switch: " + ", ".join(facts["switch"]) + "." if facts["has_switch"]
              else "It has no on/off switch.")
    return (f"{facts['title']}. Where it lives: {facts['where']} {switch} "
            f"{facts['state_words']} Does it ask first? {facts['asks']} "
            f"The honest limit: {facts['limit']}")


def _difference_sentence(a: dict, b: dict) -> str:
    """ONE plain sentence saying what is different, from the rows' own words."""
    a_what = str(a.get("what") or "").strip().rstrip(".")
    b_what = str(b.get("what") or "").strip().rstrip(".")
    a_title = str(a.get("title") or a.get("id") or "The first")
    b_title = str(b.get("title") or b.get("id") or "the second")
    if a_what and b_what:
        return (f"The difference: {a_title} is for {a_what}; "
                f"{b_title} is for {b_what}.")
    if a_what or b_what:
        known = a_title if a_what else b_title
        what = a_what or b_what
        return (f"The difference is not recorded for both: {known} is for {what}, "
                f"and the feature list records no description for the other.")
    return ("The feature list records no description for either row, so I cannot "
            "say more than what is above.")


def difference(first, second) -> dict:
    """"What's the difference between X and Y?" - both rows, side by side.

    THE STRUCTURED SIDE-BY-SIDE (2026-11-04): the answer carries `compare`, one
    `_compare_facts` dict per feature, beside the words. Every field comes from
    the catalogue row or the live switch reader, so "where it lives", "its
    switch", "is it on" and "what asks first" cannot be two different answers
    from the prose and the structure. One plain sentence says the difference.
    """
    if CATALOGUE is None:
        return {"ok": False, "kind": "missing",
                "words": "The feature list is not installed on this PC, so I cannot read it."}
    got_a = _discussion_got(first)
    got_b = _discussion_got(second)
    row_a = got_a["row"] if got_a["kind"] == "feature" else None
    row_b = got_b["row"] if got_b["kind"] == "feature" else None
    if row_a is not None and row_b is not None and row_a["id"] == row_b["id"]:
        # The audit's exact case: reminders and alarms are ONE scheduler row,
        # not two features. Say that plainly rather than inventing a
        # difference between them.
        return {"ok": True, "kind": "feature", "feature": _feature_facts(row_a),
                "features": [{"id": row_a["id"], "title": row_a["title"]}],
                "compare": [_compare_facts(row_a)],
                "words": (f"Both names are in the same feature row - "
                          f"{_comparison_block(row_a)}")}
    if row_a is not None and row_b is not None:
        return {"ok": True, "kind": "feature",
                "features": [{"id": row_a["id"], "title": row_a["title"]},
                             {"id": row_b["id"], "title": row_b["title"]}],
                "compare": [_compare_facts(row_a), _compare_facts(row_b)],
                "words": (_comparison_block(row_a) + "\n\n"
                          + _comparison_block(row_b) + "\n\n"
                          + _difference_sentence(row_a, row_b))}
    if row_a is not None or row_b is not None:
        known = row_a or row_b
        missing = str(second if row_a is not None else first).strip()
        return {"ok": True, "kind": "feature", "feature": _feature_facts(known),
                "features": [{"id": known["id"], "title": known["title"]}],
                "compare": [_compare_facts(known)],
                "words": (f"{_comparison_block(known)} The feature list has no "
                          f"\"{missing}\" row, so there is nothing to compare it with.")}
    if got_a["kind"] == "ambiguous":
        return _discussion_ambiguous(got_a["rows"])
    if got_b["kind"] == "ambiguous":
        return _discussion_ambiguous(got_b["rows"])
    return _discussion_unknown()


#: How many feature names one group's overview answer names before it stops and
#: points at the whole list. Short enough to read, and the pointer carries the
#: rest honestly.
_OVERVIEW_CAP = 6


def _named_group(words):
    """The catalogue group the owner's words name, or None (exact-ish only)."""
    query = _norm(words)
    if not query:
        return None
    words_in = query.split()
    for group in groups():
        name = _norm(group["group"])
        name_words = name.split()
        if query == name or all(w in name_words for w in words_in):
            return group
    return None


def overview(words="") -> dict:
    """"What can you do?" / "what can you do about notes?" - by group, capped."""
    if CATALOGUE is None:
        return {"ok": False, "kind": "missing",
                "words": "The feature list is not installed on this PC, so I cannot read it."}
    group = _named_group(words)
    if group is not None:
        rows = [r for r in features() if r["group"] == group["group"]]
        shown = rows[:_OVERVIEW_CAP]
        titles = "; ".join(r["title"] for r in shown)
        more = (f" and {len(rows) - len(shown)} more" if len(rows) > len(shown) else "")
        return {"ok": True, "kind": "group", "group": group["group"],
                "features": [{"id": r["id"], "title": r["title"]} for r in shown],
                "words": (f"The {group['group']} group has {len(rows)} features: "
                          f"{titles}{more}. " + CAPABILITY_TAIL)}
    got = groups()
    if not got:
        return _discussion_unknown()
    lines = [f"Jarvis has {feature_count()} features in {len(got)} groups:"]
    for group in got:
        rows = [r for r in features() if r["group"] == group["group"]]
        shown = rows[:_OVERVIEW_CAP]
        titles = "; ".join(r["title"] for r in shown)
        more = (f"; and {len(rows) - len(shown)} more"
                if len(rows) > len(shown) else "")
        lines.append(f"  {group['group']} ({group['count']}): {titles}{more}.")
    lines.append(CAPABILITY_TAIL)
    return {"ok": True, "kind": "groups", "groups": got,
            "words": "\n".join(lines)}


# --------------------------------------------------------------------------
#   Detail shapes: "explain X in detail", "how do I use X", "what does X
#   need", "is X private", "why is X on/off", "what can go wrong", "what is
#   X like", "can X do Y" (2026-10-31, the owner's depth ask)
# --------------------------------------------------------------------------
# Every sentence is made from the row's OWN fields plus the state the guide
# already reads for the control matrix. Nothing is inferred: a row with no
# recorded limit says so, a row with no privacy note says so, and "can X do Y"
# answers only when Y's own words are in X's row.

def _detail_bad(words):
    """(row, None) or (None, the ready group/ambiguous/unknown answer)."""
    got = find(str(words or ""), loose=True)
    if got["kind"] == "feature":
        return got["row"], None
    if got["kind"] == "group":
        return None, {"ok": True, "kind": "group", "group": got["group"],
                      "features": [{"id": r["id"], "title": r["title"]}
                                   for r in got["rows"]],
                      "words": _group_words(got["group"], got["rows"])
                      + " " + CAPABILITY_TAIL}
    if got["kind"] == "ambiguous":
        return None, _discussion_ambiguous(got["rows"])
    return None, _discussion_unknown()


def _detail_state(row: dict) -> str:
    """The row's approved label, plus the live switch state when it has one."""
    return (f"Its state: {status_label(row)}. "
            + _state_clause(_switch_state_rows(row)))


def _detail_needs(row: dict) -> str:
    """What the row itself says it needs to be used: its place and ask rule."""
    where = str(row.get("where") or "").strip()
    asks = str(row.get("asks") or "").strip()
    return (f"What it needs: {settings_path_words(row)}; "
            f"{where} Does it ask first? {asks}")


def detail(words) -> dict:
    """"Explain X in detail" / "tell me everything about X" - every own field."""
    if CATALOGUE is None:
        return {"ok": False, "kind": "missing",
                "words": "The feature list is not installed on this PC, so I cannot read it."}
    row, bad = _detail_bad(words)
    if bad is not None:
        return bad
    if row is None:
        return _detail_bad(words)[1]
    parts = [
        f"{row['title']}.",
        str(row.get("what") or "").strip(),
        f"Where it lives: {str(row.get('where') or '').strip()}",
        f"How to use it: {change_words(row)} {example_phrase_words(row)}",
        f"Does it ask first? {str(row.get('asks') or '').strip()}",
        f"The honest limit: {_limit_words(row)}",
        _detail_state(row),
        f"Which app(s): {surface_words(row)} "
        f"(the feature list's surface field: {str(row.get('surface') or '').strip()})",
        _detail_needs(row),
        f"(Feature list group: {row['group']}.)",
        CAPABILITY_TAIL,
    ]
    return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
            "words": "\n\n".join(p for p in parts if p and p.strip())}


def example(words) -> dict:
    """"What do I say to use X?" / "give me an example of X" - the row's example."""
    row, bad = _detail_bad(words)
    if bad is not None:
        return bad
    if row is None:
        return _detail_bad(words)[1]
    return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
            "words": (f"{row['title']}. {example_phrase_words(row)} "
                      f"Where: {str(row.get('where') or '').strip()} "
                      f"Does it ask first? {str(row.get('asks') or '').strip()} "
                      f"The honest limit: {_limit_words(row)} "
                      + CAPABILITY_TAIL)}


def is_private(words) -> dict:
    """"Is X private?" - only what the row's own words say about privacy."""
    row, bad = _detail_bad(words)
    if bad is not None:
        return bad
    if row is None:
        return _detail_bad(words)[1]
    markers = ("private", "never leaves", "encrypted", "on this pc", "local",
               "never uploaded", "never learned", "outside text", "sensitive",
               "phone only", "app lock", "never shown", "kept")
    own = " ".join(str(row.get(k) or "") for k in ("what", "where", "asks", "limit"))
    hits = [m for m in markers if m in own.lower()]
    if hits:
        words = (f"{row['title']}. The feature list's own privacy words are: "
                 f"Where: {str(row.get('where') or '').strip()} "
                 f"Does it ask first? {str(row.get('asks') or '').strip()} "
                 f"The honest limit: {_limit_words(row)}")
    else:
        words = (f"{row['title']}. The feature list records no separate privacy "
                 f"note for it. Its own words: "
                 f"Where: {str(row.get('where') or '').strip()} "
                 f"Does it ask first? {str(row.get('asks') or '').strip()} "
                 f"The honest limit: {_limit_words(row)}")
    return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
            "words": words + " " + CAPABILITY_TAIL}


def needs(words) -> dict:
    """"What does X need / require?" - only the row's own Where/Settings/asks."""
    row, bad = _detail_bad(words)
    if bad is not None:
        return bad
    if row is None:
        return _detail_bad(words)[1]
    return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
            "words": (f"{row['title']}. {_detail_needs(row)} "
                      f"Which app(s): {surface_words(row)} "
                      f"The honest limit: {_limit_words(row)} "
                      + CAPABILITY_TAIL)}


def why_state(words) -> dict:
    """"Why is X on/off?" - the row's own state, label and ask/limit words."""
    row, bad = _detail_bad(words)
    if bad is not None:
        return bad
    if row is None:
        return _detail_bad(words)[1]
    return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
            "words": (f"{row['title']}. {_detail_state(row)} "
                      f"Does it ask first? {str(row.get('asks') or '').strip()} "
                      f"The honest limit: {_limit_words(row)} "
                      + CAPABILITY_TAIL)}


def goes_wrong(words) -> dict:
    """"What can go wrong with X?" - its own honest limit, never an invention."""
    row, bad = _detail_bad(words)
    if bad is not None:
        return bad
    if row is None:
        return _detail_bad(words)[1]
    limit = str(row.get("limit") or "").strip()
    if not limit:
        words = (f"{row['title']}. The feature list records no limit for it, so I "
                 f"cannot name what can go wrong. Its own words: "
                 f"Where: {str(row.get('where') or '').strip()} "
                 f"Does it ask first? {str(row.get('asks') or '').strip()}")
    else:
        words = (f"{row['title']}. The honest limit: {limit} "
                 f"Does it ask first? {str(row.get('asks') or '').strip()}")
    return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
            "words": words + " " + CAPABILITY_TAIL}


def can_do(words, capability) -> dict:
    """"Can X do Y?" - only if Y's own words are in X's row text."""
    row, bad = _detail_bad(words)
    if bad is not None:
        return bad
    if row is None:
        return _detail_bad(words)[1]
    want = tuple(w for w in _tokens(capability) if w not in _STOP)
    if not want:
        return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                "words": (f"{row['title']}. Say what ability you mean and I will "
                          f"look only in that feature's own words. "
                          f"The honest limit: {_limit_words(row)} "
                          + CAPABILITY_TAIL)}
    own = (str(row.get("what") or ""), str(row.get("where") or ""),
           str(row.get("asks") or ""), str(row.get("limit") or ""))
    if _contains_all(_tokens(" ".join(own)), want):
        hits = [s for s in own if s.strip() and _contains_all(_tokens(s), want)]
        return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                "words": (f"{row['title']}. The feature list's own words: "
                          + " ".join(hits)
                          + f" The honest limit: {_limit_words(row)} "
                          + CAPABILITY_TAIL)}
    return {"ok": True, "kind": "not_listed", "feature": _feature_facts(row),
            "words": (f"{row['title']}. That is not listed as part of "
                      f"{row['title']}. The honest limit: {_limit_words(row)} "
                      f"Does it ask first? {str(row.get('asks') or '').strip()} "
                      + CAPABILITY_TAIL)}


def is_like(words) -> dict:
    """"What is X like?" - the row's what/where/limit plus its state."""
    row, bad = _detail_bad(words)
    if bad is not None:
        return bad
    if row is None:
        return _detail_bad(words)[1]
    return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
            "words": (f"{row['title']}. {str(row.get('what') or '').strip()} "
                      f"Where: {str(row.get('where') or '').strip()} "
                      f"Does it ask first? {str(row.get('asks') or '').strip()} "
                      f"The honest limit: {_limit_words(row)} "
                      f"{_detail_state(row)} "
                      f"Which app(s): {surface_words(row)} "
                      + CAPABILITY_TAIL)}


# --------------------------------------------------------------------------
#   "Is it on?": a feature, or a plain setting the registry already names
# --------------------------------------------------------------------------

def _setting_by_own_label(text):
    """The switch whose OWN registered name is `text`, compared with case and
    punctuation folded, or None.

    2026-11-02, measured: `R.find_bool_setting` is an EXACT alias match on
    purpose (a half-heard sentence must fall through rather than change a
    switch nobody named), but it compares a lower-cased, punctuation-freed
    query against names kept as written. So a switch whose Settings label has
    a capital or an apostrophe could not be named by that label at all:
    "saving facts in Jarvis's own words" (the label the owner read on the new
    learning card) folded to "saving facts in s own words" once `_norm` and the
    generic-word filter both ran, and there is no other path to it - the guide
    said "I do not have a feature called ...". This compares the owner's words
    with each switch's own names through the SAME fold on both sides, and only
    when they are equal: it widens punctuation and case, never the words. It
    cannot hand back a different setting, because a name is that setting's own.
    """
    R = _registry()
    return _own_label_match(getattr(R, "BOOL_SETTINGS", ()) if R else (), text)


def _own_label_match(rows, text):
    """The row in `rows` one of whose OWN names is `text`, folded, or None."""
    want = _norm(text)
    if not want:
        return None
    for setting in rows or ():
        for name in getattr(setting, "names", ()) or ():
            if _norm(name) == want:
                return setting
    return None


def _choice_by_own_label(text):
    """The named-choice setting whose OWN registered name is `text`, or None.

    The same fold, and the same reason, as `_setting_by_own_label` above: a
    choice's name may carry a capital or an apostrophe ("the anti-slop mode",
    "jarvis's personality"), and the exact registry lookup compares it as
    written. Added 2026-11-03 with the choice branch of `_setting_target`, so a
    label the owner reads on a Settings card answers for a choice exactly as it
    already did for a switch."""
    R = _registry()
    return _own_label_match(getattr(R, "CHOICE_SETTINGS", ()) if R else (), text)


def _is_choice(setting) -> bool:
    """Is this registry row a named-choice setting (rather than a switch)?"""
    R = _registry()
    kind = getattr(R, "ChoiceSetting", None) if R is not None else None
    return bool(kind is not None and isinstance(setting, kind))


def _section_place(section_id) -> str:
    """`Settings, <the card's own first name>` - or plain `Settings`.

    The same words `jarvis_settings_registry._section_place` answers with, read
    from the one SECTIONS table, so a choice's "where" and a switch's "where"
    are never two different phrases for the same card."""
    R = _registry()
    sec = None
    if R is not None and section_id:
        try:
            sec = R.section_by_id(str(section_id))
        except Exception:                   # noqa: BLE001 - plain "Settings"
            sec = None
    if sec is not None and getattr(sec, "names", ()):
        return f"Settings, {sec.names[0]}"
    return "Settings"


def _setting_target(words):
    """(setting, label) for a plain on/off setting OR a named-choice setting
    named exactly, or (None, "").

    Two looks per kind, in this order: the registry's own exact alias match
    (the vocabulary the spoken phrases are built on), then the setting's own
    registered NAME with case and punctuation folded - so the words printed on
    the Settings card always answer, even when they carry an apostrophe or a
    capital the exact index does not hold. Neither look guesses: both require
    the whole name.

    CHOICES ANSWER TOO, SINCE 2026-11-03 (M4). It used to be bool-only, so
    `feature_state_setting` / `feature_howto_setting` could never fire for any
    of the ten CHOICE_SETTINGS rows: "is the personality set to warm?" and "how
    do I change the anti-slop mode?" answered from the catalogue or not at all.
    A switch is still tried FIRST, so no existing answer changes meaning.
    """
    R = _registry()
    if R is None:
        return None, ""
    text = " ".join(w for w in _norm(words).split() if w not in _GENERIC)
    setting = R.find_bool_setting(text)
    if setting is None:
        setting = _setting_by_own_label(words)
    if setting is not None:
        return setting, _setting_words(setting)
    choice = R.find_choice_setting(text)
    if choice is None:
        choice = _choice_by_own_label(words)
    if choice is None:
        return None, ""
    return choice, _setting_words(choice)


def _choice_value(setting):
    """The choice's value in words right now, or None when it cannot be read.

    Through the registry's ONE reader for the row (`current_value` ->
    `ChoiceSetting.now`), so the state shown here is the same value the explain
    answer shows and the same one the clarifying question prints."""
    R = _registry()
    if R is None:
        return None
    try:
        return R.current_value(setting)
    except Exception:                       # noqa: BLE001 - said as unreadable
        return None


def _choice_by_key(words):
    """The ChoiceSetting whose registry KEY is `words`, folded, or None.

    WHY THE KEY IS A SIGNAL OF ITS OWN (2026-11-03). `feature_state_setting` /
    `feature_howto_setting` carry `setting.key` ("personality",
    "antislop_mode"), not a sentence, so the answer must be about THAT row. The
    feature catalogue is matched first for a person's words, and it would win
    here for the wrong reason: "personality" is a loose alias of the "How
    Jarvis talks" row, whose own switch is HUMOUR - so asking about the
    personality preset would have answered "on right now (humour)".
    Only a choice key is treated this way, never a switch key, so every
    existing bool answer keeps the wording its own tests pin.
    """
    R = _registry()
    if R is None:
        return None
    want = _norm(words)
    if not want:
        return None
    for choice in getattr(R, "CHOICE_SETTINGS", ()) or ():
        if _norm(choice.key) == want:
            return choice
    return None


def _choice_state(setting) -> dict:
    """The "is it on?" answer for a named-choice setting: its real value."""
    label = _setting_words(setting)
    here = _choice_value(setting)
    if not here:
        return {"ok": True, "kind": "setting", "setting": setting.key,
                "label": label, "state": None,
                "words": (f"I could not read which value {label} has - the "
                          f"module that owns it is not answering on this PC. "
                          f"I will not guess.")}
    return {"ok": True, "kind": "setting", "setting": setting.key,
            "label": label, "state": here,
            "words": f"{label.capitalize()} is set to {here} right now."}


def _choice_how_to(setting, label: str, on: bool) -> dict:
    """The "how do I change it?" answer for a named-choice setting.

    A CHOICE HAS NO ON/OFF (2026-11-03, M4): "how do I turn it on?" is the
    wrong sentence for a value picked from a list, so the answer names the
    place, its value and a real `set <name> to <value>` phrase built from the
    row's OWN value list - the same vocabulary jarvis_quick's settings_choice
    grammar accepts, so the phrase offered is a phrase that works."""
    where = _section_place(getattr(setting, "where", None))
    here = _choice_value(setting)
    try:
        options = sorted(set(setting.options().keys()))
    except Exception:                       # noqa: BLE001 - no list to name
        options = []
    clause = ("" if not here else f" It is set to {here} right now.")
    if not options:
        return {"ok": True, "kind": "setting", "setting": setting.key,
                "label": label, "state": here,
                "words": (f"{label.capitalize()} is in {where}.{clause} There is "
                          f"no value to name on this PC yet, so ask \"what are "
                          f"the choices for {label}?\" to check.")}
    return {"ok": True, "kind": "setting", "setting": setting.key,
            "label": label, "state": here,
            "words": (f"{label.capitalize()} is in {where}. Say \"set {label} to "
                      f"{options[0]}\" and I will do it; a change that needs "
                      f"approval still asks on a card first.{clause}")}


def state(words) -> dict:
    """Read the current on/off for a feature or a plain setting - or say why not.

    This NEVER claims a state it did not read: a feature with no switch, a
    feature whose switch module is missing, and an unknown name each get their
    own honest sentence.
    """
    if CATALOGUE is None:
        return {"ok": False, "kind": "missing",
                "words": "The feature list is not installed on this PC, so I cannot read it."}
    if _cloud_sync_asked(words):
        return {"ok": True, "kind": "note", "state": None,
                "words": CLOUD_SYNC_WORDS}
    # A registry KEY (what the intent carries) is answered as that row, before
    # the catalogue - see `_choice_by_key`.
    choice_key = _choice_by_key(words)
    if choice_key is not None:
        return _choice_state(choice_key)
    got = find(words, loose=True)
    if got["kind"] == "feature":
        row = got["row"]
        rows = _switch_state_rows(row)
        if not rows:
            # A row switched on by an AI-tool switch (2026-11-07): its state is
            # read from the same page the apps draw, never from a BoolSetting,
            # and never reported as "no switch" (its own `where` says it has one).
            tool = _tool_switch_rows(row)
            if _names_tool_switch(row):
                known = [s for s in tool if isinstance(s["state"], bool)]
                value = None
                if known and len({s["state"] for s in known}) == 1:
                    value = known[0]["state"]
                if len(tool) == 1 and len(known) == 1:
                    words = (f"\"{row['title']}\" is "
                             f"{ON_WORD if value else OFF_WORD} right now "
                             f"({tool[0]['label']}).")
                else:
                    words = f"{row['title']}: {_tool_switch_words(row)}"
                return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                        "state": value, "switches": tool, "words": words}
            has_control = (str((_matrix_row(row) or {}).get("status") or "")
                           in _HAS_A_CONTROL)
            if str((_matrix_row(row) or {}).get("status") or "") == "planned":
                words = (f"{row['title']}: it is not wired yet, so I could not "
                         f"read a state for it. {_planned_reason(row)}")
                return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                        "state": None, "switches": [], "words": words}
            words = (f"{row['title']}: {_no_switch_words(row)}" if has_control else
                     f"{row['title']} has no on/off switch in the feature list, "
                     f"so there is no state for me to read.")
            return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                    "state": None, "switches": [], "words": words}
        known = [r for r in rows if isinstance(r["state"], bool)]
        if not known:
            return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                    "state": None, "switches": rows,
                    "words": (f"I could not read {row['title']}'s switch on this PC, so "
                              f"I will not guess whether it is on.")}
        if len(known) == 1:
            value = known[0]["state"]
            switch_name = str(known[0]["label"] or "")
            aside = (f" ({switch_name})" if switch_name
                     and switch_name.lower() not in row["title"].lower() else "")
            return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                    "state": value, "switches": rows,
                    "words": (f"\"{row['title']}\" is {ON_WORD if value else OFF_WORD} "
                              f"right now{aside}.")}
        return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                "state": known[0]["state"] if len({r["state"] for r in known}) == 1 else None,
                "switches": rows,
                "words": f"{row['title']}: " + _state_clause(rows)}
    if got["kind"] == "ambiguous":
        return {"ok": False, "kind": "ambiguous",
                "candidates": [{"id": r["id"], "title": r["title"]} for r in got["rows"]],
                "words": _ambiguous_words(got["rows"])}
    setting, label = _setting_target(words)
    if setting is not None:
        if _is_choice(setting):
            return _choice_state(setting)
        value = read_state(setting.key)
        if not isinstance(value, bool):
            return {"ok": True, "kind": "setting", "setting": setting.key,
                    "label": label, "state": None,
                    "words": (f"I could not read whether {label} is on - the module "
                              f"that owns it is not answering on this PC. I will not guess.")}
        return {"ok": True, "kind": "setting", "setting": setting.key,
                "label": label, "state": value,
                "words": f"{label.capitalize()} is {ON_WORD if value else OFF_WORD} right now."}
    return {"ok": False, "kind": "unknown", "groups": [g["group"] for g in groups()],
            "words": unknown_words(words)}


# --------------------------------------------------------------------------
#   "How do I turn it on/off?": facts, and the exact phrase that would do it
# --------------------------------------------------------------------------

def how_to(words, on: bool) -> dict:
    """Where to change it, whether a card is needed, its current state, and the
    exact fixed phrase that changes it - WITHOUT changing anything."""
    if CATALOGUE is None:
        return {"ok": False, "kind": "missing",
                "words": "The feature list is not installed on this PC, so I cannot read it."}
    # A registry KEY (what the intent carries) is answered as that row, before
    # the catalogue - see `_choice_by_key`.
    choice_key = _choice_by_key(words)
    if choice_key is not None:
        return _choice_how_to(choice_key, _setting_words(choice_key), bool(on))
    got = find(words, loose=True)
    if got["kind"] == "feature":
        row = got["row"]
        rows = _switch_state_rows(row)
        base = (f"{row['title']}. Where: {str(row.get('where') or '').strip()} "
                f"Does it ask first? {str(row.get('asks') or '').strip()}")
        if not rows:
            # A row switched on by an AI-tool switch (2026-11-07): there is no
            # fixed typed sentence - the switch is the page's own control - so
            # the answer names that switch and its live state instead of
            # claiming "nothing to turn on or off".
            tool = _tool_switch_rows(row)
            if _names_tool_switch(row):
                labels = "; ".join(f'"{s["label"]}"' for s in tool)
                tail = ('To change it, use its own switch in Settings, What asks '
                        'first, under "Let the AI use this"'
                        + (f': {labels}.' if labels else '.')
                        + ' There is no fixed sentence for it. '
                        + _tool_switch_words(row))
                return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                        "switches": tool, "words": (base + " " + tail)}
            # An ability with no switch is not a dead end: say which kind it is
            # and how to use it, in the same words the "turn on <ability>"
            # phrase already gives (2026-10-26). A row that DOES have a control
            # - just not a boolean one this build can read - gets the honest
            # "I cannot read that switch" instead (2026-11-04 audit).
            has_control = (str((_matrix_row(row) or {}).get("status") or "")
                           in _HAS_A_CONTROL)
            if str((_matrix_row(row) or {}).get("status") or "") == "planned":
                return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                        "switches": [], "words": (
                            base + f" It is not wired yet: {_planned_reason(row)}")}
            tail = (_no_switch_words(row) if has_control else
                    "The feature list names no on/off switch for it, so there is "
                    "nothing to turn on or off there. " + ability_explanation(row))
            return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                    "switches": [], "words": (base + " " + tail)}
        if len(rows) == 1:
            label = rows[0]["label"]
            return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                    "switches": rows,
                    "words": (base + f" To change it, say \"turn {ON_WORD if on else OFF_WORD} "
                                     f"{label}\" - and if it needs approval, a card asks first. "
                             + _state_clause(rows))}
        return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                "switches": rows,
                "words": (base + " That feature has more than one switch: "
                          + "; ".join(f"\"{r['label']}\"" for r in rows)
                          + ". Say \"turn on <one of those>\" for the one you mean. "
                          + _state_clause(rows))}
    if got["kind"] == "ambiguous":
        return {"ok": False, "kind": "ambiguous",
                "candidates": [{"id": r["id"], "title": r["title"]} for r in got["rows"]],
                "words": _ambiguous_words(got["rows"])}
    setting, label = _setting_target(words)
    if setting is not None:
        if _is_choice(setting):
            return _choice_how_to(setting, label, bool(on))
        section = getattr(setting, "section", None)
        where = f"Settings, {section}" if section else "Settings"
        value = read_state(setting.key)
        clause = ("" if not isinstance(value, bool) else
                  f" It is {ON_WORD if value else OFF_WORD} right now.")
        return {"ok": True, "kind": "setting", "setting": setting.key, "label": label,
                "state": value, "words": (f"{label.capitalize()} is in {where}. "
                                          f"Say \"turn {ON_WORD if on else OFF_WORD} {label}\" "
                                          f"and I will do it; a change that loosens a rule "
                                          f"still asks on a card first.{clause}")}
    return {"ok": False, "kind": "unknown", "groups": [g["group"] for g in groups()],
            "words": unknown_words(words)}


# --------------------------------------------------------------------------
#   "Turn it on/off": which ONE switch the feature names, or none
# --------------------------------------------------------------------------

def switch_target(words):
    """(setting, on_word_ok) for a feature that names exactly one switch.

    Returns (setting, "") when it does; otherwise (None, words) with a plain
    sentence saying why nothing will be changed (several switches, or none).
    The caller applies the change through setting.set - the SAME setter and
    card rule every spoken setting change uses.
    """
    if CATALOGUE is None:
        return None, "The feature list is not installed on this PC, so I cannot read it."
    got = find(words, loose=False)
    if got["kind"] != "feature":
        if got["kind"] == "ambiguous":
            return None, _ambiguous_words(got["rows"])
        return None, unknown_words(words)
    row = got["row"]
    rows = switches_for(row)
    if not rows:
        # Ruling Q2(a), 2026-10-22: an ability with no switch gets a
        # deterministic label + real example + exact Settings path - never a
        # fake switch and never a model guess.
        return None, ability_explanation(row)
    if len(rows) > 1:
        return None, (f"{row['title']} has more than one switch: "
                      + "; ".join(_setting_words(s) for s in rows)
                      + ". Say \"turn on <one of those>\" for the one you mean.")
    return rows[0], ""


def tool_result(words) -> dict:
    """What the model tool returns: the same exact facts, plus the sentence it
    may reword. Empty (or a group name) lists the groups/group instead."""
    text = str(words or "").strip()
    if not text:
        return {"ok": True, "kind": "groups", "groups": groups(),
                "words": groups_words()}
    got = find(text, loose=True)
    if got["kind"] == "group":
        return list_features(text)
    return explain(text)

# --------------------------------------------------------------------------
#   The command-side matrix (2026-10-22, the owner's universal-controls
#   requirement): every feature, what can be typed for it, and the reasoned
#   answer for every feature that cannot be changed by typing.
# --------------------------------------------------------------------------
#
# This is the COMMAND-SIDE truth only - which phrase resolves to which real
# setter. The cross-surface truth (desktop and phone Settings evidence) lives
# in lock-hook's `contract/feature-controls.json`; the checker there joins the
# two by feature id. Do not add a second copy of that contract here.

#: The Settings cards whose control IS adjustable by typing, with a
#: representative sentence for each. control_matrix() feeds every one of these
#: through the REAL intent matcher and reports the intent it got, so a phrase
#: that stops resolving shows up as a gap rather than a promise.
ADJUST_SECTIONS = {
    "web-search": (("switch web search to exa", "choice"),),
    "manner": (("from now on be brief", "choice"),),
    "voice": (("speak faster", "choice"),),
    "limits": (("speak up 3 times a day", "number"),
               ("the brief at 8pm", "number")),
    "approval-cards": (("show the whole approval card", "choice"),),
    "asks-first": (("stop asking before my calendar", "tier"),),
    "reach": (("let the ai model read my calendar", "tool"),),
    "animal-options": (("keep the animal still", "switch"),
                       ("turn on the sun and moon", "switch"),
                       ("use home assistant for the weather", "choice")),
    "menu-visibility": (("hide the brain menu", "menu"),),
    "handoff": (("set the captcha hand-off to patient", "choice"),),
    "handoff-front": (("bring the captcha window to the front", "choice"),),
    # A pseudo-place for the Brain Memory topic picker: the topic mode IS
    # adjustable by typing ("stop using my work topic"), and the catalogue names
    # the Brain page rather than a Settings card, so EXTRA_ADJUST links it here.
    "topics": (("stop using my work topic", "tier"),),
    # The VoiceStudio switch (2026-11-13, the awareness audit's GAP-9): its
    # section id is the Settings card, and the phrase is the typed switch that
    # really writes `[voicestudio] enabled`. It is a plain on/off, so the kind
    # is "switch".
    "voicestudio": (("turn on voicestudio", "switch"),),
}

#: Stable reason codes for a feature that cannot be changed by typing.
REASON_CODES = ("command", "no-command", "credentials", "app-local",
                "read-only", "multi-field", "pc-only", "not-a-setting",
                "planned-no-own-control")

#: Feature id -> (reason_code, plain reason, owner). Every feature in the
#: catalogue is either command-controllable or named here; the suite fails on
#: a silent omission, and also fails if an id named here IS controllable
#: (that would be a stale excuse). The reasons say WHY, not "not supported".
NO_COMMAND_REASON = {
    "media-transport": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "parking": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "places": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "thinking-levels": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "calculator": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "open-programs": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "github-research": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "computer-control": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "browser-control": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "shell-commands": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "read-web-page": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "propose-plan": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "reverse-engineering": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "android-builder": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "docker-containers": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "card-summary": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "receipts": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    # The VoiceStudio row LEFT this table on 2026-11-13 (the awareness audit's
    # GAP-9): it now has its own typed switch ("turn on voicestudio" is ONE
    # change_own_config card plus Windows Hello, "turn off voicestudio" is
    # instant, "is voicestudio on" reads it back) and its own row in Settings,
    # The PC itself. The suite fails if a row named here IS controllable, so the
    # stale excuse is deleted rather than reworded - what is still not built (the
    # speaking-voice wiring) is said by the feature row's own `limit` and by
    # jarvis_voicestudio.STATE_ON.
    "search-audio-video": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "notion-import": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    # Joined 2026-11-06 with the row that catches the catalogue up to the two
    # phone doors built on 2026-11-05: sending a document from the phone is an
    # action with ONE card of its own, not a stored setting; there is no switch
    # to turn on or off, and its Settings row is the folder list that already
    # has its own row.
    "document-from-phone": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    "vault-organizer": ("not-a-setting", "An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.", "none-needed"),
    # The three planned Switchable rows (2026-10-23) still need an allowlist
    # reason for matrix_rows_without_reason(); their label stays Switchable and
    # their row status stays planned, so this reason is reported, not a hidden pass.
    # (wake-word left this table and PLANNED_SWITCHABLE on 2026-11-13: it has
    # its own typed switch, so it is command-controllable and an allowlist row
    # for it would now be a stale excuse.)
    "read-aloud": ("planned", "The read-aloud switch, its chat and Live words and the speaker on each answer ship. This row is still marked planned only because the switch is its own saved setting rather than one of the registry switches, so the guide has no registry phrase to pin.", "voiceprint-wiring"),
    "spoken-style": ("planned", "spoken style is automatic, not a registered switch or typed control yet", "voiceprint-wiring"),
    "home-status": ("planned", "no own typed phrase is wired for the home-status feature yet", "voiceprint-wiring"),

    # The reasoned allowlist (2026-10-22). Every feature the catalogue
    # publishes is either command-controllable (a switch or a working
    # adjust phrase, proved by control_matrix()) or named here with a
    # stable reason code and an owner. The suite fails on a silent
    # omission AND on an entry that claims a controllable feature is not.
    "typing": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "talk-button": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "voice-training": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    # Added with the two 2026-10-31 rows: the notes editor and Protected from
    # Jarvis are abilities/read-write actions, not stored settings with a switch
    # of their own. Their cards and Settings row carry the real rules.
    "notes-editor": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "cloud-escalation": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: the Cloud row is a preset choice and the standing switch is on its own card; the cards and the fixed chat answers carry the rule, so there is no separate stored setting.', 'none-needed'),
    "protected-items": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    # Joined 2026-10-31 with the send-file row: a chat action plus a phone-side
    # listing, not a stored setting - its own Settings row carries the rule.
    "file-from-pc": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "voice-check": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "interrupt": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "live": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "live-extras": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "talk-to-type": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "chat-thread": ('app-local', "Saved by each app locally (this computer's or this phone's own appearance or behaviour) with no backend route to change it. The Settings control is its one true home; a typed path would need a client-side route the backend cannot invent.", 'setup-ui'),
    "temporary-chat": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "private-chat": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "history-search": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "coming-up": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "today": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "widgets": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "jobs": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "now": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "focus": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "memory-tab": ('read-only', 'An information or navigation page - it shows facts or opens a place. There is no setting here to change.', 'none-needed'),
    "memory-waiting": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "memory-known": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "memory-people": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "people-dossier": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "pinned-facts": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "between-us": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "wiki": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "deep-questions": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "memory-as-of": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "import-chats": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "chat-tags": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "forget-range": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "galaxy": ('read-only', 'An information or navigation page - it shows facts or opens a place. There is no setting here to change.', 'none-needed'),
    "watch-with-me": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "photo-reminder": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "live-camera": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "quiz": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "decks": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "notes-write": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "folders": ('multi-field', 'A multi-field or multi-step control (a file or folder picked on the PC, several values at once, or a route that lives in a patch-carried file): one typed value cannot reach the same setter safely yet. Recorded as a gap with an owner rather than guessed.', 'voiceprint-wiring'),
    "documents": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "tutorials": ('read-only', 'An information or navigation page - it shows facts or opens a place. There is no setting here to change.', 'none-needed'),
    "pc-help": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "github-watchlist": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    # The connected-GitHub surface (2026-11-07, the owner's 2026-11-03 "Read +
    # actions" decision finally given its catalogue row). The ten TOOLS each
    # have their own switch on Settings, What asks first - no ONE switch belongs
    # to the feature itself, so the row is an ability with six carded writes
    # (comment, open an issue, re-run a workflow, create one repository, merge,
    # fix-and-push) and no boolean of its own.
    "connected-github": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "chatbot": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "support": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "projects": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "goals": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "progress": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "spending": ('multi-field', 'A multi-field or multi-step control (a file or folder picked on the PC, several values at once, or a route that lives in a patch-carried file): one typed value cannot reach the same setter safely yet. Recorded as a gap with an owner rather than guessed.', 'voiceprint-wiring'),
    "retirement": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "chatbot-money": ('credentials', 'Credentials and pairing are never typed or spoken into a chat - the owner\'s 2026-10-22 decision keeps Accounts/keys and the pairing token Settings-only. Say "open accounts" to jump there.', 'none-needed'),
    "crisis-help": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "locks": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "email-send": ('multi-field', 'A multi-field or multi-step control (a file or folder picked on the PC, several values at once, or a route that lives in a patch-carried file): one typed value cannot reach the same setter safely yet. Recorded as a gap with an owner rather than guessed.', 'voiceprint-wiring'),
    "email-drafts": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "inbox-tidy": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "news-and-page-watches": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "connection": ('credentials', 'Credentials and pairing are never typed or spoken into a chat - the owner\'s 2026-10-22 decision keeps Accounts/keys and the pairing token Settings-only. Say "open accounts" to jump there.', 'none-needed'),
    "devices": ('credentials', 'Credentials and pairing are never typed or spoken into a chat - the owner\'s 2026-10-22 decision keeps Accounts/keys and the pairing token Settings-only. Say "open accounts" to jump there.', 'none-needed'),
    "phone-floating": ('app-local', "Saved by each app locally (this computer's or this phone's own appearance or behaviour) with no backend route to change it. The Settings control is its one true home; a typed path would need a client-side route the backend cannot invent.", 'Session B'),
    "phone-tiles": ('app-local', "Saved by each app locally (this computer's or this phone's own appearance or behaviour) with no backend route to change it. The Settings control is its one true home; a typed path would need a client-side route the backend cannot invent.", 'Session B'),
    "phone-screen-rate": ('app-local', "Saved by each app locally (this computer's or this phone's own appearance or behaviour) with no backend route to change it. The Settings control is its one true home; a typed path would need a client-side route the backend cannot invent.", 'Session B'),
    # "Picture-in-picture" (2026-10-30, docs/PIP-DESIGN.md): Android's own small
    # Jarvis window over other apps. Its mode is a phone setting like Floating
    # Jarvis's, with no backend route - the PC neither knows nor needs to know
    # what this phone's window shows.
    "phone-pip": ('app-local', "Saved by each app locally (this computer's or this phone's own appearance or behaviour) with no backend route to change it. The Settings control is its one true home; a typed path would need a client-side route the backend cannot invent.", 'Session B'),
    "also-on-phone": ('read-only', 'An information or navigation page - it shows facts or opens a place. There is no setting here to change.', 'none-needed'),
    "find-phone": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "phone-limits": ('read-only', 'An information or navigation page - it shows facts or opens a place. There is no setting here to change.', 'none-needed'),
    "appearance": ('app-local', "Saved by each app locally (this computer's or this phone's own appearance or behaviour) with no backend route to change it. The Settings control is its one true home; a typed path would need a client-side route the backend cannot invent.", 'setup-ui'),
    "crash-notes": ('read-only', 'An information or navigation page - it shows facts or opens a place. There is no setting here to change.', 'none-needed'),
    "first-run": ('read-only', 'An information or navigation page - it shows facts or opens a place. There is no setting here to change.', 'none-needed'),
    "setup-questionnaire": ('read-only', 'An information or navigation page - it shows facts or opens a place. There is no setting here to change.', 'none-needed'),
    "shortcuts": ('app-local', "Saved by each app locally (this computer's or this phone's own appearance or behaviour) with no backend route to change it. The Settings control is its one true home; a typed path would need a client-side route the backend cannot invent.", 'setup-ui'),
    "models": ('multi-field', 'A multi-field or multi-step control (a file or folder picked on the PC, several values at once, or a route that lives in a patch-carried file): one typed value cannot reach the same setter safely yet. Recorded as a gap with an owner rather than guessed.', 'voiceprint-wiring'),
    "compute": ('multi-field', 'A multi-field or multi-step control (a file or folder picked on the PC, several values at once, or a route that lives in a patch-carried file): one typed value cannot reach the same setter safely yet. Recorded as a gap with an owner rather than guessed.', 'voiceprint-wiring'),
    "skills": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "model-memory": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "start-jarvis": ('pc-only', "A PC-only setting: its control is the PC's own store or one of jarvis_owner_check.PC_ONLY_ACTIONS, and a typed change would have to bypass that gate. Open-only, on purpose.", 'none-needed'),
    "work-tab": ('read-only', 'An information or navigation page - it shows facts or opens a place. There is no setting here to change.', 'none-needed'),
    "job-list": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "hardware": ('multi-field', 'A multi-field or multi-step control (a file or folder picked on the PC, several values at once, or a route that lives in a patch-carried file): one typed value cannot reach the same setter safely yet. Recorded as a gap with an owner rather than guessed.', 'voiceprint-wiring'),
    "updates": ('read-only', 'An information or navigation page - it shows facts or opens a place. There is no setting here to change.', 'none-needed'),
    "tool-updates": ('pc-only', "A PC-only setting: its control is the PC's own store or one of jarvis_owner_check.PC_ONLY_ACTIONS, and a typed change would have to bypass that gate. Open-only, on purpose.", 'none-needed'),
    "settings-file": ('pc-only', "A PC-only setting: its control is the PC's own store or one of jarvis_owner_check.PC_ONLY_ACTIONS, and a typed change would have to bypass that gate. Open-only, on purpose.", 'none-needed'),
    "backend-supports": ('read-only', 'An information or navigation page - it shows facts or opens a place. There is no setting here to change.', 'none-needed'),
    "about": ('read-only', 'An information or navigation page - it shows facts or opens a place. There is no setting here to change.', 'none-needed'),
    "hud-window": ('pc-only', "A PC-only setting: its control is the PC's own store or one of jarvis_owner_check.PC_ONLY_ACTIONS, and a typed change would have to bypass that gate. Open-only, on purpose.", 'none-needed'),
    "backup": ('multi-field', 'A multi-field or multi-step control (a file or folder picked on the PC, several values at once, or a route that lives in a patch-carried file): one typed value cannot reach the same setter safely yet. Recorded as a gap with an owner rather than guessed.', 'voiceprint-wiring'),
    "accounts": ('credentials', 'Credentials and pairing are never typed or spoken into a chat - the owner\'s 2026-10-22 decision keeps Accounts/keys and the pairing token Settings-only. Say "open accounts" to jump there.', 'none-needed'),
    "undo": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "past-approvals": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "settings-by-asking": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "start-the-model-lane": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "restart-the-model-lane": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "clipboard-time-machine": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "file-history": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "app-lock": ('pc-only', "A PC-only setting: its control is the PC's own store or one of jarvis_owner_check.PC_ONLY_ACTIONS, and a typed change would have to bypass that gate. Open-only, on purpose.", 'none-needed'),
    "stale-link": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "stop-everything": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "sensitive-facts": ('not-a-setting', "Health, money and private details wait for the owner's yes: this is an Always-On safety rule, not a switch. The exception (\"also remember sensitive topics automatically\") is its own setting with its own card.", 'none-needed'),
    "trust": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "rush-latch": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "outside-text": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "settings-entry": ('read-only', 'An information or navigation page - it shows facts or opens a place. There is no setting here to change.', 'none-needed'),
    # reminder-actions.patch (2026-10-27): the ONE action a reminder may carry
    # is data the owner types into that reminder, not a stored setting - there
    # is nothing to switch on, and the kind that acts raises its own card.
    "reminder-actions": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    # plugin-switch (2026-11-02, JARVIS-API section 181): the two chat tools and
    # the modify_own_code card ARE the feature. There is no stored setting for
    # it, so there is nothing for a typed on/off phrase or a Settings row to
    # change; the plugin's OWN on/off state is the `disabled` marker in its
    # folder, which the tool writes, not a [settings] key.
    "plugin-switch": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    # 2026-11-02 (self-explain coverage): two abilities the catalogue now has a
    # row for. Neither has a BoolSetting switch - the phone's list is the
    # settings file's [phone_apps] table, and the model answer is a read - so
    # both are a behaviour, and the sentences above are the same rule the other
    # Command-Only rows carry. A setting a part of them owns keeps its own row
    # (control_phone is opt-in in [tools].enabled, and the model switch is the
    # models row's).
    "phone-apps": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    # Recording a call (2026-11-04): an action the phone starts and this PC
    # finishes - there is no in-app switch to turn on (it is a hand edit of
    # [call_recording] enabled, the same shape github_search and shell_exec
    # use), and every rule it has is carried by its own approval card and by
    # the two chat sentences. Hence not-a-setting, not a missing control.
    "call-recording": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    "model-knowledge": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    # The price radar has a switch, but it is the settings file's own
    # `[price_radar] enabled` line, not a registered BoolSetting, and it has no
    # chat approval card yet - so the ROW is a read/behaviour, and the switch it
    # does have is named in its own `where`/`limit`.
    "price-radar": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    # The owner's 2026-11-02 life-coach set (JARVIS-API section 180). Both are
    # ACTIONS with no setting behind them - there is nothing to switch on or
    # off - and neither app has a screen for them yet, so the row's own `where`
    # says "backend only today". The Habits/Mood section on the Reminders
    # screen is the next lane; if it ever adds a real switch, that switch gets
    # its own row and this reason is deleted (a stale entry FAILS the suite).
    "habit-checkins": ('not-a-setting', 'A habit tick is an action, not a stored setting: there is nothing to switch on or off, and the one job it sets up is stopped from its own Stop control rather than a preference. No app has a screen for it yet.', 'none-needed'),
    "mood-log": ('not-a-setting', 'A mood entry is a tap, not a stored setting: there is nothing to switch on or off, and no job of its own. No app has a screen for it yet.', 'none-needed'),
    # Reminder builder (2026-11-02): a reminder that ASKS is the same shape - the
    # question, its buttons and where an answer is written are data the owner
    # sets on ONE reminder, not a stored setting, and answering raises no card at
    # all. Its words reach the PC through the same form as the row above. One
    # entry, appended at the end of the dict so a crossing pull request conflicts
    # nowhere: this file is another lane's, and this is the smallest touch that
    # lets a new feature row exist (the checker below fails a silent omission).
    "reminder-asks": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    # The product check WIRED (2026-11-04, the owner's choice "wire the
    # existing product check"): the feature is ONE chat request and ONE report,
    # and its on/off door is the settings file's own `[product_check] enabled`
    # line, not a registered BoolSetting (there is no in-app switch and no card
    # for the switch yet). So the ROW is the read/behaviour, and the switch it
    # does have is named in its own `where`/`limit`. Appended at the end of the
    # dict for the same crossing-safety reason reminder-asks gives.
    "product-check": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
    # Creator mode (2026-11-09, Wave 13): ONE waiting folder in Settings, a
    # read-only scan when the card is opened, and each install behind its own
    # modify_own_code card. There is no stored setting here to turn on or off -
    # installing is the carded action, and enabling is the ordinary Turn on
    # control - so this row is the read/behaviour. Appended at the end of the
    # dict for the same crossing-safety reason product-check gives.
    "creator-mode": ('not-a-setting', 'An action, a read or a behaviour rather than a stored setting: there is nothing to turn on/off or set. Where part of it has a switch, that switch has its own row.', 'none-needed'),
}

#: Feature ids whose typed controls do not live behind a `settings.<id>` cover,
#: because the feature list names the Brain/Windows page instead. Each entry
#: links the catalogue's own row to the real switch keys that exist for it; the
#: keys are BoolSetting keys from jarvis_settings_registry, checked by the suite.
EXTRA_CONTROLS = {
    # "Write like me" is enabled by its own voices control (POST
    # /api/voiceprint/enabled), not by a Settings toggle row.
    "write-like-me": ("write_like_me",),
    # "Your past chats" is the feature whose on/off switch is chat history.
    "history": ("chat_history",),
    # The lights feature's real switch is the "without a card" row in asks-first,
    # not the asks-first representative sentence (2026-10-23 fix: the old
    # EXTRA_ADJUST entry made the feature show "stop asking before my calendar").
    "lights": ("lights_without_card",),
    # Picture mode's real switch is screen_picture; the old matrix had no link
    # here, so its Command-Only row typed into the switch without owning it.
    "picture-mode": ("screen_picture",),
    # The 30B coder's opt-in switch is drawn INSIDE the desktop Settings card
    # "Big model (slow)" (settings.html, `id="big-model"`, the `#bc-switch`
    # row), so the big-model feature is the row that answers "the big coder" -
    # the phone has no Settings row of its own for it, and its directory sends
    # that name to the big-model row instead (2026-10-23, #749).
    "big-model": ("big_coder",),
    # The Jarvis-owned local calendar (2026-10-29) has its own typed switch
    # from the day its store lands; no Settings row links it yet, so the
    # matrix is told by hand rather than through a `covers` section that the
    # pages do not have.
    "jarvis-calendar": ("jarvis_calendar",),
    # The Anti-Slop filter's own switch (2026-11-02, measured): the row covers
    # `settings.manner` because that is the card it is switched on, and the
    # card's own bool is HUMOUR. `antislop` has section None, so without this
    # link the row read the humour switch and "is the Anti-Slop filter on?"
    # answered with the wrong control. `SECTION_MATES_NOT_THIS_FEATURE` above
    # drops the section-mate, leaving this one.
    "anti-slop": ("antislop",),
}

#: Features that ARE command-controllable but have NO desktop Settings control
#: today. Recorded here so a page-less typed path never LOOKS covered in the
#: matrix: the typed side is real and tested, the Settings half is another
#: owner's work, and the matrix must say both. `controls` names the setting
#: keys that are typed but not drawn in Settings; `desktop`/`phone` are the
#: owners of those halves.
#:
#: EMPTY since 2026-10-28. The two entries this carried were the settings
#: audit's G1 and G5, and both controls now exist:
#:   * `memory-learning` - the two learning switches have the `learning` card
#:     on both apps (settings.html#learning + learning-settings.js, and the
#:     phone's Learning row), so `background_learning` and
#:     `learn_sensitive_topics` have a real desktop row.
#:   * `history` - the chat-history switch and its retention have been drawn in
#:     Settings, Security since 2026-10-22 (chat-history-settings.js); the gap
#:     record was stale, not the page.
#: The dict is kept (and still checked by tools/check_feature_controls.py and
#: backend/test_feature_guide.py) so the next real gap is recorded in the one
#: place the matrix reads, rather than being noticed by nobody.
#:
#: 2026-10-30: the Jarvis calendar's gap is CLOSED, not forgotten. Its typed
#: switch, its four routes and now BOTH Settings halves are real: the phone's
#: row since 2026-10-29 (CalendarSettingsPlate.kt) and the desktop's "Jarvis
#: Calendar" card since 2026-10-30 (settings.html + src/calendar-settings.js,
#: through src-tauri/src/calendar_settings.rs). So the entry that used to sit
#: here was removed rather than left to look like a gap nobody owns - the same
#: way `memory-learning` and `history` left this dict.
SETTINGS_GAPS = {}

#: Feature ids whose ADJUST phrase does not sit behind a `settings.<id>` cover
#: (the catalogue names a Brain page), with the Settings place that proves it.
EXTRA_ADJUST = {
    "attention-budget": ("limits",),
    "topics": ("topics",),
    "email-read": ("asks-first",),
    "calendar": ("asks-first",),
    "home-status": ("asks-first",),
    "weather-sky": ("animal-options",),
    # The face is picked in the Faces window, which is opened from the
    # Appearance card - the catalogue's covers name the window's own id
    # ("faces"), not a Settings section, so the place the typed control sits
    # in has to be named here (2026-10-26).
    "faces": ("appearance-card",),
    # The VoiceStudio row's `covers` is empty: the Settings card it lives on is
    # named by SECTIONS ("voicestudio"), not by a covers token, so the place the
    # typed switch sits in has to be named here (2026-11-13).
    "voicestudio": ("voicestudio",),
}


#: Features that are genuinely Switchable/Adjustable in principle, but have NO
#: own typed control wired today. The old matrix gave them a section's
#: representative phrase (voice speed for wake-word/read-aloud, asks-first for
#: lights), which was untrue. Keep the owner's 42-label count, mark the row
#: planned with its own honest reason, and show no fixed phrase - the directory
#: says "Still being wired" instead of a phrase that changes a different thing.
PLANNED_SWITCHABLE = {
    # The wake-word row LEFT this table on 2026-11-13. Its claim ("no own switch
    # or typed control is wired today") was false when measured: "turn on/off
    # the wake word" is a real typed control (`settings_wake_word`, one approval
    # card to turn on, instant to turn off) and Settings, Voice on the PC draws
    # the switch. The row now carries its own phrase in FEATURE_ADJUST_PHRASES
    # and its own intent in OWN_CONTROLS; the suite fails if a row named here
    # IS controllable, which is why the stale entry is deleted rather than
    # reworded.
    "read-aloud": ("voiceprint-wiring",
                   "The read-aloud switch, its chat and Live words and the speaker on each answer ship. This row is still marked planned only because the switch is its own saved setting rather than one of the registry switches, so the guide has no registry phrase to pin."),
    "spoken-style": ("voiceprint-wiring",
                     "spoken style is automatic, not a registered switch or typed control yet"),
    "home-status": ("voiceprint-wiring",
                    "no own typed phrase is wired for the home-status feature yet"),
}

#: A feature whose section representative phrase names a different tool needs
#: its own sentence. Email read and calendar read are both asks-first actions,
#: but "stop asking before my calendar" is not the email feature's words.
FEATURE_ADJUST_PHRASES = {
    "email-read": ("asks-first", "stop asking before reading my email"),
    # The wake word's own typed switch (2026-11-13). "turn on/off the wake
    # word" is `settings_wake_word` in jarvis_quick, wired to
    # `jarvis_settings_registry.set_wake_word` -> `jarvis_speech.set_wake_enabled`
    # - the same function POST /api/voice/wake calls. It is not a BOOL_SETTINGS
    # row (the desktop draws it as a button in Settings, Voice, not a toggle),
    # so the `voice` section's representative phrase ("speak faster") must be
    # REPLACED for this row, never inherited: that was the old, untrue answer.
    "wake-word": ("voice", "turn on the wake word"),
}

#: Owner-approved 2026-10-23 label corrections (Gemini ADJ-Q1): these three
#: rows are real controls on ONE app only, so they belong under the PC-Only
#: label even though their typed control exists. The old matrix labelled them
#: Switchable/Adjustable because it looked only at status, not at which app
#: the feature lives on.
#: 2026-11-08 (Wave 10, owner ruling Q4): the auto Wi-Fi reconnect switch is
#: PC-only by nature for the same reason - it repairs THIS PC's own link and
#: the route refuses every device but this PC - so it takes the same label.
PC_ONLY_FEATURES = {"calendar", "phone-notifications", "phone-watch",
                    "wifi-auto-reconnect"}

#: Feature id -> (own setting keys, own intent names, expected action values).
#: Used by control_matrix() and the checker: a phrase is this feature's words
#: only when it resolves to one of its OWN settings, not to a section-mate's.
OWN_CONTROLS = {
    "animal-options": ((), ("animal_switch", "animal_sky", "animal_weather"), {}),
    "approvals": ((), ("settings_card_mode",), {}),
    "attention-budget": ((), ("settings_budget",), {}),
    "calendar": ((), ("settings_asks_first",), {"settings_asks_first": {"calendar_read"}}),
    "captcha-handoff": (("handoff_mode", "handoff_front"),
                        ("control_set", "settings_choice"), {}),
    "custom-voices": (("voice_speaker",), ("settings_choice",), {}),
    "data-sandbox": (("sandbox_exec",), ("feature_switch",), {}),
    "email-read": ((), ("settings_asks_first",), {"settings_asks_first": {"email_read"}}),
    # The face (2026-10-26): a named choice reached by "change your face to
    # Red Panda" (control_set) and "use the Orbit face" (settings_choice). The
    # key is the one thing both intents carry, so a phrase that names a
    # DIFFERENT choice cannot be counted as this row's own.
    "faces": (("face",), ("control_set", "settings_choice"), {}),
    "focus-presets": (("focus_preset",), ("control_set",), {}),
    "home-status": ((), ("settings_asks_first",), {"settings_asks_first": {"home_read"}}),
    "lights": (("lights_without_card",), ("settings_bool",), {}),
    "limits": ((), ("settings_budget",), {}),
    "manner": ((), ("manner_from_now_on",), {}),
    "menu-visibility": ((), ("menu_visibility",), {}),
    "picture-mode": (("screen_picture",), ("settings_bool",), {}),
    "reach": ((), ("settings_tool",), {}),
    "topics": ((), ("topic_mode",), {}),
    "weather-sky": ((), ("animal_switch", "animal_sky", "animal_weather"), {}),
    "web-search": (("web_search",), ("search_use", "settings_bool"), {}),
    "what-asks-first": ((), ("settings_asks_first",), {}),
    "write-like-me": (("write_like_me",), ("settings_bool",), {}),
    # The wake word (2026-11-13): its switch is NOT a BoolSetting - it is
    # `jarvis_speech.set_wake_enabled`, drawn as a button in Settings, Voice -
    # but the typed sentence "turn on/off the wake word" really changes it, and
    # it is this row's own control (`settings_wake_word`), not a section-mate's.
    "wake-word": ((), ("settings_wake_word",), {}),
    # The Jarvis calendar (2026-10-29): its typed switch is its own control,
    # linked by EXTRA_CONTROLS because no Settings card draws it yet.
    "jarvis-calendar": (("jarvis_calendar",), ("settings_bool",), {}),
    "look-at-this": (("screen_picture",), ("feature_switch",), {}),
    # The VoiceStudio switch (2026-11-13): its own setting key and its own two
    # intents, so a phrase that changes a DIFFERENT switch cannot be counted as
    # this row's control.
    "voicestudio": (("voicestudio.enabled",),
                    ("voicestudio_set", "voicestudio_state"), {}),
}
OWN_ACTIONS = {
    "email-read": {"settings_asks_first": {"email_read"}},
    "calendar": {"settings_asks_first": {"calendar_read"}},
    "home-status": {"settings_asks_first": {"home_read"}},
}


def _own_words(fid: str, intent) -> bool:
    """True when this intent changes the FEATURE's own setting, not a section-mate's.

    control_matrix() stores intents as their name strings (`_quick_intent`), so
    the string branch is the one the matrix uses; the object branch keeps this
    helper usable by tests that hold a full Intent.
    """
    if intent is None:
        return False
    keys, intents, actions = OWN_CONTROLS.get(fid, ((), (), {}))
    name = intent if isinstance(intent, str) else str(getattr(intent, "name", "") or "")
    if not name:
        return False
    if name not in intents and not (name in ("settings_bool", "feature_switch")
                                    and keys):
        return False
    if not isinstance(intent, str):
        if name in actions:
            got = (intent.f or {}).get("action")
            if got not in actions[name]:
                return False
        if name in ("settings_bool", "feature_switch", "settings_choice", "control_set"):
            key = (intent.f or {}).get("key")
            if keys and key not in keys:
                return False
    return True


def _example_text(fid: str, status: str, title: str, adjust: list) -> str:
    """What a person says for this row: a typed sentence, a real example for a
    Command-Only ability, or the honest "no phrase" for a safety rule."""
    if status in ("switch", "adjust") and adjust:
        return str(adjust[0].get("phrase") or "")
    phrase = EXAMPLE_PHRASES.get(fid)
    if phrase:
        return phrase
    if _label_from(status, "", fid) == LABEL_ALWAYS_ON:
        return "\u2014 (always on; nothing to say to change it)"
    return "\u2014 (no fixed phrase; ask for it in your own words)"


def _screen_path_text(status: str, reason: str, sections: list) -> str:
    """Where the owner finds it, in app words - and the phone's honest half
    when the change is PC-only."""
    if sections:
        desktop = "desktop Settings: " + ", ".join(sections)
    else:
        desktop = "desktop Settings: All features and abilities"
    if reason == "pc-only":
        return desktop + "; phone: read-only (PC-only setting)"
    if reason == "credentials":
        return desktop + "; phone: points to the PC (security boundary)"
    if reason in ("app-local",):
        return desktop + "; phone: that app's own Settings"
    return desktop + "; phone: All features and abilities"


def _not_a_toggle_text(status: str) -> str:
    if status == "switch":
        return ""
    return ("This is not a toggle: it has no on/off switch. It runs only when "
            "you ask." if status != "not-a-setting"
            else "This is not a toggle: it has no on/off switch.")


def _fields_for(fid: str, sections: list) -> list:
    """The Q3 (control, field) entries this feature can be adjusted through."""
    R = _registry_module()
    if R is None:
        return []
    out = []
    for control, fields in getattr(R, "CONTROL_FIELDS", {}).items():
        for field in fields:
            if field.setting.where in sections:
                out.append({"control": control, "field": field.field,
                            "values": sorted(field.setting.options().keys())})
    return out


def _adjust_ok(intent) -> bool:
    """A proof phrase worked unless it was answered as a known-bad value."""
    name = str(intent or "")
    return bool(name) and not name.endswith("_bad") and name != "settings_choice_bad"


def _registry_module():
    return _registry()


def _quick_intent(phrase: str) -> Optional[str]:
    """The intent a sentence reaches through the REAL matcher, or None.

    Imported lazily: jarvis_quick imports this module lazily in turn, so a
    module-level import would be a cycle. A matcher that is absent (an older
    tree, a suite that did not ship it) is reported as None - never guessed."""
    try:
        import jarvis_quick as Q
        got = Q.match(phrase)
    except Exception:                       # noqa: BLE001
        return None
    return got.name if got is not None else None


#: Ruling (c), 2026-10-31 (Gemini, after the overnight wave): a feature row may
#: carry BOTH its Settings-registry SECTION id ("protection") and its Settings
#: MENU id ("settings.protection"). They are different facts - the section is
#: the surface the row OWNS, the menu id is where it opens - and the row that
#: does this is the list itself, not a stored setting living inside the section.
#: Folding that section into `sections` here would derive status "open-only" and
#: flip the owner's five-label row to Settings-Only, which the owner's decision
#: of 2026-10-22 reserves for accounts and restore-backup. So for the named row
#: the section is NOT folded in: its covers still name both ids, its label stays
#: Command-Only. Kept as an explicit, dated map rather than a heuristic.
SETTINGS_ROW_IDS = {"protected-items": "protection",
                    # 2026-10-31: the same shape for the send-file feature - the
                    # section is the surface its Settings row IS, not a setting inside it.
                    "file-from-pc": "files"}


def _sections_in(row: dict) -> list:
    R = _registry_module()
    if R is None:
        return []
    row_id = str((row or {}).get("id") or "")
    owned_section = SETTINGS_ROW_IDS.get(row_id)
    out = []
    for cover in row.get("covers") or ():
        text = str(cover or "")
        if not text.startswith("settings."):
            continue
        sid = text.split("settings.", 1)[1]
        if sid == owned_section:
            # The row OWNS this section (ruling (c)); it is not a setting in it.
            continue
        if R.section_by_id(sid) is not None and sid not in out:
            out.append(sid)
    return out


def _phrase(text: str) -> dict:
    return {"text": text, "intent": _quick_intent(text)}


_MATRIX_CACHE = None
#: id -> matrix row, built on first use so `_matrix_row()` is a dict lookup
#: rather than a 140-row scan per answer. Reset whenever the cache is rebuilt.
_MATRIX_BY_ID = None
#: True while `_build_matrix` runs. The matrix calls the real matcher, and the
#: matcher can reach back into `label_for` (a "turn on <ability>" phrase becomes
#: `switch_target` -> `ability_explanation` -> `label_for`). Without this guard
#: the first such phrase rebuilt the matrix from inside its own build and the
#: nested ask died on Python's recursion limit - swallowed by `_quick_intent`,
#: so the row silently lost its typed-phrase intent. A nested ask now gets an
#: empty table and the sentence it builds is thrown away; the outer build keeps
#: going and the cached table is complete.
_MATRIX_BUILDING = False


def _matrix() -> list:
    """The cached control_matrix() - one build per process (it calls the real
    matcher ~500 times), so the directory/label helpers stay fast."""
    global _MATRIX_CACHE, _MATRIX_BUILDING, _MATRIX_BY_ID
    if _MATRIX_CACHE is None:
        if _MATRIX_BUILDING:
            return []
        _MATRIX_BUILDING = True
        try:
            _MATRIX_CACHE = _build_matrix()
            _MATRIX_BY_ID = None
        finally:
            _MATRIX_BUILDING = False
    return _MATRIX_CACHE


def control_matrix() -> list:
    """Every feature, its typed controls, and the honest reason for the rest.

    Returns a list in catalogue order. Each row:
      id, name, group, surface, where, covers, sections, switch_keys,
      on_phrase{text,intent}, off_phrase{text,intent},
      how_to_phrase{text,intent}, adjust[{place,phrase,intent,kind}],
      status (switch|adjust|open-only|not-a-setting),
      reason_code, reason, owner.

    `status` is derived: any switch -> "switch"; otherwise any working adjust
    path -> "adjust"; otherwise a real Settings card -> "open-only"; otherwise
    "not-a-setting". `reason_code`/`reason`/`owner` come from
    NO_COMMAND_REASON for every feature that is not switch/adjust. Never
    claims a phrase works: each is run through jarvis_quick.match."""
    return _matrix()


def _build_matrix() -> list:
    R = _registry_module()
    out = []
    for row in features():
        fid = row.get("id") or ""
        title = row.get("title") or fid
        sections = _sections_in(row)
        switches = switches_for(row)
        switch_keys = [s.key for s in switches]
        for key in EXTRA_CONTROLS.get(fid, ()):     # links the covers cannot name
            if key not in switch_keys:
                switch_keys.append(key)
        if fid in ALWAYS_ON_IDS:
            # Lead's 2026-10-22 ruling: an Always-On SAFETY RULE owns no switch.
            # Its exception (e.g. learn_sensitive_topics) belongs to its own
            # setting row, where typed on/off and card gating work as before.
            switch_keys = []
            switches = []
        planned_switchable = fid in PLANNED_SWITCHABLE
        if planned_switchable:
            # A planned row shows no typed phrase at all: the old section
            # sentence (voice speed / asks-first) changed a DIFFERENT feature.
            switch_keys = []
            switches = []
        on_phrase = _phrase(f"turn on {title}")
        off_phrase = _phrase(f"turn off {title}")
        how_to = _phrase(f"how do I turn on {title}")
        adjust = []
        if not planned_switchable:
            places = list(sections)
            for extra_place in EXTRA_ADJUST.get(fid, ()):
                if extra_place not in places:
                    places.append(extra_place)
            for sid in places:
                phrases = ADJUST_SECTIONS.get(sid, ())
                own = FEATURE_ADJUST_PHRASES.get(fid)
                if own and own[0] == sid:
                    phrases = ((own[1], "tier"),)
                for phrase, kind in phrases:
                    intent = _quick_intent(phrase)
                    if _adjust_ok(intent) and _own_words(fid, intent):
                        adjust.append({"place": sid, "phrase": phrase,
                                       "intent": intent, "kind": kind})
        if R is not None:
            for choice in R.CHOICE_SETTINGS:
                if choice.where not in places:
                    continue
                options = choice.options()
                if not options:
                    continue
                # A short id-like value is the least ambiguous proof sentence.
                sample = min(options, key=lambda k: (k != options[k], len(k)))
                phrase = f"set {choice.names[0]} to {sample}"
                intent = _quick_intent(phrase)
                if _adjust_ok(intent) and _own_words(fid, intent):
                    adjust.append({"place": choice.where,
                                   "phrase": phrase,
                                   "intent": intent,
                                   "kind": "choice"})
        if switch_keys:
            status = "switch"
        elif adjust:
            status = "adjust"
        elif sections:
            status = "open-only"
        else:
            status = "not-a-setting"
        if planned_switchable:
            status = "planned"
            owner, reason = PLANNED_SWITCHABLE[fid]
            reason_code = "planned-no-own-control"
        elif status in ("switch", "adjust"):
            reason_code, reason, owner = "command", "", "voiceprint-wiring"
        else:
            got = NO_COMMAND_REASON.get(fid)
            if got:
                reason_code, reason, owner = got
            else:
                reason_code, reason, owner = ("no-command", "", "voiceprint-wiring")
        out.append({
            "id": fid,
            "name": title,
            "group": row.get("group") or "",
            "surface": row.get("surface") or "",
            "where": row.get("where") or "",
            "covers": list(row.get("covers") or ()),
            "sections": sections,
            "switch_keys": switch_keys,
            "on_phrase": on_phrase,
            "off_phrase": off_phrase,
            "how_to_phrase": how_to,
            "adjust": adjust,
            "status": status,
            "reason_code": reason_code,
            "reason": reason,
            "owner": owner,
            # Command-controllable but NOT drawn in Settings today (a gap with
            # its own owner), or None when the typed path has its page control.
            "settings_gap": SETTINGS_GAPS.get(fid),
            # The owner-facing five labels (Q8) and the directory/search fields
            # both apps render (Q2b) - exactly one class per feature.
            "control_class": (LABEL_PC_ONLY if fid in PC_ONLY_FEATURES
                              else (LABEL_SWITCH_ADJUST if planned_switchable
                                    else _label_from(status, reason_code, fid))),
            "control_label": (LABEL_PC_ONLY if fid in PC_ONLY_FEATURES
                              else (LABEL_SWITCH_ADJUST if planned_switchable
                                    else _label_from(status, reason_code, fid))),
            "label": (LABEL_PC_ONLY if fid in PC_ONLY_FEATURES
                      else (LABEL_SWITCH_ADJUST if planned_switchable
                            else _label_from(status, reason_code, fid))),
            "own_keys": sorted(set(list(switch_keys)
                                    + list(OWN_CONTROLS.get(fid, ((), (), {}))[0]))),
            "own_intents": sorted(set(OWN_CONTROLS.get(fid, ((), (), {}))[1])),
            "own_actions": {k: sorted(v) for k, v in OWN_ACTIONS.get(fid, {}).items()},
            "example": _example_text(fid, status, title, adjust),
            "screen_path": _screen_path_text(status, reason_code, sections),
            "is_toggle": status == "switch",
            "not_a_toggle_words": _not_a_toggle_text(status),
            "planned": reason_code == "multi-field" and fid not in SETTINGS_ONLY_IDS,
            "planned_words": ("Typed path planned - adjustable in Settings today, "
                              "typed control not yet proved"
                              if reason_code == "multi-field" and fid not in SETTINGS_ONLY_IDS else ""),
            "has_example": bool((status in ("switch", "adjust") and adjust)
                                or EXAMPLE_PHRASES.get(fid)),
            "fields": _fields_for(fid, sections),
        })
    return out


def matrix_rows_without_reason() -> list:
    """Feature ids that are not command-controllable and have no allowlist row.

    The suite asserts this is empty, so a new feature (or a new gap) fails
    loudly instead of disappearing from the matrix."""
    return [r["id"] for r in control_matrix()
            if r["status"] not in ("switch", "adjust")
            and not NO_COMMAND_REASON.get(r["id"])]





# --------------------------------------------------------------------------
#   The owner-facing five labels + the "Abilities & commands" directory
#   (Gemini rulings Q2 and Q8, 2026-10-22).
# --------------------------------------------------------------------------
#
# The owner's request has two halves: change it by typing AND find it in
# Settings. For a switch or a choice both halves exist. For an ability that is
# a command or an always-on safety rule there is nothing to switch - and the
# honest answer says exactly which kind it is, gives a real example and names
# the Settings place, instead of pretending a toggle exists. These are the
# FIVE plain labels Gemini approved (verbatim), used by the report, the
# Settings directory both apps are building, and the typed refusal.

LABEL_SWITCH_ADJUST = "Switchable / Adjustable (Typed & Settings)"
LABEL_SETTINGS_ONLY = "Settings-Only (By Design — Security Boundary)"
LABEL_PC_ONLY = "PC-Only Setting (Honest Refusal on Phone)"
LABEL_COMMAND_ONLY = "Command-Only (Runs When You Ask — No Switch Needed)"
LABEL_ALWAYS_ON = "Always On (Core Safety Rule — Cannot Be Turned Off)"

CONTROL_LABELS = (LABEL_SWITCH_ADJUST, LABEL_SETTINGS_ONLY, LABEL_PC_ONLY,
                  LABEL_COMMAND_ONLY, LABEL_ALWAYS_ON)

#: Features that do nothing in the background and run only when asked. The
#: EXAMPLE_PHRASES below are REAL sentences the matcher reaches (checked by
#: test_feature_guide.py through jarvis_quick.match); an ability with no safe
#: example says so rather than inventing one.
EXAMPLE_PHRASES = {
    "typing": "what is the weather today",
    "talk-button": "start listening",
    "read-aloud": "read that out loud",
    "interrupt": "stop talking",
    "coming-up": "what is coming up",
    "today": "what is on today",
    "focus": "focus for 25 minutes",
    "history-search": "what did i say about the garden",
    "temporary-chat": "start an incognito chat",
    "memory-known": "what do you remember about me",
    "memory-saved": "what have you learned about me",
    "memory-as-of": "what did i believe on this date",
    "forget-range": "forget what you learned last week",
    "wiki": "build my wiki",
    "document": "ask about a pdf",
    "documents": "ask about a pdf",
    "quiz": "quiz me on a text",
    "decks": "my study decks",
    "notes-write": "write a note for me",
    "pc-help": "why is my pc slow",
    "projects": "my projects",
    "goals": "my goals",
    "progress": "my progress",
    "spending": "how much did i spend",
    "retirement": "run a retirement what-if",
    "calendar": "what is on my calendar",
    "email-read": "read my email",
    "email-send": "send an email",
    "inbox-tidy": "tidy my inbox",
    "weather-sky": "what is the weather",
    "home-status": "how is the house",
    "lights": "turn on the light",
    "find-phone": "ring my phone",
    "undo": "undo that",
    "stop-everything": "stop everything",
    "approvals": "show me the approval cards",
    "what-asks-first": "what asks first",
}

#: The approved Always On safety list (Gemini Q8, Lead's 2026-10-22 wording):
#: these are the rules the app may never turn off. The label wins over the
#: feature's own typed control (e.g. "approvals" also has a card-display
#: choice) because the SAFETY half is what the owner is being told about.
ALWAYS_ON_IDS = {
    "approvals", "app-lock", "trust", "rush-latch", "outside-text",
    "stale-link", "stop-everything", "crisis-help", "sensitive-facts",
    "memory-waiting", "settings-entry", "devices",
}

#: Exactly TWO rows get the Settings-Only (Security Boundary) label, per the
#: Lead's ruling: Accounts/credentials and Restore backup (the backup row).
#: Pairing/device keys are NOT a "security boundary" for this purpose - they
#: are PC-Only rows below.
SETTINGS_ONLY_IDS = {"accounts", "backup"}

#: An Always-On rule may have a RELATIVE setting elsewhere (the exception that
#: is allowed). The deterministic answer names it, but the safety rule itself
#: owns no switch (Lead's 2026-10-22 sensitive-facts ruling).
ALWAYS_ON_EXCEPTION = {
    "sensitive-facts": (
        "The setting that lets sensitive topics be remembered automatically "
        "is its own switch: say \"turn on also remember sensitive topics "
        "automatically\" and it asks for your card; the safety rule itself "
        "stays on."),
}

#: The Always-On rows whose rule is ALSO a real switch with an OFF path. Only
#: `app-lock` qualifies, and it is why the blanket "cannot be turned off" was
#: false (2026-10-26 semantic read, finding 2): the PC's Settings has a real
#: App lock checkbox (`jarvis-desktop/src/settings.html:1517`,
#: `<input id="sec-app-lock" type="checkbox">`), whose change goes through
#: `set_security_settings` (`jarvis-desktop/src-tauri/src/lock.rs:1089`).
#: Turning a lock OFF is a loosening, so it asks Windows Hello first
#: (`lock.rs:1104-1107`; `jarvis-desktop/src/security-settings.js:76-79`,
#: `(prev.appLock && !next.appLock)`), and both apps have that switch, OFF by
#: default (`docs/ARCHITECTURE.md:2189`). What never turns off is the rule under
#: it: a risky action is never approved without Windows Hello, lock or no lock
#: (`lock/rules.rs:41-48`, the owner's 2026-09-25 decision).
ALWAYS_ON_OFF_PATH = {
    "app-lock": (
        "The rule underneath is what stays on: a risky action is never approved "
        "without Windows Hello, lock or no lock. App lock itself is a real "
        "switch in Settings, Security - turning it on is instant, and turning "
        "it off asks for Windows Hello first."),
}

#: The Status line for those rows. DISPLAY ONLY, the same shape as
#: `PHONE_ONLY_DISPLAY_LABEL` below: `label_for()` keeps the owner-approved
#: five-label mix and its pinned counts (40/2/16/70/12,
#: `tools/check_feature_controls.py:425-433`), but this row's Status line must
#: not read out "Cannot Be Turned Off" for a control that can.
ALWAYS_ON_DISPLAY = {
    "app-lock": "Always On (Core Safety Rule — Off Only With Windows Hello)",
}

#: Rows BOTH apps have whose control the phone really does use itself. The
#: blanket `both_pc_change_words()` sentence says the phone "cannot change the
#: PC's setting", which is false for these three.
#:
#: Two of them write a SHARED appearance document (2026-10-26 semantic read,
#: finding 3): the phone's Appearance screen picks a face and pushes it -
#: `appearance.setFace()` then `JarvisRuntime.pushAppearance()`
#: (`jarvis-client/.../MainActivity.kt:3233-3236`), the document carries `face`
#: (`.../data/AppearanceStore.kt:424-429`), and the desktop adopts it
#: (`jarvis-desktop/src-tauri/src/appearance.rs:76`, `:166-177`). The theme is
#: deliberately NOT in that document (`AppearanceStore.kt:417-422`), so each row
#: says which half travels.
#:
#: The third is `phone-floating`, which joined on 2026-10-29 (the settings
#: wrong-app audit, finding 6) when its row became `surface: both`: the PC's
#: half is the "Floating face" toggle inside Appearance and the phone's is its
#: own Floating Jarvis card, each saved on its own device. It is not a shared
#: document, so its sentence says so rather than borrowing the two above.
#: Each string is the sentence after "Its setting is in <place>. "
BOTH_PHONE_WRITES = {
    "faces": ("On the phone, Appearance picks the same face and sends it to the "
              "PC, so either app can change it."),
    "appearance": ("On the phone, Appearance changes the same face and state "
                   "colours and sends them to the PC; the theme itself stays on "
                   "each device."),
    "phone-floating": ("On the phone, Settings, Floating Jarvis turns that phone's "
                       "own bubble on or off; the PC keeps its own floating face, "
                       "in Appearance."),
}

#: One-switch Switchable rows: does loosening the switch ask on a card?
#: `change_words()` used to append "A change that loosens a rule still asks on a
#: card first." to EVERY single-switch row, and it was false on four of them
#: (2026-10-26 semantic read, finding 5). The sentence is data now: it appears
#: only for a switch listed in CARD_ON_LOOSENING, and the suite fails on a
#: single-switch row whose key is in NEITHER set, so a new switch cannot
#: silently inherit the promise. Each entry quotes the switch's own rule and the
#: line it was read from.
CARD_ON_LOOSENING = frozenset({
    # "either setting on raises an approval card; turning it off is immediate"
    "background_learning",   # jarvis_auto_learn.py:16, :260-264
    # 2026-11-02: ON is one card (learning_paraphrase_enable), OFF is
    # immediate - the same shape exactly.
    "learn_paraphrase",      # jarvis_auto_learn.py PARAPHRASE_ACTION
    "briefing_senders",      # "ON through ONE approval card" jarvis_briefing.py:2116
    "chat_history",          # "OFF at once, ON is its own card" registry:967
    "media_index",           # "ON is ONE normal approval card" registry:721-725
    "headless_browser",      # BE.request(...) registry:688-694
    "screen_picture",        # SP.request(...) registry:662-668
    "lights_without_card",   # request_lights(...) registry:605-611
    "sandbox_exec",          # "ON is ONE normal approval card" registry:700-705
})
#: ...and the five whose setter says it never asks. `humour` is the row the
#: semantic read caught: `set_humor` - "At once either way - it changes wording
#: only." (registry:910-912).
CARD_FREE_SWITCHES = frozenset({
    "prompt_coach",   # "Neither direction asks" registry:566-568
    "humor",          # "At once either way" registry:910-912
    "write_like_me",  # "No card either way" registry:976-979
    "pictures",       # "BOTH directions ... neither asks" registry:736-738
    "antislop",       # "No card either way - it changes only how an answer is
                      # worded" (the Anti-Slop filter's own setter, 2026-10-28)
    # The Jarvis calendar's switch hides or shows the owner's own events and
    # keeps every one of them: no card either way (2026-10-29).
    "jarvis_calendar",
})

#: The Settings place the owner is sent to for an ability with no switch. The
#: directory itself is the guaranteed path (both apps build it, ruling Q2b -
#: the desktop since #748 and the phone since #749); a feature with a real
#: Settings card names that card instead. No " (planned)" marker: both halves
#: exist now, and a live path that still said planned would name a screen the
#: owner can open.
SETTINGS_DIRECTORY = "Settings, All features and abilities"


def _section_words(row: dict) -> str:
    R = _registry_module()
    names = []
    if R is not None:
        for sid in _sections_in(row):
            section = R.section_by_id(sid)
            if section is not None and section.names:
                names.append(str(section.names[0]))
    return ", ".join(names)


#: A Settings place is a SHORT NAME ("Connection", "A new conversation starts
#: after"), never a sentence. These are the limits a path is held to when it is
#: read out of a row's own `where` prose: the owner's list writes the setting
#: place as `Settings, <Place>` and then carries on with a full stop, a dash or
#: a second clause, and reading the whole of that as a place is what glued a
#: fragment to "on this PC" (2026-10-26, part B: "It is changed at Settings, a
#: new conversation starts after on this PC").
_MAX_PLACE_WORDS = 6
#: A place never opens like a clause of prose. Deliberately checked on the
#: FIRST word only, and only for a place read out of `where` - the registry's
#: own names ("the big model") are trusted as written.
_PROSE_OPENERS = ("the", "a", "an", "it", "this", "that", "then", "and", "or",
                  "when", "where", "what", "how", "if", "so")


def _path_shaped(place: str, *, section: str = "") -> bool:
    """Is this a Settings place, or a piece of prose that happens to follow a comma?

    The guard exists because `where` is written for a person to read, not to be
    split: "Settings, Appearance, then Open Faces on the PC." must yield
    "Appearance", and "Settings, the first card on the page." must yield nothing
    (it names a position, not a place) so the answer falls back to the directory
    instead of inventing a path.

    `section` is the registry's own name for the card the row covers. A place
    that IS that card is a real place whatever its first word - "Settings, How
    Jarvis talks." opens with a prose opener but names the card, and refusing it
    is what left `manner` reading its lowercase spoken alias instead (2026-10-26
    semantic read, finding 8).
    """
    place = " ".join(str(place or "").split())
    if not place:
        return False
    if section and _norm(place) == _norm(section):
        return True
    words = place.split()
    if len(words) > _MAX_PLACE_WORDS:
        return False
    if any(ch in place for ch in '.;:!?,"()'):
        return False
    if words[0].lower().strip("'") in _PROSE_OPENERS:
        return False
    return True


def _where_place(row: dict, *, section: str = "") -> str:
    """The `<Place>` of the row's own opening "Settings, <Place>", or "".

    Only the OPENING path is read, and only up to its own full stop, dash or
    second comma - never the rest of the sentence. `_path_shaped` then decides
    whether that really was a place.
    """
    where = " ".join(str(row.get("where") or "").split())
    if not where.lower().startswith("settings,"):
        return ""
    rest = where[len("settings,"):].strip()
    head = rest.split(".", 1)[0]
    head = head.split(" - ", 1)[0]
    head = head.split(",", 1)[0].strip()
    return head if _path_shaped(head, section=section) else ""


#: Words that are NAMES rather than ordinary nouns when a Settings place is
#: written out. The registry keeps them lowercase because there they are MATCHING
#: aliases ("how jarvis talks", `backend/jarvis_settings_registry.py:252`), while
#: the card they open is capitalised (`jarvis-desktop/src/settings.html:1020`,
#: "How Jarvis talks") and the row's own `where` prints it that way. Written out
#: as a place, "Settings: Settings, how jarvis talks." therefore disagreed with
#: the "Where: Settings, How Jarvis talks." line directly under it (2026-10-26
#: semantic read, finding 8: 107 of 405 answer heads).
_PLACE_NAMES = {"jarvis": "Jarvis", "hud": "HUD", "api": "API"}


def _place_display(name: str) -> str:
    """A Settings place as the card writes it: names capitalised, sentence first letter.

    DISPLAY ONLY. `_norm()` matching still sees the registry's own lowercase text
    (`_section_words()` and `find()` are untouched), and no section id or alias
    changes - only the words an answer prints.
    """
    shown = []
    for word in " ".join(str(name or "").split()).split(" "):
        stem, apostrophe, tail = word.partition("'")
        shown.append(_PLACE_NAMES.get(stem.lower(), stem) + apostrophe + tail)
    text = " ".join(shown)
    return text[:1].upper() + text[1:] if text[:1].islower() else text


def settings_path_words(row: dict) -> str:
    """The EXACT place the owner finds this feature, in Settings words.

    The registry's section names come FIRST: they are the Settings cards this
    repository already knows how to open. When the row's own `where` names that
    SAME card, its words are used instead, because `where` is the sentence the
    Settings page itself shows ("Settings, How Jarvis talks.") and the two lines
    of one answer must not disagree about capitalisation (2026-10-26 semantic
    read, finding 8). A section name with no such place is written out by
    `_place_display()`. When a row covers no card, its own `where` may still open
    with a path - "Settings, Appearance, then Open Faces on the PC." - and that
    place is used only if it passes `_path_shaped`. What is never used is the
    prose after the first comma unexamined; when no path survives, the answer
    gives the directory, which every feature really is listed at.
    """
    sections = _section_words(row)
    if sections:
        place = _where_place(row, section=sections)
        if place and _norm(place) == _norm(sections):
            return f"Settings, {_place_display(place)}"
        return f"Settings, {_place_display(sections)}"
    place = _where_place(row)
    if place:
        return f"Settings, {_place_display(place)}"
    return SETTINGS_DIRECTORY


def _label_from(status: str, reason: str, fid: str) -> str:
    """The five-label mapping (Lead's 2026-10-22 classification rules):
    Settings-Only exactly Accounts + Restore backup; the approved safety list
    is Always On; real switch/choice/multi-field rows are Switchable/
    Adjustable (a multi-field typed path still pending is `planned`, not a
    fake control); PC-only + app-local are PC-Only; everything else (remaining
    abilities and read-only pages) is Command-Only."""
    if fid in SETTINGS_ONLY_IDS:
        return LABEL_SETTINGS_ONLY
    if fid in ALWAYS_ON_IDS:
        return LABEL_ALWAYS_ON
    # Owner-approved 2026-10-23 (ADJ-Q1): three one-app controls are PC-Only
    # even though their typed control exists, and three genuinely-adjustable
    # features have no own typed control yet (planned, still Switchable).
    if fid in PC_ONLY_FEATURES:
        return LABEL_PC_ONLY
    if fid in PLANNED_SWITCHABLE:
        return LABEL_SWITCH_ADJUST
    if status in ("switch", "adjust") or reason == "multi-field":
        return LABEL_SWITCH_ADJUST
    if reason in ("pc-only", "app-local", "credentials"):
        return LABEL_PC_ONLY
    return LABEL_COMMAND_ONLY


def label_for(row: dict) -> str:
    """One of the five owner-facing labels (Gemini Q8), from the real row."""
    fid = str((row or {}).get("id") or "")
    mine = next((r for r in _matrix() if r["id"] == fid), {})
    return _label_from(mine.get("status", ""), mine.get("reason_code", ""), fid)


def example_phrase_words(row: dict) -> str:
    """A real example sentence to use the ability, or an honest "none needed".

    Only phrases pinned by a test are returned; anything else says the ability
    has no fixed sentence rather than inventing one."""
    fid = str(row.get("id") or "")
    phrase = EXAMPLE_PHRASES.get(fid)
    if phrase:
        return f'Say, for example: "{phrase}"'
    return ("There is no fixed sentence for it: ask for it in your own words "
            "when you want it.")


def ability_explanation(row: dict) -> str:
    """The deterministic answer when the owner types turn on/off an ability.

    NO MODEL, no guess and no pretence of a switch: says which of the five
    kinds it is, why, a real example where one exists, and the exact Settings
    place. Used by jarvis_quick's turn-on/off path through switch_target()."""
    label = label_for(row)
    title = str(row.get("title") or row.get("id") or "That")
    path = settings_path_words(row)
    # Same rule as change_words(): a phone-only row is changed on the phone, and
    # the PC-Only label must never put its control "on this PC" (F3, 2026-10-26);
    # a row BOTH apps have says the setting is the PC's, never that the phone
    # lacks the feature (part B, 2026-10-26).
    if (str(row.get("surface") or "") == "phone"
            and label in (LABEL_PC_ONLY, LABEL_SETTINGS_ONLY)):
        return (f"{title} is on the phone only: it is changed in "
                f"{_phone_settings_words(row)} {_phone_pc_claim(row)}")
    if str(row.get("surface") or "") == "both" and label == LABEL_PC_ONLY:
        return f"{title} is a PC-Only Setting. {both_pc_change_words(row)}"
    if label == LABEL_ALWAYS_ON:
        why = str(row.get("what") or row.get("asks") or "").strip()
        fid = str(row.get("id") or "")
        off_path = ALWAYS_ON_OFF_PATH.get(fid)
        extra = ALWAYS_ON_EXCEPTION.get(fid)
        if off_path:
            return (f"{title} is Always On (Core Safety Rule). {why} {off_path} "
                    f"It is inspected at {path}.")
        return (f"{title} is Always On (Core Safety Rule) and cannot be turned "
                f"off. {why} It is inspected at {path}."
                + (f" {extra}" if extra else ""))
    if label == LABEL_PC_ONLY:
        return (f"{title} is a PC-Only Setting: it is changed at {path} on this "
                f"PC, and the phone says so rather than pretending it changed. "
                f"{str(row.get('where') or '').strip()}")
    if label == LABEL_SETTINGS_ONLY:
        return (f"{title} is Settings-Only by your decision and is never typed "
                f"or spoken. Open {path} on the PC.")
    # A planned row must not be given the Command-Only sentence (2026-11-13):
    # its typed path is not wired yet, but its Settings control may well ship -
    # read-aloud's does - and "nothing to turn on or off" would contradict the
    # row's own `where`. Say the planned truth and name that place instead.
    if str((_matrix_row(row) or {}).get("status") or "") == "planned":
        where = str(row.get("where") or "").strip()
        return (f"{title} is not wired yet: {_planned_reason(row)}"
                + (f" Where: {where}" if where else ""))
    # A Switchable/Adjustable row whose only proof is a typed ADJUST phrase has
    # a real control, but no boolean switch `switch_target` could name - the
    # wake word, attention budget, topics, the captcha hand-off and eleven more.
    # The Command-Only sentence was false for every one of them (2026-11-13);
    # name the phrase that really works and the place it lives instead.
    mine = _matrix_row(row) or {}
    if str(mine.get("status") or "") == "adjust" and (mine.get("adjust") or ()):
        phrase = str((mine["adjust"][0] or {}).get("phrase") or "").strip()
        where = str(row.get("where") or "").strip()
        said = f"{title} is Switchable/Adjustable."
        if phrase:
            said += f' To change it, say "{phrase}".'
        if where:
            said += f" Where: {where}"
            if not said.endswith("."):
                said += "."
        return said
    why = str(row.get("what") or "").strip()
    example = example_phrase_words(row).rstrip(".")
    return (f"{title} is a Command-Only ability (runs when you ask, no switch "
            f"needed). {why} {example}. It is listed at {path}.")


def ability_row(row: dict) -> dict:
    """One row of the owner-facing directory (both apps render this data)."""
    matrix = {r["id"]: r for r in control_matrix()}
    mine = matrix.get(str(row.get("id") or "")) or {}
    return {
        "id": row.get("id"),
        "name": row.get("title"),
        "group": row.get("group"),
        "surface": row.get("surface"),
        "label": label_for(row),
        "why": str(row.get("what") or "").strip(),
        "example_phrase": EXAMPLE_PHRASES.get(str(row.get("id") or "")),
        "example_words": example_phrase_words(row),
        "settings_path": settings_path_words(row),
        "typed_controls": mine.get("adjust") or [],
        "switch_keys": mine.get("switch_keys") or [],
        "reason_code": mine.get("reason_code") or "",
        "settings_gap": mine.get("settings_gap"),
        "planned": bool(mine.get("planned")),
        "planned_words": mine.get("planned_words") or "",
        "has_example": bool(mine.get("has_example")),
    }


def abilities_directory() -> list:
    """All 140 features with the five plain labels - the data both apps'
    "All features & abilities" Settings directory and search are built from
    (Gemini Q2b/Q8; the UI itself is setup-ui's and Session B's)."""
    return [ability_row(row) for row in features()]

# ---------------------------------------------------------------------------
#   THE SELF-KNOWLEDGE TABLE (2026-11-07, the feature self-awareness audit)
# ---------------------------------------------------------------------------
# The live audit of 2026-11-07 measured the model falsely DENYING capabilities
# this PC really has - the Muse failure mode the competitor audit warns about
# ("it described its own access wrongly"). Four families were the worst:
# approval policy, watches/CI, spending limits and chat history. Each is a
# READ-ONLY fixed sentence built from the shipped record, so the fixed phrases
# can answer without a model, and the `self_portrait` digest can hand the model
# the same bounded fact instead of letting it guess. No state is read here and
# nothing is changed: `where`/`limit` are the project's own words.
#
# WHY A TABLE AND NOT A CATALOGUE ROW: the 179 catalogue rows are generated
# from features/features.json and their count is pinned by several checkers.
# These four facts are about how Jarvis talks about itself, not new features,
# so they live here and are held by `backend/test_self_answers.py`.
SELF_FACT_IDS = ("approval_policy", "watches_ci", "spending_limits", "chat_history",
                 "github_connect", "model_benchmarks",
                 # The owner's 2026-11-09 report: Jarvis denied web browsing while
                 # web search was ON, and answered "I cannot create a repository"
                 # to "create a repository called Fitness Band". Four different
                 # things reach the internet, and the model conflated them.
                 "internet_access")

SELF_FACTS = {
    "approval_policy": {
        "family": "approval_policy",
        "digest": ("You can change what needs an approval card by asking. Three parts, "
                   "one action and one part at a time: whether it raises a card, whether "
                   "it needs a second yes, and whether a yes must pass Windows Hello. More "
                   "asking is instant; less asking raises one PC-only card needing Windows "
                   "Hello. No bulk form."),
        "sentence": ("Yes. You can change what needs an approval card by talking to me. "
                     "It has three separate parts and changes one action and one part at a "
                     "time: whether an action raises a card at all (its tier), whether it "
                     "needs a second yes, and whether a yes must also pass Windows Hello on "
                     "this PC. More asking - a card where there was none, a second yes, "
                     "Windows Hello - happens at once with no card, like turning a switch "
                     "off. Less asking raises ONE card on the PC that needs Windows Hello "
                     "to approve, and it is refused from any other device; nothing is "
                     "written until you approve it. There is no bulk form: a sentence that "
                     "names two parts is refused before anything is read or raised. "
                     "Where: Settings, What asks first, on the PC - that page is read-only, "
                     "and the change itself is by asking. Say for example "
                     "\"make editing notes ask me first\" or \"let saving facts happen "
                     "without a card\"."),
    },
    "watches_ci": {
        "family": "watches_ci",
        "digest": ("Yes: a \"tell me when\" watch can watch a page for changes, and the "
                   "CI watcher watches GitHub Actions runs. Both are set up by asking and "
                   "list what they saw on the PC."),
        "sentence": ("Yes. I can watch a web page for you and tell you when it changes - "
                     "that is the \"tell me when\" watch, and its list is on the PC's Brain, "
                     "Watch tab. I can also watch a GitHub Actions run and tell you when it "
                     "fails: say which repository, branch or pull request to follow, and the "
                     "CI watcher keeps checking it on this PC. A watch that reads outside "
                     "text is checked first, and a watch never acts by itself. Say, for "
                     "example, \"tell me when this page changes: <address>\" or \"tell me "
                     "when the CI fails on main\"."),
    },
    "spending_limits": {
        "family": "spending_limits",
        "digest": ("Yes: spending limits exist - a per-service money cap with a monthly "
                   "limit and spending profiles; a cloud request that cannot be paid for "
                   "is simply not sent, and a card that can spend money is capped too. It "
                   "is set in Settings, Spending, on the PC."),
        "sentence": ("Yes, spending limits are a feature I have. The cloud service's own "
                     "money cap is kept on this PC, per service, with a monthly limit: a "
                     "cloud request that cannot be paid for within it is never sent, and I "
                     "say so instead. The same rule bounds a card that could spend money, "
                     "and spending profiles record what you allow. Where: Settings, "
                     "Spending, on the PC - changing a limit asks on the PC with its own "
                     "approval, never silently. Say \"what are my spending limits?\" for "
                     "the current numbers, never a guess."),
    },
    "chat_history": {
        "family": "chat_history",
        "digest": ("Yes: chat history is kept on this PC by default, encrypted, with a "
                   "switch to turn it off and a retention length. It is in Settings, "
                   "Security; turning history OFF is instant."),
        "sentence": ("Yes. Chat history is kept on this PC by default - encrypted, on this "
                     "machine, with no cloud copy - and both apps list it. There is a "
                     "switch to turn it off (turning it off is instant), a number setting "
                     "for how long it is kept, and Forget a time frame for deleting a "
                     "range. Where: Settings, Security, on the PC, and the phone's History "
                     "and Privacy screens. Turning history back on asks on a card first."),
    },
    # THE OWNER'S 2026-11-08 REPORT, added 2026-11-08. He saved a GitHub token on
    # the connect card (the host ran ONE real test: `GET /user`), typed "i added a
    # token", and the CODING-preset model answered "I've tested the token and it
    # works. I can now access your GitHub repositories and perform actions like
    # cloning, pushing, and pulling code" - then contradicted itself. This family
    # is the bounded self-digest the model's `self_portrait` tool result carries,
    # so a model turn that is asked about the token has the real surface and the
    # real never-list instead of an invented one. `jarvis_quick.py` answers the
    # same words deterministically from the saved test receipt, before any model.
    "github_connect": {
        "family": "github_connect",
        "digest": ("A GitHub token saved through the connect card is tested ONCE with "
                   "one GitHub request; that one test proves the token identifies your "
                   "GitHub account and nothing more. A saved token lets Jarvis search "
                   "GitHub, see private repositories and watch CI. With the GitHub tools "
                   "switched on - TEN of them, all off by default - it can also read your "
                   "repositories, pull requests, issues, CI status, one file and the PR "
                   "cockpit (whether each open pull request can merge, with its 40-hex "
                   "head commit); comment; open an issue; re-run a workflow; create one "
                   "new empty repository on your own account; merge ONE pull request with "
                   "a merge commit pinned to the exact 40-hex head commit on its own card; "
                   "and fix-and-push - copy a failing pull request into an isolated "
                   "scratch folder on this PC, then push commits a person made there to "
                   "that pull request's own branch, two stages and two cards. Every one "
                   "of those six writes asks on its own approval card and is in "
                   "jarvis_agent.NEEDS_A_PERSON. The four reads ship asking too, and "
                   "since 2026-11-10 the owner can make GitHub reads card-free from "
                   "Settings, What asks first - turning the card back on is instant. "
                   "It never force-pushes, squash-merges, "
                   "rebases, uses an admin bypass or auto-merge, bypasses required checks, "
                   "pushes directly to main, deletes or closes a repository or branch, "
                   "approves a pull request, dispatches a workflow or touches gists, and "
                   "it has no tool that edits or commits code."),
        "sentence": ("A GitHub token saved on the connect card is tested once with one "
                     "GitHub request - that proves the token identifies your GitHub "
                     "account, nothing more. It lets me search GitHub, see private "
                     "repositories and watch CI. With the GitHub tools switched on - ten "
                     "of them, all off by default - I can also read your repositories, "
                     "pull requests, issues, CI status, one file and the pull request "
                     "cockpit (whether each open pull request can merge, with its head "
                     "commit), comment, open an issue, re-run a workflow, create one new "
                     "empty repository on your own account, merge ONE pull request with a "
                     "merge commit pinned to the exact head commit on its approval card, "
                     "and fix-and-push: copy a failing pull request into an isolated folder "
                     "on this PC, then push commits a person made there to that pull "
                     "request's own branch - two stages and two cards, with the token sent "
                     "to api.github.com and nowhere else. I never force-push, squash-merge, "
                     "rebase, use an admin bypass or auto-merge, bypass required checks, "
                     "push directly to main, delete or close a repository or branch, "
                     "approve a pull request, dispatch a workflow or touch gists, and I "
                     "have no tool that edits or commits code."),
        # The capability half alone, for the deterministic chat answer after a
        # connect-card save: short, and the same words as `sentence`'s second
        # half. One source of truth for both.
        # NO "cloning / pushing / pulling" in this chat-facing half (GH-5): the
        # overclaim words an owner reads as "so you can do that". Since
        # 2026-11-10 the honest answer also names the two carded writes that ARE
        # built - the merge and the fix-and-push - because a sentence saying
        # "there is no merge card" became false when that card shipped.
        "short": ("It lets me search GitHub, see private repositories and watch CI; with "
                  "the GitHub tools switched on - ten of them, all off by default - it "
                  "can also read your repositories, pull requests, issues, CI status, one "
                  "file and the pull request cockpit (whether each open pull request can "
                  "merge, with its head commit), comment, open an issue, re-run a "
                  "workflow, create one new empty repository on your own account, merge "
                  "ONE pull request with one merge commit pinned to the exact head commit "
                  "on its own approval card, and fix-and-push: copy a failing pull "
                  "request into an isolated folder on this PC, then push commits a person "
                  "made there to that pull request's own branch - two stages and two "
                  "cards. The four reads ship asking too, and the owner can make "
                  "GitHub reads card-free from Settings, What asks first. It never "
                  "force-pushes, squash-merges, rebases, uses an admin "
                  "bypass or auto-merge, bypasses required checks, pushes to main, "
                  "deletes or closes a repository or branch, approves a pull request, "
                  "dispatches a workflow or touches gists, and there is no tool that "
                  "edits or commits code."),
        # The same never-list, said as the answer to "can you clone/push/pull?".
        # Kept here so the fixed answer, the model's digest and the chat receipt
        # answer cannot drift apart.
        "never": ("No - I never copy a repository to this PC, and I have no tool that "
                  "edits or commits code. What a saved token does let me do: search "
                  "GitHub, see private repositories and watch CI; and with the GitHub "
                  "tools switched on, read your repositories, pull requests, issues, CI "
                  "status, one file and the pull request cockpit (whether each open pull "
                  "request can merge, with its head commit), comment, open an issue, "
                  "re-run a workflow and create one new empty repository on your own "
                  "account - each on its own approval card; and, on its own cards, merge "
                  "ONE pull request with one merge commit pinned to the exact 40-hex head "
                  "commit its card shows, and fix-and-push: copy a failing pull request "
                  "into an isolated folder on this PC, then push commits a person made "
                  "there to that pull request's own branch - two stages and two cards. "
                  "It never force-pushes, squash-merges, rebases, uses an admin bypass or "
                  "auto-merge, bypasses required checks, pushes to main, deletes or "
                  "closes a repository or branch, approves a pull request, dispatches a "
                  "workflow or touches gists."),
    },
    # THE OWNER'S 2026-11-08 ASK: "talk about the local AI models - what has
    # been measured, start Benchmarks, what a better models for the current
    # Presets, what are the current models for the current Presets". This digest
    # is what the model's `self_portrait` tool result carries, so a model turn
    # cannot contradict the deterministic answers or invent a measurement.
    "model_benchmarks": {
        "family": "model_benchmarks",
        "digest": ("You can ask about the local models, all answered on this PC: "
                   "what has been measured (speed runs and the five suite "
                   "scorecards, with the date), which model each preset uses, "
                   "whether a candidate is MEASURED ON THIS PC or only an "
                   "ESTIMATED FIT (run benchmark to verify), and what model ran "
                   "before from the change journal. A benchmark is started by "
                   "asking and uses a throwaway model server on a spare port, "
                   "never a live lane's own server directly; it may pause the lane "
                   "it needs and puts the active preset back. No number may be "
                   "invented, and a model is never called better until a benchmark "
                   "measured it for that preset."),
        "sentence": ("Yes. You can talk to me about the local models and I answer "
                     "from this PC's own records, never the model's memory. Ask "
                     "\"what has been measured?\" and I read the newest speed runs "
                     "and the five suite scorecards - speed, coding, general, "
                     "tool-calling and vision - with their dates. Ask \"what models "
                     "do the current presets use?\" and I list each preset's model, "
                     "card and context window. Ask \"what is a better model for the "
                     "coding preset?\" and I give the current model plus the "
                     "hardware-aware list's candidates, each labelled MEASURED ON "
                     "THIS PC or ESTIMATED FIT (run benchmark to verify) - a "
                     "candidate is never called better until a benchmark measured "
                     "it for that preset. To start one, say \"start a benchmark\" "
                     "(the current model's speed) or \"start the benchmark suites\" "
                     "(all five), or name one like \"benchmark the coding model\": "
                     "it uses a throwaway model server on a spare port, never your "
                     "live lane's own server directly, may pause the lane it needs "
                     "and puts your active preset back afterwards, refuses while I "
                     "am answering a turn, and only one runs at a time. The results "
                     "are kept in Brain, Model, Models. Ask \"what did you use "
                     "before?\" and I read the change journal - with nothing "
                     "recorded I say so instead of guessing."),
    },
    # THE OWNER'S 2026-11-09 REPORT, added 2026-11-09. He asked why Jarvis denied
    # web browsing while `web_search` was ON, and asked it to create a repository
    # called "Fitness Band". Both were factual self-description faults: FOUR
    # different things leave this PC for the internet, each with its own switch
    # and its own card, and the model answered as if "the web" were one thing.
    # `jarvis_quick.py` answers the same question deterministically from
    # `jarvis_reach.view()` and the GitHub modules, so the words here are the
    # bounded digest the model's own `self_portrait` carries - one source, two
    # readers. Read-only: no state is read here.
    "internet_access": {
        "family": "internet_access",
        "digest": ("Four SEPARATE things reach the internet, and one being on never "
                   "turns another on: (a) web search - the search words go to a search "
                   "engine and titles/snippets come back, switched in Settings, Web "
                   "search and by the web_search tool row; (b) reading one web page - "
                   "its own tool that fetches the ONE address on its card and nothing "
                   "else; (c) browser control - a real browser tab being clicked and "
                   "typed in, which needs its own switch and the second card's browser "
                   "lane or the windowless browser; (d) the GitHub integration - a saved "
                   "token plus its own tools, each use on its own card. A refusal must "
                   "name WHICH of the four is off and what turns it on; never say 'I "
                   "cannot browse the web' when web search is on, and never say a "
                   "switch is on without reading it."),
        "sentence": ("Four separate things reach the internet, and turning on one never "
                     "turns on another. Web search sends your search words to a search "
                     "engine and brings back titles and snippets - it is switched in "
                     "Settings, Web search, and by the web_search row on Settings, What "
                     "asks first. Reading one web page is a different tool: it fetches "
                     "the one address shown on its card, once, and never a link on the "
                     "page. Browser control is different again: it works a real page by "
                     "clicking and typing in one tab, and it needs its own switch in "
                     "Settings, What asks first, plus the second graphics card's browser "
                     "lane or the windowless browser. The GitHub integration is separate "
                     "from all three: it needs a token saved through the connect card and "
                     "its own tools switched on, and every GitHub use raises its own card. "
                     "So \"I cannot browse the web\" is never the whole true answer - the "
                     "honest answer names which of the four is off and what turns it on."),
    },
}


def self_fact(family: str):
    """One bounded self-fact by family id, a copy, or None - never a guess."""
    row = SELF_FACTS.get(str(family or ""))
    return dict(row) if row else None


def self_fact_words(family: str) -> str:
    """The owner-facing sentence for one family, or "" for an unknown id."""
    row = self_fact(family)
    return str(row.get("sentence") or "") if row else ""


#: WHERE a function lives when it has no Settings card of its own (F14,
#: 2026-11-07). The live audit measured "where do I change X?" reaching the
#: model for these, and the model sent the owner to places that do not exist
#: ("Settings, under Shortcuts" for the face size). Each entry is the real
#: place in the project's own words; `words` is the answer, `key` the phrase
#: the chat matcher accepts.
PLACES = {
    "standby hours": {
        "key": "standby hours",
        "words": ("Standby hours are a schedule on this PC's own scheduler, not a Settings "
                  "switch: the Brain's Power card holds the hours, and a change raises one "
                  "change-own-config approval card. Say for example \"standby from 1am to "
                  "7am\" in chat, or open the Power card in the Brain."),
    },
    "attention budget": {
        "key": "attention budget",
        "words": ("The interruption (attention) budget lives in the Brain, on the Now "
                  "page's Attention budget block. It says how many times a day I may speak "
                  "up first, and a change is made there on the PC."),
    },
    "spending": {
        "key": "spending limits",
        "words": ("Spending limits are in Settings, Spending, on the PC. They are kept on "
                  "this machine, and changing a limit asks on the PC with its own approval. "
                  "The phone has a spending screen too."),
    },
    "notification styles": {
        "key": "notification styles",
        "words": ("Notification styles are the phone's own: Settings, Appearance, "
                  "notification styles, on the Android app. The PC has no card for them - "
                  "Windows draws its own toast - and the chat preview works on both."),
    },
    "face size": {
        "key": "face size",
        "words": ("The face size is a HUD look on this PC, not a setting the PC owns: open "
                  "the faces panel from the HUD's left rail and choose Small, Medium or "
                  "Large. It is kept for this device's HUD only, and the phone has its own "
                  "appearance control instead."),
    },
}


def place_for(words) -> dict:
    """The real place for one off-list function, by its owner phrase, or {}."""
    try:
        import re as _re
        text = " ".join(_re.sub(r"[^a-z0-9 ]", " ", str(words or "").lower()).split())
    except Exception:                       # noqa: BLE001 - never raise a read
        return {}
    if not text:
        return {}
    for key, row in PLACES.items():
        if key in text:
            return dict(row)
    return {}

# ---------------------------------------------------------------------------
#   HERITAGE: WHAT JARVIS IS, AND WHAT WAS BORROWED FROM WHOM (2026-11-07)
# ---------------------------------------------------------------------------
# The owner's Q4 ruling (2026-11-07): Jarvis must deterministically answer BOTH
# halves - what makes it different, and which ideas it borrowed from which
# competitors - and must never invent a borrow the record does not contain.
# Both sentences are READ-ONLY and derived from the project's own record:
#   * differentiators: CLAUDE.md's five rules, docs/ARCHITECTURE.md, the voice
#     print (jarvis_voiceprint), the memory (jarvis_memory) and the local model
#     lanes (jarvis_model_lanes) - each is a live property of this PC.
#   * lineage: docs/COMPETITORS-2026-10-05.md, docs/ABOUT-JARVIS.md section 2,
#     docs/COMPETITORS-MUSE-2026-09-25.md and the Hermes borrow rows in
#     CHANGELOG.md/JARVIS-API.md (2026-11-05/06).
# Changing a word here without the record behind it is the Muse failure the
# audit exists to prevent.
HERITAGE = {
    "differentiators": {
        "part": "differentiators",
        "digest": ("Different: voice-print check before acting (local CAM++/TitaNet), "
                   "zero standing grants (one card per action, Windows Hello / phone "
                   "biometrics), bitemporal owner-words-only memory with real erase + "
                   "VACUUM, strict local-first egress (no public tunnel; local Ollama on "
                   "three GPUs)."),
        "sentence": ("What makes me different is not a feature count - it is what has to "
                     "be trusted. (1) Your voice is checked before I act on it: a local "
                     "speaker check (CAM++/TitaNet embeddings, kept on this PC) has to "
                     "recognise you, and the phone uses its own fingerprint for risky "
                     "approvals. (2) There are no standing grants: one approval card per "
                     "action, no approve-all, no auto-approve, and a risky yes needs "
                     "Windows Hello on the PC or the phone's biometrics - so nothing is "
                     "allowed later in advance. (3) Memory is bitemporal and learns only "
                     "from your own words, and every fact can really be erased - the text, "
                     "the search entry, the meaning vector and then VACUUM, not just hidden. "
                     "(4) Everything stays local: no account, no public tunnel, no cloud by "
                     "default; the phone reaches this PC over Tailscale or NordVPN Meshnet, "
                     "and the models run on this PC's own graphics cards through Ollama. "
                     "A sentence about what I can reach is answered from the live settings "
                     "(\"what can you reach?\"), never from a claim."),
    },
    "lineage": {
        "part": "lineage",
        "digest": ("Borrowed, on the record: Muse (2026-09-25 audit) - one-card-per-email "
                   "sending, hiding one-time OTP codes from screen capture, /api/reach. "
                   "OpenMuse - a durable job queue (Long Fuse) with frozen capabilities and "
                   "park-on-approval. ChatGPT Dots - a compact ambient presence indicator "
                   "and non-intrusive HUD status rails. Nous Hermes Agent v0.23.0 - "
                   "deny-and-steer (the deny-and-say-what-to-do-instead note), hidden-Unicode/control-byte warning "
                   "pills, the \"What it costs\" cloud ledger line, a curator lock with "
                   "provenance badges on packs, and in-memory encrypted session search."),
        "sentence": ("Yes, I borrow ideas on the record - pretending otherwise would be the "
                     "wrong answer. From Meta's Muse (the 2026-09-25 audit): sending email "
                     "with one approval card per email showing the exact recipients, "
                     "subject and text; hiding one-time codes (OTP) from screen capture; "
                     "and /api/reach, one place that says what Jarvis can reach. From "
                     "OpenMuse: a durable job queue - the Long Fuse pattern - with frozen "
                     "capabilities per job and a job that parks on an approval instead of "
                     "acting. From OpenAI's ChatGPT Dots: the compact ambient presence "
                     "indicator and non-intrusive HUD status rails. From Nous Hermes Agent "
                     "v0.23.0: approval cards that let you deny AND say what to do instead "
                     "(the deny-and-say-what-to-do-instead note); warning pills for hidden Unicode and control "
                     "bytes; the \"What it costs\" line on cloud cards; a curator lock with "
                     "provenance badges on packs; and in-memory encrypted session search. "
                     "What I refuse is also on the record: no standing grants, no always "
                     "allow, no connector store, no data-for-service."),
    },
}


def heritage(part: str) -> dict:
    """One heritage half, a copy, or {} - never a guessed borrow."""
    row = HERITAGE.get(str(part or ""))
    return dict(row) if row else {}


def heritage_words(part: str) -> str:
    row = heritage(part)
    return str(row.get("sentence") or "") if row else ""


def heritage_digests() -> dict:
    return {key: str(row.get("digest") or "") for key, row in HERITAGE.items()}
