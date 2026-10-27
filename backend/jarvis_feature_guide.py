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


def _name_tokens(row: dict) -> tuple:
    out = _tokens(row["id"].replace("-", " ")) + _tokens(row["title"])
    for alias in row.get("aliases") or ():
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
    for alias in row.get("aliases") or ():
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
    return any(query == _norm(alias) for alias in row.get("aliases") or ())


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


def _read_second_card_feature(feature: str):
    def reader():
        import jarvis_second_card as M
        features = M.status().get("features") or {}
        if feature not in features:
            raise LookupError(feature)
        return features.get(feature) is True
    return reader


def _read_second_card_suggest(signal: str):
    def reader():
        import jarvis_second_card as M
        for row in M.suggest_settings().get("switches") or ():
            if isinstance(row, dict) and row.get("id") == signal:
                return row.get("enabled") is True
        raise LookupError(signal)
    return reader


#: BoolSetting.key -> the reader above. One entry per switch in
#: jarvis_settings_registry.BOOL_SETTINGS; `test_feature_guide.py` fails if a
#: switch is added to that table without a reader here, so "is it on?" can
#: never silently answer for only some of the switches.
STATE_READERS = {
    "background_learning": lambda: _read_auto_learn("auto"),
    "learn_sensitive_topics": lambda: _read_auto_learn("auto_sensitive"),
    "lights_without_card": _read_lights_without_card,
    "prompt_coach": _read_prompt_coach,
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
    "second_card_combined": _read_second_card_feature("combined"),
    "second_card_suggest_struggle": _read_second_card_suggest("struggle"),
    "second_card_suggest_correction": _read_second_card_suggest("correction"),
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


def switches_for(row: dict) -> list:
    """The BoolSetting objects whose Settings place this feature covers.

    The link is the feature list's own `covers` (`settings.<section id>`) and
    BoolSetting.section - the same section ids `jarvis_quick` opens by name.
    """
    R = _registry()
    if R is None or not row:
        return []
    covers = set(row.get("covers") or [])
    out = []
    for setting in R.BOOL_SETTINGS:
        section = getattr(setting, "section", None)
        if section and f"settings.{section}" in covers:
            out.append(setting)
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
    the SAME switch the five labels are built from; `switches_for()` stays the
    write path's own rule, untouched, because `switch_target()` must not start
    resolving a switch it did not before.
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


def _state_clause(rows: list) -> str:
    """One plain sentence about the switches, or "" when the feature has none."""
    if not rows:
        return ("The feature list names no on/off switch for it, so there is no "
                "state for me to read.")
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
#: Each row's own `surface_reason` says so - "the desktop's floating face draws the
#: real animal" (phone-floating) and "the desktop's frame-rate setting is the
#: animal's, a different thing" (phone-screen-rate) - so "The PC does not have that
#: control" contradicted the surface line printed in the same answer (2026-10-26,
#: part B). The PC's control is not this setting, and the row's `where` names only
#: the phone's.
PHONE_PC_COUNTERPART = {
    "phone-floating": "The PC's floating face is a different control.",
    "phone-screen-rate": "The PC's frame-rate setting is the animal's, a different control.",
}


def _phone_pc_claim(row: dict) -> str:
    """What this phone row says about the PC's own side, from the row's data."""
    return PHONE_PC_COUNTERPART.get(
        str(row.get("id") or ""), "The PC does not have that control.")


def phone_change_words(row: dict) -> str:
    """How a PHONE-ONLY row is changed: on the phone, never "on this PC".

    Five rows (phone-notifications, phone-watch, phone-floating, phone-tiles,
    phone-screen-rate) carry the PC-Only label because the phone is the only app
    with the control, and `_label_from` picks that label from the row's reason
    without looking at `surface`. The label's own words therefore said "on this
    PC" for rows the PC does not have at all (2026-10-26 review, F3). The row's
    `surface` wins, and the row's own `where` names the place.

    The closing claim about the PC is per row (`_phone_pc_claim`): three of the
    five really have no PC control, and saying so for the other two would
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

    TWO rows are the exception, and their sentence is replaced rather than
    softened for all four: the phone's Appearance screen really does write the
    SHARED document - it picks a face and pushes it, and the desktop adopts it
    (2026-10-26 semantic read, finding 3). See BOTH_PHONE_WRITES.
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
    clause = _state_clause(rows)
    if clause:
        parts.append(clause)
    parts.append(change_words(row))
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


# --------------------------------------------------------------------------
#   "Is it on?": a feature, or a plain setting the registry already names
# --------------------------------------------------------------------------

def _setting_target(words):
    """(setting, label) for a plain on/off setting named exactly, or (None, "")."""
    R = _registry()
    if R is None:
        return None, ""
    text = " ".join(w for w in _norm(words).split() if w not in _GENERIC)
    setting = R.find_bool_setting(text)
    if setting is None:
        return None, ""
    return setting, _setting_words(setting)


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
    got = find(words, loose=True)
    if got["kind"] == "feature":
        row = got["row"]
        rows = _switch_state_rows(row)
        if not rows:
            return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                    "state": None, "switches": [],
                    "words": (f"{row['title']} has no on/off switch in the feature list, "
                              f"so there is no state for me to read.")}
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
    got = find(words, loose=True)
    if got["kind"] == "feature":
        row = got["row"]
        rows = _switch_state_rows(row)
        base = (f"{row['title']}. Where: {str(row.get('where') or '').strip()} "
                f"Does it ask first? {str(row.get('asks') or '').strip()}")
        if not rows:
            # An ability with no switch is not a dead end: say which kind it is
            # and how to use it, in the same words the "turn on <ability>"
            # phrase already gives (2026-10-26).
            return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                    "switches": [], "words": (base + " The feature list names no on/off "
                                              "switch for it, so there is nothing to turn "
                                              "on or off there. " + ability_explanation(row))}
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
    # The three planned Switchable rows (2026-10-23) still need an allowlist
    # reason for matrix_rows_without_reason(); their label stays Switchable and
    # their row status stays planned, so this reason is reported, not a hidden pass.
    "wake-word": ("planned", "no own switch or typed control is wired today; planned row", "voiceprint-wiring"),
    "read-aloud": ("planned", "the read-aloud control is not a registered switch and has no typed path yet", "voiceprint-wiring"),
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
}

#: Feature ids whose typed controls do not live behind a `settings.<id>` cover,
#: because the feature list names the Brain/Windows page instead. Each entry
#: links the catalogue's own row to the real switch keys that exist for it; the
#: keys are BoolSetting keys from jarvis_settings_registry, checked by the suite.
EXTRA_CONTROLS = {
    "memory-saved": ("background_learning",),
    # The two learning switches are explained by the feature row that names the
    # Brain's Memory tab; their Settings card is `memory-learning` (2026-10-22).
    "memory-learning": ("background_learning", "learn_sensitive_topics"),
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
}

#: Features that ARE command-controllable but have NO desktop Settings control
#: today (setup-ui's audit of 2026-10-22, checked against the page). Recorded
#: here so a page-less typed path never LOOKS covered in the matrix: the typed
#: side is real and tested, the Settings half is another owner's work, and the
#: matrix must say both. `controls` names the setting keys that are typed but
#: not drawn in Settings; `desktop`/`phone` are the owners of those halves.
SETTINGS_GAPS = {
    "history": {
        "controls": ("chat_history",),
        "desktop": "setup-ui",
        "phone": "Session B",
        "reason": ("The chat-history switch and its retention choice live only in "
                   "Brain -> History; the desktop Settings page has no control "
                   "for either (just a jump note), and the phone has no Settings "
                   "row for them. The retention choice is NOT typed for now "
                   "(2026-10-22 decision: no spoken path to immediate deletion)."),
    },
    "memory-learning": {
        "controls": ("background_learning", "learn_sensitive_topics"),
        "desktop": "setup-ui",
        "phone": "Session B",
        "reason": ("Both learning switches live only in Brain -> Memory -> "
                   "Learning; no Settings row exists on either app. A desktop-only "
                   "card would also need a phone OpenPlace decision, so it is "
                   "recorded rather than faked."),
    },
}

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
}


#: Features that are genuinely Switchable/Adjustable in principle, but have NO
#: own typed control wired today. The old matrix gave them a section's
#: representative phrase (voice speed for wake-word/read-aloud, asks-first for
#: lights), which was untrue. Keep the owner's 42-label count, mark the row
#: planned with its own honest reason, and show no fixed phrase - the directory
#: says "Still being wired" instead of a phrase that changes a different thing.
PLANNED_SWITCHABLE = {
    "wake-word": ("voiceprint-wiring",
                  "no own switch or typed control is wired today; a planned row, not a fake phrase"),
    "read-aloud": ("voiceprint-wiring",
                   "the read-aloud control is not a registered switch and has no typed path yet"),
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
}

#: Owner-approved 2026-10-23 label corrections (Gemini ADJ-Q1): these three
#: rows are real controls on ONE app only, so they belong under the PC-Only
#: label even though their typed control exists. The old matrix labelled them
#: Switchable/Adjustable because it looked only at status, not at which app
#: the feature lives on.
PC_ONLY_FEATURES = {"calendar", "phone-notifications", "phone-watch"}

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
    "look-at-this": (("screen_picture",), ("feature_switch",), {}),
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


def _sections_in(row: dict) -> list:
    R = _registry_module()
    if R is None:
        return []
    out = []
    for cover in row.get("covers") or ():
        text = str(cover or "")
        if not text.startswith("settings."):
            continue
        sid = text.split("settings.", 1)[1]
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

#: Rows BOTH apps have whose SHARED appearance document the phone really does
#: write. The blanket `both_pc_change_words()` sentence says the phone "cannot
#: change the PC's setting", which is false for these two (2026-10-26 semantic
#: read, finding 3): the phone's Appearance screen picks a face and pushes it -
#: `appearance.setFace()` then `JarvisRuntime.pushAppearance()`
#: (`jarvis-client/.../MainActivity.kt:3233-3236`), the document carries `face`
#: (`.../data/AppearanceStore.kt:424-429`), and the desktop adopts it
#: (`jarvis-desktop/src-tauri/src/appearance.rs:76`, `:166-177`). The theme is
#: deliberately NOT in that document (`AppearanceStore.kt:417-422`), so each row
#: says which half travels. Each string is the sentence after "Its setting is
#: in <place>. "
BOTH_PHONE_WRITES = {
    "faces": ("On the phone, Appearance picks the same face and sends it to the "
              "PC, so either app can change it."),
    "appearance": ("On the phone, Appearance changes the same face and state "
                   "colours and sends them to the PC; the theme itself stays on "
                   "each device."),
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
    "briefing_senders",      # "ON through ONE approval card" jarvis_briefing.py:2116
    "chat_history",          # "OFF at once, ON is its own card" registry:967
    "media_index",           # "ON is ONE normal approval card" registry:721-725
    "headless_browser",      # BE.request(...) registry:688-694
    "screen_picture",        # SP.request(...) registry:662-668
    "lights_without_card",   # request_lights(...) registry:605-611
    "sandbox_exec",          # "ON is ONE normal approval card" registry:700-705
})
#: ...and the four whose setter says it never asks. `humour` is the row the
#: semantic read caught: `set_humor` - "At once either way - it changes wording
#: only." (registry:910-912).
CARD_FREE_SWITCHES = frozenset({
    "prompt_coach",   # "Neither direction asks" registry:566-568
    "humor",          # "At once either way" registry:910-912
    "write_like_me",  # "No card either way" registry:976-979
    "pictures",       # "BOTH directions ... neither asks" registry:736-738
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
