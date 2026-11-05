"""jarvis_self_portrait.py - what Jarvis is made of on this PC, right now.

THE OWNER'S ASK (2026-11-03): "Jarvis must be as flexible and versatile as it
reasonably can be - open any menu or setting area on request, pull up any old
conversation, have multiple conversation windows open at once, clear any memory
or conversation on request, and be aware of every setting, function and ability
it has."

THIS MODULE IS THE INVENTORY HALF of that, and it adds no new source of truth:

  * PLACES ARE IMPORTED, never hand-written. Every place this module names comes
    from the two registries that already exist and are already held to the real
    UI by their own tests and generators:
        jarvis_settings_registry.SECTIONS - every Settings card, tied to
            settings.html's ids and SettingsScreen.kt's item keys;
        jarvis_menus.MENUS - the per-app menu ids that Show-or-hide lists,
            with `area` (settings | brain | entry | safety) and `view`.
    A hand-written fourth list would disagree with the apps within a week
    (docs/RESEARCH; the F6 research's F2). `test_self_portrait.py` fails if a
    single real section or menu is missing from the portrait.
  * THE SAME GOES FOR EVERYTHING ELSE. Settings are the registry's own
    BOOL_SETTINGS / CHOICE_SETTINGS, with their live on/off values read through
    jarvis_feature_guide.read_state() (the one public reader). Abilities are
    jarvis_feature_guide.features(). What asks first is jarvis_asks_first.view().
    Plugins are the drop-in folders jarvis_plugins already discovered.
  * FIXED DATA AND LIVE STATE ONLY (the F6 research's F10). Nothing here reads,
    stores or returns the pairing token, an API key, an account secret, raw
    memory or chat text, an email or web page, an owner folder path, or any
    model-written sentence. A store whose count cannot be read says so rather
    than guessing. A switch that cannot be read says `null`, never "off".
  * IT IS NOT A THIRD EXPLANATION SOURCE. "What is feature X?" / "how do I use
    it?" belongs to jarvis_feature_guide.py (and the F5 work on the same
    branch); "change setting X" belongs to jarvis_settings_registry.py. This
    module answers "what exists, what is it called, is it on, where does it
    live, how is it changed" - the manifest, not the prose.

WHAT IT SERVES (all GET unless noted; every one read-only except the clear):

    GET  /api/self                  - the portrait (this module's build())
    GET  /api/self/version          - the cheap identity block alone, for an
                                      updater that only wants to compare
    GET  /api/conversations         - the history list (adapter, one truth:
                                      jarvis_chat_log.handle_get)
    GET  /api/conversations/<id>    - one conversation's turns (adapter)
    POST /api/conversations/clear   - ONE conversation, ONE approval card

WHY THE CONVERSATION ROUTES ARE ADAPTERS AND NOT A SECOND STORE. Conversation
ids already exist and are already per-request: both clients send
`conversation_id` on every /api/chat call, jarvis_chat_log keeps one row per id,
and two windows already hold two ids. So "multiple concurrent conversations"
needs no registry and no schema change - it is what the storage already does.
The routes here are thin aliases onto jarvis_chat_log's own tested handlers, so
there is exactly one list, one reader and one delete in the codebase.

CLEAR IS TWO-PHASE AND ONE ITEM (the F6 research's F8/F9 and the Lead's
correction): the request names ONE conversation id; this module reads that
conversation, builds a consequence-first card naming its title and message
count, that the learned facts are KEPT, and that copies in older backups stay
until they age out, and raises ONE approval card (action `conversation_clear`,
tier `ask`). Only a person's yes deletes anything, through the existing
jarvis_chat_log.delete(). There is no bulk route, no cardless path, and the
model cannot clear without that card - the request function refuses any other
tier exactly as "Forget a time frame" does. Deleting a chat never touches the
memory store; test_self_portrait.py proves a fact survives a cleared chat.

NEW MODULE, shipped whole, no patch of its own: its routes come from the
drop-in folder plugins/ready/self-portrait, which calls install(). Standard
library only. No network. No writes at import time; the only writes it ever
makes are the one delete a person approved.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, quote, urlsplit

#: The one version this answer's shape is; a client that does not know a newer
#: number ignores what it does not understand instead of guessing (the F6
#: research's F11, "version skew is first-class").
SCHEMA = "jarvis-self-portrait/1"

SELF_PATH = "/api/self"
VERSION_PATH = "/api/self/version"
REFRESH_PATH = "/api/self/refresh"
CONVERSATIONS_PATH = "/api/conversations"
CLEAR_PATH = "/api/conversations/clear"

#: Every route install() answers. A path not in here goes straight to the
#: server's own handler, so this module cannot shadow anything.
ROUTES = (SELF_PATH, VERSION_PATH, REFRESH_PATH, CONVERSATIONS_PATH, CLEAR_PATH)

#: The storage self-scan's own routes, when `jarvis_storage_health.py` is on
#: this PC (a separate worker's module, shipped by PR #1117). It is NOT a
#: dependency: with the module absent its routes are simply not served and
#: everything here works exactly as before; the scan itself, its plan and its
#: ONE-card apply are that module's.
#:
#: THE IMPORT IS A PLAIN, GUARDED `import` ON PURPOSE, so a PC whose install
#: predates the module, or whose copy is damaged, keeps this page up. Since
#: #1117 merged, the module is in _where.py's SHIPPED set and the published
#: base carries it, so the two audit exemptions this comment used to name
#: (test_shipped_modules.py's REPO_ONLY_IMPORTS and
#: test_base_matches_repo.py's OPTIONAL_IMPORTS) are gone - they were removed
#: in the same change, along with the stale reason they recorded. A PC without
#: the module must still SAY so rather than serving nothing quietly - see
#: storage_absence_words() and the start-up banner line.
try:
    import jarvis_storage_health as _STORAGE
except ImportError:                          # not installed on this older PC
    _STORAGE = None
except Exception:                            # noqa: BLE001 - a damaged drop-in must not
    _STORAGE = None                          # take the self portrait down with it

#: The one sentence said when the storage self-scan is not on this PC. It is
#: TESTED (test_self_portrait.py) so the absence cannot silently read as "there
#: is nothing to scan".
STORAGE_MISSING = ("The storage self-scan is not installed on this PC, so there "
                   "is no scan to run yet. Everything else works as before.")


def storage_available() -> bool:
    """True when PR #1117's drop-in module is really on this PC."""
    return _STORAGE is not None


def storage_absence_words() -> str:
    """The plain sentence for a PC without the storage self-scan, or ""."""
    return "" if _STORAGE is not None else STORAGE_MISSING


def storage_routes() -> tuple:
    """The storage module's own route paths, or () when it is not on this PC.

    `jarvis_storage_health` ships its routes in BOTH shapes: `ROUTES` is a
    tuple of row dicts (method/path/handler/what) and `GET_ROUTES`/`POST_ROUTES`
    hold the bare paths. Accept either, so a module that changes shape cannot
    take the scan down quietly: a dict row contributes its "path" when that is
    a non-empty str, a string contributes itself, and anything else is skipped.
    Never raises.
    """
    if _STORAGE is None:
        return ()
    try:
        routes = []
        for entry in getattr(_STORAGE, "ROUTES", ()) or ():
            if isinstance(entry, dict):
                path = entry.get("path")
                if isinstance(path, str) and path:
                    routes.append(path)
            elif isinstance(entry, str):
                routes.append(entry)
        return tuple(routes)
    except Exception:                       # noqa: BLE001 - a route list that cannot be read
        return ()


#: The gate action the clear card is raised under. It must be tier "ask" in
#: jarvis-framework.toml; any other tier is refused rather than obeyed (the
#: same rule jarvis_forget_range.py applies to its own action).
CLEAR_ACTION = "conversation_clear"

#: The recorded deploy state apply-patches.ps1 writes beside jarvis_hud.py.
#: The live modules the deploy replaces are identified by the sha256 in its
#: `files` map (and, when tools/reseal_live_install.py has run, by the
#: `resealed` block's commit). Read-only, at most once per STATE_TTL seconds,
#: and a missing or unreadable file is "unknown" - never an exception.
STATE_NAME = "_jarvis-state.json"
IDENTITY_MODULES = ("jarvis_gate.py", "jarvis_hud.py", "jarvis_skills.py")

#: How long one built portrait is reused. The inventory is fixed registry data;
#: only the live state (switch values, counts) can move, and a HUD that reads
#: this on a timer must not re-read every module once a second.
TTL = 20.0
STATE_TTL = 60.0

#: A conversation id, the same shape jarvis_chat_log accepts (`_CID` there).
_CID = re.compile(r"[A-Za-z0-9_-]{8,64}")
#: Characters a title may carry out to a card. No newlines - a card is lines.
_TITLE_MAX = 120

_CACHE: dict = {"at": 0.0, "portrait": None}
_CACHE_LOCK = threading.Lock()
_STATE_CACHE: dict = {"at": 0.0, "block": None}
_STATE_LOCK = threading.Lock()

#: One card at a time, and the last outcome - for the route and the suites.
_CLEAR_LOCK = threading.Lock()
_CLEAR_STATE: dict = {"pending": None, "last": None}

#: Said once when a clear was approved. Counts only, never the title or words.
_LAST_WORDS = {
    "done": "Deleted that one conversation from this PC. The facts Jarvis "
            "learned from it are kept.",
    "denied": "You said no, so nothing was deleted.",
    "timed_out": "Nobody answered the card, so nothing was deleted.",
    "refused": "The approval card could not be used, so nothing was deleted.",
    "failed": "The conversation could not be deleted. Nothing was changed.",
}


# ---------------------------------------------------------------------------
#   Places: every place an "open ..." sentence may name
# ---------------------------------------------------------------------------


def _registry():
    try:
        import jarvis_settings_registry as R
        return R
    except Exception:                       # noqa: BLE001 - older PC
        return None


def _menus():
    try:
        import jarvis_menus as M
        return M
    except Exception:                       # noqa: BLE001 - older PC
        return None


def sections() -> list:
    """The Settings registry's own SECTIONS, in its order, as copies."""
    R = _registry()
    if R is None:
        return []
    out = []
    for s in getattr(R, "SECTIONS", ()) or ():
        names = tuple(getattr(s, "names", ()) or ())
        out.append({"id": str(s.id),
                    "label": (names[0] if names else str(s.id)),
                    "names": list(names),
                    "app": str(getattr(s, "app", "both") or "both"),
                    "where": str(getattr(s, "where", "settings") or "settings"),
                    "openable": bool(getattr(s, "openable", True))})
    return out


def menus() -> list:
    """The menu registry's own MENUS, in its order, as copies."""
    M = _menus()
    if M is None:
        return []
    out = []
    for m in getattr(M, "MENUS", ()) or ():
        out.append({"id": str(m.id),
                    "title": str(getattr(m, "title", "") or ""),
                    "apps": list(getattr(m, "apps", ()) or ()),
                    "area": str(getattr(m, "area", "") or ""),
                    "view": str(getattr(m, "view", "") or ""),
                    "group": str(getattr(m, "group", "") or ""),
                    "kind": str(getattr(m, "kind", "card") or "card"),
                    "hide": bool(getattr(m, "hide", True))})
    return out


def places() -> list:
    """Every place, as two kinds with the registries' own ids.

    `kind` is "settings_section" (id is the section id both Settings screens
    already use) or "menu" (id is jarvis_menus' own stable id). No id is made
    up here: the two registries are the authority, and a test proves every one
    of their ids is present and nothing else is.
    """
    out = []
    for s in sections():
        out.append({"id": s["id"], "kind": "settings_section",
                    "title": s["label"], "apps": [s["app"]],
                    "where": s["where"], "openable": s["openable"]})
    for m in menus():
        out.append({"id": m["id"], "kind": "menu", "title": m["title"],
                    "apps": list(m["apps"]), "area": m["area"],
                    "view": m["view"], "group": m["group"],
                    "openable": True})
    return out


def place_by_id(pid) -> Optional[dict]:
    """One place by its exact id, or None. Never guesses."""
    pid = str(pid or "")
    for row in places():
        if row["id"] == pid:
            return row
    return None


def resolve_place(words) -> Optional[dict]:
    """The place an "open ..." sentence names, as {"route", "id"}, or None.

    EXACT aliases only, read from the two registries (never a fuzzy guess): a
    tail that names no place returns None and the caller falls through to the
    model, exactly as "open the door" already does. `route` is the existing
    X-Jarvis-Route field the apps already act on:
        "settings" - open Settings at that section id (jarvis_quick uses this
                     today for every SECTIONS row);
        "brain"    - open that Brain place (jarvis_open._BRAIN_PLACES values).
    A menu in the `settings` area maps to the section with the same id after
    its "settings." prefix; a menu in the `brain` area maps to its own `view`.
    Both mappings are derived here and checked by test_self_portrait.py, so a
    new menu cannot silently become unopenable.
    """
    text = str(words or "").strip().lower()
    if not text:
        return None
    R = _registry()
    if R is not None:
        try:
            section = R.find_section(text)
        except Exception:                   # noqa: BLE001 - absent registry
            section = None
        if section is not None and getattr(section, "openable", True):
            return {"route": "settings", "id": str(section.id)}
    M = _menus()
    if M is not None:
        try:
            menu_id = M.resolve(text)
        except Exception:                   # noqa: BLE001 - absent registry
            menu_id = None
        if menu_id:
            row = M.menu(menu_id)
            if row is not None:
                area = str(getattr(row, "area", "") or "")
                if area == "settings":
                    # The menu id after "settings." names the row; a SUB-row
                    # ("settings.second-card.study-helper") shares its parent's
                    # card, so the longest PREFIX that is a real section is the
                    # place to open. Never answer a menu id as a section id: a
                    # client would jump nowhere (the apps' goToPlace knows only
                    # SECTIONS ids).
                    bare = menu_id[len("settings."):] if menu_id.startswith(
                        "settings.") else ""
                    parts = bare.split(".") if bare else []
                    while parts:
                        candidate = ".".join(parts)
                        if R is not None and R.section_by_id(candidate) is not None:
                            return {"route": "settings", "id": candidate}
                        parts.pop()
                    return None
                view = str(getattr(row, "view", "") or "")
                if area == "brain" and view:
                    return {"route": "brain", "id": view}
    return None


# ---------------------------------------------------------------------------
#   The fixed inventory: settings, what asks first, abilities, plugins
# ---------------------------------------------------------------------------


def _feature_guide():
    try:
        import jarvis_feature_guide as FG
        return FG
    except Exception:                       # noqa: BLE001 - older PC
        return None


#: Said for a choice whose stored value could not be read on this PC just now.
#: Fixed text, and never a default dressed up as the value (see settings()).
CHOICE_VALUE_UNKNOWN = ("The value could not be read on this PC just now - the module that "
                        "owns it is missing or did not answer. It is not guessed here.")


def settings() -> list:
    """Every setting a person can find, with its live value where one is known.

    The rows are the registry's own BOOL_SETTINGS (a switch) and CHOICE_SETTINGS
    (a named choice), so this list cannot name a setting that does not exist.
    A switch's value is jarvis_feature_guide.read_state() - None when it cannot
    be read here, which is said as `null` and never as "off".

    A CHOICE'S VALUE IS READ TOO (2026-11-04). It used to be hard-coded
    `null` / `value_known: false` for all ten, on the belief that no public
    reader existed; one does, and the Settings explainer has used it since
    2026-11-03: `jarvis_settings_registry.current_value()` ->
    `ChoiceSetting.now()`, whose branches call the module that OWNS each value
    (jarvis_handoff_mode, jarvis_handoff_front, jarvis_voices, jarvis_manner,
    jarvis_presets, jarvis_antislop, jarvis_owner_check, jarvis_schedule, the
    HUD's appearance view). This module stores nothing and defaults nothing: it
    asks that one reader, so the portrait and the settings answer cannot say two
    different values. A read that fails stays `value_known: false` with
    `value_why` naming the reason - never a default pretending to be the value.
    """
    R = _registry()
    FG = _feature_guide()
    if R is None:
        return []
    rows = []
    for b in getattr(R, "BOOL_SETTINGS", ()) or ():
        names = tuple(getattr(b, "names", ()) or ())
        value = None
        if FG is not None:
            try:
                value = FG.read_state(str(b.key))
            except Exception:               # noqa: BLE001 - said as unknown
                value = None
        rows.append({
            "id": str(b.key), "kind": "switch",
            "label": (names[0] if names else str(b.key)),
            "names": list(names),
            "section": str(getattr(b, "section", "") or ""),
            "value": value if isinstance(value, bool) else None,
            "value_known": isinstance(value, bool),
            "changeable": True,
            "how_to_change": ("Say \"turn on/off <the setting>\". A change that "
                              "loosens a rule still raises its own card."),
        })
    for c in getattr(R, "CHOICE_SETTINGS", ()) or ():
        names = tuple(getattr(c, "names", ()) or ())
        options = []
        try:
            options = sorted(str(k) for k in (c.options() or {}))[:24]
        except Exception:                   # noqa: BLE001 - absent module
            options = []
        value = None
        try:
            value = R.current_value(c)
        except Exception:                   # noqa: BLE001 - said as unknown
            value = None
        known = isinstance(value, str) and bool(value.strip())
        rows.append({
            "id": str(c.key), "kind": "choice",
            "label": (names[0] if names else str(c.key)),
            "names": list(names),
            "section": str(getattr(c, "where", "") or ""),
            "value": value if known else None,
            "value_known": known,
            "value_why": "" if known else CHOICE_VALUE_UNKNOWN,
            "options": options,
            "changeable": True,
            "how_to_change": ("Say \"set <the setting> to <one of its own "
                              "choices>\". Its own card rule still applies."),
        })
    for n in getattr(R, "NUMBER_SETTINGS", ()) or ():
        names = tuple(getattr(n, "names", ()) or ())
        value = None
        try:
            import jarvis_limits as JL
            limit = n.limit()
            if limit is not None:
                value = JL.value_of(limit)
        except Exception:                   # noqa: BLE001 - said as unknown
            value = None
        try:
            label = n.title()
        except Exception:                   # noqa: BLE001
            label = names[0] if names else str(n.key)
        rows.append({
            "id": str(n.key), "kind": "number",
            "label": label,
            "names": list(names),
            "section": "",
            "value": value if isinstance(value, int) else None,
            "value_known": isinstance(value, int),
            "low": n.low(), "high": n.high(), "unit": n.unit(),
            "changeable": True,
            "how_to_change": ("Say \"set <the setting> to <a number of seconds or "
                              "minutes>\". Nothing loosens: it only decides when "
                              "an idle session ends."),
        })
    return rows


def asks_first() -> dict:
    """What asks first, straight from jarvis_asks_first's own view().

    That view is the page both apps already draw: one row per action, its tier
    (read vs ask), and its own words. Read here, never reworded, so this cannot
    promise a permission the gate does not keep.
    """
    try:
        import jarvis_asks_first as A
        view = A.view(here=False)
    except Exception:                       # noqa: BLE001 - older PC
        return {"available": False, "groups": [], "why": "jarvis_asks_first.py is not on this PC"}
    groups = []
    for g in view.get("groups") or ():
        rows = []
        for r in g.get("rows") or ():
            rows.append({"id": str(r.get("id") or ""),
                         "title": str(r.get("title") or ""),
                         "tier": str(r.get("tier") or ("fixed" if r.get("fixed") else "")),
                         "says": str(r.get("says") or "")})
        groups.append({"group": str(g.get("title") or ""), "rows": rows})
    return {"available": True, "groups": groups, "why": ""}


def abilities() -> list:
    """Every feature row the features list ships, as copies.

    The rows are jarvis_feature_guide.features(): the same list the Features
    page on both apps shows, generated from features/features.json. Only the
    inventory fields are carried - the prose (`what`, `where`, `asks`, `limit`)
    stays in jarvis_feature_guide, which is the one module allowed to explain a
    feature (this module is not a third explanation source).
    """
    FG = _feature_guide()
    if FG is None:
        return []
    out = []
    for row in FG.features():
        out.append({"id": str(row.get("id") or ""),
                    "group": str(row.get("group") or ""),
                    "title": str(row.get("title") or ""),
                    "surface": str(row.get("surface") or "both")})
    return out


def tool_inventory() -> dict:
    """The tools this backend registers, and the ones the AI model is offered.

    THE NUMBER THAT USED TO BE WRONG (the 2026-11-04 self-awareness audit).
    `counts()["tools"]` held the ASKS-FIRST ROW COUNT - 136 permission rows -
    and the model's own self_portrait tool handed that dict straight back, so
    "how many tools do you have" could be answered "136" with total confidence
    while this backend had 51 tools and 13 switched on. The two real counts are
    here, each from the registry that owns it:

      * `registered` - `jarvis_agent.TOOLS`, the tools this backend has built;
      * `enabled`    - the names switched on in `[tools].enabled` of the
        owner's own settings file, read through
        `jarvis_asks_first.tools_enabled_set()` - the SAME read the "What asks
        first" page makes, never a second copy and never a default.

    A tool's OWN switch can still hold it back at turn time (`web_search`'s
    separate on/off, browser control's second-card rule, the data sandbox) -
    that is `jarvis_agent.offered_tools()`'s business and is not counted here,
    because this number answers "how many are switched on in your settings
    file", the question the old 136 was pretending to answer.

    `enabled` is None (never 0) when the settings file cannot be read: a PC
    without the framework module, or with a damaged file, is said as unknown
    rather than as "no tools", exactly like an unread switch.
    """
    registered = None
    try:
        import jarvis_agent as A
        registered = sorted(str(n) for n in (A.TOOLS or {}))
    except Exception:                       # noqa: BLE001 - said as unknown
        registered = None
    enabled = None
    try:
        import jarvis_asks_first as AF
        wanted = set(AF.tools_enabled_set() or ())
        # Names this backend has never had are not tools; the legacy
        # `email_read` spelling is read as the tool it means by real_tool().
        real = {str(getattr(AF, "real_tool", lambda n: n)(n)) for n in wanted}
        registered_set = set(registered or ())
        enabled = sorted(n for n in real
                         if not registered_set or n in registered_set)
    except Exception:                       # noqa: BLE001 - said as unknown
        enabled = None
    why = "" if enabled is not None else (
        "The settings file could not be read, so which tools are offered is unknown.")
    return {"registered": len(registered) if registered is not None else None,
            "registered_names": registered or [],
            "enabled": len(enabled) if enabled is not None else None,
            "enabled_names": enabled or [],
            "source": ("jarvis_agent.TOOLS and "
                       "jarvis_asks_first.tools_enabled_set()"),
            "why": why}


def plugins() -> list:
    """The drop-in module folders this PC has, and whether each is on.

    jarvis_plugins is the loader that owns this folder; its own available()
    reads each folder's plugin.json. A summary is the folder's OWN checked-in
    text (a drop-in folder is code that runs inside the backend process, the
    same trust as jarvis_hud.py itself), never anything the running model
    wrote. A PC with no folder - a checkout, a fresh install - answers [].
    """
    try:
        import jarvis_plugins as P
    except Exception:                       # noqa: BLE001 - older PC
        return []
    try:
        rows = P.available()
        st = P.status() if hasattr(P, "status") else {}
    except Exception:                       # noqa: BLE001 - a read that must not fail
        return []
    loaded = set(st.get("loaded") or ())
    failed = {f.get("name"): f.get("why") for f in st.get("failed") or ()
              if isinstance(f, dict)}
    out = []
    for r in rows:
        name = str(r.get("name") or "")
        out.append({"id": name,
                    "module": str(r.get("module") or ""),
                    "on": bool(r.get("ok")) and not r.get("disabled"),
                    "loaded": name in loaded,
                    "why_not": str(r.get("why") or failed.get(name) or "")})
    return out


# ---------------------------------------------------------------------------
#   Live state: what is stored, and the version/identity block
# ---------------------------------------------------------------------------


def _private(app_locked=None, hide_memory_lists=None) -> dict:
    try:
        import jarvis_private_view as PV
        return PV.effective(app_locked=app_locked,
                            hide_memory_lists=hide_memory_lists)
    except Exception:                       # noqa: BLE001 - absent hook is unlocked
        return {"locked": False, "why": ""}


def _conversation_count() -> tuple:
    """(count or None, why) for the number of kept conversations.

    A COUNT only - no title, no turn and no word is opened, which is why this
    can stay cheap. Read-only SQLite (`mode=ro`), so it can never write to the
    store; a database that is missing, busy or not shaped as expected answers
    None with the reason, never a guess.
    """
    try:
        import jarvis_chat_log as CL
        log = CL._log()
        path = Path(getattr(log, "db_path"))
        if not path.is_file():
            return 0, ""
        # closing(), not a bare `with sqlite3.connect(...) as c:`: the connection
        # object's own context manager commits/rolls back but does NOT close the
        # handle (2026-11-03, test_sqlite_close_guard's finding on this line).
        # A leaked handle is what made schedule.json undeletable on the Windows
        # runner on 2026-10-07; this is the same trap in a read-only count.
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True,
                                     timeout=1.0)) as c:
            return int(c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]), ""
    except Exception as exc:                # noqa: BLE001 - said, never raised
        return None, f"could not be counted ({type(exc).__name__})"


def stores(*, lock: Optional[dict] = None) -> list:
    """The three stores the owner may clear, with live counts where cheap.

    Never a path, never a word: memory counts by number (jarvis_memory's own
    status()), chat-history count by SQL COUNT only. While App lock or "Hide
    memory lists and chat history" is on, the private counts are WITHHELD -
    the same rule /api/history and /api/memory/status already carry.
    """
    lock = lock or {"locked": False, "why": ""}
    withheld = bool(lock.get("locked"))
    out = []

    mem = {"id": "memory", "label": "What Jarvis learned",
           "available": False, "count": None, "counts": {},
           "how_to_clear": ("Forget one fact in Memory, or say \"forget what you "
                            "learned last week\" for Forget a time frame.")}
    if not withheld:
        try:
            import jarvis_memory as M
            st = M.store().status()
            mem["available"] = True
            mem["count"] = int(st.get("current") or 0)
            mem["counts"] = {"facts": int(st.get("facts") or 0),
                             "current": int(st.get("current") or 0),
                             "retired": int(st.get("retired") or 0),
                             "entities": int(st.get("entities") or 0)}
        except Exception as exc:            # noqa: BLE001 - said, never raised
            mem["why_not"] = f"not readable here ({type(exc).__name__})"
    else:
        mem["why_not"] = str(lock.get("why") or "")
    out.append(mem)

    conv = {"id": "conversations", "label": "Chat history",
            "available": False, "count": None,
            "how_to_clear": ("One conversation at a time: ask me to clear one, "
                             "and it is deleted only after you approve ONE card. "
                             "Deleting a chat does not forget facts Jarvis "
                             "learned from it.")}
    try:
        import jarvis_chat_log as CL
        st = CL.status()
        conv["available"] = True
        conv["recording"] = bool(st.get("recording"))
        conv["enabled"] = bool(st.get("enabled"))
        if withheld:
            conv["why_not"] = str(lock.get("why") or "")
        else:
            count, why = _conversation_count()
            conv["count"] = count
            if count is None:
                conv["why_not"] = why
    except Exception as exc:                # noqa: BLE001 - said, never raised
        conv["why_not"] = f"not readable here ({type(exc).__name__})"
    out.append(conv)

    rec = {"id": "receipts", "label": "Action receipts",
           "available": True, "count": None,
           "count_why": ("a receipt list is paged and the store keeps no total "
                         "it can answer here"),
           "how_to_clear": "Undo one in Receipts, on the PC or the phone."}
    try:
        import jarvis_receipts  # noqa: F401 - present means the store exists
        if withheld:
            rec["why_not"] = str(lock.get("why") or "")
    except Exception as exc:                # noqa: BLE001 - said, never raised
        rec["available"] = False
        rec["why_not"] = f"not readable here ({type(exc).__name__})"
    out.append(rec)
    return out


def _app_version() -> tuple:
    """(version, source). "unknown" rather than a guess when there is no file.

    VERSION is the one number the desktop, the phone and the backend share,
    kept by `backend/test_version.py`; backend/selftest.py reads it from the
    repository root. Deployed backend folders do not carry it (the installer
    copies modules, not repository files), so on the live PC this is honestly
    "unknown" and the deploy block below is the real identity.
    """
    here = Path(__file__).resolve().parent
    for cand in (here / "VERSION", here.parent / "VERSION"):
        try:
            text = cand.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if re.fullmatch(r"\d+\.\d+\.\d+", text):
            return text, f"VERSION beside {cand.parent.name or 'the backend'}"
    return "unknown", "no VERSION file beside the backend"


def _started_at() -> Optional[float]:
    """When the running server started, from jarvis_events' own `_STARTED`.

    That module is imported by jarvis_hud.py at boot, so its stamp is the
    server's start. Absent (a checkout, a test) is None, never 0.
    """
    try:
        import jarvis_events as E
        value = float(getattr(E, "_STARTED", 0.0) or 0.0)
        return value if value > 0 else None
    except Exception:                       # noqa: BLE001 - said as unknown
        return None


def _api_version() -> Optional[int]:
    try:
        import jarvis_events as E
        return int(getattr(E, "API_VERSION"))
    except Exception:                       # noqa: BLE001 - said as unknown
        return None


def deploy_block(folder=None) -> dict:
    """What the installer RECORDED about the live backend, or "unknown".

    `_jarvis-state.json` is written beside jarvis_hud.py by
    scripts/apply-patches.ps1 and repaired by tools/reseal_live_install.py. It
    carries sha256 per deployed file and, after a reseal, the repository commit
    the install was put back on. This function reads that file at most once per
    STATE_TTL, never opens the big module files, and answers `recorded: false`
    for a checkout or a folder without one - it is called by a route, so it
    must never raise, never crash the HUD and never write. `folder` is the
    tests' own seam (the module's own folder by default).
    """
    if folder is not None:
        return _read_deploy_state(folder)
    now = time.time()
    with _STATE_LOCK:
        if _STATE_CACHE["block"] is not None and now - _STATE_CACHE["at"] < STATE_TTL:
            return dict(_STATE_CACHE["block"])
    block = _read_deploy_state()
    with _STATE_LOCK:
        _STATE_CACHE["block"] = block
        _STATE_CACHE["at"] = now
    return dict(block)


def _read_deploy_state(folder=None) -> dict:
    out = {"recorded": False, "schema": "", "written": "", "run": "",
           "files_recorded": 0, "files_verified": 0,
           "resealed": {"at": "", "ref": "", "commit": ""},
           "identity": {name: "" for name in IDENTITY_MODULES},
           "why_not": ""}
    path = (Path(folder) if folder is not None
            else Path(__file__).resolve().parent) / STATE_NAME
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        out["why_not"] = "no deploy record beside the backend on this PC"
        return out
    except Exception as exc:                # noqa: BLE001 - a damaged record
        out["why_not"] = f"the deploy record could not be read ({type(exc).__name__})"
        return out
    if not isinstance(doc, dict):
        out["why_not"] = "the deploy record is not an object"
        return out
    out["recorded"] = True
    out["schema"] = str(doc.get("schema") or "")
    out["written"] = str(doc.get("written") or "")
    out["run"] = str(doc.get("run") or "")
    files = doc.get("files") if isinstance(doc.get("files"), dict) else {}
    out["files_recorded"] = len(files)
    verified = 0
    for name in IDENTITY_MODULES:
        row = files.get(name) if isinstance(files.get(name), dict) else {}
        sha = str(row.get("sha256") or "")
        if re.fullmatch(r"[0-9a-f]{64}", sha):
            out["identity"][name] = sha
            if row.get("verified") is True:
                verified += 1
        elif row.get("verified") is True:
            verified += 1
    out["files_verified"] = verified
    resealed = doc.get("resealed") if isinstance(doc.get("resealed"), dict) else {}
    out["resealed"] = {"at": str(resealed.get("at") or ""),
                       # A 40-character hex commit only: this is an identity,
                       # not a place to echo whatever a file happens to hold.
                       "ref": _hex_ref(resealed.get("ref")),
                       "commit": _hex_ref(resealed.get("commit"))}
    return out


def _hex_ref(value) -> str:
    text = str(value or "").strip().lower()
    return text if re.fullmatch(r"[0-9a-f]{7,40}", text) else ""


def version_block() -> dict:
    """The cheap, stable identity an updater can compare. No paths, no secrets.

    `app_version` is the VERSION file when the backend sits beside one, else
    "unknown". `deploy` is the installer's own recorded state: which modules
    the deploy replaced, their sha256, and the commit a reseal put them back
    on. A HUD update button can compare `deploy.identity` / `deploy.resealed`
    against what it is about to install; nothing here changes anything.

    PROVENANCE (Gemini ruling 3, 2026-11-03): `pid` and `started_at` prove which
    PROCESS answered, and `deploy` is the `_jarvis-state.json` manifest summary
    (when it was written, how many files it recorded/verified, the resealed
    commit and the identity hashes) - read-only, no patch to jarvis_hud's own
    /api/version, and the out-of-band Get-FileHash + Get-NetTCPConnection proof
    stays the primary hardware evidence.
    """
    version, source = _app_version()
    deploy = deploy_block()
    return {"schema": SCHEMA,
            "app_version": version,
            "app_version_source": source,
            "api_version": _api_version(),
            "server": "jarvis-hud",
            "pid": os.getpid(),
            "started_at": _started_at(),
            "deploy": deploy,
            # The manifest summary a runner can compare against the folder: the
            # same fields deploy_block reads, copied here so the shape is stable
            # even if deploy's own keys grow later.
            "manifest": {"recorded": bool(deploy.get("recorded")),
                         "written": str(deploy.get("written") or ""),
                         "files_recorded": int(deploy.get("files_recorded") or 0),
                         "files_verified": int(deploy.get("files_verified") or 0),
                         "resealed": dict(deploy.get("resealed") or {})}}


# ---------------------------------------------------------------------------
#   The portrait itself
# ---------------------------------------------------------------------------


def build(*, client: str = "", app_locked=None,
          hide_memory_lists=None, refresh: bool = False) -> dict:
    """The whole inventory + live state. Cached for TTL seconds.

    Fixed registry data and live state only - see the module docstring for the
    list of things this must never contain. `client` is X-Jarvis-Client echoed
    back so a caller can confirm the server saw it (it is NOT used to decide
    anything, the same rule /api/version states).

    ONLY THE UNLOCKED PORTRAIT IS CACHED, and that is a privacy rule rather than
    a performance one. The cache is keyed by nothing, so a locked request that
    hit an unlocked entry would be handed the private counts (memory facts,
    conversations) that the unlocked read was allowed to show - the exact leak
    App lock exists to stop. A locked build therefore bypasses the cache in both
    directions: it never reads it and it never stores into it.
    """
    lock = _private(app_locked=app_locked, hide_memory_lists=hide_memory_lists)
    locked = bool(lock.get("locked"))
    now = time.time()
    if not locked:
        with _CACHE_LOCK:
            if (not refresh and _CACHE["portrait"] is not None
                    and now - _CACHE["at"] < TTL):
                out = dict(_CACHE["portrait"])
                out["client"] = str(client or "")
                return out
    portrait = {
        "schema": SCHEMA,
        "client": str(client or ""),
        "version": version_block(),
        "places": places(),
        "settings": settings(),
        "asks_first": asks_first(),
        "abilities": abilities(),
        "tools": tool_inventory(),
        "plugins": plugins(),
        "stores": stores(lock=lock),
        "private": {"locked": locked,
                    "why": str(lock.get("why") or "")},
    }
    if not locked:
        with _CACHE_LOCK:
            _CACHE["portrait"] = portrait
            _CACHE["at"] = now
    return dict(portrait)


# ---------------------------------------------------------------------------
#   Refresh: re-read now, change nothing, say what moved
# ---------------------------------------------------------------------------

#: Held while one refresh clears and rebuilds, so two callers cannot interleave
#: a cleared cache with the other's read. It guards nothing else: a refresh
#: restarts no server, writes no file and changes no setting.
_REFRESH_LOCK = threading.Lock()


def counts(portrait: Optional[dict] = None) -> dict:
    """The numbers one portrait holds - what a refresh reports and compares.

    Counts only: no name, no title, no setting value. `stored_*` is the three
    stores' own count where it can be read here and None otherwise.

    THE `tools` KEY IS THE TOOLS (2026-11-04). It used to hold the asks-first
    row count (136 on the audit tree), which read as "136 tools" and was handed
    to the model verbatim. It is now `tools_enabled` - the number of tools the
    owner's settings file really offers - with `tools_registered` beside it and
    the old number kept under its true name, `asks_first_rows`. A caller that
    only knows the old key keeps working; it now gets the true number.
    """
    p = portrait if isinstance(portrait, dict) else build()
    ask = p.get("asks_first") or {}
    places = p.get("places") or ()
    stores = {s.get("id"): s.get("count") for s in p.get("stores") or ()
              if isinstance(s, dict)}
    version = p.get("version") or {}
    tools = p.get("tools")
    if not isinstance(tools, dict):
        tools = tool_inventory()
    return {
        "places": len(places),
        "settings": len(p.get("settings") or ()),
        "tools": tools.get("enabled"),
        "tools_enabled": tools.get("enabled"),
        "tools_registered": tools.get("registered"),
        "asks_first_rows": sum(len(g.get("rows") or ())
                               for g in (ask.get("groups") or ())),
        "abilities": len(p.get("abilities") or ()),
        "plugins": len(p.get("plugins") or ()),
        "settings_places": sum(1 for r in places
                               if r.get("kind") == "settings_section"),
        "menu_places": sum(1 for r in places if r.get("kind") == "menu"),
        "stored_memory": stores.get("memory"),
        "stored_conversations": stores.get("conversations"),
        "app_version": version.get("app_version"),
        "started_at": version.get("started_at"),
    }


def _clear_caches() -> None:
    """Forget the built portrait and the deploy block, nothing else. A refresh
    re-reads; it never touches a pending card, a setting or a store."""
    with _CACHE_LOCK:
        _CACHE.update({"at": 0.0, "portrait": None})
    with _STATE_LOCK:
        _STATE_CACHE.update({"at": 0.0, "block": None})


def refresh(*, client: str = "", app_locked=None,
            hide_memory_lists=None) -> dict:
    """POST /api/self/refresh - re-read the inventory and live state NOW.

    The owner asked (2026-11-03) that Jarvis can "refresh its function and
    capabilities awareness". This clears the two caches, rebuilds the portrait
    from the modules as they are at this moment, and answers ONE plain
    sentence naming what moved (the counts and the version). No card: it reads
    nothing from outside the PC, writes nothing, changes no setting, and
    restarts nothing - `started_at` is carried straight through, so a caller
    can see the server is the same process.

    THE PRIVATE VIEW APPLIES HERE TOO. A refresh reports the stores' counts, so
    while App lock or "Hide memory lists and chat history" is on it must
    WITHHOLD them exactly as GET /api/self does - the same request flags are
    threaded through both builds, and nothing in this route can unlock.
    """
    with _REFRESH_LOCK:
        before = counts(build(app_locked=app_locked,
                              hide_memory_lists=hide_memory_lists))
        _clear_caches()
        after_p = build(refresh=True, app_locked=app_locked,
                        hide_memory_lists=hide_memory_lists)
        after = counts(after_p)
    changed = {k: {"before": before.get(k), "after": after.get(k)}
               for k in after if before.get(k) != after.get(k)}
    return {"ok": True, "schema": SCHEMA, "client": str(client or ""),
            "changed": changed, "counts": after,
            "private": dict(after_p.get("private") or {"locked": False, "why": ""}),
            "said": refresh_sentence(changed, after)}


def refresh_sentence(changed: dict, now: dict) -> str:
    """One plain sentence: what a refresh found, in the owner's words.

    Names the numbers it read and, when something moved, exactly which
    number or the version; never claims a capability it cannot count.
    `tools_registered` and `tools_enabled` are named as what they are, so the
    old 136-row confusion cannot come back through this sentence either.
    """
    def _n(value) -> str:
        return "unknown" if value is None else str(value)

    base = (f"{_n(now.get('places'))} places, {_n(now.get('settings'))} settings, "
            f"{_n(now.get('tools_registered'))} tools "
            f"({_n(now.get('tools_enabled'))} switched on in your settings), "
            f"{_n(now.get('asks_first_rows'))} ask-first actions, "
            f"{_n(now.get('plugins'))} plugins and "
            f"{_n(now.get('abilities'))} abilities")
    if not changed:
        return (f"I re-read what I can do and have now: {base}. Everything "
                f"matches what I had. Nothing was restarted.")
    moved = []
    for key, pair in changed.items():
        # `tools` is the same number as `tools_enabled` (kept because the key
        # has always been there), so it is not named twice.
        if key == "tools" and "tools_enabled" in changed:
            continue
        if key in ("started_at", "app_version"):
            moved.append(f"the version ({pair['before']} -> {pair['after']})")
        elif key.startswith("stored_"):
            moved.append(f"{key[len('stored_'):].replace('_', ' ')} "
                         f"({pair['before']} -> {pair['after']})")
        else:
            moved.append(f"{key.replace('_', ' ')} ({pair['before']} -> "
                         f"{pair['after']})")
    return (f"I re-read what I can do and have now: {base}. Changed since I "
            f"last looked: {', '.join(moved)}. Nothing was restarted.")


# ---------------------------------------------------------------------------
#   Conversations: thin adapters over jarvis_chat_log's own routes
# ---------------------------------------------------------------------------


def _chat_log():
    import jarvis_chat_log as CL
    return CL


def conversation_list(query: str = "") -> tuple:
    """GET /api/conversations - the same list GET /api/history answers.

    One truth: this calls jarvis_chat_log's own handler, so the two routes can
    never disagree about what is kept, which page, or what App lock hides.
    """
    return _chat_log().handle_get("/api/history", query)


def conversation_get(cid, query: str = "") -> tuple:
    """GET /api/conversations/<id> - that conversation's turns, or the same
    400/404/503 its own route answers."""
    if not _CID.fullmatch(str(cid or "")):
        return 400, {"error": "need a conversation id"}
    return _chat_log().handle_get("/api/history/conversation", f"id={quote(str(cid))}")


def clear_card_text(conv: dict) -> str:
    """The ONE card's words for deleting one conversation.

    Consequence first and specific (the F6 research's F9, NN/g): the exact
    conversation by title and message count, that it cannot be undone, that
    learned facts are KEPT, and where older copies live. The title cannot
    carry a newline (or a card could be forged into two), and no other text
    from the conversation is quoted.
    """
    title = str(conv.get("title") or "").replace("\r", " ").replace("\n", " ")
    title = title.strip()[:_TITLE_MAX] or "(no title)"
    turns = conv.get("turns") if isinstance(conv.get("turns"), list) else []
    count = len(turns)
    plural = "message" if count == 1 else "messages"
    return "\n".join([
        "Delete ONE conversation from this PC?",
        "",
        f'"{title}" - {count} {plural}.',
        "",
        "It is removed from this PC and this cannot be undone.",
        "The facts Jarvis learned from it are KEPT - deleting a chat never "
        "forgets them. To forget those too, use Forget a time frame.",
        "Copies in older backups stay until they age out.",
        "",
        "Approve to delete this one conversation. Nothing else is touched.",
    ])


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    """The action's tier from the settings file, via jarvis_framework."""
    try:
        import jarvis_framework as fw
        return str(fw.action_tier(action))
    except Exception:                       # noqa: BLE001 - fail closed below
        return ""


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-self-portrait-clear",
                     daemon=True).start()


def _person_said_yes(v) -> bool:
    """The same test jarvis_forget_range uses: a person's own yes, at tier ask."""
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


def _audit(event: str, detail: dict) -> None:
    """Counts and outcomes only: never a title and never a word of the chat."""
    try:
        import jarvis_framework as fw
        fw.audit_log(event, detail)
    except Exception:                       # noqa: BLE001 - bookkeeping only
        pass


def _finish(token: str, outcome: str, why: str = "", message: str = "") -> None:
    with _CLEAR_LOCK:
        p = _CLEAR_STATE["pending"]
        if p and p.get("token") == token:
            _CLEAR_STATE["pending"] = None
        _CLEAR_STATE["last"] = {"outcome": outcome, "why": why,
                                "at": time.time(),
                                "message": message or _LAST_WORDS.get(outcome, "")}


def _decide(job: dict, gate: Callable, tier_of: Callable) -> None:
    """Wait for the ONE card, then delete exactly the id the card named.

    The id is re-read through jarvis_chat_log's own handler BEFORE deleting, so
    an id already deleted or moved while the card was up deletes nothing and
    says so. Deleting a conversation never touches the memory store.
    """
    token, text, cid = job["token"], job["text"], job["id"]
    # `replaces` IS NOT DECORATION (2026-11-03, audit finding): jarvis_gate's
    # replaces_for() gives a card the two-press "REPLACES CURRENT DATA" guard
    # either when its action is in _REPLACES_ACTIONS or when the module that
    # raised it marks its own detail with {"replaces": True}. This card DELETES
    # a kept conversation and cannot be undone, so it must carry the marker:
    # without it one press would delete data while delete_file and
    # memory_forget_range take two. The action itself is deliberately NOT added
    # to _REPLACES_ACTIONS - that table lives in the patch stack, and the marker
    # is the documented route for an action of a module outside it.
    detail = {"text": text, "what": "delete ONE conversation from this PC",
              "conversation_id": cid, "title": job["title"],
              "messages": job["messages"], "leaves_this_pc": False,
              "replaces": True}
    try:
        v = gate(CLEAR_ACTION, detail, text)
    except Exception as exc:                # noqa: BLE001 - a card that failed
        return _finish(token, "refused",
                       f"the approval gate failed ({type(exc).__name__})")
    if getattr(v, "tier", "none") != "ask" or tier_of(CLEAR_ACTION) != "ask":
        return _finish(token, "refused",
                       "the gate answered at a tier that is not a person saying yes")
    if not _person_said_yes(v):
        outcome = getattr(v, "outcome", None)
        if outcome in ("denied", "timed_out"):
            return _finish(token, outcome)
        return _finish(token, "refused", str(getattr(v, "reason", "refused"))[:200])
    try:
        code, _body = _chat_log().handle_get("/api/history/conversation",
                                             f"id={quote(str(cid))}")
        if code != 200:
            return _finish(token, "failed",
                           "the conversation is no longer there, so nothing was deleted")
        if not _chat_log().delete(cid):
            return _finish(token, "failed")
    except Exception as exc:                # noqa: BLE001 - said, never raised
        return _finish(token, "failed", type(exc).__name__)
    _audit("conversations.clear.done", {"messages": int(job["messages"])})
    _finish(token, "done")


def clear_request(body, *, gate: Optional[Callable] = None,
                  tier_of: Optional[Callable] = None,
                  spawn: Optional[Callable] = None) -> tuple:
    """POST /api/conversations/clear - ONE conversation, 202 and ONE card.

    Phase one: this reads that conversation (through jarvis_chat_log's own
    handler, so App lock, 404 and 503 are the same answers the list gives),
    builds the card's words, and raises the card. Phase two runs only after a
    person approves it: _decide deletes that exact id through the existing
    jarvis_chat_log.delete(). There is no bulk form, no cardless form, and the
    model cannot reach the delete without this card.
    """
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "Send a JSON object."}
    if set(body) != {"id"}:
        return 400, {"ok": False, "error": 'Send exactly {"id": "<conversation id>"} - '
                                           'one conversation per request. There is no '
                                           'bulk clear.'}
    cid = body.get("id")
    if not isinstance(cid, str) or not _CID.fullmatch(cid):
        return 400, {"ok": False, "error": "That is not a conversation id."}
    t = tier_of(CLEAR_ACTION)
    if t != "ask":
        return 503, {"ok": False, "error": (
            f"{CLEAR_ACTION} is tier {t!r} in jarvis-framework.toml; deleting a "
            f"conversation needs a person to say yes, so it must be 'ask'")}
    with _CLEAR_LOCK:
        if _CLEAR_STATE["pending"] is not None:
            return 409, {"ok": False, "error": "A card for clearing a conversation is "
                                               "already waiting - answer it first."}
    try:
        code, conv = conversation_get(cid)
    except Exception as exc:                # noqa: BLE001 - said, never raised
        return 503, {"ok": False, "error": f"the chat history could not be read "
                                           f"({type(exc).__name__})"}
    if code == 423:
        return 423, {"ok": False, "error": "Hidden while App lock or \"Hide memory "
                                           "lists and chat history\" is on."}
    if code == 503:
        return 503, {"ok": False, "error": "chat history is not available on this PC"}
    if code != 200:
        return 404, {"ok": False, "error": "no such conversation - it may already "
                                           "have been deleted"}
    if not isinstance(conv, dict):
        return 503, {"ok": False, "error": "the chat history answered in a shape "
                                           "this route does not know"}
    title = str(conv.get("title") or "")
    turns = conv.get("turns") if isinstance(conv.get("turns"), list) else []
    text = clear_card_text(conv)
    token = uuid.uuid4().hex
    with _CLEAR_LOCK:
        if _CLEAR_STATE["pending"] is not None:
            return 409, {"ok": False, "error": "A card for clearing a conversation is "
                                               "already waiting - answer it first."}
        _CLEAR_STATE["pending"] = {"token": token, "since": time.time(),
                                   "id": cid}
    job = {"token": token, "id": cid, "text": text, "title": title,
           "messages": len(turns)}
    try:
        spawn(lambda: _decide(job, gate, tier_of))
    except Exception:                       # noqa: BLE001 - no card, nothing deleted
        with _CLEAR_LOCK:
            _CLEAR_STATE["pending"] = None
        return 503, {"ok": False, "error": "could not raise the approval card"}
    _audit("conversations.clear.asked", {"messages": len(turns)})
    return 202, {"ok": True, "waiting": True, "id": cid, "title": title,
                 "messages": len(turns), "action": CLEAR_ACTION,
                 "message": "Waiting for your approval. Nothing is deleted unless "
                            "you approve the card."}


def clear_status() -> dict:
    """What the last clear card did - for the route's own tests."""
    with _CLEAR_LOCK:
        return {"pending": bool(_CLEAR_STATE["pending"]),
                "last": dict(_CLEAR_STATE["last"]) if _CLEAR_STATE["last"] else None}


# ---------------------------------------------------------------------------
#   The HTTP door
# ---------------------------------------------------------------------------


def _storage_get(route: str, query: str = "") -> tuple:
    """One GET for the storage self-scan module, when it is on this PC.

    That module owns everything about it: the scan, the plan, and the ONE-card
    apply. This is only the door beside the self routes, and its own signature
    is tried first, then the plain route-only call - a shape mismatch is
    answered, never raised, so a missing or older module cannot take the self
    portrait down with it.
    """
    try:
        try:
            return _STORAGE.handle_get(route, query)
        except TypeError:
            return _STORAGE.handle_get(route)
    except Exception as exc:                # noqa: BLE001 - a route that must not crash
        return 503, {"ok": False, "error": f"the storage scan failed ({type(exc).__name__})"}


def _storage_post(route: str, body) -> tuple:
    """One POST for the storage self-scan module. Never raises."""
    try:
        return _STORAGE.handle_post(route, body)
    except Exception as exc:                # noqa: BLE001 - a route that must not crash
        return 503, {"ok": False, "error": f"the storage change failed ({type(exc).__name__})"}


def handle_get(path: str, query: str = "", *, client: str = "",
               app_locked=None, hide_memory_lists=None) -> tuple:
    """One GET, answered. (code, body). Unknown paths are 404 - install()
    never routes a path here that is not in ROUTES (or the storage module's)."""
    route = str(path or "").rstrip("/") or "/"
    if route == SELF_PATH:
        return 200, build(client=client, app_locked=app_locked,
                          hide_memory_lists=hide_memory_lists)
    if route == VERSION_PATH:
        return 200, version_block()
    if route == REFRESH_PATH:
        return 405, {"ok": False, "error": "use POST to refresh the self portrait"}
    if route == CONVERSATIONS_PATH:
        return conversation_list(query)
    if route.startswith(CONVERSATIONS_PATH + "/"):
        cid = route[len(CONVERSATIONS_PATH) + 1:]
        if not cid or "/" in cid:
            return 404, {"error": "no such conversation"}
        return conversation_get(cid, query)
    if route in storage_routes():
        return _storage_get(route, query)
    return 404, {"error": "no such route"}


def handle_post(route: str, body, *, client: str = "",
                app_locked=None, hide_memory_lists=None) -> tuple:
    """One POST, answered. (code, body)."""
    route = str(route or "").rstrip("/")
    if route == REFRESH_PATH:
        return 200, refresh(client=client, app_locked=app_locked,
                            hide_memory_lists=hide_memory_lists)
    if route == CLEAR_PATH:
        return clear_request(body)
    if route in storage_routes():
        return _storage_post(route, body)
    return 404, {"error": "no such route"}


def _flag(value) -> bool:
    try:
        return str(value or "").strip().lower() in ("1", "true", "yes", "on")
    except Exception:                       # noqa: BLE001
        return False


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap do_GET/do_POST so the self portrait and conversation routes answer
    here, after the server's own origin and token checks. Every other request
    goes straight to the original handler - the reason this feature needs no
    patch and no change to jarvis_hud.py."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_self_portrait", False):
        return "  self       What Jarvis knows about itself (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:                   # noqa: BLE001 - fail closed
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/") or "/"
        if not (route in ROUTES or route in storage_routes()
                or route.startswith(CONVERSATIONS_PATH + "/")):
            return get0(self)
        if not _allowed(self):
            return None
        try:
            q = parse_qs(parts.query or "")
            client = str(getattr(self, "headers", {}).get("X-Jarvis-Client", "") or "")
            code, out = handle_get(
                route, parts.query, client=client,
                app_locked=(q.get("app_locked") or [""])[0],
                hide_memory_lists=(q.get("hide_memory_lists") or [""])[0])
        except Exception as exc:            # noqa: BLE001 - a route that must not crash
            code, out = 503, {"error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        storage = storage_routes()
        if route not in ROUTES and route not in storage:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception:                   # noqa: BLE001 - refused in words
            body = None
        try:
            client = str(getattr(self, "headers", {}).get("X-Jarvis-Client", "") or "")
            # The same two flags GET has: a refresh reports counts, so a locked
            # request must withhold them. They can only add withholding.
            q = parse_qs(parts.query or "")
            code, out = handle_post(
                route, body, client=client,
                app_locked=(q.get("app_locked") or [""])[0],
                hide_memory_lists=(q.get("hide_memory_lists") or [""])[0])
        except Exception as exc:            # noqa: BLE001 - a route that must not crash
            code, out = 503, {"error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_self_portrait = True
    do_POST._jarvis_self_portrait = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    try:
        n_places = len(places())
        n_settings = len(settings())
    except Exception:                       # noqa: BLE001 - the banner must print
        n_places = n_settings = 0
    # SAY SO WHEN THE STORAGE SELF-SCAN IS ABSENT, in the start-up banner. The
    # module is PR #1117's and is wired optionally; a deploy without it must not
    # read as "the storage feature is on" by silence, which is the hazard the
    # audit named when the import was hidden behind a built name.
    extra = ("; storage scan beside it" if storage_available()
             else "; storage self-scan NOT installed")
    return (f"  self       Self portrait: {n_places} places, {n_settings} settings "
            f"(GET /api/self, /api/self/version, POST /api/self/refresh, "
            f"/api/conversations; clear needs one card{extra})")


def _reset_for_tests() -> None:
    """Back to a cold cache and no pending card. Never called by a route."""
    _clear_caches()
    with _CLEAR_LOCK:
        _CLEAR_STATE.update({"pending": None, "last": None})


if __name__ == "__main__":
    import sys
    out = build(refresh=True)
    print(f"{SCHEMA}: {len(out['places'])} places, {len(out['settings'])} settings, "
          f"{sum(len(g['rows']) for g in out['asks_first']['groups'])} ask rows, "
          f"{len(out['abilities'])} abilities, {len(out['plugins'])} plugins")
    print(json.dumps(out["version"], indent=1))
    sys.exit(0)
