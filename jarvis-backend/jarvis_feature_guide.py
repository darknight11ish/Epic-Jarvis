"""jarvis_feature_guide.py - "what is this feature?", "where is it?", "is it on?"

The owner's request (2026-10-20, after the field test of 2026-10-19/20): "Does
Jarvis ... have the ability to explain the different features the program has
and activate/deactivate them for me?" Chat could already CHANGE 52 settings by
fixed phrases, but it could not explain a single feature, and "is the prompt
coach on?" was answered "I don't know its current state directly". This module
is the missing read half - and it only ever reports facts that are written
down, never a guess:

  * WHAT a feature is, and WHERE it is switched on, come VERBATIM from the
    owner's own feature list (`features/features.json`, 137 rows). The list is
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
    parts = [f"{row['title']}.", str(row.get("what") or "").strip(), "",
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
        return None, (f"{row['title']} has no on/off switch in the feature list, so there "
                      f"is nothing for me to change. {explain_words(row)}")
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
