"""jarvis_feature_guide.py - "what is this feature?", "where is it?", "is it on?"

The owner's request (2026-10-20, after the field test of 2026-10-19/20): "Does
Jarvis ... have the ability to explain the different features the program has
and activate/deactivate them for me?" Chat could already CHANGE 52 settings by
fixed phrases, but it could not explain a single feature, and "is the prompt
coach on?" was answered "I don't know its current state directly". This module
is the missing read half - and it only ever reports facts that are written
down, never a guess:

  * WHAT a feature is, and WHERE it is switched on, come VERBATIM from the
    owner's own feature list (`features/features.json`, 138 rows). The list is
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
    return _tokens(row["id"].replace("-", " ")) + _tokens(row["title"])


def _extra_tokens(row: dict) -> tuple:
    """Words from `what`/`where`: aliases the owner may use ("the coach
    button"), only consulted when the question says "feature"/"explain"."""
    out = []
    for key in ("what", "where"):
        for word in _tokens(row.get(key) or ""):
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
    return query in (_norm(row["id"].replace("-", " ")), _norm(row["title"]))


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


def _switch_state_rows(row: dict) -> list:
    out = []
    for setting in switches_for(row):
        out.append({"key": setting.key, "label": _setting_words(setting),
                    "state": read_state(setting.key)})
    return out


def _surface_words(surface: str) -> str:
    return {"both": "It is in both apps - the PC and the phone.",
            "desktop": "It is on the PC only.",
            "phone": "It is on the phone only."}.get(surface, "")


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


def explain_words(row: dict) -> str:
    """The exact facts, in plain words, made only from the row and the switches."""
    parts = [f"{row['title']}.", str(row.get("what") or "").strip(),
             f"Status: {label_for(row)}.",
             f"Settings: {settings_path_words(row)}.", "",
             f"Where: {str(row.get('where') or '').strip()}",
             f"Does it ask first? {str(row.get('asks') or '').strip()}",
             f"The honest limit: {_limit_words(row)}"]
    if _surface_words(row.get("surface")):
        parts.append(_surface_words(row.get("surface")))
    rows = _switch_state_rows(row)
    clause = _state_clause(rows)
    if clause:
        parts.append(clause)
    if len(rows) == 1:
        setting = next((s for s in switches_for(row) if s.key == rows[0]["key"]), None)
        if setting is not None:
            parts.append(f"To change it, say \"turn on {rows[0]['label']}\" or "
                         f"\"turn off {rows[0]['label']}\".")
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
            return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                    "state": value, "switches": rows,
                    "words": (f"\"{row['title']}\" is {ON_WORD if value else OFF_WORD} "
                              f"right now.")}
        return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                "state": known[0]["state"] if len({r["state"] for r in known}) == 1 else None,
                "switches": rows, "words": _state_clause(rows)}
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
            return {"ok": True, "kind": "feature", "feature": _feature_facts(row),
                    "switches": [], "words": (base + " The feature list names no on/off "
                                              "switch for it, so there is nothing to turn "
                                              "on or off there.")}
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
    "faces": ('app-local', "Saved by each app locally (this computer's or this phone's own appearance or behaviour) with no backend route to change it. The Settings control is its one true home; a typed path would need a client-side route the backend cannot invent.", 'setup-ui'),
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


def _matrix() -> list:
    """The cached control_matrix() - one build per process (it calls the real
    matcher ~500 times), so the directory/label helpers stay fast."""
    global _MATRIX_CACHE
    if _MATRIX_CACHE is None:
        _MATRIX_CACHE = _build_matrix()
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
    "temporary-chat": "start a temporary chat",
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


def settings_path_words(row: dict) -> str:
    """The EXACT place the owner finds this feature, in Settings words."""
    sections = _section_words(row)
    if sections:
        return f"Settings, {sections}"
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
    if label == LABEL_ALWAYS_ON:
        why = str(row.get("what") or row.get("asks") or "").strip()
        extra = ALWAYS_ON_EXCEPTION.get(str(row.get("id") or ""))
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
    return (f"{title} is a Command-Only ability (runs when you ask, no switch "
            f"needed). {why} {example_phrase_words(row)}. It is listed at {path}.")


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
    """All 139 features with the five plain labels - the data both apps'
    "All features & abilities" Settings directory and search are built from
    (Gemini Q2b/Q8; the UI itself is setup-ui's and Session B's)."""
    return [ability_row(row) for row in features()]
