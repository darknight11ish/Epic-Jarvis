#!/usr/bin/env python3
"""Writes "Show or hide menus"'s contract file for both apps, and checks it.

    python3 tools/gen_menu_cases.py            # write both copies
    python3 tools/gen_menu_cases.py --check    # compare only

What the menu list really is (backend/jarvis_menus.py), made by the real code -
nothing is written by hand:

    jarvis-desktop/tests/fixtures/menu-cases.json
    jarvis-client/app/src/test/resources/contract/menu-cases.json

(byte-identical). The phone's MenuVisibilityTest and the desktop's
tests/menu-visibility.mjs read it, so neither app can carry a different list
of menu ids, groups, never-hideable ids, words, defaults or rules.

The file holds:
  words / replies   every sentence both apps show, and Jarvis's answers
  menus             every menu id: title, one-line description, which apps have
                    it, where it lives, its feature group, its parent, whether
                    it can be hidden, whether it can be folded, why not
  groups            the feature groups, their members per app, whether each app
                    lists them (a group with no member in an app is not listed)
  never_hide        the fixed never-hideable list, with reasons
  aliases           every spoken name Jarvis understands -> a menu or group id
  defaults, migration   where each app stores its choices, and the rules
  state_cases       worked cases of the state machine (hide, show, fold,
                    groups, parents, stale ids, visit overrides, counts)
  sanitize_cases    stored data that must be cleaned on load
  route_cases       X-Jarvis-Route headers and what an app must read from them
  voice_cases       sentences and what Jarvis answers (backend only reads these)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import jarvis_menus as M  # noqa: E402

DESKTOP_APP = M.DESKTOP
PHONE_APP = M.PHONE

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "menu-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "menu-cases.json")
COPIES = (DESKTOP, PHONE)
#: The phone's hardcoded copy of the list (a generated Kotlin file, so 100+ ids are never
#: typed by hand). tests: MenuVisibilityTest holds it to the fixture above.
KOTLIN = (ROOT / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
          / "client" / "net" / "MenuCatalog.kt")
JS_CATALOG = ROOT / "jarvis-desktop" / "src" / "menu-catalog.js"


# --------------------------------------------------------------------------
#   Worked cases (inputs are chosen by hand; every OUTPUT comes from the module)
# --------------------------------------------------------------------------
def _probe_ids(app: str) -> list:
    return [m.id for m in M.MENUS if app in m.apps]


def _run_case(name: str, app: str, start: dict, steps: list, visit: str = "") -> dict:
    st = M.sanitize(M.State.of(start), app) if start.get("_sanitize") else M.State.of(start)
    out_steps = []
    for op, target in steps:
        res = M.apply(st, op, target, app)
        out_steps.append({"op": op, "id": target, "result": res})
    vs = M.visit_set(visit) if visit else frozenset()
    ids = _probe_ids(app)
    return {
        "name": name,
        "app": app,
        "start": {"hidden": sorted(start.get("hidden") or ()),
                  "collapsed": sorted(start.get("collapsed") or ())},
        "steps": out_steps,
        "end": st.as_dict(),
        "visit": visit,
        "hidden": {i: M.is_hidden(st, i, vs) for i in ids},
        "collapsed": {i: M.is_collapsed(st, i, vs) for i in ids
                      if M.menu(i).collapse},
        "hidden_count": M.hidden_count(st, app),
    }


def state_cases() -> list:
    e = {"hidden": [], "collapsed": []}
    return [
        _run_case("hide one menu", "desktop", e, [("hide", "brain.work.quiz")]),
        _run_case("hiding a group stores the group id only", "phone", e,
                  [("hide", "group.finance")]),
        _run_case("a member hidden first is folded into the group", "phone", e,
                  [("hide", "brain.work.retirement"), ("hide", "group.finance")]),
        _run_case("showing a group clears its members too", "phone",
                  {"hidden": ["group.study", "brain.work.quiz"], "collapsed": []},
                  [("show", "group.study")]),
        _run_case("showing one member of a hidden group keeps the others hidden", "desktop", e,
                  [("hide", "group.study"), ("show", "brain.work.quiz")]),
        _run_case("showing a card of a hidden tab shows only that card", "desktop", e,
                  [("hide", "brain.tab.work"), ("show", "brain.work.goals")]),
        _run_case("a card under a hidden tab is hidden and is not counted twice", "desktop", e,
                  [("hide", "brain.tab.work"), ("hide", "brain.work.quiz")]),
        _run_case("a never-hideable menu is refused", "desktop", e,
                  [("hide", "settings.security"), ("hide", "brain.tab.watch"),
                   ("hide", "settings.menu-visibility"), ("hide", "brain.work.coming-up")]),
        _run_case("an unknown id, and an id the other app has, are refused", "desktop", e,
                  [("hide", "settings.no-such-menu"), ("hide", "brain.memory.people-things"),
                   ("hide", "group.home")]),
        _run_case("a group with no member here is refused", "desktop", e,
                  [("hide", "group.home")]),
        _run_case("folding and opening", "phone", e,
                  [("collapse", "brain.work.goals"), ("collapse", "brain.work.quiz"),
                   ("expand", "brain.work.quiz")]),
        _run_case("a menu that cannot be folded is refused", "desktop", e,
                  [("collapse", "brain.tab.work"), ("collapse", "settings.security"),
                   ("collapse", "brain.work.quiz.youtube")]),
        _run_case("folding a group folds its foldable members", "desktop", e,
                  [("collapse", "group.study")]),
        _run_case("showing does not touch the folded set", "desktop",
                  {"hidden": ["brain.work.goals"], "collapsed": ["brain.work.goals"]},
                  [("show", "brain.work.goals")]),
        _run_case("reset clears both sets", "phone",
                  {"hidden": ["group.finance", "settings.voice"], "collapsed": ["brain.work.goals"]},
                  [("reset", "")]),
        _run_case("a link opens a hidden menu for the visit only", "phone",
                  {"hidden": ["group.study"], "collapsed": ["brain.work.quiz"]}, [],
                  visit="brain.work.quiz"),
        _run_case("a link to a card opens its hidden tab for the visit", "desktop",
                  {"hidden": ["brain.tab.work", "brain.work.quiz"], "collapsed": []}, [],
                  visit="brain.work.quiz"),
        _run_case("hiding a parent hides its rows", "phone", e,
                  [("hide", "settings.second-card")]),
        _run_case("a row can be hidden alone", "phone", e,
                  [("hide", "settings.second-card.study-helper")]),
        _run_case("a group counts once", "phone", e,
                  [("hide", "group.graphics-cards"), ("hide", "settings.voice")]),
    ]


def sanitize_cases() -> list:
    cases = []
    for app, start in (
        ("desktop", {"hidden": ["group.study", "settings.old-thing", "settings.security",
                                "group.home", "brain.memory.people-things", "brain.work.quiz",
                                "brain.tab.trust"],
                     "collapsed": ["brain.work.goals", "brain.tab.work", "nonsense",
                                   "settings.security"]}),
        ("phone", {"hidden": ["group.finance", "brain.tab.galaxy", "settings.floating-avatar",
                              "entry.settings", "x"],
                   "collapsed": ["brain.memory.topics", "settings.quick-tiles",
                                 "brain.work.undo"]}),
        ("desktop", {"hidden": [], "collapsed": []}),
    ):
        end = M.sanitize(M.State.of(start), app)
        cases.append({"app": app,
                      "start": {"hidden": sorted(start["hidden"]),
                                "collapsed": sorted(start["collapsed"])},
                      "end": end.as_dict()})
    return cases


def route_cases() -> list:
    def hdr(o) -> str:
        return json.dumps(o, ensure_ascii=False, separators=(",", ":"))

    def parsed(o):
        r = o.get("menu_visibility") if isinstance(o, dict) else None
        if not isinstance(r, dict):
            return None
        a, t = r.get("action"), r.get("target")
        if a not in M.ACTIONS or not isinstance(t, str) or not t:
            return None
        return {"action": a, "target": t}

    raw = [
        {"quick": "menu_visibility", "menu_visibility": {"action": "hide", "target": "group.finance"}},
        {"quick": "menu_visibility", "menu_visibility": {"action": "show", "target": "brain.work.quiz"}},
        {"quick": "menu_visibility", "menu_visibility": {"action": "reset", "target": "all"}},
        {"quick": "menu_visibility", "menu_visibility": {"action": "collapse", "target": "brain.work.goals"}},
        {"quick": "menu_visibility"},
        {"quick": "menu_visibility", "menu_visibility": {"action": "explode", "target": "x"}},
        {"quick": "menu_visibility", "menu_visibility": {"action": "hide"}},
        {"quick": "menu_visibility", "menu_visibility": {"action": "hide", "target": 5}},
        {"quick": "menu_visibility", "menu_visibility": "hide the finance menu"},
        {"open_settings": "voice"},
    ]
    out = [{"header": hdr(o), "parsed": parsed(o)} for o in raw]
    out.append({"header": "not json", "parsed": None})
    out.append({"header": "", "parsed": None})
    return out


def voice_cases() -> list:
    import jarvis_quick as Q  # noqa: E402
    texts = [
        "hide the finance menu", "Hide the Finance menu.", "show the finance menu",
        "unhide the finance menu", "collapse the goals menu", "expand the goals menu",
        "show the quiz menu", "hide the quiz section", "hide the security menu",
        "show the security menu", "collapse the security menu", "hide the what asks first menu",
        "hide the flux menu", "show me the dinner menu", "hide the home menu",
        "show everything", "show all my menus", "unhide my menus", "reset everything",
        "show me the voice settings", "show the voice section", "hide the study menu",
        "hide the second graphics card menu", "collapse the tabs menu",
        "hide the stop everything menu", "hide the crisis help menu",
    ]
    out = []
    for t in texts:
        i = Q.match(t)
        if i is None or i.name != "menu_visibility":
            out.append({"text": t, "quick": i.name if i else None, "reply": None, "route": None})
            continue
        r = Q.run(i, None, 0.0)
        out.append({"text": t, "quick": "menu_visibility", "reply": r.reply,
                    "route": r.menu_visibility})
    return out


def build() -> dict:
    groups = []
    for g in M.GROUPS:
        mem = {a: list(M.members(g.id, a)) for a in M.BOTH}
        groups.append({
            "id": M.GROUP_PREFIX + g.id, "title": g.title, "about": g.about,
            "names": list(g.names), "members": mem,
            "listed": {a: bool(mem[a]) for a in M.BOTH},
        })
    menus = []
    for m in M.MENUS:
        menus.append({
            "id": m.id, "title": m.title, "about": m.about, "apps": list(m.apps),
            "area": m.area, "view": m.view, "kind": m.kind,
            "group": (M.GROUP_PREFIX + m.group) if m.group else None,
            "parent": m.parent, "hide": m.hide, "collapse": m.collapse,
            "why": m.why, "names": list(m.names),
        })
    return {
        "_comment": ("Generated by tools/gen_menu_cases.py from backend/jarvis_menus.py. "
                     "Do not edit by hand."),
        "version": M.VERSION,
        "words": M.WORDS,
        "replies": M.REPLIES,
        "actions": list(M.ACTIONS),
        "group_prefix": M.GROUP_PREFIX,
        "menus": menus,
        "groups": groups,
        "never_hide": [{"id": i, "why": w} for i, w in M.NEVER_HIDE],
        "aliases": dict(sorted(M.aliases().items())),
        "defaults": {
            "hidden": [], "collapsed": [],
            "note": ("Everything visible and unfolded. Advanced tabs on the desktop keep their "
                     "own switch (a tab is shown only when BOTH allow it)."),
            "storage": {
                "desktop": {"hidden_key": "jarvis.menus.hidden",
                            "collapsed_key": "jarvis.menus.collapsed",
                            "version_key": "jarvis.menus.v", "version": M.VERSION,
                            "format": "JSON array of strings, in localStorage, in try/catch"},
                "phone": {"prefs_file": "jarvis_menus", "hidden_key": "hidden",
                          "collapsed_key": "collapsed", "version_key": "v",
                          "version": M.VERSION,
                          "format": "string sets in SharedPreferences, guarded"},
            },
        },
        "migration": [
            {"rule": "first_run",
             "text": "Nothing to migrate: no earlier choice exists. Start with everything visible."},
            {"rule": "stale_ids",
             "text": ("A stored id that no longer exists, or belongs to the other app, is ignored "
                      "silently and dropped the next time the list is saved.")},
            {"rule": "never_ids",
             "text": "A never-hideable id found in the hidden set is ignored and dropped."},
            {"rule": "unknown_version",
             "text": ("A stored version other than 1 is read as empty (everything visible) and is "
                      "not overwritten until the owner changes something.")},
            {"rule": "storage_failure",
             "text": "If storage cannot be read or written, everything shows and nothing crashes."},
            {"rule": "existing_folds",
             "text": ("The Advanced switch, #more-options and 'Hide memory lists and chat history' "
                      "keep their own storage; this store neither reads nor replaces them.")},
        ],
        "state_cases": state_cases(),
        "sanitize_cases": sanitize_cases(),
        "route_cases": route_cases(),
        "voice_cases": voice_cases(),
    }


def _kt(text: str) -> str:
    """A Kotlin string literal."""
    out = []
    for ch in str(text):
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "$":
            out.append("\\$")
        elif ch == "\n":
            out.append("\\n")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def kotlin_source() -> str:
    lines = [
        "package com.jarvis.client.net",
        "",
        "// GENERATED by tools/gen_menu_cases.py from backend/jarvis_menus.py - do not edit by hand.",
        "// Run `python3 tools/gen_menu_cases.py` after changing the list; CI runs `--check`.",
        "// MenuVisibilityTest holds this file to src/test/resources/contract/menu-cases.json.",
        "",
        "/**",
        " * Every menu the phone or the desktop may hide or fold (docs/MENU-VISIBILITY-DESIGN.md,",
        " * docs/JARVIS-API.md section 109). ONE id is ONE feature in both apps; [Menu.phone] says",
        " * whether this app has it. Ids are never reused and never renamed.",
        " */",
        "object MenuCatalog {",
        "    data class Menu(",
        "        val id: String,",
        "        val title: String,",
        "        val about: String,",
        "        val desktop: Boolean,",
        "        val phone: Boolean,",
        "        val area: String,",
        "        val view: String,",
        "        val kind: String,",
        "        val group: String?,",
        "        val parent: String?,",
        "        val hide: Boolean,",
        "        val collapse: Boolean,",
        "        val why: String,",
        "    )",
        "",
        "    data class Group(val id: String, val title: String, val about: String)",
        "",
        f"    const val VERSION = {M.VERSION}",
        f"    const val GROUP_PREFIX = {_kt(M.GROUP_PREFIX)}",
        "",
        "    val GROUPS: List<Group> = listOf(",
    ]
    for g in M.GROUPS:
        lines.append(f"        Group({_kt(M.GROUP_PREFIX + g.id)}, {_kt(g.title)}, {_kt(g.about)}),")
    lines += [")".rjust(5), "", "    val MENUS: List<Menu> = listOf("]
    for m in M.MENUS:
        grp = _kt(M.GROUP_PREFIX + m.group) if m.group else "null"
        par = _kt(m.parent) if m.parent else "null"
        lines.append(
            f"        Menu({_kt(m.id)}, {_kt(m.title)}, {_kt(m.about)}, "
            f"{str(DESKTOP_APP in m.apps).lower()}, {str(PHONE_APP in m.apps).lower()}, "
            f"{_kt(m.area)}, {_kt(m.view)}, {_kt(m.kind)}, {grp}, {par}, "
            f"{str(m.hide).lower()}, {str(m.collapse).lower()}, {_kt(m.why)}),")
    lines += [")".rjust(5), "", "    /** The fixed never-hideable list (design section 5); a test fails if one is hideable. */",
              "    val NEVER_HIDE: List<String> = listOf("]
    for i, _ in M.NEVER_HIDE:
        lines.append(f"        {_kt(i)},")
    lines += [")".rjust(5), "}", "", "/** The words both apps show, word for word (the fixture's `words`). */", "object MenuWords {"]
    for k, v in M.WORDS.items():
        lines.append(f"    const val {k.upper()} = {_kt(v)}")
    lines += ["}", ""]
    return "\n".join(lines)


def js_source(doc: dict) -> str:
    lines = [
        "// GENERATED by tools/gen_menu_cases.py from backend/jarvis_menus.py - do not edit by hand.",
        "// Run `python3 tools/gen_menu_cases.py` after changing the list; CI runs `--check`.",
        "",
        f"export const VERSION = {json.dumps(doc['version'])};",
        f"export const GROUP_PREFIX = {json.dumps(doc['group_prefix'])};",
        f"export const WORDS = {json.dumps(doc['words'], indent=2)};",
        f"export const REPLIES = {json.dumps(doc['replies'], indent=2)};",
        f"export const ACTIONS = {json.dumps(doc['actions'])};",
        f"export const GROUPS = {json.dumps(doc['groups'], indent=2)};",
        f"export const MENUS = {json.dumps(doc['menus'], indent=2)};",
        f"export const NEVER_HIDE = {json.dumps([n['id'] for n in doc['never_hide']], indent=2)};",
        f"export const ALIASES = {json.dumps(doc['aliases'], indent=2)};",
        f"export const DEFAULTS = {json.dumps(doc['defaults'], indent=2)};",
        f"export const MIGRATION = {json.dumps(doc['migration'], indent=2)};",
        "",
    ]
    return "\n".join(lines)


def document() -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    b = build()
    doc = json.dumps(b, indent=2, ensure_ascii=False) + "\n"
    kt = kotlin_source()
    js = js_source(b)
    targets = [(p, doc) for p in COPIES] + [(KOTLIN, kt), (JS_CATALOG, js)]
    if "--check" in sys.argv:
        bad = [p for p, text in targets
               if not p.exists() or p.read_text(encoding="utf-8") != text]
        for p in bad:
            print(f"STALE {p.relative_to(ROOT)} - run python3 tools/gen_menu_cases.py")
        if not bad:
            print("menu-cases.json (both copies), MenuCatalog.kt and menu-catalog.js match")
        return 1 if bad else 0
    for p, text in targets:
        p.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n": without it the .json, .kt and .js below come out CRLF on
        # Windows and LF elsewhere (the repository is LF everywhere).
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
